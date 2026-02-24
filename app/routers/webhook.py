import logging
import asyncio
import json
import time
from fastapi import APIRouter, Request, HTTPException, Header
from fastapi.responses import JSONResponse

from app.dependencies import analytics_tracker
from app.services.welcome import (
    get_welcome_message,
    get_usage_guide,
    get_product_catalog_message,
    get_help_menu
)
from app.utils.line.text_messages import (
    get_initial_questions_text,
    get_analyzing_text,
    get_growth_stage_question_text,
    get_other_plant_prompt_text,
    get_plant_type_retry_text,
    format_product_list_text
)
from app.services.cache import (
    save_pending_context,
    get_pending_context,
    delete_pending_context
)
from app.services.memory import (
    clear_memory,
    add_to_memory,
    save_recommended_products
)
try:
    from app.services.disease.detection import smart_detect_disease
except ImportError:
    smart_detect_disease = None
from app.services.product.recommendation import retrieve_products_with_matching_score, get_search_query_for_disease
try:
    from app.services.disease.response import generate_text_response
except ImportError:
    generate_text_response = None
from app.services.chat.handler import handle_natural_conversation
from app.services.context_handler import (
    handle_context_interrupt,
    handle_new_image_during_flow
)
from app.utils.line.helpers import (
    verify_line_signature,
    get_image_content_from_line,
    reply_line,
    push_line
)
from app.utils.rate_limiter import check_user_rate_limit
from app.config import MAX_CONCURRENT_TASKS

logger = logging.getLogger(__name__)

# Centralized no-data filter — suppress ANY answer containing these phrases
_NO_DATA_PHRASES_FINAL = [
    "ไม่พบข้อมูล", "ไม่มีข้อมูล", "ไม่อยู่ในฐานข้อมูล",
    "ไม่มีในระบบ", "ไม่พบสินค้า", "ยังไม่มีสินค้าในระบบ",
    "ไม่พบในระบบ", "ไม่พบในฐานข้อมูล",
]

def _is_no_data_answer(answer: str) -> bool:
    """ตรวจว่า answer เป็นคำตอบ 'ไม่มีข้อมูล' ที่ไม่ควรส่งให้ user"""
    return any(p in answer for p in _NO_DATA_PHRASES_FINAL)

router = APIRouter()

# Semaphore to limit concurrent background tasks (prevents memory exhaustion)
_task_semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)


@router.post("/webhook")
async def callback(request: Request, x_line_signature: str = Header(None)):
    """
    LINE Webhook endpoint - returns 200 immediately to prevent timeout.
    Actual processing happens in background via asyncio.create_task.
    """
    if not x_line_signature:
        raise HTTPException(status_code=400, detail="Missing X-Line-Signature header")

    body = await request.body()

    # Reject oversized payloads (LINE messages typically < 50 KB)
    MAX_BODY_SIZE = 1024 * 256  # 256 KB
    if len(body) > MAX_BODY_SIZE:
        logger.warning(f"Payload too large: {len(body)} bytes")
        raise HTTPException(status_code=413, detail="Payload too large")

    body_str = body.decode('utf-8')

    # Verify signature
    try:
        if not verify_line_signature(body, x_line_signature):
            logger.warning("Invalid signature")
            raise HTTPException(status_code=400, detail="Invalid signature")
    except HTTPException:
        raise
    except Exception as sig_err:
        logger.error(f"Signature verification error: {sig_err}", exc_info=True)
        raise HTTPException(status_code=500, detail="Signature verification failed")

    # Parse events
    try:
        events = json.loads(body_str).get("events", [])
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse webhook body: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # FIX: Return 200 IMMEDIATELY to prevent LINE timeout (499)
    # Process events in background - reply_token valid for ~30 seconds
    if events:
        asyncio.create_task(_guarded_process_webhook(events))

    return JSONResponse(content={"status": "success"})


