"""
What-if simulator + assistant endpoints.

POST /scenarios/simulate     deterministic what-if (no LLM): villages, drivers, incidents
POST /chat                   conversational what-if assistant (Claude + simulation tools)
GET  /chat/{session_id}      conversation transcript
GET  /geo/regions            monitored regions with districts and reference spells
GET  /geo/villages           village terrain / hydrology profiles
GET  /geo/incidents          documented past flood incidents
"""

from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.chat import ChatHistoryItem, ChatRequest, ChatResponse
from app.schemas.scenario import ScenarioRequest, ScenarioResult
from app.services import geo_data, incident_service
from app.services.chat.assistant import AssistantUnavailableError, get_assistant
from app.services.scenario_service import ScenarioService

scenario_router = APIRouter()
chat_router = APIRouter()
geo_router = APIRouter()

_scenarios = ScenarioService()


@scenario_router.post("/simulate", response_model=ScenarioResult)
def simulate(req: ScenarioRequest) -> ScenarioResult:
    """Run a what-if: e.g. `{"region": "Kerala", "rainfall_change_pct": 20}`."""
    try:
        return _scenarios.simulate(req)
    except geo_data.UnknownRegionError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@chat_router.post("", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    """Describe a situation in plain language; the assistant simulates it and explains
    what could happen, why, and which past incidents looked similar."""
    try:
        return get_assistant().chat(req.message, req.session_id)
    except AssistantUnavailableError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


@chat_router.get("/{session_id}", response_model=list[ChatHistoryItem])
def chat_transcript(session_id: str) -> list[ChatHistoryItem]:
    return get_assistant().transcript(session_id)


@geo_router.get("/regions")
def regions() -> list[dict]:
    return geo_data.regions()


@geo_router.get("/villages")
def villages(region: str | None = Query(None)) -> list[dict]:
    try:
        return geo_data.villages_in(region) if region else geo_data.villages()
    except geo_data.UnknownRegionError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@geo_router.get("/incidents")
def incidents(
    region: str | None = Query(None),
    cause: str | None = Query(None),
    village: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> list[dict]:
    try:
        return incident_service.search(region=region, cause=cause, village=village, limit=limit)
    except geo_data.UnknownRegionError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
