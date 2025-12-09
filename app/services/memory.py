import logging
from app.services.services import supabase_client
from app.config import MAX_MEMORY_MESSAGES, MEMORY_CONTEXT_WINDOW

logger = logging.getLogger(__name__)

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
            .select('role, content, created_at')\
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
            role = "ผู้ใช้" if msg["role"] == "user" else "ฉัน"
            content = msg["content"][:150]  # Truncate for context
            context_parts.append(f"{role}: {content}")
        
        logger.info(f"✓ Retrieved {len(messages)} messages from memory")
        return "\n".join(context_parts)
        
    except Exception as e:
        logger.error(f"Failed to get conversation context: {e}")
        return ""

async def cleanup_old_memory(user_id: str):
    """Keep only last N messages per user"""
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
        ids_to_keep = [msg['id'] for msg in result.data[:MAX_MEMORY_MESSAGES]]
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
    """Clear all conversation memory for user"""
    try:
        if not supabase_client:
            logger.warning("Supabase not available")
            return
        
        result = supabase_client.table('conversation_memory')\
            .delete()\
            .eq('user_id', user_id)\
            .execute()
        
        logger.info(f"✓ Cleared memory for user {user_id[:8]}...")
        
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
