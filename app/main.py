"""
LINE Plant Disease Detection Bot with Google Gemini Vision and Supabase RAG
Production-grade FastAPI implementation with Multi-Agent System
"""

import os
import logging
import time
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
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
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

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

# Initialize Rate Limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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
# Memory System (Supabase-based) + Caching + Cleanup
# ============================================================================#
# In-memory store for pending image contexts awaiting user symptom input
# Keyed by user_id -> dict with image_bytes and reply_token (optional)
pending_image_contexts: Dict[str, Dict[str, Any]] = {}

# Cache configuration
CACHE_TTL = 3600  # 1 hour
PENDING_CONTEXT_TTL = 300  # 5 minutes
MAX_CACHE_SIZE = 1000  # Maximum cache entries

# Detection cache (image hash -> result)
detection_cache: Dict[str, Dict[str, Any]] = {}

# Product recommendation cache (disease_name -> products)
product_cache: Dict[str, Dict[str, Any]] = {}

# Knowledge cache (query -> knowledge)
knowledge_cache: Dict[str, Dict[str, Any]] = {}

# Rate limiting per user
user_request_counts: Dict[str, List[float]] = {}
USER_RATE_LIMIT = 10  # requests per minute
USER_RATE_WINDOW = 60  # seconds

# Memory configuration
MAX_MEMORY_MESSAGES = 20 # Keep last 20messages for context
MEMORY_CONTEXT_WINDOW = 10 # Use last 10messages for context

# ============================================================================#
# Cache Helper Functions
# ============================================================================#
def get_image_hash(image_bytes: bytes) -> str:
    """Generate hash for image caching"""
    return hashlib.md5(image_bytes).hexdigest()

def get_cache_key(prefix: str, key: str) -> str:
    """Generate cache key with prefix"""
    return f"{prefix}:{key}"

async def get_from_cache(cache_dict: dict, key: str) -> Optional[Any]:
    """Get item from cache if not expired"""
    if key not in cache_dict:
        return None
    
    entry = cache_dict[key]
    if time.time() - entry.get("timestamp", 0) > CACHE_TTL:
        # Expired, remove it
        del cache_dict[key]
        return None
    
    logger.info(f"✓ Cache hit: {key[:50]}")
    return entry.get("data")

async def set_to_cache(cache_dict: dict, key: str, data: Any):
    """Set item to cache with timestamp"""
    # Check cache size limit
    if len(cache_dict) >= MAX_CACHE_SIZE:
        # Remove oldest entries (simple FIFO)
        oldest_keys = sorted(cache_dict.keys(), key=lambda k: cache_dict[k].get("timestamp", 0))[:100]
        for old_key in oldest_keys:
            del cache_dict[old_key]
        logger.info(f"Cache cleanup: removed {len(oldest_keys)} old entries")
    
    cache_dict[key] = {
        "data": data,
        "timestamp": time.time()
    }
    logger.info(f"✓ Cache set: {key[:50]}")

async def cleanup_expired_cache():
    """Clean up expired cache entries"""
    current_time = time.time()
    
    # Cleanup detection cache
    expired_keys = [k for k, v in detection_cache.items() if current_time - v.get("timestamp", 0) > CACHE_TTL]
    for key in expired_keys:
        del detection_cache[key]
    
    # Cleanup product cache
    expired_keys = [k for k, v in product_cache.items() if current_time - v.get("timestamp", 0) > CACHE_TTL]
    for key in expired_keys:
        del product_cache[key]
    
    # Cleanup knowledge cache
    expired_keys = [k for k, v in knowledge_cache.items() if current_time - v.get("timestamp", 0) > CACHE_TTL]
    for key in expired_keys:
        del knowledge_cache[key]
    
    # Cleanup pending contexts
    expired_users = [
        user_id for user_id, ctx in pending_image_contexts.items()
        if current_time - ctx.get("timestamp", 0) > PENDING_CONTEXT_TTL
    ]
    for user_id in expired_users:
        del pending_image_contexts[user_id]
    
    if expired_keys or expired_users:
        logger.info(f"Cache cleanup: removed {len(expired_keys)} cache entries, {len(expired_users)} pending contexts")

async def get_cache_stats() -> dict:
    """Get cache statistics"""
    return {
        "detection_cache_size": len(detection_cache),
        "product_cache_size": len(product_cache),
        "knowledge_cache_size": len(knowledge_cache),
        "pending_contexts": len(pending_image_contexts),
        "total_memory_items": len(detection_cache) + len(product_cache) + len(knowledge_cache) + len(pending_image_contexts)
    }

# ============================================================================#
# Rate Limiting Helper Functions
# ============================================================================#
async def check_user_rate_limit(user_id: str) -> bool:
    """Check if user exceeded rate limit"""
    current_time = time.time()
    
    # Initialize user if not exists
    if user_id not in user_request_counts:
        user_request_counts[user_id] = []
    
    # Remove old timestamps outside the window
    user_request_counts[user_id] = [
        ts for ts in user_request_counts[user_id]
        if current_time - ts < USER_RATE_WINDOW
    ]
    
    # Check if exceeded limit
    if len(user_request_counts[user_id]) >= USER_RATE_LIMIT:
        logger.warning(f"Rate limit exceeded for user {user_id[:8]}...")
        return False
    
    # Add current request
    user_request_counts[user_id].append(current_time)
    return True

async def cleanup_rate_limit_data():
    """Clean up old rate limit data"""
    current_time = time.time()
    users_to_remove = []
    
    for user_id, timestamps in user_request_counts.items():
        # Remove old timestamps
        user_request_counts[user_id] = [
            ts for ts in timestamps
            if current_time - ts < USER_RATE_WINDOW
        ]
        
        # If no recent requests, remove user
        if not user_request_counts[user_id]:
            users_to_remove.append(user_id)
    
    for user_id in users_to_remove:
        del user_request_counts[user_id]
    
    if users_to_remove:
        logger.info(f"Rate limit cleanup: removed {len(users_to_remove)} inactive users")

# ============================================================================#
# Background Tasks
# ============================================================================#
async def periodic_cleanup():
    """Run periodic cleanup tasks"""
    while True:
        try:
            await asyncio.sleep(300)  # Run every 5 minutes
            logger.info("Running periodic cleanup...")
            await cleanup_expired_cache()
            await cleanup_rate_limit_data()
            
            # Log stats
            stats = await get_cache_stats()
            logger.info(f"Cache stats: {stats}")
            
        except Exception as e:
            logger.error(f"Error in periodic cleanup: {e}")

@app.on_event("startup")
async def startup_event():
    """Start background tasks on startup"""
    logger.info("Starting background tasks...")
    asyncio.create_task(periodic_cleanup())

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down gracefully...")
    # Clear all caches
    detection_cache.clear()
    product_cache.clear()
    knowledge_cache.clear()
    pending_image_contexts.clear()
    user_request_counts.clear()
    logger.info("All caches cleared")

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
    usage_period: Optional[str] = ""
    usage_rate: Optional[str] = ""
    score: float = 0.0

