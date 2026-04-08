import os
import logging as _logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

_cfg_logger = _logging.getLogger(__name__)

# ============================================================================#
# ENVIRONMENT / SERVICES
# ============================================================================#
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")  # For Gemini 3.0 flash (disease detection)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Facebook Messenger
FB_PAGE_ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN", "")
FB_VERIFY_TOKEN = os.getenv("FB_VERIFY_TOKEN", "")
FB_APP_SECRET = os.getenv("FB_APP_SECRET", "")

# Admin Authentication
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "ladda")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
SECRET_KEY = os.getenv("SECRET_KEY", "")

if not ADMIN_PASSWORD or len(ADMIN_PASSWORD) < 8:
    _cfg_logger.critical("ADMIN_PASSWORD not set or too short (min 8 chars)! Set env var.")
if not SECRET_KEY or len(SECRET_KEY) < 16:
    _cfg_logger.critical("SECRET_KEY not set or too short (min 16 chars)! Set env var.")

# Cache configuration
CACHE_TTL = 3600  # 1 hour
PENDING_CONTEXT_TTL = 1800  # 30 minutes (เพิ่มจาก 5 นาที เพื่อให้ user มีเวลาตอบ)
CONVERSATION_STATE_TTL = int(os.getenv("CONVERSATION_STATE_TTL", "1800"))  # 30 min — conversation state expiry
MAX_CACHE_SIZE = 5000  # Maximum cache entries (เพิ่มจาก 1000 เป็น 5000)

# Semantic Cache — in-memory cosine similarity cache
SEMANTIC_CACHE_ENABLED = os.getenv("SEMANTIC_CACHE_ENABLED", "1") == "1"
SEMANTIC_CACHE_THRESHOLD = float(os.getenv("SEMANTIC_CACHE_THRESHOLD", "0.90"))  # 0.93→0.90 เพิ่ม hit rate ~2x (ยังปลอดภัย: plant match ป้องกัน false hit)
SEMANTIC_CACHE_TTL = int(os.getenv("SEMANTIC_CACHE_TTL", "7200"))  # 30min→2hr (ข้อมูลสินค้าไม่เปลี่ยนบ่อย)
SEMANTIC_CACHE_MAX_ENTRIES = int(os.getenv("SEMANTIC_CACHE_MAX_ENTRIES", "500"))  # 200→500 entries

# Rate limiting per user
USER_RATE_LIMIT = 20  # requests per minute
USER_RATE_WINDOW = 60  # seconds

# Concurrency control — limit background tasks to prevent memory exhaustion
MAX_CONCURRENT_TASKS = int(os.getenv("MAX_CONCURRENT_TASKS", "100"))
MAX_QUEUE_DEPTH = int(os.getenv("MAX_QUEUE_DEPTH", "50"))

# Image diagnosis feature toggle
# Set to "1" to enable image-based disease diagnosis, "0" to disable (default)
ENABLE_IMAGE_DIAGNOSIS = os.getenv("ENABLE_IMAGE_DIAGNOSIS", "0") == "1"

# Image analysis throttling
IMAGE_COOLDOWN = int(os.getenv("IMAGE_COOLDOWN", "10"))  # seconds between image requests per user
MAX_CONCURRENT_ANALYSIS = int(os.getenv("MAX_CONCURRENT_ANALYSIS", "10"))  # max concurrent image analyses

# Redis configuration (for scale-out support)
# Set REDIS_URL or UPSTASH_REDIS_REST_URL + UPSTASH_REDIS_REST_TOKEN
REDIS_URL = os.getenv("REDIS_URL")
UPSTASH_REDIS_REST_URL = os.getenv("UPSTASH_REDIS_REST_URL")
UPSTASH_REDIS_REST_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN")
USE_REDIS_CACHE = bool(REDIS_URL or UPSTASH_REDIS_REST_URL)

