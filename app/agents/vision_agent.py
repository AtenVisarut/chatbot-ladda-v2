"""
Vision Agent: Handles image analysis using OpenAI Vision API
"""
from typing import Dict, Any
from langgraph.graph import MessageGraph
from pydantic import BaseModel, Field

class VisionAgent(BaseModel):
    """Agent for analyzing plant images using OpenAI Vision"""
    
    openai_client: Any = Field(description="OpenAI client instance")
    
    async def analyze(self, image_url: str) -> Dict[str, Any]:
        """Analyze image using OpenAI Vision"""
        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-4-vision-preview",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Analyze this plant image for diseases or pests. Return structured JSON with these fields: disease_name (Thai), pest_type, confidence_level_percent, confidence (สูง/ปานกลาง/ต่ำ), symptoms_in_image, symptoms, possible_cause, severity_level, severity, description. All text fields should be in Thai."},
                        {"type": "image_url", "image_url": image_url}
                    ]
                }],
                max_tokens=1000
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            raise Exception(f"Vision analysis failed: {str(e)}")

    def __call__(self, message: Dict) -> Dict:
        """Process message in graph"""
        if "image_url" not in message:
            return {"error": "No image URL provided"}
            
        result = await self.analyze(message["image_url"])
        return {"vision_result": result}