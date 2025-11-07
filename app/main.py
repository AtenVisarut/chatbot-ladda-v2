"""
LINE Plant Disease Detection Bot with OpenAI Vision and Supabase RAG
Production-grade FastAPI implementation
Minimal RAG output (5 fields): ชื่อสินค้า, สารสำคัญ, ศัตรูพืช, ใช้ได้กับพืช, วิธีใช้
Friendly Thai output (single long text block)
"""

import os
import logging
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import httpx
import base64
import hashlib
import hmac
import json
from dotenv import load_dotenv
from supabase import create_client, Client
from openai import OpenAI

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="LINE Plant Disease Detection Bot",
    description="AI-powered plant disease detection with product recommendations",
    version="1.0.0"
)

# ============================================================================#
# ENVIRONMENT / SERVICES
# ============================================================================#
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

required_env_vars = {
    "LINE_CHANNEL_ACCESS_TOKEN": LINE_CHANNEL_ACCESS_TOKEN,
    "LINE_CHANNEL_SECRET": LINE_CHANNEL_SECRET,
    "OPENAI_API_KEY": OPENAI_API_KEY,
    "SUPABASE_URL": SUPABASE_URL,
    "SUPABASE_KEY": SUPABASE_KEY,
}
for var_name, var_value in required_env_vars.items():
    if not var_value:
        logger.error(f"Missing required environment variable: {var_name}")

# Initialize OpenAI
openai_client = None
if OPENAI_API_KEY:
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
    logger.info("OpenAI initialized successfully")

# Initialize Supabase
supabase_client: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Supabase initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Supabase: {e}")

# ============================================================================#
# Pydantic Models
# ============================================================================#
class LineWebhookEvent(BaseModel):
    type: str
    message: Optional[Dict[str, Any]] = None
    replyToken: str
    source: Dict[str, Any]
    timestamp: int

class DiseaseDetectionResult(BaseModel):
    disease_name: str
    confidence: str
    symptoms: str
    severity: str
    raw_analysis: str

class ProductRecommendation(BaseModel):
    product_name: str
    active_ingredient: Optional[str] = ""
    target_pest: Optional[str] = ""
    applicable_crops: Optional[str] = ""
    how_to_use: Optional[str] = ""
    score: float = 0.0

# ============================================================================#
# Helpers
# ============================================================================#
def verify_line_signature(body: bytes, signature: str) -> bool:
    if not LINE_CHANNEL_SECRET:
        logger.warning("LINE_CHANNEL_SECRET not set, skipping signature verification")
        return True
    hash_digest = hmac.new(
        LINE_CHANNEL_SECRET.encode('utf-8'),
        body,
        hashlib.sha256
    ).digest()
    expected_signature = base64.b64encode(hash_digest).decode('utf-8')
    return hmac.compare_digest(signature, expected_signature)

