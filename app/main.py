# LINE Plant Disease Detection Bot v2.5.1
import logging
import asyncio
import json
import time
import os
import uvicorn
from fastapi import FastAPI, Request, HTTPException, Header, BackgroundTasks
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from pydantic import BaseModel

# Import config
from app.config import (
    LINE_CHANNEL_ACCESS_TOKEN,
    LINE_CHANNEL_SECRET,
    OPENAI_API_KEY,
    SUPABASE_URL,
    SUPABASE_KEY,
    CACHE_TTL,
    PENDING_CONTEXT_TTL,
    MAX_CACHE_SIZE,
    ADMIN_USERNAME,
    ADMIN_PASSWORD,
    SECRET_KEY,
    LIFF_ID,
    LIFF_URL
)

# Import services
from app.services.services import (
    openai_client,
    supabase_client,
    analytics_tracker,
    alert_manager
)
from app.services.welcome import (
    get_welcome_message,
    get_usage_guide,
    get_product_catalog_message,
    get_registration_required_message,
    get_help_menu
)
from app.utils.text_messages import (
    get_liff_welcome_text,
    get_registration_required_text,
    get_initial_questions_text,
    get_analyzing_text,
    get_growth_stage_question_text,
    get_other_plant_prompt_text,
    get_plant_type_retry_text,
    format_product_list_text
)
from app.services.liff_service import LiffRegistrationData, register_user_from_liff
from app.services.cache import (
    cleanup_expired_cache,
    get_cache_stats,
    save_pending_context,
    get_pending_context,
    delete_pending_context,
    clear_all_caches
)
from app.services.memory import (
    clear_memory,
    get_memory_stats,
    add_to_memory,
    save_recommended_products
)
from app.services.disease_detection import smart_detect_disease
from app.services.product_recommendation import retrieve_products_with_matching_score, get_search_query_for_disease
from app.services.response_generator import generate_final_response, generate_text_response, generate_diagnosis_with_stage_question
# Q&A Chat Service - Vector Search from products, diseases, knowledge tables
from app.services.chat import handle_natural_conversation
from app.services.context_handler import (
    handle_context_interrupt,
    handle_new_image_during_flow
)

# Import utils
from app.utils.line_helpers import (
    verify_line_signature,
    get_image_content_from_line,
    reply_line,
    push_line
)
from app.utils.question_templates import (
    get_initial_questions_message,
    get_analyzing_with_info_message,
    get_skip_analysis_message,
    should_skip_questions
)
from app.utils.rate_limiter import (
    check_user_rate_limit,
    cleanup_rate_limit_data
)

# Import models
from app.models import DiseaseDetectionResult

# Setup templates
templates = Jinja2Templates(directory="templates")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================#
# Lifespan Events
# ============================================================================#
from contextlib import asynccontextmanager

async def periodic_cleanup():
    """Periodic cleanup task"""
    while True:
        try:
            await asyncio.sleep(300)  # Run every 5 minutes
            logger.info("Running periodic cleanup...")
            await cleanup_expired_cache()
            await cleanup_rate_limit_data()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in cleanup task: {e}")
            await asyncio.sleep(60)

@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    # Startup
    logger.info("=" * 60)
    logger.info("Starting LINE Plant Pest & Disease Detection Bot (Refactored)")
    logger.info(f"OpenAI API: {'✓' if OPENAI_API_KEY else '✗'}")
    logger.info(f"Supabase: {'✓' if supabase_client else '✗'}")
    logger.info(f"LINE Bot: {'✓' if LINE_CHANNEL_ACCESS_TOKEN else '✗'}")
    logger.info(f"Analytics: {'✓' if analytics_tracker else '✗'}")
    logger.info("=" * 60)
    
    # Start background tasks only when explicitly enabled (not recommended on serverless)
    RUN_BACKGROUND_TASKS = os.getenv("RUN_BACKGROUND_TASKS", "0") == "1"
    cleanup_task = None
    if RUN_BACKGROUND_TASKS:
        logger.info("Starting background tasks...")
        cleanup_task = asyncio.create_task(periodic_cleanup())
    else:
        logger.info("RUN_BACKGROUND_TASKS not set or false — skipping background tasks (serverless mode)")
    
    yield
    
    # Shutdown
    logger.info("Shutting down gracefully...")
    if cleanup_task:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass

    # Clear all caches
    await clear_all_caches()
    logger.info("All caches cleared")

