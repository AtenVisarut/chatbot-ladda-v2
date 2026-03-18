"""
Async wrapper for sync Supabase .execute() calls.

Supabase Python SDK uses sync httpx — every .execute() blocks the async event loop
for 50-200ms. This wrapper runs them in a thread pool via asyncio.to_thread().
"""

import asyncio
from typing import Any


async def aexecute(query_builder) -> Any:
    """Run sync Supabase .execute() in thread pool — does not block event loop."""
    return await asyncio.to_thread(query_builder.execute)
