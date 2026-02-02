import logging
import re
from typing import List, Dict, Optional, Tuple
from app.services.services import openai_client, supabase_client
from app.services.memory import add_to_memory, get_conversation_context, get_recommended_products
from app.services.knowledge_base import answer_question_with_knowledge
from app.utils.text_processing import extract_keywords_from_question, post_process_answer
from app.services.product_recommendation import recommend_products_by_intent, hybrid_search_products
from app.services.disease_search import search_diseases_by_text, build_context_from_diseases

logger = logging.getLogger(__name__)

# =============================================================================
# คำสำคัญสำหรับตรวจจับคำถามเรื่องพืช/โรคพืช/การเกษตร
# =============================================================================
AGRICULTURE_KEYWORDS = [
    # พืช
    "ข้าว", "ทุเรียน", "อ้อย", "มันสำปะหลัง", "มันสัมปะหลัง", "ยางพารา", "ปาล์ม",
    "มะม่วง", "ลำไย", "ลิ้นจี่", "เงาะ", "มังคุด", "พริก", "มะเขือเทศ", "ข้าวโพด",
    "ถั่ว", "ผัก", "ผลไม้", "กล้วย", "มะพร้าว", "ส้ม", "มะนาว", "ฝรั่ง", "ชมพู่",
    # โรค/ปัญหา
    "โรค", "โรคพืช", "ใบไหม้", "ใบเหลือง", "ใบจุด", "รากเน่า", "โคนเน่า", "ผลเน่า",
    "เชื้อรา", "แบคทีเรีย", "ไวรัส", "แมลง", "เพลี้ย", "หนอน", "ด้วง", "ศัตรูพืช",
    "ราน้ำค้าง", "ราแป้ง", "ราสนิม", "แอนแทรคโนส", "กิ่งแห้ง", "ลำต้นเน่า",
    # การเกษตรทั่วไป
    "ระยะ", "ช่วง", "ปลูก", "เก็บเกี่ยว", "ดูแล", "บำรุง", "เสี่ยง", "ป้องกัน",
    "อาการ", "สาเหตุ", "การรักษา", "วิธีแก้", "วิธีป้องกัน"
]


def is_agriculture_question(message: str) -> bool:
    """ตรวจสอบว่าเป็นคำถามเกี่ยวกับการเกษตร/พืช/โรคพืชหรือไม่"""
    message_lower = message.lower()
    for keyword in AGRICULTURE_KEYWORDS:
        if keyword in message_lower:
            return True
    return False


# =============================================================================
# Keywords สำหรับตรวจจับคำถามเกี่ยวกับสินค้า/ผลิตภัณฑ์
# =============================================================================
PRODUCT_KEYWORDS = [
    "สินค้า", "ผลิตภัณฑ์", "ยา", "ยาฆ่า", "ยากำจัด", "ยาป้องกัน",
    "ยาฆ่าแมลง", "ยาฆ่าหญ้า", "ยาฆ่าเชื้อรา", "ปุ๋ย", "ฮอร์โมน",
    "สารเคมี", "สารกำจัด", "สารป้องกัน", "ยาพ่น", "ยาฉีด",
    "แนะนำยา", "ใช้ยาอะไร", "ยาตัวไหน", "ยาอะไรดี",
    "icp", "ladda", "ไอซีพี", "ลัดดา"
]

# =============================================================================
# รายชื่อสินค้า ICP Ladda (สำหรับตรวจสอบชื่อยาในคำถาม)
# =============================================================================
ICP_PRODUCT_NAMES = {
    # ชื่อเต็ม -> ชื่อที่ใช้ค้นหา (รองรับการพิมพ์ผิด/ย่อ)
    "กะรัต": ["กะรัต", "กะรัต 35"],
    "ก็อปกัน": ["ก็อปกัน", "กอปกัน", "ท็อปกัน", "ทอปกัน"],
    "คาริสมา": ["คาริสมา", "คาริสม่า"],
    "ซิมเมอร์": ["ซิมเมอร์", "ซิมเมอ"],
    "ซีเอ็มจี": ["ซีเอ็มจี", "cmg", "ซีเอมจี"],
    "ทูโฟฟอส": ["ทูโฟฟอส", "ทูโฟ"],
    "นาแดน": ["นาแดน", "นาแดน 6 จี", "นาแดน-จี"],
    "บลูไวท์": ["บลูไวท์", "บลูไวต์"],
    "พรีดิคท์": ["พรีดิคท์", "พรีดิค", "predict"],
    "พาสนาว": ["พาสนาว", "พาสนาว์"],
    "พานาส": ["พานาส", "เลกาซี 20 + พานาส"],
    "ราเซอร์": ["ราเซอร์", "เรเซอร์"],
    "รีโนเวท": ["รีโนเวท", "รีโนเวต", "renovate"],
    "วอร์แรนต์": ["วอร์แรนต์", "วอแรนต์", "warrant"],
    "อะนิลการ์ด": ["อะนิลการ์ด", "อนิลการ์ด"],
    "อัพดาว": ["อัพดาว", "อัปดาว"],
    "อาร์ดอน": ["อาร์ดอน", "อาดอน"],
    "อาร์เทมีส": ["อาร์เทมีส", "อาเทมิส", "อาร์เทมิส", "artemis"],
    "อิมิดาโกลด์": ["อิมิดาโกลด์", "อิมิดา", "อิมิดาโกล", "imidagold", "อิมิดาโกลด์70", "อิมิดาโกลด์ 70"],
    "เกรค": ["เกรค", "เกรค 5 เอสซี"],
    "เคเซีย": ["เคเซีย", "เคเซีย์"],
    "เทอราโน่": ["เทอราโน่", "เทอราโน", "terano"],
    "เบนซาน่า": ["เบนซาน่า", "เบนซาน่า เอฟ"],
    "เมลสัน": ["เมลสัน", "เมลซัน"],
    "แกนเตอร์": ["แกนเตอร์", "แกนเตอ"],
    "แจ๊ส": ["แจ๊ส", "แจส", "jazz"],
    "แมสฟอร์ด": ["แมสฟอร์ด", "แมสฟอด"],
    "แอนดาแม็กซ์": ["แอนดาแม็กซ์", "แอนดาแมกซ์", "แอนดาแม็ก", "andamax"],
    "แอสไปร์": ["แอสไปร์", "แอสไปร", "aspire"],
    "โค-ราซ": ["โค-ราซ", "โคราซ"],
    "โคเบิล": ["โคเบิล", "โคเบิ้ล"],
    "โซนิก": ["โซนิก", "sonic"],
    "โทมาฮอค": ["โทมาฮอค", "โทมาฮอก", "tomahawk"],
    "โม-เซ่": ["โม-เซ่", "โมเซ่", "โมเซ"],
    "โมเดิน": ["โมเดิน", "โมเดิน 50", "โมเดิน50"],
    "โฮป": ["โฮป", "hope"],
    "ไซม๊อกซิเมท": ["ไซม๊อกซิเมท", "ไซมอกซิเมท", "cymoximate"],
    "ไดแพ๊กซ์": ["ไดแพ๊กซ์", "ไดแพกซ์"],
    "ไพรซีน": ["ไพรซีน", "ไพรซิน"],
    "ไฮซีส": ["ไฮซีส", "ไฮซิส", "hysis"],
    "ชุดกล่องม่วง": ["ชุดกล่องม่วง", "กล่องม่วง"],
    "เลกาซี": ["เลกาซี", "legacy"],
    # เพิ่มสินค้าจาก knowledge table
    "โตโร่": ["โตโร่", "โตโร"],
    "โบร์แลน": ["โบร์แลน", "โบรแลน"],
    "โคราช": ["โคราช"],
    "ธานอส": ["ธานอส", "thanos"],
    "ไกลโฟเสท": ["ไกลโฟเสท", "glyphosate"],
    "ไดพิม": ["ไดพิม", "ไดพิม 90", "ไดพิม90"],
    "อาทราซีน": ["อาทราซีน", "อาทราซีน80", "atrazine"],
    "เวคเตอร์": ["เวคเตอร์", "vector"],
}


def extract_product_name_from_question(question: str) -> Optional[str]:
    """
    ดึงชื่อสินค้าจากคำถาม
    Returns: ชื่อสินค้าที่พบ หรือ None ถ้าไม่พบ
    """
    question_lower = question.lower()

    for product_name, aliases in ICP_PRODUCT_NAMES.items():
        for alias in aliases:
            if alias.lower() in question_lower:
                return product_name

    return None