# Initialize FastAPI app
app = FastAPI(
    title="LINE Plant Disease Detection Bot",
    description="AI-powered plant disease detection with Multi-Agent System",
    version="2.0.0",
    lifespan=lifespan
)

# Initialize Rate Limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add Session Middleware
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

# Add CORS Middleware for LIFF
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow LIFF to call our API
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# NOTE: Static mount removed - using explicit routes instead (line 576+)
# Static mount was intercepting requests before routes could handle them
# liff_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "liff")
# if os.path.exists(liff_path):
#     app.mount("/liff", StaticFiles(directory=liff_path, html=True), name="liff")

# ============================================================================#
# Authentication
# ============================================================================#

class LoginRequest(BaseModel):
    username: str
    password: str

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(request: Request, login_data: LoginRequest):
    if login_data.username == ADMIN_USERNAME and login_data.password == ADMIN_PASSWORD:
        request.session["user"] = "admin"
        return {"status": "success", "message": "Login successful"}
    else:
        return JSONResponse(
            status_code=401,
            content={"status": "error", "message": "Invalid username or password"}
        )

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login")

async def get_current_admin(request: Request):
    user = request.session.get("user")
    if not user or user != "admin":
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user

# ============================================================================#
# API Endpoints
# ============================================================================#

@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "Plant Disease Detection Bot",
        "version": "2.0.0",
        "features": [
            "GPT-4o-mini Vision Analysis",
            "Vector Search Product Recommendation",
            "RAG Knowledge Base",
            "Context-Aware Chat",
            "Analytics Dashboard"
        ]
    }

@app.get("/health")
async def health_check():
    # Check if liff files exist for debugging
    liff_diseases_path = os.path.join(os.path.dirname(__file__), "..", "liff", "diseases.html")
    liff_dir = os.path.join(os.path.dirname(__file__), "..", "liff")
    liff_files = []
    if os.path.exists(liff_dir):
        liff_files = [f for f in os.listdir(liff_dir) if f.endswith('.html')]

    return {
        "status": "healthy",
        "version": "2.6.0-diseases",  # Version to track deployment
        "cache_stats": await get_cache_stats(),
        "services": {
            "openai": bool(openai_client),
            "supabase": bool(supabase_client)
        },
        "debug": {
            "liff_diseases_exists": os.path.exists(liff_diseases_path),
            "liff_dir_exists": os.path.exists(liff_dir),
            "liff_files": liff_files
        }
    }

@app.get("/cache/stats")
async def cache_stats_endpoint():
    return await get_cache_stats()

@app.post("/cache/clear")
async def clear_cache_endpoint(request: Request):
    # In production, add authentication here
    await clear_all_caches()
    return {"status": "success", "message": "All caches cleared"}

# ============================================================================#
# Dashboard Endpoints
# ============================================================================#

@app.get("/dashboard", response_class=HTMLResponse)
@limiter.limit("30/minute")  # Rate limit: 30 requests per minute
async def dashboard(request: Request):
    # Check authentication
    if not request.session.get("user"):
        return RedirectResponse(url="/login")
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/api/analytics/dashboard")
@limiter.limit("60/minute")  # Rate limit: 60 requests per minute
async def get_dashboard_data(request: Request, days: int = 1):
    # Check authentication
    if not request.session.get("user"):
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    if not analytics_tracker:
        raise HTTPException(status_code=503, detail="Analytics service not available")
    return await analytics_tracker.get_dashboard_stats(days=days)

@app.get("/api/analytics/health")
@limiter.limit("60/minute")  # Rate limit: 60 requests per minute
async def get_system_health(request: Request):
    if not analytics_tracker:
        raise HTTPException(status_code=503, detail="Analytics service not available")
    return await analytics_tracker.get_system_health()

@app.get("/api/analytics/alerts")
@limiter.limit("60/minute")  # Rate limit: 60 requests per minute
async def get_alerts(request: Request):
    if not alert_manager:
        raise HTTPException(status_code=503, detail="Alert service not available")
    return await alert_manager.get_active_alerts()

# ============================================================================#
# LIFF Endpoints
# ============================================================================#

@app.get("/liff-register")
async def liff_register_page():
    """Redirect to LIFF registration page"""
    liff_html_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "liff", "index.html")
    if os.path.exists(liff_html_path):
        return FileResponse(liff_html_path)
    raise HTTPException(status_code=404, detail="LIFF page not found")

