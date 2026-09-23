"""
Early-warning alert endpoints.

GET  /alerts                     active alerts (newest first) with delivery status
GET  /alerts/recent              latest alerts incl. expired / superseded
GET  /alerts/stream              Server-Sent Events: live alert + delivery feed
GET  /alerts/providers           which notification channels are configured
POST /alerts/evaluate            run the monitor for a region now (optionally with observed rain)
POST /alerts/test                send a realistic TEST alert through the channels
GET  /alerts/{id}                one alert
POST /alerts/{id}/acknowledge    acknowledge from the dashboard
GET  /alerts/{id}/ack            one-click acknowledge link used inside messages
GET  /alerts/{id}/events         audit trail
POST /alerts/{id}/review | /severity | /resolve | /note   operator lifecycle actions
"""

import asyncio
import hmac
import json
from html import escape

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, StreamingResponse

from app.db.models import Recipient
from app.db.session import session_scope
from app.schemas.alert import (
    AcknowledgeRequest,
    AlertEventResponse,
    AlertResponse,
    EvaluateRequest,
    EvaluateResponse,
    NoteRequest,
    ProviderStatus,
    ResolveRequest,
    ReviewRequest,
    SeverityRequest,
    TestAlertRequest,
)
from app.services.alert_service import AlertNotFoundError, evaluate_and_dispatch, get_alert_service
from app.services.geo_data import UnknownRegionError
from app.services.notifications.broadcaster import broadcaster
from app.services.notifications.dispatcher import ack_token, get_dispatcher

router = APIRouter()


@router.get("", response_model=list[AlertResponse])
def list_active_alerts() -> list[AlertResponse]:
    """All currently active early-warning alerts, newest first."""
    return get_alert_service().list_active()


@router.get("/recent", response_model=list[AlertResponse])
def list_recent_alerts(limit: int = Query(50, ge=1, le=500)) -> list[AlertResponse]:
    return get_alert_service().list_recent(limit)


STREAM_LIFETIME_S = 10
STREAM_RETRY_MS = 1000


@router.get("/stream")
async def alert_stream(request: Request) -> StreamingResponse:
    """Live feed for the dashboard (EventSource).

    Each connection ends after STREAM_LIFETIME_S and the browser reconnects
    (`retry:`). An endless response would block uvicorn's graceful shutdown,
    so `--reload` froze the whole API while a dashboard tab was open.
    """
    queue = broadcaster.subscribe()
    loop = asyncio.get_running_loop()
    deadline = loop.time() + STREAM_LIFETIME_S

    async def events():
        try:
            yield f"retry: {STREAM_RETRY_MS}\ndata: {json.dumps({'type': 'hello'})}\n\n"
            while not await request.is_disconnected():
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=min(remaining, 15))
                    yield f"data: {json.dumps(event, default=str)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            broadcaster.unsubscribe(queue)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/providers", response_model=list[ProviderStatus])
def provider_status() -> list[dict]:
    return get_dispatcher().provider_status()


@router.post("/evaluate", response_model=EvaluateResponse)
async def evaluate(req: EvaluateRequest) -> EvaluateResponse:
    """Evaluate a region right now. Supply observed/forecast rain (`rain_24h_mm`
    or `rain_event_mm`) to assess a live situation; alerts that cross the
    configured thresholds are issued and dispatched."""
    try:
        return await evaluate_and_dispatch(req, source="manual")
    except UnknownRegionError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post("/test", response_model=AlertResponse)
async def send_test_alert(req: TestAlertRequest) -> AlertResponse:
    service = get_alert_service()
    try:
        alert_id = await asyncio.to_thread(service.create_test_alert, req)
    except (UnknownRegionError, ValueError) as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    await get_dispatcher().dispatch(alert_id, recipient_ids=req.recipient_ids, channels=req.channels)
    return service.get(alert_id)


