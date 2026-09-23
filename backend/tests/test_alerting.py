"""Real-time alerting: thresholds, cooldown/escalation, fan-out, retries, acknowledgement."""

from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.notifications.base import DeliveryResult, NotificationProvider, RecipientTarget
from app.services.notifications.dispatcher import AlertDispatcher, ack_url, set_dispatcher
from app.services.notifications.providers import ConsoleProvider, InAppProvider

client = TestClient(app)


class FakeProvider(NotificationProvider):
    def __init__(self, channel: str, *, enabled: bool = True, fail_times: int = 0, retryable: bool = True):
        self.channel = channel
        self.display_name = f"Fake {channel}"
        self._enabled = enabled
        self.fail_times = fail_times
        self.retryable = retryable
        self.sent: list[tuple[str, int]] = []

    def enabled(self) -> bool:
        return self._enabled

    def missing_config(self) -> list[str]:
        return [] if self._enabled else [f"{self.channel.upper()}_TOKEN"]

    def target_for(self, recipient: RecipientTarget) -> str | None:
        return {
            "email": recipient.email, "telegram": recipient.telegram_chat_id,
            "sms": recipient.phone, "whatsapp": recipient.whatsapp or recipient.phone,
        }[self.channel]

    async def send(self, target, alert, recipient) -> DeliveryResult:
        if self.fail_times > 0:
            self.fail_times -= 1
            return DeliveryResult(ok=False, error="temporary failure", retryable=self.retryable)
        self.sent.append((target, alert.id))
        return DeliveryResult(ok=True, provider_message_id=f"{self.channel}-{len(self.sent)}")


@pytest.fixture
def providers():
    fakes = {
        "email": FakeProvider("email"),
        "telegram": FakeProvider("telegram", fail_times=1),       # succeeds on retry
        "sms": FakeProvider("sms", enabled=False),                 # not configured
        "whatsapp": FakeProvider("whatsapp", fail_times=5, retryable=False),  # permanent failure
        "inapp": InAppProvider(),
        "console": ConsoleProvider(),
    }
    set_dispatcher(AlertDispatcher(providers=fakes, backoff_seconds=0))
    yield fakes
    set_dispatcher(None)


@pytest.fixture
def collector():
    response = client.post(
        "/api/v1/recipients",
        json={
            "name": "District Collector, Alappuzha (test)",
            "region": "kerala",
            "district": "Alappuzha",
            "email": "collector.alp@example.gov.in",
            "telegram_chat_id": "123456",
            "phone": "+919800000001",
            "channels": ["email", "telegram", "sms", "whatsapp"],
            "min_level": "high",
        },
    )
    assert response.status_code == 201, response.text
    recipient = response.json()
    assert recipient["region"] == "Kerala"
    yield recipient
    client.delete(f"/api/v1/recipients/{recipient['id']}")


