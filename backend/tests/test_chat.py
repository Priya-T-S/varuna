"""What-if assistant: tool functions + the chat loop against a scripted fake Claude client."""

import json

import pytest
from anthropic.types.beta import BetaMessage, BetaTextBlock, BetaToolUseBlock
from fastapi.testclient import TestClient

from app.main import app
from app.services.chat import assistant as assistant_module
from app.services.chat.assistant import FloodAssistant
from app.services.chat.tools import (
    TOOLS,
    begin_collection,
    draft_alert_message,
    get_village_profile,
    search_past_incidents,
    simulate_flood_scenario,
)

client = TestClient(app)


def _message(content, stop_reason):
    return BetaMessage(
        id="msg_test", type="message", role="assistant", model="claude-opus-5", content=content,
        stop_reason=stop_reason, stop_sequence=None,
        usage={"input_tokens": 10, "output_tokens": 10},
    )


class FakeRunner:
    """Mimics the SDK tool runner: turn 1 calls a tool, turn 2 answers."""

    def __init__(self, tools, tool_name, tool_input, answer):
        self.tools = {t.name: t for t in tools}
        self.turns = [
            _message([BetaToolUseBlock(type="tool_use", id="toolu_1", name=tool_name, input=tool_input)], "tool_use"),
            _message([BetaTextBlock(type="text", text=answer)], "end_turn"),
        ]
        self._current = None
        self._cached = None

    def __iter__(self):
        for turn in self.turns:
            self._current = turn
            self._cached = None
            yield turn

    def generate_tool_call_response(self):
        if self._current.stop_reason != "tool_use":
            return None
        if self._cached is None:
            block = self._current.content[0]
            output = self.tools[block.name].call(block.input)
            self._cached = {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": block.id, "content": output}],
            }
        return self._cached


class FakeClient:
    def __init__(self, answer="**What could happen**: Kuttanad floods."):
        self.calls = []
        self.answer = answer
        outer = self

        class _Messages:
            def tool_runner(self, **kwargs):
                outer.calls.append(kwargs)
                return FakeRunner(
                    kwargs["tools"], "simulate_flood_scenario",
                    {"region": "Kerala", "rainfall_change_pct": 20}, outer.answer,
                )

        class _Beta:
            messages = _Messages()

        self.beta = _Beta()


@pytest.fixture
def fake_assistant(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(assistant_module, "_assistant", FloodAssistant(client=fake))
    return fake


# --- Tools (no LLM) -------------------------------------------------------------
def test_simulate_tool_returns_grounded_json_and_records_artifact():
    artifacts = begin_collection()
    out = json.loads(simulate_flood_scenario.call({"region": "Kerala", "rainfall_change_pct": 20}))
    assert out["headline"] and out["villages"] and out["similar_past_incidents"]
    assert out["rainfall"]["scenario"]["change_pct"] == 20
    assert artifacts.scenario is not None and artifacts.scenario.region == "Kerala"


def test_simulate_tool_reports_unknown_region_as_data_not_exception():
    begin_collection()
    out = json.loads(simulate_flood_scenario.call({"region": "Gotham"}))
    assert "error" in out and "Kerala" in out["monitored_regions"]


def test_village_and_incident_tools():
    begin_collection()
    village = json.loads(get_village_profile.call({"village_name": "velachery"}))
    assert village["village"]["district"] == "Chennai"
    assert any("2015" in i["date"] for i in village["past_incidents"])
    incidents = json.loads(search_past_incidents.call({"region": "Assam", "cause": "embankment_breach"}))
    assert incidents["count"] >= 1


def test_draft_alert_requires_a_simulation_first():
    begin_collection()
    assert "error" in json.loads(draft_alert_message.call({"district": "Alappuzha"}))
    simulate_flood_scenario.call({"region": "Kerala", "rainfall_change_pct": 40, "antecedent": "saturated"})
    draft = json.loads(draft_alert_message.call({"district": "Alappuzha"}))
    assert "Alappuzha" in draft["draft"] and "Not sent" in draft["note"]


def test_tool_schemas_are_valid_for_the_api():
    for tool in TOOLS:
        spec = tool.to_dict()
        assert spec["name"] and spec["description"] and spec["input_schema"]["type"] == "object"


# --- Chat loop ------------------------------------------------------------------
def test_chat_runs_tools_persists_history_and_returns_scenario(fake_assistant):
    first = client.post("/api/v1/chat", json={"message": "If rainfall increases by 20% in Kerala, which villages flood?"})
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["reply_markdown"].startswith("**What could happen**")
    assert body["scenario"]["region"] == "Kerala"
    assert body["tools_used"] == ["simulate_flood_scenario"]

    call = fake_assistant.calls[0]
    assert call["model"] == "claude-opus-5"
    assert call["thinking"] == {"type": "adaptive"}
    assert call["fallbacks"] == "default"

    second = client.post("/api/v1/chat", json={"message": "And with dams releasing?", "session_id": body["session_id"]})
    assert second.status_code == 200
    history = fake_assistant.calls[1]["messages"]
    # user, assistant(tool_use), user(tool_result), assistant(answer), new user
    assert [m["role"] for m in history] == ["user", "assistant", "user", "assistant", "user"]
    assert history[2]["content"][0]["type"] == "tool_result"

    transcript = client.get(f"/api/v1/chat/{body['session_id']}").json()
    assert transcript[0]["text"].startswith("If rainfall increases")
    assert len(transcript) == 4


def test_chat_without_api_key_returns_503(monkeypatch):
    import anthropic

    class NoKeyClient:
        class beta:
            class messages:
                @staticmethod
                def tool_runner(**_):
                    raise anthropic.AnthropicError("Could not resolve authentication method")

    monkeypatch.setattr(assistant_module, "_assistant", FloodAssistant(client=NoKeyClient()))
    response = client.post("/api/v1/chat", json={"message": "hello"})
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]


