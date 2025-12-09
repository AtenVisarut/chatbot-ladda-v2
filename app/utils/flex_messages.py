"""
LINE Flex Message Templates
สำหรับ Chatbot Ladda - Plant Disease Detection
"""

from typing import Dict, List, Optional


# =============================================================================
# Helper Functions สำหรับ format ข้อความให้อ่านง่าย
# =============================================================================

def _format_symptoms(symptoms: str) -> str:
    """Format อาการที่พบให้กระชับและอ่านง่าย"""
    if not symptoms:
        return "ไม่พบข้อมูลอาการ"

    # ลบคำซ้ำและ format ใหม่
    symptoms = symptoms.strip()

    # ถ้าสั้นอยู่แล้ว ส่งคืนเลย
    if len(symptoms) <= 200:
        return symptoms

    # ตัดที่ประโยคแรกๆ ไม่ให้ขาดกลางคำ
    # หาจุดตัดที่เหมาะสม (จุด, เครื่องหมาย |, หรือ comma)
    cut_point = 200
    for sep in ['. ', ' | ', ', ', ' ']:
        idx = symptoms.rfind(sep, 0, 250)
        if idx > 100:
            cut_point = idx + len(sep)
            break

    return symptoms[:cut_point].strip()


def _get_severity_label(severity: str) -> str:
    """แปลง severity เป็น label สั้นๆ"""
    if not severity:
        return "ปานกลาง"

    severity_lower = severity.lower()

    if any(x in severity_lower for x in ['รุนแรง', 'สูง', 'มาก', 'severe', 'high']):
        return "รุนแรง"
    elif any(x in severity_lower for x in ['เล็กน้อย', 'ต่ำ', 'น้อย', 'mild', 'low', 'light']):
        return "เล็กน้อย"
    else:
        return "ปานกลาง"


def _get_severity_color(severity: str) -> str:
    """ให้สีตามระดับความรุนแรง"""
    label = _get_severity_label(severity)

    if label == "รุนแรง":
        return "#E74C3C"  # Red
    elif label == "เล็กน้อย":
        return "#27AE60"  # Green
    else:
        return "#F39C12"  # Orange


def _format_recommendation(raw_analysis: str) -> str:
    """Format คำแนะนำให้กระชับ ไม่ตัดกลางประโยค"""
    if not raw_analysis:
        return "ควรปรึกษาผู้เชี่ยวชาญเพื่อการรักษาที่เหมาะสม"

    # แยกส่วนต่างๆ ออก
    parts = raw_analysis.split(' | ')

    # เอาส่วนคำแนะนำหลัก (ส่วนแรกมักเป็นคำอธิบาย)
    main_part = parts[0] if parts else raw_analysis

    # ถ้ามีคำแนะนำเพิ่มเติมที่สำคัญ เช่น "แยกจาก:"
    extra_info = ""
    for part in parts[1:]:
        if "แยกจาก" in part or "หมายเหตุ" in part:
            extra_info = "\n" + part.strip()
            break

    result = main_part.strip()

    # ถ้ายาวเกิน 300 ตัวอักษร ตัดที่ประโยค
    if len(result) > 300:
        # หาจุดตัดที่เหมาะสม
        cut_point = 300
        for sep in ['. ', '। ', ' - ']:
            idx = result.rfind(sep, 0, 350)
            if idx > 150:
                cut_point = idx + len(sep)
                break
        result = result[:cut_point].strip()

    return result + extra_info


def _parse_root_cause_data(raw_analysis: str) -> Dict:
    """Parse Root Cause Analysis data จาก raw_analysis string"""
    data = {
        "plant_type": "",
        "key_features": "",
        "possible_causes": "",
        "cause_chain": "",
        "contributing_factors": "",
        "risk_factors": "",
        "prevention": "",
        "treatment_priority": ""
    }

    if not raw_analysis:
        return data

    # Parse แต่ละส่วนจาก raw_analysis
    parts = raw_analysis.split(' | ')

    for part in parts:
        part = part.strip()
        if part.startswith("ชนิดพืช:"):
            data["plant_type"] = part.replace("ชนิดพืช:", "").strip()
        elif part.startswith("ลักษณะสำคัญ:"):
            data["key_features"] = part.replace("ลักษณะสำคัญ:", "").strip()
        elif part.startswith("สาเหตุที่เป็นไปได้:"):
            data["possible_causes"] = part.replace("สาเหตุที่เป็นไปได้:", "").strip()
        elif part.startswith("ลำดับสาเหตุ:"):
            data["cause_chain"] = part.replace("ลำดับสาเหตุ:", "").strip()
        elif part.startswith("ปัจจัยเสริม:"):
            data["contributing_factors"] = part.replace("ปัจจัยเสริม:", "").strip()
        elif part.startswith("ปัจจัยเสี่ยง:"):
            data["risk_factors"] = part.replace("ปัจจัยเสี่ยง:", "").strip()
        elif part.startswith("การป้องกัน:"):
            data["prevention"] = part.replace("การป้องกัน:", "").strip()
        elif part.startswith("ความเร่งด่วน:"):
            data["treatment_priority"] = part.replace("ความเร่งด่วน:", "").strip()

    return data


def _get_priority_color(priority: str) -> str:
    """ให้สีตามระดับความเร่งด่วน"""
    if not priority:
        return "#888888"

    priority_lower = priority.lower()
    if any(x in priority_lower for x in ['เร่งด่วน', 'urgent', 'critical', 'ด่วน']):
        return "#E74C3C"  # Red
    elif any(x in priority_lower for x in ['ไม่เร่งด่วน', 'low', 'ไม่ด่วน']):
        return "#27AE60"  # Green
    else:
        return "#F39C12"  # Orange


