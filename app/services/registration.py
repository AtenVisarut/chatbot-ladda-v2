"""
User Registration Service - Conversational Flow
Handles user registration through chat with Quick Reply buttons
"""
import logging
from typing import Optional, Dict, Any, List
from app.services.services import supabase_client, analytics_tracker
from app.utils.flex_messages import create_registration_complete_flex

logger = logging.getLogger(__name__)

# Registration states
REGISTRATION_STATES = {
    "ASK_NAME": "ask_name",
    "ASK_PHONE": "ask_phone",
    "ASK_PROVINCE": "ask_province",
    "ASK_CROPS": "ask_crops",
    "COMPLETE": "complete"
}

# Thai provinces list
PROVINCES = [
    "เชียงใหม่", "เชียงราย", "น่าน", "พะเยา", "แพร่", "แม่ฮ่องสอน", "ลำปาง", "ลำพูน", "อุตรดิตถ์",
    "กาฬสินธุ์", "ขอนแก่น", "ชัยภูมิ", "นครพนม", "นครราชสีมา", "บึงกาฬ", "บุรีรัมย์", "มหาสารคาม", "มุกดาหาร", "ยโสธร", "ร้อยเอ็ด", "เลย", "สกลนคร", "สุรินทร์", "ศรีสะเกษ", "หนองคาย", "หนองบัวลำภู", "อุดรธานี", "อุบลราชธานี", "อำนาจเจริญ",
    "กรุงเทพมหานคร", "กำแพงเพชร", "ชัยนาท", "นครนายก", "นครปฐม", "นครสวรรค์", "นนทบุรี", "ปทุมธานี", "พระนครศรีอยุธยา", "พิจิตร", "พิษณุโลก", "เพชรบูรณ์", "ลพบุรี", "สมุทรปราการ", "สมุทรสงคราม", "สมุทรสาคร", "สระบุรี", "สิงห์บุรี", "สุโขทัย", "สุพรรณบุรี", "อ่างทอง", "อุทัยธานี",
    "จันทบุรี", "ฉะเชิงเทรา", "ชลบุรี", "ตราด", "ปราจีนบุรี", "ระยอง", "สระแก้ว",
    "กาญจนบุรี", "ตาก", "ประจวบคีรีขันธ์", "เพชรบุรี", "ราชบุรี",
    "กระบี่", "ชุมพร", "ตรัง", "นครศรีธรรมราช", "นราธิวาส", "ปัตตานี", "พังงา", "พัทลุง", "ภูเก็ต", "ยะลา", "ระนอง", "สงขลา", "สตูล", "สุราษฎร์ธานี",
    "ระบุจังหวัดอื่นๆ"
]

# Crops list
CROPS = [
    "ข้าว", "ข้าวโพด", "อ้อย", "มันสำปะหลัง",
    "ทุเรียน", "มะม่วง","ระบุข้อมูลอื่นๆ"
]


