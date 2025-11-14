"""
LINE Plant Disease Detection Bot with Google Gemini Vision and Supabase RAG
Production-grade FastAPI implementation with Multi-Agent System
"""

import os
import logging
import time
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
import google.generativeai as genai
from PIL import Image
import io
from sentence_transformers import SentenceTransformer

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# LightRAG - removed (not used)

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
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

required_env_vars = {
    "LINE_CHANNEL_ACCESS_TOKEN": LINE_CHANNEL_ACCESS_TOKEN,
    "LINE_CHANNEL_SECRET": LINE_CHANNEL_SECRET,
    "GEMINI_API_KEY": GEMINI_API_KEY,
    "SUPABASE_URL": SUPABASE_URL,
    "SUPABASE_KEY": SUPABASE_KEY,
}
for var_name, var_value in required_env_vars.items():
    if not var_value:
        logger.error(f"Missing required environment variable: {var_name}")

# Initialize Gemini (for Vision)
gemini_model = None
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel('gemini-2.5-flash')
    logger.info("Gemini initialized successfully (gemini-2.5-flash)")

# Initialize E5 model for embeddings (768 dimensions)
e5_model = None
try:
    e5_model = SentenceTransformer('intfloat/multilingual-e5-base')
    logger.info("E5 model initialized successfully (768 dimensions)")
except Exception as e:
    logger.warning(f"E5 model initialization failed: {e}")

# Initialize Supabase (fallback)
supabase_client: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Supabase initialized successfully (fallback)")
    except Exception as e:
        logger.error(f"Failed to initialize Supabase: {e}")

# Using Supabase Vector Search with Gemini filtering
logger.info("Using Supabase Vector Search + Gemini Filtering")

# ============================================================================#
# Memory System (Supabase-based)
# ============================================================================#
# In-memory store for pending image contexts awaiting user symptom input
# Keyed by user_id -> dict with image_bytes and reply_token (optional)
pending_image_contexts: Dict[str, Dict[str, Any]] = {}

# Memory configuration
MAX_MEMORY_MESSAGES = 10  # Keep last 10 messages for context
MEMORY_CONTEXT_WINDOW = 5  # Use last 5 messages for context

async def add_to_memory(user_id: str, role: str, content: str, metadata: dict = None):
    """Add message to conversation memory in Supabase"""
    try:
        if not supabase_client:
            logger.warning("Supabase not available, skipping memory storage")
            return
        
        # Truncate very long messages
        truncated_content = content[:2000] if len(content) > 2000 else content
        
        data = {
            "user_id": user_id,
            "role": role,  # "user" or "assistant"
            "content": truncated_content,
            "metadata": metadata or {}
        }
        
        result = supabase_client.table('conversation_memory').insert(data).execute()
        logger.info(f"✓ Added to memory: {role} message for user {user_id[:8]}...")
        
        # Clean up old messages (keep last N per user)
        await cleanup_old_memory(user_id)
        
    except Exception as e:
        logger.error(f"Failed to add to memory: {e}")

async def get_conversation_context(user_id: str, limit: int = MEMORY_CONTEXT_WINDOW) -> str:
    """Get conversation history as context string from Supabase"""
    try:
        if not supabase_client:
            return ""
        
        # Get last N messages for this user
        result = supabase_client.table('conversation_memory')\
            .select('role, content, created_at')\
            .eq('user_id', user_id)\
            .order('created_at', desc=True)\
            .limit(limit)\
            .execute()
        
        if not result.data:
            return ""
        
        # Reverse to get chronological order
        messages = list(reversed(result.data))
        
        context_parts = []
        for msg in messages:
            role = "ผู้ใช้" if msg["role"] == "user" else "ฉัน"
            content = msg["content"][:150]  # Truncate for context
            context_parts.append(f"{role}: {content}")
        
        logger.info(f"✓ Retrieved {len(messages)} messages from memory")
        return "\n".join(context_parts)
        
    except Exception as e:
        logger.error(f"Failed to get conversation context: {e}")
        return ""

async def cleanup_old_memory(user_id: str):
    """Keep only last N messages per user"""
    try:
        if not supabase_client:
            return
        
        # Get all message IDs for this user, ordered by created_at desc
        result = supabase_client.table('conversation_memory')\
            .select('id')\
            .eq('user_id', user_id)\
            .order('created_at', desc=True)\
            .execute()
        
        if not result.data or len(result.data) <= MAX_MEMORY_MESSAGES:
            return
        
        # Get IDs to delete (keep only last MAX_MEMORY_MESSAGES)
        ids_to_keep = [msg['id'] for msg in result.data[:MAX_MEMORY_MESSAGES]]
        ids_to_delete = [msg['id'] for msg in result.data[MAX_MEMORY_MESSAGES:]]
        
        if ids_to_delete:
            # Delete old messages
            supabase_client.table('conversation_memory')\
                .delete()\
                .in_('id', ids_to_delete)\
                .execute()
            logger.info(f"✓ Cleaned up {len(ids_to_delete)} old messages for user {user_id[:8]}...")
            
    except Exception as e:
        logger.error(f"Failed to cleanup old memory: {e}")