def _create_root_cause_section(raw_analysis: str) -> List[Dict]:
    """สร้าง Flex contents สำหรับ Root Cause Analysis section"""
    contents = []
    data = _parse_root_cause_data(raw_analysis)

    # ถ้าไม่มีข้อมูล Root Cause ให้ return empty list
    has_data = any([
        data["possible_causes"],
        data["cause_chain"],
        data["risk_factors"],
        data["prevention"]
    ])

    if not has_data:
        return contents

    # Separator ก่อน Root Cause Section
    contents.append({
        "type": "separator",
        "margin": "lg"
    })

    # Header สำหรับ Root Cause Analysis
    contents.append({
        "type": "text",
        "text": "🔬 การวิเคราะห์เชิงลึก",
        "size": "sm",
        "weight": "bold",
        "color": "#8E44AD",
        "margin": "lg"
    })

    # 1. สาเหตุที่เป็นไปได้
    if data["possible_causes"]:
        contents.append({
            "type": "box",
            "layout": "vertical",
            "margin": "md",
            "contents": [
                {
                    "type": "text",
                    "text": "📊 สาเหตุที่เป็นไปได้:",
                    "size": "xs",
                    "color": "#E67E22",
                    "weight": "bold"
                },
                {
                    "type": "text",
                    "text": data["possible_causes"][:150],
                    "size": "xs",
                    "color": "#333333",
                    "wrap": True,
                    "margin": "sm"
                }
            ]
        })

    # 2. ลำดับสาเหตุ (Cause Chain)
    if data["cause_chain"]:
        contents.append({
            "type": "box",
            "layout": "vertical",
            "margin": "md",
            "contents": [
                {
                    "type": "text",
                    "text": "🔗 ลำดับสาเหตุ:",
                    "size": "xs",
                    "color": "#3498DB",
                    "weight": "bold"
                },
                {
                    "type": "text",
                    "text": data["cause_chain"][:150],
                    "size": "xs",
                    "color": "#333333",
                    "wrap": True,
                    "margin": "sm"
                }
            ]
        })

    # 3. ปัจจัยเสี่ยง
    if data["risk_factors"]:
        contents.append({
            "type": "box",
            "layout": "vertical",
            "margin": "md",
            "contents": [
                {
                    "type": "text",
                    "text": "⚠️ ปัจจัยเสี่ยง:",
                    "size": "xs",
                    "color": "#E74C3C",
                    "weight": "bold"
                },
                {
                    "type": "text",
                    "text": data["risk_factors"][:100],
                    "size": "xs",
                    "color": "#333333",
                    "wrap": True,
                    "margin": "sm"
                }
            ]
        })

    # 4. การป้องกัน
    if data["prevention"]:
        contents.append({
            "type": "box",
            "layout": "vertical",
            "margin": "md",
            "contents": [
                {
                    "type": "text",
                    "text": "🛡️ การป้องกัน:",
                    "size": "xs",
                    "color": "#27AE60",
                    "weight": "bold"
                },
                {
                    "type": "text",
                    "text": data["prevention"][:100],
                    "size": "xs",
                    "color": "#333333",
                    "wrap": True,
                    "margin": "sm"
                }
            ]
        })

    # 5. ความเร่งด่วน
    if data["treatment_priority"]:
        priority_color = _get_priority_color(data["treatment_priority"])
        contents.append({
            "type": "box",
            "layout": "horizontal",
            "margin": "md",
            "contents": [
                {
                    "type": "text",
                    "text": "🚨 ความเร่งด่วน:",
                    "size": "xs",
                    "color": "#888888",
                    "flex": 0
                },
                {
                    "type": "text",
                    "text": data["treatment_priority"][:50],
                    "size": "xs",
                    "color": priority_color,
                    "weight": "bold",
                    "margin": "sm",
                    "wrap": True
                }
            ]
        })

    return contents


def create_welcome_flex() -> Dict:
    """
    สร้าง Flex Message สำหรับต้อนรับ user ใหม่
    """
    return {
        "type": "flex",
        "altText": "ยินดีต้อนรับสู่ Chatbot Ladda",
        "contents": {
            "type": "bubble",
            "size": "giga",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "text",
                                "text": "CHATBOT LADDA",
                                "color": "#ffffff",
                                "size": "xl",
                                "weight": "bold",
                                "align": "center"
                            },
                            {
                                "type": "text",
                                "text": "ผู้ช่วยด้านการเกษตรอัจฉริยะ",
                                "color": "#ffffff",
                                "size": "sm",
                                "align": "center",
                                "margin": "sm"
                            }
                        ]
                    }
                ],
                "backgroundColor": "#27AE60",
                "paddingAll": "20px"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "ยินดีต้อนรับค่ะ!",
                        "weight": "bold",
                        "size": "xl",
                        "margin": "md",
                        "color": "#27AE60"
                    },
                    {
                        "type": "text",
                        "text": "ฉันคือผู้ช่วยที่จะช่วยคุณดูแลพืชผล",
                        "size": "sm",
                        "color": "#666666",
                        "margin": "md",
                        "wrap": True
                    },
                    {
                        "type": "separator",
                        "margin": "lg"
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "margin": "lg",
                        "spacing": "md",
                        "contents": [
                            {
                                "type": "box",
                                "layout": "horizontal",
                                "contents": [
                                    {
                                        "type": "text",
                                        "text": "🔍",
                                        "size": "xl",
                                        "flex": 0
                                    },
                                    {
                                        "type": "box",
                                        "layout": "vertical",
                                        "contents": [
                                            {
                                                "type": "text",
                                                "text": "วิเคราะห์โรคพืช",
                                                "weight": "bold",
                                                "size": "sm"
                                            },
                                            {
                                                "type": "text",
                                                "text": "ส่งรูปใบพืชมาวิเคราะห์โรค",
                                                "size": "xs",
                                                "color": "#888888"
                                            }
                                        ],
                                        "margin": "md"
                                    }
                                ]
                            },
                            {
                                "type": "box",
                                "layout": "horizontal",
                                "contents": [
                                    {
                                        "type": "text",
                                        "text": "💊",
                                        "size": "xl",
                                        "flex": 0
                                    },
                                    {
                                        "type": "box",
                                        "layout": "vertical",
                                        "contents": [
                                            {
                                                "type": "text",
                                                "text": "แนะนำผลิตภัณฑ์",
                                                "weight": "bold",
                                                "size": "sm"
                                            },
                                            {
                                                "type": "text",
                                                "text": "รับคำแนะนำยาและปุ๋ยที่เหมาะสม",
                                                "size": "xs",
                                                "color": "#888888"
                                            }
                                        ],
                                        "margin": "md"
                                    }
                                ]
                            },
                            {
                                "type": "box",
                                "layout": "horizontal",
                                "contents": [
                                    {
                                        "type": "text",
                                        "text": "💬",
                                        "size": "xl",
                                        "flex": 0
                                    },
                                    {
                                        "type": "box",
                                        "layout": "vertical",
                                        "contents": [
                                            {
                                                "type": "text",
                                                "text": "ถาม-ตอบการเกษตร",
                                                "weight": "bold",
                                                "size": "sm"
                                            },
                                            {
                                                "type": "text",
                                                "text": "สอบถามปัญหาเกี่ยวกับพืช",
                                                "size": "xs",
                                                "color": "#888888"
                                            }
                                        ],
                                        "margin": "md"
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "type": "separator",
                        "margin": "lg"
                    },
                    {
                        "type": "text",
                        "text": "📝 กรุณาลงทะเบียนเพื่อเริ่มใช้งาน",
                        "size": "sm",
                        "color": "#E74C3C",
                        "margin": "lg",
                        "weight": "bold",
                        "align": "center"
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "height": "sm",
                        "action": {
                            "type": "message",
                            "label": "📝 ลงทะเบียน",
                            "text": "ลงทะเบียน"
                        },
                        "color": "#27AE60"
                    },
                    {
                        "type": "button",
                        "style": "secondary",
                        "height": "sm",
                        "action": {
                            "type": "message",
                            "label": "📖 วิธีใช้งาน",
                            "text": "วิธีใช้งาน"
                        }
                    }
                ],
                "flex": 0
            }
        }
    }