async def get_image_content_from_line(message_id: str) -> bytes:
    url = f"https://api-data.line.me/v2/bot/message/{message_id}/content"
    headers = {"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.content

def _resolve_meta_field(metadata: dict, *keys: List[str]) -> str:
    """
    Return first non-empty metadata value among provided keys.
    keys may be canonical english key or various thai variants (unicode variants included).
    """
    for k in keys:
        if not k:
            continue
        v = metadata.get(k)
        if v and isinstance(v, str) and v.strip():
            return v.strip()
    return ""

# ============================================================================#
# Core: Detect disease (OpenAI Vision)
# ============================================================================#
async def detect_disease(image_bytes: bytes) -> DiseaseDetectionResult:
    logger.info("Starting pest/disease detection with OpenAI Vision")
    try:
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        prompt = """คุณคือผู้เชี่ยวชาญด้านโรคพืชและศัตรูพืชของกรมวิชาการเกษตรไทย ทำงานวิเคราะห์ภาพพืชจากภาพถ่ายภาคสนาม

ให้คุณวิเคราะห์ภาพพืชนี้เพื่อระบุว่าเป็น:
1. เชื้อรา (Fungus) - เช่น แอนแทรคโนส, ใบไหม้, ราน้ำค้าง, ราสนิม
2. ไวรัส (Virus) - เช่น โรคใบด่าง, โรคใบหงิก
3. ศัตรูพืช (Pest) - เช่น เพลี้ยไฟ, หนอน, แมลง, ไร
4. วัชพืช  (Weed) - หญ้า, กก, หนวด

ห้ามสร้างโรคที่ไม่มีจริง และห้ามเดาโดยไม่มีหลักฐานในภาพ

ให้ตอบ **ONLY JSON** 100% ไม่ต้องอธิบายเพิ่ม ไม่ต้องมี markdown code block

Format JSON:
{
  "disease_name": "ชื่อเชื้อรา/ไวรัส/ศัตรูพืช",
  "pest_type": "เชื้อรา/ไวรัส/ศัตรูพืช",
  "confidence_level_percent": 0-100,
  "confidence": "สูง/ปานกลาง/ต่ำ",
  "symptoms_in_image": "อาการที่เห็นในภาพ",
  "symptoms": "รายละเอียดอาการ",
  "possible_cause": "สาเหตุที่เป็นไปได้",
  "severity_level": "รุนแรง/ปานกลาง/เล็กน้อย",
  "severity": "ระดับความรุนแรง",
  "description": "คำอธิบายเพิ่มเติม"
}

Rules:
- หากไม่พบปัญหา ให้ disease_name = "ไม่พบปัญหา"
- pest_type ต้องระบุเป็น "เชื้อรา", "ไวรัส", หรือ "ศัตรูพืช ,วัชพืช"
- confidence ให้เป็นตัวเลข 0-100 (หากมี) หรือ เป็นคำ (สูง/ปานกลาง/ต่ำ)
- severity ให้เลือกจากรายการหรือคำที่เหมาะสม
- ห้ามใส่วิธีรักษาในผลลัพธ์ JSON"""
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=800
        )
        raw_text = response.choices[0].message.content
        logger.info(f"OpenAI raw response: {raw_text}")

        # Extract JSON flexibly
        try:
            json_str = raw_text.strip()
            if json_str.startswith("```"):
                # remove code fences and find JSON part
                parts = json_str.split("```")
                for p in parts:
                    p_s = p.strip()
                    if p_s.startswith("{") and p_s.endswith("}"):
                        json_str = p_s
                        break
            # find first { ... } block if extra text present
            if "{" in json_str and "}" in json_str:
                start = json_str.find("{")
                end = json_str.rfind("}") + 1
                json_str = json_str[start:end]
            data = json.loads(json_str)
        except Exception as e:
            logger.warning(f"Failed to parse JSON from OpenAI response: {e}", exc_info=True)
            data = {"disease_name": "ไม่ทราบชื่อโรค", "confidence": "ปานกลาง", "symptoms": "", "severity": "ปานกลาง", "description": raw_text}

        # Map many possible keys to canonical fields
        disease_name = data.get("disease_name") or data.get("disease") or data.get("โรค") or "ไม่ทราบชื่อโรค"
        # confidence prefer numeric percent if provided
        confidence = ""
        if "confidence_level_percent" in data:
            confidence = str(data.get("confidence_level_percent"))
        elif "confidence" in data:
            confidence = str(data.get("confidence"))
        elif "confidence_percent" in data:
            confidence = str(data.get("confidence_percent"))
        else:
            confidence = "ปานกลาง"
        # symptoms
        symptoms = data.get("symptoms_in_image") or data.get("symptoms") or data.get("อาการ") or ""
        # severity
        severity = data.get("severity_level") or data.get("severity") or data.get("ความรุนแรง") or "ปานกลาง"
        # description / raw
        description = data.get("description") or data.get("possible_cause") or raw_text

        # Extract pest_type
        pest_type = data.get("pest_type") or "ศัตรูพืช"
        
        result = DiseaseDetectionResult(
            disease_name=str(disease_name),
            confidence=str(confidence),
            symptoms=str(symptoms),
            severity=str(severity),
            raw_analysis=f"{pest_type}: {description}"
        )
        logger.info(f"Pest/Disease detected: {result.disease_name} (Type: {pest_type})")
        return result

    except Exception as e:
        logger.error(f"Error in pest/disease detection: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Detection failed: {str(e)}")