async def clear_memory(user_id: str):
    """Clear all conversation memory for user"""
    try:
        if not supabase_client:
            logger.warning("Supabase not available")
            return
        
        result = supabase_client.table('conversation_memory')\
            .delete()\
            .eq('user_id', user_id)\
            .execute()
        
        logger.info(f"✓ Cleared memory for user {user_id[:8]}...")
        
    except Exception as e:
        logger.error(f"Failed to clear memory: {e}")

async def get_memory_stats(user_id: str) -> dict:
    """Get memory statistics for user"""
    try:
        if not supabase_client:
            return {"total": 0, "user_messages": 0, "assistant_messages": 0}
        
        result = supabase_client.table('conversation_memory')\
            .select('role')\
            .eq('user_id', user_id)\
            .execute()
        
        if not result.data:
            return {"total": 0, "user_messages": 0, "assistant_messages": 0}
        
        user_count = sum(1 for msg in result.data if msg['role'] == 'user')
        assistant_count = sum(1 for msg in result.data if msg['role'] == 'assistant')
        
        return {
            "total": len(result.data),
            "user_messages": user_count,
            "assistant_messages": assistant_count
        }
        
    except Exception as e:
        logger.error(f"Failed to get memory stats: {e}")
        return {"total": 0, "user_messages": 0, "assistant_messages": 0}

# ============================================================================#
# Pydantic Models
# ============================================================================#
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
    usage_rate: Optional[str] = ""
    score: float = 0.0

# ============================================================================#
# Helpers
# ============================================================================#
def clean_knowledge_text(text: str) -> str:
    """Clean and format knowledge text for better readability"""
    if not text:
        return ""
    
    import re
    
    # Fix encoding issues - remove corrupted characters
    # Common patterns: จĞำ, ลĞำ, ทĞำ, นĞ้ำ, กĞำ
    text = re.sub(r'([ก-ฮ])Ğ([ำ])', r'\1\2', text)  # จĞำ → จำ
    text = re.sub(r'([ก-ฮ])Ğ([้])', r'\1\2', text)  # นĞ้ → น้
    text = re.sub(r'Ğ', '', text)  # Remove remaining Ğ
    
    # Fix other corrupted characters
    text = text.replace('ต้', 'ต้')  # Fix tone marks
    text = text.replace('ต', 'ต')
    
    # Remove excessive whitespace
    text = ' '.join(text.split())
    
    # Fix common issues
    text = text.replace('  ', ' ')  # Double spaces
    text = text.replace(' ,', ',')  # Space before comma
    text = text.replace(' .', '.')  # Space before period
    text = text.replace('( ', '(')  # Space after opening parenthesis
    text = text.replace(' )', ')')  # Space before closing parenthesis
    
    # Fix Thai-specific issues
    text = text.replace('ฺ', '')  # Remove Thai character above
    text = text.replace('์', '')  # Remove Thai character above (optional - keep for now)
    
    # Remove multiple consecutive spaces
    text = re.sub(r'\s+', ' ', text)
    
    # Ensure proper sentence spacing
    text = re.sub(r'([.!?])\s*([A-Za-zก-๙])', r'\1 \2', text)
    
    # Remove leading/trailing whitespace
    text = text.strip()
    
    return text

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



