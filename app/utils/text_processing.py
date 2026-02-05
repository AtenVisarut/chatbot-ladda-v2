import re
from typing import List, Dict

# Allowed emojis: 😊 (U+1F60A) and 🌱 (U+1F331)
_ALLOWED_EMOJIS = {'\U0001F60A', '\U0001F331'}

# Unicode ranges covering most emoji (simplified but effective)
_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # Emoticons
    "\U0001F300-\U0001F5FF"  # Misc Symbols and Pictographs
    "\U0001F680-\U0001F6FF"  # Transport and Map
    "\U0001F1E0-\U0001F1FF"  # Flags
    "\U0001F900-\U0001F9FF"  # Supplemental Symbols
    "\U0001FA00-\U0001FA6F"  # Chess Symbols
    "\U0001FA70-\U0001FAFF"  # Symbols Extended-A
    "\U00002702-\U000027B0"  # Dingbats
    "\U000024C2-\U0001F251"  # Enclosed characters
    "\U0000FE0F"             # Variation Selector
    "\U00002600-\U000026FF"  # Misc Symbols (☀️⚠️⚡ etc.)
    "\U00002700-\U000027BF"  # Dingbats
    "\U0000200D"             # ZWJ
    "\U00002B50"             # Star
    "\U0000203C\U00002049"   # Exclamation marks
    "\U000023E9-\U000023F3"  # Media symbols
    "\U000023F8-\U000023FA"  # Media symbols
    "]+",
    flags=re.UNICODE
)

def _strip_banned_emojis(text: str) -> str:
    """Remove all emojis except 😊 and 🌱"""
    def _replace(match):
        chars = match.group()
        # Keep only allowed emojis from the matched span
        kept = ''.join(c for c in chars if c in _ALLOWED_EMOJIS)
        return kept
    return _EMOJI_PATTERN.sub(_replace, text)


def post_process_answer(answer: str) -> str:
    """Post-process Gemini answer for better quality"""
    if not answer:
        return ""
    
    # 1. Remove markdown formatting
    answer = answer.replace("```", "")
    answer = answer.replace("**", "")
    answer = answer.replace("##", "")
    answer = answer.replace("###", "")
    answer = re.sub(r'\*\*([^*]+)\*\*', r'\1', answer)  # **text** → text
    answer = re.sub(r'\*([^*]+)\*', r'\1', answer)  # *text* → text
    
    # 2. Fix Thai encoding issues
    answer = re.sub(r'([ก-ฮ])Ğ([ำิีุูเแโใไ่้๊๋])', r'\1\2', answer)
    answer = answer.replace('Ğ', '')
    answer = answer.replace('', '')
    answer = answer.replace('\x00', '')
    
    # 3. Fix spacing issues (preserve newlines!)
    # Only collapse multiple spaces within lines, preserve newlines
    answer = re.sub(r'[ \t]+', ' ', answer)  # Multiple spaces/tabs → single space (preserve \n)
    answer = answer.replace(' ,', ',')
    answer = answer.replace(' .', '.')
    answer = answer.replace(' :', ':')
    answer = answer.replace('( ', '(')
    answer = answer.replace(' )', ')')
    
    # 4. Fix bullet points (convert markdown to Thai style)
    answer = re.sub(r'^\s*[-*]\s+', '• ', answer, flags=re.MULTILINE)
    answer = re.sub(r'\n\s*[-*]\s+', '\n• ', answer)
    
    # 5. Ensure proper line breaks
    answer = re.sub(r'\n{3,}', '\n\n', answer)  # Max 2 line breaks
    
    # 6. Remove leading/trailing whitespace
    answer = answer.strip()
    
    # 7. Fix common Thai typos
    answer = answer.replace('ต้', 'ต้')
    answer = answer.replace('ต', 'ต')
    
    # 8. Strip all emojis except 😊 and 🌱
    answer = _strip_banned_emojis(answer)

    # 9. Normalize dividers to standard format
    answer = re.sub(r'^[-=─]{3,}$', '━━━━━━━━━━━━━━━', answer, flags=re.MULTILINE)

    # 10. Remove old [หัวข้อ] bracket format (fallback cleanup)
    answer = re.sub(r'^\[([^\]]+)\]\s*$', r'\1', answer, flags=re.MULTILINE)

    return answer