# ============================================================================#
# Core: Retrieve product recommendations (minimal RAG with Supabase)
# ============================================================================#
async def retrieve_product_recommendation(disease_info: DiseaseDetectionResult) -> List[ProductRecommendation]:
    """
    Query Supabase with embedding of disease keywords and return top product candidates.
    Minimal RAG: return only 5 fields (product_name, active_ingredient, target_pest, applicable_crops, how_to_use)
    """
    try:
        logger.info(f"Retrieve products for: {disease_info.disease_name}")

        if not supabase_client:
            logger.warning("Supabase not configured")
            return []

        if not openai_client:
            logger.warning("OpenAI not configured")
            return []

        # Extract pest type from raw_analysis
        pest_type = ""
        if "เชื้อรา" in disease_info.raw_analysis:
            pest_type = "เชื้อรา โรคพืช ป้องกันโรค"
        elif "ไวรัส" in disease_info.raw_analysis:
            pest_type = "ไวรัส โรคพืช ป้องกันโรค"
        elif "ศัตรูพืช" in disease_info.raw_analysis:
            pest_type = "ศัตรูพืช แมลง หนอน เพลี้ย"
        elif "วัชพืข" in disease_info.raw_analysis:
            pest_type = "หญ้า กก หนวด" 

        # Build enhanced query with multiple strategies
        keywords = []
        
        # Add disease name
        if disease_info.disease_name and disease_info.disease_name != "ไม่พบปัญหา":
            keywords.append(disease_info.disease_name)
        
        # Add pest type
        if pest_type:
            keywords.append(pest_type)
        
        # Add symptoms (extract key terms)
        if disease_info.symptoms:
            # Extract key symptom words
            symptom_keywords = []
            for word in ["เพลี้ย", "หนอน", "แมลง", "ไร", "รา", "ไวรัส", "ใบไหม้", "ใบจุด", "แอนแทรคโนส","หญ้า","หนวด","กก"]:
                if word in disease_info.symptoms:
                    symptom_keywords.append(word)
            if symptom_keywords:
                keywords.extend(symptom_keywords)
        
        # Create query text with emphasis on disease name
        if keywords:
            query_text = " ".join(keywords[:1] * 3 + keywords[1:])  # Repeat first keyword 3 times
        else:
            query_text = "ป้องกันกำจัดศัตรูพืช"
        
        logger.info(f"Query text: {query_text}")

        # Generate embedding
        try:
            emb_resp = openai_client.embeddings.create(model="text-embedding-3-small", input=query_text)
            query_vec = emb_resp.data[0].embedding
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}", exc_info=True)
            return []

        # Use keyword-based search (more reliable than vector search for Thai)
        matches = []
        
        # Extract search keywords
        search_keywords = []
        
        # Common pest/disease keywords
        pest_keywords = ["เพลี้ย", "หนอน", "แมลง", "ไร", "รา", "ไวรัส", "โรค", 
                        "ใบไหม้", "ใบจุด", "แอนแทรคโนส", "ราน้ำค้าง", "ราสนิม",
                        "เพลี้ยไฟ", "เพลี้ยแป้ง", "หนอนกอ", "หนอนม้วนใบ","กก","หนวด"]
        
        # Extract keywords from disease name and symptoms
        text_to_search = f"{disease_info.disease_name} {disease_info.symptoms}".lower()
        for keyword in pest_keywords:
            if keyword in text_to_search:
                search_keywords.append(keyword)
        
        # If no specific keywords found, use disease name
        if not search_keywords and disease_info.disease_name:
            search_keywords = [disease_info.disease_name]
        
        logger.info(f"Search keywords: {search_keywords}")
        
        # Search database with keywords
        try:
            all_matches = []
            seen_ids = set()
            
            for keyword in search_keywords[:3]:  # Limit to top 3 keywords
                response = supabase_client.table('products').select('*').or_(
                    f'target_pest.ilike.%{keyword}%,product_name.ilike.%{keyword}%'
                ).limit(10).execute()
                
                if response.data:
                    for item in response.data:
                        if item['id'] not in seen_ids:
                            # Calculate simple relevance score
                            score = 0.5
                            if keyword in item.get('target_pest', '').lower():
                                score += 0.3
                            if keyword in item.get('product_name', '').lower():
                                score += 0.2
                            
                            all_matches.append({'similarity': min(score, 1.0), **item})
                            seen_ids.add(item['id'])
            
            # Sort by similarity score
            matches = sorted(all_matches, key=lambda x: x['similarity'], reverse=True)[:10]
            logger.info(f"Keyword search found {len(matches)} products")
            
        except Exception as e:
            logger.error(f"Keyword search failed: {e}", exc_info=True)
            return []
        
        if not matches:
            logger.warning("No matches found with keyword search")
            return []

        # Keep best score per product_name (group rows of same product)
        product_map: Dict[str, Dict[str, Any]] = {}
        for match in matches:
            score = match.get("similarity", 0)
            # Handle both direct fields and metadata
            if "metadata" in match and match["metadata"]:
                try:
                    metadata = json.loads(match["metadata"]) if isinstance(match["metadata"], str) else match["metadata"]
                except:
                    metadata = match
            else:
                metadata = match
            
            # resolve product_name with variants
            pname = (match.get("product_name") or 
                    metadata.get("product_name") or 
                    metadata.get("ชื่อสินค้า (ชื่อการค้า)") or
                    metadata.get("ชื่อสินค้า") or
                    "ไม่ระบุชื่อ")

            prev = product_map.get(pname)
            if prev is None or score > prev["score"]:
                product_map[pname] = {"score": score, "metadata": metadata, "match": match}

        # Build recommendations sorted by score
        sorted_products = sorted(product_map.items(), key=lambda x: x[1]["score"], reverse=True)

        recommendations: List[ProductRecommendation] = []
        for pname, info in sorted_products:
            score = info["score"]
            match = info["match"]
            metadata = info["metadata"] or {}

            # extract minimal 5 fields - try direct fields first, then metadata
            active = (match.get("active_ingredient") or 
                     metadata.get("active_ingredient") or 
                     metadata.get("สารสำคัญ") or 
                     metadata.get("สารสําคัญ") or "")
            pest = (match.get("target_pest") or 
                   metadata.get("target_pest") or 
                   metadata.get("ศัตรูพืช") or 
                   metadata.get("ศัตรูพืชที่กำจัดได้") or "")
            crops = (match.get("applicable_crops") or 
                    metadata.get("applicable_crops") or 
                    metadata.get("ใช้ได้กับพืช") or "")
            howto = (match.get("how_to_use") or 
                    metadata.get("how_to_use") or 
                    metadata.get("วิธีใช้") or "")

            # Skip if no pest info
            if not pest or pest.strip() == "":
                continue

            rec = ProductRecommendation(
                product_name=pname,
                active_ingredient=active,
                target_pest=pest,
                applicable_crops=crops,
                how_to_use=howto,
                score=float(score)
            )
            recommendations.append(rec)
            # limit number returned (keep top 5 for better coverage)
            if len(recommendations) >= 5:
                break

        logger.info(f"Returning {len(recommendations)} recommendations")
        return recommendations

    except Exception as e:
        logger.error(f"Error retrieving product recommendations: {e}", exc_info=True)
        return []

