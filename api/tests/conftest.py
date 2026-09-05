import asyncio

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db import engine
from app.main import app
from app.redis_client import redis_client

# The DB engine's connection pool is a module-level singleton whose asyncpg
# connections are bound to whichever event loop first used them.
# pytest-asyncio's default is a fresh loop per test function, which would
# make later tests reuse connections from an already-closed loop — share one
# loop for the whole session instead.


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture(autouse=True)
async def clean_db():
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE leadership_log, admin_actions, webhook_events, bids, "
                "payment_intents, project_claims, projects, refresh_tokens, otp_requests, users "
                "RESTART IDENTITY CASCADE"
            )
        )
    await redis_client.flushdb()
    yield
