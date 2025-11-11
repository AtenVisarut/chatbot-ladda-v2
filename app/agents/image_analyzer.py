"""
Image analysis agent that handles image processing and disease detection
"""
from typing import Any, Dict, Optional
from .base_agent import BaseAgent
from openai import OpenAI
import os

class ImageAnalyzerAgent(BaseAgent):
    def __init__(self):
        super().__init__("ImageAnalyzer")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    async def can_handle(self, data: Dict[str, Any]) -> bool:
        return "image_url" in data or "image_content" in data
    
    async def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze image using OpenAI Vision API
        """
        try:
            if "image_content" in data:
                image = data["image_content"]
            else:
                # Download image from URL if needed
                image = data["image_url"]
            
            response = self.client.chat.completions.create(
                model="gpt-4-vision-preview",
                messages=[
                    {
                        "role": "system",
                        "content": "คุณเป็นผู้เชี่ยวชาญในการวินิจฉัยโรคพืช วิเคราะห์ภาพและให้คำแนะนำเกี่ยวกับปัญหาของพืช"
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "วิเคราะห์ภาพนี้และบอกว่าพืชมีปัญหาอะไร มีลักษณะอาการอย่างไร"
                            },
                            {
                                "type": "image_url",
                                "image_url": image
                            }
                        ]
                    }
                ],
                max_tokens=500
            )
            
            return {
                "analysis": response.choices[0].message.content,
                "confidence": 0.95,  # Example confidence score
                "detected_issues": []  # List of detected issues/diseases
            }
            
        except Exception as e:
            return {
                "error": f"Image analysis failed: {str(e)}",
                "success": False
            }