import logging
import asyncio
from app.services.services import supabase_client
from app.config import MAX_MEMORY_MESSAGES, MEMORY_CONTEXT_WINDOW, MEMORY_CONTENT_PREVIEW

logger = logging.getLogger(__name__)

# Lock to prevent concurrent cleanup_old_memory for the same user
_cleanup_locks: dict = {}

def _get_cleanup_lock(user_id: str) -> asyncio.Lock:
    """Get or create a per-user asyncio lock for memory cleanup"""
    if user_id not in _cleanup_locks:
        _cleanup_locks[user_id] = asyncio.Lock()
    return _cleanup_locks[user_id]

async def add_to_memory(user_id: str, role: str, content: str, metadata: dict = None):
    """Add message to conversation memory in Supabase"""
    try:
        if not supabase_client:
            logger.warning("Supabase not available, skipping memory storage")
            return
        
        # Truncate very long messages
        truncated_content = content[:2000] if len(content) > 2000 else content
        
        data = {
            "user_id": user_id,
            "role": role,  # "user" or "assistant"
            "content": truncated_content,
            "metadata": metadata or {}
        }
        
        result = supabase_client.table('conversation_memory').insert(data).execute()
        logger.info(f"✓ Added to memory: {role} message for user {user_id[:8]}...")
        
        # Clean up old messages (keep last N per user)
        await cleanup_old_memory(user_id)
        
    except Exception as e:
        logger.error(f"Failed to add to memory: {e}")

async def get_conversation_context(user_id: str, limit: int = MEMORY_CONTEXT_WINDOW) -> str:
    """Get conversation history as context string from Supabase"""
    try:
        if not supabase_client:
            return ""

        # Get last N messages for this user
        result = supabase_client.table('conversation_memory')\
            .select('role, content, metadata, created_at')\
            .eq('user_id', user_id)\
            .order('created_at', desc=True)\
            .limit(limit)\
            .execute()

        if not result.data:
            return ""

        # Reverse to get chronological order
        messages = list(reversed(result.data))

        context_parts = []
        for msg in messages:
            role = "ผู้ใช้" if msg["role"] == "user" else "น้องลัดดา"
            content = msg["content"][:MEMORY_CONTENT_PREVIEW]  # Use config value

            # Add product info from metadata if available
            metadata = msg.get("metadata", {})
            if isinstance(metadata, dict) and metadata.get("type") == "product_recommendation":
                products = metadata.get("products", [])
                if products:
                    product_names = [p.get("product_name", "") for p in products[:3]]
                    content += f" (สินค้าที่แนะนำ: {', '.join(product_names)})"

            context_parts.append(f"{role}: {content}")

        logger.info(f"✓ Retrieved {len(messages)} messages from memory")
        return "\n".join(context_parts)

    except Exception as e:
        logger.error(f"Failed to get conversation context: {e}")
        return ""

async def cleanup_old_memory(user_id: str):
    """Keep only last N messages per user (per-user lock prevents race conditions)"""
    lock = _get_cleanup_lock(user_id)
    if lock.locked():
        # Another cleanup is already running for this user — skip
        return

    async with lock:
        try:
            if not supabase_client:
                return

            # Get all message IDs for this user, ordered by created_at desc
            result = supabase_client.table('conversation_memory')\
                .select('id')\
                .eq('user_id', user_id)\
                .order('created_at', desc=True)\
                .execute()

            if not result.data or len(result.data) <= MAX_MEMORY_MESSAGES:
                return

            # Get IDs to delete (keep only last MAX_MEMORY_MESSAGES)
            ids_to_delete = [msg['id'] for msg in result.data[MAX_MEMORY_MESSAGES:]]

            if ids_to_delete:
                # Delete old messages
                supabase_client.table('conversation_memory')\
                    .delete()\
                    .in_('id', ids_to_delete)\
                    .execute()
                logger.info(f"✓ Cleaned up {len(ids_to_delete)} old messages for user {user_id[:8]}...")

        except Exception as e:
            logger.error(f"Failed to cleanup old memory: {e}")

async def clear_memory(user_id: str):
    """Clear all conversation memory + all cache layers for user"""
    try:
        if not supabase_client:
            logger.warning("Supabase not available")
            return

        # 1. Delete from conversation_memory table
        supabase_client.table('conversation_memory')\
            .delete()\
            .eq('user_id', user_id)\
            .execute()

        # 2. Clear product focus (in-memory + Supabase)
        await clear_product_focus(user_id)

        logger.info(f"✓ Cleared memory + product focus for user {user_id[:8]}...")

    except Exception as e:
        logger.error(f"Failed to clear memory: {e}")