def clean_knowledge_text(text: str) -> str:
    """Clean and format knowledge text for better readability"""
    if not text:
        return ""
    
    # Fix encoding issues - remove corrupted characters
    # Common patterns: จĞำ, ลĞำ, ทĞำ, นĞ้ำ, กĞำ
    text = re.sub(r'([ก-ฮ])Ğ([ำ])', r'\1\2', text)  # จĞำ → จำ
    text = re.sub(r'([ก-ฮ])Ğ([้])', r'\1\2', text)  # นĞ้ → น้
    text = re.sub(r'([ก-ฮ])Ğ([ิ])', r'\1\2', text)  # กĞิ → กิ
    text = re.sub(r'([ก-ฮ])Ğ([ี])', r'\1\2', text)  # กĞี → กี
    text = re.sub(r'([ก-ฮ])Ğ([ุ])', r'\1\2', text)  # กĞุ → กุ
    text = re.sub(r'([ก-ฮ])Ğ([ู])', r'\1\2', text)  # กĞู → กู
    text = re.sub(r'([ก-ฮ])Ğ([่])', r'\1\2', text)  # กĞ่ → ก่
    text = re.sub(r'([ก-ฮ])Ğ([้])', r'\1\2', text)  # กĞ้ → ก้
    text = re.sub(r'([ก-ฮ])Ğ([๊])', r'\1\2', text)  # กĞ๊ → ก๊
    text = re.sub(r'([ก-ฮ])Ğ([๋])', r'\1\2', text)  # กĞ๋ → ก๋
    text = re.sub(r'Ğ', '', text)  # Remove remaining Ğ
    
    # Fix other corrupted characters
    text = text.replace('ต้', 'ต้')  # Fix tone marks
    text = text.replace('ต', 'ต')
    text = text.replace('', '')  # Remove replacement character
    text = text.replace('\x00', '')  # Remove null character
    
    # Fix common Thai encoding issues
    text = text.replace('à¸', '')  # Remove Thai encoding prefix
    text = text.replace('à¹', '')  # Remove Thai encoding prefix
    
    # Remove excessive whitespace
    text = ' '.join(text.split())
    
    # Fix common issues
    text = text.replace('  ', ' ')  # Double spaces
    text = text.replace(' ,', ',')  # Space before comma
    text = text.replace(' .', '.')  # Space before period
    text = text.replace('( ', '(')  # Space after opening parenthesis
    text = text.replace(' )', ')')  # Space before closing parenthesis
    text = text.replace(' :', ':')  # Space before colon
    
    # Fix Thai-specific issues (keep important marks)
    # text = text.replace('ฺ', '')  # Keep Thai character above
    # text = text.replace('์', '')  # Keep Thai character above
    
    # Remove multiple consecutive spaces
    text = re.sub(r'\s+', ' ', text)
    
    # Ensure proper sentence spacing
    text = re.sub(r'([.!?])\s*([A-Za-zก-๙])', r'\1 \2', text)
    
    # Remove leading/trailing whitespace
    text = text.strip()
    
    # Remove lines with only special characters
    lines = text.split('\n')
    cleaned_lines = [line for line in lines if line.strip() and not re.match(r'^[^\w\s]+$', line.strip())]
    text = '\n'.join(cleaned_lines)
    
    return text

