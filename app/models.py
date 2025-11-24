from typing import Optional
from pydantic import BaseModel

class DiseaseDetectionResult(BaseModel):
    disease_name: str
    confidence: str
    symptoms: str
    severity: str
    raw_analysis: str

class ProductRecommendation(BaseModel):
    product_name: str
    active_ingredient: Optional[str] = ""
    target_pest: Optional[str] = ""
    applicable_crops: Optional[str] = ""
    how_to_use: Optional[str] = ""
    usage_period: Optional[str] = ""
    usage_rate: Optional[str] = ""
    score: float = 0.0