@router.get("/{alert_id}", response_model=AlertResponse)
def get_alert(alert_id: int) -> AlertResponse:
    alert = get_alert_service().get(alert_id)
    if alert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found")
    return alert


@router.post("/{alert_id}/acknowledge", response_model=AlertResponse)
async def acknowledge(alert_id: int, body: AcknowledgeRequest) -> AlertResponse:
    alert = get_alert_service().acknowledge(alert_id, body.by)
    if alert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found")
    broadcaster.publish({"type": "acknowledged", "alert_id": alert_id, "by": alert.acknowledged_by})
    return alert


# --- Lifecycle / audit trail ------------------------------------------------
def _lifecycle(alert_id: int, event_type: str, fn) -> AlertResponse:
    try:
        alert = fn()
    except AlertNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found") from exc
    broadcaster.publish({"type": event_type, "alert_id": alert_id})
    return alert


@router.get("/{alert_id}/events", response_model=list[AlertEventResponse])
def alert_events(alert_id: int) -> list[AlertEventResponse]:
    """Full audit trail: detected, generated, reviewed, sent, acknowledged, severity changes, notes, resolved."""
    try:
        return get_alert_service().events(alert_id)
    except AlertNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found") from exc


@router.post("/{alert_id}/review", response_model=AlertResponse)
async def review_alert(alert_id: int, body: ReviewRequest) -> AlertResponse:
    return _lifecycle(alert_id, "reviewed", lambda: get_alert_service().review(alert_id, body.by, body.note))


@router.post("/{alert_id}/severity", response_model=AlertResponse)
async def change_severity(alert_id: int, body: SeverityRequest) -> AlertResponse:
    return _lifecycle(
        alert_id, "severity_changed",
        lambda: get_alert_service().change_severity(alert_id, body.by, body.level, body.reason),
    )


@router.post("/{alert_id}/resolve", response_model=AlertResponse)
async def resolve_alert(alert_id: int, body: ResolveRequest) -> AlertResponse:
    return _lifecycle(alert_id, "resolved", lambda: get_alert_service().resolve(alert_id, body.by, body.note))


@router.post("/{alert_id}/note", response_model=AlertResponse)
async def add_note(alert_id: int, body: NoteRequest) -> AlertResponse:
    return _lifecycle(alert_id, "note", lambda: get_alert_service().add_note(alert_id, body.by, body.text))


@router.get("/{alert_id}/ack", response_class=HTMLResponse)
async def acknowledge_link(alert_id: int, token: str, r: int = 0) -> HTMLResponse:
    """Target of the 'Acknowledge' button in Telegram / e-mail / WhatsApp messages."""
    recipient_id = r or None
    if not hmac.compare_digest(token, ack_token(alert_id, recipient_id)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid acknowledgement link")
    by = "Control room"
    if recipient_id:
        with session_scope() as db:
            recipient = db.get(Recipient, recipient_id)
            by = recipient.name if recipient else by
    alert = get_alert_service().acknowledge(alert_id, by)
    if alert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found")
    broadcaster.publish({"type": "acknowledged", "alert_id": alert_id, "by": alert.acknowledged_by})
    return HTMLResponse(
        f"""<!doctype html><meta name=viewport content="width=device-width,initial-scale=1">
<title>Alert acknowledged</title>
<body style="font-family:system-ui,sans-serif;background:#f1f5f9;display:grid;place-items:center;min-height:100vh;margin:0">
<div style="background:#fff;padding:28px 32px;border-radius:12px;max-width:420px;box-shadow:0 1px 3px #0002">
<div style="font-size:40px">✅</div><h2 style="margin:8px 0">Alert #{alert.id} acknowledged</h2>
<p style="color:#475569">{escape(alert.title)}</p>
<p style="color:#475569">Acknowledged by <b>{escape(alert.acknowledged_by or by)}</b>. The control room dashboard has been updated.</p>
</div></body>"""
    )
