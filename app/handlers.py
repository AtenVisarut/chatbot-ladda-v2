"""
LINE webhook handlers for Multi-Agent System
"""
from typing import Dict, Any, List
import logging
from fastapi import HTTPException
try:
    from linebot.models import TextSendMessage, FlexSendMessage
except Exception:
    # line-bot-sdk may not be installed in dev environment; allow imports to fail at runtime
    TextSendMessage = None
    FlexSendMessage = None

logger = logging.getLogger(__name__)


async def handle_image_message(event: Dict[str, Any], coordinator) -> Dict[str, Any]:
    """
    Process image messages using Multi-Agent System
    """
    try:
        # Extract image content/URL
        message_id = event["message"]["id"]
        reply_token = event.get("replyToken")

        # Prepare data for agents
        data = {
            "message_id": message_id,
            "image_url": f"https://api-data.line.me/v2/bot/message/{message_id}/content",
            "user_id": event["source"].get("userId")
        }

        # Process with agent system
        result = await coordinator.process_request(data)

        # Format response for LINE
        formatted = coordinator.format_response(result)
        
        # Add website links for more details
        messages = formatted.get("messages", [])
        if any(msg.get("type") == "flex" for msg in messages):  # If there's product information
            messages.extend([
                {
                    "type": "text",
                    "text": "รายละเอียดเพิ่มเติมของผลิตภัณฑ์และสินค้าทั้งหมด สามารถดูได้ที่:\nhttps://www.icpladda.com/product-category/%E0%B8%AA%E0%B8%B4%E0%B8%99%E0%B8%84%E0%B9%89%E0%B8%B2%E0%B8%97%E0%B8%B1%E0%B9%89%E0%B8%87%E0%B8%AB%E0%B8%A1%E0%B8%94/"
                },
                {
                    "type": "text",
                    "text": "ดูข้อมูลเพิ่มเติมเกี่ยวกับบริษัทได้ที่:\nhttps://www.icpladda.com/about/"
                }
            ])
        
        return {"replyToken": reply_token, "messages": messages}

    except Exception as e:
        logger.error(f"Error processing image: {str(e)}")
        return {"replyToken": event.get("replyToken"), "messages": [{
            "type": "text",
            "text": "ขออภัยค่ะ เกิดข้อผิดพลาดในการวิเคราะห์รูปภาพ กรุณาลองใหม่อีกครั้ง"
        }]}


async def handle_text_message(event: Dict[str, Any], coordinator) -> Dict[str, Any]:
    """
    Process text messages using Multi-Agent System
    """
    try:
        # Extract message text
        message_text = event["message"]["text"]
        reply_token = event.get("replyToken")

        # Prepare data for agents
        data = {
            "message": message_text,
            "user_id": event["source"].get("userId")
        }

        # Process with agent system
        result = await coordinator.process_request(data)

        # Format response for LINE
        formatted = coordinator.format_response(result)
        
        # Add website links for more details
        messages = formatted.get("messages", [])
        if any(msg.get("type") == "flex" for msg in messages):  # If there's product information
            messages.extend([
                {
                    "type": "text",
                    "text": "รายละเอียดเพิ่มเติมของผลิตภัณฑ์และสินค้าทั้งหมด สามารถดูได้ที่:\nhttps://www.icpladda.com/product-category/%E0%B8%AA%E0%B8%B4%E0%B8%99%E0%B8%84%E0%B9%89%E0%B8%B2%E0%B8%97%E0%B8%B1%E0%B9%89%E0%B8%87%E0%B8%AB%E0%B8%A1%E0%B8%94/"
                },
                {
                    "type": "text",
                    "text": "ดูข้อมูลเพิ่มเติมเกี่ยวกับบริษัทได้ที่:\nhttps://www.icpladda.com/about/"
                }
            ])
        
        return {"replyToken": reply_token, "messages": messages}

    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        return {"replyToken": event.get("replyToken"), "messages": [{
            "type": "text",
            "text": "ขออภัยค่ะ เกิดข้อผิดพลาดในการประมวลผล กรุณาลองใหม่อีกครั้ง"
        }]}


def send_line_response(reply_token: str, messages: List[Dict[str, Any]], line_bot_api) -> None:
    """
    Send formatted messages to LINE (synchronous call to line-bot-sdk)
    """
    try:
        message_objects = []
        for message in messages:
            if message.get("type") == "text":
                if TextSendMessage is None:
                    raise RuntimeError("line-bot-sdk not installed")
                message_objects.append(TextSendMessage(text=message.get("text", "")))
            elif message.get("type") == "flex":
                if FlexSendMessage is None:
                    raise RuntimeError("line-bot-sdk not installed")
                message_objects.append(FlexSendMessage(alt_text=message.get("altText", "message"), contents=message.get("contents")))

        if message_objects:
            line_bot_api.reply_message(reply_token, message_objects)

    except Exception as e:
        logger.error(f"Error sending LINE response: {str(e)}")
        raise HTTPException(status_code=500, detail="Error sending LINE response")