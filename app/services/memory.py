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