def detect_unknown_product_in_question(question: str) -> Optional[str]:
    """
    ตรวจสอบว่า user ถามเกี่ยวกับสินค้าที่ไม่มีใน ICP_PRODUCT_NAMES หรือไม่
    Returns: ชื่อสินค้าที่ไม่รู้จัก หรือ None

    หมายเหตุ: ใช้เฉพาะกรณีที่ user ถามชื่อสินค้าโดยตรง เช่น "โตโร่ ใช้ยังไง"
    ไม่ใช้กับคำถามทั่วไป เช่น "แนะนำยาตัวไหน"
    """
    # ถ้าพบสินค้าที่รู้จักแล้ว → return None
    if extract_product_name_from_question(question):
        return None

    # คำที่ต้องข้าม (คำทั่วไป, คำถาม, คำกริยา)
    skip_words = [
        'อะไร', 'ยังไง', 'อย่างไร', 'เท่าไหร่', 'ตัวไหน', 'กี่', 'ทำไม', 'ไหม',
        'ใช้', 'พ่น', 'ฉีด', 'ผสม', 'กำจัด', 'รักษา', 'แนะนำ', 'ดี', 'ได้',
        'ยา', 'สาร', 'โรค', 'แมลง', 'หญ้า', 'วัชพืช', 'ธาตุ', 'อาหาร',
        'ข้าว', 'ทุเรียน', 'มะม่วง', 'ส้ม', 'พริก', 'ข้าวโพด', 'อ้อย',
        'นา', 'ไร่', 'สวน', 'ต้น', 'ใบ', 'ผล', 'ดอก',
        'ฆ่า', 'ป้องกัน', 'ควบคุม', 'ขาด', 'ร่วง', 'เหลือง', 'จุด',
        'สำคัญ', 'ที่สุด', 'บำรุง', 'ติด', 'การ'
    ]

    # pattern สำหรับตรวจจับชื่อสินค้าที่ไม่รู้จัก
    # เฉพาะกรณี "XXX ใช้ยังไง" ที่ XXX เป็นชื่อสินค้าโดยตรง
    import re

    # Pattern 1: "XXX ใช้ยังไง" - XXX ต้องขึ้นต้นประโยค
    match = re.match(r'^([ก-๙a-zA-Z]+)\s+(?:ใช้|พ่น|ฉีด|ผสม)', question.strip())
    if match:
        potential_product = match.group(1)
        # ตรวจสอบว่าไม่ใช่คำทั่วไป และมีความยาวเหมาะสม
        if potential_product.lower() not in [w.lower() for w in skip_words]:
            if 2 < len(potential_product) < 20:
                return potential_product

    return None


def extract_plant_type_from_question(question: str) -> Optional[str]:
    """
    ดึงชื่อพืชจากคำถาม
    Returns: ชื่อพืช หรือ None ถ้าไม่พบ
    """
    # รายชื่อพืชที่รองรับ
    plants = [
        "ทุเรียน", "ข้าว", "ข้าวโพด", "มันสำปะหลัง", "อ้อย", "ยางพารา", "ปาล์ม",
        "มะม่วง", "ลำไย", "ลิ้นจี่", "เงาะ", "มังคุด", "พริก", "มะเขือเทศ",
        "ถั่ว", "กล้วย", "มะพร้าว", "ส้ม", "มะนาว", "ฝรั่ง", "ชมพู่",
        "สับปะรด", "หอมแดง", "กระเทียม", "ผัก", "ไม้ผล"
    ]

    question_lower = question.lower()
    for plant in plants:
        if plant in question_lower:
            return plant
    return None


def validate_knowledge_results(results: List[Dict], product_name: str, plant_type: str = None) -> List[Dict]:
    """
    ตรวจสอบว่าผลลัพธ์ตรงกับชื่อสินค้าที่ถามหรือไม่
    กรองเฉพาะผลที่มีชื่อสินค้าตรงกัน และ prioritize ตาม plant type
    """
    if not product_name or not results:
        return results

    product_lower = product_name.lower()
    aliases = ICP_PRODUCT_NAMES.get(product_name, [product_name])

    # กรองผลที่มีชื่อสินค้าตรง
    matched = []
    for r in results:
        title = (r.get('title') or '').lower()
        content = (r.get('content') or '').lower()

        # ตรวจสอบว่ามีชื่อสินค้าใน title หรือ content
        for alias in aliases:
            if alias.lower() in title or alias.lower() in content:
                matched.append(r)
                break

    # ถ้ามี plant_type → จัดเรียงให้ผลที่ตรง plant อยู่บนสุด
    if plant_type and matched:
        plant_lower = plant_type.lower()
        # แยกเป็น 2 กลุ่ม: ตรง plant vs ไม่ตรง
        with_plant = []
        without_plant = []
        for r in matched:
            title = (r.get('title') or '').lower()
            if plant_lower in title:
                with_plant.append(r)
            else:
                without_plant.append(r)

        # ถ้ามีผลที่ตรง plant → ใช้เฉพาะนั้น
        if with_plant:
            return with_plant
        # ถ้าไม่มี → ใช้ทั้งหมดที่ match product
        return without_plant if without_plant else matched

    return matched


def is_product_question(message: str) -> bool:
    """ตรวจสอบว่าเป็นคำถามเกี่ยวกับสินค้า/ผลิตภัณฑ์หรือไม่"""
    message_lower = message.lower()
    for keyword in PRODUCT_KEYWORDS:
        if keyword in message_lower:
            return True
    return False


# =============================================================================
# ตรวจจับประเภทปัญหา: โรค vs แมลง vs ธาตุอาหาร vs วัชพืช
# =============================================================================
DISEASE_KEYWORDS = [
    # โรคทั่วไป
    "โรค", "ใบจุด", "ใบไหม้", "ราน้ำค้าง", "ราแป้ง", "ราสนิม", "เชื้อรา",
    "แอนแทรคโนส", "ผลเน่า", "รากเน่า", "โคนเน่า", "ลำต้นเน่า", "กิ่งแห้ง",
    "ราดำ", "จุดสีน้ำตาล", "ใบแห้ง", "ไฟท็อป", "ใบติด",
    # English
    "disease", "fungus", "fungal", "rot", "blight", "mildew", "rust", "anthracnose"
]

INSECT_KEYWORDS = [
    # แมลง (หมายเหตุ: หลีกเลี่ยง "ไร" เพราะจะ match กับ "อะไร")
    "แมลง", "เพลี้ย", "หนอน", "ด้วง", "มด", "ปลวก", "เพลี้ยไฟ",
    "เพลี้ยอ่อน", "เพลี้ยแป้ง", "เพลี้ยกระโดด", "หนอนกอ", "หนอนเจาะ",
    "หนอนใย", "แมลงวัน", "จักจั่น", "ทริปส์", "ศัตรูพืช",
    "ไรแดง", "ไรขาว", "ไรแมง", "ตัวไร",
    # English
    "insect", "pest", "aphid", "thrips", "mite", "worm", "caterpillar", "beetle"
]

# เพิ่ม: Keywords สำหรับธาตุอาหาร/การบำรุง
NUTRIENT_KEYWORDS = [
    # ขาดธาตุ/บำรุง
    "ขาดธาตุ", "ธาตุอาหาร", "บำรุง", "เสริมธาตุ", "ปุ๋ย",
    # อาการ
    "ดอกร่วง", "ผลร่วง", "ใบเหลือง", "ใบร่วง", "ไม่ติดดอก", "ไม่ติดผล",
    "ดอกไม่ติด", "ผลไม่ติด", "ต้นโทรม", "ต้นไม่สมบูรณ์",
    # การบำรุง
    "ติดดอก", "ติดผล", "ขยายผล", "บำรุงดอก", "บำรุงผล", "บำรุงต้น",
    "เร่งดอก", "เร่งผล", "สะสมอาหาร", "เพิ่มผลผลิต",
    # ธาตุเฉพาะ
    "โพแทสเซียม", "ฟอสฟอรัส", "ไนโตรเจน", "แคลเซียม", "โบรอน", "สังกะสี", "ซิงค์"
]