# ============================================================================#
# Helpers
# ============================================================================#
def post_process_answer(answer: str) -> str:
    """Post-process Gemini answer for better quality"""
    if not answer:
        return ""
    
    import re
    
    # 1. Remove markdown formatting
    answer = answer.replace("```", "")
    answer = answer.replace("**", "")
    answer = answer.replace("##", "")
    answer = answer.replace("###", "")
    answer = re.sub(r'\*\*([^*]+)\*\*', r'\1', answer)  # **text** → text
    answer = re.sub(r'\*([^*]+)\*', r'\1', answer)  # *text* → text
    
    # 2. Fix Thai encoding issues
    answer = re.sub(r'([ก-ฮ])Ğ([ำิีุูเแโใไ่้๊๋])', r'\1\2', answer)
    answer = answer.replace('Ğ', '')
    answer = answer.replace('�', '')
    answer = answer.replace('\x00', '')
    
    # 3. Fix spacing issues
    answer = re.sub(r'\s+', ' ', answer)  # Multiple spaces → single space
    answer = answer.replace(' ,', ',')
    answer = answer.replace(' .', '.')
    answer = answer.replace(' :', ':')
    answer = answer.replace('( ', '(')
    answer = answer.replace(' )', ')')
    
    # 4. Fix bullet points (convert markdown to Thai style)
    answer = re.sub(r'^\s*[-*]\s+', '• ', answer, flags=re.MULTILINE)
    answer = re.sub(r'\n\s*[-*]\s+', '\n• ', answer)
    
    # 5. Ensure proper line breaks
    answer = re.sub(r'\n{3,}', '\n\n', answer)  # Max 2 line breaks
    
    # 6. Remove leading/trailing whitespace
    answer = answer.strip()
    
    # 7. Fix common Thai typos
    answer = answer.replace('ต้', 'ต้')
    answer = answer.replace('ต', 'ต')
    
    # 8. Ensure emoji spacing
    answer = re.sub(r'([🌱🐛🍄💊⚠️✅📚💡🎯📋🔍])([ก-๙A-Za-z])', r'\1 \2', answer)
    
    return answer

def clean_knowledge_text(text: str) -> str:
    """Clean and format knowledge text for better readability"""
    if not text:
        return ""
    
    import re
    
    # Fix encoding issues - remove corrupted characters
    # Common patterns: จĞำ, ลĞำ, ทĞำ, นĞ้ำ, กĞำ
    text = re.sub(r'([ก-ฮ])Ğ([ำ])', r'\1\2', text)  # จĞำ → จำ
    text = re.sub(r'([ก-ฮ])Ğ([้])', r'\1\2', text)  # นĞ้ → น้
    text = re.sub(r'([ก-ฮ])Ğ([ิ])', r'\1\2', text)  # กĞิ → กิ
    text = re.sub(r'([ก-ฮ])Ğ([ี])', r'\1\2', text)  # กĞี → กี
    text = re.sub(r'([ก-ฮ])Ğ([ุ])', r'\1\2', text)  # กĞุ → กุ
    text = re.sub(r'([ก-ฮ])Ğ([ู])', r'\1\2', text)  # กĞู → กู
    text = re.sub(r'([ก-ฮ])Ğ([่])', r'\1\2', text)  # กĞ่ → ก่
    text = re.sub(r'([ก-ฮ])Ğ([้])', r'\1\2', text)  # กĞ้ → ก้
    text = re.sub(r'([ก-ฮ])Ğ([๊])', r'\1\2', text)  # กĞ๊ → ก๊
    text = re.sub(r'([ก-ฮ])Ğ([๋])', r'\1\2', text)  # กĞ๋ → ก๋
    text = re.sub(r'Ğ', '', text)  # Remove remaining Ğ
    
    # Fix other corrupted characters
    text = text.replace('ต้', 'ต้')  # Fix tone marks
    text = text.replace('ต', 'ต')
    text = text.replace('�', '')  # Remove replacement character
    text = text.replace('\x00', '')  # Remove null character
    
    # Fix common Thai encoding issues
    text = text.replace('à¸', '')  # Remove Thai encoding prefix
    text = text.replace('à¹', '')  # Remove Thai encoding prefix
    
    # Remove excessive whitespace
    text = ' '.join(text.split())
    
    # Fix common issues
    text = text.replace('  ', ' ')  # Double spaces
    text = text.replace(' ,', ',')  # Space before comma
    text = text.replace(' .', '.')  # Space before period
    text = text.replace('( ', '(')  # Space after opening parenthesis
    text = text.replace(' )', ')')  # Space before closing parenthesis
    text = text.replace(' :', ':')  # Space before colon
    
    # Fix Thai-specific issues (keep important marks)
    # text = text.replace('ฺ', '')  # Keep Thai character above
    # text = text.replace('์', '')  # Keep Thai character above
    
    # Remove multiple consecutive spaces
    text = re.sub(r'\s+', ' ', text)
    
    # Ensure proper sentence spacing
    text = re.sub(r'([.!?])\s*([A-Za-zก-๙])', r'\1 \2', text)
    
    # Remove leading/trailing whitespace
    text = text.strip()
    
    # Remove lines with only special characters
    lines = text.split('\n')
    cleaned_lines = [line for line in lines if line.strip() and not re.match(r'^[^\w\s]+$', line.strip())]
    text = '\n'.join(cleaned_lines)
    
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
    
    # Check cache first (only if no extra user info)
    if not extra_user_info:
        image_hash = get_image_hash(image_bytes)
        cached_result = await get_from_cache(detection_cache, image_hash)
        if cached_result:
            logger.info("✓ Using cached detection result")
            return DiseaseDetectionResult(**cached_result)
    
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
        
        # Cache the result (only if no extra user info)
        if not extra_user_info:
            image_hash = get_image_hash(image_bytes)
            await set_to_cache(detection_cache, image_hash, result.dict())
        
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
# Core: Retrieve product recommendations (Supabase Vector Search)
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
        
        # Check cache first
        cache_key = f"products:{disease_name}"
        cached_products = await get_from_cache(product_cache, cache_key)
        if cached_products:
            logger.info("✓ Using cached product recommendations")
            return [ProductRecommendation(**p) for p in cached_products]
        
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
        recommendations = build_recommendations_from_data(matches_data[:6])
        
        # Cache the results
        if recommendations:
            await set_to_cache(product_cache, cache_key, [r.dict() for r in recommendations])
        
        return recommendations

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
                                usage_period=product.get('usage_period', ''),
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
            usage_period=product.get("usage_period", ""),
            usage_rate=product.get("usage_rate", ""),
            score=product.get("similarity", 0.7)
        )
        recommendations.append(rec)
    
    return recommendations



