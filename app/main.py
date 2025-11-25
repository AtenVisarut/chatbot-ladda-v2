import logging
import asyncio
import json
import time
import os
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
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
    SECRET_KEY
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
    get_product_catalog_message
)
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
    add_to_memory
)
from app.services.disease_detection import detect_disease
from app.services.product_recommendation import retrieve_product_recommendation
from app.services.response_generator import generate_final_response
from app.services.chat import handle_natural_conversation

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
            from app.services.user_service import ensure_user_exists
            await ensure_user_exists(user_id)
            
            # 1. Handle Follow Event (Welcome Message)
            if event_type == "follow":
                logger.info(f"User {user_id} followed the bot")
                welcome_msg = get_welcome_message()
                await reply_line(reply_token, welcome_msg)
                continue

            # 2. Handle Image Message (Interactive Diagnosis)
            if event_type == "message" and event.get("message", {}).get("type") == "image":
                message_id = event["message"]["id"]
                logger.info(f"Received image from {user_id}")
                
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
                    questions_message = get_initial_questions_message()
                    await reply_line(reply_token, questions_message)
                    
                    # Add to memory
                    await add_to_memory(user_id, "user", "[ส่งรูปภาพพืช]")
                    await add_to_memory(user_id, "assistant", questions_message)
                    
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
                # Registration Flow
                # ============================================================================#
                from app.services.registration import registration_manager
                
                logger.info(f"🟢 Checking registration for text: '{text}'")
                
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
                
                # 1. Check if user wants to start registration
                if text == "ลงทะเบียน":
                    logger.info(f"🟢 User {user_id} wants to start registration")
                    reg_message = await registration_manager.start_registration(user_id)
                    # Already a dict, no need to convert
                    await reply_line(reply_token, reg_message)
                    return JSONResponse(content={"status": "success"})
                
                # 2. Check if user is in registration process
                reg_state = await registration_manager.get_registration_state(user_id)
                logger.info(f"🟢 Registration state for {user_id}: {reg_state}")
                if reg_state:
                    logger.info(f"🟢 User {user_id} is in registration, handling input")
                    response_msg = await registration_manager.handle_registration_input(user_id, text)
                    # Already a dict, no need to convert
                    await reply_line(reply_token, response_msg)
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
                                skip_msg = get_skip_analysis_message()
                                await reply_line(reply_token, skip_msg)
                                
                                detection_result = await detect_disease(image_bytes)
                                
                                # Check if we should recommend products
                                # Skip if: Not found, Unknown, Normal, Unclear
                                skip_keywords = ["ไม่พบ", "ไม่ทราบ", "ปกติ", "ไม่ชัดเจน"]
                                should_recommend = True
                                for kw in skip_keywords:
                                    if kw in detection_result.disease_name:
                                        should_recommend = False
                                        break
                                
                                if should_recommend:
                                    recommendations = await retrieve_product_recommendation(detection_result)
                                else:
                                    logger.info(f"Skipping product recommendation for: {detection_result.disease_name}")
                                    recommendations = []
                                    
                                final_response = await generate_final_response(detection_result, recommendations)
                                
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
                                    
                                    # Track product recommendations
                                    if recommendations:
                                        product_names = [p.product_name for p in recommendations]
                                        await analytics_tracker.track_product_recommendation(
                                            user_id=user_id,
                                            disease_name=detection_result.disease_name,
                                            products=product_names
                                        )
                                
                                # Send result via push (reply_token already used)
                                await push_line(user_id, final_response)
                                
                                # Clear context
                                await delete_pending_context(user_id)
                                
                                # Add to memory
                                await add_to_memory(user_id, "user", f"[ข้าม] {text}")
                                await add_to_memory(user_id, "assistant", final_response)
                                
                            except Exception as e:
                                logger.error(f"Error in skip analysis: {e}")
                                await push_line(user_id, "ขออภัยค่า เกิดข้อผิดพลาดในการวิเคราะห์ 😢")
                        else:
                            # Analyze with user's additional information
                            try:
                                analyzing_msg = get_analyzing_with_info_message()
                                await reply_line(reply_token, analyzing_msg)
                                
                                # Run detection with extra context
                                detection_result = await detect_disease(image_bytes, extra_user_info=text)
                                recommendations = await retrieve_product_recommendation(detection_result)
                                final_response = await generate_final_response(detection_result, recommendations, extra_user_info=text)
                                
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
                                    
                                    # Track product recommendations
                                    if recommendations:
                                        product_names = [p.product_name for p in recommendations]
                                        await analytics_tracker.track_product_recommendation(
                                            user_id=user_id,
                                            disease_name=detection_result.disease_name,
                                            products=product_names
                                        )
                                
                                # Send result via push (reply_token already used)
                                await push_line(user_id, final_response)
                                
                                # Clear context
                                await delete_pending_context(user_id)
                                
                                # Add to memory
                                await add_to_memory(user_id, "user", f"[ข้อมูลเพิ่มเติม] {text}")
                                await add_to_memory(user_id, "assistant", final_response)
                                
                            except Exception as e:
                                logger.error(f"Error in analysis with info: {e}")
                                await push_line(user_id, "ขออภัยค่ะ เกิดข้อผิดพลาดในการวิเคราะห์ 😢")
                    else:
                        # Context exists but not awaiting info (shouldn't happen normally)
                        logger.warning(f"Found context for {user_id} but state is not awaiting_info")
                        # Fall through to normal conversation
                
                else:
                    # Normal Chat / Q&A
                    if text.lower() in ["ล้างความจำ", "reset", "clear"]:
                        await clear_memory(user_id)
                        await reply_line(reply_token, "ล้างความจำเรียบร้อยค่ะ เริ่มต้นใหม่ได้เลย! ✨")
                    
                    elif text.lower() in ["ช่วยเหลือ", "help", "เมนู"]:
                        help_msg = """🌱 **เมนูช่วยเหลือ**
1. **ตรวจโรคพืช**: ส่งรูปภาพใบพืชที่มีอาการ
2. **ถามข้อมูล**: พิมพ์คำถามเกี่ยวกับโรคหรือผลิตภัณฑ์
3. **ลงทะเบียน**: พิมพ์ "ลงทะเบียน" เพื่อรับบริการเต็มรูปแบบ
4. **ล้างความจำ**: พิมพ์ "reset" เพื่อเริ่มใหม่

ต้องการให้ช่วยอะไรบอกได้เลยนะคะ! 😊"""
                        await reply_line(reply_token, help_msg)
                    
                    else:
                        # Natural Conversation Handler
                        response = await handle_natural_conversation(user_id, text)
                        await reply_line(reply_token, response)
                        
                        # Track analytics
                        if analytics_tracker:
                            response_time = (time.time() - start_time) * 1000
                            await analytics_tracker.track_question(
                                user_id=user_id, 
                                question=text,
                                response_time_ms=response_time
                            )

            # 4. Handle Sticker (Just for fun)
            elif event_type == "message" and event.get("message", {}).get("type") == "sticker":
                # Reply with a sticker
                await reply_line(reply_token, "ขอบคุณค่ะ! 😊", with_sticker=True)

        return JSONResponse(content={"status": "success"})
        
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