def create_registration_required_flex() -> Dict:
    """
    สร้าง Flex Message แจ้งเตือนให้ลงทะเบียนก่อนใช้งาน
    """
    return {
        "type": "flex",
        "altText": "กรุณาลงทะเบียนก่อนใช้งาน",
        "contents": {
            "type": "bubble",
            "size": "kilo",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "⚠️ กรุณาลงทะเบียน",
                        "color": "#ffffff",
                        "size": "lg",
                        "weight": "bold",
                        "align": "center"
                    }
                ],
                "backgroundColor": "#E74C3C",
                "paddingAll": "15px"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "เพื่อให้บริการคุณได้ดียิ่งขึ้น",
                        "size": "sm",
                        "color": "#666666",
                        "align": "center",
                        "wrap": True
                    },
                    {
                        "type": "text",
                        "text": "กรุณาลงทะเบียนข้อมูลพื้นฐานก่อนนะคะ",
                        "size": "sm",
                        "color": "#666666",
                        "align": "center",
                        "wrap": True,
                        "margin": "sm"
                    },
                    {
                        "type": "separator",
                        "margin": "lg"
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "margin": "lg",
                        "contents": [
                            {
                                "type": "text",
                                "text": "ข้อมูลที่ต้องกรอก:",
                                "size": "sm",
                                "weight": "bold"
                            },
                            {
                                "type": "text",
                                "text": "• ชื่อ-นามสกุล",
                                "size": "xs",
                                "color": "#888888",
                                "margin": "sm"
                            },
                            {
                                "type": "text",
                                "text": "• เบอร์โทรศัพท์",
                                "size": "xs",
                                "color": "#888888"
                            },
                            {
                                "type": "text",
                                "text": "• จังหวัด",
                                "size": "xs",
                                "color": "#888888"
                            },
                            {
                                "type": "text",
                                "text": "• พืชที่ปลูก",
                                "size": "xs",
                                "color": "#888888"
                            }
                        ]
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "height": "sm",
                        "action": {
                            "type": "message",
                            "label": "📝 ลงทะเบียนเลย",
                            "text": "ลงทะเบียน"
                        },
                        "color": "#27AE60"
                    }
                ]
            }
        }
    }


def create_registration_complete_flex(
    name: str,
    phone: str,
    province: str,
    crops: List[str]
) -> Dict:
    """
    สร้าง Flex Message สรุปการลงทะเบียนสำเร็จ
    """
    crops_text = ", ".join(crops) if crops else "ไม่ระบุ"

    return {
        "type": "flex",
        "altText": "ลงทะเบียนสำเร็จ!",
        "contents": {
            "type": "bubble",
            "size": "kilo",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "✅ ลงทะเบียนสำเร็จ!",
                        "color": "#ffffff",
                        "size": "lg",
                        "weight": "bold",
                        "align": "center"
                    }
                ],
                "backgroundColor": "#27AE60",
                "paddingAll": "15px"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "contents": [
                            {
                                "type": "text",
                                "text": "👤 ชื่อ",
                                "size": "sm",
                                "color": "#888888",
                                "flex": 2
                            },
                            {
                                "type": "text",
                                "text": name,
                                "size": "sm",
                                "color": "#333333",
                                "flex": 4,
                                "weight": "bold"
                            }
                        ],
                        "margin": "md"
                    },
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "contents": [
                            {
                                "type": "text",
                                "text": "📱 เบอร์",
                                "size": "sm",
                                "color": "#888888",
                                "flex": 2
                            },
                            {
                                "type": "text",
                                "text": phone,
                                "size": "sm",
                                "color": "#333333",
                                "flex": 4,
                                "weight": "bold"
                            }
                        ],
                        "margin": "sm"
                    },
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "contents": [
                            {
                                "type": "text",
                                "text": "📍 จังหวัด",
                                "size": "sm",
                                "color": "#888888",
                                "flex": 2
                            },
                            {
                                "type": "text",
                                "text": province,
                                "size": "sm",
                                "color": "#333333",
                                "flex": 4,
                                "weight": "bold"
                            }
                        ],
                        "margin": "sm"
                    },
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "contents": [
                            {
                                "type": "text",
                                "text": "🌾 พืช",
                                "size": "sm",
                                "color": "#888888",
                                "flex": 2
                            },
                            {
                                "type": "text",
                                "text": crops_text,
                                "size": "sm",
                                "color": "#333333",
                                "flex": 4,
                                "weight": "bold",
                                "wrap": True
                            }
                        ],
                        "margin": "sm"
                    },
                    {
                        "type": "separator",
                        "margin": "lg"
                    },
                    {
                        "type": "text",
                        "text": "🎉 พร้อมใช้งานแล้ว!",
                        "size": "sm",
                        "color": "#27AE60",
                        "align": "center",
                        "margin": "lg",
                        "weight": "bold"
                    },
                    {
                        "type": "text",
                        "text": "ส่งรูปพืชมาวิเคราะห์โรคได้เลยค่ะ",
                        "size": "xs",
                        "color": "#888888",
                        "align": "center",
                        "margin": "sm"
                    }
                ]
            }
        }
    }