def _get_mock_recommendations(disease_info: DiseaseDetectionResult) -> List[ProductRecommendation]:
    logger.warning("Returning empty/mock recommendations")
    return []

# ============================================================================#
# Core: Generate final response (single long text block, friendly Thai)
# ============================================================================#
async def generate_final_response(
    disease_info: DiseaseDetectionResult,
    recommendations: List[ProductRecommendation]
) -> str:
    try:
        logger.info("Generating final response (Thai friendly minimal RAG)")

        # Header: disease summary
        header = f"ผลตรวจจากภาพ: {disease_info.disease_name}\n\n"
        header += f"ระดับความมั่นใจ: {disease_info.confidence}\n"
        header += f"ความรุนแรง: {disease_info.severity}\n\n"
        header += f"อาการที่เห็น: {disease_info.symptoms}\n\n"

        if not recommendations:
            body = "⚠️ ขณะนี้ยังไม่มีข้อมูลผลิตภัณฑ์ที่ตรงกับอาการในฐานข้อมูลของเรา\n"
            body += "แนะนำ: เก็บตัวอย่างหรือปรึกษาผู้เชี่ยวชาญก่อนใช้สารป้องกันกำจัด\n"
            body += "หากต้องการให้ช่วยอีกครั้ง ส่งรูปภาพเพิ่มหรือลองถ่ายมุมอื่นนะครับ 😊"
            return header + body

        # Build product blocks (minimal fields)
        body = "สินค้าแนะนำ:\n"
        for rec in recommendations:
            body += f"\n• {rec.product_name}\n"
            if rec.active_ingredient:
                body += f"- สารสำคัญ: {rec.active_ingredient}\n"
            if rec.target_pest:
                body += f"- ศัตรูพืชเป้าหมาย: {rec.target_pest}\n"
            if rec.applicable_crops:
                body += f"- ใช้ได้กับพืช: {rec.applicable_crops}\n"
            # friendly short how-to: if long, take first line
            if rec.how_to_use:
                short_how = rec.how_to_use.split("\n")[0].strip()
                body += f"- วิธีใช้ (สรุป): {short_how}\n"
            body += f"- ความเกี่ยวข้อง: {int(rec.score * 100)}%\n"

        footer = "\nหมายเหตุ: ปรับอัตรา/ปริมาณตามฉลากจริงก่อนใช้ทุกครั้งครับ\nหากต้องการข้อมูลเพิ่ม ส่งรูปหรือถามมาได้เลย 😊"
        return header + body + footer

    except Exception as e:
        logger.error(f"Error generating final response: {e}", exc_info=True)
        # fallback simple template
        products_text = "\n".join([f"• {p.product_name}" for p in (recommendations or [])[:3]])
        return f"ผลการวิเคราะห์: {disease_info.disease_name}\n\nผลิตภัณฑ์แนะนำ:\n{products_text}\n\nโปรดตรวจสอบฉลากก่อนใช้"