# Memory configuration
MAX_MEMORY_MESSAGES = 50  # Keep last 50 messages for context (ปรับจาก 100 เพื่อ performance)
MEMORY_CONTEXT_WINDOW = 10  # Use last 10 messages for context
MEMORY_CONTENT_PREVIEW = 800  # Characters to show in context preview (เพิ่มจาก 300 เพื่อให้ชื่อสินค้าไม่ถูกตัด)
MEMORY_SESSION_TIMEOUT_HOURS = int(os.getenv("MEMORY_SESSION_TIMEOUT_HOURS", "6"))  # ถ้า user หายไปเกิน 6 ชม. → ไม่ส่ง context เก่าให้ LLM
MEMORY_TTL_DAYS = int(os.getenv("MEMORY_TTL_DAYS", "7"))  # ลบ memory เก่ากว่า 7 วัน

# ============================================================================#
# PRODUCT TABLE — switch between products2 (backup) and products3 (new Excel)
# ============================================================================#
PRODUCT_TABLE = os.getenv("PRODUCT_TABLE", "products3")
PRODUCT_RPC = os.getenv("PRODUCT_RPC", "hybrid_search_products3")

# ============================================================================#
# MEMORY TABLE — แยก conversation memory ระหว่าง project
# ============================================================================#
MEMORY_TABLE = os.getenv("MEMORY_TABLE", "memory_chatladda")

# ============================================================================#
# AGENTIC RAG CONFIGURATION
# ============================================================================#
# Set to "1" to enable Agentic RAG pipeline for Q&A
# Set to "0" to disable (legacy functions have been removed)
USE_AGENTIC_RAG = os.getenv("USE_AGENTIC_RAG", "1") == "1"

# ============================================================================#
# LLM MODEL NAMES (centralized — change once, applies everywhere)
# ============================================================================#
LLM_MODEL_GENERAL_CHAT = os.getenv("LLM_MODEL_GENERAL_CHAT", "gpt-4o")
LLM_MODEL_QUERY_UNDERSTANDING = os.getenv("LLM_MODEL_QUERY_UNDERSTANDING", "gpt-4o-mini")
LLM_MODEL_RERANKING = os.getenv("LLM_MODEL_RERANKING", "gpt-4o-mini")
LLM_MODEL_RESPONSE_GEN = os.getenv("LLM_MODEL_RESPONSE_GEN", "gpt-4o")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

AGENTIC_RAG_CONFIG = {
    # Vector search threshold (lowered to 0.25 for better recall)
    "VECTOR_THRESHOLD": float(os.getenv("AGENTIC_VECTOR_THRESHOLD", "0.25")),

    # Minimum rerank score to include in results
    "RERANK_THRESHOLD": float(os.getenv("AGENTIC_RERANK_THRESHOLD", "0.50")),

    # Minimum number of relevant documents to return
    "MIN_RELEVANT_DOCS": int(os.getenv("AGENTIC_MIN_DOCS", "3")),

    # Maximum citations to include in response
    "MAX_CITATIONS": int(os.getenv("AGENTIC_MAX_CITATIONS", "3")),
}

# ============================================================================#
# LLM PARAMETERS (temperature / max_tokens per component)
# ============================================================================#
# --- RAG Pipeline (Agentic RAG) ---
LLM_TEMP_QUERY_UNDERSTANDING = 0.1   # Agent 1: วิเคราะห์ intent + extract entities (query_understanding_agent.py)
LLM_TOKENS_QUERY_UNDERSTANDING = 500
LLM_TEMP_RERANKING = 0               # Agent 2: re-rank ลำดับสินค้า (retrieval_agent.py, reranker.py)
LLM_TOKENS_RERANKING = 100
LLM_TEMP_RESPONSE_GEN = 0.2          # Agent 3: สร้างคำตอบจาก RAG pipeline (response_generator_agent.py)
LLM_TOKENS_RESPONSE_GEN = 600
# --- Handler (chat/handler.py) ---
LLM_TEMP_HANDLER_RAG = 0.1           # ตอบคำถามสินค้าจาก vector search (Q&A)
LLM_TOKENS_HANDLER_RAG = 600
LLM_TEMP_GENERAL_CHAT = 0.3          # General chat คุยทั่วไป (ไม่เกี่ยวเกษตร)
LLM_TOKENS_GENERAL_CHAT = 250

# --- Product Recommendation (product/recommendation.py) ---
LLM_TEMP_PRODUCT_FORMAT = 0.1        # Format คำตอบแนะนำสินค้า
LLM_TOKENS_PRODUCT_FORMAT = 800