def create_disease_result_flex(
    disease_name: str,
    confidence: str,
    symptoms: str,
    severity: str = "ปานกลาง",
    raw_analysis: str = "",
    pest_type: str = "โรคพืช",
    pest_vector: str = None
) -> Dict:
    """
    สร้าง Flex Message แสดงผลการวิเคราะห์โรคพืช

    Args:
        disease_name: ชื่อโรค
        confidence: ความมั่นใจ (เช่น "85%" หรือ "0.85")
        symptoms: อาการที่พบ
        severity: ระดับความรุนแรง
        raw_analysis: ข้อมูลวิเคราะห์ดิบ
        pest_type: ประเภทศัตรูพืช
        pest_vector: แมลงพาหะของโรค (ถ้ามี)
    """
    # แปลง confidence เป็น percentage
    try:
        if isinstance(confidence, str):
            # ถ้าเป็น string เช่น "85%" หรือ "สูง"
            confidence_clean = confidence.replace("%", "").strip()
            if confidence_clean.replace(".", "").isdigit():
                conf_val = float(confidence_clean)
                confidence_pct = int(conf_val) if conf_val > 1 else int(conf_val * 100)
            else:
                # ถ้าเป็นข้อความ เช่น "สูง", "ปานกลาง"
                confidence_pct = 75  # default
        else:
            conf_val = float(confidence)
            confidence_pct = int(conf_val) if conf_val > 1 else int(conf_val * 100)
    except:
        confidence_pct = 75  # default

    # กำหนดสีตาม confidence level
    if confidence_pct >= 80:
        confidence_color = "#27AE60"  # Green
        confidence_text = "สูง"
    elif confidence_pct >= 50:
        confidence_color = "#F39C12"  # Orange
        confidence_text = "ปานกลาง"
    else:
        confidence_color = "#E74C3C"  # Red
        confidence_text = "ต่ำ"

    # กำหนดสี header ตามประเภท
    if "แมลง" in pest_type or "หนอน" in pest_type:
        header_color = "#E67E22"  # Orange for insects
        icon = "🐛"
    elif "โรค" in pest_type or "เชื้อ" in pest_type:
        header_color = "#E74C3C"  # Red for diseases
        icon = "🦠"
    else:
        header_color = "#3498DB"  # Blue for others
        icon = "🔬"

    return {
        "type": "flex",
        "altText": f"ผลวิเคราะห์: {disease_name}",
        "contents": {
            "type": "bubble",
            "size": "giga",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": f"{icon} ผลการวิเคราะห์",
                        "color": "#ffffff",
                        "size": "lg",
                        "weight": "bold"
                    },
                    {
                        "type": "text",
                        "text": pest_type,
                        "color": "#ffffff",
                        "size": "xs",
                        "margin": "sm"
                    }
                ],
                "backgroundColor": header_color,
                "paddingAll": "15px"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    # Disease Name
                    {
                        "type": "text",
                        "text": disease_name,
                        "weight": "bold",
                        "size": "xl",
                        "color": "#333333",
                        "wrap": True
                    },
                    # Confidence Bar
                    {
                        "type": "box",
                        "layout": "vertical",
                        "margin": "lg",
                        "contents": [
                            {
                                "type": "box",
                                "layout": "horizontal",
                                "contents": [
                                    {
                                        "type": "text",
                                        "text": "ความมั่นใจ",
                                        "size": "sm",
                                        "color": "#888888"
                                    },
                                    {
                                        "type": "text",
                                        "text": f"{confidence_pct}% ({confidence_text})",
                                        "size": "sm",
                                        "color": confidence_color,
                                        "weight": "bold",
                                        "align": "end"
                                    }
                                ]
                            },
                            {
                                "type": "box",
                                "layout": "horizontal",
                                "margin": "sm",
                                "contents": [
                                    {
                                        "type": "box",
                                        "layout": "vertical",
                                        "contents": [],
                                        "backgroundColor": confidence_color,
                                        "width": f"{confidence_pct}%",
                                        "height": "6px",
                                        "cornerRadius": "3px"
                                    }
                                ],
                                "backgroundColor": "#E0E0E0",
                                "cornerRadius": "3px"
                            }
                        ]
                    },
                    {
                        "type": "separator",
                        "margin": "lg"
                    },
                    # Symptoms - แสดงอาการกระชับ
                    {
                        "type": "box",
                        "layout": "vertical",
                        "margin": "lg",
                        "contents": [
                            {
                                "type": "text",
                                "text": "📋 อาการที่พบ",
                                "size": "sm",
                                "weight": "bold",
                                "color": "#27AE60"
                            },
                            {
                                "type": "text",
                                "text": _format_symptoms(symptoms),
                                "size": "sm",
                                "color": "#333333",
                                "wrap": True,
                                "margin": "sm"
                            }
                        ]
                    },
                    # Severity - แสดงระดับความรุนแรง
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "margin": "md",
                        "contents": [
                            {
                                "type": "text",
                                "text": "⚠️ ความรุนแรง:",
                                "size": "sm",
                                "color": "#888888",
                                "flex": 0
                            },
                            {
                                "type": "text",
                                "text": _get_severity_label(severity),
                                "size": "sm",
                                "color": _get_severity_color(severity),
                                "weight": "bold",
                                "margin": "sm"
                            }
                        ]
                    }
                ] + (
                    # Pest Vector Section - แสดงข้อมูลแมลงพาหะ (ถ้ามี)
                    [
                        {
                            "type": "box",
                            "layout": "vertical",
                            "margin": "lg",
                            "backgroundColor": "#FFF3E0",
                            "cornerRadius": "8px",
                            "paddingAll": "12px",
                            "contents": [
                                {
                                    "type": "text",
                                    "text": "🐛 แมลงพาหะนำโรค",
                                    "size": "sm",
                                    "weight": "bold",
                                    "color": "#E65100"
                                },
                                {
                                    "type": "text",
                                    "text": pest_vector,
                                    "size": "md",
                                    "weight": "bold",
                                    "color": "#BF360C",
                                    "margin": "sm"
                                },
                                {
                                    "type": "text",
                                    "text": "⚠️ โรคนี้เกิดจากแมลงพาหะ ควรกำจัดแมลงเพื่อป้องกันการแพร่ระบาด",
                                    "size": "xs",
                                    "color": "#795548",
                                    "wrap": True,
                                    "margin": "sm"
                                }
                            ]
                        }
                    ] if pest_vector else []
                ) + [
                    # Raw Analysis / Recommendation - คำแนะนำครบถ้วน
                    {
                        "type": "box",
                        "layout": "vertical",
                        "margin": "lg",
                        "contents": [
                            {
                                "type": "text",
                                "text": "💡 คำแนะนำ",
                                "size": "sm",
                                "weight": "bold",
                                "color": "#3498DB"
                            },
                            {
                                "type": "text",
                                "text": _format_recommendation(raw_analysis),
                                "size": "sm",
                                "color": "#333333",
                                "wrap": True,
                                "margin": "sm"
                            }
                        ]
                    }
                ] + _create_root_cause_section(raw_analysis)
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "text",
                        "text": "👇 ผลิตภัณฑ์แนะนำด้านล่าง",
                        "size": "xs",
                        "color": "#888888",
                        "align": "center"
                    }
                ]
            }
        }
    }


