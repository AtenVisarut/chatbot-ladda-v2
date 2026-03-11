"""
Shared fixtures for all tests.
Mocks external services (OpenAI, Supabase, Redis, LINE) so tests run
without real credentials.
"""

import os
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Set dummy env BEFORE any app module is imported
# ---------------------------------------------------------------------------
os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "eyJ-test-dummy")
os.environ.setdefault("LINE_CHANNEL_ACCESS_TOKEN", "test-dummy")
os.environ.setdefault("LINE_CHANNEL_SECRET", "test-dummy")
os.environ.setdefault("SECRET_KEY", "ci-test-secret")
os.environ.setdefault("ADMIN_PASSWORD", "ci-test-password")


# ---------------------------------------------------------------------------
# Event loop (pytest-asyncio)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# Mock Supabase client
# ---------------------------------------------------------------------------
@pytest.fixture()
def mock_supabase():
    client = MagicMock()
    # .table("x").select("*").execute() → empty data
    table = MagicMock()
    table.select.return_value = table
    table.eq.return_value = table
    table.ilike.return_value = table
    table.limit.return_value = table
    table.execute.return_value = MagicMock(data=[], count=0)
    client.table.return_value = table
    # .rpc("hybrid_search_products3", ...).execute() → empty
    client.rpc.return_value = MagicMock(execute=MagicMock(return_value=MagicMock(data=[])))
    return client


# ---------------------------------------------------------------------------
# Mock OpenAI async client
# ---------------------------------------------------------------------------
@pytest.fixture()
def mock_openai():
    client = AsyncMock()
    # chat.completions.create → fake response
    choice = MagicMock()
    choice.message.content = '{"intent": "greeting", "confidence": 0.9}'
    response = MagicMock(choices=[choice])
    client.chat.completions.create = AsyncMock(return_value=response)
    # embeddings.create → fake embedding
    embedding_data = MagicMock(embedding=[0.0] * 1536)
    client.embeddings.create = AsyncMock(
        return_value=MagicMock(data=[embedding_data])
    )
    return client


# ---------------------------------------------------------------------------
# FastAPI test client (httpx)
# ---------------------------------------------------------------------------
@pytest.fixture()
def test_app():
    """Return the FastAPI app with mocked lifespan dependencies."""
    from app.main import app
    return app


@pytest.fixture()
async def client(test_app):
    """Async httpx test client — no real server needed."""
    from httpx import AsyncClient, ASGITransport

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