def test_chat_with_real_sdk_client_but_no_credentials_returns_503(monkeypatch):
    """The real SDK raises TypeError (not AnthropicError) when no credential resolves."""
    import anthropic

    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE"):
        monkeypatch.delenv(var, raising=False)
    no_creds = anthropic.Anthropic(api_key=None, auth_token=None)
    monkeypatch.setattr(assistant_module, "_assistant", FloodAssistant(client=no_creds))
    response = client.post("/api/v1/chat", json={"message": "Kerala +20%"})
    assert response.status_code == 503, response.text
    assert "ANTHROPIC_API_KEY" in response.json()["detail"]


# --- Offline mode (no API key) ----------------------------------------------------
@pytest.fixture
def offline_assistant(monkeypatch):
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(assistant_module.settings, "ANTHROPIC_API_KEY", None)
    monkeypatch.setattr(assistant_module.settings, "CHAT_PROVIDER", "auto")
    monkeypatch.setattr(assistant_module, "_assistant", FloodAssistant())


def test_offline_chat_answers_without_api_key(offline_assistant):
    first = client.post("/api/v1/chat", json={"message": "If rainfall increases by 20% in Kerala, which villages flood?"})
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["model"] == "varuna-offline-rules"
    assert body["scenario"]["region"] == "Kerala"
    assert body["scenario"]["scenario"]["rainfall_change_pct"] == 20
    assert "**What could happen**" in body["reply_markdown"]
    assert "Kuttanad" in body["reply_markdown"]

    follow = client.post("/api/v1/chat", json={"message": "and if the dams also release?", "session_id": body["session_id"]})
    scenario = follow.json()["scenario"]["scenario"]
    assert scenario["region"] == "Kerala" and scenario["rainfall_change_pct"] == 20 and scenario["dam_release"] is True

    alert = client.post("/api/v1/chat", json={"message": "Draft an alert for Alappuzha", "session_id": body["session_id"]})
    assert "Alappuzha" in alert.json()["alert_preview"]
    assert len(client.get(f"/api/v1/chat/{body['session_id']}").json()) == 6


@pytest.mark.parametrize("message, expected", [
    ("Chennai gets 2015-level rain during high tide", {"region": "Chennai", "rainfall_mm": 490, "high_tide": True}),
    ("500 mm in 2 days in Bombay with saturated soil",
     {"region": "Mumbai", "rainfall_mm": 500, "duration_days": 2, "antecedent": "saturated"}),
    ("30% less rain in Velachery", {"region": "Chennai", "rainfall_change_pct": -30, "district": "Chennai"}),
])
def test_offline_parser_maps_plain_language_to_scenario(offline_assistant, message, expected):
    scenario = client.post("/api/v1/chat", json={"message": message}).json()["scenario"]["scenario"]
    for key, value in expected.items():
        assert scenario[key] == value, (key, scenario)


def test_offline_non_scenario_questions(offline_assistant):
    assert client.post("/api/v1/chat", json={"message": "past floods in Assam"}).json()["incidents"]
    assert client.post("/api/v1/chat", json={"message": "tell me about Velachery"}).json()["villages"]
    unknown = client.post("/api/v1/chat", json={"message": "30% more rain in Pune"}).json()
    assert unknown["scenario"] is None and "Kerala" in unknown["reply_markdown"]


def test_offline_small_talk_does_not_rerun_previous_scenario(offline_assistant):
    sid = client.post("/api/v1/chat", json={"message": "Kerala +20% rainfall"}).json()["session_id"]
    for message in ("hi", "Hello!", "thanks", "ok", "blah blah", "help"):
        body = client.post("/api/v1/chat", json={"message": message, "session_id": sid}).json()
        assert body["scenario"] is None, message
        assert "What could happen" not in body["reply_markdown"], message
    # The scenario context survives the chatter.
    body = client.post("/api/v1/chat", json={"message": "and with dams releasing?", "session_id": sid}).json()
    assert body["scenario"]["scenario"]["region"] == "Kerala" and body["scenario"]["scenario"]["dam_release"] is True