async def get_memory_stats(user_id: str) -> dict:
    """Get memory statistics for user"""
    try:
        if not supabase_client:
            return {"total": 0, "user_messages": 0, "assistant_messages": 0}

        result = supabase_client.table('conversation_memory')\
            .select('role')\
            .eq('user_id', user_id)\
            .execute()

        if not result.data:
            return {"total": 0, "user_messages": 0, "assistant_messages": 0}

        user_count = sum(1 for msg in result.data if msg['role'] == 'user')
        assistant_count = sum(1 for msg in result.data if msg['role'] == 'assistant')

        return {
            "total": len(result.data),
            "user_messages": user_count,
            "assistant_messages": assistant_count
        }

    except Exception as e:
        logger.error(f"Failed to get memory stats: {e}")
        return {"total": 0, "user_messages": 0, "assistant_messages": 0}


async def save_recommended_products(user_id: str, products: list, disease_name: str = ""):
    """
    เก็บข้อมูลสินค้าที่แนะนำใน memory พร้อม metadata
    เพื่อให้สามารถถามวิธีใช้ต่อได้
    """
    try:
        if not supabase_client:
            logger.warning("Supabase not available, skipping product memory")
            return

        import json

        # สร้าง product data สำหรับเก็บ
        products_data = []
        for p in products:
            if hasattr(p, 'dict'):
                # ProductRecommendation model
                prod_dict = p.dict()
            elif isinstance(p, dict):
                prod_dict = p
            else:
                continue

            products_data.append({
                "product_name": prod_dict.get("product_name", ""),
                "how_to_use": prod_dict.get("how_to_use", ""),
                "usage_rate": prod_dict.get("usage_rate", ""),
                "usage_period": prod_dict.get("usage_period", ""),
                "target_pest": prod_dict.get("target_pest", ""),
                "active_ingredient": prod_dict.get("active_ingredient", ""),
                "applicable_crops": prod_dict.get("applicable_crops", ""),
                "package_size": prod_dict.get("package_size", ""),
                "absorption_method": prod_dict.get("absorption_method", ""),
                "mechanism_of_action": prod_dict.get("mechanism_of_action", ""),
            })

        if not products_data:
            return

        # เก็บใน memory พร้อม metadata
        metadata = {
            "type": "product_recommendation",
            "disease_name": disease_name,
            "products": products_data
        }

        # สร้างข้อความสรุปสินค้า
        product_names = [p["product_name"] for p in products_data]
        content = f"[แนะนำสินค้า] {', '.join(product_names[:5])}"
        if disease_name:
            content = f"[แนะนำสินค้าสำหรับ {disease_name}] {', '.join(product_names[:5])}"

        data = {
            "user_id": user_id,
            "role": "assistant",
            "content": content,
            "metadata": metadata
        }

        result = supabase_client.table('conversation_memory').insert(data).execute()
        logger.info(f"✓ Saved {len(products_data)} recommended products to memory for user {user_id[:8]}...")

    except Exception as e:
        logger.error(f"Failed to save recommended products: {e}")


async def get_recommended_products(user_id: str, limit: int = 5) -> list:
    """
    ดึงข้อมูลสินค้าที่แนะนำล่าสุดจาก memory
    สำหรับตอบคำถามวิธีใช้/การพ่นยา
    """
    try:
        if not supabase_client:
            return []

        # ค้นหาข้อความที่มี metadata เป็น product_recommendation
        result = supabase_client.table('conversation_memory')\
            .select('content, metadata, created_at')\
            .eq('user_id', user_id)\
            .order('created_at', desc=True)\
            .limit(20)\
            .execute()

        if not result.data:
            return []

        # หา product recommendations จาก metadata
        all_products = []
        for msg in result.data:
            metadata = msg.get("metadata", {})
            if isinstance(metadata, dict) and metadata.get("type") == "product_recommendation":
                products = metadata.get("products", [])
                if products:
                    all_products.extend(products)
                    # ได้สินค้าพอแล้ว
                    if len(all_products) >= limit:
                        break

        # ลบ duplicate
        seen = set()
        unique_products = []
        for p in all_products:
            name = p.get("product_name", "")
            if name and name not in seen:
                seen.add(name)
                unique_products.append(p)

        logger.info(f"✓ Retrieved {len(unique_products)} products from memory for user {user_id[:8]}...")
        return unique_products[:limit]

    except Exception as e:
        logger.error(f"Failed to get recommended products: {e}")
        return []


