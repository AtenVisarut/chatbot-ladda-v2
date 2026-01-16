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

# Agro-Risk API Configuration
AGRO_RISK_API_URL = os.getenv("AGRO_RISK_API_URL", "https://thai-water.vercel.app")

# Cache configuration
CACHE_TTL = 3600  # 1 hour
PENDING_CONTEXT_TTL = 1800  # 30 minutes (เพิ่มจาก 5 นาที เพื่อให้ user มีเวลาตอบ)
MAX_CACHE_SIZE = 1000  # Maximum cache entries

# Rate limiting per user
USER_RATE_LIMIT = 10  # requests per minute
USER_RATE_WINDOW = 60  # seconds

# Memory configuration
MAX_MEMORY_MESSAGES = 40  # Keep last 40 messages for context
MEMORY_CONTEXT_WINDOW = 20  # Use last 20 messages for context (จำบทสนทนา 20 ข้อความ)

# RAG-based Disease Detection
# Set to "1" to use RAG + Vector Search (faster, cheaper)
# Set to "0" to use original hardcoded database (default for rollback)
USE_RAG_DETECTION = os.getenv("USE_RAG_DETECTION", "0") == "1"