# เพิ่ม: Keywords สำหรับวัชพืช
WEED_KEYWORDS = [
    "หญ้า", "วัชพืช", "กำจัดหญ้า", "ยาฆ่าหญ้า", "หญ้าขึ้น", "หญ้างอก",
    "ใบแคบ", "ใบกว้าง", "กก"
]


def detect_problem_type(message: str) -> str:
    """
    ตรวจจับประเภทปัญหา
    Returns: 'disease', 'insect', 'nutrient', 'weed', หรือ 'unknown'

    Priority: nutrient > disease > insect > weed > unknown
    (เพราะคำถามเรื่องบำรุงมักมีคำว่า "ใบเหลือง" ซึ่งอาจซ้ำกับ disease)
    """
    message_lower = message.lower()

    # นับ keywords แต่ละประเภท
    nutrient_count = sum(1 for kw in NUTRIENT_KEYWORDS if kw in message_lower)
    disease_count = sum(1 for kw in DISEASE_KEYWORDS if kw in message_lower)
    insect_count = sum(1 for kw in INSECT_KEYWORDS if kw in message_lower)
    weed_count = sum(1 for kw in WEED_KEYWORDS if kw in message_lower)

    # หา max count
    counts = {
        'nutrient': nutrient_count,
        'disease': disease_count,
        'insect': insect_count,
        'weed': weed_count
    }

    max_count = max(counts.values())
    if max_count == 0:
        return 'unknown'

    # Return ตาม priority: nutrient > disease > insect > weed
    if counts['nutrient'] == max_count:
        return 'nutrient'
    elif counts['disease'] == max_count:
        return 'disease'
    elif counts['insect'] == max_count:
        return 'insect'
    elif counts['weed'] == max_count:
        return 'weed'
    else:
        return 'unknown'


# =============================================================================
# Vector Search Functions สำหรับ Q&A
# =============================================================================
async def generate_embedding(text: str) -> List[float]:
    """Generate embedding for search query using OpenAI"""
    if not openai_client:
        logger.error("OpenAI client not available")
        return []

    try:
        response = await openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
            encoding_format="float"
        )
        return response.data[0].embedding
    except Exception as e:
        logger.error(f"Failed to generate embedding: {e}")
        return []


async def vector_search_knowledge(query: str, top_k: int = 5, validate_product: bool = True, problem_type: str = None) -> Tuple[List[Dict], Optional[str]]:
    """
    Vector search จากตาราง knowledge พร้อมกรองตาม category

    Args:
        query: คำถาม
        top_k: จำนวนผลลัพธ์สูงสุด
        validate_product: ตรวจสอบว่าชื่อสินค้าตรงกับผลลัพธ์หรือไม่
        problem_type: 'disease', 'insect', หรือ None

    Returns:
        Tuple[results, product_not_found_message]
    """
    if not supabase_client or not openai_client:
        return [], None

    try:
        # ตรวจสอบว่าคำถามถามเกี่ยวกับสินค้าตัวไหน และพืชอะไร
        # Extract เสมอ เพื่อกรองผลลัพธ์ให้ตรงกับสินค้าที่ถาม
        product_in_question = extract_product_name_from_question(query)
        plant_in_question = extract_plant_type_from_question(query)

        # ตรวจจับประเภทปัญหาถ้าไม่ได้ระบุ
        if problem_type is None:
            problem_type = detect_problem_type(query)

        query_embedding = await generate_embedding(query)
        if not query_embedding:
            return [], None

        result = supabase_client.rpc(
            'match_knowledge',
            {
                'query_embedding': query_embedding,
                'match_threshold': 0.20,
                'match_count': top_k * 10  # ดึงมามากขึ้นเพื่อกรองตาม category
            }
        ).execute()

        if not result.data:
            if product_in_question:
                return [], f"ไม่พบข้อมูลเกี่ยวกับ \"{product_in_question}\" ในฐานข้อมูล"
            return [], None

        logger.info(f"✓ Found {len(result.data)} knowledge docs via vector search (problem_type={problem_type})")

        # กรองตาม category ตามประเภทปัญหา
        filtered_results = result.data

        # กำหนด category mapping
        CATEGORY_MAPPING = {
            'disease': ['fungicide'],
            'insect': ['insecticide'],
            'nutrient': ['fertilizer', 'growth_regulator', 'enhancer'],
            'weed': ['herbicide']
        }

        if problem_type in CATEGORY_MAPPING:
            target_categories = CATEGORY_MAPPING[problem_type]

            filtered = []
            for doc in result.data:
                category = (doc.get('category') or '').lower()

                # ตรวจสอบว่า category ตรงกับที่ต้องการ
                if any(cat in category for cat in target_categories):
                    filtered.append(doc)

            if filtered:
                filtered_results = filtered
                logger.info(f"✓ Filtered to {len(filtered_results)} {problem_type}-related docs")
            else:
                # ถ้าไม่เจอ category ที่ตรง → ลองใช้ผลทั้งหมด
                logger.info(f"⚠️ No {problem_type} category found, using all results")

        # ถ้าถามเกี่ยวกับสินค้าเฉพาะ → กรองเฉพาะสินค้าที่ตรงกับชื่อ
        if product_in_question:
            validated_results = validate_knowledge_results(filtered_results, product_in_question, plant_in_question)

            if validated_results:
                logger.info(f"✓ Validated: {len(validated_results)} results match product '{product_in_question}'")
                return validated_results[:top_k], None
            else:
                # ถ้าไม่เจอสินค้าที่ตรงกัน
                if validate_product:
                    # Strict mode: return error
                    logger.warning(f"⚠️ ถามเกี่ยวกับ '{product_in_question}' แต่ไม่พบข้อมูลตรง")
                    return [], f"ไม่พบข้อมูลเกี่ยวกับ \"{product_in_question}\" ในฐานข้อมูล กรุณาตรวจสอบชื่อสินค้าอีกครั้ง"
                else:
                    # Relaxed mode: return top results anyway
                    logger.info(f"ℹ️ ไม่พบ '{product_in_question}' ตรงๆ ใช้ผลลัพธ์จาก vector search")
                    return filtered_results[:top_k], None

        # กรองตาม plant_type ถ้ามี
        if plant_in_question:
            plant_filtered = []
            for doc in filtered_results:
                plant_type = (doc.get('plant_type') or '').lower()
                title = (doc.get('title') or '').lower()
                if plant_in_question.lower() in plant_type or plant_in_question.lower() in title:
                    plant_filtered.append(doc)

            if plant_filtered:
                filtered_results = plant_filtered
                logger.info(f"✓ Filtered to {len(filtered_results)} docs for plant '{plant_in_question}'")

        return filtered_results[:top_k], None

    except Exception as e:
        logger.error(f"Knowledge vector search failed: {e}")
        return [], None


async def vector_search_products(query: str, top_k: int = 5) -> List[Dict]:
    """Vector search จากตาราง products"""
    try:
        # ใช้ hybrid_search_products ที่มีอยู่แล้ว
        products = await hybrid_search_products(
            query=query,
            match_count=top_k,
            vector_weight=0.6,
            keyword_weight=0.4
        )
        if products:
            logger.info(f"✓ Found {len(products)} products via vector search")
        return products or []
    except Exception as e:
        logger.error(f"Product vector search failed: {e}")
        return []