async def get_full_conversation_history(user_id: str, limit: int = MEMORY_CONTEXT_WINDOW) -> list:
    """
    ดึงประวัติการสนทนาแบบเต็มรูปแบบ (รวม metadata)
    สำหรับใช้ใน AI ที่ต้องการ context ละเอียด
    """
    try:
        if not supabase_client:
            return []

        result = supabase_client.table('conversation_memory')\
            .select('role, content, metadata, created_at')\
            .eq('user_id', user_id)\
            .order('created_at', desc=True)\
            .limit(limit)\
            .execute()

        if not result.data:
            return []

        # Reverse to get chronological order
        messages = list(reversed(result.data))
        logger.info(f"✓ Retrieved {len(messages)} full messages from memory")
        return messages

    except Exception as e:
        logger.error(f"Failed to get full conversation history: {e}")
        return []


async def get_conversation_summary(user_id: str) -> dict:
    """
    สรุปบทสนทนา: หัวข้อที่คุย, สินค้าที่แนะนำ, พืชที่ถาม
    ใช้สำหรับให้ AI เข้าใจ context ได้ดีขึ้น
    """
    try:
        if not supabase_client:
            return {}

        result = supabase_client.table('conversation_memory')\
            .select('role, content, metadata, created_at')\
            .eq('user_id', user_id)\
            .order('created_at', desc=True)\
            .limit(MEMORY_CONTEXT_WINDOW)\
            .execute()

        if not result.data:
            return {}

        # Extract topics and products from conversation
        topics = []
        products_mentioned = []
        plants_mentioned = []
        last_question = ""

        # Plant keywords
        plant_keywords = [
            "ข้าว", "ทุเรียน", "มะม่วง", "ส้ม", "พริก", "ข้าวโพด", "อ้อย",
            "ลำไย", "มันสำปะหลัง", "ยางพารา", "ปาล์ม", "ถั่ว", "ผัก"
        ]

        for msg in result.data:
            content = msg.get("content", "")
            metadata = msg.get("metadata", {})

            # Get last user question
            if msg["role"] == "user" and not last_question:
                last_question = content[:200]

            # Extract products from metadata
            if isinstance(metadata, dict) and metadata.get("type") == "product_recommendation":
                products = metadata.get("products", [])
                for p in products:
                    name = p.get("product_name", "")
                    if name and name not in products_mentioned:
                        products_mentioned.append(name)

            # Extract plants from content
            for plant in plant_keywords:
                if plant in content and plant not in plants_mentioned:
                    plants_mentioned.append(plant)

            # Extract topics (simple keyword detection)
            if msg["role"] == "user":
                if any(kw in content for kw in ["โรค", "รักษา", "ป้องกัน"]):
                    if "โรคพืช" not in topics:
                        topics.append("โรคพืช")
                if any(kw in content for kw in ["แมลง", "เพลี้ย", "หนอน", "กำจัด"]):
                    if "แมลงศัตรูพืช" not in topics:
                        topics.append("แมลงศัตรูพืช")
                if any(kw in content for kw in ["หญ้า", "วัชพืช"]):
                    if "วัชพืช" not in topics:
                        topics.append("วัชพืช")
                if any(kw in content for kw in ["บำรุง", "ธาตุ", "ปุ๋ย", "ติดดอก", "ติดผล"]):
                    if "การบำรุง" not in topics:
                        topics.append("การบำรุง")
                if any(kw in content for kw in ["วิธีใช้", "อัตรา", "ผสม"]):
                    if "วิธีใช้สินค้า" not in topics:
                        topics.append("วิธีใช้สินค้า")

        # Fallback: if no products found via metadata, scan assistant message text
        if not products_mentioned:
            try:
                from app.services.chat import ICP_PRODUCT_NAMES
                for msg in result.data:
                    if msg["role"] != "assistant":
                        continue
                    content_lower = msg.get("content", "").lower()
                    for product_name, aliases in ICP_PRODUCT_NAMES.items():
                        for alias in aliases:
                            if alias.lower() in content_lower and product_name not in products_mentioned:
                                products_mentioned.append(product_name)
                    if products_mentioned:
                        break  # got products from most recent assistant message
            except ImportError:
                logger.warning("Could not import ICP_PRODUCT_NAMES for fallback product extraction")

        summary = {
            "topics": topics[:5],
            "products_mentioned": products_mentioned[:10],
            "plants_mentioned": plants_mentioned[:5],
            "last_question": last_question,
            "total_messages": len(result.data)
        }

        logger.info(f"✓ Conversation summary: {len(topics)} topics, {len(products_mentioned)} products")
        return summary

    except Exception as e:
        logger.error(f"Failed to get conversation summary: {e}")
        return {}