# ============================================================================#
# Core: Detect disease (Gemini Vision)
# ============================================================================#
async def detect_disease(image_bytes: bytes, extra_user_info: Optional[str] = None) -> DiseaseDetectionResult:
    logger.info("Starting pest/disease detection with Gemini Vision")
    try:
        # Convert bytes to PIL Image for Gemini
        image = Image.open(io.BytesIO(image_bytes))
        
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

        # Call Gemini with image
        response = gemini_model.generate_content([prompt, image])
        raw_text = response.text
        logger.info(f"Gemini raw response: {raw_text}")

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
            logger.warning(f"Failed to parse JSON from Gemini response: {e}", exc_info=True)
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
    Query products using Vector Search + Gemini filtering
    Returns top 3-5 most relevant products
    """
    try:
        logger.info("🔍 Retrieving products with Vector Search + Gemini Filter")

        if not supabase_client:
            logger.warning("Supabase not configured")
            return []

        disease_name = disease_info.disease_name
        logger.info(f"📝 Searching products for: {disease_name}")
        
        # Strategy 1: Vector search by disease name (most accurate)
        try:
            if e5_model:
                # Generate embedding for disease name
                query_text = f"query: {disease_name}"
                query_embedding = e5_model.encode(query_text, normalize_embeddings=True).tolist()
                logger.info("✓ Product query embedding generated")
                
                # Vector search in products table
                result = supabase_client.rpc(
                    'match_products',
                    {
                        'query_embedding': query_embedding,
                        'match_threshold': 0.3,  # Lower threshold for more candidates
                        'match_count': 15  # Get more candidates for Gemini filtering
                    }
                ).execute()
                
                if result.data and len(result.data) > 0:
                    logger.info(f"✓ Found {len(result.data)} product candidates via vector search")
                    
                    # Use Gemini to filter and rank products
                    filtered_products = await filter_products_with_gemini(
                        disease_name,
                        disease_info.raw_analysis,
                        result.data
                    )
                    
                    if filtered_products:
                        logger.info(f"✓ Gemini filtered {len(filtered_products)} relevant products")
                        return filtered_products
                    else:
                        logger.warning("⚠️ Gemini filtering returned no products, using top vector results")
                        # Fallback: use top vector search results
                        return build_recommendations_from_data(result.data[:6])
                else:
                    logger.info("No products found via vector search, trying keyword search")
            else:
                logger.warning("E5 model not available, using keyword search")
        except Exception as e:
            logger.warning(f"Vector search failed: {e}, trying keyword search")
        
        # Strategy 2: Keyword search fallback
        matches_data = []
        
        # Search in target_pest field
        try:
            result = supabase_client.table('products')\
                .select('*')\
                .ilike('target_pest', f'%{disease_name}%')\
                .limit(10)\
                .execute()
            
            if result.data:
                matches_data.extend(result.data)
                logger.info(f"Found {len(result.data)} products in target_pest")
        except Exception as e:
            logger.warning(f"target_pest search failed: {e}")
        
        # If no results, search by pest type
        if not matches_data:
            try:
                pest_keywords = []
                if "เชื้อรา" in disease_info.raw_analysis:
                    pest_keywords = ["เชื้อรา", "โรคพืช"]
                elif "ไวรัส" in disease_info.raw_analysis:
                    pest_keywords = ["ไวรัส"]
                elif "ศัตรูพืช" in disease_info.raw_analysis or "แมลง" in disease_info.raw_analysis:
                    pest_keywords = ["แมลง", "ศัตรูพืช", "เพลี้ย"]
                elif "วัชพืช" in disease_info.raw_analysis:
                    pest_keywords = ["วัชพืช", "หญ้า"]
                
                for keyword in pest_keywords:
                    result = supabase_client.table('products')\
                        .select('*')\
                        .ilike('target_pest', f'%{keyword}%')\
                        .limit(5)\
                        .execute()
                    
                    if result.data:
                        matches_data.extend(result.data)
                        logger.info(f"Found {len(result.data)} products for keyword: {keyword}")
                        break
                        
            except Exception as e:
                logger.warning(f"Keyword search failed: {e}")
        
        if not matches_data:
            logger.warning("No products found with any search strategy")
            return []
        
        logger.info(f"Total products found: {len(matches_data)}")
        return build_recommendations_from_data(matches_data[:6])

    except Exception as e:
        logger.error(f"Product search failed: {e}", exc_info=True)
        return []

async def filter_products_with_gemini(disease_name: str, raw_analysis: str, product_candidates: List[Dict]) -> List[ProductRecommendation]:
    """Use Gemini to filter and rank the most relevant products"""
    try:
        if not gemini_model:
            return []
        
        # Build product list for Gemini
        products_text = ""
        for idx, p in enumerate(product_candidates[:10], 1):  # Top 10 candidates
            products_text += f"\n[{idx}] {p.get('product_name', 'N/A')}\n"
            products_text += f"   สารสำคัญ: {p.get('active_ingredient', 'N/A')}\n"
            products_text += f"   ศัตรูพืช: {p.get('target_pest', 'N/A')[:100]}\n"
            products_text += f"   Similarity: {p.get('similarity', 0):.0%}\n"
        
        prompt = f"""คุณคือผู้เชี่ยวชาญด้านผลิตภัณฑ์ป้องกันกำจัดศัตรูพืช

🎯 **ภารกิจ**: เลือกผลิตภัณฑ์ที่เหมาะสมสำหรับ "{disease_name}"

📊 **ข้อมูลโรค**:
{raw_analysis}

📦 **ผลิตภัณฑ์ที่พบ**:
{products_text}

📋 **คำสั่ง**:
1. อ่านข้อมูลโรคและผลิตภัณฑ์ทั้งหมดอย่างละเอียด
2. เลือกผลิตภัณฑ์ที่เหมาะสมที่สุด 3-5 รายการ
3. จัดอันดับตามความเหมาะสม (เหมาะสมที่สุดก่อน)
4. ตอบเป็น JSON array ของ product index เท่านั้น

⚠️ **เกณฑ์การเลือก**:
- ศัตรูพืชเป้าหมายตรงกับโรคที่ตรวจพบ
- สารสำคัญเหมาะสมกับประเภทโรค (เชื้อรา/แมลง/วัชพืช)
- ห้ามเลือกผลิตภัณฑ์ที่ไม่เกี่ยวข้อง

