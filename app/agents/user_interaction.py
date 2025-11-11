"""
User interaction agent that handles conversations with users
"""
from typing import Any, Dict, List, Optional
from .base_agent import BaseAgent

class UserInteractionAgent(BaseAgent):
    def __init__(self):
        super().__init__("UserInteraction")
    
    async def can_handle(self, data: Dict[str, Any]) -> bool:
        return "message" in data or "question" in data
    
    async def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process user messages and generate appropriate responses
        """
        try:
            if "analysis_result" in data:
                # Generate follow-up questions based on image analysis
                questions = self._generate_followup_questions(data["analysis_result"])
                return {
                    "response_type": "questions",
                    "questions": questions,
                    "success": True
                }
            elif "message" in data:
                # Process user's text response
                processed_response = self._process_user_response(data["message"])
                return {
                    "response_type": "message",
                    "processed_data": processed_response,
                    "success": True
                }
            
            return {
                "error": "No valid input found",
                "success": False
            }
            
        except Exception as e:
            return {
                "error": f"User interaction failed: {str(e)}",
                "success": False
            }
    
    def _generate_followup_questions(self, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Generate relevant follow-up questions based on image analysis
        Returns a list of questions with their categories and priorities
        """
        questions = [
            {
                "category": "timeline",
                "priority": 1,
                "question": "คุณสังเกตเห็นอาการนี้มานานแค่ไหนแล้วครับ?",
                "choices": ["1-3 วัน", "4-7 วัน", "มากกว่า 1 สัปดาห์", "มากกว่า 1 เดือน"]
            },
            {
                "category": "treatment_history",
                "priority": 2,
                "question": "มีการใช้ยาหรือสารเคมีอะไรไปแล้วบ้างไหมครับ?",
                "detail_required": True
            },
            {
                "category": "environment",
                "priority": 3,
                "question": "สภาพแวดล้อมการปลูกเป็นอย่างไรบ้างครับ?",
                "sub_questions": [
                    "พืชที่ปลูกอยู่ในที่ร่มหรือกลางแจ้ง?",
                    "ความชื้นในพื้นที่เป็นอย่างไร?",
                    "มีการให้น้ำบ่อยแค่ไหน?"
                ]
            },
            {
                "category": "spread",
                "priority": 4,
                "question": "การระบาดของโรค/แมลง",
                "sub_questions": [
                    "มีพืชต้นอื่นๆ ที่แสดงอาการคล้ายกันหรือไม่?",
                    "อาการเริ่มจากส่วนไหนของพืชก่อน?",
                    "การระบาดเป็นวงกว้างหรือเฉพาะจุด?"
                ]
            },
            {
                "category": "plant_details",
                "priority": 5,
                "question": "ข้อมูลเพิ่มเติมเกี่ยวกับพืช",
                "sub_questions": [
                    "พืชนี้อายุเท่าไหร่แล้ว?",
                    "ปลูกในดินหรือในกระถาง?",
                    "มีการใส่ปุ๋ยอะไรบ้าง?"
                ]
            }
        ]
        
        # ปรับคำถามตามผลการวิเคราะห์
        if "analysis" in analysis:
            analysis_text = analysis["analysis"].lower()
            # ถ้าพบเกี่ยวกับเชื้อรา เพิ่มคำถามเกี่ยวกับความชื้น
            if "เชื้อรา" in analysis_text or "ราน้ำค้าง" in analysis_text:
                questions.append({
                    "category": "fungus_specific",
                    "priority": 2,
                    "question": "เกี่ยวกับความชื้น",
                    "sub_questions": [
                        "พื้นที่มีอากาศถ่ายเทดีหรือไม่?",
                        "มีน้ำขังบริเวณโคนต้นหรือไม่?",
                        "ช่วงนี้มีฝนตกบ่อยไหม?"
                    ]
                })
            # ถ้าพบเกี่ยวกับแมลง เพิ่มคำถามเกี่ยวกับการระบาด
            elif "แมลง" in analysis_text or "หนอน" in analysis_text or "เพลี้ย" in analysis_text:
                questions.append({
                    "category": "pest_specific",
                    "priority": 2,
                    "question": "เกี่ยวกับแมลง",
                    "sub_questions": [
                        "พบแมลงในช่วงเวลาใดมากที่สุด?",
                        "เคยมีการระบาดในพื้นที่ใกล้เคียงหรือไม่?",
                        "มีการใช้กับดักแมลงหรือไม่?"
                    ]
                })
        
        # เรียงลำดับตาม priority
        return sorted(questions, key=lambda x: x["priority"])
    
    def _process_user_response(self, message: str) -> Dict[str, Any]:
        """
        Process user's text response and extract relevant information
        """
        # Add your text processing logic here
        return {
            "original_message": message,
            "processed_info": {},
            "requires_followup": False
        }