# ============================================================================#
# Core: Intent-based Product Recommendation (NEW)
# ============================================================================#
async def recommend_products_by_intent(question: str, keywords: dict) -> str:
    """แนะนำผลิตภัณฑ์ตาม intent ของผู้ใช้ (เพิ่มผลผลิต, แก้ปัญหา, ฯลฯ)"""
    try:
        intent = keywords.get('intent')
        logger.info(f"🎯 Intent-based recommendation: {intent}")
        logger.info(f"📝 Keywords: crops={keywords.get('crops')}, pests={keywords.get('pests')}")
        
        if not supabase_client:
            logger.error("❌ Supabase client not available")
            return await answer_product_question(question, keywords)
        
        if not e5_model:
            logger.error("❌ E5 model not available")
            return await answer_product_question(question, keywords)
        
        intent = keywords.get("intent")
        crops = keywords.get("crops", [])
        pests = keywords.get("pests", [])
        
        # Build search query based on intent
        search_queries = []
        
        if intent == "increase_yield":
            # เพิ่มผลผลิต
            if crops:
                for crop in crops[:2]:
                    search_queries.append(f"เพิ่มผลผลิต {crop}")
                    search_queries.append(f"ปุ๋ยบำรุง {crop}")
                    search_queries.append(f"ฮอร์โมน {crop}")
            else:
                search_queries.append("เพิ่มผลผลิต ปุ๋ย ฮอร์โมน")
        
        elif intent == "solve_problem":
            # แก้ปัญหาศัตรูพืช
            if pests and crops:
                for pest in pests[:2]:
                    for crop in crops[:2]:
                        search_queries.append(f"กำจัด {pest} {crop}")
            elif pests:
                for pest in pests[:2]:
                    search_queries.append(f"กำจัด {pest}")
            elif crops:
                for crop in crops[:2]:
                    search_queries.append(f"ป้องกันโรค {crop}")
        
        elif intent == "general_care":
            # ดูแลทั่วไป
            if crops:
                for crop in crops[:2]:
                    search_queries.append(f"ดูแล {crop}")
                    search_queries.append(f"บำรุง {crop}")
        
        else:
            # Default: product inquiry
            if crops:
                search_queries.append(f"ผลิตภัณฑ์ {crops[0]}")
            if pests:
                search_queries.append(f"กำจัด {pests[0]}")
        
        # Vector search for each query
        all_products = []
        logger.info(f"🔍 Searching with {len(search_queries)} queries: {search_queries[:3]}")
        
        for query in search_queries[:3]:  # Top 3 queries
            try:
                logger.info(f"   → Query: '{query}'")
                query_embedding = e5_model.encode(f"query: {query}", normalize_embeddings=True).tolist()
                
                result = supabase_client.rpc(
                    'match_products',
                    {
                        'query_embedding': query_embedding,
                        'match_threshold': 0.25,  # Lower threshold for more results
                        'match_count': 10
                    }
                ).execute()
                
                if result.data:
                    all_products.extend(result.data)
                    logger.info(f"   ✓ Found {len(result.data)} products")
                else:
                    logger.warning(f"   ⚠️ No products found")
            except Exception as e:
                logger.error(f"   ❌ Vector search failed: {e}", exc_info=True)
        
        # Remove duplicates
        seen = set()
        unique_products = []
        for p in all_products:
            pname = p.get('product_name', '')
            if pname and pname not in seen:
                seen.add(pname)
                unique_products.append(p)
        
        logger.info(f"📦 Total products: {len(all_products)}, Unique: {len(unique_products)}")
        
        if not unique_products:
            # Fallback to keyword search
            logger.warning("⚠️ No products from vector search, trying keyword search")
            return await answer_product_question(question, keywords)
        
        # Log product names
        product_names = [p.get('product_name', 'N/A') for p in unique_products[:5]]
        logger.info(f"📋 Top products: {', '.join(product_names)}")
        
        # Use Gemini to filter and create natural response
        products_text = ""
        for idx, p in enumerate(unique_products[:15], 1):  # Top 15 for Gemini
            products_text += f"\n[{idx}] {p.get('product_name', 'N/A')}"
            products_text += f"\n    สารสำคัญ: {p.get('active_ingredient', 'N/A')}"
            products_text += f"\n    ศัตรูพืช: {p.get('target_pest', 'N/A')[:100]}"
            products_text += f"\n    ใช้กับพืช: {p.get('applicable_crops', 'N/A')[:80]}"
            products_text += f"\n    ช่วงการใช้: {p.get('usage_period', 'N/A')}"
            products_text += f"\n    อัตราใช้: {p.get('usage_rate', 'N/A')}"
            products_text += f"\n    Similarity: {p.get('similarity', 0):.0%}\n"
        
        # Create intent-specific prompt
        if intent == "increase_yield":
            prompt = f"""คุณคือผู้เชี่ยวชาญด้านการเพิ่มผลผลิตพืช

คำถามจากเกษตรกร: {question}

ผลิตภัณฑ์ที่พบในระบบ:
{products_text}

🎯 **ภารกิจ**: แนะนำผลิตภัณฑ์เพื่อเพิ่มผลผลิต

📋 **คำแนะนำในการตอบ**:
1. **เลือกผลิตภัณฑ์ที่เหมาะสม** 3-5 รายการ:
   - ปุ๋ยบำรุง (NPK, ปุ๋ยอินทรีย์)
   - ฮอร์โมนเร่งการเจริญเติบโต
   - สารเสริมภูมิคุ้มกัน
   - ผลิตภัณฑ์ที่ช่วยเพิ่มคุณภาพผลผลิต

2. **จัดกลุ่มผลิตภัณฑ์**:
   - กลุ่มที่ 1: ปุ๋ยบำรุง (เพิ่มการเจริญเติบโต)
   - กลุ่มที่ 2: ฮอร์โมน/PGR (เพิ่มผลผลิต)
   - กลุ่มที่ 3: ป้องกันโรค (รักษาคุณภาพ)

3. **แสดงรายละเอียด**:
   - ชื่อผลิตภัณฑ์
   - ประโยชน์ (เพิ่มผลผลิตอย่างไร)
   - วิธีใช้และเวลาที่เหมาะสม
   - ผลลัพธ์ที่คาดหวัง

4. **เพิ่มคำแนะนำ**:
   - ควรใช้ร่วมกันอย่างไร
   - ช่วงเวลาที่เหมาะสม (ก่อนออกดอก, ติดผล)
   - ข้อควรระวัง

5. **ใช้ภาษาง่ายๆ** พร้อม emoji (🌱 💪 ⭐ ✅)
6. **ไม่ใช้ markdown** - ตอบเป็นข้อความธรรมดา

⚠️ **สำคัญ**:
- เลือกเฉพาะผลิตภัณฑ์ที่เกี่ยวข้องกับการเพิ่มผลผลิต
- ถ้าถามเกี่ยวกับพืชเฉพาะ ให้เลือกที่ใช้กับพืชนั้นได้
- ห้ามแนะนำยากำจัดศัตรูพืช (ยกเว้นเป็นส่วนเสริม)

ตอบคำถาม:"""
        
        elif intent == "solve_problem":
            prompt = f"""คุณคือผู้เชี่ยวชาญด้านการแก้ปัญหาศัตรูพืช

คำถามจากเกษตรกร: {question}

ผลิตภัณฑ์ที่พบในระบบ:
{products_text}

🎯 **ภารกิจ**: แนะนำผลิตภัณฑ์เพื่อแก้ปัญหาศัตรูพืช

📋 **คำแนะนำในการตอบ**:
1. **วิเคราะห์ปัญหา**:
   - ศัตรูพืชที่พบ: {', '.join(pests) if pests else 'ไม่ระบุ'}
   - พืชที่ปลูก: {', '.join(crops) if crops else 'ไม่ระบุ'}

2. **เลือกผลิตภัณฑ์ที่เหมาะสม** 3-5 รายการ:
   - ต้องกำจัดศัตรูพืชที่ระบุได้
   - ต้องใช้กับพืชที่ระบุได้
   - จัดลำดับตามความเหมาะสม

3. **แสดงรายละเอียด**:
   - ชื่อผลิตภัณฑ์
   - สารสำคัญ
   - ศัตรูพืชที่กำจัดได้
   - อัตราการใช้
   - วิธีใช้ให้ได้ผล

4. **เพิ่มเคล็ดลับ**:
   - เวลาที่เหมาะสมในการพ่น
   - จำนวนครั้งที่ควรพ่น
   - การสลับสารเพื่อป้องกันการดื้อยา
   - ข้อควรระวัง

5. **ใช้ภาษาง่ายๆ** พร้อม emoji (💊 🐛 ⚡ ✅)
6. **ไม่ใช้ markdown** - ตอบเป็นข้อความธรรมดา

⚠️ **สำคัญ**:
- เลือกเฉพาะผลิตภัณฑ์ที่กำจัดศัตรูพืชที่ระบุได้
- ถ้าระบุพืช ต้องเลือกที่ใช้กับพืชนั้นได้
- ห้ามแนะนำผลิตภัณฑ์ที่ไม่เกี่ยวข้อง

ตอบคำถาม:"""
        
        else:
            # General product inquiry
            prompt = f"""คุณคือผู้เชี่ยวชาญด้านผลิตภัณฑ์เกษตรของ ICP Ladda

คำถามจากเกษตรกร: {question}

ผลิตภัณฑ์ที่พบในระบบ:
{products_text}

🎯 **ภารกิจ**: แนะนำผลิตภัณฑ์ที่เหมาะสม

📋 **คำแนะนำในการตอบ**:
1. **เลือกผลิตภัณฑ์ที่เหมาะสม** 3-5 รายการ
2. **จัดลำดับ** ตามความเหมาะสม
3. **แสดงรายละเอียด** ครบถ้วน
4. **เพิ่มคำแนะนำ** การใช้งาน
5. **ใช้ภาษาง่ายๆ** พร้อม emoji
6. **ไม่ใช้ markdown**

ตอบคำถาม:"""
        
        # Check if Gemini is available
        if not gemini_model:
            logger.warning("Gemini model not available, using simple format")
            return await format_product_list_simple(unique_products[:5], question, intent)
        
        try:
            response = gemini_model.generate_content(prompt)
            answer = response.text.strip()
            answer = answer.replace("```", "").replace("**", "").replace("##", "")
            
            # Add footer
            answer += "\n\n" + "="*40
            answer += "\n📚 ดูรายละเอียดผลิตภัณฑ์ทั้งหมด:"
            answer += "\n🔗 https://www.icpladda.com/about/"
            answer += "\n\n💡 หากต้องการข้อมูลเพิ่มเติม กรุณาถามได้เลยค่ะ 😊"
            
            logger.info(f"✓ Intent-based answer generated ({intent})")
            return answer
            
        except Exception as e:
            logger.error(f"Gemini generation failed: {e}", exc_info=True)
            # Fallback to simple product list
            return await format_product_list_simple(unique_products[:5], question, intent)
        
    except Exception as e:
        logger.error(f"Error in intent-based recommendation: {e}", exc_info=True)
        return await answer_product_question(question, keywords)