ตอบเป็น JSON array เท่านั้น (ไม่ต้องมี markdown):
[1, 3, 5]"""

        response = gemini_model.generate_content(prompt)
        result_text = response.text.strip()
        
        # Parse JSON response
        try:
            # Extract JSON array
            if "[" in result_text and "]" in result_text:
                start = result_text.find("[")
                end = result_text.rfind("]") + 1
                json_str = result_text[start:end]
                selected_indices = json.loads(json_str)
                
                if selected_indices and len(selected_indices) > 0:
                    # Build recommendations from selected products
                    recommendations = []
                    for idx in selected_indices[:5]:  # Max 5
                        if 1 <= idx <= len(product_candidates):
                            product = product_candidates[idx - 1]
                            rec = ProductRecommendation(
                                product_name=product.get('product_name', 'N/A'),
                                active_ingredient=product.get('active_ingredient', ''),
                                target_pest=product.get('target_pest', ''),
                                applicable_crops=product.get('applicable_crops', ''),
                                how_to_use=product.get('how_to_use', ''),
                                usage_rate=product.get('usage_rate', ''),
                                score=product.get('similarity', 0.8)
                            )
                            recommendations.append(rec)
                    
                    logger.info(f"✓ Gemini selected {len(recommendations)} products")
                    return recommendations
                else:
                    logger.warning("Gemini returned empty selection")
                    return []
            else:
                logger.warning(f"Invalid Gemini response format: {result_text[:100]}")
                return []
                
        except Exception as e:
            logger.error(f"Failed to parse Gemini response: {e}")
            return []
        
    except Exception as e:
        logger.error(f"Gemini product filtering failed: {e}")
        return []

def build_recommendations_from_data(products_data: List[Dict]) -> List[ProductRecommendation]:
    """Build ProductRecommendation list from raw data"""
    recommendations = []
    seen_products = set()
    
    for product in products_data:
        pname = product.get("product_name", "ไม่ระบุชื่อ")
        
        if pname in seen_products:
            continue
        seen_products.add(pname)
        
        pest = product.get("target_pest", "")
        if not pest or pest.strip() == "":
            continue
        
        rec = ProductRecommendation(
            product_name=pname,
            active_ingredient=product.get("active_ingredient", ""),
            target_pest=pest,
            applicable_crops=product.get("applicable_crops", ""),
            how_to_use=product.get("how_to_use", ""),
            usage_rate=product.get("usage_rate", ""),
            score=product.get("similarity", 0.7)
        )
        recommendations.append(rec)
    
    return recommendations



# ============================================================================#
# Core: Smart Q&A - Answer questions using Knowledge Base
# ============================================================================#
async def answer_question_with_knowledge(question: str) -> str:
    """Answer user questions using knowledge base and Gemini"""
    try:
        logger.info(f"Answering question: {question[:50]}...")
        
        if not supabase_client or not gemini_model:
            return "ขออภัยค่ะ ระบบไม่พร้อมใช้งานในขณะนี้"
        
        # 1. Generate embedding for the question using E5 model (768 dimensions)
        try:
            if e5_model:
                # E5 requires "query: " prefix for queries
                query_text = f"query: {question}"
                query_embedding = e5_model.encode(query_text, normalize_embeddings=True).tolist()
                logger.info("✓ Question embedding generated (E5, 768 dim)")
            else:
                logger.warning("E5 model not available, using keyword search")
                return await answer_with_keyword_search(question)
        except Exception as e:
            logger.warning(f"Failed to generate E5 embedding: {e}")
            # Fallback to keyword search
            return await answer_with_keyword_search(question)
        
        # 2. Search knowledge base using vector search
        try:
            result = supabase_client.rpc(
                'match_knowledge',
                {
                    'query_embedding': query_embedding,
                    'match_threshold': 0.3,  # Lower threshold for more results
                    'match_count': 10  # Get more candidates
                }
            ).execute()
            
            if result.data:
                logger.info(f"✓ Found {len(result.data)} relevant knowledge entries")
                # Combine knowledge content
                knowledge_texts = []
                for item in result.data:
                    content = item.get('content', '').strip()
                    similarity = item.get('similarity', 0)
                    # Lower filter threshold to get more results
                    if content and similarity > 0.3:
                        # Clean the text before adding
                        cleaned_content = clean_knowledge_text(content)
                        if cleaned_content:
                            knowledge_texts.append(cleaned_content)
                
                if knowledge_texts:
                    combined_knowledge = "\n\n".join(knowledge_texts[:5])  # Top 5 for better context
                else:
                    # Fallback to keyword search
                    return await answer_with_keyword_search(question)
            else:
                # Fallback to keyword search
                return await answer_with_keyword_search(question)
                
        except Exception as e:
            logger.warning(f"Vector search failed: {e}")
            return await answer_with_keyword_search(question)
        
        # 3. Search for relevant products
        products_info = ""
        try:
            # Extract keywords for product search
            keywords = extract_keywords_from_question(question)
            if keywords:
                product_result = supabase_client.table('products')\
                    .select('product_name, active_ingredient, target_pest, how_to_use , usage_rate')\
                    .ilike('target_pest', f'%{keywords[0]}%')\
                    .limit(3)\
                    .execute()
                
                if product_result.data:
                    products_list = []
                    for p in product_result.data:
                        products_list.append(
                            f"- {p.get('product_name')}: {p.get('active_ingredient', 'N/A')}"
                        )
                    products_info = "\n".join(products_list)
        except Exception as e:
            logger.warning(f"Product search failed: {e}")
        
        # 4. Use Gemini to generate natural answer
        prompt = f"""คุณคือผู้เชี่ยวชาญด้านโรคพืชและศัตรูพืชของกรมวิชาการเกษตรไทย มีประสบการณ์ 20 ปี

คำถามจากเกษตรกร: {question}

ความรู้จากฐานข้อมูล:
{combined_knowledge}

ผลิตภัณฑ์ที่เกี่ยวข้อง:
{products_info if products_info else "ไม่มีข้อมูลผลิตภัณฑ์"}

คำแนะนำในการตอบ:
1. **อ่านความรู้ทั้งหมดอย่างละเอียด** แล้วสรุปเป็นคำตอบที่เข้าใจง่าย
2. **จัดระเบียบคำตอบ** ให้มีหัวข้อชัดเจน เช่น:
   - สาเหตุ/ลักษณะ
   - วิธีป้องกัน
   - วิธีกำจัด/รักษา
   - ผลิตภัณฑ์แนะนำ (ถ้ามี)