async def answer_qa_with_vector_search(question: str, context: str = "") -> str:
    """
    ตอบคำถาม Q&A โดยใช้ Vector Search จาก knowledge table เป็นหลัก
    พร้อมกรองตาม category (โรค vs แมลง)

    Flow ที่ถูกต้อง:
    1. รับคำถามจาก user
    2. ตรวจจับ: ชื่อสินค้า, ชื่อพืช, ประเภทปัญหา
    3. ถ้าถามเรื่องโรค/แมลง แต่ไม่ระบุพืช → ถามพืชก่อน
    4. ถ้าถามเรื่องสินค้าเฉพาะแต่ไม่ระบุพืช → ถามพืชก่อน (เพื่อให้อัตราการใช้ถูกต้อง)
    5. ค้นหาจาก knowledge table
    6. ตอบเฉพาะข้อมูลที่มีใน DB - ห้าม hallucinate
    """
    try:
        logger.info(f"Q&A Vector Search: {question[:50]}...")

        # ตรวจสอบว่าเป็นคำถามประเภทไหน
        is_product_q = is_product_question(question)
        is_agri_q = is_agriculture_question(question)

        # ตรวจจับประเภทปัญหา (โรค vs แมลง)
        problem_type = detect_problem_type(question)
        plant_in_question = extract_plant_type_from_question(question)
        product_in_question = extract_product_name_from_question(question)

        logger.info(f"Detected: problem_type={problem_type}, plant={plant_in_question}, product={product_in_question}")

        # =================================================================
        # STEP 2: ถ้าคำถามสั้นเกินไป (เช่น "อัตราการใช้") → ถามรายละเอียด
        # =================================================================
        short_questions = ['อัตราการใช้', 'วิธีใช้', 'อัตราผสม', 'ผสมยังไง', 'ใช้ยังไง', 'อัตรา']
        is_very_short = question.strip() in short_questions or (len(question.strip()) < 12 and not product_in_question and not plant_in_question)

        # เช็คคำถามถามขนาดถัง
        tank_keywords = ['ถังเล็ก', 'ถังใหญ่', 'ถัง 20', 'ถัง 100', 'ถัง 200', 'ถังพ่น', 'กี่ลิตร']
        is_tank_question = any(kw in question.lower() for kw in tank_keywords)

        if is_tank_question:
            # Extract tank size from question
            tank_size_match = re.search(r'(\d+)\s*ลิตร', question)
            if tank_size_match:
                tank_size = int(tank_size_match.group(1))
                logger.info(f"ถามถังขนาด {tank_size} ลิตร")
                # ถ้าระบุขนาดถังแล้ว → ไปค้นหาข้อมูลต่อ (จะคำนวณในส่วน response)
            elif 'ถังเล็ก' in question.lower():
                logger.info(f"ถามถังเล็ก → ถามขนาดที่แน่นอน")
                return "ขอทราบขนาดถังเล็กกี่ลิตรด้วยค่ะ จะได้คำนวณให้เป๊ะนะคะ\n\nตัวอย่างถัง 20 ลิตร: น้องลัดดาจะคำนวณอัตราให้ตามขนาดถังที่บอกค่ะ"
            elif 'ถังใหญ่' in question.lower():
                logger.info(f"ถามถังใหญ่ → ถามขนาดที่แน่นอน")
                return "ถังใหญ่กี่ลิตรคะ บอกน้องลัดดานิด จะได้คำนวณให้ตรงค่ะ\n\nตัวอย่างคำนวณให้ก่อนนะคะ\n- ถัง 200 ลิตร: ใช้อัตราตามฉลาก\n- ถัง 100 ลิตร: ลดครึ่งจากอัตราปกติ"

        if is_very_short and problem_type == 'unknown' and not is_tank_question:
            logger.info(f"⚠️ คำถามสั้นไม่มีรายละเอียด: {question}")
            return "ขอทราบรายละเอียดเพิ่มเติมค่ะ\n- ต้องการทราบข้อมูลของสินค้าตัวไหนคะ?\n- และใช้กับพืชอะไรคะ?\n\nเพื่อให้น้องลัดดาตอบได้ถูกต้องค่ะ"

        # =================================================================
        # STEP 2.5: ถ้าถามเกี่ยวกับสินค้าที่ไม่มีใน ICP → บอกว่าไม่มี
        # =================================================================
        unknown_product = detect_unknown_product_in_question(question)
        if unknown_product and not product_in_question:
            logger.info(f"⚠️ ถามเกี่ยวกับสินค้าที่ไม่รู้จัก: {unknown_product}")
            return f"ขออภัยค่ะ ไม่พบข้อมูลสินค้า \"{unknown_product}\" ในฐานข้อมูลของ ICP Ladda ค่ะ\n\nกรุณาตรวจสอบชื่อสินค้าอีกครั้ง หรือสอบถามเกี่ยวกับสินค้าอื่นได้เลยค่ะ"

        # =================================================================
        # STEP 3: ถ้าถามเรื่องโรค/แมลง แต่ไม่ระบุพืช → ถามพืชก่อน
        # =================================================================
        # ตรวจสอบว่าเป็นคำถาม "รักษา/กำจัด" ที่ต้องการสินค้า
        is_treatment_question = any(kw in question.lower() for kw in [
            'รักษา', 'กำจัด', 'แนะนำ', 'ใช้ยา', 'ยาอะไร', 'สารอะไร',
            'ป้องกัน', 'ฆ่า', 'ควบคุม', 'จัดการ'
        ])

        # ถ้าถามเรื่องโรค/แมลง และต้องการรักษา แต่ไม่ระบุพืช → ถามพืชก่อน
        if problem_type in ['insect', 'disease'] and is_treatment_question and not plant_in_question and not product_in_question:
            logger.info(f"⚠️ ถามเรื่อง {problem_type} แต่ไม่ระบุพืช → ถามพืชก่อน")
            # Extract ชื่อปัญหา/แมลง/โรค จากคำถาม
            problem_name = ""
            for kw in INSECT_KEYWORDS + DISEASE_KEYWORDS:
                if kw in question.lower() and len(kw) > 2:
                    problem_name = kw
                    break

            if problem_type == 'insect':
                return f"น้องลัดดาขอเช็คให้ก่อนนะคะ จากข้อมูลสินค้า ยังไม่พบตัวยาที่ระบุใช้กับ \"{problem_name}\" โดยตรงค่ะ\n\nรบกวนบอกเพิ่มหน่อยว่าเป็นพืชอะไร และอยู่ช่วงไหน (แตกใบอ่อน/ออกดอก/ติดผล) จะได้ค้นหาตัวที่เหมาะให้ตรงที่สุดนะคะ"
            else:  # disease
                return f"น้องลัดดาขอเช็คให้ก่อนนะคะ จากข้อมูลสินค้า ยังไม่พบตัวยาที่ระบุใช้กับ \"{problem_name}\" โดยตรงค่ะ\n\nรบกวนบอกเพิ่มหน่อยว่าเป็นพืชอะไร และอยู่ช่วงไหน (แตกใบอ่อน/ออกดอก/ติดผล) จะได้ค้นหาตัวที่เหมาะให้ตรงที่สุดนะคะ"

        # เก็บ context จากแต่ละ source
        all_context_parts = []

        # 1. ค้นหาจาก knowledge table เป็นหลัก
        # ถ้าถามเกี่ยวกับสินค้าเฉพาะ → ค้นหาโดยไม่ต้อง strict validate (เพื่อให้พบผลลัพธ์)
        knowledge_docs, product_not_found_msg = await vector_search_knowledge(
            question,
            top_k=5,
            validate_product=False,  # ไม่ต้อง strict validate เพื่อให้พบผลลัพธ์มากขึ้น
            problem_type=problem_type
        )

        if knowledge_docs:
            knowledge_context = "ข้อมูลสินค้าและวิธีใช้:\n"
            for idx, doc in enumerate(knowledge_docs[:5], 1):
                title = doc.get('title', '')
                content = doc.get('content', '')[:400]
                product_name = doc.get('product_name', '')
                usage_rate = doc.get('usage_rate', '')
                target_pest = doc.get('target_pest', '')
                category = doc.get('category', '')

                knowledge_context += f"\n[{idx}] {title}"
                if product_name:
                    knowledge_context += f"\n   ชื่อสินค้า: {product_name}"
                if category:
                    knowledge_context += f"\n   ประเภท: {category}"
                if target_pest:
                    knowledge_context += f"\n   ใช้กำจัด: {target_pest[:100]}"
                if usage_rate:
                    knowledge_context += f"\n   อัตราใช้: {usage_rate}"
                knowledge_context += f"\n   รายละเอียด: {content}"

            all_context_parts.append(knowledge_context)
            logger.info(f"Added {len(knowledge_docs)} knowledge docs to context")

        elif product_not_found_msg:
            logger.warning(f"Product not found: {product_not_found_msg}")
            all_context_parts.append(f"หมายเหตุ: {product_not_found_msg}")

        # 2. ค้นหาจาก diseases (เสริม - ถ้าเป็นคำถามเกี่ยวกับโรค)
        if is_agri_q and problem_type == 'disease':
            diseases = await search_diseases_by_text(question, top_k=2)
            if diseases:
                disease_context = build_context_from_diseases(diseases)
                all_context_parts.append(f"ข้อมูลโรค:\n{disease_context}")
                logger.info(f"Added {len(diseases)} diseases to context")

        # รวม context ทั้งหมด
        combined_context = "\n\n".join(all_context_parts) if all_context_parts else "(ไม่พบข้อมูลในฐานข้อมูล)"

        # ตรวจจับประเภทคำถาม
        is_what_question = any(kw in question.lower() for kw in ['ใช้ทำอะไร', 'คืออะไร', 'ใช้อะไร', 'ทำอะไร', 'เป็นอะไร'])
        is_how_question = any(kw in question.lower() for kw in ['ใช้ยังไง', 'ใช้อย่างไร', 'วิธีใช้', 'ผสมยังไง'])
        is_rate_question = any(kw in question.lower() for kw in ['อัตรา', 'ผสมเท่าไหร่', 'กี่ซีซี', 'กี่ลิตร'])
        # เพิ่ม: คำถามแนะนำสินค้า/สาร
        is_recommend_question = any(kw in question.lower() for kw in ['แนะนำ', 'ใช้ยาอะไร', 'ใช้สารอะไร', 'ยาตัวไหน', 'สารตัวไหน', 'ฉีดพ่น'])

        # สร้าง prompt ตามประเภทคำถาม
        if is_recommend_question and knowledge_docs:
            # คำถามแนะนำสินค้า (มี knowledge_docs แล้ว) → ตอบจากข้อมูลที่มี
            prompt = f"""คุณคือ "น้องลัดดา" ผู้เชี่ยวชาญด้านการเกษตรของ ICP Ladda

คำถาม: {question}

ข้อมูลจากฐานข้อมูล:
{combined_context}

หลักการตอบ (สำคัญมาก!):
1. เริ่มต้นด้วย "จากข้อมูลสินค้า" + คำอธิบายสั้นๆ
2. ใส่ชื่อสินค้าในเครื่องหมาย "" เสมอ
3. ถ้าเป็นวัชพืช → จัดกลุ่มตามช่วง:
   - ก่อนวัชพืชงอก: ใช้ "ชื่อยา" อัตรา XX มล./ไร่ พ่น...
   - หลังวัชพืชงอก:
     - ทางเลือก 1: "ชื่อยา" XX มล./ไร่ ...
     - ทางเลือก 2: "ชื่อยา" XX มล./ไร่ ...

4. ถ้าเป็นแมลง/โรค → ตอบแบบนี้:
   จากข้อมูลสินค้า แนะนำ "ชื่อยา" ใช้กำจัด XX ได้ค่ะ
   - อัตราใช้: XX กรัม ต่อน้ำ XX ลิตร
   - วิธีใช้: ผสมน้ำตามอัตรา แล้วฉีดพ่นให้ทั่วทรงพุ่ม
   - ช่วงใช้: ใช้ได้ทุกระยะ

5. ปิดท้ายด้วยการถามขนาดถัง:
   "ถ้าบอกขนาดถังพ่น น้องลัดดาช่วยคำนวณอัตราให้ได้ค่ะ"

6. ห้ามแต่งข้อมูลเอง ใช้เฉพาะที่มีในฐานข้อมูล
7. ห้ามใช้ ** หรือ ## หรือ emoji

ตอบ:"""
        elif product_in_question and is_what_question:
            # คำถามแบบ "X ใช้ทำอะไร" → ตอบสั้นๆ + ถาม follow-up
            prompt = f"""คุณคือ "น้องลัดดา" ผู้เชี่ยวชาญด้านการเกษตรของ ICP Ladda

คำถาม: {question}

ข้อมูลจากฐานข้อมูล:
{combined_context}

หลักการตอบ (สำคัญมาก!):
1. เริ่มด้วย "จากข้อมูลสินค้า" + คำอธิบายสั้นๆ
2. ใส่ชื่อสินค้าในเครื่องหมาย "" เสมอ
3. บอกว่าสินค้านี้คืออะไร ใช้ทำอะไร (2-3 ประโยค)
4. ปิดท้ายด้วยการถามข้อมูลเพิ่มเติม
5. ห้ามใช้ ** หรือ ## หรือ emoji
6. ห้ามแต่งข้อมูลเอง

ตัวอย่างการตอบ:
จากข้อมูลสินค้า "{product_in_question}" เป็น [ประเภทสาร] ใช้สำหรับ [วัตถุประสงค์หลัก] ค่ะ

ต้องการทราบข้อมูลเพิ่มเติมไหมคะ เช่น วิธีใช้, อัตราผสม, หรือใช้กับพืชอะไรได้บ้าง?

ตอบ:"""
        elif product_in_question and (is_how_question or is_rate_question):
            # คำถามเฉพาะเจาะจง → ตอบเฉพาะสิ่งที่ถาม
            prompt = f"""คุณคือ "น้องลัดดา" ผู้เชี่ยวชาญด้านการเกษตรของ ICP Ladda

คำถาม: {question}

ข้อมูลจากฐานข้อมูล:
{combined_context}

หลักการตอบ:
1. เริ่มด้วย "จากข้อมูลสินค้า แนะนำ" หรือ "จากข้อมูลสินค้า"
2. ใส่ชื่อสินค้าในเครื่องหมาย "" เสมอ
3. ตอบแบบนี้:
   จากข้อมูลสินค้า แนะนำ "{product_in_question}" ... ค่ะ
   - อัตราใช้: XX กรัม/มล. ต่อน้ำ XX ลิตร
   - วิธีใช้: ผสมน้ำตามอัตรา แล้วฉีดพ่น...
   - ช่วงใช้: ใช้ได้ทุกระยะ / ช่วง...

   ถ้าบอกขนาดถังพ่น น้องลัดดาช่วยคำนวณอัตราให้ได้ค่ะ

4. ห้ามแต่งข้อมูลเอง ใช้เฉพาะที่มีในฐานข้อมูล
5. ห้ามใช้ ** หรือ ## หรือ emoji

ตอบ:"""
        else:
            # คำถามทั่วไป → ตอบตามปกติแต่กระชับ
            prompt = f"""คุณคือ "น้องลัดดา" ผู้เชี่ยวชาญด้านการเกษตรของ ICP Ladda

คำถาม: {question}

บริบท: {context if context else "(เริ่มสนทนาใหม่)"}

ข้อมูลจากฐานข้อมูล:
{combined_context}

หลักการตอบ (สำคัญมาก!):
1. เริ่มด้วย "จากข้อมูลสินค้า" + คำอธิบายสั้นๆ
2. ใส่ชื่อสินค้าในเครื่องหมาย "" เสมอ

3. ถ้าเป็นวัชพืช → จัดกลุ่มตามช่วง:
   จากข้อมูลสินค้า จัดการ "ชื่อวัชพืช" ใน... เลือกใช้ตามช่วงนี้ได้เลยค่ะ
   - ก่อนวัชพืชงอก: ใช้ "ชื่อยา" อัตรา XX มล./ไร่ พ่นหลังหว่าน X วัน...
   - หลังวัชพืชงอก:
     - ทางเลือก 1: "ชื่อยา" XX มล./ไร่ ร่วมกับ "ชื่อยา" XX มล./ไร่ พ่นหลังหว่าน X วัน...
     - ทางเลือก 2: "ชื่อยา" XX มล./ไร่ พ่นหลังหว่าน X วัน...

4. ถ้าเป็นแมลง/โรค → ตอบแบบนี้:
   จากข้อมูลสินค้า แนะนำ "ชื่อยา" ใช้กำจัด XX ใน YY ได้ค่ะ
   - อัตราใช้: XX กรัม ต่อน้ำ XX ลิตร
   - วิธีใช้: ผสมน้ำตามอัตรา แล้วฉีดพ่นให้ทั่วทรงพุ่ม
   - ช่วงใช้: ใช้ได้ทุกระยะ ทั้งแตกใบอ่อน ออกดอก และติดผล

5. ปิดท้ายด้วยการถามขนาดถัง:
   "บอกน้องลัดดาหน่อยค่ะ ตอนนี้หลังหว่านมากี่วันแล้ว และใช้ถังพ่นกี่ลิตร น้องลัดดาคำนวณอัตราต่อถังให้เป๊ะๆ ได้เลยค่ะ"
   หรือ
   "ถ้าบอกขนาดถังพ่น น้องลัดดาช่วยคำนวณอัตราให้ได้ค่ะ"

6. ถ้าคำถามไม่ชัดเจน ให้ถามกลับ เช่น "ขอทราบชื่อพืชด้วยค่ะ?"
7. ห้ามแต่งข้อมูลเอง ใช้เฉพาะที่มีในฐานข้อมูล
8. ห้ามใช้ ** หรือ ## หรือ emoji

ตอบ:"""

        if not openai_client:
            return "ขออภัยค่ะ ระบบ AI ไม่พร้อมใช้งานในขณะนี้"

        # ถ้าไม่พบข้อมูลในฐานข้อมูล → บอกตรงๆ
        if not knowledge_docs:
            return f"น้องลัดดาขอเช็คให้ก่อนนะคะ จากข้อมูลสินค้า ยังไม่พบข้อมูลที่ตรงกับคำถามโดยตรงค่ะ\n\nรบกวนบอกเพิ่มหน่อยว่า:\n- เป็นพืชอะไรคะ (เช่น ข้าว, ทุเรียน, มะม่วง)\n- ปัญหาที่พบ (เช่น โรค, แมลง, วัชพืช)\n\nจะได้ค้นหาตัวที่เหมาะให้ตรงที่สุดนะคะ"

        # =================================================================
        # สร้างรายชื่อสินค้าที่อนุญาตให้แนะนำ (จาก knowledge_docs เท่านั้น)
        # =================================================================
        allowed_products = []
        for doc in knowledge_docs:
            pname = doc.get('product_name') or doc.get('title', '')
            if pname and pname not in allowed_products:
                allowed_products.append(pname)

        allowed_products_str = ", ".join(allowed_products[:10]) if allowed_products else "(ไม่มี)"

        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": f"""คุณคือน้องลัดดา ผู้เชี่ยวชาญด้านการเกษตรของ ICP Ladda

