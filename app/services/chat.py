import logging
import re
from difflib import SequenceMatcher
from typing import List, Dict, Optional, Tuple
from app.services.services import openai_client, supabase_client
from app.services.memory import add_to_memory, get_conversation_context, get_enhanced_context
from app.utils.text_processing import post_process_answer
from app.services.product_recommendation import hybrid_search_products
from app.config import USE_AGENTIC_RAG
from app.prompts import (
    GENERAL_CHAT_PROMPT,
    GREETINGS,
    ERROR_GENERIC,
    INTENT_CLASSIFICATION_PROMPT,
)

logger = logging.getLogger(__name__)

# Import AgenticRAG (lazy import to avoid circular dependencies)
_agentic_rag = None

def _get_agentic_rag():
    """Lazy import and get AgenticRAG instance"""
    global _agentic_rag
    if _agentic_rag is None and USE_AGENTIC_RAG:
        from app.services.agentic_rag import get_agentic_rag
        _agentic_rag = get_agentic_rag()
    return _agentic_rag

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
    "คาริสมา": ["คาริสมา", "คาริสม่า", "คาริส"],
    "ซิมเมอร์": ["ซิมเมอร์", "ซิมเมอ"],
    "ซีเอ็มจี": ["ซีเอ็มจี", "cmg", "ซีเอมจี"],
    "ทูโฟฟอส": ["ทูโฟฟอส", "ทูโฟ", "ทูโฟโฟส"],
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
    "เกรค": ["เกรค", "เกรค 5 เอสซี", "เกรด", "เกรด5", "เกรค5", "เกรด 5"],
    "เคเซีย": ["เคเซีย", "เคเซีย์"],
    "เทอราโน่": ["เทอราโน่", "เทอราโน", "terano"],
    "เบนซาน่า": ["เบนซาน่า", "เบนซาน่า เอฟ"],
    "เมลสัน": ["เมลสัน", "เมลซัน"],
    "แกนเตอร์": ["แกนเตอร์", "แกนเตอ", "แกนเตอร"],
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
}


def extract_product_name_from_question(question: str) -> Optional[str]:
    """
    ดึงชื่อสินค้าจากคำถาม
    Returns: ชื่อสินค้าที่พบ หรือ None ถ้าไม่พบ
    """
    question_lower = question.lower()

    # Step 1: Exact substring match (เร็ว)
    for product_name, aliases in ICP_PRODUCT_NAMES.items():
        for alias in aliases:
            if alias.lower() in question_lower:
                return product_name

    # Step 2: Fuzzy match (fallback สำหรับพิมพ์ผิด)
    return fuzzy_match_product_name(question)


def fuzzy_match_product_name(text: str, threshold: float = 0.65) -> Optional[str]:
    """
    Fuzzy matching สำหรับชื่อสินค้าที่พิมพ์ผิด
    เช่น "แแกนเตอ" → "แกนเตอร์", "โมเดิ้น" → "โมเดิน"
    """
    # แยกคำ: ทั้งคำภาษาไทยต่อกัน และคำ English
    tokens = re.findall(r'[\u0E00-\u0E7F]+|[a-zA-Z]+', text)

    best_match = None
    best_score = 0.0

    for token in tokens:
        if len(token) < 3:  # ข้ามคำสั้นเกินไป
            continue
        token_lower = token.lower()
        for product_name, aliases in ICP_PRODUCT_NAMES.items():
            for alias in aliases:
                alias_lower = alias.lower()
                # Direct comparison
                score = SequenceMatcher(None, token_lower, alias_lower).ratio()
                if score > best_score and score >= threshold:
                    best_score = score
                    best_match = product_name

                # Sliding window: ถ้า token ยาวกว่า alias มาก ให้ลองเทียบ substring
                alias_len = len(alias_lower)
                if len(token_lower) > alias_len + 1 and alias_len >= 3:
                    for i in range(len(token_lower) - alias_len + 2):
                        end = min(i + alias_len + 1, len(token_lower))
                        sub = token_lower[i:end]
                        score = SequenceMatcher(None, sub, alias_lower).ratio()
                        if score > best_score and score >= threshold:
                            best_score = score
                            best_match = product_name

    return best_match


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


# =============================================================================
# Mapping: problem_type → product_category ใน products table
# =============================================================================
PROBLEM_TYPE_TO_PRODUCT_CATEGORY = {
    'disease': 'ป้องกันโรค',
    'insect': 'กำจัดแมลง',
    'nutrient': 'ปุ๋ยและสารบำรุง',
    'weed': 'กำจัดวัชพืช'
}


# =============================================================================
# Legacy functions removed: vector_search_products_for_qa,
# answer_qa_with_vector_search, answer_agriculture_question,
# is_usage_question, answer_usage_question
# All Q&A routing now goes through AgenticRAG pipeline
# =============================================================================


