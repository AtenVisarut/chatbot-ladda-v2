# Context Handler - จัดการ interrupt และ fallback ระหว่าง flow
import logging
from typing import Optional, Tuple

from app.services.cache import get_pending_context, save_pending_context, delete_pending_context
from app.utils.line_helpers import reply_line
from app.utils.flex_messages import create_initial_questions_flex

logger = logging.getLogger(__name__)

# Keywords สำหรับตรวจจับคำสั่ง
CANCEL_KEYWORDS = ["ยกเลิก", "cancel", "เริ่มใหม่", "reset", "ล้าง", "หยุด"]
CONTINUE_KEYWORDS = ["ทำต่อ", "continue", "ต่อ", "กลับ"]
NEW_IMAGE_KEYWORDS = ["รูปใหม่", "ใช้รูปใหม่", "วิเคราะห์รูปใหม่"]
OLD_IMAGE_KEYWORDS = ["รูปเดิม", "ใช้รูปเดิม", "ทำต่อรูปเดิม"]

# Valid responses สำหรับแต่ละ state
VALID_GROWTH_STAGES = [
    "ระยะกล้า", "ระยะแตกกอ", "ระยะตั้งท้อง", 
    "ระยะออกรวง", "ระยะสุกแก่", "ไม่ทราบ",
    "กล้า", "แตกกอ", "ตั้งท้อง", "ออกรวง", "สุกแก่"
]

SKIP_KEYWORDS = ["ข้าม", "skip", "ไม่ทราบ", "ไม่รู้", "ไม่มี"]


def is_cancel_command(text: str) -> bool:
    """ตรวจว่าเป็นคำสั่งยกเลิกหรือไม่"""
    text_lower = text.lower().strip()
    return any(kw in text_lower for kw in CANCEL_KEYWORDS)


def is_continue_command(text: str) -> bool:
    """ตรวจว่าเป็นคำสั่งทำต่อหรือไม่"""
    text_lower = text.lower().strip()
    return any(kw in text_lower for kw in CONTINUE_KEYWORDS)


def is_new_image_command(text: str) -> bool:
    """ตรวจว่าเป็นคำสั่งใช้รูปใหม่หรือไม่"""
    text_lower = text.lower().strip()
    return any(kw in text_lower for kw in NEW_IMAGE_KEYWORDS)


def is_old_image_command(text: str) -> bool:
    """ตรวจว่าเป็นคำสั่งใช้รูปเดิมหรือไม่"""
    text_lower = text.lower().strip()
    return any(kw in text_lower for kw in OLD_IMAGE_KEYWORDS)


def is_valid_growth_stage(text: str) -> bool:
    """ตรวจว่าเป็นระยะปลูกที่ valid หรือไม่"""
    text_lower = text.lower().strip()
    return any(stage.lower() in text_lower for stage in VALID_GROWTH_STAGES)


def is_skip_command(text: str) -> bool:
    """ตรวจว่าเป็นคำสั่งข้ามหรือไม่"""
    text_lower = text.lower().strip()
    return any(kw in text_lower for kw in SKIP_KEYWORDS)


def is_general_question(text: str) -> bool:
    """ตรวจว่าเป็นคำถามทั่วไป ไม่ใช่ข้อมูลพืช"""
    question_patterns = ["?", "ไหม", "อะไร", "ยังไง", "ทำไม", "เท่าไหร่", "ที่ไหน", "เมื่อไหร่"]
    # ถ้ามี pattern คำถาม และไม่ใช่ข้อมูลพืช
    has_question = any(p in text for p in question_patterns)
    # ข้อมูลพืชมักจะสั้นและไม่มีคำถาม
    return has_question and len(text) > 20


async def create_continue_or_cancel_flex(current_task: str) -> dict:
    """สร้าง Flex Message ถาม ทำต่อ/ยกเลิก"""
    return {
        "type": "flex",
        "altText": f"คุณกำลัง{current_task}อยู่",
        "contents": {
            "type": "bubble",
            "size": "kilo",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "⚠️ มีงานค้างอยู่",
                        "weight": "bold",
                        "size": "lg",
                        "color": "#FF6B00"
                    },
                    {
                        "type": "text",
                        "text": f"คุณกำลัง{current_task}อยู่ค่ะ",
                        "size": "sm",
                        "color": "#666666",
                        "margin": "md",
                        "wrap": True
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "horizontal",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "color": "#4CAF50",
                        "action": {
                            "type": "message",
                            "label": "✅ ทำต่อ",
                            "text": "ทำต่อ"
                        }
                    },
                    {
                        "type": "button",
                        "style": "secondary",
                        "action": {
                            "type": "message",
                            "label": "❌ ยกเลิก",
                            "text": "ยกเลิก"
                        }
                    }
                ]
            }
        }
    }


