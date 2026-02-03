import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ============================================================================#
# ENVIRONMENT / SERVICES
# ============================================================================#
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")  # For Gemini 3.0 flash (disease detection)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Admin Authentication
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "ladda")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "ladda123")
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")

# LIFF Configuration
LIFF_ID = os.getenv("LIFF_ID", "2008723334-Zz1OoaPy")
LIFF_URL = f"https://liff.line.me/{LIFF_ID}"

# LIFF Disease Guide URL (หน้าคู่มือโรคพืช)
LIFF_DISEASES_URL = os.getenv("LIFF_DISEASES_URL", "https://chatbot-ladda-production.up.railway.app/liff/diseases")

# Cache configuration
CACHE_TTL = 3600  # 1 hour
PENDING_CONTEXT_TTL = 1800  # 30 minutes (เพิ่มจาก 5 นาที เพื่อให้ user มีเวลาตอบ)
MAX_CACHE_SIZE = 5000  # Maximum cache entries (เพิ่มจาก 1000 เป็น 5000)

# Rate limiting per user
USER_RATE_LIMIT = 20  # requests per minute
USER_RATE_WINDOW = 60  # seconds

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
MEMORY_CONTEXT_WINDOW = 30  # Use last 30 messages for context
MEMORY_CONTENT_PREVIEW = 300  # Characters to show in context preview (ลดจาก 400)

# RAG-based Disease Detection
# Set to "1" to use RAG + Vector Search (faster, cheaper)
# Set to "0" to use original hardcoded database (default for rollback)
USE_RAG_DETECTION = os.getenv("USE_RAG_DETECTION", "0") == "1"

# ============================================================================#
# AGENTIC RAG CONFIGURATION
# ============================================================================#
# Set to "1" to enable Agentic RAG pipeline for Q&A
# Set to "0" to use legacy answer_qa_with_vector_search
USE_AGENTIC_RAG = os.getenv("USE_AGENTIC_RAG", "1") == "1"

AGENTIC_RAG_CONFIG = {
    # Vector search threshold (increased from 0.20 for better precision)
    "VECTOR_THRESHOLD": float(os.getenv("AGENTIC_VECTOR_THRESHOLD", "0.35")),

    # Minimum rerank score to include in results
    "RERANK_THRESHOLD": float(os.getenv("AGENTIC_RERANK_THRESHOLD", "0.50")),

    # Minimum number of relevant documents to return
    "MIN_RELEVANT_DOCS": int(os.getenv("AGENTIC_MIN_DOCS", "3")),

    # Enable grounding check (hallucination prevention)
    "ENABLE_GROUNDING": os.getenv("AGENTIC_ENABLE_GROUNDING", "1") == "1",

    # Maximum citations to include in response
    "MAX_CITATIONS": int(os.getenv("AGENTIC_MAX_CITATIONS", "3")),
}
