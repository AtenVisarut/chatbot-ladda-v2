"""
LINE Plant Disease Detection Bot with OpenAI Vision and Supabase RAG
Production-grade FastAPI implementation with Multi-Agent System
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

# LightRAG disabled due to compatibility issues
# Using Supabase + keyword search (works better with Thai language)
LIGHTRAG_AVAILABLE = False

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
    description="AI-powered plant disease detection with Multi-Agent System",
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

# Initialize Supabase (fallback)
supabase_client: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Supabase initialized successfully (fallback)")
    except Exception as e:
        logger.error(f"Failed to initialize Supabase: {e}")

# LightRAG disabled - using Supabase instead
lightrag_instance = None

# In-memory store for pending image contexts awaiting user symptom input
# Keyed by user_id -> dict with image_bytes and reply_token (optional)
pending_image_contexts: Dict[str, Dict[str, Any]] = {}

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
async def detect_disease(image_bytes: bytes, extra_user_info: Optional[str] = None) -> DiseaseDetectionResult:
    logger.info("Starting pest/disease detection with OpenAI Vision")
    try:
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        prompt = """คุณคือผู้เชี่ยวชาญด้านโรคพืชและศัตรูพืชของกรมวิชาการเกษตรไทย มีประสบการณ์ 20 ปี

🎯 **ภารกิจ**: วิเคราะห์ภาพพืชเพื่อระบุปัญหาอย่างแม่นยำ

📋 **ขั้นตอนการวิเคราะห์**:
1. สังเกตอาการบนใบ/ลำต้น/ผล อย่างละเอียด
2. ระบุสี รูปร่าง และลักษณะของความเสียหาย
3. มองหาแมลง ไข่ หรือร่องรอยของศัตรูพืช
4. ประเมินความรุนแรงจากพื้นที่ที่เสียหาย

🔍 **จำแนกประเภท**:
- **เชื้อรา (Fungus)**: จุดสีน้ำตาล/ดำ, แผลเปียก, ราขาว, ใบไหม้
- **ไวรัส (Virus)**: ใบด่าง, ใบหงิก, เส้นใบเหลือง, แคระแกร็น
- **ศัตรูพืช (Pest)**: เห็นแมลง, รอยกัด, ใบม้วน, มีเยื่อใย
- **วัชพืช (Weed)**: พืชแปลกปลอมในแปลง

⚠️ **ข้อควรระวัง**:
- ห้ามเดาโดยไม่มีหลักฐานในภาพ
- ถ้าไม่แน่ใจ ให้ระบุ confidence ต่ำ
- ถ้าภาพไม่ชัด ให้ระบุว่า "ต้องการภาพเพิ่มเติม"

📤 **ตอบเป็น JSON เท่านั้น** (ไม่ต้องมี markdown):

{
  "disease_name": "ชื่อเฉพาะเจาะจง เช่น เพลี้ยไฟ, แอนแทรคโนส, ราน้ำค้าง",
  "pest_type": "เชื้อรา/ไวรัส/ศัตรูพืช/วัชพืช",
  "confidence_level_percent": 0-100,
  "confidence": "สูง/ปานกลาง/ต่ำ",
  "symptoms_in_image": "อาการที่เห็นชัดในภาพ (สั้นๆ)",
  "symptoms": "รายละเอียดอาการทั้งหมด รวมสี ตำแหน่ง ขนาด",
  "possible_cause": "สาเหตุที่เป็นไปได้ และปัจจัยเสี่ยง",
  "severity_level": "รุนแรง/ปานกลาง/เล็กน้อย",
  "severity": "ระดับความรุนแรง พร้อมเหตุผล",
  "description": "คำอธิบายเพิ่มเติม และข้อแนะนำเบื้องต้น",
  "affected_area": "ส่วนของพืชที่ได้รับผลกระทบ",
  "spread_risk": "ความเสี่ยงการแพร่กระจาย (สูง/ปานกลาง/ต่ำ)"
}