class RegistrationManager:
    """Manages user registration flow through conversational chat"""
    
    def __init__(self):
        self.state_key_prefix = "registration_state_"
        self.data_key_prefix = "registration_data_"
    
    async def get_registration_state(self, user_id: str) -> Optional[str]:
        """Get current registration state for user"""
        try:
            result = supabase_client.table("cache").select("value").eq(
                "key", f"{self.state_key_prefix}{user_id}"
            ).execute()
            
            if result.data:
                return result.data[0]["value"]
            return None
        except Exception as e:
            logger.error(f"Error getting registration state: {e}")
            return None
    
    async def set_registration_state(self, user_id: str, state: str):
        """Set registration state for user"""
        try:
            from datetime import datetime, timedelta
            expires_at = (datetime.now() + timedelta(hours=1)).isoformat()
            supabase_client.table("cache").upsert({
                "key": f"{self.state_key_prefix}{user_id}",
                "value": state,
                "expires_at": expires_at
            }).execute()
        except Exception as e:
            logger.error(f"Error setting registration state: {e}")
    
    async def get_registration_data(self, user_id: str) -> Dict[str, Any]:
        """Get accumulated registration data"""
        try:
            result = supabase_client.table("cache").select("value").eq(
                "key", f"{self.data_key_prefix}{user_id}"
            ).execute()
            
            if result.data:
                import json
                return json.loads(result.data[0]["value"])
            return {}
        except Exception as e:
            logger.error(f"Error getting registration data: {e}")
            return {}
    
    async def set_registration_data(self, user_id: str, data: Dict[str, Any]):
        """Save registration data"""
        try:
            import json
            from datetime import datetime, timedelta
            expires_at = (datetime.now() + timedelta(hours=1)).isoformat()
            supabase_client.table("cache").upsert({
                "key": f"{self.data_key_prefix}{user_id}",
                "value": json.dumps(data, ensure_ascii=False),
                "expires_at": expires_at
            }).execute()
        except Exception as e:
            logger.error(f"Error setting registration data: {e}")
    
    async def clear_registration(self, user_id: str):
        """Clear registration state and data"""
        try:
            supabase_client.table("cache").delete().eq(
                "key", f"{self.state_key_prefix}{user_id}"
            ).execute()
            supabase_client.table("cache").delete().eq(
                "key", f"{self.data_key_prefix}{user_id}"
            ).execute()
        except Exception as e:
            logger.error(f"Error clearing registration: {e}")
    
    def _create_text_message(self, text: str, quick_reply_items: List[Dict] = None) -> Dict:
        """Helper to create LINE text message dict with optional quick replies"""
        message = {
            "type": "text",
            "text": text
        }
        
        if quick_reply_items:
            message["quickReply"] = {
                "items": quick_reply_items
            }
            
        return message

    def _create_quick_reply_item(self, label: str, text: str) -> Dict:
        """Helper to create a quick reply item"""
        return {
            "type": "action",
            "action": {
                "type": "message",
                "label": label[:20],  # LINE limit
                "text": text
            }
        }

    async def start_registration(self, user_id: str) -> Dict:
        """Start registration flow"""
        logger.info(f"🔵 Starting registration for user: {user_id}")
        await self.set_registration_state(user_id, REGISTRATION_STATES["ASK_NAME"])
        await self.set_registration_data(user_id, {})
        logger.info(f"🔵 Registration state set to ASK_NAME for user: {user_id}")
        
        return self._create_text_message(
            text="📝 ลงทะเบียนเกษตรกร\n\n"
                 "กรุณาระบุชื่อ-นามสกุลของคุณ\n"
                 "(เช่น สมชาย ใจดี)",
            quick_reply_items=[
                self._create_quick_reply_item("❌ ยกเลิก", "ยกเลิก")
            ]
        )
    
    async def handle_registration_input(
        self,
        user_id: str,
        user_input: str
    ) -> Dict:
        """Handle user input during registration"""
        
        logger.info(f"🔵 Handling registration input for {user_id}: {user_input}")
        
        # Check for cancellation
        if user_input.strip() in ["ยกเลิก", "cancel", "ไม่ต้องการ"]:
            await self.clear_registration(user_id)
            return self._create_text_message("✅ ยกเลิกการลงทะเบียนเรียบร้อยแล้ว")
        
        state = await self.get_registration_state(user_id)
        data = await self.get_registration_data(user_id)
        
        logger.info(f"🔵 Current state: {state}, Data: {data}")
        
        if state == REGISTRATION_STATES["ASK_NAME"]:
            return await self._handle_name(user_id, user_input, data)
        elif state == REGISTRATION_STATES["ASK_PHONE"]:
            return await self._handle_phone(user_id, user_input, data)
        elif state == REGISTRATION_STATES["ASK_PROVINCE"]:
            return await self._handle_province(user_id, user_input, data)
        elif state == REGISTRATION_STATES["ASK_CROPS"]:
            return await self._handle_crops(user_id, user_input, data)
        
        return self._create_text_message("เกิดข้อผิดพลาด กรุณาเริ่มใหม่อีกครั้ง")
    
    async def _handle_name(self, user_id: str, name: str, data: Dict) -> Dict:
        """Handle name input"""
        if len(name) < 2:
            return self._create_text_message(
                "❌ ชื่อสั้นเกินไป กรุณาระบุชื่อ-นามสกุลที่ถูกต้อง"
            )
            
        data["full_name"] = name.strip()
        await self.set_registration_data(user_id, data)
        await self.set_registration_state(user_id, REGISTRATION_STATES["ASK_PHONE"])
        
        return self._create_text_message(
            text=f"✅ บันทึกชื่อ: {name}\n\n"
                 "📱 กรุณาระบุเบอร์โทรศัพท์ของคุณ\n"
                 "(ตัวอย่าง: 0812345678)"
        )

    async def _handle_phone(self, user_id: str, phone: str, data: Dict) -> Dict:
        """Handle phone number input"""
        # Basic validation
        phone = phone.strip().replace("-", "").replace(" ", "")
        if not phone.isdigit() or len(phone) not in [9, 10]:
            return self._create_text_message(
                "❌ เบอร์โทรศัพท์ไม่ถูกต้อง\nกรุณาระบุเบอร์โทรศัพท์ 10 หลัก (เช่น 0812345678)"
            )
        
        data["phone_number"] = phone
        await self.set_registration_data(user_id, data)
        await self.set_registration_state(user_id, REGISTRATION_STATES["ASK_PROVINCE"])
        
        # Create Quick Reply with common provinces
        # We can't show all 77 provinces, so show major ones + "อื่นๆ" or ask user to type
        # Let's show regions representatives
        common_provinces = ["เชียงใหม่", "ขอนแก่น", "นครราชสีมา", "กรุงเทพฯ", "ชลบุรี", "สงขลา"]
        
        province_items = [
            self._create_quick_reply_item(p, p)
            for p in common_provinces
        ]
        
        return self._create_text_message(
            text=f"✅ บันทึกเบอร์: {phone}\n\n"
                 "📍 กรุณาระบุจังหวัดที่คุณอาศัยอยู่\n"
                 "(พิมพ์ชื่อจังหวัด หรือเลือกจากรายการ)",
            quick_reply_items=province_items
        )

    async def _handle_province(self, user_id: str, province: str, data: Dict) -> Dict:
        """Handle province input"""
        province = province.strip()
        
        # Basic validation (check if it looks like a Thai string)
        if len(province) < 2:
             return self._create_text_message(
                "❌ ชื่อจังหวัดสั้นเกินไป กรุณาระบุใหม่"
            )

        data["province"] = province
        await self.set_registration_data(user_id, data)
        await self.set_registration_state(user_id, REGISTRATION_STATES["ASK_CROPS"])
        
        # Create Quick Reply with crops
        crop_items = [
            self._create_quick_reply_item(c, c)
            for c in CROPS[:12]  # Leave space for "เสร็จสิ้น" button
        ]
        crop_items.append(
            self._create_quick_reply_item("✅ เสร็จสิ้น", "เสร็จสิ้น")
        )
        
        return self._create_text_message(
            text=f"✅ บันทึกจังหวัด: {province}\n\n"
                 "🌾 เลือกพืชที่คุณปลูก (เลือกได้หลายชนิด)\n"
                 "พิมพ์ชื่อพืช หรือกดปุ่ม แล้วกด 'เสร็จสิ้น' เมื่อเลือกครบ",
            quick_reply_items=crop_items
        )
    
    async def _handle_crops(self, user_id: str, crop_input: str, data: Dict) -> Dict:
        """Handle crops input"""
        if crop_input.strip() == "เสร็จสิ้น":
            # Complete registration immediately
            return await self._complete_registration(user_id, data)
        
        # Add crop to list
        if "crops_grown" not in data:
            data["crops_grown"] = []
        
        crop = crop_input.strip()
        if crop not in data["crops_grown"]:
            data["crops_grown"].append(crop)
        
        await self.set_registration_data(user_id, data)
        
        # Show current selections
        crops_text = ", ".join(data["crops_grown"]) if data["crops_grown"] else "(ยังไม่ได้เลือก)"
        
        crop_items = [
            self._create_quick_reply_item(c, c)
            for c in CROPS[:12]
        ]
        crop_items.append(
            self._create_quick_reply_item("✅ เสร็จสิ้น", "เสร็จสิ้น")
        )
        
        return self._create_text_message(
            text=f"พืชที่เลือก: {crops_text}\n\n"
                 "เลือกเพิ่มหรือกด 'เสร็จสิ้น'",
            quick_reply_items=crop_items
        )
    
    async def _complete_registration(self, user_id: str, data: Dict) -> Dict:
        """Save registration data to database"""
        try:
            logger.info(f"🔵 Completing registration for {user_id}")
            logger.info(f"🔵 Data to save: {data}")
            
            # Upsert user record (create if not exists, update if exists)
            update_data = {
                "line_user_id": user_id,  # Primary key for upsert
                "display_name": data.get("full_name"),
                "phone_number": data.get("phone_number"),
                "province": data.get("province"),
                "crops_grown": data.get("crops_grown", []),
                "registration_completed": True
            }
            
            logger.info(f"🔵 Upserting to Supabase: {update_data}")
            result = supabase_client.table("users").upsert(
                update_data,
                on_conflict="line_user_id"
            ).execute()
            logger.info(f"🔵 Supabase result: {result}")
            
            # Track registration event
            if analytics_tracker:
                await analytics_tracker.track_registration(user_id)
            
            # Clear registration state
            await self.clear_registration(user_id)

            # Create Flex Message summary
            return create_registration_complete_flex(
                name=data.get('full_name', 'ไม่ระบุ'),
                phone=data.get('phone_number', 'ไม่ระบุ'),
                province=data.get('province', 'ไม่ระบุ'),
                crops=data.get('crops_grown', [])
            )
            
        except Exception as e:
            logger.error(f"Error completing registration: {e}")
            await self.clear_registration(user_id)
            return self._create_text_message(
                "❌ เกิดข้อผิดพลาดในการบันทึกข้อมูล\nกรุณาลองใหม่อีกครั้ง"
            )


# Global instance
registration_manager = RegistrationManager()