def create_product_carousel_flex(products: List[Dict]) -> Dict:
    """
    สร้าง Flex Message Carousel แสดงผลิตภัณฑ์แนะนำ

    products: List of dict with keys:
        - product_name
        - active_ingredient
        - target_pest
        - how_to_use
        - usage_rate
        - similarity (optional)
    """
    bubbles = []

    for i, product in enumerate(products[:10]):  # LINE limit 10 bubbles
        similarity = product.get('similarity', 0)
        similarity_pct = int(similarity * 100) if similarity else 0

        bubble = {
            "type": "bubble",
            "size": "kilo",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": f"#{i+1}",
                        "color": "#ffffff",
                        "size": "xs"
                    },
                    {
                        "type": "text",
                        "text": product.get('product_name', 'ไม่ระบุชื่อ'),
                        "color": "#ffffff",
                        "size": "md",
                        "weight": "bold",
                        "wrap": True
                    }
                ],
                "backgroundColor": "#27AE60",
                "paddingAll": "12px"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    # Active Ingredient
                    {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "text",
                                "text": "💊 สารสำคัญ",
                                "size": "xs",
                                "color": "#888888"
                            },
                            {
                                "type": "text",
                                "text": product.get('active_ingredient', '-')[:150],
                                "size": "xs",
                                "color": "#333333",
                                "wrap": True
                            }
                        ]
                    },
                    # Target Pest
                    {
                        "type": "box",
                        "layout": "vertical",
                        "margin": "md",
                        "contents": [
                            {
                                "type": "text",
                                "text": "🎯 ศัตรูพืชเป้าหมาย",
                                "size": "xs",
                                "color": "#888888"
                            },
                            {
                                "type": "text",
                                "text": product.get('target_pest', '-')[:200],
                                "size": "xs",
                                "color": "#333333",
                                "wrap": True
                            }
                        ]
                    },
                    # Applicable Crops
                    {
                        "type": "box",
                        "layout": "vertical",
                        "margin": "md",
                        "contents": [
                            {
                                "type": "text",
                                "text": "🌾 พืชที่ใช้ได้",
                                "size": "xs",
                                "color": "#888888"
                            },
                            {
                                "type": "text",
                                "text": product.get('applicable_crops', '-')[:200],
                                "size": "xs",
                                "color": "#333333",
                                "wrap": True
                            }
                        ]
                    },
                    # Usage Period
                    {
                        "type": "box",
                        "layout": "vertical",
                        "margin": "md",
                        "contents": [
                            {
                                "type": "text",
                                "text": "📅 ช่วงการใช้",
                                "size": "xs",
                                "color": "#888888"
                            },
                            {
                                "type": "text",
                                "text": product.get('usage_period', '-')[:200],
                                "size": "xs",
                                "color": "#333333",
                                "wrap": True
                            }
                        ]
                    },
                    # How to Use
                    {
                        "type": "box",
                        "layout": "vertical",
                        "margin": "md",
                        "contents": [
                            {
                                "type": "text",
                                "text": "📝 วิธีใช้",
                                "size": "xs",
                                "color": "#888888"
                            },
                            {
                                "type": "text",
                                "text": product.get('how_to_use', '-')[:300],
                                "size": "xs",
                                "color": "#333333",
                                "wrap": True
                            }
                        ]
                    },
                    # Usage Rate
                    {
                        "type": "box",
                        "layout": "vertical",
                        "margin": "md",
                        "contents": [
                            {
                                "type": "text",
                                "text": "📏 อัตราใช้",
                                "size": "xs",
                                "color": "#888888"
                            },
                            {
                                "type": "text",
                                "text": product.get('usage_rate', '-')[:150],
                                "size": "xs",
                                "color": "#333333",
                                "wrap": True
                            }
                        ]
                    },
                ],
                "spacing": "sm",
                "paddingAll": "12px"
            },
        }

        # Add footer with product link
        product_url = product.get('link_product', '')
        if product_url:
            try:
                import re
                import logging
                logger = logging.getLogger(__name__)

                # Convert to string and clean
                product_url = str(product_url).strip()

                # Log original URL for debugging (FULL URL)
                logger.info(f"Product URL (len={len(product_url)}): [{product_url}]")

                # Remove all control characters and whitespace
                product_url = re.sub(r'[\x00-\x1f\x7f-\x9f\s]', '', product_url)

                # Encode square brackets (Facebook URLs have __cft__[0]= which is invalid)
                product_url = product_url.replace('[', '%5B').replace(']', '%5D')

                # Validate URL format with regex
                url_pattern = re.compile(
                    r'^https?://'  # http:// or https://
                    r'[a-zA-Z0-9]'  # Start with alphanumeric
                    r'[a-zA-Z0-9\-\.]*'  # Domain characters
                    r'\.[a-zA-Z]{2,}'  # TLD
                    r'[^\s]*$'  # Rest of URL (no whitespace)
                )

                is_valid = (
                    url_pattern.match(product_url)
                    and len(product_url) >= 10
                    and len(product_url) <= 1000
                )

                logger.info(f"Product URL valid={is_valid}, len={len(product_url)}")

                if is_valid:
                    bubble["footer"] = {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "button",
                                "action": {
                                    "type": "uri",
                                    "label": "ดูรายละเอียด",
                                    "uri": product_url
                                },
                                "style": "primary",
                                "color": "#27AE60",
                                "height": "sm"
                            }
                        ],
                        "paddingAll": "10px"
                    }
                else:
                    logger.warning(f"Invalid URL skipped: [{product_url[:50]}]")
            except Exception as e:
                logger.error(f"URL processing error: {e}")

        bubbles.append(bubble)

    # ถ้าไม่มีผลิตภัณฑ์
    if not bubbles:
        return {
            "type": "flex",
            "altText": "ไม่พบผลิตภัณฑ์แนะนำ",
            "contents": {
                "type": "bubble",
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": "ไม่พบผลิตภัณฑ์แนะนำ",
                            "align": "center",
                            "color": "#888888"
                        }
                    ]
                }
            }
        }

    return {
        "type": "flex",
        "altText": f"ผลิตภัณฑ์แนะนำ {len(bubbles)} รายการ",
        "contents": {
            "type": "carousel",
            "contents": bubbles
        }
    }


def create_simple_text_flex(title: str, message: str, button_label: str = None, button_text: str = None) -> Dict:
    """
    สร้าง Flex Message แบบง่ายๆ มีหัวข้อและเนื้อหา
    """
    contents = {
        "type": "bubble",
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": title,
                    "weight": "bold",
                    "size": "lg",
                    "color": "#333333"
                },
                {
                    "type": "text",
                    "text": message,
                    "size": "sm",
                    "color": "#666666",
                    "wrap": True,
                    "margin": "md"
                }
            ]
        }
    }

    if button_label and button_text:
        contents["footer"] = {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "button",
                    "style": "primary",
                    "action": {
                        "type": "message",
                        "label": button_label,
                        "text": button_text
                    },
                    "color": "#27AE60"
                }
            ]
        }

    return {
        "type": "flex",
        "altText": title,
        "contents": contents
    }


def create_help_menu_flex() -> Dict:
    """
    สร้าง Flex Message สำหรับเมนูช่วยเหลือ
    """
    return {
        "type": "flex",
        "altText": "เมนูช่วยเหลือ",
        "contents": {
            "type": "bubble",
            "size": "kilo",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "📋 เมนูช่วยเหลือ",
                        "color": "#ffffff",
                        "size": "lg",
                        "weight": "bold",
                        "align": "center"
                    }
                ],
                "backgroundColor": "#3498DB",
                "paddingAll": "15px"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "contents": [
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "contents": [
                            {"type": "text", "text": "📷", "size": "xl", "flex": 0},
                            {
                                "type": "box",
                                "layout": "vertical",
                                "contents": [
                                    {"type": "text", "text": "ตรวจโรคพืช", "weight": "bold", "size": "sm"},
                                    {"type": "text", "text": "ส่งรูปใบพืชที่มีอาการ", "size": "xs", "color": "#888888"}
                                ],
                                "margin": "md"
                            }
                        ]
                    },
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "contents": [
                            {"type": "text", "text": "💬", "size": "xl", "flex": 0},
                            {
                                "type": "box",
                                "layout": "vertical",
                                "contents": [
                                    {"type": "text", "text": "ถามข้อมูล", "weight": "bold", "size": "sm"},
                                    {"type": "text", "text": "พิมพ์คำถามเกี่ยวกับโรค/ผลิตภัณฑ์", "size": "xs", "color": "#888888"}
                                ],
                                "margin": "md"
                            }
                        ]
                    },
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "contents": [
                            {"type": "text", "text": "📝", "size": "xl", "flex": 0},
                            {
                                "type": "box",
                                "layout": "vertical",
                                "contents": [
                                    {"type": "text", "text": "ลงทะเบียน", "weight": "bold", "size": "sm"},
                                    {"type": "text", "text": "รับบริการเต็มรูปแบบ", "size": "xs", "color": "#888888"}
                                ],
                                "margin": "md"
                            }
                        ]
                    },
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "contents": [
                            {"type": "text", "text": "🔄", "size": "xl", "flex": 0},
                            {
                                "type": "box",
                                "layout": "vertical",
                                "contents": [
                                    {"type": "text", "text": "ล้างความจำ", "weight": "bold", "size": "sm"},
                                    {"type": "text", "text": "พิมพ์ 'reset' เพื่อเริ่มใหม่", "size": "xs", "color": "#888888"}
                                ],
                                "margin": "md"
                            }
                        ]
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "horizontal",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "height": "sm",
                        "action": {
                            "type": "message",
                            "label": "📝 ลงทะเบียน",
                            "text": "ลงทะเบียน"
                        },
                        "color": "#27AE60",
                        "flex": 1
                    },
                    {
                        "type": "button",
                        "style": "secondary",
                        "height": "sm",
                        "action": {
                            "type": "message",
                            "label": "📖 วิธีใช้",
                            "text": "วิธีใช้งาน"
                        },
                        "flex": 1
                    }
                ]
            }
        }
    }


