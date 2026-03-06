from typing import Optional
from pydantic import BaseModel

class DiseaseDetectionResult(BaseModel):
    disease_name: str
    confidence: str
    symptoms: str
    severity: str
    raw_analysis: str
    plant_type: Optional[str] = ""  # ชนิดพืชจากการวินิจฉัย
    category: Optional[str] = ""  # กลุ่มโรค: fungal/bacterial/viral/insect/nutrient

class ProductRecommendation(BaseModel):
    product_name: str
    active_ingredient: Optional[str] = ""
    fungicides: Optional[str] = ""
    insecticides: Optional[str] = ""
    herbicides: Optional[str] = ""
    biostimulant: Optional[str] = ""
    pgr_hormones: Optional[str] = ""
    applicable_crops: Optional[str] = ""
    how_to_use: Optional[str] = ""
    usage_period: Optional[str] = ""
    usage_rate: Optional[str] = ""
    link_product: Optional[str] = ""
    image_url: Optional[str] = ""
    score: float = 0.0