# ============================================================================#
# LINE reply helper
# ============================================================================#
async def reply_line(reply_token: str, message: str) -> None:
    try:
        logger.info(f"Replying to LINE token: {reply_token[:10]}...")
        url = "https://api.line.me/v2/bot/message/reply"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
        }
        payload = {"replyToken": reply_token, "messages": [{"type": "text", "text": message}]}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
        logger.info("Reply sent to LINE")
    except Exception as e:
        logger.error(f"Error sending LINE reply: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to send LINE reply: {str(e)}")

# ============================================================================#
# API endpoints (unchanged flow)
# ============================================================================#
@app.get("/")
async def root():
    return {"status": "ok", "service": "LINE Plant Disease Detection Bot", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "services": {
            "openai": "ok" if OPENAI_API_KEY else "not_configured",
            "supabase": "ok" if supabase_client else "not_configured",
            "line": "ok" if LINE_CHANNEL_ACCESS_TOKEN else "not_configured"
        }
    }

@app.post("/webhook")
async def webhook(
    request: Request,
    x_line_signature: str = Header(None, alias="X-Line-Signature")
):
    try:
        body = await request.body()
        if x_line_signature and not verify_line_signature(body, x_line_signature):
            logger.warning("Invalid LINE signature")
            raise HTTPException(status_code=403, detail="Invalid signature")
        webhook_data = json.loads(body.decode("utf-8"))
        events = webhook_data.get("events", [])
        logger.info(f"Received {len(events)} events from LINE")
        for event in events:
            event_type = event.get("type")
            reply_token = event.get("replyToken")
            if event_type == "message":
                message = event.get("message", {})
                message_type = message.get("type")
                if message_type == "image":
                    message_id = message.get("id")
                    try:
                        image_bytes = await get_image_content_from_line(message_id)
                        disease_result = await detect_disease(image_bytes)
                        recommendations = await retrieve_product_recommendation(disease_result)
                        final_message = await generate_final_response(disease_result, recommendations)
                        await reply_line(reply_token, final_message)
                    except Exception as e:
                        logger.error(f"Error processing image event: {e}", exc_info=True)
                        error_message = "ขออภัยค่ะ เกิดข้อผิดพลาดในการวิเคราะห์รูปภาพ กรุณาลองใหม่อีกครั้งค่ะ 🙏"
                        await reply_line(reply_token, error_message)
                elif message_type == "text":
                    text = message.get("text", "")
                    help_message = """สวัสดีค่ะ! 🌱

ส่งรูปภาพพืชที่ต้องการตรวจสอบมาให้ฉัน ฉันจะวิเคราะห์และแนะนำผลิตภัณฑ์ที่เหมาะสมให้ค่ะ
"""
                    await reply_line(reply_token, help_message)
        return JSONResponse(content={"status": "ok"})
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================#
# Startup
# ============================================================================#
@app.on_event("startup")
async def startup_event():
    logger.info("=" * 60)
    logger.info("Starting LINE Plant Pest & Disease Detection Bot")
    logger.info(f"OpenAI API: {'✓' if OPENAI_API_KEY else '✗'}")
    logger.info(f"Supabase: {'✓' if supabase_client else '✗'}")
    logger.info(f"LINE Bot: {'✓' if LINE_CHANNEL_ACCESS_TOKEN else '✗'}")
    logger.info("=" * 60)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