async def create_image_choice_flex() -> dict:
    """สร้าง Flex Message ถาม รูปใหม่/รูปเดิม"""
    return {
        "type": "flex",
        "altText": "คุณส่งรูปใหม่มา",
        "contents": {
            "type": "bubble",
            "size": "kilo",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "📷 ส่งรูปใหม่",
                        "weight": "bold",
                        "size": "lg",
                        "color": "#1E88E5"
                    },
                    {
                        "type": "text",
                        "text": "คุณกำลังวิเคราะห์รูปอยู่ แต่ส่งรูปใหม่มา",
                        "size": "sm",
                        "color": "#666666",
                        "margin": "md",
                        "wrap": True
                    },
                    {
                        "type": "text",
                        "text": "ต้องการวิเคราะห์รูปไหนคะ?",
                        "size": "sm",
                        "color": "#666666",
                        "margin": "sm",
                        "wrap": True
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "horizontal",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "color": "#1E88E5",
                        "action": {
                            "type": "message",
                            "label": "🆕 รูปใหม่",
                            "text": "รูปใหม่"
                        }
                    },
                    {
                        "type": "button",
                        "style": "secondary",
                        "action": {
                            "type": "message",
                            "label": "📷 รูปเดิม",
                            "text": "รูปเดิม"
                        }
                    }
                ]
            }
        }
    }


async def create_growth_stage_flex() -> dict:
    """สร้าง Flex Message ถามระยะปลูก"""
    return {
        "type": "flex",
        "altText": "เลือกระยะการเจริญเติบโต",
        "contents": {
            "type": "bubble",
            "size": "kilo",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "🌱 เลือกระยะปลูก",
                        "weight": "bold",
                        "size": "lg",
                        "color": "#4CAF50"
                    },
                    {
                        "type": "text",
                        "text": "กรุณาเลือกระยะการเจริญเติบโตของพืช",
                        "size": "sm",
                        "color": "#666666",
                        "margin": "md",
                        "wrap": True
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "spacing": "sm",
                        "contents": [
                            {
                                "type": "button",
                                "style": "primary",
                                "color": "#81C784",
                                "action": {
                                    "type": "message",
                                    "label": "🌱 ระยะกล้า",
                                    "text": "ระยะกล้า"
                                }
                            },
                            {
                                "type": "button",
                                "style": "primary",
                                "color": "#66BB6A",
                                "action": {
                                    "type": "message",
                                    "label": "🌿 ระยะแตกกอ",
                                    "text": "ระยะแตกกอ"
                                }
                            }
                        ]
                    },
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "spacing": "sm",
                        "contents": [
                            {
                                "type": "button",
                                "style": "primary",
                                "color": "#4CAF50",
                                "action": {
                                    "type": "message",
                                    "label": "🌾 ระยะออกรวง",
                                    "text": "ระยะออกรวง"
                                }
                            },
                            {
                                "type": "button",
                                "style": "secondary",
                                "action": {
                                    "type": "message",
                                    "label": "❓ ไม่ทราบ",
                                    "text": "ไม่ทราบ"
                                }
                            }
                        ]
                    },
                    {
                        "type": "button",
                        "style": "secondary",
                        "action": {
                            "type": "message",
                            "label": "❌ ยกเลิก",
                            "text": "ยกเลิก"
                        }
                    }
                ]
            }
        }
    }


