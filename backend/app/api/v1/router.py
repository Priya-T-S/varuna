"""Versioned API router — aggregates all v1 endpoint modules."""

from fastapi import APIRouter

from app.api.v1.endpoints import alert_admin, alerts, health, predictions, scenarios, system

api_router = APIRouter()

api_router.include_router(health.router, tags=["health"])
api_router.include_router(predictions.router, prefix="/predictions", tags=["predictions"])
api_router.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
api_router.include_router(alert_admin.recipients_router, prefix="/recipients", tags=["alert admin"])
api_router.include_router(alert_admin.rules_router, prefix="/alert-rules", tags=["alert admin"])
api_router.include_router(scenarios.scenario_router, prefix="/scenarios", tags=["what-if"])
api_router.include_router(scenarios.chat_router, prefix="/chat", tags=["what-if"])
api_router.include_router(scenarios.geo_router, prefix="/geo", tags=["what-if"])
api_router.include_router(system.router, prefix="/system", tags=["system"])
api_router.include_router(system.demo_router, prefix="/demo", tags=["demo"])