⛔ กฎเหล็กที่ห้ามละเมิดเด็ดขาด:

1. ห้ามตอบมั่ว ห้ามแต่งข้อมูลเด็ดขาด
   - ถ้าคำถามไหนไม่มีข้อมูลในฐานข้อมูล → ตอบตรงๆ ว่า:
     "ขออภัยค่ะ ไม่มีข้อมูลเรื่องนี้ในฐานข้อมูลของลัดดาค่ะ"
   - ห้ามเดา ห้ามสมมติ ห้ามใช้ความรู้ทั่วไป

2. แนะนำได้เฉพาะสินค้าต่อไปนี้เท่านั้น (ห้ามแต่งชื่ออื่น):
   [{allowed_products_str}]

3. ถ้าถามเรื่องสินค้าที่ไม่อยู่ในรายการด้านบน → ตอบว่า:
   "ขออภัยค่ะ ไม่พบข้อมูลสินค้านี้ในฐานข้อมูลค่ะ"

4. ห้ามแต่งข้อมูลต่อไปนี้เด็ดขาด:
   - ห้ามแต่งอัตราการใช้ (ถ้าไม่มีในข้อมูล → บอกว่าไม่มี)
   - ห้ามแต่งวิธีการใช้ (ถ้าไม่มีในข้อมูล → บอกว่าไม่มี)
   - ห้ามแต่งชื่อสารเคมี (ถ้าไม่มีในข้อมูล → บอกว่าไม่มี)
   - ห้ามแต่งชื่อโรค/แมลง (ถ้าไม่มีในข้อมูล → บอกว่าไม่มี)