async def _guarded_process_webhook(events: list):
    """Acquire semaphore before processing — limits concurrent background tasks."""
    try:
        # Try to acquire without blocking (timeout=0)
        try:
            await asyncio.wait_for(_task_semaphore.acquire(), timeout=0.01)
        except asyncio.TimeoutError:
            # All slots busy — notify first user and wait for a slot
            logger.warning(f"Semaphore full ({MAX_CONCURRENT_TASKS} tasks running) — queuing")
            reply_token = next((e.get("replyToken") for e in events if e.get("replyToken")), None)
            if reply_token:
                try:
                    await reply_line(reply_token, "ขออภัยค่ะ ระบบกำลังยุ่งอยู่ กรุณารอสักครู่แล้วลองใหม่นะคะ ⏳")
                except Exception:
                    pass
            # Still wait for a slot (graceful queuing, not rejection)
            await _task_semaphore.acquire()

        try:
            await _process_webhook_events(events)
        finally:
            _task_semaphore.release()
    except Exception as e:
        logger.error(f"Guarded webhook error: {e}", exc_info=True)


async def _process_webhook_events(events: list):
    """Process webhook events in background task (per-event error isolation)"""
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
            from app.services.user_service import ensure_user_exists
            await ensure_user_exists(user_id)

            # 1. Handle Follow Event (Welcome Message)
            if event_type == "follow":
                logger.info(f"User {user_id} followed the bot")

                # Register user in user_ladda(LINE,FACE) table
                from app.services.user_service import get_line_profile, register_user_ladda
                profile = await get_line_profile(user_id)
                display_name = profile.get("displayName") if profile else None
                await register_user_ladda(user_id, display_name)

                welcome_text = get_welcome_message()
                await reply_line(reply_token, welcome_text)
                continue

            # 2. Handle Image Message (Interactive Diagnosis)
            if event_type == "message" and event.get("message", {}).get("type") == "image":
                from app.config import ENABLE_IMAGE_DIAGNOSIS
                if not ENABLE_IMAGE_DIAGNOSIS:
                    await reply_line(reply_token, "น้องลัดดายังไม่สามารถสแกนโรคพืชจากภาพได้ค่ะ ลัดดาจะรับได้เฉพาะข้อความเท่านั้นนะคะ ขอบคุณค่ะ")
                    continue

                message_id = event["message"]["id"]
                logger.info(f"Received image from {user_id}")

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


                # ============================================================================#

                if ctx:
                    # === ถ้าปิด image diagnosis แล้วมี pending context ค้าง → ลบทิ้งแล้วไป normal flow ===
                    from app.config import ENABLE_IMAGE_DIAGNOSIS
                    if not ENABLE_IMAGE_DIAGNOSIS:
                        await delete_pending_context(user_id)
                        answer = await handle_natural_conversation(user_id, text)
                        if answer is not None and not _is_no_data_answer(answer):
                            await reply_line(reply_token, answer)
                        else:
                            logger.info(f"⏭️ No data for {user_id} — skipping reply (admin will handle)")
                        continue

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

                        # Q&A Chat - Vector Search from products, diseases, knowledge
                        answer = await handle_natural_conversation(user_id, text)
                        if answer is not None and not _is_no_data_answer(answer):
                            await reply_line(reply_token, answer)
                        else:
                            logger.info(f"⏭️ No data for {user_id} — skipping reply (admin will handle)")

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
                        # Q&A Chat - Vector Search from products, diseases, knowledge
                        answer = await handle_natural_conversation(user_id, text)
                        if answer is not None and not _is_no_data_answer(answer):
                            await reply_line(reply_token, answer)
                        else:
                            logger.info(f"⏭️ No data for {user_id} — skipping reply (admin will handle)")

            # 4. Handle Sticker (Just for fun)
            elif event_type == "message" and event.get("message", {}).get("type") == "sticker":
                # Reply with a sticker
                await reply_line(reply_token, "ขอบคุณค่ะ! 😊", with_sticker=True)

        logger.info(f"✅ Background webhook processing completed in {time.time() - start_time:.2f}s")

    except Exception as e:
        logger.error(f"Background webhook error: {e}", exc_info=True)
        # Try to send error reply if we have a valid reply_token
        try:
            if 'reply_token' in dir() and reply_token:
                await reply_line(reply_token, "ขออภัยค่ะ เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้งนะคะ")
        except Exception:
            pass  # reply_token may have expired