@app.post("/api/liff/register")
async def liff_register(data: LiffRegistrationData):
    """
    Register user from LIFF frontend
    """
    try:
        result = await register_user_from_liff(data)
        return JSONResponse(content=result, status_code=200)
    except Exception as e:
        logger.error(f"LIFF registration error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/liff/status/{user_id}")
async def liff_registration_status(user_id: str):
    """
    Check if user has completed registration
    """
    from app.services.user_service import is_registration_completed
    registered = await is_registration_completed(user_id)
    return {"user_id": user_id, "registered": registered}

# ============================================================================#
# Disease Guide API (สำหรับ LIFF)
# ============================================================================#

@app.get("/api/diseases")
async def get_diseases(category: str = None, plant: str = None, limit: int = 50):
    """
    ดึงรายการโรคพืชทั้งหมด หรือ filter ตาม category/plant
    """
    try:
        if not supabase_client:
            raise HTTPException(status_code=500, detail="Database not available")

        query = supabase_client.table('diseases').select('*').eq('is_active', True)

        if category:
            query = query.eq('category', category)

        if plant:
            query = query.ilike('applicable_plants', f'%{plant}%')

        result = query.order('name_th').limit(limit).execute()

        return {
            "success": True,
            "count": len(result.data) if result.data else 0,
            "diseases": result.data or []
        }
    except Exception as e:
        logger.error(f"Get diseases error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/diseases/{disease_key}")