async def format_product_list_simple(products: list, question: str, intent: str) -> str:
    """Format product list as simple fallback"""
    if intent == "increase_yield":
        header = "🌱 ผลิตภัณฑ์แนะนำสำหรับเพิ่มผลผลิต:\n"
    elif intent == "solve_problem":
        header = "💊 ผลิตภัณฑ์แนะนำสำหรับแก้ปัญหาศัตรูพืช:\n"
    else:
        header = "📦 ผลิตภัณฑ์แนะนำ:\n"
    
    response = header
    for idx, p in enumerate(products, 1):
        response += f"\n{idx}. {p.get('product_name', 'N/A')}"
        if p.get('active_ingredient'):
            response += f"\n   สารสำคัญ: {p.get('active_ingredient')}"
        if p.get('target_pest'):
            pest = p.get('target_pest')[:80] + "..." if len(p.get('target_pest', '')) > 80 else p.get('target_pest', '')
            response += f"\n   ศัตรูพืช: {pest}"
        if p.get('applicable_crops'):
            crops = p.get('applicable_crops')[:60] + "..." if len(p.get('applicable_crops', '')) > 60 else p.get('applicable_crops', '')
            response += f"\n   ใช้กับพืช: {crops}"
        if p.get('usage_period'):
            response += f"\n   ช่วงการใช้: {p.get('usage_period')}"
        if p.get('usage_rate'):
            response += f"\n   อัตราใช้: {p.get('usage_rate')}"
        response += "\n"
        if p.get('active_ingredient'):
            response += f"\n   สารสำคัญ: {p.get('active_ingredient')}"
        if p.get('target_pest'):
            pest = p.get('target_pest')[:80] + "..." if len(p.get('target_pest', '')) > 80 else p.get('target_pest', '')
            response += f"\n   ศัตรูพืช: {pest}"
        if p.get('applicable_crops'):
            crops = p.get('applicable_crops')[:60] + "..." if len(p.get('applicable_crops', '')) > 60 else p.get('applicable_crops', '')
            response += f"\n   ใช้กับพืช: {crops}"
        if p.get('usage_period'):
            response += f"\n   ช่วงการใช้: {p.get('usage_period')}"
        if p.get('usage_rate'):
            response += f"\n   อัตราใช้: {p.get('usage_rate')}"
        response += "\n"
    
    response += "\n📚 ดูรายละเอียดเพิ่มเติม: https://www.icpladda.com/about/"
    return response

