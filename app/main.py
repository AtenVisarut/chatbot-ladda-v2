# LINE Plant Disease Detection Bot v2.5.1
import logging
import asyncio
import json
import time
import os
import uvicorn
from fastapi import FastAPI, Request, HTTPException, Header
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
    e5_model,
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
from app.utils.flex_messages import (
    create_chat_response_flex,
    create_liff_registration_flex,
    create_liff_welcome_flex,
    create_initial_questions_flex,
    create_analyzing_flex,
    create_product_carousel_flex
)
from app.services.liff_service import LiffRegistrationData, register_user_from_liff
from app.services.cache import (
    cleanup_expired_cache,
    get_cache_stats,
    set_to_cache,
    get_image_hash,
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
from app.services.disease_detection import detect_disease
from app.services.product_recommendation import retrieve_product_recommendation, retrieve_products_with_matching_score
from app.services.response_generator import generate_final_response, generate_flex_response, generate_diagnosis_with_stage_question
from app.services.chat import handle_natural_conversation
from app.services.agro_risk import (
    check_weather,
    analyze_crop_risk,
    create_weather_error_flex,
    create_crop_selection_flex
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
    should_skip_questions,
    get_welcome_message
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

# Mount LIFF static files
liff_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "liff")
if os.path.exists(liff_path):
    app.mount("/liff", StaticFiles(directory=liff_path, html=True), name="liff")

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
    return {
        "status": "healthy",
        "cache_stats": await get_cache_stats(),
        "services": {
            "openai": bool(openai_client),
            "supabase": bool(supabase_client),
            "e5_model": bool(e5_model)
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
# LINE Webhook
# ============================================================================#

@app.post("/webhook")
async def callback(request: Request, x_line_signature: str = Header(None)):
    start_time = time.time()
    if not x_line_signature:
        raise HTTPException(status_code=400, detail="Missing X-Line-Signature header")
    
    body = await request.body()
    body_str = body.decode('utf-8')
    
    # Verify signature
    if not verify_line_signature(body, x_line_signature):
        logger.warning("Invalid signature")
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    try:
        events = json.loads(body_str).get("events", [])
        
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
            from app.services.user_service import ensure_user_exists, is_registration_completed
            await ensure_user_exists(user_id)
            
            # 1. Handle Follow Event (Welcome Message with LIFF)
            if event_type == "follow":
                logger.info(f"User {user_id} followed the bot")
                # Send LIFF welcome message
                welcome_flex = create_liff_welcome_flex(LIFF_URL)
                await reply_line(reply_token, welcome_flex)
                continue

            # 2. Handle Image Message (Interactive Diagnosis)
            if event_type == "message" and event.get("message", {}).get("type") == "image":
                message_id = event["message"]["id"]
                logger.info(f"Received image from {user_id}")

                # Check if user has completed registration
                if not await is_registration_completed(user_id):
                    logger.info(f"User {user_id} not registered - blocking disease detection")
                    # Send LIFF registration message
                    reg_flex = create_liff_registration_flex(LIFF_URL)
                    await reply_line(reply_token, reg_flex)
                    continue

                try:
                    # Get image content
                    image_bytes = await get_image_content_from_line(message_id)
                    
                    # Store image context and set state to awaiting additional info
                    await save_pending_context(user_id, {
                        "image_bytes": image_bytes,
                        "timestamp": asyncio.get_event_loop().time(),
                        "state": "awaiting_info",
                        "additional_info": None
                    })
                    
                    # Ask for additional information instead of immediate analysis
                    questions_flex = create_initial_questions_flex()
                    await reply_line(reply_token, questions_flex)

                    # Add to memory
                    await add_to_memory(user_id, "user", "[ส่งรูปภาพพืช]")
                    await add_to_memory(user_id, "assistant", "[ถามข้อมูลเพิ่มเติมสำหรับวิเคราะห์]")
                    
                    logger.info(f"Asked questions for user {user_id}, waiting for additional info")
                    
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
                    return JSONResponse(content={"status": "success"})

                # 0.1 Check for product catalog request
                if text in ["ดูผลิตภัณฑ์", "ผลิตภัณฑ์", "สินค้า", "products"]:
                    logger.info(f"🟢 User {user_id} requested product catalog")
                    catalog = get_product_catalog_message()
                    await reply_line(reply_token, catalog)
                    return JSONResponse(content={"status": "success"})

                # 0.2 Check for weather request - ส่ง Text พร้อม Quick Reply ขอ location
                if text in ["ดูสภาพอากาศ", "สภาพอากาศ", "อากาศ", "weather", "🌤️"]:
                    logger.info(f"🟢 User {user_id} requested weather")
                    # ใช้ Quick Reply เพราะ location action ใช้ใน Flex button ไม่ได้
                    weather_message = {
                        "type": "text",
                        "text": "🌤️ ดูสภาพอากาศในพื้นที่\n\nกดปุ่ม 📍 ด้านล่างเพื่อแชร์ตำแหน่งของคุณ\n\nข้อมูลที่จะได้รับ:\n• อุณหภูมิและความชื้น\n• โอกาสฝนตก\n• ความเสี่ยงน้ำท่วม/ภัยแล้ง\n• คำแนะนำสำหรับเกษตรกร",
                        "quickReply": {
                            "items": [
                                {
                                    "type": "action",
                                    "action": {
                                        "type": "location",
                                        "label": "📍 แชร์ตำแหน่ง"
                                    }
                                }
                            ]
                        }
                    }
                    await reply_line(reply_token, weather_message)
                    return JSONResponse(content={"status": "success"})

                # 1. Check if user wants to register - send LIFF link
                if text in ["ลงทะเบียน", "register", "สมัคร"]:
                    logger.info(f"🟢 User {user_id} wants to register - sending LIFF link")
                    reg_flex = create_liff_registration_flex(LIFF_URL)
                    await reply_line(reply_token, reg_flex)
                    return JSONResponse(content={"status": "success"})
                # ============================================================================#

                if ctx:
                    # Check if we're waiting for additional info
                    if ctx.get("state") == "awaiting_info":
                        logger.info(f"Processing user response to image questions for {user_id}")
                        
                        # Get the image bytes
                        image_bytes = ctx["image_bytes"]
                        
                        # Check if user wants to skip questions
                        if should_skip_questions(text):
                            # Analyze without additional info
                            try:
                                skip_flex = create_analyzing_flex(with_info=False)
                                await reply_line(reply_token, skip_flex)
                                
                                detection_result = await detect_disease(image_bytes)
                                
                                # Check if we should recommend products
                                # Skip if: Not found, Unknown, Normal, Unclear, Nutrient deficiency
                                skip_keywords = [
                                    "ไม่พบ", "ไม่ทราบ", "ปกติ", "ไม่ชัดเจน",
                                    "ขาดธาตุ", "ขาดไนโตรเจน", "ขาดฟอสฟอรัส", "ขาดโพแทสเซียม",
                                    "ขาดแมกนีเซียม", "ขาดเหล็ก", "ขาดแคลเซียม", "ขาดโบรอน",
                                    "Deficiency", "deficiency",
                                    "ใบเหลือง", "ใบซีด", "ใบด่าง",
                                    "สุขภาพดี", "healthy", "Healthy"
                                ]
                                should_recommend = True
                                disease_name_lower = detection_result.disease_name.lower()
                                for kw in skip_keywords:
                                    if kw.lower() in disease_name_lower:
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
                                    # ถามระยะปลูกก่อนแนะนำสินค้า
                                    logger.info(f"🌱 Asking for growth stage before product recommendation")

                                    # Save detection result to context for later use
                                    await save_pending_context(user_id, {
                                        "state": "awaiting_growth_stage",
                                        "detection_result": detection_result.dict(),
                                        "plant_type": detection_result.plant_type or "",
                                    })

                                    # Generate diagnosis with growth stage question
                                    flex_messages = await generate_diagnosis_with_stage_question(detection_result)

                                    # Send Flex Messages
                                    await push_line(user_id, flex_messages)

                                    # Add to memory
                                    await add_to_memory(user_id, "user", f"[ข้าม] {text}")
                                    await add_to_memory(user_id, "assistant", f"[ผลวิเคราะห์] {detection_result.disease_name} - รอเลือกระยะปลูก")

                                else:
                                    # ไม่ต้องแนะนำสินค้า (ขาดธาตุ, ไม่พบปัญหา, etc.)
                                    logger.info(f"Skipping product recommendation for: {detection_result.disease_name}")
                                    recommendations = []

                                    # Generate Flex Message response without products
                                    flex_messages = await generate_flex_response(detection_result, recommendations)

                                    # Send Flex Messages via push
                                    await push_line(user_id, flex_messages)

                                    # Clear context
                                    await delete_pending_context(user_id)

                                    # Add to memory
                                    await add_to_memory(user_id, "user", f"[ข้าม] {text}")
                                    await add_to_memory(user_id, "assistant", f"[ผลวิเคราะห์] {detection_result.disease_name}")

                            except Exception as e:
                                logger.error(f"Error in skip analysis: {e}")
                                await push_line(user_id, "ขออภัยค่า เกิดข้อผิดพลาดในการวิเคราะห์ 😢")
                        else:
                            # Analyze with user's additional information
                            try:
                                analyzing_flex = create_analyzing_flex(with_info=True)
                                await reply_line(reply_token, analyzing_flex)

                                # Run detection with extra context
                                detection_result = await detect_disease(image_bytes, extra_user_info=text)

                                # Check if we should recommend products
                                skip_keywords = [
                                    "ไม่พบ", "ไม่ทราบ", "ปกติ", "ไม่ชัดเจน",
                                    "ขาดธาตุ", "ขาดไนโตรเจน", "ขาดฟอสฟอรัส", "ขาดโพแทสเซียม",
                                    "ขาดแมกนีเซียม", "ขาดเหล็ก", "ขาดแคลเซียม", "ขาดโบรอน",
                                    "Deficiency", "deficiency",
                                    "ใบเหลือง", "ใบซีด", "ใบด่าง",
                                    "สุขภาพดี", "healthy", "Healthy"
                                ]
                                should_recommend = True
                                disease_name_lower = detection_result.disease_name.lower()
                                for kw in skip_keywords:
                                    if kw.lower() in disease_name_lower:
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
                                    # ถามระยะปลูกก่อนแนะนำสินค้า
                                    logger.info(f"🌱 Asking for growth stage before product recommendation")

                                    # Save detection result to context for later use
                                    await save_pending_context(user_id, {
                                        "state": "awaiting_growth_stage",
                                        "detection_result": detection_result.dict(),
                                        "plant_type": detection_result.plant_type or "",
                                        "extra_user_info": text,
                                    })

                                    # Generate diagnosis with growth stage question
                                    flex_messages = await generate_diagnosis_with_stage_question(detection_result)

                                    # Send Flex Messages
                                    await push_line(user_id, flex_messages)

                                    # Add to memory
                                    await add_to_memory(user_id, "user", f"[ข้อมูลเพิ่มเติม] {text}")
                                    await add_to_memory(user_id, "assistant", f"[ผลวิเคราะห์] {detection_result.disease_name} - รอเลือกระยะปลูก")

                                else:
                                    # ไม่ต้องแนะนำสินค้า (ขาดธาตุ, ไม่พบปัญหา, etc.)
                                    recommendations = []

                                    # Generate Flex Message response without products
                                    flex_messages = await generate_flex_response(detection_result, recommendations, extra_user_info=text)

                                    # Send Flex Messages via push
                                    await push_line(user_id, flex_messages)

                                    # Clear context
                                    await delete_pending_context(user_id)

                                    # Add to memory
                                    await add_to_memory(user_id, "user", f"[ข้อมูลเพิ่มเติม] {text}")
                                    await add_to_memory(user_id, "assistant", f"[ผลวิเคราะห์] {detection_result.disease_name}")

                            except Exception as e:
                                logger.error(f"Error in analysis with info: {e}", exc_info=True)
                                # Try to send error message
                                try:
                                    await push_line(user_id, f"ขออภัยค่ะ เกิดข้อผิดพลาดในการวิเคราะห์ 😢\n\nError: {str(e)[:100]}")
                                except Exception as e2:
                                    logger.error(f"Failed to send error message: {e2}")
                    elif ctx.get("state") == "awaiting_growth_stage":
                        # User selected growth stage - now recommend products with matching score
                        logger.info(f"🌱 User {user_id} selected growth stage: {text}")

                        try:
                            # Get stored detection result
                            detection_dict = ctx.get("detection_result", {})
                            plant_type = ctx.get("plant_type", "")
                            growth_stage = text  # User's response (e.g., "ระยะแตกกอ 20-50 วัน")

                            # Recreate DiseaseDetectionResult from stored dict
                            from app.models import DiseaseDetectionResult
                            detection_result = DiseaseDetectionResult(**detection_dict)

                            # Get product recommendations with matching score
                            recommendations = await retrieve_products_with_matching_score(
                                detection_result=detection_result,
                                plant_type=plant_type,
                                growth_stage=growth_stage
                            )

                            # Track analytics
                            if analytics_tracker and recommendations:
                                product_names = [p.product_name for p in recommendations]
                                await analytics_tracker.track_product_recommendation(
                                    user_id=user_id,
                                    disease_name=detection_result.disease_name,
                                    products=product_names
                                )

                            # Generate product carousel with context
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
                                        "similarity": p.score if hasattr(p, 'score') else 0.8
                                    })

                                product_flex = create_product_carousel_flex(product_list)

                                # Send header text + product carousel + weather suggestion
                                header_text = f"✅ แนะนำสำหรับ {plant_type} {growth_stage}\n\n💊 ผลิตภัณฑ์ที่เหมาะสม:"

                                # สร้างข้อความถามเรื่องสภาพอากาศพร้อม Quick Reply
                                weather_suggestion = {
                                    "type": "text",
                                    "text": "🌤️ ต้องการดูสภาพอากาศในพื้นที่ไหมคะ?\n\nเพื่อประเมินความเสี่ยงจากสภาพอากาศที่อาจส่งผลต่อพืชของคุณ",
                                    "quickReply": {
                                        "items": [
                                            {
                                                "type": "action",
                                                "action": {
                                                    "type": "location",
                                                    "label": "📍 ดูสภาพอากาศ"
                                                }
                                            },
                                            {
                                                "type": "action",
                                                "action": {
                                                    "type": "message",
                                                    "label": "❌ ไม่ต้องการ",
                                                    "text": "ไม่ต้องการ"
                                                }
                                            }
                                        ]
                                    }
                                }

                                await reply_line(reply_token, [
                                    {"type": "text", "text": header_text},
                                    product_flex,
                                    weather_suggestion
                                ])

                                # Save recommended products to memory
                                await save_recommended_products(
                                    user_id,
                                    recommendations,
                                    disease_name=detection_result.disease_name
                                )
                            else:
                                await reply_line(reply_token, "ขออภัยค่ะ ไม่พบผลิตภัณฑ์ที่เหมาะสมสำหรับระยะนี้ 😢")

                            # Clear context
                            await delete_pending_context(user_id)

                            # Add to memory
                            await add_to_memory(user_id, "user", f"[ระยะปลูก] {text}")
                            await add_to_memory(user_id, "assistant", f"[แนะนำสินค้า] {len(recommendations)} รายการ")

                        except Exception as e:
                            logger.error(f"Error processing growth stage response: {e}", exc_info=True)
                            await reply_line(reply_token, "ขออภัยค่ะ เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้ง 😢")
                            await delete_pending_context(user_id)

                    else:
                        # Context exists but unknown state
                        logger.warning(f"Found context for {user_id} but state is unknown: {ctx.get('state')}")
                        # Fall through to normal conversation
                
                else:
                    # Normal Chat / Q&A
                    if text.lower() in ["ล้างความจำ", "reset", "clear"]:
                        await clear_memory(user_id)
                        await reply_line(reply_token, "ล้างความจำเรียบร้อยค่ะ เริ่มต้นใหม่ได้เลย! ✨")

                    elif text.lower() in ["ช่วยเหลือ", "help", "เมนู"]:
                        # Use Flex Message for help menu
                        help_flex = get_help_menu()
                        await reply_line(reply_token, help_flex)

                    else:
                        # Check if user has completed registration before chat Q&A
                        if not await is_registration_completed(user_id):
                            logger.info(f"User {user_id} not registered - blocking chat Q&A")
                            # Send LIFF registration message
                            reg_flex = create_liff_registration_flex(LIFF_URL)
                            await reply_line(reply_token, reg_flex)
                        else:
                            # Natural Conversation Handler
                            response = await handle_natural_conversation(user_id, text)

                            # Use Flex Message for chat response
                            chat_flex = create_chat_response_flex(text, response)
                            await reply_line(reply_token, chat_flex)

                            # Track analytics
                            if analytics_tracker:
                                response_time = (time.time() - start_time) * 1000
                                await analytics_tracker.track_question(
                                    user_id=user_id,
                                    question=text,
                                    response_time_ms=response_time
                                )

            # 4. Handle Location Message (Weather Check)
            elif event_type == "message" and event.get("message", {}).get("type") == "location":
                lat = event["message"].get("latitude")
                lng = event["message"].get("longitude")
                logger.info(f"Received location from {user_id}: ({lat}, {lng})")

                try:
                    # Call weather API
                    result = await check_weather(lat, lng)

                    if result["success"] and result.get("flexMessage"):
                        # ส่ง Flex Message จาก API กลับไป
                        await reply_line(reply_token, result["flexMessage"])

                        # บันทึก location ไว้สำหรับวิเคราะห์พืช
                        await save_pending_context(user_id, {
                            "state": "weather_received",
                            "lat": lat,
                            "lng": lng,
                            "timestamp": asyncio.get_event_loop().time()
                        })
                    else:
                        # ส่ง error message
                        error_flex = create_weather_error_flex(
                            result.get("error", "ไม่สามารถดูสภาพอากาศได้ กรุณาลองใหม่")
                        )
                        await reply_line(reply_token, error_flex)

                except Exception as e:
                    logger.error(f"Error processing location: {e}")
                    error_flex = create_weather_error_flex("เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้ง")
                    await reply_line(reply_token, error_flex)

            # 5. Handle Postback Events
            elif event_type == "postback":
                postback_data = event.get("postback", {}).get("data", "")
                logger.info(f"Received postback from {user_id}: {postback_data}")

                try:
                    # Parse postback data
                    from urllib.parse import parse_qs
                    params = parse_qs(postback_data)
                    action = params.get("action", [""])[0]

                    if action == "refresh_weather":
                        # ขอ location ใหม่ - ใช้ Quick Reply เพราะ location action ใช้ใน Flex button ไม่ได้
                        refresh_message = {
                            "type": "text",
                            "text": "🔄 รีเฟรชข้อมูลสภาพอากาศ\n\nกดปุ่ม 📍 ด้านล่างเพื่อแชร์ตำแหน่งใหม่",
                            "quickReply": {
                                "items": [
                                    {
                                        "type": "action",
                                        "action": {
                                            "type": "location",
                                            "label": "📍 แชร์ตำแหน่ง"
                                        }
                                    }
                                ]
                            }
                        }
                        await reply_line(reply_token, refresh_message)

                    elif action == "analyze_crop_risk":
                        # วิเคราะห์ความเสี่ยงพืช
                        lat = float(params.get("lat", [0])[0])
                        lng = float(params.get("lng", [0])[0])
                        crop = params.get("crop", [""])[0]

                        if lat and lng and crop:
                            result = await analyze_crop_risk(lat, lng, crop)

                            if result["success"] and result.get("flexMessage"):
                                await reply_line(reply_token, result["flexMessage"])
                            else:
                                error_flex = create_weather_error_flex(
                                    result.get("error", "ไม่สามารถวิเคราะห์ได้ กรุณาลองใหม่")
                                )
                                await reply_line(reply_token, error_flex)
                        else:
                            await reply_line(reply_token, "ข้อมูลไม่ครบถ้วน กรุณาลองใหม่อีกครั้งค่ะ")

                    elif action == "select_crop_for_risk":
                        # ผู้ใช้ต้องการวิเคราะห์ความเสี่ยงพืช - แสดงตัวเลือกพืช
                        ctx = await get_pending_context(user_id)
                        if ctx and ctx.get("state") == "weather_received":
                            lat = ctx.get("lat")
                            lng = ctx.get("lng")
                            crop_flex = create_crop_selection_flex(lat, lng)
                            await reply_line(reply_token, crop_flex)
                        else:
                            # ไม่มี location - ขอให้ส่ง location ใหม่ (ใช้ Quick Reply)
                            no_location_message = {
                                "type": "text",
                                "text": "📍 กรุณาแชร์ตำแหน่งก่อน\n\nกดปุ่มด้านล่างเพื่อแชร์ตำแหน่งของคุณ",
                                "quickReply": {
                                    "items": [
                                        {
                                            "type": "action",
                                            "action": {
                                                "type": "location",
                                                "label": "🌤️ ดูสภาพอากาศ"
                                            }
                                        }
                                    ]
                                }
                            }
                            await reply_line(reply_token, no_location_message)
                    else:
                        logger.warning(f"Unknown postback action: {action}")

                except Exception as e:
                    logger.error(f"Error processing postback: {e}")
                    await reply_line(reply_token, "ขออภัยค่ะ เกิดข้อผิดพลาด กรุณาลองใหม่")

            # 6. Handle Sticker (Just for fun)
            elif event_type == "message" and event.get("message", {}).get("type") == "sticker":
                # Reply with a sticker
                await reply_line(reply_token, "ขอบคุณค่ะ! 😊", with_sticker=True)

        return JSONResponse(content={"status": "success"})
        
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)

if __name__ == "__main__":
    # อ่าน Port จาก Environment Variable ที่ Cloud Platform (Fly.io/Vercel) ส่งมา 
    # และใช้ 8080 เป็นค่า Default (ตามที่ Fly.io แนะนำ)
    port = int(os.environ.get("PORT", 8080))
    
    # รัน Uvicorn ด้วยค่า Port ที่อ่านได้
    uvicorn.run('app.main:app', host='0.0.0.0', port=port, reload=True)