3. **ให้ข้อมูลเฉพาะเจาะจง** ที่ตอบคำถามโดยตรง
4. **ใช้ภาษาง่ายๆ** ที่เกษตรกรเข้าใจได้
5. **เพิ่ม emoji** ให้น่าอ่าน (🌱 🐛 🍄 💊 ⚠️)
6. **จบด้วยคำแนะนำเพิ่มเติม** หรือข้อควรระวัง
7. **ตอบเป็นภาษาไทยเท่านั้น** ไม่ใช้ markdown

ตอบคำถาม:"""

        try:
            response = gemini_model.generate_content(prompt)
            answer = response.text.strip()
            
            # Clean up markdown if any
            answer = answer.replace("```", "").replace("**", "")
            
            logger.info("✓ Answer generated successfully")
            return answer
            
        except Exception as e:
            logger.error(f"Gemini generation failed: {e}")
            # Return knowledge directly
            return f"📚 ข้อมูลที่เกี่ยวข้อง:\n\n{combined_knowledge[:500]}...\n\n💡 หากต้องการข้อมูลเพิ่มเติม กรุณาถามคำถามที่เฉพาะเจาะจงมากขึ้นค่ะ"
        
    except Exception as e:
        logger.error(f"Error in Q&A: {e}", exc_info=True)
        return "ขออภัยค่ะ ไม่สามารถตอบคำถามได้ในขณะนี้ กรุณาลองใหม่อีกครั้ง หรือส่งรูปภาพพืชที่มีปัญหามาให้ฉันตรวจสอบค่ะ 🌱"

async def answer_with_keyword_search(question: str) -> str:
    """Fallback: Answer using keyword search"""
    try:
        # Extract main keywords
        keywords = extract_keywords_from_question(question)
        
        if not keywords:
            return "ขออภัยค่ะ ฉันไม่เข้าใจคำถาม กรุณาถามใหม่อีกครั้งหรือส่งรูปภาพพืชที่มีปัญหามาให้ฉันตรวจสอบค่ะ 🌱"
        
        # Search in knowledge table
        result = supabase_client.table('knowledge')\
            .select('content')\
            .ilike('content', f'%{keywords[0]}%')\
            .limit(2)\
            .execute()
        
        if result.data:
            # Clean and format knowledge
            cleaned_items = []
            for item in result.data:
                content = item.get('content', '')
                cleaned = clean_knowledge_text(content)
                if cleaned:
                    cleaned_items.append(cleaned[:300])
            
            knowledge = "\n\n".join(cleaned_items)
            return f"📚 ข้อมูลที่เกี่ยวข้อง:\n\n{knowledge}\n\n💡 หากต้องการข้อมูลเพิ่มเติม กรุณาถามคำถามที่เฉพาะเจาะจงมากขึ้นค่ะ"
        else:
            return "ขออภัยค่ะ ไม่พบข้อมูลที่เกี่ยวข้อง กรุณาลองถามคำถามอื่นหรือส่งรูปภาพพืชที่มีปัญหามาให้ฉันตรวจสอบค่ะ 🌱"
            
    except Exception as e:
        logger.error(f"Keyword search failed: {e}")
        return "ขออภัยค่ะ เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้งค่ะ"

def extract_keywords_from_question(question: str) -> list:
    """Extract main keywords from question"""
    # Common disease/pest keywords
    keywords = [
        "เพลี้ยไฟ", "เพลี้ยอ่อน", "เพลี้ย", "หนอน", "แมลง",
        "ราน้ำค้าง", "ราแป้ง", "ราสนิม", "เชื้อรา", "รา",
        "ไวรัส", "โรคใบด่าง", "โรคใบหงิก",
        "วัชพืช", "หญ้า",
        "โรคพืช", "ศัตรูพืช",
        "ทุเรียน", "มะม่วง", "ข้าว", "พืชผัก"
    ]
    
    found_keywords = []
    question_lower = question.lower()
    
    for keyword in keywords:
        if keyword in question_lower:
            found_keywords.append(keyword)
    
    return found_keywords[:3]  # Return top 3

# ============================================================================#
# Core: Retrieve knowledge from knowledge table (Vector Search)
# ============================================================================#
async def retrieve_knowledge_from_knowledge_table(disease_info: DiseaseDetectionResult) -> str:
    """Query knowledge table using vector search + Gemini filtering for disease information"""
    try:
        if not supabase_client:
            return ""
        
        logger.info(f"🔍 Searching knowledge for: {disease_info.disease_name}")
        
        # Strategy 1: Search by exact disease name first (most accurate)
        query_text = disease_info.disease_name
        logger.info(f"📝 Primary query: {query_text}")
        
        # Generate embedding using E5 model (768 dimensions)
        try:
            if e5_model:
                query_with_prefix = f"query: {query_text}"
                query_embedding = e5_model.encode(query_with_prefix, normalize_embeddings=True).tolist()
                logger.info("✓ Embedding generated (E5, 768 dim)")
            else:
                logger.warning("E5 model not available, using keyword search")
                return await retrieve_knowledge_keyword_search(disease_info)
        except Exception as e:
            logger.warning(f"Failed to generate E5 embedding: {e}")
            return await retrieve_knowledge_keyword_search(disease_info)
        
        # Vector similarity search
        try:
            result = supabase_client.rpc(
                'match_knowledge',
                {
                    'query_embedding': query_embedding,
                    'match_threshold': 0.4,  # Lower threshold to get more candidates
                    'match_count': 10  # Get more results for Gemini to filter
                }
            ).execute()
            
            if result.data and len(result.data) > 0:
                logger.info(f"✓ Found {len(result.data)} knowledge candidates")
                
                # Collect all knowledge content for Gemini filtering
                knowledge_candidates = []
                for idx, item in enumerate(result.data, 1):
                    content = item.get('content', '').strip()
                    similarity = item.get('similarity', 0)
                    if content and len(content) > 20:
                        cleaned_content = clean_knowledge_text(content)
                        knowledge_candidates.append({
                            'index': idx,
                            'content': cleaned_content,
                            'similarity': similarity
                        })
                
                if knowledge_candidates:
                    # Use Gemini to filter and synthesize the most relevant knowledge
                    filtered_knowledge = await filter_knowledge_with_gemini(
                        disease_info.disease_name,
                        knowledge_candidates
                    )
                    
                    if filtered_knowledge:
                        logger.info(f"✓ Gemini filtered knowledge successfully")
                        return filtered_knowledge
                    else:
                        # Fallback: return top 2 by similarity
                        logger.info("⚠️ Gemini filtering failed, using top results")
                        top_results = sorted(knowledge_candidates, key=lambda x: x['similarity'], reverse=True)[:2]
                        return "\n\n".join([k['content'][:300] + "..." if len(k['content']) > 300 else k['content'] for k in top_results])
            else:
                logger.info("No knowledge found via vector search, trying keyword search")
                return await retrieve_knowledge_keyword_search(disease_info)
                
        except Exception as e:
            logger.warning(f"Vector search failed: {e}, trying keyword search")
            return await retrieve_knowledge_keyword_search(disease_info)
        
        return ""
        
    except Exception as e:
        logger.warning(f"Failed to retrieve knowledge: {e}")
        return ""

async def filter_knowledge_with_gemini(disease_name: str, knowledge_candidates: List[Dict]) -> str:
    """Use Gemini to filter and synthesize the most relevant knowledge"""
    try:
        if not gemini_model:
            return ""
        
        # Build prompt with all candidates
        candidates_text = ""
        for k in knowledge_candidates[:5]:  # Top 5 candidates
            candidates_text += f"\n[{k['index']}] (Similarity: {k['similarity']:.0%})\n{k['content'][:400]}\n"
        
        prompt = f"""คุณคือผู้เชี่ยวชาญด้านโรคพืชและศัตรูพืช