5. ห้ามใช้ ** หรือ ## หรือ emoji

6. รูปแบบการตอบ:
   - เริ่มด้วย "จากข้อมูลสินค้า" + คำอธิบาย
   - ใส่ชื่อสินค้าในเครื่องหมาย "" เสมอ
   - ถ้าเป็นวัชพืช → จัดกลุ่มตาม: ก่อนวัชพืชงอก, หลังวัชพืชงอก (ทางเลือก 1, 2)
   - ถ้าเป็นแมลง/โรค → ระบุ: อัตราใช้, วิธีใช้, ช่วงใช้
   - ปิดท้ายด้วย: "ถ้าบอกขนาดถังพ่น น้องลัดดาช่วยคำนวณอัตราให้ได้ค่ะ"

7. ตอบกระชับ ตรงประเด็น เฉพาะข้อมูลที่มีในฐานข้อมูลเท่านั้น"""},
                {"role": "user", "content": prompt}
            ],
            max_tokens=600,
            temperature=0.1  # ลด temperature มากที่สุดเพื่อป้องกันการแต่งข้อมูล
        )

        answer = post_process_answer(response.choices[0].message.content)
        return answer

    except Exception as e:
        logger.error(f"Error in Q&A vector search: {e}", exc_info=True)
        return "ขออภัยค่ะ เกิดข้อผิดพลาดในการประมวลผล กรุณาลองใหม่อีกครั้งนะคะ"


async def answer_agriculture_question(question: str, context: str = "") -> str:
    """
    ตอบคำถามเกี่ยวกับการเกษตร/พืช/โรคพืช
    1. ค้นหาจากตาราง diseases ก่อน (vector search)
    2. ถ้าไม่พบ → ใช้ความรู้ทั่วไป + อ้างอิงกรมวิชาการเกษตร
    """
    try:
        logger.info(f"🌾 Agriculture question: {question[:50]}...")

        # 1. ค้นหาจากตาราง diseases
        diseases = await search_diseases_by_text(question, top_k=5)

        if diseases:
            # พบข้อมูลในฐานข้อมูล → สร้าง context จากโรคที่พบ
            disease_context = build_context_from_diseases(diseases)
            logger.info(f"✓ Found {len(diseases)} related diseases in database")

            prompt = f"""คุณคือ "น้องลัดดา" ผู้เชี่ยวชาญด้านการเกษตรของ ICP Ladda

คำถาม: {question}

บริบทการสนทนา:
{context if context else "(เริ่มสนทนาใหม่)"}

ข้อมูลโรค/ปัญหาที่เกี่ยวข้องจากฐานข้อมูล:
{disease_context}

รูปแบบการตอบ (สำคัญมาก!):

ตอบเป็นขั้นตอนชัดเจน แยกเป็นหัวข้อย่อย:

[สาเหตุ/ปัญหา]
อธิบายสาเหตุหรือปัญหาสั้นๆ

[อาการที่พบ]
อธิบายอาการที่พบ

[ผลิตภัณฑ์แนะนำ]
1. ชื่อสินค้า (สารสำคัญ)
   - อัตราใช้: XX ซีซี/น้ำ XX ลิตร
   - วิธีใช้: ฉีดพ่น/ราด...

2. ทางเลือกอื่น (ถ้ามี)
   - อัตราใช้: ...

[วิธีการใช้]
อธิบายขั้นตอน

[ข้อแนะนำเพิ่มเติม]
คำแนะนำอื่นๆ

หลักการ:
- ใช้ [หัวข้อ] เป็นตัวแบ่งส่วน
- แยกบรรทัดให้ชัดเจน อ่านง่าย
- ใช้ - สำหรับรายละเอียดย่อย
- ตอบเฉพาะหัวข้อที่เกี่ยวข้อง (ไม่ต้องใส่ทุกหัวข้อ)
- ห้ามใช้ ** หรือ ## หรือ emoji

ตอบ:"""
        else:
            # ไม่พบในฐานข้อมูล → บอกตรงๆ ว่าไม่มีข้อมูล (ห้ามใช้ความรู้ทั่วไป)
            logger.info("⚠️ No diseases found in database, returning no-data message")
            return "ขออภัยค่ะ ไม่พบข้อมูลเรื่องนี้ในฐานข้อมูลของลัดดาค่ะ\n\nกรุณาระบุรายละเอียดเพิ่มเติม:\n- ชื่อพืช (เช่น ทุเรียน, ข้าว, มะม่วง)\n- อาการ/ปัญหาที่พบ\n\nเพื่อให้ลัดดาค้นหาข้อมูลที่ตรงกับความต้องการค่ะ"

        if not openai_client:
            return "ขออภัยค่ะ ระบบ AI ไม่พร้อมใช้งานในขณะนี้"

        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": """คุณคือน้องลัดดา ผู้เชี่ยวชาญด้านการเกษตรของ ICP Ladda

⛔ กฎเหล็ก - ห้ามตอบมั่วเด็ดขาด:
- ตอบเฉพาะข้อมูลที่มีในฐานข้อมูลที่ให้มาเท่านั้น
- ถ้าข้อมูลไม่ครบ → บอกว่า "ไม่มีข้อมูลเรื่องนี้ในฐานข้อมูล"
- ห้ามเดา ห้ามสมมติ ห้ามแต่งข้อมูลขึ้นมาเอง