✅ หากไม่พบปัญหา: disease_name = "ไม่พบปัญหา", confidence = "สูง" """

        # If user provided extra observation text, include it as additional context
        if extra_user_info:
            prompt += f"\n\nเพิ่มเติมจากผู้ใช้: {extra_user_info}"

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
        
        # Extract additional fields for better analysis
        affected_area = data.get("affected_area") or ""
        spread_risk = data.get("spread_risk") or ""
        
        # Build comprehensive raw_analysis
        raw_parts = [f"{pest_type}: {description}"]
        if affected_area:
            raw_parts.append(f"ส่วนที่ได้รับผลกระทบ: {affected_area}")
        if spread_risk:
            raw_parts.append(f"ความเสี่ยงการแพร่: {spread_risk}")
        
        result = DiseaseDetectionResult(
            disease_name=str(disease_name),
            confidence=str(confidence),
            symptoms=str(symptoms),
            severity=str(severity),
            raw_analysis=" | ".join(raw_parts)
        )
        
        # Check confidence level and warn if low
        confidence_num = 0
        try:
            if confidence.replace("%", "").replace("สูง", "90").replace("ปานกลาง", "60").replace("ต่ำ", "30").isdigit():
                confidence_num = int(confidence.replace("%", "").replace("สูง", "90").replace("ปานกลาง", "60").replace("ต่ำ", "30"))
        except:
            pass
        
        if confidence_num < 50 or "ต่ำ" in confidence:
            logger.warning(f"Low confidence detection: {result.disease_name} ({confidence})")
        
        logger.info(f"Pest/Disease detected: {result.disease_name} (Type: {pest_type}, Confidence: {confidence})")
        
        # Log detection for analysis (optional - can be used to improve accuracy)
        try:
            import datetime
            log_entry = {
                "timestamp": datetime.datetime.now().isoformat(),
                "disease_name": result.disease_name,
                "pest_type": pest_type,
                "confidence": confidence,
                "severity": result.severity,
                "has_user_input": bool(extra_user_info)
            }
            # Could save to file or database for later analysis
            logger.debug(f"Detection log: {log_entry}")
        except Exception as e:
            logger.warning(f"Failed to log detection: {e}")
        
        return result

    except Exception as e:
        logger.error(f"Error in pest/disease detection: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Detection failed: {str(e)}")

# ============================================================================#
# Core: Retrieve product recommendations (LightRAG or Supabase fallback)
# ============================================================================#
async def retrieve_product_recommendation(disease_info: DiseaseDetectionResult) -> List[ProductRecommendation]:
    """
    Query LightRAG (preferred) or Supabase (fallback) for product recommendations.
    Minimal RAG: return only 5 fields (product_name, active_ingredient, target_pest, applicable_crops, how_to_use)
    """
    try:
        logger.info(f"Retrieve products for: {disease_info.disease_name}")
        
        # Try LightRAG first
        if lightrag_instance:
            return await retrieve_with_lightrag(disease_info)
        
        # Fallback to Supabase
        logger.info("Using Supabase fallback")
        return await retrieve_with_supabase(disease_info)
        
    except Exception as e:
        logger.error(f"Error retrieving product recommendations: {e}", exc_info=True)
        return []

async def retrieve_with_lightrag(disease_info: DiseaseDetectionResult) -> List[ProductRecommendation]:
    """Query products using LightRAG"""
    try:
        logger.info("Using LightRAG for product search")
        
        # Extract pest type
        pest_type = ""
        if "เชื้อรา" in disease_info.raw_analysis:
            pest_type = "เชื้อรา โรคพืช"
        elif "ไวรัส" in disease_info.raw_analysis:
            pest_type = "ไวรัส โรคพืช"
        elif "ศัตรูพืช" in disease_info.raw_analysis:
            pest_type = "ศัตรูพืช แมลง"
        elif "วัชพืช" in disease_info.raw_analysis:
            pest_type = "วัชพืช หญ้า"
        
        # Build query
        query_parts = []
        if disease_info.disease_name and disease_info.disease_name != "ไม่พบปัญหา":
            query_parts.append(disease_info.disease_name)
        if pest_type:
            query_parts.append(pest_type)
        if disease_info.symptoms:
            query_parts.append(disease_info.symptoms[:100])
        
        query_text = " ".join(query_parts) if query_parts else "ผลิตภัณฑ์ป้องกันกำจัดศัตรูพืช"
        
        logger.info(f"LightRAG query: {query_text}")
        
        # Query LightRAG with hybrid mode for best results
        result = lightrag_instance.query(
            query_text,
            param=QueryParam(
                mode="hybrid",  # Use hybrid mode (combines local + global)
                top_k=10,
                max_token_for_text_unit=4000,
                max_token_for_global_context=8000,
                max_token_for_local_context=4000
            )
        )
        
        logger.info(f"LightRAG result length: {len(result) if result else 0}")
        
        # Parse LightRAG result to extract product recommendations
        recommendations = parse_lightrag_result(result, disease_info)
        
        logger.info(f"Parsed {len(recommendations)} recommendations from LightRAG")
        return recommendations[:5]  # Return top 5
        
    except Exception as e:
        logger.error(f"LightRAG query failed: {e}", exc_info=True)
        # Fallback to Supabase
        return await retrieve_with_supabase(disease_info)

def parse_lightrag_result(result: str, disease_info: DiseaseDetectionResult) -> List[ProductRecommendation]:
    """Parse LightRAG text result into ProductRecommendation objects"""
    try:
        recommendations = []
        
        if not result or len(result.strip()) < 10:
            logger.warning("Empty or too short LightRAG result")
            return []
        
        # Split by product entries (look for product name patterns)
        lines = result.split('\n')
        current_product = {}
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Detect product name (usually starts with ชื่อสินค้า: or is a standalone product name)
            if 'ชื่อสินค้า:' in line or 'ชื่อสินค้า :' in line:
                if current_product and 'product_name' in current_product:
                    recommendations.append(ProductRecommendation(**current_product))
                current_product = {'product_name': line.split(':', 1)[1].strip(), 'score': 0.8}
            elif 'สารสำคัญ:' in line or 'สารสําคัญ:' in line:
                current_product['active_ingredient'] = line.split(':', 1)[1].strip()
            elif 'ศัตรูพืช' in line and ':' in line:
                current_product['target_pest'] = line.split(':', 1)[1].strip()
            elif 'ใช้ได้กับพืช:' in line:
                current_product['applicable_crops'] = line.split(':', 1)[1].strip()
            elif 'วิธีใช้:' in line:
                current_product['how_to_use'] = line.split(':', 1)[1].strip()
        
        # Add last product
        if current_product and 'product_name' in current_product:
            recommendations.append(ProductRecommendation(**current_product))
        
        # If parsing failed, try to extract any product names mentioned
        if not recommendations:
            logger.warning("Failed to parse structured data, extracting product names")
            # Look for common product name patterns in Thai
            import re
            product_patterns = [
                r'([ก-๙a-zA-Z0-9\s]+(?:50|70|80|90|EC|WP|SC|SL))',
                r'ชื่อ[:\s]*([ก-๙a-zA-Z0-9\s]+)',
            ]
            for pattern in product_patterns:
                matches = re.findall(pattern, result)
                for match in matches[:5]:
                    name = match.strip() if isinstance(match, str) else match[0].strip()
                    if len(name) > 3:
                        recommendations.append(ProductRecommendation(
                            product_name=name,
                            score=0.6
                        ))
        
        return recommendations
        
    except Exception as e:
        logger.error(f"Error parsing LightRAG result: {e}", exc_info=True)
        return []

async def retrieve_with_supabase(disease_info: DiseaseDetectionResult) -> List[ProductRecommendation]:
    """Fallback: Query products using Supabase keyword search"""
    try:
        logger.info("Using Supabase keyword search (fallback)")

        if not supabase_client:
            logger.warning("Supabase not configured")
            return []

        # Extract search keywords
        search_keywords = []
        pest_keywords = ["เพลี้ย", "หนอน", "แมลง", "ไร", "รา", "ไวรัส", "โรค", 
                        "ใบไหม้", "ใบจุด", "แอนแทรคโนส", "ราน้ำค้าง", "ราสนิม",
                        "เพลี้ยไฟ", "เพลี้ยแป้ง", "หนอนกอ", "หนอนม้วนใบ", "กก", "หนวด"]
        
        text_to_search = f"{disease_info.disease_name} {disease_info.symptoms}".lower()
        for keyword in pest_keywords:
            if keyword in text_to_search:
                search_keywords.append(keyword)
        
        if not search_keywords and disease_info.disease_name:
            search_keywords = [disease_info.disease_name]
        
        logger.info(f"Search keywords: {search_keywords}")
        
        # Search database
        all_matches = []
        seen_ids = set()
        
        for keyword in search_keywords[:3]:
            response = supabase_client.table('products').select('*').or_(
                f'target_pest.ilike.%{keyword}%,product_name.ilike.%{keyword}%'
            ).limit(10).execute()
            
            if response.data:
                for item in response.data:
                    if item['id'] not in seen_ids:
                        score = 0.5
                        if keyword in item.get('target_pest', '').lower():
                            score += 0.3
                        if keyword in item.get('product_name', '').lower():
                            score += 0.2
                        all_matches.append({'similarity': min(score, 1.0), **item})
                        seen_ids.add(item['id'])
        
        matches = sorted(all_matches, key=lambda x: x['similarity'], reverse=True)[:10]
        logger.info(f"Keyword search found {len(matches)} products")
        
        if not matches:
            return []

        # Build recommendations
        recommendations: List[ProductRecommendation] = []
        for match in matches:
            pname = match.get("product_name", "ไม่ระบุชื่อ")
            active = match.get("active_ingredient", "")
            pest = match.get("target_pest", "")
            crops = match.get("applicable_crops", "")
            howto = match.get("how_to_use", "")
            
            if not pest or pest.strip() == "":
                continue

            rec = ProductRecommendation(
                product_name=pname,
                active_ingredient=active,
                target_pest=pest,
                applicable_crops=crops,
                how_to_use=howto,
                score=float(match.get("similarity", 0.5))
            )
            recommendations.append(rec)
            if len(recommendations) >= 5:
                break

        logger.info(f"Returning {len(recommendations)} Supabase recommendations")
        return recommendations

    except Exception as e:
        logger.error(f"Supabase search failed: {e}", exc_info=True)
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

        # Header: disease summary with confidence warning
        header = f"🔍 ผลตรวจจากภาพ: {disease_info.disease_name}\n\n"
        
        # Add confidence indicator
        confidence_str = str(disease_info.confidence)
        confidence_emoji = "🟢" if "สูง" in confidence_str or any(str(x) in confidence_str for x in range(70, 101)) else \
                          "🟡" if "ปานกลาง" in confidence_str or any(str(x) in confidence_str for x in range(50, 70)) else "🔴"
        
        header += f"{confidence_emoji} ระดับความมั่นใจ: {disease_info.confidence}\n"
        
        # Add warning for low confidence
        if "ต่ำ" in confidence_str or confidence_emoji == "🔴":
            header += "⚠️ **คำเตือน**: ความมั่นใจต่ำ แนะนำให้ส่งรูปเพิ่มหรือปรึกษาผู้เชี่ยวชาญ\n\n"
        
        header += f"📊 ความรุนแรง: {disease_info.severity}\n\n"
        header += f"📝 อาการที่เห็น: {disease_info.symptoms}\n\n"

        if not recommendations:
            body = "⚠️ ขณะนี้ยังไม่มีข้อมูลผลิตภัณฑ์ที่ตรงกับอาการในฐานข้อมูลของเรา\n\n"
            body += "แนะนำ: เก็บตัวอย่างหรือปรึกษาผู้เชี่ยวชาญก่อนใช้สารป้องกันกำจัด\n\n"
            body += "📚 ดูรายละเอียดผลิตภัณฑ์ทั้งหมดได้ที่:\n"
            body += "https://www.icpladda.com/about/\n\n"
            body += "หากต้องการให้ช่วยอีกครั้ง ส่งรูปภาพเพิ่มหรือลองถ่ายมุมอื่นนะครับ 😊"
            return header + body

        # Build product blocks (minimal fields)
        body = "💊 สินค้าแนะนำ:\n"
        for idx, rec in enumerate(recommendations, 1):
            body += f"\n{idx}. {rec.product_name}\n"
            if rec.active_ingredient:
                body += f"   • สารสำคัญ: {rec.active_ingredient}\n"
            if rec.target_pest:
                # Truncate long text
                pest_text = rec.target_pest[:80] + "..." if len(rec.target_pest) > 80 else rec.target_pest
                body += f"   • ศัตรูพืชเป้าหมาย: {pest_text}\n"
            if rec.applicable_crops:
                crops_text = rec.applicable_crops[:60] + "..." if len(rec.applicable_crops) > 60 else rec.applicable_crops
                body += f"   • ใช้ได้กับพืช: {crops_text}\n"
            # friendly short how-to: if long, take first line
            if rec.how_to_use:
                short_how = rec.how_to_use.split("\n")[0].strip()
                if len(short_how) > 80:
                    short_how = short_how[:80] + "..."
                body += f"   • วิธีใช้: {short_how}\n"
            body += f"   • ความเกี่ยวข้อง: {int(rec.score * 100)}%\n"

        footer = "\n" + "="*40 + "\n"
        footer += "📋 **หมายเหตุสำคัญ**:\n"
        footer += "• ✅ ปรับอัตรา/ปริมาณตามฉลากจริงก่อนใช้ทุกครั้ง\n"
        footer += "• ✅ ควรปรึกษาผู้เชี่ยวชาญก่อนใช้\n"
        footer += "• ✅ ทดสอบในพื้นที่เล็กก่อนพ่นทั้งแปลง\n\n"
        
        footer += "�  **เพื่อความแม่นยำมากขึ้น**:\n"
        footer += "• ถ่ายรูปใกล้ๆ บริเวณที่เสียหาย\n"
        footer += "• ถ่ายหลายมุม (ใบ ลำต้น ผล)\n"
        footer += "• ถ่ายในที่แสงสว่างเพียงพอ\n"
        footer += "• ระบุชนิดพืชและอาการเพิ่มเติม\n\n"
        
        footer += "📚 ดูรายละเอียดผลิตภัณฑ์ทั้งหมด:\n"
        footer += "🔗 https://www.icpladda.com/about/\n\n"
        footer += "💬 ส่งรูปเพิ่มหรือถามข้อมูลเพิ่มเติมได้เลยค่ะ 😊"
        
        return header + body + footer

    except Exception as e:
        logger.error(f"Error generating final response: {e}", exc_info=True)
        # fallback simple template
        products_text = "\n".join([f"• {p.product_name}" for p in (recommendations or [])[:3]])
        fallback = f"ผลการวิเคราะห์: {disease_info.disease_name}\n\n"
        fallback += f"ผลิตภัณฑ์แนะนำ:\n{products_text}\n\n"
        fallback += "📚 ดูรายละเอียดเพิ่มเติม: https://www.icpladda.com/about/\n"
        fallback += "โปรดตรวจสอบฉลากก่อนใช้"
        return fallback

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
                    # When receiving an image, store it and ask the user for additional symptoms
                    message_id = message.get("id")
                    try:
                        image_bytes = await get_image_content_from_line(message_id)
                        user_id = event.get("source", {}).get("userId") or event.get("source", {}).get("userId")
                        if user_id:
                            # store pending context
                            pending_image_contexts[user_id] = {
                                "image_bytes": image_bytes,
                                "reply_token": reply_token
                            }
                        ask_message = (
                            "✅ ได้รับรูปแล้วค่ะ\n\n"
                            "📝 เพื่อความแม่นยำในการวินิจฉัย กรุณาตอบคำถามเหล่านี้:\n\n"
                            "1️⃣ **ชนิดพืช**: ทุเรียน/มะม่วง/ข้าว/อื่นๆ?\n"
                            "2️⃣ **ตำแหน่งอาการ**: ใบ/ลำต้น/ผล/ราก?\n"
                            "3️⃣ **ลักษณะอาการ**:\n"
                            "   • สีของจุด/แผล (น้ำตาล/เหลือง/ดำ/ขาว)\n"
                            "   • ขนาดพื้นที่เสียหาย (เล็กน้อย/ปานกลาง/มาก)\n"
                            "   • มีแมลงหรือไม่ (ถ้ามี สีและขนาด)\n\n"
                            "4️⃣ **ระยะเวลา**: เกิดมานานแค่ไหน?\n\n"
                            "ตัวอย่าง:\n"
                            "\"ทุเรียน ใบม้วน มีจุดสีน้ำตาล เห็นแมลงตัวเล็กสีดำ เกิดมา 3 วัน\"\n\n"
                            "ยิ่งให้รายละเอียดมาก ยิ่งวินิจฉัยแม่นยำค่ะ 🎯"
                        )
                        await reply_line(reply_token, ask_message)
                    except Exception as e:
                        logger.error(f"Error fetching image content: {e}", exc_info=True)
                        error_message = "ขออภัยค่ะ ไม่สามารถดึงรูปจาก LINE ได้ กรุณาลองส่งรูปอีกครั้ง"
                        await reply_line(reply_token, error_message)
                elif message_type == "text":
                    text = message.get("text", "").strip()
                    user_id = event.get("source", {}).get("userId")
                    # If user has a pending image, treat this text as symptom input
                    if user_id and user_id in pending_image_contexts:
                        ctx = pending_image_contexts.pop(user_id)
                        image_bytes = ctx.get("image_bytes")
                        try:
                            # Run detection with extra user-provided observations
                            disease_result = await detect_disease(image_bytes, extra_user_info=text)
                            recommendations = await retrieve_product_recommendation(disease_result)
                            final_message = await generate_final_response(disease_result, recommendations)
                            await reply_line(reply_token, final_message)
                        except Exception as e:
                            logger.error(f"Error processing combined image+text: {e}", exc_info=True)
                            error_message = "ขออภัยค่ะ เกิดข้อผิดพลาดในการวิเคราะห์ข้อมูล กรุณาลองใหม่อีกครั้งค่ะ 🙏"
                            await reply_line(reply_token, error_message)
                    else:
                        # Check for specific keywords
                        text_lower = text.lower()
                        
                        if any(keyword in text_lower for keyword in ["สินค้า", "ผลิตภัณฑ์", "รายการ", "product"]):
                            help_message = (
                                "📦 รายการผลิตภัณฑ์ทั้งหมด\n\n"
                                "เรามีผลิตภัณฑ์ป้องกันกำจัดศัตรูพืช 43 รายการ:\n\n"
                                "🐛 ยากำจัดแมลง (Insecticide)\n"
                                "🍄 ยากำจัดเชื้อรา (Fungicide)\n"
                                "🌿 ยากำจัดวัชพืช (Herbicide)\n"
                                "🌱 ตัวควบคุมการเจริญเติบโต (PGR)\n\n"
                                "📚 ดูรายละเอียดผลิตภัณฑ์ทั้งหมดได้ที่:\n"
                                "🔗 https://www.icpladda.com/about/\n\n"
                                "💡 วิธีใช้งาน:\n"
                                "ส่งรูปภาพพืชที่มีปัญหามาให้ฉัน ฉันจะวิเคราะห์และแนะนำผลิตภัณฑ์ที่เหมาะสมให้ค่ะ 😊"
                            )
                        
                        elif any(keyword in text_lower for keyword in ["ช่วย", "help", "วิธี", "ใช้งาน", "คำสั่ง"]):
                            help_message = (
                                "🌱 วิธีใช้งาน Plant Disease Bot\n\n"
                                "📸 ขั้นตอนการใช้งาน:\n"
                                "1. ถ่ายรูปพืชที่มีปัญหา (ใบ, ผล, ลำต้น)\n"
                                "2. ส่งรูปมาให้ฉัน\n"
                                "3. รอ 5-10 วินาที\n"
                                "4. ได้รับคำแนะนำและผลิตภัณฑ์ที่เหมาะสม\n\n"
                                "🔍 ฉันสามารถตรวจจับ:\n"
                                "• เชื้อรา (Fungus) - แอนแทรคโนส, ใบไหม้\n"
                                "• ไวรัส (Virus) - โรคใบด่าง, โรคใบหงิก\n"
                                "• ศัตรูพืช (Pest) - เพลี้ยไฟ, หนอน, แมลง\n\n"
                                "📚 ดูข้อมูลเพิ่มเติม:\n"
                                "🔗 https://www.icpladda.com/about/\n\n"
                                "พร้อมช่วยคุณแล้วค่ะ! 😊"
                            )
                        
                        else:
                            help_message = (
                                "สวัสดีค่ะ! 🌱\n\n"
                                "ฉันคือ AI ผู้ช่วยตรวจจับโรคพืชและศัตรูพืช\n\n"
                                "📸 ส่งรูปภาพพืชที่มีปัญหามาให้ฉัน\n"
                                "ฉันจะวิเคราะห์และแนะนำผลิตภัณฑ์ที่เหมาะสมให้ค่ะ\n\n"
                                "🔍 ตรวจจับได้:\n"
                                "• เชื้อรา (Fungus)\n"
                                "• ไวรัส (Virus)\n"
                                "• ศัตรูพืช (Pest)\n\n"
                                "📚 ดูรายละเอียดผลิตภัณฑ์:\n"
                                "🔗 https://www.icpladda.com/about/\n\n"
                                "💡 พิมพ์ 'ช่วย' เพื่อดูวิธีใช้งาน\n"
                                "💡 พิมพ์ 'สินค้า' เพื่อดูรายการผลิตภัณฑ์"
                            )
                        
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
    logger.info("RAG Method: Supabase Keyword Search (optimized for Thai)")
    logger.info("=" * 60)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
