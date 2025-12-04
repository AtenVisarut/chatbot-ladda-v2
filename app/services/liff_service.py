"""
LIFF Registration Service
Handles user registration from LIFF frontend
"""
import logging
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from app.services.services import supabase_client, analytics_tracker

logger = logging.getLogger(__name__)


class LiffRegistrationData(BaseModel):
    """Data model for LIFF registration"""
    line_user_id: str = Field(..., description="LINE User ID")
    display_name: Optional[str] = Field(None, description="LINE Display Name")
    full_name: str = Field(..., min_length=2, description="Full name")
    phone_number: str = Field(..., pattern=r'^[0-9]{9,10}$', description="Phone number")
    province: str = Field(..., min_length=2, description="Province")
    crops_grown: List[str] = Field(default=[], description="List of crops")
    picture_url: Optional[str] = Field(None, description="LINE Profile Picture URL")


async def register_user_from_liff(data: LiffRegistrationData) -> Dict[str, Any]:
    """
    Register or update user from LIFF frontend

    Args:
        data: Registration data from LIFF

    Returns:
        dict with status and message
    """
    try:
        logger.info(f"LIFF Registration for user: {data.line_user_id}")
        logger.info(f"Data: name={data.full_name}, phone={data.phone_number}, province={data.province}")

        if not supabase_client:
            raise Exception("Database service not available")

        # Prepare user data
        user_data = {
            "line_user_id": data.line_user_id,
            "display_name": data.display_name or data.full_name,
            "phone_number": data.phone_number,
            "province": data.province,
            "crops_grown": data.crops_grown or [],
            "registration_completed": True
        }

        # Upsert to database
        result = supabase_client.table("users").upsert(
            user_data,
            on_conflict="line_user_id"
        ).execute()

        logger.info(f"Successfully registered user {data.line_user_id} via LIFF")

        # Track registration event
        if analytics_tracker:
            await analytics_tracker.track_registration(data.line_user_id)

        return {
            "status": "success",
            "message": "ลงทะเบียนสำเร็จ",
            "user_id": data.line_user_id
        }

    except Exception as e:
        logger.error(f"LIFF Registration error: {e}", exc_info=True)
        raise Exception(f"Registration failed: {str(e)}")


async def check_registration_status(user_id: str) -> Dict[str, Any]:
    """
    Check if user has completed registration

    Args:
        user_id: LINE User ID

    Returns:
        dict with registration status
    """
    try:
        if not supabase_client:
            return {"registered": False, "error": "Database not available"}

        result = supabase_client.table("users").select("*").eq(
            "line_user_id", user_id
        ).execute()

        if result.data and len(result.data) > 0:
            user = result.data[0]
            return {
                "registered": user.get("registration_completed", False),
                "user": {
                    "display_name": user.get("display_name"),
                    "province": user.get("province"),
                    "crops_grown": user.get("crops_grown", [])
                }
            }

        return {"registered": False}

    except Exception as e:
        logger.error(f"Check registration error: {e}")
        return {"registered": False, "error": str(e)}