def create_usage_guide_flex() -> Dict:
    """
    สร้าง Flex Message สำหรับวิธีใช้งาน
    """
    return {
        "type": "flex",
        "altText": "วิธีใช้งาน Chatbot Ladda",
        "contents": {
            "type": "bubble",
            "size": "giga",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "📖 วิธีใช้งาน",
                        "color": "#ffffff",
                        "size": "lg",
                        "weight": "bold"
                    },
                    {
                        "type": "text",
                        "text": "Chatbot Ladda",
                        "color": "#ffffff",
                        "size": "sm"
                    }
                ],
                "backgroundColor": "#9B59B6",
                "paddingAll": "15px"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "lg",
                "contents": [
                    # Section 1: วิเคราะห์โรค
                    {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "text",
                                "text": "🔍 วิเคราะห์โรคพืช",
                                "weight": "bold",
                                "size": "sm",
                                "color": "#27AE60"
                            },
                            {
                                "type": "text",
                                "text": "1. ถ่ายรูปใบพืชที่เป็นโรค\n2. ส่งรูปมาให้ฉัน\n3. ตอบคำถามเพิ่มเติม (ถ้ามี)\n4. รับผลวิเคราะห์และคำแนะนำ",
                                "size": "xs",
                                "color": "#666666",
                                "wrap": True,
                                "margin": "sm"
                            }
                        ]
                    },
                    {"type": "separator"},
                    # Section 2: ลงทะเบียน
                    {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "text",
                                "text": "📝 ลงทะเบียน",
                                "weight": "bold",
                                "size": "sm",
                                "color": "#E74C3C"
                            },
                            {
                                "type": "text",
                                "text": "พิมพ์ 'ลงทะเบียน' แล้วกรอก:\n• ชื่อ-นามสกุล\n• เบอร์โทร\n• จังหวัด\n• พืชที่ปลูก",
                                "size": "xs",
                                "color": "#666666",
                                "wrap": True,
                                "margin": "sm"
                            }
                        ]
                    },
                    {"type": "separator"},
                    # Section 3: ถามคำถาม
                    {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "text",
                                "text": "💬 ถามคำถาม",
                                "weight": "bold",
                                "size": "sm",
                                "color": "#3498DB"
                            },
                            {
                                "type": "text",
                                "text": "พิมพ์คำถามเกี่ยวกับการเกษตร\nเช่น: 'วิธีป้องกันโรคใบจุด'",
                                "size": "xs",
                                "color": "#666666",
                                "wrap": True,
                                "margin": "sm"
                            }
                        ]
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "action": {
                            "type": "message",
                            "label": "📝 ลงทะเบียนเลย",
                            "text": "ลงทะเบียน"
                        },
                        "color": "#27AE60"
                    }
                ]
            }
        }
    }


def create_product_catalog_flex() -> Dict:
    """
    สร้าง Flex Message สำหรับแคตตาล็อกผลิตภัณฑ์
    """
    return {
        "type": "flex",
        "altText": "ผลิตภัณฑ์ ICP Ladda",
        "contents": {
            "type": "bubble",
            "size": "kilo",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "🌾 ผลิตภัณฑ์ ICP Ladda",
                        "color": "#ffffff",
                        "size": "lg",
                        "weight": "bold",
                        "align": "center"
                    }
                ],
                "backgroundColor": "#F39C12",
                "paddingAll": "15px"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "ผลิตภัณฑ์ป้องกันกำจัดศัตรูพืช 48 รายการ",
                        "size": "sm",
                        "color": "#333333",
                        "align": "center"
                    },
                    {"type": "separator", "margin": "lg"},
                    {
                        "type": "box",
                        "layout": "vertical",
                        "margin": "lg",
                        "spacing": "sm",
                        "contents": [
                            {
                                "type": "box",
                                "layout": "horizontal",
                                "contents": [
                                    {"type": "text", "text": "✅", "flex": 0},
                                    {"type": "text", "text": "ยาฆ่าแมลง", "size": "sm", "margin": "sm"}
                                ]
                            },
                            {
                                "type": "box",
                                "layout": "horizontal",
                                "contents": [
                                    {"type": "text", "text": "✅", "flex": 0},
                                    {"type": "text", "text": "ยาฆ่าเชื้อรา", "size": "sm", "margin": "sm"}
                                ]
                            },
                            {
                                "type": "box",
                                "layout": "horizontal",
                                "contents": [
                                    {"type": "text", "text": "✅", "flex": 0},
                                    {"type": "text", "text": "ยาฆ่าหญ้า", "size": "sm", "margin": "sm"}
                                ]
                            },
                            {
                                "type": "box",
                                "layout": "horizontal",
                                "contents": [
                                    {"type": "text", "text": "✅", "flex": 0},
                                    {"type": "text", "text": "ปุ๋ยและสารเสริม", "size": "sm", "margin": "sm"}
                                ]
                            }
                        ]
                    },
                    {"type": "separator", "margin": "lg"},
                    {
                        "type": "text",
                        "text": "💡 ส่งรูปพืชที่เป็นโรคมาให้ฉัน\nจะแนะนำผลิตภัณฑ์ที่เหมาะสมให้!",
                        "size": "xs",
                        "color": "#888888",
                        "wrap": True,
                        "margin": "lg",
                        "align": "center"
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "button",
                        "style": "link",
                        "action": {
                            "type": "uri",
                            "label": "🔗 เว็บไซต์ ICP Ladda",
                            "uri": "https://www.icpladda.com/about/"
                        }
                    }
                ]
            }
        }
    }


