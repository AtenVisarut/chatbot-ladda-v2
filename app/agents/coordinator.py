"""
Agent coordinator that manages communication between agents
"""
from typing import Any, Dict, List, Optional
from .base_agent import BaseAgent
from .image_analyzer import ImageAnalyzerAgent
from .user_interaction import UserInteractionAgent
from .product_recommender import ProductRecommenderAgent
import logging

logger = logging.getLogger(__name__)

class AgentCoordinator:
    def __init__(self):
        self.agents = {
            "image_analyzer": ImageAnalyzerAgent(),
            "user_interaction": UserInteractionAgent(),
            "product_recommender": ProductRecommenderAgent()
        }
    
    async def process_request(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Coordinate the processing of a request through multiple agents
        """
        try:
            result = {}
            
            # Step 1: Image Analysis
            if await self.agents["image_analyzer"].can_handle(data):
                analysis_result = await self.agents["image_analyzer"].process(data)
                result["analysis"] = analysis_result
                
                if not analysis_result.get("success", False):
                    return {
                        "error": "Image analysis failed",
                        "details": analysis_result.get("error", "Unknown error")
                    }
            
            # Step 2: User Interaction
            user_data = {**data, "analysis_result": result.get("analysis")}
            if await self.agents["user_interaction"].can_handle(user_data):
                interaction_result = await self.agents["user_interaction"].process(user_data)
                result["interaction"] = interaction_result
            
            # Step 3: Product Recommendation
            if "user_response" in data or result.get("analysis"):
                recommendation_data = {
                    **data,
                    "analysis_result": result.get("analysis"),
                    "user_interaction": result.get("interaction")
                }
                
                if await self.agents["product_recommender"].can_handle(recommendation_data):
                    recommendations = await self.agents["product_recommender"].process(recommendation_data)
                    result["recommendations"] = recommendations
            
            return {
                "success": True,
                "results": result
            }
            
        except Exception as e:
            logger.error(f"Agent coordination failed: {str(e)}")
            return {
                "success": False,
                "error": f"Agent coordination failed: {str(e)}"
            }
    
    def format_response(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format the final response for LINE messaging with rich format
        Returns a dictionary containing different message types for LINE Messaging API
        """
        if not results.get("success", False):
            return {
                "type": "error",
                "messages": [{
                    "type": "text",
                    "text": "ขออภัยค่ะ เกิดข้อผิดพลาดในการประมวลผล กรุณาลองใหม่อีกครั้ง"
                }]
            }
        
        messages = []
        
        # Add analysis results with emoji indicators
        if "analysis" in results.get("results", {}):
            analysis = results["results"]["analysis"]
            messages.append({
                "type": "text",
                "text": f"🔍 ผลการวิเคราะห์:\n{analysis.get('analysis', '')}"
            })
        
        # Add follow-up questions in carousel format
        if "interaction" in results.get("results", {}):
            questions = results["results"]["interaction"].get("questions", [])
            if questions:
                question_bubbles = []
                for q in questions:
                    bubble = {
                        "type": "bubble",
                        "header": {
                            "type": "box",
                            "layout": "vertical",
                            "contents": [{
                                "type": "text",
                                "text": f"❓ {q['category'].title()}",
                                "weight": "bold"
                            }]
                        },
                        "body": {
                            "type": "box",
                            "layout": "vertical",
                            "contents": [{
                                "type": "text",
                                "text": q["question"],
                                "wrap": True
                            }]
                        }
                    }
                    
                    # Add choices if available
                    if "choices" in q:
                        choices = []
                        for choice in q["choices"]:
                            choices.append({
                                "type": "button",
                                "action": {
                                    "type": "message",
                                    "label": choice,
                                    "text": choice
                                },
                                "style": "primary"
                            })
                        bubble["footer"] = {
                            "type": "box",
                            "layout": "vertical",
                            "contents": choices
                        }
                    
                    # Add sub-questions if available
                    if "sub_questions" in q:
                        sub_q_contents = []
                        for sub_q in q["sub_questions"]:
                            sub_q_contents.append({
                                "type": "text",
                                "text": f"• {sub_q}",
                                "size": "sm",
                                "wrap": True
                            })
                        bubble["body"]["contents"].extend(sub_q_contents)
                    
                    question_bubbles.append(bubble)
                
                messages.append({
                    "type": "flex",
                    "altText": "คำถามเพิ่มเติม",
                    "contents": {
                        "type": "carousel",
                        "contents": question_bubbles
                    }
                })
        
        # Add product recommendations in flex message
        if "recommendations" in results.get("results", {}):
            products = results["results"]["recommendations"].get("recommendations", [])
            if products:
                product_bubbles = []
                for p in products[:3]:  # Show top 3 products
                    bubble = {
                        "type": "bubble",
                        "header": {
                            "type": "box",
                            "layout": "vertical",
                            "contents": [{
                                "type": "text",
                                "text": "🛍️ สินค้าแนะนำ",
                                "weight": "bold"
                            }]
                        },
                        "body": {
                            "type": "box",
                            "layout": "vertical",
                            "contents": [
                                {
                                    "type": "text",
                                    "text": p.get("name", ""),
                                    "weight": "bold",
                                    "wrap": True
                                },
                                {
                                    "type": "text",
                                    "text": p.get("description", ""),
                                    "size": "sm",
                                    "wrap": True
                                },
                                {
                                    "type": "box",
                                    "layout": "horizontal",
                                    "contents": [
                                        {
                                            "type": "text",
                                            "text": "💊 สารสำคัญ:",
                                            "size": "sm"
                                        },
                                        {
                                            "type": "text",
                                            "text": p.get("active_ingredients", ""),
                                            "size": "sm",
                                            "wrap": True
                                        }
                                    ]
                                }
                            ]
                        },
                        "footer": {
                            "type": "box",
                            "layout": "vertical",
                            "contents": [{
                                "type": "button",
                                "action": {
                                    "type": "uri",
                                    "label": "ดูรายละเอียด",
                                    "uri": p.get("url", "https://example.com")
                                },
                                "style": "primary"
                            }]
                        }
                    }
                    product_bubbles.append(bubble)
                
                messages.append({
                    "type": "flex",
                    "altText": "สินค้าแนะนำ",
                    "contents": {
                        "type": "carousel",
                        "contents": product_bubbles
                    }
                })
        
        return {
            "type": "success",
            "messages": messages
        }