🎯 **ภารกิจ**: กรองและสังเคราะห์ความรู้ที่เกี่ยวข้องกับ "{disease_name}"

📚 **ความรู้ที่พบ**:
{candidates_text}

📋 **คำสั่ง**:
1. อ่านความรู้ทั้งหมดอย่างละเอียด
2. เลือกเฉพาะข้อมูลที่เกี่ยวข้องโดยตรงกับ "{disease_name}"
3. สังเคราะห์เป็นข้อความสั้นๆ ที่มีประโยชน์ (ไม่เกิน 250 คำ)
4. รวมข้อมูลสำคัญ: ลักษณะ, สาเหตุ, วิธีป้องกัน, วิธีกำจัด
5. ใช้ภาษาง่ายๆ ที่เกษตรกรเข้าใจได้
6. ไม่ต้องใช้ markdown หรือ bullet points

⚠️ **ข้อควรระวัง**:
- ถ้าไม่มีข้อมูลที่เกี่ยวข้อง ให้ตอบว่า "ไม่พบข้อมูล"
- ห้ามสร้างข้อมูลเอง ใช้เฉพาะข้อมูลที่มีให้เท่านั้น
- ถ้าข้อมูลไม่ชัดเจน ให้ระบุว่า "ข้อมูลไม่เพียงพอ"

ตอบเป็นข้อความสั้นๆ เลย ไม่ต้องมีหัวข้อ:"""

        response = gemini_model.generate_content(prompt)
        filtered_text = response.text.strip()
        
        # Check if Gemini found relevant info
        if "ไม่พบข้อมูล" in filtered_text or "ข้อมูลไม่เพียงพอ" in filtered_text or len(filtered_text) < 50:
            logger.warning("Gemini: No relevant knowledge found")
            return ""
        
        # Clean up markdown if any
        filtered_text = filtered_text.replace("```", "").replace("**", "").replace("##", "")
        
        logger.info(f"✓ Gemini filtered knowledge: {len(filtered_text)} chars")
        return filtered_text
        
    except Exception as e:
        logger.error(f"Gemini filtering failed: {e}")
        return ""

async def retrieve_knowledge_keyword_search(disease_info: DiseaseDetectionResult) -> str:
    """Fallback: keyword search in knowledge table"""
    try:
        result = supabase_client.table('knowledge')\
            .select('content')\
            .ilike('content', f'%{disease_info.disease_name}%')\
            .limit(2)\
            .execute()
        
        if result.data:
            logger.info(f"✓ Found {len(result.data)} knowledge entries via keyword search")
            knowledge_parts = []
            for item in result.data:
                content = item.get('content', '').strip()
                if content and len(content) > 20:
                    # Clean the text first
                    cleaned_content = clean_knowledge_text(content)
                    preview = cleaned_content[:250] + "..." if len(cleaned_content) > 250 else cleaned_content
                    knowledge_parts.append(preview)
            
            if knowledge_parts:
                return "\n\n".join(knowledge_parts)
        
        return ""
    except Exception as e:
        logger.warning(f"Keyword search failed: {e}")
        return ""

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
        
        # Retrieve additional knowledge from knowledge table (Vector Search)
        knowledge = await retrieve_knowledge_from_knowledge_table(disease_info)
        if knowledge:
            header += f"📚 ความรู้เพิ่มเติม:\n{knowledge}\n\n"

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
            if rec.usage_rate:
                body += f"   • อัตราการใช้: {rec.usage_rate}\n"
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
async def handle_natural_conversation(user_id: str, text: str, reply_token: str) -> None:
    """Handle natural conversation using Gemini AI"""
    try:
        logger.info(f"Natural conversation: {text[:50]}...")
        
        # Get conversation context
        context = await get_conversation_context(user_id)
        
        # Build prompt for Gemini
        prompt = f"""คุณคือ AI ผู้ช่วยด้านโรคพืชและศัตรูพืชที่เป็นมิตร ชื่อ "ดอกไม้" 🌸