# ============================================================================#
# Core: Product-specific Q&A
# ============================================================================#
async def answer_product_question(question: str, keywords: dict) -> str:
    """Answer product-specific questions with high accuracy"""
    try:
        logger.info(f"Product-specific query: {question[:50]}...")
        
        if not supabase_client:
            return "ขออภัยค่ะ ระบบไม่พร้อมใช้งานในขณะนี้"
        
        products_data = []
        
        # Search by pest/disease
        if keywords["pests"]:
            for pest in keywords["pests"][:2]:
                result = supabase_client.table('products')\
                    .select('*')\
                    .ilike('target_pest', f'%{pest}%')\
                    .limit(5)\
                    .execute()
                if result.data:
                    products_data.extend(result.data)
        
        # Search by crop
        if keywords["crops"]:
            for crop in keywords["crops"][:2]:
                result = supabase_client.table('products')\
                    .select('*')\
                    .ilike('applicable_crops', f'%{crop}%')\
                    .limit(5)\
                    .execute()
                if result.data:
                    products_data.extend(result.data)
        
        # Search by product name
        if keywords["products"]:
            for prod in keywords["products"]:
                if len(prod) > 3:
                    result = supabase_client.table('products')\
                        .select('*')\
                        .ilike('product_name', f'%{prod}%')\
                        .limit(5)\
                        .execute()
                    if result.data:
                        products_data.extend(result.data)
        
        # If no specific keywords, get general products
        if not products_data:
            result = supabase_client.table('products')\
                .select('*')\
                .limit(10)\
                .execute()
            if result.data:
                products_data = result.data
        
        if not products_data:
            return "ขออภัยค่ะ ไม่พบผลิตภัณฑ์ที่เกี่ยวข้อง กรุณาระบุชื่อพืชหรือศัตรูพืชที่ต้องการกำจัดค่ะ 🌱"
        
        # Remove duplicates
        seen = set()
        unique_products = []
        for p in products_data:
            pname = p.get('product_name', '')
            if pname and pname not in seen:
                seen.add(pname)
                unique_products.append(p)
        
        # Use Gemini to filter and format response
        products_text = ""
        for idx, p in enumerate(unique_products[:10], 1):
            products_text += f"\n[{idx}] {p.get('product_name', 'N/A')}"
            products_text += f"\n    สารสำคัญ: {p.get('active_ingredient', 'N/A')}"
            products_text += f"\n    ศัตรูพืช: {p.get('target_pest', 'N/A')[:100]}"
            products_text += f"\n    ใช้กับพืช: {p.get('applicable_crops', 'N/A')[:80]}"
            products_text += f"\n    ช่วงการใช้: {p.get('usage_period', 'N/A')}"
            products_text += f"\n    อัตราใช้: {p.get('usage_rate', 'N/A')}"
            products_text += "\n"
        
        prompt = f"""คุณคือผู้เชี่ยวชาญด้านผลิตภัณฑ์ป้องกันกำจัดศัตรูพืชของ ICP Ladda

คำถามจากเกษตรกร: {question}

ผลิตภัณฑ์ที่พบในระบบ:
{products_text}

คำแนะนำในการตอบ:
1. **วิเคราะห์คำถาม** - เข้าใจว่าเกษตรกรต้องการอะไร
2. **เลือกผลิตภัณฑ์ที่เหมาะสม** - เลือก 3-5 รายการที่ตรงที่สุด
3. **จัดลำดับ** - ผลิตภัณฑ์ที่เหมาะสมที่สุดก่อน
4. **แสดงรายละเอียด**:
   - ชื่อผลิตภัณฑ์
   - สารสำคัญ
   - ศัตรูพืชที่กำจัดได้
   - พืชที่ใช้ได้
   - อัตราการใช้
   - วิธีใช้โดยย่อ
5. **เพิ่มคำแนะนำ**:
   - อ่านฉลากก่อนใช้
   - ใช้อุปกรณ์ป้องกันตัว
   - ทดสอบในพื้นที่เล็กก่อน
6. **ใช้ภาษาง่ายๆ** พร้อม emoji (💊 🌱 ✅ ⚠️)
7. **ไม่ใช้ markdown** - ตอบเป็นข้อความธรรมดา

⚠️ **เกณฑ์การเลือก**:
- ถ้าถามเกี่ยวกับพืชเฉพาะ → เลือกเฉพาะที่ใช้กับพืชนั้นได้
- ถ้าถามเกี่ยวกับศัตรูพืช → เลือกที่กำจัดศัตรูพืชนั้นได้
- ถ้าถามทั่วไป → แนะนำผลิตภัณฑ์ยอดนิยม 3-5 รายการ

ตอบคำถาม:"""

        try:
            response = gemini_model.generate_content(prompt)
            answer = response.text.strip()
            answer = answer.replace("```", "").replace("**", "").replace("##", "")
            
            # Add footer
            answer += "\n\n" + "="*40
            answer += "\n📚 ดูรายละเอียดผลิตภัณฑ์ทั้งหมด:"
            answer += "\n🔗 https://www.icpladda.com/about/"
            answer += "\n\n💡 หากต้องการข้อมูลเพิ่มเติม กรุณาถามได้เลยค่ะ 😊"
            
            logger.info("✓ Product answer generated successfully")
            return answer
            
        except Exception as e:
            logger.error(f"Gemini generation failed: {e}")
            # Fallback: return top 3 products directly
            response = "💊 ผลิตภัณฑ์แนะนำจาก ICP Ladda:\n"
            for idx, p in enumerate(unique_products[:3], 1):
                response += f"\n{idx}. {p.get('product_name')}"
                if p.get('active_ingredient'):
                    response += f"\n   สารสำคัญ: {p.get('active_ingredient')}"
                if p.get('target_pest'):
                    pest = p.get('target_pest')[:80] + "..." if len(p.get('target_pest', '')) > 80 else p.get('target_pest', '')
                    response += f"\n   ศัตรูพืช: {pest}"
                if p.get('applicable_crops'):
                    crops = p.get('applicable_crops')[:60] + "..." if len(p.get('applicable_crops', '')) > 60 else p.get('applicable_crops', '')
                    response += f"\n   ใช้กับพืช: {crops}"
                if p.get('usage_period'):
                    response += f"\n   ช่วงการใช้: {p.get('usage_period')}"
                if p.get('usage_rate'):
                    response += f"\n   อัตราใช้: {p.get('usage_rate')}"
                response += "\n"
            
            response += "\n📚 ดูรายละเอียดเพิ่มเติม: https://www.icpladda.com/about/"
            return response
        
    except Exception as e:
        logger.error(f"Error in product Q&A: {e}", exc_info=True)
        return "ขออภัยค่ะ ไม่สามารถค้นหาผลิตภัณฑ์ได้ในขณะนี้ กรุณาลองใหม่อีกครั้งค่ะ 🙏"

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
                    'match_threshold': 0.6,  # Lower threshold for more results
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
        
        # 3. Search for relevant products (Enhanced)
        products_info = ""
        try:
            # Extract keywords for product search
            keywords = extract_keywords_from_question(question)
            products_data = []
            
            # Strategy 1: Search by pest/disease
            if keywords["pests"]:
                for pest in keywords["pests"][:2]:  # Top 2 pests
                    result = supabase_client.table('products')\
                        .select('product_name, active_ingredient, target_pest, applicable_crops, how_to_use, usage_rate')\
                        .ilike('target_pest', f'%{pest}%')\
                        .limit(5)\
                        .execute()
                    if result.data:
                        products_data.extend(result.data)
            
            # Strategy 2: Search by crop
            if keywords["crops"]:
                for crop in keywords["crops"][:2]:  # Top 2 crops
                    result = supabase_client.table('products')\
                        .select('product_name, active_ingredient, target_pest, applicable_crops, how_to_use, usage_rate')\
                        .ilike('applicable_crops', f'%{crop}%')\
                        .limit(5)\
                        .execute()
                    if result.data:
                        products_data.extend(result.data)
            
            # Strategy 3: Search by product name (if asking about specific product)
            if keywords["products"]:
                for prod in keywords["products"][:2]:
                    if len(prod) > 3:  # Skip short words like "ยา", "ใช้"
                        result = supabase_client.table('products')\
                            .select('product_name, active_ingredient, target_pest, applicable_crops, how_to_use, usage_rate')\
                            .ilike('product_name', f'%{prod}%')\
                            .limit(5)\
                            .execute()
                        if result.data:
                            products_data.extend(result.data)
            
            # Remove duplicates and format
            if products_data:
                seen = set()
                unique_products = []
                for p in products_data:
                    pname = p.get('product_name', '')
                    if pname and pname not in seen:
                        seen.add(pname)
                        unique_products.append(p)
                
                # Limit to top 5 products
                products_list = []
                for p in unique_products[:5]:
                    prod_text = f"\n📦 {p.get('product_name')}"
                    if p.get('active_ingredient'):
                        prod_text += f"\n   สารสำคัญ: {p.get('active_ingredient')}"
                    if p.get('target_pest'):
                        pest_short = p.get('target_pest')[:80] + "..." if len(p.get('target_pest', '')) > 80 else p.get('target_pest', '')
                        prod_text += f"\n   ศัตรูพืช: {pest_short}"
                    if p.get('applicable_crops'):
                        crops_short = p.get('applicable_crops')[:60] + "..." if len(p.get('applicable_crops', '')) > 60 else p.get('applicable_crops', '')
                        prod_text += f"\n   ใช้กับพืช: {crops_short}"
                    if p.get('usage_period'):
                        prod_text += f"\n   ช่วงการใช้: {p.get('usage_period')}"
                    if p.get('usage_rate'):
                        prod_text += f"\n   อัตราใช้: {p.get('usage_rate')}"
                    products_list.append(prod_text)
                
                products_info = "\n".join(products_list)
                logger.info(f"Found {len(unique_products)} relevant products")
        except Exception as e:
            logger.warning(f"Product search failed: {e}")
        
        # 4. Use Gemini to generate natural answer
        # Detect if this is a product-focused query
        keywords = extract_keywords_from_question(question)
        is_product_query = keywords["is_product_query"] or any(word in question.lower() for word in ["ผลิตภัณฑ์", "สินค้า", "ยา", "แนะนำ", "ใช้อะไร", "พ่นอะไร"])
        
        if is_product_query and products_info:
            # Product-focused response
            prompt = f"""คุณคือผู้เชี่ยวชาญด้านผลิตภัณฑ์ป้องกันกำจัดศัตรูพืชของ ICP Ladda

คำถามจากเกษตรกร: {question}

ผลิตภัณฑ์ที่เกี่ยวข้อง:
{products_info}

ความรู้เพิ่มเติม:
{combined_knowledge if combined_knowledge else "ไม่มีข้อมูลเพิ่มเติม"}

คำแนะนำในการตอบ:
1. **เน้นผลิตภัณฑ์เป็นหลัก** - แนะนำผลิตภัณฑ์ที่ตรงกับคำถามมากที่สุด
2. **จัดลำดับความเหมาะสม** - ผลิตภัณฑ์ที่เหมาะสมที่สุดก่อน
3. **ระบุรายละเอียดสำคัญ**:
   - ชื่อผลิตภัณฑ์
   - สารสำคัญ
   - ศัตรูพืชที่กำจัดได้
   - พืชที่ใช้ได้
   - อัตราการใช้
   - วิธีใช้โดยย่อ
4. **เพิ่มคำแนะนำ** เช่น:
   - ควรอ่านฉลากก่อนใช้
   - ทดสอบในพื้นที่เล็กก่อน
   - ใช้อุปกรณ์ป้องกันตัว
5. **ใช้ภาษาง่ายๆ** ที่เกษตรกรเข้าใจได้
6. **เพิ่ม emoji** ให้น่าอ่าน (💊 🌱 ✅ ⚠️)
7. **ตอบเป็นภาษาไทยเท่านั้น** ไม่ใช้ markdown

⚠️ **สำคัญ**: 
- ถ้าถามเกี่ยวกับพืชเฉพาะ (เช่น ทุเรียน ข้าว มะม่วง) ให้เลือกเฉพาะผลิตภัณฑ์ที่ใช้กับพืชนั้นได้
- ถ้าถามเกี่ยวกับศัตรูพืชเฉพาะ ให้เลือกผลิตภัณฑ์ที่กำจัดศัตรูพืชนั้นได้
- ห้ามแนะนำผลิตภัณฑ์ที่ไม่เกี่ยวข้อง

ตอบคำถาม:"""
        else:
            # General knowledge response with enhanced filtering
            prompt = f"""คุณคือผู้เชี่ยวชาญด้านโรคพืชและศัตรูพืชของกรมวิชาการเกษตรไทย มีประสบการณ์ 20 ปี

🎯 **คำถามจากเกษตรกร**: {question}

📚 **ความรู้จากฐานข้อมูล**:
{combined_knowledge}

💊 **ผลิตภัณฑ์ที่เกี่ยวข้อง**:
{products_info if products_info else "ไม่มีข้อมูลผลิตภัณฑ์"}

📋 **คำแนะนำในการตอบ**:

1. **วิเคราะห์และกรองข้อมูล**:
   - อ่านความรู้ทั้งหมดอย่างละเอียด
   - เลือกเฉพาะข้อมูลที่เกี่ยวข้องกับคำถามโดยตรง
   - ตัดข้อมูลที่ไม่เกี่ยวข้องออก
   - แก้ไขตัวอักษรที่ผิดพลาด (เช่น จĞำ → จำ, ต้ → ต้)

2. **จัดระเบียบคำตอบ**:
   - เริ่มด้วยคำตอบโดยตรง (ตอบคำถามก่อน)
   - แบ่งเป็นหัวข้อชัดเจน:
     • ลักษณะ/อาการ (ถ้าเกี่ยวข้อง)
     • สาเหตุ (ถ้าเกี่ยวข้อง)
     • วิธีป้องกัน
     • วิธีกำจัด/รักษา
     • ผลิตภัณฑ์แนะนำ (ถ้ามี)

3. **ให้ข้อมูลที่ถูกต้องและเฉพาะเจาะจง**:
   - ตอบเฉพาะสิ่งที่ถูกถาม
   - ใช้ข้อมูลจากฐานข้อมูลเท่านั้น
   - ห้ามสร้างข้อมูลเอง
   - ถ้าไม่มีข้อมูล ให้บอกตรงๆ

4. **ใช้ภาษาที่ถูกต้องและเข้าใจง่าย**:
   - แก้ไขตัวอักษรที่ผิดพลาดทั้งหมด
   - ใช้ภาษาไทยที่ถูกต้อง
   - หลีกเลี่ยงศัพท์เทคนิคที่ยากเกินไป
   - อธิบายให้เกษตรกรเข้าใจได้

5. **จัดรูปแบบให้อ่านง่าย**:
   - ใช้ emoji ให้เหมาะสม (🌱 🐛 🍄 💊 ⚠️ ✅)
   - แบ่งย่อหน้าชัดเจน
   - ใช้ bullet points (•) แทน markdown
   - ไม่ใช้ markdown (**, ##, ```)

6. **เพิ่มคุณค่า**:
   - เพิ่มเคล็ดลับที่เป็นประโยชน์
   - ข้อควรระวัง
   - คำแนะนำเพิ่มเติม

⚠️ **ข้อห้าม**:
- ห้ามใช้ markdown (**, ##, ```)
- ห้ามสร้างข้อมูลเอง
- ห้ามตอบนอกเรื่อง
- ห้ามใช้ตัวอักษรที่ผิดพลาด (ต้องแก้ไขให้ถูกต้อง)

✅ **ตัวอย่างการแก้ไขตัวอักษร**:
- จĞำ → จำ
- ต้ → ต้
- ลĞำ → ลำ
- นĞ้ำ → น้ำ

ตอบคำถาม (ภาษาไทยที่ถูกต้อง ไม่ใช้ markdown):"""

        try:
            response = gemini_model.generate_content(prompt)
            answer = response.text.strip()
            
            # Post-process answer for better quality
            answer = post_process_answer(answer)
            
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
        
        if not keywords["pests"] and not keywords["crops"] and not keywords["products"]:
            return "ขออภัยค่ะ ฉันไม่เข้าใจคำถาม กรุณาถามใหม่อีกครั้งหรือส่งรูปภาพพืชที่มีปัญหามาให้ฉันตรวจสอบค่ะ 🌱"
        
        # Search in knowledge table
        search_term = keywords["pests"][0] if keywords["pests"] else (keywords["crops"][0] if keywords["crops"] else keywords["products"][0])
        
        result = supabase_client.table('knowledge')\
            .select('content')\
            .ilike('content', f'%{search_term}%')\
            .limit(2)\
            .execute()
        
        # Also search products
        products_result = None
        if keywords["pests"] or keywords["crops"]:
            if keywords["pests"]:
                products_result = supabase_client.table('products')\
                    .select('product_name, active_ingredient, target_pest, applicable_crops')\
                    .ilike('target_pest', f'%{keywords["pests"][0]}%')\
                    .limit(3)\
                    .execute()
            elif keywords["crops"]:
                products_result = supabase_client.table('products')\
                    .select('product_name, active_ingredient, target_pest, applicable_crops')\
                    .ilike('applicable_crops', f'%{keywords["crops"][0]}%')\
                    .limit(3)\
                    .execute()
        
        response_parts = []
        
        if result.data:
            # Clean and format knowledge
            cleaned_items = []
            for item in result.data:
                content = item.get('content', '')
                cleaned = clean_knowledge_text(content)
                if cleaned:
                    cleaned_items.append(cleaned[:300])
            
            if cleaned_items:
                knowledge = "\n\n".join(cleaned_items)
                response_parts.append(f"📚 ข้อมูลที่เกี่ยวข้อง:\n\n{knowledge}")
        
        if products_result and products_result.data:
            products_text = "\n\n💊 ผลิตภัณฑ์แนะนำ:\n"
            for idx, p in enumerate(products_result.data, 1):
                products_text += f"\n{idx}. {p.get('product_name')}"
                if p.get('active_ingredient'):
                    products_text += f"\n   สารสำคัญ: {p.get('active_ingredient')}"
                if p.get('applicable_crops'):
                    crops = p.get('applicable_crops')[:60] + "..." if len(p.get('applicable_crops', '')) > 60 else p.get('applicable_crops', '')
                    products_text += f"\n   ใช้กับพืช: {crops}"
            response_parts.append(products_text)
        
        if response_parts:
            response = "\n\n".join(response_parts)
            response += "\n\n💡 หากต้องการข้อมูลเพิ่มเติม กรุณาถามคำถามที่เฉพาะเจาะจงมากขึ้นค่ะ"
            return response
        else:
            return "ขออภัยค่ะ ไม่พบข้อมูลที่เกี่ยวข้อง กรุณาลองถามคำถามอื่นหรือส่งรูปภาพพืชที่มีปัญหามาให้ฉันตรวจสอบค่ะ 🌱"
            
    except Exception as e:
        logger.error(f"Keyword search failed: {e}")
        return "ขออภัยค่ะ เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้งค่ะ"

