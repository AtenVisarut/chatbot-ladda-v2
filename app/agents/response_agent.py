"""
Response Agent: Generates final LINE responses
"""
from typing import Dict, Any, List
from langgraph.graph import MessageGraph
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger(__name__)

class ResponseAgent(BaseModel):
    """Agent for generating final responses"""
    
    async def format_response(
        self,
        disease_info: Dict[str, Any],
        products: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Format response for LINE"""
        try:
            messages = []
            
            # Disease info message
            disease_text = (
                f"🔍 ผลตรวจจากภาพ: {disease_info['disease_name']}\n\n"
                f"ระดับความมั่นใจ: {disease_info['confidence']}\n"
                f"ความรุนแรง: {disease_info['severity']}\n\n"
                f"อาการที่เห็น: {disease_info['symptoms']}"
            )
            
            messages.append({
                "type": "text",
                "text": disease_text
            })
            
            # Product recommendations (Flex Message)
            if products:
                product_flex = {
                    "type": "flex",
                    "altText": "แนะนำผลิตภัณฑ์สำหรับการรักษา",
                    "contents": {
                        "type": "bubble",
                        "header": {
                            "type": "box",
                            "layout": "vertical",
                            "contents": [{
                                "type": "text",
                                "text": "ผลิตภัณฑ์ที่แนะนำ",
                                "weight": "bold",
                                "size": "lg"
                            }]
                        },
                        "body": {
                            "type": "box",
                            "layout": "vertical",
                            "contents": []
                        }
                    }
                }
                
                for product in products[:5]:
                    product_flex["contents"]["body"]["contents"].append({
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "text",
                                "text": f"🏷️ {product['product_name']}",
                                "weight": "bold",
                                "wrap": True
                            },
                            {
                                "type": "text",
                                "text": f"วิธีใช้: {product['how_to_use']}",
                                "size": "sm",
                                "wrap": True
                            }
                        ],
                        "marginBottom": "md"
                    })
                
                messages.append(product_flex)
                
                # Add link to all products
                messages.append({
                    "type": "text",
                    "text": "ดูรายการสินค้าทั้งหมดได้ที่:\nhttps://www.icpladda.com/product-category/%E0%B8%AA%E0%B8%B4%E0%B8%99%E0%B8%84%E0%B9%89%E0%B8%B2%E0%B8%97%E0%B8%B1%E0%B9%89%E0%B8%87%E0%B8%AB%E0%B8%A1%E0%B8%94/"
                })
            
            return messages
            
        except Exception as e:
            logger.error(f"Response formatting failed: {str(e)}")
            return [{
                "type": "text",
                "text": "ขออภัยค่ะ เกิดข้อผิดพลาดในการแสดงผล กรุณาลองใหม่อีกครั้ง"
            }]

    async def __call__(self, message: Dict) -> Dict:
        """Process message in graph"""
        if "vision_result" not in message or "products" not in message:
            return {"error": "Missing required data"}
            
        messages = await self.format_response(
            message["vision_result"],
            message["products"]
        )
        
        return {
            "vision_result": message["vision_result"],
            "products": message["products"],
            "line_messages": messages
        }