async def get_disease_detail(disease_key: str):
    """
    ดึงรายละเอียดโรคตาม disease_key
    """
    try:
        if not supabase_client:
            raise HTTPException(status_code=500, detail="Database not available")

        result = supabase_client.table('diseases').select('*').eq(
            'disease_key', disease_key
        ).eq('is_active', True).limit(1).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Disease not found")

        disease = result.data[0]

        # ดึงสินค้าที่เกี่ยวข้อง
        products = []
        if disease.get('pathogen'):
            prod_result = supabase_client.table('products').select(
                'id, product_name, product_category, target_pest, usage_rate, how_to_use, link_product'
            ).ilike('target_pest', f'%{disease.get("name_th", "")}%').limit(5).execute()

            if prod_result.data:
                products = prod_result.data

        return {
            "success": True,
            "disease": disease,
            "recommended_products": products
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get disease detail error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/diseases/category/{category}")
async def get_diseases_by_category(category: str):
    """
    ดึงโรคตามประเภท (fungal, bacterial, viral, insect, nutrient)
    """
    try:
        if not supabase_client:
            raise HTTPException(status_code=500, detail="Database not available")

        result = supabase_client.table('diseases').select('*').eq(
            'category', category
        ).eq('is_active', True).order('name_th').execute()

        return {
            "success": True,
            "category": category,
            "count": len(result.data) if result.data else 0,
            "diseases": result.data or []
        }
    except Exception as e:
        logger.error(f"Get diseases by category error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/products/for-disease/{disease_key}")
async def get_products_for_disease(disease_key: str):
    """
    ดึงสินค้าที่แนะนำสำหรับโรคนี้
    """
    try:
        if not supabase_client:
            raise HTTPException(status_code=500, detail="Database not available")

        # ดึงข้อมูลโรคก่อน
        disease_result = supabase_client.table('diseases').select('name_th, pathogen, category').eq(
            'disease_key', disease_key
        ).limit(1).execute()

        if not disease_result.data:
            raise HTTPException(status_code=404, detail="Disease not found")

        disease = disease_result.data[0]
        disease_name = disease.get('name_th', '')

        # ค้นหาสินค้าที่ตรงกับโรค
        products = []

        # Search by disease name
        prod_result = supabase_client.table('products').select('*').ilike(
            'target_pest', f'%{disease_name}%'
        ).limit(10).execute()

        if prod_result.data:
            products = prod_result.data

        return {
            "success": True,
            "disease_key": disease_key,
            "disease_name": disease_name,
            "count": len(products),
            "products": products
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get products for disease error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# LIFF Registration Page (หน้าลงทะเบียน)
@app.get("/liff")
async def liff_registration_page():
    """Serve LIFF Registration HTML"""
    liff_html_path = os.path.join(os.path.dirname(__file__), "..", "liff", "index.html")
    if os.path.exists(liff_html_path):
        return FileResponse(liff_html_path)
    raise HTTPException(status_code=404, detail="Registration page not found")

# LIFF Disease Guide Page
@app.get("/liff/diseases")
async def liff_diseases_page():
    """Serve LIFF Disease Guide HTML"""
    liff_html_path = os.path.join(os.path.dirname(__file__), "..", "liff", "diseases.html")
    if os.path.exists(liff_html_path):
        return FileResponse(liff_html_path)
    raise HTTPException(status_code=404, detail="Disease guide page not found")

# LIFF Disease Pages by Plant Type
@app.get("/liff/diseases-rice")
async def liff_diseases_rice_page():
    """Serve LIFF Rice Diseases HTML"""
    liff_html_path = os.path.join(os.path.dirname(__file__), "..", "liff", "diseases-rice.html")
    if os.path.exists(liff_html_path):
        return FileResponse(liff_html_path)
    raise HTTPException(status_code=404, detail="Rice diseases page not found")

@app.get("/liff/diseases-durian")
async def liff_diseases_durian_page():
    """Serve LIFF Durian Diseases HTML"""
    liff_html_path = os.path.join(os.path.dirname(__file__), "..", "liff", "diseases-durian.html")
    if os.path.exists(liff_html_path):
        return FileResponse(liff_html_path)
    raise HTTPException(status_code=404, detail="Durian diseases page not found")

@app.get("/liff/diseases-corn")
async def liff_diseases_corn_page():
    """Serve LIFF Corn Diseases HTML"""
    liff_html_path = os.path.join(os.path.dirname(__file__), "..", "liff", "diseases-corn.html")
    if os.path.exists(liff_html_path):
        return FileResponse(liff_html_path)
    raise HTTPException(status_code=404, detail="Corn diseases page not found")

@app.get("/liff/diseases-cassava")
async def liff_diseases_cassava_page():
    """Serve LIFF Cassava Diseases HTML"""
    liff_html_path = os.path.join(os.path.dirname(__file__), "..", "liff", "diseases-cassava.html")
    if os.path.exists(liff_html_path):
        return FileResponse(liff_html_path)
    raise HTTPException(status_code=404, detail="Cassava diseases page not found")

@app.get("/liff/diseases-sugarcane")
async def liff_diseases_sugarcane_page():
    """Serve LIFF Sugarcane Diseases HTML"""
    liff_html_path = os.path.join(os.path.dirname(__file__), "..", "liff", "diseases-sugarcane.html")
    if os.path.exists(liff_html_path):
        return FileResponse(liff_html_path)
    raise HTTPException(status_code=404, detail="Sugarcane diseases page not found")

@app.get("/liff/diseases/{disease_key}")
async def liff_disease_detail_page(disease_key: str):
    """Serve LIFF Disease Detail HTML"""
    liff_html_path = os.path.join(os.path.dirname(__file__), "..", "liff", "disease-detail.html")
    if os.path.exists(liff_html_path):
        return FileResponse(liff_html_path)
    raise HTTPException(status_code=404, detail="Disease detail page not found")

@app.get("/liff/assets/{filename}")
async def liff_assets(filename: str):
    """Serve LIFF static assets (images, icons)"""
    allowed_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp')
    if not filename.lower().endswith(allowed_extensions):
        raise HTTPException(status_code=400, detail="Invalid file type")
    file_path = os.path.join(os.path.dirname(__file__), "..", "liff", "assets", filename)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="Asset not found")

# ============================================================================#
# LINE Webhook
# ============================================================================#

@app.post("/webhook")
async def callback(request: Request, x_line_signature: str = Header(None)):
    """
    LINE Webhook endpoint - returns 200 immediately to prevent timeout.
    Actual processing happens in background via asyncio.create_task.
    """
    if not x_line_signature:
        raise HTTPException(status_code=400, detail="Missing X-Line-Signature header")

    body = await request.body()
    body_str = body.decode('utf-8')

    # Verify signature
    if not verify_line_signature(body, x_line_signature):
        logger.warning("Invalid signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Parse events
    try:
        events = json.loads(body_str).get("events", [])
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse webhook body: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # FIX: Return 200 IMMEDIATELY to prevent LINE timeout (499)
    # Process events in background - reply_token valid for ~30 seconds
    if events:
        asyncio.create_task(_process_webhook_events(events))

    return JSONResponse(content={"status": "success"})


async def _process_webhook_events(events: list):
    """Process webhook events in background task"""
    start_time = time.time()
    try:
        for event in events:
            event_type = event.get("type")
            reply_token = event.get("replyToken")
            user_id = event.get("source", {}).get("userId")
            
            if not reply_token or not user_id:
                continue
            
            # Check rate limit
            if not await check_user_rate_limit(user_id):
                await reply_line(reply_token, "ขออภัยค่ะ คุณส่งข้อความเร็วเกินไป กรุณารอสักครู่นะคะ ⏳")
                continue
            
            # Ensure user exists (auto-register new users)
            from app.services.user_service import ensure_user_exists, is_registration_completed, get_user
            await ensure_user_exists(user_id)
            
            # 1. Handle Follow Event (Welcome Message with LIFF)
            if event_type == "follow":
                logger.info(f"User {user_id} followed the bot")
                # Send LIFF welcome text
                welcome_text = get_liff_welcome_text(LIFF_URL)
                await reply_line(reply_token, welcome_text)
                continue

            # 2. Handle Image Message (Interactive Diagnosis)
            if event_type == "message" and event.get("message", {}).get("type") == "image":
                message_id = event["message"]["id"]
                logger.info(f"Received image from {user_id}")

                # Check if user has completed registration
                if not await is_registration_completed(user_id):
                    logger.info(f"User {user_id} not registered - blocking disease detection")
                    # Send LIFF registration text
                    reg_text = get_registration_required_text(LIFF_URL)
                    await reply_line(reply_token, reg_text)
                    continue

                try:
                    # === NEW: ตรวจว่ามี context เดิมอยู่ไหม (user ส่งรูปใหม่ระหว่าง flow) ===
                    existing_ctx = await get_pending_context(user_id)
                    # เช็คทุก state ที่ user อาจส่งรูปใหม่ระหว่าง flow (2-step flow)
                    active_states = [
                        "awaiting_plant_type",   # Step 1: รอเลือกชนิดพืช
                        "awaiting_other_plant",  # Step 1.5: รอพิมพ์ชื่อพืชอื่น
                        "awaiting_growth_stage"  # Step 2: รอเลือกระยะปลูก
                    ]
                    if existing_ctx and existing_ctx.get("state") in active_states:
                        # ถาม user ว่าจะใช้รูปใหม่หรือรูปเดิม
                        handled = await handle_new_image_during_flow(user_id, message_id, existing_ctx, reply_token)
                        if handled:
                            continue
                    
                    # FIX: Reply IMMEDIATELY to prevent reply token expiration (30 sec limit)
                    # Step 1: Ask for plant type (2-step flow)
                    questions_text = get_initial_questions_text()
                    await reply_line(reply_token, questions_text)
                    logger.info(f"Replied immediately to user {user_id} - asking plant type (Step 1/2)")

                    # FIX: Store only message_id (50 bytes) instead of image_bytes (5-7 MB)
                    # This reduces cache save time from 55 seconds to < 1 second
                    await save_pending_context(user_id, {
                        "message_id": message_id,
                        "timestamp": asyncio.get_event_loop().time(),
                        "state": "awaiting_plant_type",  # Step 1: รอเลือกชนิดพืช
                        "plant_type": None,
                        "position": None,
                        "symptom": None
                    })

                    # Add to memory
                    await add_to_memory(user_id, "user", "[ส่งรูปภาพพืช]")
                    await add_to_memory(user_id, "assistant", "[ถามชนิดพืช - ขั้นตอน 1/2]")

                    logger.info(f"Asked plant type for user {user_id}, waiting for selection")
                    
                except Exception as e:
                    logger.error(f"Error processing image: {e}")
                    await reply_line(reply_token, "ขออภัยค่ะ เกิดข้อผิดพลาดในการรับรูปภาพ โปรดลองใหม่อีกครั้ง 😢")

            # 3. Handle Text Message
            elif event_type == "message" and event.get("message", {}).get("type") == "text":
                text = event["message"]["text"].strip()
                logger.info(f"Received text from {user_id}: {text}")
                
                # Check if this is a response to image questions
                # Check pending context from DB
                ctx = await get_pending_context(user_id)
                
                # ============================================================================#
                # Quick Commands
                # ============================================================================#
                logger.info(f"🟢 Processing text: '{text}'")

                # 0. Check for usage guide request
                if text in ["วิธีใช้งาน", "วิธีใช้", "ช่วยเหลือ", "help"]:
                    logger.info(f"🟢 User {user_id} requested usage guide")
                    usage_guide = get_usage_guide()
                    await reply_line(reply_token, usage_guide)
                    continue

                # 0.1 Check for product catalog request
                if text in ["ดูผลิตภัณฑ์", "ผลิตภัณฑ์", "สินค้า", "products"]:
                    logger.info(f"🟢 User {user_id} requested product catalog")
                    catalog = get_product_catalog_message()
                    await reply_line(reply_token, catalog)
                    continue


                # 1. Check if user wants to register - send LIFF link
                if text in ["ลงทะเบียน", "register", "สมัคร"]:
                    logger.info(f"🟢 User {user_id} wants to register - sending LIFF link")
                    reg_text = get_registration_required_text(LIFF_URL)
                    await reply_line(reply_token, reg_text)
                    continue
                # ============================================================================#

                if ctx:
                    # === NEW: ตรวจจับ interrupt ก่อนประมวลผล ===
                    was_handled, new_ctx = await handle_context_interrupt(user_id, text, ctx, reply_token)
                    if was_handled:
                        # Context handler จัดการแล้ว ไปทำ event ถัดไป
                        continue
                    
                    # ถ้ามี new_ctx ให้ใช้แทน ctx เดิม
                    if new_ctx:
                        ctx = new_ctx
                    if ctx.get("state") == "awaiting_plant_type":
                        logger.info(f"Step 1/2: User {user_id} selecting plant type: {text}")

                        # Valid plant types
                        valid_plants = ["ข้าว", "ทุเรียน", "ข้าวโพด", "มันสำปะหลัง", "อ้อย",]

                        if text == "อื่นๆ":
                            # User wants to type custom plant name
                            await reply_line(reply_token, get_other_plant_prompt_text())

                            # Update state to await custom plant name
                            await save_pending_context(user_id, {
                                **ctx,
                                "state": "awaiting_other_plant"
                            })
                            logger.info(f"Asking user {user_id} to type custom plant name")

                        elif text in valid_plants:
                            # Valid plant selected - go directly to Step 2 (growth stage)
                            await reply_line(reply_token, get_growth_stage_question_text(text))

                            # Update context with plant type - skip position/symptom
                            await save_pending_context(user_id, {
                                **ctx,
                                "state": "awaiting_growth_stage",
                                "plant_type": text
                            })
                            logger.info(f"Plant type '{text}' selected, asking growth stage (Step 2/2)")

                        else:
                            # Invalid response - ask again
                            await reply_line(reply_token, get_plant_type_retry_text())
                            logger.info(f"Invalid plant type response: {text}, asking again")

                    # ==========================================================================
                    # STEP 1.5: Awaiting Custom Plant Name (when "อื่นๆ" selected)
                    # ==========================================================================
                    elif ctx.get("state") == "awaiting_other_plant":
                        logger.info(f"Step 1.5: User {user_id} typing custom plant: {text}")

                        # Accept any text as plant name, go directly to Step 2 (growth stage)
                        await reply_line(reply_token, get_growth_stage_question_text(text))

                        # Update context with custom plant type - skip position/symptom
                        await save_pending_context(user_id, {
                            **ctx,
                            "state": "awaiting_growth_stage",
                            "plant_type": text
                        })
                        logger.info(f"Custom plant '{text}' accepted, asking growth stage (Step 2/2)")

                    elif ctx.get("state") == "awaiting_growth_stage":
                        # Step 2/2: User selected growth stage - analyze image and recommend products
                        logger.info(f"Step 2/2: User {user_id} selected growth stage: {text}")

                        plant_type = ctx.get("plant_type", "")
                        growth_stage = text

                        # Build extra_user_info for AI analysis
                        extra_user_info = f"พืช: {plant_type}" if plant_type else None

                        # 1. Download image
                        try:
                            message_id_from_ctx = ctx["message_id"]
                            logger.info(f"Downloading image for analysis: {message_id_from_ctx}")
                            image_bytes = await get_image_content_from_line(message_id_from_ctx)
                        except Exception as e:
                            logger.error(f"Failed to download image: {e}")
                            await reply_line(reply_token, "ขออภัยค่ะ ไม่สามารถดาวน์โหลดรูปภาพได้ กรุณาส่งรูปใหม่อีกครั้ง 😢")
                            await delete_pending_context(user_id)
                            continue

                        try:
                            # Send analyzing message
                            analyzing_text = get_analyzing_text(with_info=bool(extra_user_info))
                            await reply_line(reply_token, analyzing_text)

                            # 2. Run disease detection (no position/symptom)
                            detection_result = await smart_detect_disease(image_bytes, extra_user_info=extra_user_info)

                            # Override plant_type if user specified
                            if plant_type and not detection_result.plant_type:
                                detection_result.plant_type = plant_type

                            # Check if we should recommend products
                            skip_keywords = [
                                "ไม่พบ", "ไม่ทราบ", "ปกติ", "ไม่ชัดเจน",
                                "ขาดธาตุ", "ขาดไนโตรเจน", "ขาดฟอสฟอรัส", "ขาดโพแทสเซียม",
                                "ขาดแมกนีเซียม", "ขาดเหล็ก", "ขาดแคลเซียม", "ขาดโบรอน",
                                "Deficiency", "deficiency",
                                "ใบเหลือง", "ใบซีด",
                                "สุขภาพดี", "healthy", "Healthy",
                                "Technical Error", "ไม่สามารถระบุได้", "Error", "error",
                                "ไม่ใช่ภาพ", "ไม่ใช่รูป", "Not Found"
                            ]
                            should_recommend = True
                            disease_name_lower = detection_result.disease_name.lower()

                            try:
                                conf_value = float(detection_result.confidence) if detection_result.confidence is not None else None
                                if conf_value is not None and conf_value < 10:
                                    should_recommend = False
                                    logger.info(f"⏭️ Skipping product recommendation - confidence too low: {conf_value}%")
                            except (ValueError, TypeError):
                                pass

                            for kw in skip_keywords:
                                if kw.lower() in disease_name_lower:
                                    _, pest_name, _ = get_search_query_for_disease(detection_result.disease_name)
                                    if pest_name:
                                        logger.info(f"🐛 โรคมีพาหะ '{pest_name}' → ยังแนะนำยาฆ่าแมลงได้")
                                    else:
                                        should_recommend = False
                                        logger.info(f"⏭️ Skipping product recommendation - matched skip keyword: {kw}")
                                    break

                            # Extract pest_type from raw_analysis
                            pest_type = "ศัตรูพืช"
                            if detection_result.raw_analysis:
                                parts = detection_result.raw_analysis.split(":")
                                if len(parts) > 0:
                                    pest_type = parts[0].strip()

                            # Track analytics
                            if analytics_tracker:
                                await analytics_tracker.track_image_analysis(
                                    user_id=user_id,
                                    disease_name=detection_result.disease_name,
                                    pest_type=pest_type,
                                    confidence=detection_result.confidence,
                                    response_time_ms=0.0
                                )

                            if should_recommend:
                                # 3. Get product recommendations with matching score
                                recommendations = await retrieve_products_with_matching_score(
                                    detection_result=detection_result,
                                    plant_type=plant_type,
                                    growth_stage=growth_stage
                                )

                                # Track product recommendations
                                if analytics_tracker and recommendations:
                                    product_names = [p.product_name for p in recommendations]
                                    await analytics_tracker.track_product_recommendation(
                                        user_id=user_id,
                                        disease_name=detection_result.disease_name,
                                        products=product_names
                                    )

                                # 4. Send combined results (diagnosis + products)
                                # First send diagnosis
                                text_messages = await generate_text_response(detection_result, [], extra_user_info=extra_user_info)
                                await push_line(user_id, text_messages)

                                # Then send product recommendations if any
                                if recommendations:
                                    product_list = []
                                    for p in recommendations[:5]:
                                        product_list.append({
                                            "product_name": (p.product_name or "ไม่ระบุ")[:100],
                                            "active_ingredient": (p.active_ingredient or "-")[:100],
                                            "target_pest": (p.target_pest or "-")[:200],
                                            "applicable_crops": (p.applicable_crops or "-")[:150],
                                            "usage_period": (p.usage_period or "-")[:100],
                                            "how_to_use": (p.how_to_use or "-")[:200],
                                            "usage_rate": (p.usage_rate or "-")[:100],
                                            "link_product": (p.link_product or "")[:500] if p.link_product and str(p.link_product).startswith("http") else "",
                                            "image_url": (p.image_url or "") if hasattr(p, 'image_url') else "",
                                            "similarity": p.score if hasattr(p, 'score') else 0.8
                                        })

                                    product_text = format_product_list_text(product_list)

                                    # Send header text + product list
                                    header_text = f"💊 ผลิตภัณฑ์แนะนำสำหรับ {plant_type} {growth_stage}:"

                                    await push_line(user_id, [
                                        header_text,
                                        product_text
                                    ])

                                    # Save recommended products to memory
                                    await save_recommended_products(
                                        user_id,
                                        recommendations,
                                        disease_name=detection_result.disease_name
                                    )
                                else:
                                    await push_line(user_id, "ขออภัยค่ะ ไม่พบผลิตภัณฑ์ที่เหมาะสมสำหรับระยะนี้ 😢")

                                # Add to memory
                                await add_to_memory(user_id, "user", f"[พืช] {plant_type} [ระยะ] {growth_stage}")
                                await add_to_memory(user_id, "assistant", f"[ผลวิเคราะห์] {detection_result.disease_name} [แนะนำ] {len(recommendations)} รายการ")

                            else:
                                # ไม่ต้องแนะนำสินค้า (ขาดธาตุ, ไม่พบปัญหา, สุขภาพดี)
                                text_messages = await generate_text_response(detection_result, [], extra_user_info=extra_user_info)
                                await push_line(user_id, text_messages)

                                # Add to memory
                                await add_to_memory(user_id, "user", f"[พืช] {plant_type} [ระยะ] {growth_stage}")
                                await add_to_memory(user_id, "assistant", f"[ผลวิเคราะห์] {detection_result.disease_name}")

                            # Clear context
                            await delete_pending_context(user_id)

                        except Exception as e:
                            logger.error(f"Error processing growth stage response: {e}", exc_info=True)
                            await reply_line(reply_token, "ขออภัยค่ะ เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้ง 😢")
                            await delete_pending_context(user_id)

                    else:
                        # Context exists but unknown state
                        logger.warning(f"Found context for {user_id} but state is unknown: {ctx.get('state')}")
                        # Clear unknown context and fall through to normal conversation
                        await delete_pending_context(user_id)

                        # Handle as normal conversation
                        if not await is_registration_completed(user_id):
                            reg_text = get_registration_required_text(LIFF_URL)
                            await reply_line(reply_token, reg_text)
                        else:
                            # Q&A Chat - Vector Search from products, diseases, knowledge
                            answer = await handle_natural_conversation(user_id, text)
                            await reply_line(reply_token, answer)

                else:
                    # Normal text message handling
                    if text.lower() in ["ล้างความจำ", "reset", "clear"]:
                        await clear_memory(user_id)
                        await reply_line(reply_token, "ล้างความจำเรียบร้อยค่ะ เริ่มต้นใหม่ได้เลย! ✨")

                    elif text.lower() in ["ช่วยเหลือ", "help", "เมนู"]:
                        # Use Flex Message for help menu
                        help_flex = get_help_menu()
                        await reply_line(reply_token, help_flex)

                    else:
                        # Check registration first
                        if not await is_registration_completed(user_id):
                            logger.info(f"User {user_id} not registered")
                            reg_text = get_registration_required_text(LIFF_URL)
                            await reply_line(reply_token, reg_text)
                        else:
                            # Q&A Chat - Vector Search from products, diseases, knowledge
                            answer = await handle_natural_conversation(user_id, text)
                            await reply_line(reply_token, answer)

            # 4. Handle Sticker (Just for fun)
            elif event_type == "message" and event.get("message", {}).get("type") == "sticker":
                # Reply with a sticker
                await reply_line(reply_token, "ขอบคุณค่ะ! 😊", with_sticker=True)

        logger.info(f"✅ Background webhook processing completed in {time.time() - start_time:.2f}s")

    except Exception as e:
        logger.error(f"Background webhook error: {e}", exc_info=True)

if __name__ == "__main__":
    # อ่าน Port จาก Environment Variable ที่ Cloud Platform (Fly.io/Vercel) ส่งมา 
    # และใช้ 8080 เป็นค่า Default (ตามที่ Fly.io แนะนำ)
    port = int(os.environ.get("PORT", 8080))
    
    # รัน Uvicorn ด้วยค่า Port ที่อ่านได้
    uvicorn.run('app.main:app', host='0.0.0.0', port=port, reload=True)