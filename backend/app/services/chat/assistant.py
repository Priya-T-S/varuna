"""
What-if flood assistant.

Claude is given the VARUNA simulation tools and a system prompt that makes it
ground every number in tool output. The SDK tool runner drives the loop; we
mirror each turn into the persisted history so follow-up questions ("and if
the dams also release?") keep their context.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

import anthropic
from sqlalchemy import select

from app.core.config import settings
from app.db.models import ChatMessage
from app.db.session import session_scope
from app.schemas.chat import ChatHistoryItem, ChatResponse
from app.services import geo_data
from app.services.chat.offline import OFFLINE_MODEL, OfflineAssistant
from app.services.chat.tools import TOOLS, begin_collection

logger = logging.getLogger(__name__)

MAX_HISTORY_MESSAGES = 40
MAX_TOOL_ITERATIONS = 8

SYSTEM_PROMPT = f"""You are VARUNA Flood Advisor, the what-if assistant of VARUNA AI, an explainable \
extreme-rainfall early-warning system for Indian disaster-management officials (district collectors, SDMA staff).

Users describe a rainfall situation in plain language, for example "If rainfall increases by 20% in Kerala, which \
villages flood?" or "Chennai gets 2015-level rain during high tide". Your job is to turn that into a simulation, \
then explain the result so an official can act on it.

How to work:
- Map the description to simulate_flood_scenario parameters. Examples: "+20%" is rainfall_change_pct=20, \
"500 mm in two days" is rainfall_mm=500 with duration_days=2, and "rivers already full" or "after weeks of rain" is \
antecedent="saturated". Mentions of dam shutters or reservoir releases mean dam_release=true; a high or spring tide \
means high_tide=true. If a detail is missing, choose a sensible default, state it, and still run the simulation.
- For follow-ups, re-run the simulation with the changed parameters instead of guessing.
- Every number you give (probabilities, depths, rainfall, deaths, populations) must come from tool results. \
Never invent villages, incidents or statistics. If something is outside the data, say so.
- Monitored regions: {", ".join(geo_data.region_names())}. For anywhere else, explain that it is not modelled yet and \
offer the nearest monitored region.

Answer format (Markdown, concise, suited to a busy official):
1. **What could happen**: one headline sentence, then the villages at high or severe risk. For each, give the band \
change, probability and indicative depth, and flag landslide risk where the tool reports it.
2. **Why: driving factors**: the main physical reasons (runoff, low-lying terrain, drainage, dam, tide) and what the \
AI rainfall model's SHAP drivers show. If the AI rain probability moved against the rainfall change, explain that \
caveat briefly.
3. **Past incidents like this**: the one to three most similar documented events, with year, impact and why they are \
similar.
4. **Suggested actions**: two to four short, concrete preparedness steps that fit the risk level.
End with one line of key assumptions or caveats. Offer to draft the collector alert when the risk is high or severe.

Reply in the user's language. If they write in Hindi, Malayalam, Tamil, Assamese or Hinglish, answer in the same \
language and keep village names in their usual spelling. Be calm and factual; do not dramatise."""


class AssistantUnavailableError(RuntimeError):
    """Raised when the Claude API cannot be used (no key, auth, network)."""

    def __init__(self, message: str, status_code: int = 503) -> None:
        super().__init__(message)
        self.status_code = status_code


def _to_jsonable(value: Any) -> Any:
    """Content blocks as plain JSON (kept verbatim so thinking blocks replay intact)."""
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_none=True)
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    return value


def _is_user_text(message: dict[str, Any]) -> bool:
    content = message["content"]
    if isinstance(content, str):
        return True
    return not any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content)