def _evaluate(**overrides):
    body = {"region": "Kerala", "rain_event_mm": 420, "duration_days": 3, "antecedent": "saturated", **overrides}
    response = client.post("/api/v1/alerts/evaluate", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_threshold_crossing_issues_and_dispatches_alert(providers, collector):
    result = _evaluate(ignore_cooldown=True)
    alappuzha = next(d for d in result["districts"] if d["district"] == "Alappuzha")
    assert alappuzha["level"] in {"high", "severe"}
    assert "issued" in alappuzha["action"]
    alert_id = int(alappuzha["action"].split("#")[1].split()[0])

    deliveries = {(d["channel"], d["recipient"]): d for d in result["deliveries"][str(alert_id)]}
    name = collector["name"]
    assert deliveries[("email", name)]["status"] == "sent"
    assert deliveries[("telegram", name)]["status"] == "sent"            # after one retry
    assert deliveries[("sms", name)]["status"] == "skipped"               # provider not configured
    assert "not configured" in deliveries[("sms", name)]["error"]
    assert deliveries[("whatsapp", name)]["status"] == "failed"           # non-retryable error
    assert deliveries[("inapp", "Dashboard")]["status"] == "sent"
    assert providers["email"].sent[-1] == ("collector.alp@example.gov.in", alert_id)

    alert = client.get(f"/api/v1/alerts/{alert_id}").json()
    assert alert["district"] == "Alappuzha" and alert["is_active"]
    assert alert["affected_villages"] and alert["top_drivers"]
    assert alert["similar_incident"]["id"].startswith("KL-")
    telegram_row = next(d for d in alert["deliveries"] if d["channel"] == "telegram")
    assert telegram_row["attempts"] == 2
    email_row = next(d for d in alert["deliveries"] if d["channel"] == "email")
    assert email_row["target"].startswith("co***@")  # masked in the audit trail
    assert any(a["id"] == alert_id for a in client.get("/api/v1/alerts").json())


def test_cooldown_suppresses_repeat_but_escalation_goes_through(providers, collector):
    first = _evaluate(rain_event_mm=230, antecedent="normal", ignore_cooldown=True)
    level = next(d for d in first["districts"] if d["district"] == "Alappuzha")["level"]
    assert level in {"high", "severe"}

    repeat = _evaluate(rain_event_mm=230, antecedent="normal")
    action = next(d for d in repeat["districts"] if d["district"] == "Alappuzha")["action"]
    assert "cooldown" in action

    if level == "high":
        worse = _evaluate(rain_event_mm=600, antecedent="saturated", dam_release=True)
        escalated = next(d for d in worse["districts"] if d["district"] == "Alappuzha")
        assert escalated["level"] == "severe" and "issued" in escalated["action"]


def test_light_rain_stays_below_threshold(providers):
    result = _evaluate(rain_event_mm=15, antecedent="dry")
    assert result["alerts_created"] == []
    assert all("below threshold" in d["action"] for d in result["districts"])


def test_acknowledge_link_requires_valid_token(providers, collector):
    result = _evaluate(ignore_cooldown=True)
    alert_id = result["alerts_created"][0]
    url = urlparse(ack_url(alert_id, collector["id"]))
    query = {k: v[0] for k, v in parse_qs(url.query).items()}

    bad = client.get(url.path, params={**query, "token": "0" * 24})
    assert bad.status_code == 403
    good = client.get(url.path, params=query)
    assert good.status_code == 200 and "acknowledged" in good.text

    alert = client.get(f"/api/v1/alerts/{alert_id}").json()
    if alert["district"] == "Alappuzha":
        assert alert["acknowledged_by"] == collector["name"]
    assert alert["acknowledged_at"] is not None


def test_test_alert_respects_channel_filter(providers, collector):
    response = client.post(
        "/api/v1/alerts/test",
        json={"region": "Kerala", "district": "Alappuzha", "recipient_ids": [collector["id"]], "channels": ["email"]},
    )
    assert response.status_code == 200, response.text
    alert = response.json()
    assert alert["title"].startswith("[TEST]") and alert["source"] == "test"
    channels = {d["channel"] for d in alert["deliveries"]}
    assert "email" in channels and "telegram" not in channels and "sms" not in channels


def test_provider_status_and_rules_crud(providers):
    status = {p["channel"]: p for p in client.get("/api/v1/alerts/providers").json()}
    assert status["email"]["enabled"] and not status["sms"]["enabled"]
    assert status["sms"]["missing_config"] == ["SMS_TOKEN"]

    created = client.post("/api/v1/alert-rules", json={"region": "Mumbai", "min_level": "moderate", "cooldown_minutes": 60})
    assert created.status_code == 201
    rule = created.json()
    assert rule["region"] == "Mumbai"
    updated = client.put(f"/api/v1/alert-rules/{rule['id']}", json={**rule, "min_level": "severe"})
    assert updated.json()["min_level"] == "severe"
    assert client.delete(f"/api/v1/alert-rules/{rule['id']}").status_code == 204


def test_real_providers_report_disabled_without_credentials():
    status = {p["channel"]: p for p in AlertDispatcher().provider_status()}
    for channel in ("telegram", "email", "sms", "whatsapp"):
        assert status[channel]["enabled"] is False and status[channel]["missing_config"]
    assert status["inapp"]["enabled"] and status["console"]["enabled"]
