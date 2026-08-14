"""Realtime attendance stream (SSE).

PromptID: ADMS-Frontend-RealtimeSSE-001

GET /api/v1/stream/attendance — authenticated (VIEWER+), streams the
Collector's MQTT ``attendance/events`` topic to the browser as Server-Sent
Events. Live-only channel: no replay/backfill (that stays with the
attendance GET endpoints). No DB writes, no device access.
"""

import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.api.mqtt_stream import get_stream

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/stream", tags=["stream"])

HEARTBEAT_INTERVAL = 15.0


async def attendance_event_generator(
    stream, client_id, queue, request, heartbeat_interval: float
) -> AsyncGenerator[str, None]:
    """Core SSE body: yields attendance events + heartbeats, unregisters on exit.

    Extracted for deterministic unit testing (no HTTP layer required).
    """
    try:
        while True:
            if await request.is_disconnected():
                break
            try:
                payload = await asyncio.wait_for(
                    queue.get(), timeout=heartbeat_interval
                )
                data = json.dumps(payload, ensure_ascii=False)
                yield f"event: attendance\ndata: {data}\n\n"
            except asyncio.TimeoutError:
                yield ": ping\n\n"
    finally:
        stream.unregister(client_id)
        log.debug("SSE client %s disconnected", client_id)


@router.get(
    "/attendance",
    summary="Realtime attendance events (SSE)",
    description=(
        "Server-Sent Events stream of attendance scans as published by the "
        "Collector on MQTT. Live-only (no replay). Requires a valid Bearer "
        "token (VIEWER+)."
    ),
)
async def stream_attendance(request: Request) -> StreamingResponse:
    stream = get_stream()
    stream.ensure_started()
    client_id, queue = stream.register()

    return StreamingResponse(
        attendance_event_generator(
            stream, client_id, queue, request, HEARTBEAT_INTERVAL
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