🎯 **บทบาท**:
- ช่วยเหลือเกษตรกรเรื่องโรคพืช ศัตรูพืช และการใช้ผลิตภัณฑ์
- โต้ตอบแบบเป็นธรรมชาติ เหมือนคุยกับเพื่อน
- ใช้ภาษาไทยที่เข้าใจง่าย ไม่เป็นทางการจนเกินไป
- เพิ่ม emoji ให้น่ารัก 🌱 🐛 🍄 💊

📝 **บทสนทนาก่อนหน้า**:
{context if context else "ไม่มี (เริ่มบทสนทนาใหม่)"}

💬 **ข้อความจากผู้ใช้**: {text}

📋 **คำแนะนำในการตอบ**:
1. **เข้าใจเจตนา**: วิเคราะห์ว่าผู้ใช้ต้องการอะไร
   - ทักทาย → ทักทายกลับ
   - ถามคำถาม → ตอบคำถาม
   - ขอความช่วยเหลือ → แนะนำวิธีใช้งาน
   - สนทนาทั่วไป → โต้ตอบเป็นธรรมชาติ

2. **ตอบสั้นๆ กระชับ**: ไม่เกิน 3-4 ประโยค (ยกเว้นคำถามที่ต้องการคำตอบยาว)

3. **เป็นมิตร**: ใช้คำว่า "ค่ะ", "นะคะ", "ครับ" ตามบริบท

4. **แนะนำการใช้งาน**: ถ้าผู้ใช้ไม่แน่ใจ แนะนำให้:
   - ส่งรูปภาพพืชที่มีปัญหา
   - ถามคำถามเฉพาะเจาะจง
   - พิมพ์ "ช่วย" เพื่อดูวิธีใช้งาน

5. **ไม่ต้องใช้ markdown**: ตอบเป็นข้อความธรรมดา

⚠️ **ข้อห้าม**:
- ห้ามตอบคำถามที่ไม่เกี่ยวกับเกษตร/พืช
- ห้ามให้คำแนะนำทางการแพทย์
- ห้ามสร้างข้อมูลเอง ถ้าไม่รู้ให้บอกว่า "ไม่แน่ใจ"