def extract_keywords_from_question(question: str) -> dict:
    """Extract main keywords from question with categories"""
    question_lower = question.lower()
    
    # Pest/Disease keywords (expanded)
    pest_keywords = [
        "เพลี้ยไฟ", "เพลี้ยอ่อน", "เพลี้ย", "หนอน", "แมลง", "ด้วงงวง",
        "ราน้ำค้าง", "ราแป้ง", "ราสนิม", "เชื้อรา", "รา", "แอนแทรคโนส",
        "ไวรัส", "โรคใบด่าง", "โรคใบหงิก",
        "วัชพืช", "หญ้า", "ผักบุ้ง", "หญ้าคา",
        "โรคพืช", "ศัตรูพืช", "ไร", "เพลี้ยแป้ง", "หนอนกระทู้ข้าว",
        "จักจั่น", "หนอนเจาะ", "หนอนกอ", "หนอนใย", "ด้วง", "มด", "ปลวก",
        "เพลี้ยจักจั่น", "แมลงวันผล", "แมลงหวี่ขาว", "ทริปส์"
    ]
    
    # Crop keywords (expanded)
    crop_keywords = [
        "ทุเรียน", "มะม่วง", "ข้าว", "พืชผัก", "ผัก", "ผลไม้",
        "มะนาว", "ส้ม", "กล้วย", "มะพร้าว", "ยางพารา", "ปาล์ม",
        "ข้าวโพด", "อ้อย", "มันสำปะหลัง", "ถั่ว", "พริก", "มะเขือเทศ",
        "ลำไย", "ลิ้นจี่", "เงาะ", "มังคุด", "ฝรั่ง", "ชมพู่"
    ]
    
    # Product-related keywords
    product_keywords = [
        "ผลิตภัณฑ์", "สินค้า", "ยา", "สาร", "ปุ๋ย",
        "icp", "ladda", "icpl", "ไอซีพี", "ลัดดา",
        "โมเดิน", "ไดอะซินอน", "อิมิดาโคลพริด", "ไซเพอร์เมทริน",
        "แนะนำ", "ใช้", "พ่น", "ฉีด", "กำจัด", "ป้องกัน"
    ]
    
    # Intent keywords (NEW)
    intent_keywords = {
        "increase_yield": ["เพิ่มผลผลิต", "ผลผลิตสูง", "ผลผลิตมาก", "ผลผลิตดี", "ผลผลิตเยอะ", "ผลผลิตขึ้น", "ผลผลิตดีขึ้น", "ผลผลิตเพิ่ม"],
        "solve_problem": ["แก้ปัญหา", "แก้ไข", "รักษา", "กำจัด", "ป้องกัน", "ควบคุม"],
        "general_care": ["ดูแล", "บำรุง", "เลี้ยง", "ปลูก", "ใส่ปุ๋ย"],
        "product_inquiry": ["มีอะไรบ้าง", "มีไหม", "แนะนำ", "ควรใช้", "ใช้อะไร", "ซื้อ"]
    }
    
    found = {
        "pests": [],
        "crops": [],
        "products": [],
        "intent": None,  # NEW: detect user intent
        "is_product_query": False
    }
    
    # Extract pests
    for keyword in pest_keywords:
        if keyword in question_lower:
            found["pests"].append(keyword)
    
    # Extract crops
    for keyword in crop_keywords:
        if keyword in question_lower:
            found["crops"].append(keyword)
    
    # Extract product-related
    for keyword in product_keywords:
        if keyword in question_lower:
            found["products"].append(keyword)
            found["is_product_query"] = True
    
    # Detect intent (NEW)
    for intent, keywords in intent_keywords.items():
        for keyword in keywords:
            if keyword in question_lower:
                found["intent"] = intent
                found["is_product_query"] = True
                break
        if found["intent"]:
            break
    
    return found

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

        # ตรวจสอบว่าเป็นกรณีที่ไม่ควรแนะนำสินค้า
        disease_name_lower = disease_info.disease_name.lower()
        
        # กรณีที่ 1: ไม่พบปัญหา/โรค
        if "ไม่พบปัญหา" in disease_name_lower or "ไม่พบโรค" in disease_name_lower:
            body = "✅ **ข่าวดี!** พืชของคุณดูสุขภาพดี ไม่พบปัญหาที่น่ากังวล\n\n"
            body += "� ด**คำแนะนำในการดูแล**:\n"
            body += "• รักษาความชื้นในดินให้เหมาะสม\n"
            body += "• ให้ปุ๋ยตามกำหนดเวลา\n"
            body += "• ตรวจสอบพืชเป็นประจำ\n"
            body += "• ระวังการเปลี่ยนแปลงของสภาพอากาศ\n\n"
            body += "🌱 **การป้องกัน**:\n"
            body += "• รักษาความสะอาดรอบแปลง\n"
            body += "• ตัดใบแก่หรือเสียหายออก\n"
            body += "• ระบายน้ำให้ดี\n"
            body += "• หมั่นสังเกตอาการผิดปกติ\n\n"
            body += "📸 หากพบอาการผิดปกติในภายหลัง สามารถส่งรูปมาให้ฉันตรวจสอบได้เลยค่ะ 😊"
            return header + body
        
        # กรณีที่ 2: ไม่สามารถวิเคราะห์ได้ / ภาพไม่ชัด / ไม่พบพืช
        if any(keyword in disease_name_lower for keyword in [
            "ไม่สามารถวิเคราะห์",
            "ไม่พบพืช",
            "ภาพไม่ชัด",
            "ไม่ชัดเจน",
            "ไม่สามารถระบุ"
        ]):
            body = "⚠️ **ไม่สามารถวิเคราะห์ได้**\n\n"
            body += "📸 **เพื่อผลการวิเคราะห์ที่แม่นยำ กรุณา**:\n\n"
            body += "1️⃣ **ถ่ายรูปให้ชัดเจน**\n"
            body += "   • ใช้แสงสว่างเพียงพอ (แสงธรรมชาติดีที่สุด)\n"
            body += "   • ไม่เบลอ ไม่สั่น\n"
            body += "   • โฟกัสที่บริเวณที่มีปัญหา\n\n"
            body += "2️⃣ **ถ่ายใกล้พอ**\n"
            body += "   • เห็นรายละเอียดของใบ/ลำต้น/ผล\n"
            body += "   • เห็นอาการชัดเจน (จุด, แผล, สี)\n"
            body += "   • ระยะ 20-50 ซม. จากพืช\n\n"
            body += "3️⃣ **ถ่ายส่วนที่มีปัญหา**\n"
            body += "   • ใบที่เสียหาย\n"
            body += "   • บริเวณที่มีแมลง\n"
            body += "   • ส่วนที่เปลี่ยนสี\n\n"
            body += "4️⃣ **ถ่ายหลายมุม** (ถ้าเป็นไปได้)\n"
            body += "   • มุมใกล้ (Close-up)\n"
            body += "   • มุมกลาง (ใบทั้งใบ)\n"
            body += "   • มุมไกล (ต้นทั้งต้น)\n\n"
            body += "💡 **เคล็ดลับ**:\n"
            body += "• ถ่ายในเวลา 8-10 โมงเช้า หรือ 3-5 โมงเย็น\n"
            body += "• หลีกเลี่ยงแสงแดดจ้าจนเกินไป\n"
            body += "• ถ้ามีแมลง พยายามถ่ายให้เห็นแมลงด้วย\n\n"
            body += "📤 **พร้อมแล้ว?** ส่งรูปใหม่มาให้ฉันวิเคราะห์อีกครั้งนะคะ 😊"
            return header + body
        
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
        prompt = f"""คุณคือ AI ผู้ช่วยด้านโรคพืชและศัตรูพืชที่เป็นมิตร ชื่อ "ICP LADDA"

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
    cache_stats = await get_cache_stats()
    return {
        "status": "healthy",
        "services": {
            "gemini": "ok" if GEMINI_API_KEY else "not_configured",
            "supabase": "ok" if supabase_client else "not_configured",
            "line": "ok" if LINE_CHANNEL_ACCESS_TOKEN else "not_configured"
        },
        "cache": cache_stats,
        "rate_limiting": {
            "active_users": len(user_request_counts),
            "user_limit": f"{USER_RATE_LIMIT} requests per {USER_RATE_WINDOW}s"
        }
    }

@app.get("/cache/stats")
async def cache_stats():
    """Get detailed cache statistics"""
    stats = await get_cache_stats()
    return {
        "cache_stats": stats,
        "cache_config": {
            "ttl_seconds": CACHE_TTL,
            "max_size": MAX_CACHE_SIZE,
            "pending_context_ttl": PENDING_CONTEXT_TTL
        },
        "rate_limiting": {
            "active_users": len(user_request_counts),
            "user_limit": USER_RATE_LIMIT,
            "window_seconds": USER_RATE_WINDOW
        }
    }

@app.post("/cache/clear")
async def clear_cache():
    """Clear all caches (admin endpoint - should be protected in production)"""
    detection_cache.clear()
    product_cache.clear()
    knowledge_cache.clear()
    pending_image_contexts.clear()
    logger.info("All caches cleared manually")
    return {"status": "success", "message": "All caches cleared"}

@app.post("/webhook")
@limiter.limit("30/minute")  # Global rate limit: 30 requests per minute per IP
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
            
            # Get user ID for rate limiting
            user_id = event.get("source", {}).get("userId")
            
            # Check user-specific rate limit
            if user_id and not await check_user_rate_limit(user_id):
                rate_limit_message = (
                    "⚠️ คุณส่งคำขอมากเกินไปค่ะ\n\n"
                    f"กรุณารอ {USER_RATE_WINDOW} วินาที แล้วลองใหม่อีกครั้งนะคะ 🙏\n\n"
                    "เพื่อประสิทธิภาพที่ดี แนะนำให้:\n"
                    "• ส่งรูปที่ชัดเจน 1 รูปต่อครั้ง\n"
                    "• รอผลการวิเคราะห์ก่อนส่งรูปใหม่\n"
                    "• ถามคำถามที่เฉพาะเจาะจง"
                )
                await reply_line(reply_token, rate_limit_message)
                continue
            
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
                            # store pending context with timestamp
                            pending_image_contexts[user_id] = {
                                "image_bytes": image_bytes,
                                "reply_token": reply_token,
                                "timestamp": time.time()
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
                            
                            # ตรวจสอบว่าควรแนะนำสินค้าหรือไม่
                            disease_name_lower = disease_result.disease_name.lower()
                            
                            # ไม่แนะนำสินค้าในกรณีเหล่านี้
                            skip_product_recommendation = any(keyword in disease_name_lower for keyword in [
                                "ไม่พบปัญหา",
                                "ไม่พบโรค",
                                "ไม่สามารถวิเคราะห์",
                                "ไม่พบพืช",
                                "ภาพไม่ชัด",
                                "ไม่ชัดเจน",
                                "ไม่สามารถระบุ"
                            ])
                            
                            if skip_product_recommendation:
                                recommendations = []
                            else:
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
                        elif any(q in text_lower for q in ["?", "ยังไง", "อย่างไร", "ทำไม", "คือ", "หมายถึง", "ได้ไหม", "ใช้", "กำจัด", "ป้องกัน", "รักษา", "แนะนำ", "เพิ่ม", "แก้"]):
                            # This is a question - check if it's product-focused
                            logger.info(f"Processing Q&A: {text[:50]}...")
                            try:
                                # Extract keywords to determine query type
                                keywords = extract_keywords_from_question(text)
                                
                                # Check intent
                                intent = keywords.get("intent")
                                
                                # Check if this is a product-focused query
                                is_product_query = (
                                    keywords["is_product_query"] or 
                                    intent in ["increase_yield", "solve_problem", "general_care", "product_inquiry"] or
                                    any(word in text_lower for word in [
                                        "ผลิตภัณฑ์", "สินค้า", "ยา", "สาร", "แนะนำ", 
                                        "ใช้อะไร", "พ่นอะไร", "ฉีดอะไร", "ซื้อ",
                                        "icp", "ladda", "icpl", "ไอซีพี", "ลัดดา",
                                        "มีอะไรบ้าง", "มีไหม", "ขาย",
                                        "เพิ่มผลผลิต", "ผลผลิต", "แก้ปัญหา"
                                    ]) or
                                    (keywords["crops"] and any(word in text_lower for word in ["ใช้", "แนะนำ", "ดี", "เหมาะ", "เพิ่ม", "ผลผลิต"]))
                                )
                                
                                if is_product_query:
                                    # Check if it's intent-based query (increase yield, solve problem)
                                    if intent in ["increase_yield", "solve_problem", "general_care"]:
                                        logger.info(f"→ Intent-based query detected: {intent}")
                                        answer = await recommend_products_by_intent(text, keywords)
                                    else:
                                        # Use product-specific Q&A
                                        logger.info("→ Product-focused query detected")
                                        answer = await answer_product_question(text, keywords)
                                else:
                                    # Use general knowledge Q&A
                                    logger.info("→ General knowledge query")
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