def create_initial_questions_flex() -> Dict:
    """
    สร้าง Flex Message สำหรับถามคำถามเพิ่มเติมหลังรับรูป
    """
    return {
        "type": "flex",
        "altText": "ได้รับรูปแล้วค่ะ กรุณาตอบคำถามเพิ่มเติม",
        "contents": {
            "type": "bubble",
            "size": "giga",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "✅ ได้รับรูปแล้วค่ะ",
                        "color": "#ffffff",
                        "size": "lg",
                        "weight": "bold"
                    }
                ],
                "backgroundColor": "#27AE60",
                "paddingAll": "15px"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "👉 เพื่อความแม่นยำในการวินิจฉัย",
                        "size": "sm",
                        "color": "#E74C3C",
                        "weight": "bold"
                    },
                    {
                        "type": "text",
                        "text": "กรุณาตอบคำถามเพิ่มเติมค่ะ:",
                        "size": "sm",
                        "color": "#E74C3C",
                        "margin": "sm"
                    },
                    {
                        "type": "separator",
                        "margin": "lg"
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "margin": "lg",
                        "spacing": "md",
                        "contents": [
                            {
                                "type": "box",
                                "layout": "horizontal",
                                "contents": [
                                    {"type": "text", "text": "1️⃣", "flex": 0, "size": "sm"},
                                    {
                                        "type": "box",
                                        "layout": "vertical",
                                        "margin": "md",
                                        "contents": [
                                            {"type": "text", "text": "ชนิดพืช", "weight": "bold", "size": "sm"},
                                            {"type": "text", "text": "ทุเรียน/มะม่วง/ข้าว/อื่นๆ?", "size": "xs", "color": "#888888"}
                                        ]
                                    }
                                ]
                            },
                            {
                                "type": "box",
                                "layout": "horizontal",
                                "contents": [
                                    {"type": "text", "text": "2️⃣", "flex": 0, "size": "sm"},
                                    {
                                        "type": "box",
                                        "layout": "vertical",
                                        "margin": "md",
                                        "contents": [
                                            {"type": "text", "text": "ตำแหน่งอาการ", "weight": "bold", "size": "sm"},
                                            {"type": "text", "text": "ใบ/ลำต้น/ผล/ราก?", "size": "xs", "color": "#888888"}
                                        ]
                                    }
                                ]
                            },
                            {
                                "type": "box",
                                "layout": "horizontal",
                                "contents": [
                                    {"type": "text", "text": "3️⃣", "flex": 0, "size": "sm"},
                                    {
                                        "type": "box",
                                        "layout": "vertical",
                                        "margin": "md",
                                        "contents": [
                                            {"type": "text", "text": "ลักษณะอาการ", "weight": "bold", "size": "sm"},
                                            {"type": "text", "text": "• สีของจุด/แผล (น้ำตาล/เหลือง/ดำ/ขาว)", "size": "xs", "color": "#888888", "wrap": True},
                                            {"type": "text", "text": "• พื้นที่เสียหาย (แค่กใบ/ปลายใบ/กลางใบ/ทั่วใบ)", "size": "xs", "color": "#888888", "wrap": True},
                                            {"type": "text", "text": "• ขึ้นพองหรือไม่ (ถ้าขึ้น สีและขนาด)", "size": "xs", "color": "#888888", "wrap": True}
                                        ]
                                    }
                                ]
                            },
                            {
                                "type": "box",
                                "layout": "horizontal",
                                "contents": [
                                    {"type": "text", "text": "4️⃣", "flex": 0, "size": "sm"},
                                    {
                                        "type": "box",
                                        "layout": "vertical",
                                        "margin": "md",
                                        "contents": [
                                            {"type": "text", "text": "ระยะเวลาอาการ", "weight": "bold", "size": "sm"},
                                            {"type": "text", "text": "เพิ่งพบหรือนานแค่ไหน?", "size": "xs", "color": "#888888"}
                                        ]
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "type": "separator",
                        "margin": "lg"
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "margin": "lg",
                        "contents": [
                            {
                                "type": "text",
                                "text": "💡 ตัวอย่างการตอบกลับ:",
                                "size": "sm",
                                "color": "#3498DB",
                                "weight": "bold"
                            },
                            {
                                "type": "text",
                                "text": "\"ทุเรียน ใบมีจุดสีน้ำตาล เห็นแผลตรงกลางใบ เกิดมา 3 วัน\"",
                                "size": "xs",
                                "color": "#666666",
                                "margin": "sm",
                                "wrap": True,
                                "style": "italic"
                            }
                        ]
                    },
                    {
                        "type": "text",
                        "text": "🔬 ยิ่งให้ข้อมูลเยอะ ยิ่งวิเคราะห์ได้แม่นยำค่ะ!",
                        "size": "xs",
                        "color": "#27AE60",
                        "margin": "lg",
                        "align": "center",
                        "weight": "bold"
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "button",
                        "style": "secondary",
                        "height": "sm",
                        "action": {
                            "type": "message",
                            "label": "⏭️ ข้าม - วิเคราะห์เลย",
                            "text": "ข้าม"
                        }
                    }
                ]
            }
        }
    }


def create_analyzing_flex(with_info: bool = False) -> Dict:
    """
    สร้าง Flex Message แสดงสถานะกำลังวิเคราะห์
    """
    if with_info:
        title = "รับทราบข้อมูลค่ะ"
        subtitle = "กำลังวิเคราะห์อย่างละเอียด..."
    else:
        title = "เข้าใจค่ะ"
        subtitle = "กำลังวิเคราะห์จากรูปภาพ..."

    return {
        "type": "flex",
        "altText": subtitle,
        "contents": {
            "type": "bubble",
            "size": "kilo",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "contents": [
                            {
                                "type": "text",
                                "text": "🔍",
                                "size": "3xl",
                                "flex": 0
                            },
                            {
                                "type": "box",
                                "layout": "vertical",
                                "margin": "lg",
                                "contents": [
                                    {
                                        "type": "text",
                                        "text": title,
                                        "weight": "bold",
                                        "size": "lg",
                                        "color": "#27AE60"
                                    },
                                    {
                                        "type": "text",
                                        "text": subtitle,
                                        "size": "sm",
                                        "color": "#666666",
                                        "margin": "sm"
                                    }
                                ]
                            }
                        ],
                        "alignItems": "center"
                    },
                    {
                        "type": "text",
                        "text": "🌱 กรุณารอสักครู่...",
                        "size": "xs",
                        "color": "#888888",
                        "align": "center",
                        "margin": "lg"
                    }
                ],
                "paddingAll": "20px"
            }
        }
    }


def create_chat_response_flex(question: str, answer: str) -> Dict:
    """
    สร้าง Flex Message สำหรับการตอบคำถาม Chat Q&A
    ไม่มีปุ่มช่วยเหลือ - แสดงเฉพาะคำตอบ
    """
    # ตัดข้อความให้สั้นลงถ้ายาวเกินไป
    display_question = question[:50] + "..." if len(question) > 50 else question

    return {
        "type": "flex",
        "altText": f"คำตอบ: {display_question}",
        "contents": {
            "type": "bubble",
            "size": "giga",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "💬 คำตอบจาก Ladda",
                        "color": "#ffffff",
                        "size": "md",
                        "weight": "bold"
                    }
                ],
                "backgroundColor": "#27AE60",
                "paddingAll": "12px"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": answer,
                        "size": "sm",
                        "color": "#333333",
                        "wrap": True
                    }
                ]
            }
        }
    }


# =============================================================================
# LIFF Registration Flex Messages
# =============================================================================

