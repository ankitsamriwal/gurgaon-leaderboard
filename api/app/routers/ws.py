"""WS /ws/leaderboard (docs/02-api-spec.md). Server pushes the recomputed
leaderboard whenever a webhook-verified (or mock) bid lands — see
app/services/projects.py's publish_leaderboard_update(), called from
app/routers/webhooks.py and app/routers/payments.py.

Broadcasts via Redis pub/sub rather than an in-process list of sockets, so
this works correctly across multiple uvicorn/gunicorn worker processes in
production (docs/00's Redis is already load-bearing for cache/rate-limit;
this is the same instance).
"""

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.redis_client import redis_client
from app.services.projects import LEADERBOARD_WS_CHANNEL, get_leaderboard
from app.db import async_session

router = APIRouter()
logger = logging.getLogger("ws")


@router.websocket("/ws/leaderboard")
async def ws_leaderboard(websocket: WebSocket) -> None:
    await websocket.accept()

    # Send current state immediately so the client doesn't wait for the
    # next bid to render anything.
    async with async_session() as session:
        await websocket.send_json(await get_leaderboard(session))

    pubsub = redis_client.pubsub()
    await pubsub.subscribe(LEADERBOARD_WS_CHANNEL)
    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            await websocket.send_text(message["data"])
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(LEADERBOARD_WS_CHANNEL)
        await pubsub.aclose()