รูปแบบการตอบ:
- ตอบเป็นขั้นตอน แยกหัวข้อชัดเจนด้วย [หัวข้อ]
- ใช้เลขลำดับ 1. 2. 3. สำหรับรายการสินค้า
- ใช้ - สำหรับรายละเอียดย่อย (อัตราใช้, วิธีใช้)
- แยกบรรทัดให้อ่านง่าย
- ห้ามใช้ ** หรือ ## หรือ emoji
- ถ้าคำถามไม่ชัดเจน ให้ถามกลับสั้นๆ"""},
                {"role": "user", "content": prompt}
            ],
            max_tokens=800,
            temperature=0.2  # ลด temperature เพื่อป้องกันการแต่งข้อมูล
        )

        answer = post_process_answer(response.choices[0].message.content)
        return answer

    except Exception as e:
        logger.error(f"Error answering agriculture question: {e}", exc_info=True)
        return "ขออภัยค่ะ เกิดข้อผิดพลาดในการประมวลผล กรุณาลองใหม่อีกครั้งนะคะ"


# =============================================================================
# คำถามเกี่ยวกับวิธีใช้สินค้า / การพ่นยา / การฉีด
# =============================================================================
USAGE_QUESTION_PATTERNS = [
    # วิธีใช้ทั่วไป
    r"วิธี(?:ใช้|พ่น|ฉีด|ผสม)",
    r"ใช้(?:ยัง|ยังไง|อย่างไร|ย่างไร)",
    r"พ่น(?:ยัง|ยังไง|อย่างไร|ย่างไร)",
    r"ฉีด(?:ยัง|ยังไง|อย่างไร|ย่างไร)",
    r"ผสม(?:ยัง|ยังไง|อย่างไร|ย่างไร)",
    # อัตราส่วน
    r"อัตรา(?:การ)?(?:ใช้|ผสม|ส่วน)",
    r"ผสม(?:กี่|เท่าไหร่|เท่าไร)",
    r"ใช้(?:กี่|เท่าไหร่|เท่าไร)",
    # ช่วงเวลา
    r"(?:พ่น|ฉีด|ใช้)(?:ตอน|เมื่อ|ช่วง)",
    r"(?:ตอน|เมื่อ|ช่วง)(?:ไหน|ใด).*(?:พ่น|ฉีด|ใช้)",
    # คำถามเฉพาะ
    r"(?:แนะนำ)?(?:วิธี|ขั้นตอน).*(?:พ่น|ฉีด|ใช้|รักษา)",
    r"(?:พ่น|ฉีด).*(?:กี่|บ่อย|ถี่)",
    r"(?:ละลาย|เจือจาง).*(?:น้ำ|ยัง)",
    # ถามต่อจากสินค้าที่แนะนำ
    r"(?:ตัว)?(?:นี้|นั้น|แรก|ที่\d).*(?:ใช้|พ่น|ฉีด)",
    r"(?:ใช้|พ่น|ฉีด).*(?:ตัว)?(?:นี้|นั้น|แรก|ที่\d)",
]


def is_usage_question(message: str) -> bool:
    """ตรวจสอบว่าเป็นคำถามเกี่ยวกับวิธีใช้สินค้าหรือไม่"""
    message_lower = message.lower()
    for pattern in USAGE_QUESTION_PATTERNS:
        if re.search(pattern, message_lower):
            return True
    return False


async def answer_usage_question(user_id: str, message: str, context: str = "") -> str:
    """
    ตอบคำถามเกี่ยวกับวิธีใช้สินค้าจากข้อมูลที่เก็บใน memory

    Flow ที่ถูกต้อง:
    1. ถ้าถามแบบสั้น (เช่น "อัตราการใช้") โดยไม่ระบุสินค้า/พืช → ถามกลับ
    2. ถ้ามีสินค้าใน memory และระบุพืช → ตอบจาก memory
    3. ถ้าไม่มี memory → ไป flow ปกติ
    """
    try:
        # ตรวจสอบว่าคำถามระบุสินค้าหรือพืชหรือไม่
        product_in_question = extract_product_name_from_question(message)
        plant_in_question = extract_plant_type_from_question(message)

        # ถ้าถามแบบสั้นๆ (เช่น "อัตราการใช้", "วิธีใช้") โดยไม่ระบุสินค้า → ต้องถามกลับ
        short_questions = ['อัตราการใช้', 'วิธีใช้', 'อัตราผสม', 'ผสมยังไง', 'ใช้ยังไง']
        is_short_question = message.strip() in short_questions or len(message.strip()) < 15

        if is_short_question and not product_in_question and not plant_in_question:
            logger.info(f"⚠️ คำถามสั้นไม่ระบุรายละเอียด: {message}")
            return "ขอทราบรายละเอียดเพิ่มเติมค่ะ:\n- ต้องการทราบอัตราการใช้ของสินค้าตัวไหนคะ?\n- และใช้กับพืชอะไรคะ?\n\nเพื่อให้ลัดดาแนะนำอัตราการใช้ที่ถูกต้องค่ะ"

        # ดึงข้อมูลสินค้าที่แนะนำล่าสุด
        products = await get_recommended_products(user_id, limit=5)

        if not products:
            return None  # ไม่มีสินค้าใน memory → ให้ไปใช้ flow ปกติ

        # สร้าง prompt สำหรับ AI
        products_text = ""
        for idx, p in enumerate(products, 1):
            products_text += f"\n[{idx}] {p.get('product_name', 'N/A')}"
            if p.get('how_to_use'):
                products_text += f"\n   • วิธีใช้: {p.get('how_to_use')}"
            if p.get('usage_rate'):
                products_text += f"\n   • อัตราใช้: {p.get('usage_rate')}"
            if p.get('usage_period'):
                products_text += f"\n   • ช่วงการใช้: {p.get('usage_period')}"
            if p.get('target_pest'):
                products_text += f"\n   • ศัตรูพืชที่กำจัด: {p.get('target_pest')[:100]}"
            if p.get('applicable_crops'):
                products_text += f"\n   • ใช้กับพืช: {p.get('applicable_crops')[:100]}"
            products_text += "\n"

        prompt = f"""คุณคือ "น้องลัดดา" ผู้เชี่ยวชาญด้านการใช้ยาฆ่าศัตรูพืชจาก ICP Ladda

สินค้าที่เพิ่งแนะนำให้ผู้ใช้:
{products_text}

บทสนทนาก่อนหน้า:
{context if context else "(ไม่มี)"}

คำถามจากผู้ใช้: {message}

รูปแบบการตอบ (สำคัญมาก!):

ตอบเป็นขั้นตอนชัดเจน ใช้ [หัวข้อ] เป็นตัวแบ่ง:

[ผลิตภัณฑ์]
ชื่อสินค้า

[วิธีใช้]
1. ขั้นตอนที่ 1
2. ขั้นตอนที่ 2
3. ขั้นตอนที่ 3

[อัตราผสม]
- อัตราใช้: XX ซีซี/น้ำ XX ลิตร

[ช่วงเวลาที่เหมาะสม]
บอกช่วงเวลาที่ควรพ่น/ฉีด

[ข้อควรระวัง]
- ใส่ถุงมือ หน้ากากป้องกัน
- คำเตือนอื่นๆ

หลักการ:
- ใช้ [หัวข้อ] เป็นตัวแบ่งส่วน
- แยกบรรทัดให้อ่านง่าย
- ใช้ - สำหรับรายละเอียดย่อย
- ห้ามแต่งข้อมูลเอง ใช้เฉพาะข้อมูลที่ให้มา
- ห้ามใช้ ** หรือ ## หรือ emoji

ตอบ:"""

        if not openai_client:
            # Fallback: แสดงข้อมูลดิบ
            response = "[วิธีใช้ผลิตภัณฑ์ที่แนะนำ]\n"
            for idx, p in enumerate(products[:3], 1):
                response += f"\n{idx}. {p.get('product_name', 'N/A')}"
                if p.get('how_to_use'):
                    response += f"\n   - วิธีใช้: {p.get('how_to_use')}"
                if p.get('usage_rate'):
                    response += f"\n   - อัตราใช้: {p.get('usage_rate')}"
            response += "\n\n[ข้อควรระวัง]\nอ่านฉลากก่อนใช้ทุกครั้งนะคะ"
            return response

        response = await openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": """คุณคือผู้เชี่ยวชาญด้านการใช้ยาฆ่าศัตรูพืช