def create_liff_registration_flex(liff_url: str) -> Dict:
    """
    สร้าง Flex Message สำหรับเปิด LIFF ลงทะเบียน

    Args:
        liff_url: URL ของ LIFF app (เช่น https://liff.line.me/xxxx)
    """
    return {
        "type": "flex",
        "altText": "กรุณาลงทะเบียนก่อนใช้งาน",
        "contents": {
            "type": "bubble",
            "size": "kilo",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "🌾 Login ICP",
                        "color": "#ffffff",
                        "size": "xl",
                        "weight": "bold",
                        "align": "center"
                    },
                    {
                        "type": "text",
                        "text": "ลงทะเบียนเกษตรกรอัจฉริยะ",
                        "color": "#ffffff",
                        "size": "sm",
                        "align": "center",
                        "margin": "sm"
                    }
                ],
                "backgroundColor": "#2d5016",
                "paddingAll": "20px"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "เพื่อให้บริการคุณได้ดียิ่งขึ้น",
                        "size": "sm",
                        "color": "#333333",
                        "align": "center"
                    },
                    {
                        "type": "text",
                        "text": "กรุณาลงทะเบียนข้อมูลพื้นฐาน",
                        "size": "sm",
                        "color": "#333333",
                        "align": "center",
                        "margin": "sm"
                    },
                    {
                        "type": "separator",
                        "margin": "lg"
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "margin": "lg",
                        "spacing": "sm",
                        "contents": [
                            {
                                "type": "box",
                                "layout": "horizontal",
                                "contents": [
                                    {"type": "text", "text": "👤", "flex": 0, "size": "sm"},
                                    {"type": "text", "text": "ชื่อ-นามสกุล", "size": "sm", "margin": "md", "color": "#666666"}
                                ]
                            },
                            {
                                "type": "box",
                                "layout": "horizontal",
                                "contents": [
                                    {"type": "text", "text": "📱", "flex": 0, "size": "sm"},
                                    {"type": "text", "text": "เบอร์โทรศัพท์", "size": "sm", "margin": "md", "color": "#666666"}
                                ]
                            },
                            {
                                "type": "box",
                                "layout": "horizontal",
                                "contents": [
                                    {"type": "text", "text": "📍", "flex": 0, "size": "sm"},
                                    {"type": "text", "text": "จังหวัด", "size": "sm", "margin": "md", "color": "#666666"}
                                ]
                            },
                            {
                                "type": "box",
                                "layout": "horizontal",
                                "contents": [
                                    {"type": "text", "text": "🌱", "flex": 0, "size": "sm"},
                                    {"type": "text", "text": "พืชที่ปลูก", "size": "sm", "margin": "md", "color": "#666666"}
                                ]
                            }
                        ]
                    },
                    {
                        "type": "text",
                        "text": "ใช้เวลาไม่ถึง 1 นาที!",
                        "size": "xs",
                        "color": "#4a7c23",
                        "align": "center",
                        "margin": "lg",
                        "weight": "bold"
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "action": {
                            "type": "uri",
                            "label": "📝 ลงทะเบียนเลย",
                            "uri": liff_url
                        },
                        "color": "#4a7c23",
                        "height": "md"
                    }
                ]
            }
        }
    }


def create_liff_welcome_flex(liff_url: str) -> Dict:
    """
    สร้าง Flex Message ต้อนรับพร้อมปุ่ม LIFF ลงทะเบียน

    Args:
        liff_url: URL ของ LIFF app
    """
    return {
        "type": "flex",
        "altText": "ยินดีต้อนรับสู่ Chatbot Ladda",
        "contents": {
            "type": "bubble",
            "size": "giga",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "text",
                                "text": "🌾 CHATBOT LADDA",
                                "color": "#ffffff",
                                "size": "xl",
                                "weight": "bold",
                                "align": "center"
                            },
                            {
                                "type": "text",
                                "text": "ผู้ช่วยด้านการเกษตรอัจฉริยะ",
                                "color": "#ffffff",
                                "size": "sm",
                                "align": "center",
                                "margin": "sm"
                            }
                        ]
                    }
                ],
                "backgroundColor": "#2d5016",
                "paddingAll": "20px"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "ยินดีต้อนรับค่ะ!",
                        "weight": "bold",
                        "size": "xl",
                        "margin": "md",
                        "color": "#4a7c23"
                    },
                    {
                        "type": "text",
                        "text": "ฉันคือผู้ช่วยที่จะช่วยคุณดูแลพืชผล",
                        "size": "sm",
                        "color": "#666666",
                        "margin": "md",
                        "wrap": True
                    },
                    {
                        "type": "separator",
                        "margin": "lg"
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "margin": "lg",
                        "spacing": "md",
                        "contents": [
                            {
                                "type": "box",
                                "layout": "horizontal",
                                "contents": [
                                    {
                                        "type": "text",
                                        "text": "🔍",
                                        "size": "xl",
                                        "flex": 0
                                    },
                                    {
                                        "type": "box",
                                        "layout": "vertical",
                                        "contents": [
                                            {
                                                "type": "text",
                                                "text": "วิเคราะห์โรคพืช",
                                                "weight": "bold",
                                                "size": "sm"
                                            },
                                            {
                                                "type": "text",
                                                "text": "ส่งรูปใบพืชมาวิเคราะห์โรค",
                                                "size": "xs",
                                                "color": "#888888"
                                            }
                                        ],
                                        "margin": "md"
                                    }
                                ]
                            },
                            {
                                "type": "box",
                                "layout": "horizontal",
                                "contents": [
                                    {
                                        "type": "text",
                                        "text": "💊",
                                        "size": "xl",
                                        "flex": 0
                                    },
                                    {
                                        "type": "box",
                                        "layout": "vertical",
                                        "contents": [
                                            {
                                                "type": "text",
                                                "text": "แนะนำผลิตภัณฑ์",
                                                "weight": "bold",
                                                "size": "sm"
                                            },
                                            {
                                                "type": "text",
                                                "text": "รับคำแนะนำยาและปุ๋ยที่เหมาะสม",
                                                "size": "xs",
                                                "color": "#888888"
                                            }
                                        ],
                                        "margin": "md"
                                    }
                                ]
                            },
                            {
                                "type": "box",
                                "layout": "horizontal",
                                "contents": [
                                    {
                                        "type": "text",
                                        "text": "💬",
                                        "size": "xl",
                                        "flex": 0
                                    },
                                    {
                                        "type": "box",
                                        "layout": "vertical",
                                        "contents": [
                                            {
                                                "type": "text",
                                                "text": "ถาม-ตอบการเกษตร",
                                                "weight": "bold",
                                                "size": "sm"
                                            },
                                            {
                                                "type": "text",
                                                "text": "สอบถามปัญหาเกี่ยวกับพืช",
                                                "size": "xs",
                                                "color": "#888888"
                                            }
                                        ],
                                        "margin": "md"
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "type": "separator",
                        "margin": "lg"
                    },
                    {
                        "type": "text",
                        "text": "📝 กรุณาลงทะเบียนเพื่อเริ่มใช้งาน",
                        "size": "sm",
                        "color": "#E74C3C",
                        "margin": "lg",
                        "weight": "bold",
                        "align": "center"
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "height": "md",
                        "action": {
                            "type": "uri",
                            "label": "📝 ลงทะเบียน",
                            "uri": liff_url
                        },
                        "color": "#4a7c23"
                    },
                    {
                        "type": "button",
                        "style": "secondary",
                        "height": "sm",
                        "action": {
                            "type": "message",
                            "label": "📖 วิธีใช้งาน",
                            "text": "วิธีใช้งาน"
                        }
                    }
                ],
                "flex": 0
            }
        }
    }