def extract_keywords_from_question(question: str) -> dict:
    """Extract main keywords from question with categories"""
    question_lower = question.lower()
    # Normalize simple punctuation to spaces for better matching
    question_norm = re.sub(r'[\.,\?\!\:\;\(\)\/]',' ', question_lower)
    
    # Pest/Disease keywords (expanded)
    pest_keywords = [
        # Thai - แมลง
        "เพลี้ยไฟ", "เพลี้ยอ่อน", "เพลี้ย", "หนอน", "แมลง", "ด้วงงวง",
        "จักจั่น", "หนอนเจาะ", "หนอนกอ", "หนอนใย", "ด้วง", "มด", "ปลวก",
        "เพลี้ยจักจั่น", "แมลงวันผล", "แมลงหวี่ขาว", "ทริปส์",
        "ศัตรูพืช", "ไร", "เพลี้ยแป้ง", "หนอนกระทู้ข้าว",
        # Thai - โรคเชื้อรา
        "ราน้ำค้าง", "ราแป้ง", "ราสนิม", "เชื้อรา", "รา", "แอนแทรคโนส",
        "โรคผลเน่า", "ผลเน่า", "โรคใบไหม้", "ใบไหม้", "โรคราดำ", "ราดำ",
        "โรคใบจุด", "ใบจุด", "โรคกิ่งแห้ง", "กิ่งแห้ง", "โรครากเน่า", "รากเน่า",
        "โรคลำต้นเน่า", "ลำต้นเน่า", "โรคโคนเน่า", "โคนเน่า",
        # Thai - ไวรัส
        "ไวรัส", "โรคใบด่าง", "โรคใบหงิก", "โรคจู๋", "โรคเหลือง",
        # Thai - วัชพืช
        "วัชพืช", "หญ้า", "ผักบุ้ง", "หญ้าคา",
        # Thai - ทั่วไป
        "โรคพืช", "โรค",
        # English
        "aphid", "thrips", "whitefly", "moth", "caterpillar", "worm", "beetle",
        "mildew", "powdery mildew", "rust", "fungus", "fungal", "anthracnose",
        "virus", "viral", "disease", "weed", "grass", "mite", "borer", "leaf miner",
        "insect", "pest", "armyworm", "thrips", "fruit rot", "root rot", "stem rot"
    ]
    
    # Crop keywords (expanded)
    crop_keywords = [
        # Thai
        "ทุเรียน", "มะม่วง", "ข้าว", "พืชผัก", "ผัก", "ผลไม้",
        "มะนาว", "ส้ม", "กล้วย", "มะพร้าว", "ยางพารา", "ปาล์ม",
        "ข้าวโพด", "อ้อย", "มันสำปะหลัง", "ถั่ว", "พริก", "มะเขือเทศ",
        "ลำไย", "ลิ้นจี่", "เงาะ", "มังคุด", "ฝรั่ง", "ชมพู่",
        # English
        "durian", "mango", "rice", "vegetable", "vegetables", "fruit",
        "lime", "orange", "banana", "coconut", "rubber", "palm",
        "corn", "sugarcane", "cassava", "peanut", "chilli", "tomato",
        "longan", "lychee", "rambutan", "mangosteen", "guava"
    ]
    
    # Product-related keywords
    product_keywords = [
        # Thai
        "ผลิตภัณฑ์", "สินค้า", "ยา", "สาร", "ปุ๋ย",
        "icp", "ladda", "icpl", "ไอซีพี", "ลัดดา",
        "โมเดิน", "ไดอะซินอน", "อิมิดาโคลพริด", "ไซเพอร์เมทริน",
        "แนะนำ", "ใช้", "พ่น", "ฉีด", "กำจัด", "ป้องกัน",
        # English
        "product", "products", "fertilizer", "pesticide", "insecticide", "fungicide", "recommend"
    ]

    # Fertilizer-specific keywords (NEW)
    fertilizer_keywords = [
        # ประเภทปุ๋ย/สารบำรุง
        "ปุ๋ย", "สารบำรุง", "ธาตุอาหาร", "ฮอร์โมน", "สารเร่ง",
        "ปุ๋ยเคมี", "ปุ๋ยอินทรีย์", "ปุ๋ยชีวภาพ",
        # ชื่อสินค้าปุ๋ย ICP (จาก CSV)
        "กระรัต", "การูก้า", "คอนทาฟ", "ซอยบอม", "ซีเอ็มจี",
        "ท๊อปกัน", "พานาส", "ราเซอร์", "เวคเตอร์", "รีโนเวท",
        "อิมิดาโกลด์", "เกรค", "เทอราโน", "เมทามอร์ป", "แมสฟอร์ด",
        "แอนดาแม็กซ์", "แอ็คนาว", "โฮป", "ไกลโฟเสท", "อัพดาว",
        "ไดพิม", "ไฮซีส", "บอมส์", "พรีดิคท์", "วอแรนด์",
        "อินเนอร์", "เบนซาน่า", "แจ๊ส", "นาแดน", "คาซ่า",
        "ซิมเมอร์", "อาทราซีน", "คาริสมา",
        # ประเภทสารเคมี
        "สารกำจัดแมลง", "สารป้องกันโรค", "สารกำจัดวัชพืช",
        "ยาฆ่าแมลง", "ยาฆ่าหญ้า", "ยาฆ่าเชื้อรา",
        # คำถามเกี่ยวกับปุ๋ย
        "อัตราใช้", "อัตราผสม", "วิธีใช้ปุ๋ย", "ใส่ปุ๋ย",
        # English
        "fertilizer", "nutrient", "hormone", "chemical"
    ]
    
    # Intent keywords (NEW)
    intent_keywords = {
        "increase_yield": [
            # Thai
            "เพิ่มผลผลิต", "ผลผลิตสูง", "ผลผลิตมาก", "ผลผลิตดี", "ผลผลิตเยอะ", "ผลผลิตขึ้น", "ผลผลิตดีขึ้น", "ผลผลิตเพิ่ม",
            # English
            "increase yield", "higher yield", "more yield", "increase production", "boost yield", "increase harvest"
        ],
        "solve_problem": [
            # Thai
            "แก้ปัญหา", "แก้ไข", "รักษา", "กำจัด", "ป้องกัน", "ควบคุม", "แก้โรค", "แก้",
            # English
            "solve problem", "control", "kill", "manage pest", "prevent", "control pest", "treat"
        ],
        "general_care": [
            # Thai
            "ดูแล", "บำรุง", "เลี้ยง", "ปลูก", "ใส่ปุ๋ย",
            # English
            "care", "fertilize", "general care", "maintenance", "nurture"
        ],
        "product_inquiry": [
            # Thai - เพิ่ม patterns สำหรับถามหาสินค้า
            "มีอะไรบ้าง", "มีไหม", "แนะนำ", "ควรใช้", "ใช้อะไร", "ซื้อ",
            "ตัวไหน", "ยาอะไร", "ใช้ตัวไหน", "ใช้ยาอะไร", "พ่นอะไร", "ฉีดอะไร",
            "สารอะไร", "ใช้สารอะไร", "ใช้อะไรดี", "ตัวไหนดี", "ยาตัวไหน",
            "มียาอะไร", "มีตัวไหน", "ได้บ้าง", "บ้าง",
            # English
            "what products", "what is available", "recommend product", "recommend", "what to use", "is there"
        ]
    }
    
    found = {
        "pests": [],
        "crops": [],
        "products": [],
        "fertilizers": [],  # NEW: fertilizer keywords
        "intent": None,  # NEW: detect user intent
        "is_product_query": False,
        "is_fertilizer_query": False  # NEW: flag for fertilizer questions
    }
    
    # Extract pests
    for keyword in pest_keywords:
        if keyword in question_norm:
            found["pests"].append(keyword)
    
    # Extract crops
    for keyword in crop_keywords:
        if keyword in question_norm:
            found["crops"].append(keyword)
    
    # Extract product-related
    for keyword in product_keywords:
        if keyword in question_norm:
            found["products"].append(keyword)
            found["is_product_query"] = True

    # Extract fertilizer-related (NEW)
    for keyword in fertilizer_keywords:
        if keyword in question_norm:
            found["fertilizers"].append(keyword)
            found["is_fertilizer_query"] = True
            found["is_product_query"] = True

    # Detect intent (NEW)
    # Detect intent (MATCH ON NORMALIZED TEXT)
    for intent, keywords in intent_keywords.items():
        for keyword in keywords:
            if keyword in question_norm:
                found["intent"] = intent
                found["is_product_query"] = True
                break
        if found["intent"]:
            break
    
    return found


