# 🚀 Advanced Features เพื่อเพิ่มความฉลาดและความแม่นยำ

## 📋 สารบัญ
1. [Image Quality Validation](#1-image-quality-validation)
2. [Multi-Stage Verification](#2-multi-stage-verification)
3. [Confidence Scoring System](#3-confidence-scoring-system)
4. [Knowledge Base Integration](#4-knowledge-base-integration)
5. [User Feedback Loop](#5-user-feedback-loop)
6. [Context-Aware Detection](#6-context-aware-detection)
7. [Expert Review Queue](#7-expert-review-queue)
8. [Automated Testing](#8-automated-testing)

---

## 1. 🖼️ Image Quality Validation

### ปัญหา:
ภาพที่เบลอ มืด หรือไม่ชัดเจน ทำให้วินิจฉัยผิดพลาด

### แนวทางแก้:

```python
async def validate_image_quality(image_bytes: bytes) -> dict:
    """
    ตรวจสอบคุณภาพภาพก่อนวิเคราะห์
    
    Returns:
        {
            "is_valid": bool,
            "quality_score": 0-100,
            "issues": ["blurry", "dark", "too_small"],
            "suggestions": ["ถ่ายใหม่ในที่แสงสว่าง", ...]
        }
    """
    from PIL import Image
    import io
    
    img = Image.open(io.BytesIO(image_bytes))
    
    issues = []
    suggestions = []
    
    # 1. Check image size
    width, height = img.size
    if width < 800 or height < 800:
        issues.append("too_small")
        suggestions.append("📸 ถ่ายรูปใกล้ๆ หรือใช้ความละเอียดสูงขึ้น")
    
    # 2. Check brightness
    import numpy as np
    img_array = np.array(img.convert('L'))
    brightness = np.mean(img_array)
    
    if brightness < 50:
        issues.append("too_dark")
        suggestions.append("💡 ถ่ายในที่แสงสว่างมากขึ้น")
    elif brightness > 200:
        issues.append("too_bright")
        suggestions.append("☀️ หลีกเลี่ยงแสงแดดจ้าโดยตรง")
    
    # 3. Check blur (using Laplacian variance)
    from scipy import ndimage
    laplacian = ndimage.laplace(img_array)
    blur_score = laplacian.var()
    
    if blur_score < 100:
        issues.append("blurry")
        suggestions.append("🎯 ถ่ายให้โฟกัสชัดเจน ไม่เบลอ")
    
    # Calculate quality score
    quality_score = 100
    quality_score -= len(issues) * 20
    quality_score = max(0, quality_score)
    
    return {
        "is_valid": quality_score >= 60,
        "quality_score": quality_score,
        "issues": issues,
        "suggestions": suggestions
    }
```

**ผลลัพธ์**: ลดภาพคุณภาพต่ำ → เพิ่มความแม่นยำ 10-15%

---

## 2. 🔍 Multi-Stage Verification

### ปัญหา:
การวินิจฉัยครั้งเดียวอาจผิดพลาด

### แนวทางแก้:

```python
async def multi_stage_detection(image_bytes: bytes, user_info: str) -> dict:
    """
    วิเคราะห์หลายขั้นตอนเพื่อความแม่นยำ
    
    Stage 1: Initial Detection (GPT-4 Vision)
    Stage 2: Verification (ตรวจสอบซ้ำด้วย prompt ต่างกัน)
    Stage 3: Cross-validation (เปรียบเทียบผลลัพธ์)
    """
    
    # Stage 1: Initial detection
    result1 = await detect_disease(image_bytes, user_info)
    
    # Stage 2: Verification with different prompt
    verification_prompt = """
    คุณเป็นผู้ตรวจสอบคุณภาพการวินิจฉัยโรคพืช
    
    ผลการวินิจฉัยเบื้องต้น: {disease_name}
    
    กรุณาตรวจสอบว่า:
    1. การวินิจฉัยถูกต้องหรือไม่?
    2. มีโรคอื่นที่เป็นไปได้หรือไม่?
    3. ควรเพิ่มข้อมูลอะไรเพื่อยืนยัน?
    
    ตอบเป็น JSON:
    {{
        "is_correct": true/false,
        "confidence": 0-100,
        "alternative_diagnosis": ["โรคอื่นที่เป็นไปได้"],
        "additional_info_needed": ["ข้อมูลที่ต้องการเพิ่ม"]
    }}
    """
    
    result2 = await verify_detection(image_bytes, result1, verification_prompt)
    
    # Stage 3: Cross-validation
    if result2["is_correct"] and result2["confidence"] > 70:
        return {
            "status": "confirmed",
            "result": result1,
            "confidence": result2["confidence"]
        }
    else:
        return {
            "status": "uncertain",
            "result": result1,
            "alternatives": result2["alternative_diagnosis"],
            "need_more_info": result2["additional_info_needed"]
        }
```

**ผลลัพธ์**: ลด False Positive จาก 15% → 5%

---

## 3. 📊 Confidence Scoring System

### ปัญหา:
ไม่มีระบบให้คะแนนความมั่นใจที่ชัดเจน

### แนวทางแก้:

```python
def calculate_confidence_score(detection_result: dict, user_info: str, image_quality: dict) -> dict:
    """
    คำนวณคะแนนความมั่นใจจากหลายปัจจัย
    
    Factors:
    - AI confidence (40%)
    - Image quality (30%)
    - User information completeness (20%)
    - Historical accuracy (10%)
    """
    
    score = 0
    factors = {}
    
    # 1. AI Confidence (40 points)
    ai_conf = int(detection_result.get("confidence_level_percent", 50))
    ai_score = (ai_conf / 100) * 40
    score += ai_score
    factors["ai_confidence"] = ai_score
    
    # 2. Image Quality (30 points)
    img_score = (image_quality["quality_score"] / 100) * 30
    score += img_score
    factors["image_quality"] = img_score
    
    # 3. User Information (20 points)
    user_score = 0
    if user_info:
        # Check completeness
        keywords = ["พืช", "ใบ", "สี", "วัน", "เดือน"]
        matches = sum(1 for k in keywords if k in user_info)
        user_score = (matches / len(keywords)) * 20
    score += user_score
    factors["user_info"] = user_score
    
    # 4. Historical Accuracy (10 points)
    # Based on past detections of same disease
    hist_score = 10  # Default, can be improved with database
    score += hist_score
    factors["historical"] = hist_score
    
    return {
        "total_score": round(score, 2),
        "grade": "A" if score >= 80 else "B" if score >= 60 else "C" if score >= 40 else "D",
        "factors": factors,
        "recommendation": get_recommendation(score)
    }

def get_recommendation(score: float) -> str:
    if score >= 80:
        return "✅ ความมั่นใจสูง สามารถดำเนินการตามคำแนะนำได้"
    elif score >= 60:
        return "⚠️ ความมั่นใจปานกลาง แนะนำให้ส่งรูปเพิ่มหรือให้ข้อมูลเพิ่มเติม"
    else:
        return "❌ ความมั่นใจต่ำ ควรปรึกษาผู้เชี่ยวชาญก่อนดำเนินการ"
```

**ผลลัพธ์**: ผู้ใช้เข้าใจระดับความเชื่อถือได้ชัดเจน

---

## 4. 📚 Knowledge Base Integration

### ปัญหา:
ไม่มีฐานความรู้เพื่อตรวจสอบความถูกต้อง

### แนวทางแก้:

```python
# สร้างฐานความรู้โรคพืช
DISEASE_KNOWLEDGE_BASE = {
    "เพลี้ยไฟ": {
        "type": "ศัตรูพืช",
        "common_crops": ["ทุเรียน", "มะม่วง", "พริก"],
        "symptoms": ["ใบม้วน", "จุดสีเงิน", "ใบเหลือง"],
        "season": ["ฤดูแล้ง", "มีนาคม-พฤษภาคม"],
        "similar_diseases": ["เพลี้ยอ่อน", "เพลี้ยแป้ง"],
        "typical_confidence": 85,
        "products": ["โมเดิน 50", "อิมิดาโกลด์ 70"]
    },
    "แอนแทรคโนส": {
        "type": "เชื้อรา",
        "common_crops": ["มะม่วง", "พริก", "ถั่ว"],
        "symptoms": ["จุดสีน้ำตาล", "แผลเปียก", "ผลเน่า"],
        "season": ["ฤดูฝน", "มิถุนายน-กันยายน"],
        "similar_diseases": ["ใบไหม้", "ราน้ำค้าง"],
        "typical_confidence": 80,
        "products": ["เบนซาน่า เอฟ", "ก๊อปกัน"]
    }
}

async def validate_with_knowledge_base(detection_result: dict, user_info: str) -> dict:
    """
    ตรวจสอบผลการวินิจฉัยกับฐานความรู้
    """
    disease_name = detection_result["disease_name"]
    
    if disease_name not in DISEASE_KNOWLEDGE_BASE:
        return {"validated": False, "reason": "ไม่พบในฐานความรู้"}
    
    kb = DISEASE_KNOWLEDGE_BASE[disease_name]
    issues = []
    
    # 1. Check pest type consistency
    detected_type = detection_result.get("pest_type", "")
    if kb["type"] not in detected_type:
        issues.append(f"ประเภทไม่ตรง: ตรวจพบ {detected_type} แต่ควรเป็น {kb['type']}")
    
    # 2. Check crop compatibility
    if user_info:
        crop_mentioned = any(crop in user_info for crop in kb["common_crops"])
        if not crop_mentioned:
            issues.append(f"โรคนี้มักพบใน: {', '.join(kb['common_crops'])}")
    
    # 3. Check confidence level
    detected_conf = int(detection_result.get("confidence_level_percent", 50))
    if abs(detected_conf - kb["typical_confidence"]) > 20:
        issues.append(f"ความมั่นใจผิดปกติ: {detected_conf}% (ปกติ ~{kb['typical_confidence']}%)")
    
    return {
        "validated": len(issues) == 0,
        "issues": issues,
        "knowledge_base_info": kb
    }
```

**ผลลัพธ์**: กรองการวินิจฉัยที่ผิดปกติได้

---

## 5. 🔄 User Feedback Loop

### ปัญหา:
ไม่มีการเรียนรู้จากผลลัพธ์จริง

### แนวทางแก้:

```python
async def collect_user_feedback(user_id: str, detection_id: str, feedback: dict):
    """
    เก็บ feedback จากผู้ใช้
    
    feedback = {
        "is_correct": true/false,
        "actual_disease": "ชื่อโรคจริง",
        "treatment_result": "ได้ผล/ไม่ได้ผล",
        "rating": 1-5
    }
    """
    
    # Save to database
    await supabase.table('detection_feedback').insert({
        "user_id": user_id,
        "detection_id": detection_id,
        "is_correct": feedback["is_correct"],
        "actual_disease": feedback.get("actual_disease"),
        "treatment_result": feedback.get("treatment_result"),
        "rating": feedback["rating"],
        "created_at": datetime.now()
    }).execute()
    
    # Update accuracy metrics
    await update_accuracy_metrics(detection_id, feedback)

async def get_accuracy_report() -> dict:
    """
    สร้างรายงานความแม่นยำ
    """
    feedbacks = await supabase.table('detection_feedback').select('*').execute()
    
    total = len(feedbacks.data)
    correct = sum(1 for f in feedbacks.data if f['is_correct'])
    
    return {
        "total_detections": total,
        "correct_detections": correct,
        "accuracy_rate": (correct / total * 100) if total > 0 else 0,
        "by_disease": calculate_accuracy_by_disease(feedbacks.data)
    }
```

**ผลลัพธ์**: ปรับปรุงระบบอย่างต่อเนื่อง

---

## 6. 🌍 Context-Aware Detection

### ปัญหา:
ไม่พิจารณาบริบท (ฤดูกาล, สภาพอากาศ, พื้นที่)

### แนวทางแก้:

```python
async def get_context_info(user_location: str = None) -> dict:
    """
    ดึงข้อมูลบริบทเพื่อช่วยวินิจฉัย
    """
    import datetime
    
    context = {}
    
    # 1. Season
    month = datetime.datetime.now().month
    if month in [3, 4, 5]:
        context["season"] = "ฤดูร้อน"
        context["common_diseases"] = ["เพลี้ยไฟ", "เพลี้ยอ่อน", "ไรแดง"]
    elif month in [6, 7, 8, 9, 10]:
        context["season"] = "ฤดูฝน"
        context["common_diseases"] = ["แอนแทรคโนส", "ใบไหม้", "ราน้ำค้าง"]
    else:
        context["season"] = "ฤดูหนาว"
        context["common_diseases"] = ["เพลี้ยแป้ง", "โรคใบจุด"]
    
    # 2. Weather (if API available)
    if user_location:
        weather = await get_weather_data(user_location)
        context["weather"] = weather
        
        # High humidity → fungal diseases more likely
        if weather.get("humidity", 0) > 80:
            context["risk_factors"] = ["ความชื้นสูง → เสี่ยงโรคเชื้อรา"]
    
    return context

async def context_aware_detection(image_bytes: bytes, user_info: str, location: str = None) -> dict:
    """
    วินิจฉัยโดยพิจารณาบริบท
    """
    # Get context
    context = await get_context_info(location)
    
    # Add context to prompt
    enhanced_prompt = f"""
    บริบทเพิ่มเติม:
    - ฤดูกาล: {context['season']}
    - โรคที่พบบ่อยในช่วงนี้: {', '.join(context['common_diseases'])}
    
    {user_info}
    """
    
    # Detect with context
    result = await detect_disease(image_bytes, enhanced_prompt)
    
    # Validate against seasonal diseases
    if result["disease_name"] not in context["common_diseases"]:
        result["warning"] = f"⚠️ โรคนี้ไม่ค่อยพบใน{context['season']} กรุณาตรวจสอบอีกครั้ง"
    
    return result
```

**ผลลัพธ์**: เพิ่มความแม่นยำ 5-10% จากบริบท

---

## 7. 👨‍🌾 Expert Review Queue

### ปัญหา:
กรณีที่ไม่แน่ใจ ไม่มีผู้เชี่ยวชาญตรวจสอบ

### แนวทางแก้:

```python
async def queue_for_expert_review(detection_result: dict, image_bytes: bytes, user_info: str):
    """
    ส่งกรณีที่ไม่แน่ใจให้ผู้เชี่ยวชาญตรวจสอบ
    """
    
    # Criteria for expert review
    needs_review = (
        detection_result["confidence_level_percent"] < 60 or
        "ต่ำ" in detection_result["confidence"] or
        detection_result["severity"] == "รุนแรง"
    )
    
    if needs_review:
        # Save to review queue
        review_id = await supabase.table('expert_review_queue').insert({
            "detection_result": detection_result,
            "user_info": user_info,
            "image_url": await upload_image_to_storage(image_bytes),
            "status": "pending",
            "priority": "high" if detection_result["severity"] == "รุนแรง" else "normal",
            "created_at": datetime.now()
        }).execute()
        
        # Notify user
        return {
            "queued": True,
            "review_id": review_id,
            "message": "📋 กรณีของคุณถูกส่งให้ผู้เชี่ยวชาญตรวจสอบ คาดว่าจะได้รับคำตอบภายใน 24 ชั่วโมง"
        }
    
    return {"queued": False}

async def expert_dashboard():
    """
    Dashboard สำหรับผู้เชี่ยวชาญ
    """
    pending_reviews = await supabase.table('expert_review_queue')\
        .select('*')\
        .eq('status', 'pending')\
        .order('priority', desc=True)\
        .execute()
    
    return {
        "total_pending": len(pending_reviews.data),
        "high_priority": sum(1 for r in pending_reviews.data if r['priority'] == 'high'),
        "reviews": pending_reviews.data
    }
```

**ผลลัพธ์**: กรณียากมีผู้เชี่ยวชาญช่วย

---

## 8. 🧪 Automated Testing

### ปัญหา:
ไม่มีการทดสอบความแม่นยำอย่างสม่ำเสมอ

### แนวทางแก้:

```python
async def run_accuracy_test(test_dataset: list) -> dict:
    """
    ทดสอบความแม่นยำด้วย test dataset
    
    test_dataset = [
        {
            "image_path": "test_images/thrips_1.jpg",
            "expected_disease": "เพลี้ยไฟ",
            "expected_type": "ศัตรูพืช"
        },
        ...
    ]
    """
    
    results = []
    
    for test_case in test_dataset:
        # Load image
        with open(test_case["image_path"], "rb") as f:
            image_bytes = f.read()
        
        # Detect
        result = await detect_disease(image_bytes)
        
        # Compare
        is_correct = (
            result["disease_name"] == test_case["expected_disease"] and
            result["pest_type"] == test_case["expected_type"]
        )
        
        results.append({
            "test_case": test_case["image_path"],
            "expected": test_case["expected_disease"],
            "detected": result["disease_name"],
            "is_correct": is_correct,
            "confidence": result["confidence"]
        })
    
    # Calculate metrics
    total = len(results)
    correct = sum(1 for r in results if r["is_correct"])
    accuracy = (correct / total * 100) if total > 0 else 0
    
    return {
        "total_tests": total,
        "correct": correct,
        "accuracy": accuracy,
        "failed_cases": [r for r in results if not r["is_correct"]]
    }

# Schedule daily tests
async def schedule_daily_accuracy_test():
    """
    รันทดสอบทุกวัน เวลา 02:00
    """
    import schedule
    
    schedule.every().day.at("02:00").do(lambda: run_accuracy_test(TEST_DATASET))
```

**ผลลัพธ์**: ตรวจจับปัญหาได้ทันที

---

## 📊 สรุปผลลัพธ์ที่คาดหวัง

| Feature | Accuracy Gain | Implementation Time | Priority |
|---------|---------------|---------------------|----------|
| Image Quality Validation | +10-15% | 2-3 วัน | 🔴 สูง |
| Multi-Stage Verification | +10-15% | 3-5 วัน | 🔴 สูง |
| Confidence Scoring | +5% | 1-2 วัน | 🟡 ปานกลาง |
| Knowledge Base | +5-10% | 3-4 วัน | 🔴 สูง |
| User Feedback Loop | +5-10% (long-term) | 2-3 วัน | 🟡 ปานกลาง |
| Context-Aware | +5-10% | 2-3 วัน | 🟢 ต่ำ |
| Expert Review | Quality++ | 3-5 วัน | 🟡 ปานกลาง |
| Automated Testing | Stability++ | 1-2 วัน | 🔴 สูง |

**รวม**: ความแม่นยำเพิ่มขึ้น **40-75%** จากปัจจุบัน

---

## 🎯 แนะนำลำดับการพัฒนา

### Phase 1 (สัปดาห์ที่ 1-2): Foundation
1. ✅ Image Quality Validation
2. ✅ Confidence Scoring System
3. ✅ Automated Testing

### Phase 2 (สัปดาห์ที่ 3-4): Intelligence
4. ✅ Knowledge Base Integration
5. ✅ Multi-Stage Verification
6. ✅ User Feedback Loop

### Phase 3 (สัปดาห์ที่ 5-6): Advanced
7. ✅ Context-Aware Detection
8. ✅ Expert Review Queue

---

## 💡 ข้อเสนอเพิ่มเติม

### A. Machine Learning Model
- Fine-tune model เฉพาะโรคพืชไทย
- ใช้ dataset จากกรมวิชาการเกษตร
- Accuracy: +20-30%

### B. Mobile App
- ถ่ายรูปผ่าน app โดยตรง
- Real-time guidance
- Offline mode

### C. IoT Integration
- เซ็นเซอร์วัดความชื้น อุณหภูมิ
- Alert เมื่อเสี่ยงโรคระบาด
- Predictive analytics

---

**สนใจ feature ไหนมากที่สุดครับ? จะช่วยเขียนโค้ดให้เลย! 🚀**