ตอบข้อความ (ไม่ต้องมี markdown):"""

        # Call Gemini
        response = gemini_model.generate_content(prompt)
        answer = response.text.strip()
        
        # Clean up markdown if any
        answer = answer.replace("```", "").replace("**", "").replace("##", "")
        
        # Add to memory
        await add_to_memory(user_id, "user", text)
        await add_to_memory(user_id, "assistant", answer)
        
        # Reply
        await reply_line(reply_token, answer)
        
    except Exception as e:
        logger.error(f"Natural conversation error: {e}", exc_info=True)
        fallback = "ขออภัยค่ะ ฉันไม่เข้าใจคำถาม 😅\n\n💡 ลองส่งรูปภาพพืชที่มีปัญหามาให้ฉันดูนะคะ หรือพิมพ์ 'ช่วย' เพื่อดูวิธีใช้งาน 🌱"
        await reply_line(reply_token, fallback)

async def reply_line(reply_token: str, message: str, with_sticker: bool = False) -> None:
    """Reply to LINE with text message and optionally a sticker"""
    try:
        logger.info(f"Replying to LINE token: {reply_token[:10]}...")
        url = "https://api.line.me/v2/bot/message/reply"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
        }
        
        # Build messages array
        messages = [{"type": "text", "text": message}]
        
        # Add sticker if requested
        if with_sticker:
            # Use LINE's free sticker packages
            # Package 446: Brown & Cony's Friendly Stickers
            sticker_message = {
                "type": "sticker",
                "packageId": "446",
                "stickerId": "1988"  # Thumbs up sticker
            }
            messages.append(sticker_message)
        
        payload = {"replyToken": reply_token, "messages": messages}
        
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
            "gemini": "ok" if GEMINI_API_KEY else "not_configured",
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
                            "ตัวอย่างการตอบกลับ:\n"
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
                        # Natural conversation with memory
                        text_lower = text.lower()
                        
                        # Check for memory clear command
                        if any(keyword in text_lower for keyword in ["ลืม", "ลบประวัติ", "เริ่มใหม่", "clear", "reset"]):
                            await clear_memory(user_id)
                            clear_message = "✅ ลบประวัติการสนทนาเรียบร้อยแล้วค่ะ\n\nเริ่มบทสนทนาใหม่ได้เลยนะคะ 🌱"
                            await reply_line(reply_token, clear_message)
                        
                        # Check for specific commands that need exact responses
                        elif any(keyword in text_lower for keyword in ["ช่วย", "help", "วิธีใช้", "คำสั่ง"]):
                            help_message = (
                                "🌱 วิธีใช้งาน Plant Disease Bot\n\n"
                                "� ตรวำจจับโรคพืช:\n"
                                "1. ถ่ายรูปพืชที่มีปัญหา\n"
                                "2. ส่งรูปมาให้ฉัน\n"
                                "3. รอ 5-10 วินาที\n"
                                "4. ได้รับคำแนะนำและผลิตภัณฑ์\n\n"
                                "� ถามคำถา/มได้เลย เช่น:\n"
                                "• \"เพลี้ยไฟกำจัดยังไง?\"\n"
                                "• \"ราน้ำค้างเกิดจากอะไร?\"\n"
                                "• \"โมเดิน 50 ใช้กับข้าวได้ไหม?\"\n\n"
                                "🎯 ฉันสามารถ:\n"
                                "• ตรวจจับโรคพืช/ศัตรูพืช\n"
                                "• ตอบคำถามเกี่ยวกับโรคพืช\n"
                                "• แนะนำผลิตภัณฑ์และวิธีใช้\n"
                                "• สนทนาเป็นธรรมชาติ\n\n"
                                "พร้อมช่วยคุณแล้วค่ะ! 😊"
                            )
                            await add_to_memory(user_id, "user", text)
                            await add_to_memory(user_id, "assistant", help_message)
                            await reply_line(reply_token, help_message)
                        
                        elif any(keyword in text_lower for keyword in ["สินค้า", "ผลิตภัณฑ์", "รายการ", "product"]):
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
                            await add_to_memory(user_id, "user", text)
                            await add_to_memory(user_id, "assistant", help_message)
                            await reply_line(reply_token, help_message)
                        
                        # Check if it's a specific question that needs knowledge base
                        elif any(q in text_lower for q in ["?", "ยังไง", "อย่างไร", "ทำไม", "คือ", "หมายถึง", "ได้ไหม", "ใช้", "กำจัด", "ป้องกัน", "รักษา"]):
                            # This is a question - use Smart Q&A with knowledge base
                            logger.info(f"Processing Q&A with knowledge: {text[:50]}...")
                            try:
                                answer = await answer_question_with_knowledge(text)
                                await add_to_memory(user_id, "user", text)
                                await add_to_memory(user_id, "assistant", answer)
                                await reply_line(reply_token, answer)
                            except Exception as e:
                                logger.error(f"Q&A error: {e}", exc_info=True)
                                # Fallback to natural conversation
                                await handle_natural_conversation(user_id, text, reply_token)
                        
                        else:
                            # Natural conversation for everything else
                            await handle_natural_conversation(user_id, text, reply_token)
                
                elif message_type == "sticker":
                    # Handle sticker messages
                    sticker_id = message.get("stickerId")
                    package_id = message.get("packageId")
                    logger.info(f"Received sticker: packageId={package_id}, stickerId={sticker_id}")
                    
                    # Reply with a friendly sticker response
                    sticker_response = (
                        "😊 ขอบคุณสำหรับสติ๊กเกอร์น่ารักค่ะ!\n\n"
                        "🌱 ฉันพร้อมช่วยคุณตรวจสอบโรคพืชแล้วค่ะ\n\n"
                        "📸 ส่งรูปภาพพืชที่มีปัญหามาให้ฉัน\n"
                        "ฉันจะวิเคราะห์และแนะนำผลิตภัณฑ์ที่เหมาะสมให้ค่ะ\n\n"
                        "💡 พิมพ์ 'ช่วย' เพื่อดูวิธีใช้งาน"
                    )
                    # Reply with text and sticker
                    await reply_line(reply_token, sticker_response, with_sticker=True)
                
                else:
                    # Handle other message types (video, audio, location, etc.)
                    logger.info(f"Received unsupported message type: {message_type}")
                    unsupported_message = (
                        "ขออภัยค่ะ ฉันรองรับเฉพาะ:\n\n"
                        "📸 รูปภาพ - สำหรับตรวจจับโรคพืช\n"
                        "💬 ข้อความ - สำหรับถามคำถาม\n"
                        "😊 สติ๊กเกอร์ - สำหรับทักทาย\n\n"
                        "กรุณาส่งรูปภาพพืชที่มีปัญหามาให้ฉันค่ะ 🌱"
                    )
                    await reply_line(reply_token, unsupported_message)
        
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
    logger.info(f"Gemini API: {'✓' if GEMINI_API_KEY else '✗'}")
    logger.info(f"Supabase: {'✓' if supabase_client else '✗'}")
    logger.info(f"LINE Bot: {'✓' if LINE_CHANNEL_ACCESS_TOKEN else '✗'}")
    logger.info("Vision: Google Gemini 2.5 Flash")
    logger.info("RAG Method: Keyword Search (Fast & Reliable)")
    logger.info("=" * 60)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
