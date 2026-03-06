"""
Response Template Builder
Builds detailed disease response using templates (NO AI generation)
Reduces token usage by 85-90%
"""

import logging
from typing import List, Dict, Optional
from app.models import DiseaseDetectionResult, ProductRecommendation

logger = logging.getLogger(__name__)


def calculate_severity_score(disease_info: DiseaseDetectionResult) -> int:
    """
    Calculate severity score 0-100 based on disease info
    
    Args:
        disease_info: Disease detection result
        
    Returns:
        Severity score (0-100)
    """
    score = 50  # Default medium severity
    
    severity_text = disease_info.severity.lower()
    
    # Map severity text to score
    if "รุนแรง" in severity_text or "severe" in severity_text:
        score = 85
    elif "ปานกลาง" in severity_text or "moderate" in severity_text:
        score = 60
    elif "เล็กน้อย" in severity_text or "mild" in severity_text or "ต่ำ" in severity_text:
        score = 35
    elif "ไม่พบ" in severity_text or "no" in severity_text:
        score = 0
    
    # Adjust based on confidence
    confidence_text = disease_info.confidence.lower()
    if "สูง" in confidence_text or "high" in confidence_text or any(char.isdigit() for char in confidence_text):
        # Extract number if present
        try:
            import re
            numbers = re.findall(r'\d+', confidence_text)
            if numbers:
                conf_num = int(numbers[0])
                if conf_num > 70:
                    # High confidence, use score as is
                    pass
                elif conf_num < 50:
                    # Low confidence, reduce score slightly
                    score = max(0, score - 10)
        except:
            pass
    elif "ต่ำ" in confidence_text or "low" in confidence_text:
        score = max(0, score - 15)
    
    return min(100, max(0, score))


def build_detailed_response(
    disease_info: DiseaseDetectionResult,
    knowledge: str,
    products: List[ProductRecommendation],
    extra_user_info: Optional[str] = None
) -> str:
    """
    Build detailed response using template (NO AI tokens used)
    
    Format matches reference image with sections:
    - ผลตรวจจากภาพ
    - ระดับความรุนแรง
    - ความเชื่อมั่น
    - อาการที่พบ
    - ความรู้เพิ่มเติม
    - สินค้าแนะนำ
    - หมายเหตุสำคัญ
    
    Args:
        disease_info: Disease detection result from vision model
        knowledge: Knowledge from vector search
        products: Product recommendations from vector search
        extra_user_info: Additional info from user
        
    Returns:
        Formatted response string
    """
    try:
        # Calculate severity score
        severity_score = calculate_severity_score(disease_info)
        
        # Build header section
        response = f"""🔍 ผลตรวจจากภาพ: {disease_info.disease_name}
🟢 ระดับความรุนแรง: {severity_score}
📊 ความเชื่อมั่น: {disease_info.confidence}

🌿 อาการที่พบ:
{disease_info.symptoms}"""
        
        # Add user provided info if available
        if extra_user_info:
            response += f"\n\n📝 ข้อมูลเพิ่มเติมจากคุณ:\n{extra_user_info}"
        
        # Add knowledge section if available
        if knowledge and knowledge.strip():
            response += f"\n\n🌱 ความรู้เพิ่มเติม:\n{knowledge[:500]}"  # Limit length
        
        # Add product recommendations
        if products and len(products) > 0:
            response += "\n\n💊 สินค้าแนะนำ:\n"
            
            for idx, product in enumerate(products[:5], 1):  # Top 5 products
                response += f"\n{idx}. {product.product_name}"
                
                # สารสำคัญ
                if product.active_ingredient:
                    response += f"\n   • สารสำคัญ: {product.active_ingredient}"
                
                # ศัตรูพืชที่กำจัดได้ (แยกตามประเภท)
                from app.utils.pest_columns import get_pest_display, PEST_COLUMNS
                _pest_dict = {col: getattr(product, col, '') or '' for col in PEST_COLUMNS}
                _pest_disp = get_pest_display(_pest_dict, max_len=150)
                if _pest_disp:
                    for _line in _pest_disp.split('\n'):
                        response += f"\n   • {_line}"
                
                # วิธีใช้
                if product.how_to_use:
                    how_to = product.how_to_use[:200]
                    if len(product.how_to_use) > 200:
                        how_to += "..."
                    response += f"\n   • วิธีใช้: {how_to}"
                
                # อัตราการใช้
                if product.usage_rate:
                    response += f"\n   • อัตราการใช้: {product.usage_rate}"
                
                # ช่วงการใช้
                if product.usage_period:
                    response += f"\n   • ช่วงการใช้: {product.usage_period}"
                
                # ใช้ได้กับพืช
                if product.applicable_crops:
                    crops = product.applicable_crops[:150]
                    if len(product.applicable_crops) > 150:
                        crops += "..."
                    response += f"\n   • ใช้ได้กับพืช: {crops}"
                
                # ความเข้ากันได้
                if hasattr(product, 'score') and product.score:
                    compatibility = int(product.score * 100)
                    response += f"\n   • ความเข้ากันได้: {compatibility}%"
                
                response += "\n"
        else:
            response += "\n\n💊 สินค้าแนะนำ:\nไม่พบผลิตภัณฑ์ที่เหมาะสมในฐานข้อมูล กรุณาปรึกษาผู้เชี่ยวชาญ\n"
        
        # Add important notes (replace control measures)
        response += "\n📋 **\"หมายเหตุสำคัญ\"**:"
        response += "\n✅ ปรับปรุงระบบการระบายอากาศให้ดี"
        response += "\n✅ ควบคุมการใช้ปุ๋ยไนโตรเจนให้เหมาะสม"
        response += "\n✅ ทำความสะอาดพื้นที่ปลูกและเศษซากพืช"
        
        logger.info(f"✓ Built response template for {disease_info.disease_name}")
        
        return response
        
    except Exception as e:
        logger.error(f"Error building response template: {e}", exc_info=True)
        # Fallback: simple response
        return f"""🔍 ผลตรวจ: {disease_info.disease_name}
📊 ความเชื่อมั่น: {disease_info.confidence}

🌿 อาการ: {disease_info.symptoms}

⚠️ กรุณาปรึกษาผู้เชี่ยวชาญเพื่อการวินิจฉัยที่แม่นยำ"""


def build_simple_response(disease_info: DiseaseDetectionResult) -> str:
    """
    Build minimal response for when data is unavailable
    
    Args:
        disease_info: Disease detection result
        
    Returns:
        Simple formatted response
    """
    severity_score = calculate_severity_score(disease_info)
    
    return f"""🔍 ผลตรวจจากภาพ: {disease_info.disease_name}
🟢 ระดับความรุนแรง: {severity_score}
📊 ความเชื่อมั่น: {disease_info.confidence}

🌿 อาการที่พบ:
{disease_info.symptoms}

⚠️ ไม่สามารถโหลดข้อมูลเพิ่มเติมได้ในขณะนี้
กรุณาปรึกษาผู้เชี่ยวชาญด้านโรคพืช"""
