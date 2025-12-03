"""
Welcome Service
Handles welcome messages and usage guides for new users
"""

import logging
from typing import Dict, List
from app.utils.flex_messages import (
    create_welcome_flex,
    create_registration_required_flex,
    create_usage_guide_flex,
    create_product_catalog_flex,
    create_help_menu_flex
)

logger = logging.getLogger(__name__)


def get_welcome_message() -> Dict:
    """
    Create welcome message for new users (follow event)
    Returns LINE Flex Message
    """
    return create_welcome_flex()


def get_usage_guide() -> Dict:
    """
    Create comprehensive usage guide message
    Returns LINE Flex Message
    """
    return create_usage_guide_flex()


def get_registration_required_message() -> Dict:
    """
    Create message asking user to register before using features
    Returns LINE Flex Message
    """
    return create_registration_required_flex()


def get_product_catalog_message() -> Dict:
    """
    Create product catalog message
    Returns LINE Flex Message
    """
    return create_product_catalog_flex()


def get_help_menu() -> Dict:
    """
    Create help menu message
    Returns LINE Flex Message
    """
    return create_help_menu_flex()
