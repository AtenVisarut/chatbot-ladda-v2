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
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Admin Authentication
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "ladda")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "ladda123")
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")

# Cache configuration
CACHE_TTL = 3600  # 1 hour
PENDING_CONTEXT_TTL = 300  # 5 minutes
MAX_CACHE_SIZE = 1000  # Maximum cache entries

# Rate limiting per user
USER_RATE_LIMIT = 10  # requests per minute
USER_RATE_WINDOW = 60  # seconds

# Memory configuration
MAX_MEMORY_MESSAGES = 20 # Keep last 20messages for context
MEMORY_CONTEXT_WINDOW = 10 # Use last 10messages for context