class FloodAssistant:
    def __init__(self, client: anthropic.Anthropic | None = None) -> None:
        self._client = client

    @property
    def client(self) -> anthropic.Anthropic:
        if self._client is None:
            try:
                self._client = (
                    anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
                    if settings.ANTHROPIC_API_KEY else anthropic.Anthropic()
                )
            except anthropic.AnthropicError as exc:
                raise AssistantUnavailableError(
                    "The what-if assistant is not configured. Set ANTHROPIC_API_KEY in backend/.env "
                    "(the structured simulator at POST /api/v1/scenarios/simulate works without it)."
                ) from exc
        return self._client

    # ------------------------------------------------------------------
    def history(self, session_id: str) -> list[dict[str, Any]]:
        with session_scope() as db:
            rows = db.scalars(
                select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.id)
            ).all()
            messages = [{"role": r.role, "content": r.content} for r in rows]
        if len(messages) > MAX_HISTORY_MESSAGES:
            messages = messages[-MAX_HISTORY_MESSAGES:]
            # Start on a plain user turn so no tool_result is orphaned from its tool_use.
            while messages and not (messages[0]["role"] == "user" and _is_user_text(messages[0])):
                messages.pop(0)
        return messages

    def transcript(self, session_id: str) -> list[ChatHistoryItem]:
        items = []
        for m in self.history(session_id):
            blocks = m["content"] if isinstance(m["content"], list) else [{"type": "text", "text": m["content"]}]
            text = "\n".join(b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text")
            if text.strip():
                items.append(ChatHistoryItem(role=m["role"], text=text))
        return items

    def _use_offline(self) -> bool:
        provider = settings.CHAT_PROVIDER.strip().lower()
        if provider == "offline":
            return True
        if provider == "claude" or self._client is not None:
            return False
        has_credentials = settings.ANTHROPIC_API_KEY or any(
            os.environ.get(var) for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
        )
        return not has_credentials

    def _offline_chat(self, message: str, session_id: str) -> ChatResponse:
        history = self.history(session_id)
        previous = [
            "\n".join(b.get("text", "") for b in (m["content"] if isinstance(m["content"], list) else
                                                  [{"type": "text", "text": m["content"]}])
                      if isinstance(b, dict) and b.get("type") == "text")
            for m in history if m["role"] == "user" and _is_user_text(m)
        ]
        artifacts = begin_collection()
        reply = OfflineAssistant().answer(message, previous, artifacts)
        # Stored as plain text blocks, so the history stays valid if a Claude key is added later.
        with session_scope() as db:
            db.add_all([
                ChatMessage(session_id=session_id, role="user", content=[{"type": "text", "text": message}]),
                ChatMessage(session_id=session_id, role="assistant", content=[{"type": "text", "text": reply}]),
            ])
        return ChatResponse(
            session_id=session_id,
            reply_markdown=reply,
            scenario=artifacts.scenario,
            incidents=artifacts.incidents,
            villages=artifacts.villages,
            alert_preview=artifacts.alert_preview,
            tools_used=artifacts.tools_used,
            model=OFFLINE_MODEL,
        )

    # ------------------------------------------------------------------
    def chat(self, message: str, session_id: str | None = None) -> ChatResponse:
        session_id = session_id or uuid.uuid4().hex
        if self._use_offline():
            return self._offline_chat(message, session_id)
        history = self.history(session_id)
        new_messages: list[dict[str, Any]] = [{"role": "user", "content": [{"type": "text", "text": message}]}]
        messages = history + new_messages
        artifacts = begin_collection()

        try:
            runner = self.client.beta.messages.tool_runner(
                model=settings.CHAT_MODEL,
                max_tokens=16000,
                thinking={"type": "adaptive"},
                output_config={"effort": settings.CHAT_EFFORT},
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=list(messages),
                max_iterations=MAX_TOOL_ITERATIONS,
                # Server-side refusal fallback: a policy decline is retried on
                # Anthropic's recommended fallback model inside the same call.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
            final = None
            for turn in runner:
                final = turn
                new_messages.append({"role": "assistant", "content": _to_jsonable(turn.content)})
                tool_response = runner.generate_tool_call_response()
                if tool_response is not None:
                    new_messages.append(_to_jsonable(tool_response))
        except anthropic.AuthenticationError as exc:
            raise AssistantUnavailableError("Claude API key was rejected. Check ANTHROPIC_API_KEY.") from exc
        except anthropic.PermissionDeniedError as exc:
            raise AssistantUnavailableError(f"Claude API permission denied: {exc.message}") from exc
        except anthropic.RateLimitError as exc:
            raise AssistantUnavailableError("The assistant is rate-limited. Please retry in a minute.", 429) from exc
        except anthropic.APIStatusError as exc:
            logger.exception("Claude API error")
            raise AssistantUnavailableError(f"Claude API error ({exc.status_code}). Please retry.", 502) from exc
        except anthropic.APIConnectionError as exc:
            raise AssistantUnavailableError("Could not reach the Claude API. Check network access.") from exc
        except anthropic.AnthropicError as exc:
            raise AssistantUnavailableError(f"The what-if assistant is not configured: {exc}") from exc
        except TypeError as exc:
            # The SDK raises TypeError at request time when no credential is found.
            if "authentication" not in str(exc).lower():
                raise
            raise AssistantUnavailableError(
                "The what-if assistant is not configured. Set ANTHROPIC_API_KEY in backend/.env "
                "(the scenario controls work without it)."
            ) from exc

        reply = self._reply_text(final)
        # Persist only complete turns, so a failed call never leaves a dangling tool_use.
        with session_scope() as db:
            db.add_all(
                ChatMessage(session_id=session_id, role=m["role"], content=m["content"]) for m in new_messages
            )

        return ChatResponse(
            session_id=session_id,
            reply_markdown=reply,
            scenario=artifacts.scenario,
            incidents=artifacts.incidents,
            villages=artifacts.villages,
            alert_preview=artifacts.alert_preview,
            tools_used=artifacts.tools_used,
            model=getattr(final, "model", settings.CHAT_MODEL) if final else settings.CHAT_MODEL,
        )

    @staticmethod
    def _reply_text(final: Any) -> str:
        if final is None:
            return "I could not produce an answer. Please try rephrasing the scenario."
        if final.stop_reason == "refusal":
            return "I can't help with that request. I can simulate rainfall and flood scenarios for the monitored regions."
        text = "\n\n".join(b.text for b in final.content if getattr(b, "type", None) == "text").strip()
        if final.stop_reason == "max_tokens":
            text += "\n\n_(Answer truncated. Ask me to continue.)_"
        if final.stop_reason == "tool_use":
            text = text or "The analysis needed more steps than allowed. Please narrow the question."
        return text or "Done. See the simulation panel for details."


_assistant: FloodAssistant | None = None


def get_assistant() -> FloodAssistant:
    global _assistant
    if _assistant is None:
        _assistant = FloodAssistant()
    return _assistant