def generate_thai_disease_variants(disease_name: str) -> List[str]:
    """
    Generate Thai disease name variants for fuzzy matching.

    Thai farmers commonly drop "สี" (color) from disease names:
      ราสีชมพู → ราชมพู, จุดสีน้ำตาล → จุดน้ำตาล

    Also handles โรค prefix add/remove.

    Returns list of variants including the original name.
    """
    variants = {disease_name}

    # Strip โรค prefix for matching, but also keep variant with it
    bare = disease_name
    if bare.startswith("โรค"):
        bare = bare[len("โรค"):]
        variants.add(bare)
    else:
        variants.add("โรค" + bare)

    _COLORS = ["ชมพู", "น้ำตาล", "เทา", "ขาว", "ดำ", "ม่วง", "เหลือง", "ส้ม"]

    for color in _COLORS:
        # รา+สี+color ↔ รา+color
        with_si = f"ราสี{color}"
        without_si = f"รา{color}"
        if with_si in bare or without_si in bare:
            variants.add(bare.replace(with_si, without_si))
            variants.add(bare.replace(without_si, with_si))
            variants.add("โรค" + bare.replace(with_si, without_si))
            variants.add("โรค" + bare.replace(without_si, with_si))

        # จุด+สี+color ↔ จุด+color
        jud_with_si = f"จุดสี{color}"
        jud_without_si = f"จุด{color}"
        if jud_with_si in bare or jud_without_si in bare:
            variants.add(bare.replace(jud_with_si, jud_without_si))
            variants.add(bare.replace(jud_without_si, jud_with_si))
            variants.add("โรค" + bare.replace(jud_with_si, jud_without_si))
            variants.add("โรค" + bare.replace(jud_without_si, jud_with_si))

    return list(variants)