รูปแบบการตอบ:
- ตอบเป็นขั้นตอน แยกหัวข้อด้วย [หัวข้อ]
- ใช้เลขลำดับ 1. 2. 3. สำหรับขั้นตอน
- ใช้ - สำหรับรายละเอียดย่อย
- แยกบรรทัดให้อ่านง่าย
- ห้ามใช้ ** หรือ ## หรือ emoji"""},
                {"role": "user", "content": prompt}
            ],
            max_tokens=600,
            temperature=0.3
        )

        answer = response.choices[0].message.content.strip()
        answer = answer.replace("**", "").replace("##", "").replace("```", "")

        # เพิ่ม footer
        answer += "\n\nหากต้องการข้อมูลเพิ่มเติม สอบถามได้เลยค่ะ"

        logger.info(f"✓ Answered usage question from memory products")
        return answer

    except Exception as e:
        logger.error(f"Error answering usage question: {e}", exc_info=True)
        return None

async def handle_natural_conversation(user_id: str, message: str) -> str:
    """Handle natural conversation with context and intent detection"""
    try:
        # 1. Add user message to memory
        await add_to_memory(user_id, "user", message)

        # 2. Get conversation context
        context = await get_conversation_context(user_id)

        # 3. Check if this is a usage/application question (วิธีใช้/พ่น/ฉีด)
        if is_usage_question(message):
            logger.info(f"🔧 Detected usage question: {message[:50]}...")
            usage_answer = await answer_usage_question(user_id, message, context)
            if usage_answer:
                # Add assistant response to memory
                await add_to_memory(user_id, "assistant", usage_answer)
                return usage_answer
            # ถ้าไม่มีสินค้าใน memory → ให้ไปใช้ flow ปกติ
            logger.info("No products in memory, falling back to normal flow")

        # 4. Analyze intent and keywords
        keywords = extract_keywords_from_question(message)

        # 5. Route based on intent
        # Priority 1: Q&A เกี่ยวกับการเกษตร/สินค้า/โรค → Vector Search จาก 3 tables
        is_agri_q = is_agriculture_question(message) or keywords["pests"] or keywords["crops"]
        is_prod_q = is_product_question(message) or keywords["is_product_query"]
        is_fert_q = keywords.get("is_fertilizer_query", False)

        if is_agri_q or is_prod_q or is_fert_q:
            logger.info(f"🔍 Routing to Q&A Vector Search (agri={is_agri_q}, product={is_prod_q}, fertilizer={is_fert_q})")
            answer = await answer_qa_with_vector_search(message, context)

            # Track analytics if product recommendation
            if is_prod_q:
                from app.services.services import analytics_tracker
                if analytics_tracker:
                    product_pattern = r'\d+\.\s+([^\n]+?)(?:\n|$)'
                    product_matches = re.findall(product_pattern, answer)
                    product_names = []
                    for match in product_matches:
                        clean_name = match.split('\n')[0].strip()
                        clean_name = clean_name.replace('ชื่อผลิตภัณฑ์:', '').strip()
                        if clean_name and len(clean_name) > 3:
                            product_names.append(clean_name)
                    if product_names:
                        await analytics_tracker.track_product_recommendation(
                            user_id=user_id,
                            disease_name="Q&A",
                            products=product_names[:5]
                        )
                        logger.info(f"Tracked {len(product_names)} products from Q&A")

            # Add assistant response to memory
            await add_to_memory(user_id, "assistant", answer)
            return answer
            
        else:
            logger.info("Routing to general chat")
            # General conversation with persona - Enhanced for natural conversation

            system_prompt = """คุณคือ "น้องลัดดา" ผู้ช่วยอัจฉริยะจาก ICP Ladda

บุคลิกภาพ:
- อายุประมาณ 25-28 ปี สาวใจดี ร่าเริง เข้าถึงง่าย
- เป็นคนบ้านนอก (อีสาน) แต่เรียนจบด้านเกษตรมา
- ชอบใช้คำพูดเป็นกันเอง แต่สุภาพ (ค่ะ, คะ, นะคะ)
- มีอารมณ์ขัน ชอบหยอกล้อเบาๆ
- ใส่ใจและห่วงใยเกษตรกรเหมือนเป็นครอบครัว

ความเชี่ยวชาญ:
- ความรู้ด้านการเกษตร โรคพืช ศัตรูพืช,การดูแลรักษาพืช
- ผลิตภัณฑ์ ICP Ladda (ยาฆ่าแมลง, ยาฆ่าเชื้อรา, ปุ๋ย)
- เข้าใจปัญหาของเกษตรกรไทย

วิธีตอบ:
- ตอบสั้นกระชับ (1-3 ประโยค) ยกเว้นถามเรื่องเทคนิค
- ใช้ภาษาง่ายๆ ไม่ต้องเป็นทางการมาก
- ห้ามใช้ emoji
- ถ้าเป็นการทักทาย → ทักทายกลับอบอุ่น
- ถ้าถามเรื่องส่วนตัว → ตอบแบบน่ารักขี้เล่น
- ถ้าถามเรื่องที่ไม่เกี่ยวกับเกษตร → ตอบได้แต่ชวนคุยเรื่องเกษตรเบาๆ
- ถ้าผู้ใช้มีปัญหา → แสดงความเห็นใจก่อน แล้วค่อยช่วย

ตัวอย่างการตอบ:
- "สวัสดีค่า" → "สวัสดีค่ะ วันนี้สบายดีไหมคะ มีอะไรให้ลัดดาช่วยมั้ยคะ"
- "ดีจ้า" → "ดีค่ะพี่ วันนี้มีเรื่องอะไรมาคุยกันคะ"
- "ชื่ออะไร" → "ชื่อลัดดาค่ะ เรียกน้องลัดดาก็ได้นะคะ ยินดีที่ได้รู้จักค่ะ"
- "ทำอะไรอยู่" → "กำลังรอช่วยพี่ๆ เกษตรกรอยู่ค่ะ มีอะไรให้ช่วยไหมคะ"
- "เหนื่อยจัง" → "พักผ่อนบ้างนะคะพี่ ทำไร่ทำสวนเหนื่อยนะคะ ดูแลสุขภาพด้วยนะคะ"
- "ขอบคุณ" → "ยินดีค่ะ มีอะไรก็ทักมาได้ตลอดนะคะ"

ข้อห้าม:
- ไม่พูดถึงราคาสินค้า (ให้บอกว่าติดต่อตัวแทนจำหน่าย)
- ไม่แนะนำยี่ห้ออื่นนอกจาก ICP Ladda
- ไม่ตอบเรื่องการเมือง ศาสนา หรือเรื่องอ่อนไหว

กฎเหล็ก - ห้ามตอบมั่วเด็ดขาด:
- ถ้าถามเรื่องที่ไม่รู้ หรือไม่มีข้อมูล → ตอบตรงๆ ว่า "ขออภัยค่ะ ลัดดาไม่มีข้อมูลเรื่องนี้ค่ะ"
- ห้ามเดา ห้ามสมมติ ห้ามแต่งข้อมูลขึ้นมาเอง
- ถ้าถามเรื่องสินค้า/โรค/แมลง ที่ไม่รู้ → บอกว่า "ขอโทษค่ะ ไม่มีข้อมูลเรื่องนี้ในฐานข้อมูลค่ะ" """

            user_prompt = f"""บริบทการสนทนาก่อนหน้า:
{context if context else "(เริ่มสนทนาใหม่)"}

ข้อความจากผู้ใช้: {message}

ตอบกลับอย่างเป็นธรรมชาติ เหมือนคุยกับเพื่อน:"""

            response = await openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=300,
                temperature=0.7  # เพิ่มความหลากหลายในการตอบ
            )
            answer = post_process_answer(response.choices[0].message.content)
            
            # Add assistant response to memory
            await add_to_memory(user_id, "assistant", answer)
            return answer

    except Exception as e:
        logger.error(f"Error in natural conversation: {e}", exc_info=True)
        return "ขออภัยค่ะ น้องลัดดามึนหัวนิดหน่อย คุยเรื่องอื่นกันก่อนได้ไหมคะ"