async def classify_message_intent(message: str) -> str:
    """
    Classify user message intent using LLM (gpt-4o-mini).
    Returns: 'product_qa' | 'general_chat' | 'greeting'
    """
    try:
        if not openai_client:
            # Keyword fallback
            return _keyword_classify_intent(message)

        response = await openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": INTENT_CLASSIFICATION_PROMPT
                },
                {"role": "user", "content": message}
            ],
            temperature=0,
            max_tokens=20
        )

        result = response.choices[0].message.content.strip().lower()

        if result in ('product_qa', 'general_chat', 'greeting'):
            return result

        # LLM returned unexpected value → keyword fallback
        return _keyword_classify_intent(message)

    except Exception as e:
        logger.warning(f"classify_message_intent error: {e}, using keyword fallback")
        return _keyword_classify_intent(message)


def _keyword_classify_intent(message: str) -> str:
    """Keyword-based intent classification fallback"""
    message_lower = message.lower()

    # Greeting check
    greeting_keywords = ["สวัสดี", "ดีจ้า", "หวัดดี", "hello", "hi", "ดีค่ะ", "ดีครับ"]
    if any(kw in message_lower for kw in greeting_keywords) and len(message.strip()) < 30:
        return "greeting"

    # Follow-up keywords (usage questions that imply product context)
    followup_keywords = ["ใช้ยังไง", "ผสมกี่", "ใช้เท่าไหร่", "ใช้ช่วงไหน",
                         "อัตราผสม", "ใช้กี่", "พ่นกี่", "ฉีดกี่", "กี่ลิตร",
                         "กี่ซีซี", "ใช้ได้ไหม", "ใช้ตอนไหน", "ใช้กับ"]
    if any(kw in message_lower for kw in followup_keywords):
        return "product_qa"

    # Product/agriculture check
    has_product = extract_product_name_from_question(message) is not None
    has_agri = is_agriculture_question(message)
    has_product_kw = is_product_question(message)

    if has_product or has_agri or has_product_kw:
        return "product_qa"

    return "general_chat"



async def handle_natural_conversation(user_id: str, message: str) -> str:
    """Handle natural conversation with simplified intent-based routing.

    Flow:
    1. Add message to memory
    2. Get enhanced context
    3. Classify intent (LLM-based)
    4. Route: greeting → greeting response, product_qa → AgenticRAG, general_chat → general chat LLM
    """
    try:
        # 1. Add user message to memory
        await add_to_memory(user_id, "user", message)

        # 2. Get enhanced conversation context
        context = await get_enhanced_context(user_id)

        # 3. Classify intent
        intent = await classify_message_intent(message)
        logger.info(f"Classified intent: {intent} for message: {message[:50]}...")

        # 4. Route based on intent
        if intent == "greeting":
            logger.info("Routing to greeting response")
            import random
            answer = random.choice(GREETINGS)
            await add_to_memory(user_id, "assistant", answer)
            return answer

        elif intent == "product_qa":
            logger.info("Routing to AgenticRAG pipeline")

            # Use AgenticRAG
            agentic_rag = _get_agentic_rag()
            if agentic_rag:
                rag_response = await agentic_rag.process(message, context, user_id)

                # Check if AgenticRAG wants to fallback to general chat
                if rag_response.answer is None:
                    logger.info("AgenticRAG returned None, falling back to general chat")
                    # Fall through to general chat below
                else:
                    answer = rag_response.answer
                    logger.info(f"AgenticRAG response: confidence={rag_response.confidence:.2f}, grounded={rag_response.is_grounded}")

                    # Track analytics for product recommendations
                    try:
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
                                    disease_name="AgenticRAG",
                                    products=product_names[:5]
                                )
                                logger.info(f"Tracked {len(product_names)} products from AgenticRAG")
                    except Exception as track_err:
                        logger.warning(f"Analytics tracking failed: {track_err}")

                    # Add assistant response to memory with product metadata
                    memory_metadata = {}
                    detected_products = []
                    try:
                        for pname, aliases in ICP_PRODUCT_NAMES.items():
                            for alias in aliases:
                                if alias.lower() in answer.lower():
                                    detected_products.append({"product_name": pname})
                                    break
                        if detected_products:
                            memory_metadata = {
                                "type": "product_recommendation",
                                "products": detected_products[:3]
                            }
                    except Exception:
                        pass
                    await add_to_memory(user_id, "assistant", answer, metadata=memory_metadata)
                    return answer
            else:
                logger.warning("AgenticRAG not available")

        # General chat (intent == "general_chat" or fallback)
        logger.info("Routing to general chat")

        system_prompt = GENERAL_CHAT_PROMPT

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
            temperature=0.7
        )
        answer = post_process_answer(response.choices[0].message.content)

        # Add assistant response to memory
        await add_to_memory(user_id, "assistant", answer)
        return answer

    except Exception as e:
        logger.error(f"Error in natural conversation: {e}", exc_info=True)
        return ERROR_GENERIC