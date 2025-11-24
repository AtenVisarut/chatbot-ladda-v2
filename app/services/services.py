import logging
from supabase import create_client, Client

from sentence_transformers import SentenceTransformer
from app.config import OPENAI_API_KEY, SUPABASE_URL, SUPABASE_KEY
from app.analytics import AnalyticsTracker, AlertManager

logger = logging.getLogger(__name__)

# Initialize OpenAI
openai_client = None
if OPENAI_API_KEY:
    from openai import AsyncOpenAI
    openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    logger.info("OpenAI initialized successfully")

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

# Initialize Analytics
analytics_tracker = None
alert_manager = None
if supabase_client:
    try:
        analytics_tracker = AnalyticsTracker(supabase_client)
        alert_manager = AlertManager(supabase_client)
        logger.info("Analytics initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize analytics: {e}")