async def get_enhanced_context(user_id: str) -> str:
    """
    สร้าง context แบบ enhanced สำหรับ AI
    รวม: สินค้าที่กำลังคุย + บทสนทนาล่าสุด + สรุปหัวข้อ + สินค้าที่แนะนำ
    ใช้ structured format เพื่อให้ AI เข้าใจง่ายขึ้น
    """
    try:
        # Get current product focus first (most important for follow-up questions)
        current_focus = await get_current_product_focus(user_id)

        # Get conversation context (use config value)
        context = await get_conversation_context(user_id, limit=MEMORY_CONTEXT_WINDOW)

        # Get conversation summary
        summary = await get_conversation_summary(user_id)

        # Build structured enhanced context
        parts = []

        # Section 0: Current product focus (most important!)
        if current_focus:
            parts.append(f"[สินค้าที่กำลังคุยอยู่] {current_focus['product_name']}")
            parts.append("")

        # Section 1: Recent conversation
        if context:
            parts.append("[บทสนทนาล่าสุด]")
            parts.append(context)

        if not summary:
            return "\n".join(parts) if parts else context

        # Section 2: Products recommended
        if summary.get("products_mentioned"):
            parts.append("")
            parts.append(f"[สินค้าที่แนะนำไปแล้ว] {', '.join(summary['products_mentioned'][:5])}")

        # Section 3: Current topics
        topic_parts = []
        if summary.get("topics"):
            topic_parts.append(f"หัวข้อ: {', '.join(summary['topics'])}")
        if summary.get("plants_mentioned"):
            topic_parts.append(f"พืช: {', '.join(summary['plants_mentioned'])}")
        if topic_parts:
            parts.append("")
            parts.append(f"[หัวข้อที่กำลังคุย] {' | '.join(topic_parts)}")

        return "\n".join(parts)

    except Exception as e:
        logger.error(f"Failed to get enhanced context: {e}")
        return await get_conversation_context(user_id)


# =================================================================
# Current Product Focus Tracking
# =================================================================
# เก็บใน Supabase `cache` table เท่านั้น (ไม่มี in-memory)
# TTL 5 นาที — หลังจากนี้จะถือว่าเริ่มบทสนทนาใหม่

PRODUCT_FOCUS_TTL_SECONDS = 300  # 5 minutes


def _focus_key(user_id: str) -> str:
    return f"product_focus:{user_id}"


async def save_current_product_focus(user_id: str, product_name: str, metadata: dict = None):
    """
    บันทึกสินค้าที่กำลังคุยอยู่ลง Supabase cache table
    TTL: 5 นาที
    """
    from datetime import datetime, timedelta, timezone

    try:
        if not supabase_client:
            return
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=PRODUCT_FOCUS_TTL_SECONDS)).isoformat()
        supabase_client.table('cache').upsert({
            "key": _focus_key(user_id),
            "value": {"product_name": product_name, "metadata": metadata or {}},
            "expires_at": expires_at
        }).execute()
        logger.info(f"✓ Saved product focus: {product_name} for user {user_id[:8]}... (TTL={PRODUCT_FOCUS_TTL_SECONDS}s)")
    except Exception as e:
        logger.warning(f"Failed to save product focus: {e}")


async def get_current_product_focus(user_id: str) -> dict | None:
    """
    ดึงสินค้าที่กำลังคุยอยู่จาก Supabase cache table (ถ้ายังไม่หมดอายุ)
    Returns: {"product_name": str} หรือ None
    """
    from datetime import datetime, timezone

    try:
        if not supabase_client:
            return None
        result = supabase_client.table('cache')\
            .select('value, expires_at')\
            .eq('key', _focus_key(user_id))\
            .gt('expires_at', datetime.now(timezone.utc).isoformat())\
            .execute()
        if result.data:
            return result.data[0]['value']
        return None
    except Exception as e:
        logger.warning(f"Failed to get product focus: {e}")
        return None


async def clear_product_focus(user_id: str):
    """ล้าง product focus"""
    try:
        if supabase_client:
            supabase_client.table('cache')\
                .delete()\
                .eq('key', _focus_key(user_id))\
                .execute()
    except Exception as e:
        logger.warning(f"Failed to clear product focus: {e}")

    logger.info(f"✓ Cleared product focus for user {user_id[:8]}...")