async def handle_context_interrupt(user_id: str, text: str, ctx: dict, reply_token: str) -> Tuple[bool, Optional[dict]]:
    """
    จัดการเมื่อ user ส่งข้อความระหว่าง flow
    
    Returns:
        Tuple[bool, Optional[dict]]:
            - (True, None): จัดการแล้ว ไม่ต้องทำอะไรต่อ
            - (True, new_ctx): จัดการแล้ว และมี context ใหม่ให้ใช้
            - (False, None): ไม่ได้จัดการ ให้ flow ปกติทำต่อ
    """
    state = ctx.get("state")
    logger.info(f"🔍 Context handler: user={user_id}, state={state}, text={text[:50]}")
    
    # === 1. ตรวจจับคำสั่งยกเลิก ===
    if is_cancel_command(text):
        logger.info(f"❌ User {user_id} cancelled flow")
        await delete_pending_context(user_id)
        await reply_line(reply_token, "ยกเลิกแล้วค่ะ ส่งรูปใหม่ได้เลย 📷")
        return (True, None)
    
    # === 2. ตรวจจับคำสั่งทำต่อ ===
    if is_continue_command(text):
        logger.info(f"✅ User {user_id} wants to continue")
        return await resend_current_question(user_id, ctx, reply_token)
    
    # === 3. ตรวจจับคำสั่งเลือกรูป (กรณี awaiting_image_choice) ===
    if state == "awaiting_image_choice":
        if is_new_image_command(text):
            # ใช้รูปใหม่
            new_message_id = ctx.get("new_message_id")
            logger.info(f"🆕 User {user_id} chose new image: {new_message_id}")
            
            # สร้าง context ใหม่ด้วยรูปใหม่
            new_ctx = {
                "message_id": new_message_id,
                "timestamp": ctx.get("timestamp"),
                "state": "awaiting_info",
                "additional_info": None
            }
            await save_pending_context(user_id, new_ctx)
            
            # ส่งคำถามใหม่
            questions_flex = create_initial_questions_flex()
            await reply_line(reply_token, questions_flex)
            return (True, None)
            
        elif is_old_image_command(text):
            # ใช้รูปเดิม - กลับไป state เดิม
            old_state = ctx.get("old_state", "awaiting_info")
            logger.info(f"📷 User {user_id} chose old image, back to state: {old_state}")
            
            # Restore context เดิม
            new_ctx = {
                "message_id": ctx.get("old_message_id", ctx.get("message_id")),
                "timestamp": ctx.get("timestamp"),
                "state": old_state,
                "additional_info": ctx.get("additional_info"),
                "detection_result": ctx.get("detection_result"),
                "plant_type": ctx.get("plant_type"),
                "extra_user_info": ctx.get("extra_user_info")
            }
            await save_pending_context(user_id, new_ctx)
            
            # ส่งคำถามตาม state เดิม
            return await resend_current_question(user_id, new_ctx, reply_token)
        else:
            # ไม่ใช่คำตอบที่คาดหวัง - ถามซ้ำ
            image_choice_flex = await create_image_choice_flex()
            await reply_line(reply_token, image_choice_flex)
            return (True, None)
    
    # === 4. ตรวจจับคำตอบที่ไม่ valid สำหรับ awaiting_growth_stage ===
    # Relaxed validation: Allow any text answer to pass through to main logic
    # unless it is an explicit Cancel command (already handled in step 1)
    if state == "awaiting_growth_stage":
        # ถ้าเป็นคำสั่งข้าม ให้ผ่านไป
        if is_skip_command(text):
            return (False, None)
            
        # ถ้าพิมพ์ยาวๆ หรือเป็นประโยค อาจจะเป็น feedback หรือข้อมูลเพิ่มเติม 
        # ให้ main.py จัดการต่อได้เลย ไม่ต้อง block
        pass
    
    # === 5. ตรวจจับคำถามทั่วไประหว่าง awaiting_info ===
    if state == "awaiting_info":
        if is_general_question(text):
            logger.info(f"⚠️ General question during awaiting_info from {user_id}: {text}")
            flex = await create_continue_or_cancel_flex("วิเคราะห์รูปพืช")
            await reply_line(reply_token, flex)
            return (True, None)
    
    # === ไม่ตรงเงื่อนไขใดๆ - ให้ flow ปกติทำต่อ ===
    return (False, None)


async def resend_current_question(user_id: str, ctx: dict, reply_token: str) -> Tuple[bool, Optional[dict]]:
    """ส่งคำถามปัจจุบันซ้ำ"""
    state = ctx.get("state")
    logger.info(f"🔄 Resending question for state: {state}")
    
    if state == "awaiting_info":
        questions_flex = create_initial_questions_flex()
        await reply_line(reply_token, questions_flex)
        return (True, None)
        
    elif state == "awaiting_growth_stage":
        growth_flex = await create_growth_stage_flex()
        await reply_line(reply_token, growth_flex)
        return (True, None)
    
    elif state == "awaiting_image_choice":
        image_flex = await create_image_choice_flex()
        await reply_line(reply_token, image_flex)
        return (True, None)
    
    # Unknown state - ให้ flow ปกติจัดการ
    return (False, None)


async def handle_new_image_during_flow(user_id: str, new_message_id: str, existing_ctx: dict, reply_token: str) -> bool:
    """
    จัดการเมื่อ user ส่งรูปใหม่ระหว่าง flow
    
    Returns:
        True: จัดการแล้ว (ถาม user ว่าจะใช้รูปไหน)
        False: ไม่มี context เดิม ให้ทำงานปกติ
    """
    if not existing_ctx:
        return False
    
    current_state = existing_ctx.get("state")
    logger.info(f"📷 New image during flow: user={user_id}, current_state={current_state}")
    
    # เก็บรูปใหม่และ state เดิมไว้
    await save_pending_context(user_id, {
        **existing_ctx,
        "new_message_id": new_message_id,
        "old_message_id": existing_ctx.get("message_id"),
        "old_state": current_state,
        "state": "awaiting_image_choice"
    })
    
    # ถาม user ว่าจะใช้รูปไหน
    image_choice_flex = await create_image_choice_flex()
    await reply_line(reply_token, image_choice_flex)
    
    return True
