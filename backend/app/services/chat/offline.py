"""
Offline what-if assistant (no API key, no LLM, free).

Parses the question with simple rules, runs the same VARUNA tools the Claude
assistant uses (simulator, SHAP drivers, village profiles, incident catalogue)
and writes the answer from templates. Every number comes from those tools.

Follow-ups work: the scenario is rebuilt from all user turns in the session,
so "and if the dams also release?" keeps the earlier region and rainfall.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.services import geo_data, incident_service
from app.services.chat.tools import (
    ToolArtifacts,
    draft_alert_message,
    get_village_profile,
    list_monitored_places,
    search_past_incidents,
    simulate_flood_scenario,
)

OFFLINE_MODEL = "varuna-offline-rules"

# Common alternative names -> (region, district or None)
ALIASES: dict[str, tuple[str, str | None]] = {
    "bombay": ("Mumbai", None),
    "madras": ("Chennai", None),
    "guwahati": ("Assam", "Kamrup Metropolitan"),
    "kochi": ("Kerala", "Ernakulam"),
    "cochin": ("Kerala", "Ernakulam"),
    "trivandrum": ("Kerala", "Thiruvananthapuram"),
    "calicut": ("Kerala", "Kozhikode"),
    "tamil nadu": ("Chennai", None),
    "maharashtra": ("Mumbai", None),
}

NUMBER_WORDS = {"one": 1, "a": 1, "an": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


@dataclass
class ScenarioState:
    region: str | None = None
    district: str | None = None
    village: str | None = None
    rainfall_change_pct: float | None = None
    rainfall_mm: float | None = None
    duration_days: int | None = None
    antecedent: str | None = None
    dam_release: bool | None = None
    high_tide: bool | None = None
    notes: list[str] = field(default_factory=list)

    def tool_args(self) -> dict[str, Any]:
        args: dict[str, Any] = {"region": self.region}
        if self.rainfall_mm is not None:
            args["rainfall_mm"] = self.rainfall_mm
        else:
            args["rainfall_change_pct"] = self.rainfall_change_pct or 0.0
        args["duration_days"] = self.duration_days or 3
        args["antecedent"] = self.antecedent or "normal"
        args["dam_release"] = bool(self.dam_release)
        args["high_tide"] = bool(self.high_tide)
        if self.district:
            args["district"] = self.district
        return args


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def _has(text: str, *patterns: str) -> bool:
    return any(re.search(p, text) for p in patterns)


def _find_place(text: str) -> tuple[str | None, str | None, str | None]:
    """(region, district, village) mentioned in the text, most specific wins."""
    # Villages first (longest names first so "Kuttanad (Kainakary)" beats "Kuttanad").
    for v in sorted(geo_data.villages(), key=lambda v: -len(v["name"])):
        full = v["name"].lower()
        short = full.split(" (")[0]
        inner = full[full.find("(") + 1:full.find(")")] if "(" in full else None
        for key in filter(None, (full, short, inner)):
            if len(key) >= 4 and re.search(rf"\b{re.escape(key)}\b", text):
                # Region names that are also village/district names ("Chennai", "Majuli")
                # should resolve to the region unless the user clearly means the place.
                if key in (r["name"].lower() for r in geo_data.regions()):
                    break
                return v["region"], v["district"], v["name"]
    for region in geo_data.regions():
        for d in region["districts"]:
            name = d["name"].lower()
            if name != region["name"].lower() and re.search(rf"\b{re.escape(name)}\b", text):
                return region["name"], d["name"], None
    for alias, (region, district) in ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", text):
            return region, district, None
    for region in geo_data.regions():
        if re.search(rf"\b{re.escape(region['name'].lower())}\b", text) or \
                re.search(rf"\b{re.escape(region['state'].lower())}\b", text):
            return region["name"], None, None
    return None, None, None


def _parse_into(state: ScenarioState, message: str) -> dict[str, bool]:
    """Apply one user message onto the running scenario. Returns detected intents."""
    text = message.lower()
    region, district, village = _find_place(text)
    if region:
        # Naming a place resets the focus: a bare region means the whole region.
        state.region, state.district, state.village = region, district, village

    rain_given = False
    # "2015-level rain", "like 2005", "same as 2018"
    year = re.search(r"\b(19[5-9]\d|20[0-4]\d)\b", text)
    if year and state.region and _has(text, r"level", r"like", r"same as", r"repeat", r"as in", r"similar"):
        matches = [i for i in geo_data.incidents()
                   if i["region"] == state.region and i["date"].startswith(year.group(1))]
        if matches:
            inc = max(matches, key=lambda i: i["rainfall_mm"])
            state.rainfall_mm = min(float(inc["rainfall_mm"]), 2000.0)
            state.duration_days = max(1, min(int(inc["rainfall_window_days"]), 10))
            state.rainfall_change_pct = None
            state.notes.append(
                f"Used the rainfall of {incident_service.incident_label(inc['name'], inc['date'])}: "
                f"{inc['rainfall_mm']:.0f} mm over {inc['rainfall_window_days']} day(s)."
            )
            rain_given = True

    mm = re.search(r"(\d+(?:\.\d+)?)\s*(?:mm|millimet)", text)
    if mm and not rain_given:
        state.rainfall_mm = max(1.0, min(float(mm.group(1)), 2000.0))
        state.rainfall_change_pct = None
        rain_given = True

    pct = re.search(r"([+-]?\d+(?:\.\d+)?)\s*(?:%|percent|per cent)", text)
    if pct and not rain_given:
        value = float(pct.group(1))
        if value > 0 and _has(text, r"\bless\b", r"decreas", r"\bdrop", r"reduc", r"\blower\b", r"\bfall", r"\bdown\b", r"\bfewer\b"):
            value = -value
        state.rainfall_change_pct = max(-90.0, min(value, 500.0))
        state.rainfall_mm = None
        rain_given = True
    elif not rain_given:
        for words, value in ((r"\bdoubl", 100.0), (r"\btripl", 200.0), (r"\bhalf\b|\bhalve", -50.0)):
            if _has(text, words):
                state.rainfall_change_pct, state.rainfall_mm = value, None
                rain_given = True
                break

    days = re.search(r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|a|an)\s*-?\s*(day|days|week|weeks|hours|hrs|hour)\b", text)
    if days:
        n = days.group(1)
        n = NUMBER_WORDS.get(n, None) if not n.isdigit() else int(n)
        unit = days.group(2)
        if n:
            if unit.startswith("week"):
                n *= 7
            elif unit.startswith("h"):
                n = max(1, -(-n // 24))
            state.duration_days = max(1, min(n, 10))
    elif _has(text, r"\bin a day\b", r"\bsingle day\b", r"\bovernight\b", r"\bcloudburst\b"):
        state.duration_days = 1

    if _has(text, r"saturat", r"already full", r"weeks of rain", r"waterlog", r"wet soil", r"soaked", r"after .*rain"):
        state.antecedent = "saturated"
    elif _has(text, r"\bdry\b", r"drought", r"parched"):
        state.antecedent = "dry"
    elif _has(text, r"normal soil", r"normal condition"):
        state.antecedent = "normal"

    if _has(text, r"(no|without|not?)\s+(\w+\s+){0,2}(dam|reservoir|shutter)"):
        state.dam_release = False
    elif _has(text, r"\bdams?\b", r"reservoir", r"shutter", r"spillway"):
        state.dam_release = True

    if _has(text, r"(no|without|low)\s+(\w+\s+){0,2}tide"):
        state.high_tide = False
    elif _has(text, r"\btide", r"\btidal"):
        state.high_tide = True

    scenario_words = rain_given or _has(text, r"\brain", r"flood", r"what if", r"\bif\b", r"simulat",
                                        r"\bdam", r"tide", r"saturat", r"\bdry\b", r"drought")
    short = len(re.findall(r"\w+", text)) <= 6
    return {
        "place": bool(region),
        "greeting": short and not rain_given and _has(
            text, r"^\W*(hi+|hel+o+|hey+|hiya|namaste|namaskar|vanakkam|good (morning|afternoon|evening))\b"),
        "thanks": short and not rain_given and _has(
            text, r"\b(thanks|thank you|thx|ty|great|nice|cool|ok(ay)?|bye|goodbye)\b"),
        "rain_given": rain_given,
        "scenario": scenario_words,
        "list": _has(text, r"which (regions|places|areas|villages) .*(monitor|cover|support)",
                     r"(list|show) .*(regions|places|villages|districts)", r"what .*(regions|places) .*(cover|monitor)"),
        "history": _has(text, r"past (flood|incident|event|disaster)", r"flood history", r"historical",
                        r"previous (flood|incident)", r"has .* flooded before", r"incidents?\b"),
        "alert": _has(text, r"\balert\b", r"\bdraft\b", r"\bmessage\b", r"\bsms\b", r"whatsapp"),
        "profile": bool(village) and _has(text, r"profile", r"tell me about", r"about\b", r"terrain",
                                          r"elevation", r"why is .* (vulnerable|prone)"),
        "help": _has(text, r"^\W*help\b", r"what can you do", r"how do i use", r"who are you",
                     r"what (do|can) i ask", r"how does this work"),
    }


# ---------------------------------------------------------------------------
# Answer writing
# ---------------------------------------------------------------------------
def _fmt_int(n: int | None) -> str:
    return "not recorded" if n is None else f"{n:,}"


def _help_text() -> str:
    regions = ", ".join(geo_data.region_names())
    return (
        "I'm the VARUNA flood advisor, running in **offline mode**: I use VARUNA's own models, "
        "no external AI.\n\n"
        f"I cover these regions: **{regions}**. Try asking:\n"
        "- *If rainfall increases by 20% in Kerala, which villages flood?*\n"
        "- *Chennai gets 2015-level rain during high tide*\n"
        "- *500 mm in 2 days in Mumbai with saturated soil*\n"
        "- *And if the dams also release?* (follow-up)\n"
        "- *Past floods in Assam*, *Tell me about Velachery*, *Draft an alert for Alappuzha*"
    )


def _scenario_answer(result, state: ScenarioState) -> str:
    s = result.summary
    sr = result.scenario_rain
    lines = [f"**What could happen**: {s.headline}", ""]

    at_risk = [v for v in result.villages if v.band in ("high", "severe")]
    shown = at_risk[:8] or result.villages[:5]
    if not at_risk:
        lines.append("No village reaches high or severe risk. These are the most exposed:")
    for v in shown:
        change = f"{v.baseline_band} → **{v.band}**" if v.band != v.baseline_band else f"**{v.band}**"
        extra = " ⚠️ landslide risk" if v.landslide_risk else ""
        lines.append(
            f"- **{v.name}** ({v.district}): {change}, flood probability "
            f"{v.baseline_probability:.0%} → {v.flood_probability:.0%}, about {v.expected_depth_m} m deep, "
            f"population {v.population:,}{extra}"
        )
    if len(at_risk) > len(shown):
        lines.append(f"- …and {len(at_risk) - len(shown)} more at high or severe risk (see the map).")
    lines.append(
        f"\nPeople at risk: **{s.population_at_risk:,}** in {s.villages_high_or_severe} of "
        f"{s.villages_assessed} villages. Districts: {', '.join(s.districts_at_risk) or 'none'}."
    )

    lines += ["", "**Why: driving factors**"]
    worst = result.villages[0] if result.villages else None
    if worst:
        for r in worst.reasons[:3]:
            lines.append(f"- {worst.name}: {r}")
    if result.baseline_model and result.scenario_model:
        b, sc = result.baseline_model.probability, result.scenario_model.probability
        lines.append(
            f"- AI rainfall model: probability of heavy rain in the next 24 h is {b:.0%} → {sc:.0%} "
            f"({result.scenario_model.risk_level}, {result.scenario_model.confidence_label.lower()} confidence)."
        )
        drivers = [d for d in result.driver_changes[:3] if abs(d.delta) > 1e-3]
        if drivers:
            lines.append("- Top SHAP drivers that changed: " + "; ".join(
                f"{d.label} ({'+' if d.delta >= 0 else ''}{d.delta:.2f})" for d in drivers) + ".")
        if (sr.change_pct > 0 and sc < b) or (sr.change_pct < 0 and sc > b):
            lines.append("- Note: the AI rain probability moved against the rainfall change. It scores "
                         "atmospheric conditions for the next 24 h, not the rain total you gave.")

    lines += ["", "**Past incidents like this**"]
    if result.similar_incidents:
        for inc in result.similar_incidents[:3]:
            why = "; ".join(inc.why_similar[:2])
            lines.append(
                f"- **{incident_service.incident_label(inc.name, inc.date)}**: {inc.rainfall_mm:.0f} mm over "
                f"{inc.rainfall_window_days} day(s), deaths {_fmt_int(inc.deaths)}, displaced "
                f"{_fmt_int(inc.displaced)}. {why}"
            )
    else:
        lines.append("- No close match in the incident catalogue.")

    lines += ["", "**Suggested actions**"]
    if result.actions:
        for a in result.actions[:4]:
            lines.append(f"- {a.text} _(owner: {a.owner})_")
    else:
        lines.append("- Keep monitoring IMD bulletins and river gauges.")

    assumptions = [
        f"{sr.event_total_mm:.0f} mm over {sr.duration_days} day(s) ({sr.change_pct:+.0f}% vs reference spell)",
        f"soil {result.scenario.antecedent}",
        "dams releasing" if result.scenario.dam_release else "no dam release",
        "high tide" if result.scenario.high_tide else "normal tide",
    ]
    lines.append("")
    for note in state.notes[-1:]:
        lines.append(f"_{note}_")
    lines.append("_Assumptions: " + ", ".join(assumptions) + ". Depths are indicative, not gauge readings._")
    if any(v.band in ("high", "severe") for v in result.villages) and result.villages:
        lines.append(f"\nI can draft the collector alert: ask *\"Draft an alert for {result.villages[0].district}\"*.")
    return "\n".join(lines)


class OfflineAssistant:
    """Rule-based answerer. `chat` returns (reply_markdown, artifacts)."""

    def answer(self, message: str, previous_user_messages: list[str], artifacts: ToolArtifacts) -> str:
        state = ScenarioState()
        for old in previous_user_messages:
            _parse_into(state, old)
        state.notes.clear()
        had_region = state.region
        intent = _parse_into(state, message)

        # Small talk never re-runs the previous scenario.
        if intent["greeting"] or (intent["help"] and not intent["place"]):
            return _help_text()
        if intent["thanks"] and not intent["place"]:
            return ("You're welcome. Ask another what-if whenever you like, for example "
                    "*\"and with saturated soil?\"* or *\"Mumbai 500 mm in 2 days\"*.")
        if intent["list"]:
            list_monitored_places.call({})
            lines = ["**Monitored places**"]
            for r in geo_data.regions():
                spell = r["heavy_spell"]
                lines.append(f"- **{r['name']}** ({r['state']}): {len(geo_data.villages_in(r['name']))} villages "
                             f"in {len(r['districts'])} districts; reference heavy spell {spell['rain_1d']} mm/day, "
                             f"{spell['rain_3d']} mm over 3 days")
            return "\n".join(lines)

        if intent["profile"] and state.village and not intent["rain_given"]:
            get_village_profile.call({"village_name": state.village})
            v = artifacts.villages[-1]
            hist = incident_service.search(village=v["name"], limit=5)
            lines = [
                f"**{v['name']}** ({v['district']}, {v['state']})",
                f"- Elevation {v['elevation_m']} m; {v['hand_m']} m above the nearest drainage; slope {v['slope_pct']}%",
                f"- {v['dist_to_river_km']} km from {v.get('river_name') or 'the nearest river'}; "
                f"drainage {v['drainage_class']}; soil {v['soil_type']}; {v['urban_fraction']:.0%} urban",
                f"- Population {v['population']:,}; floods on record: {v['flood_history_count']}",
            ]
            if v.get("downstream_of_dam"):
                lines.append(f"- Downstream of {v['downstream_of_dam']} dam")
            if v.get("coastal"):
                lines.append("- Coastal: high tides slow drainage")
            if hist:
                lines += ["", "**Past floods here**"] + [
                    f"- {incident_service.incident_label(i['name'], i['date'])}: {i['rainfall_mm']:.0f} mm, "
                    f"deaths {_fmt_int(i['deaths'])}. {i['summary']}" for i in hist
                ]
            return "\n".join(lines)

        if intent["alert"]:
            if not state.region:
                return "Which district should the alert be for? For example: *Draft an alert for Alappuzha*."
            simulate_flood_scenario.call(state.tool_args())
            district = state.district or (artifacts.scenario.villages[0].district if artifacts.scenario and artifacts.scenario.villages else "")
            draft_alert_message.call({"district": district})
            if artifacts.alert_preview:
                return ("Here's the draft alert for the current scenario (**not sent**; send it from the Alerts page):\n\n"
                        f"```\n{artifacts.alert_preview}\n```")
            return f"No simulated villages in {district}, so I couldn't draft an alert."

        if intent["history"] and not re.search(r"\d+\s*(%|mm)", message.lower()):
            args = {"region": state.region} if state.region else {}
            if state.village:
                args["village"] = state.village
            search_past_incidents.call(args)
            incs = artifacts.incidents
            if not incs:
                return "No documented incidents match that."
            where = state.village or state.region or "all monitored regions"
            lines = [f"**Documented floods: {where}**"]
            for i in incs:
                lines.append(f"- **{incident_service.incident_label(i['name'], i['date'])}**: {i['rainfall_mm']:.0f} mm over "
                             f"{i['rainfall_window_days']} day(s), deaths {_fmt_int(i['deaths'])}, displaced "
                             f"{_fmt_int(i['displaced'])}. {i['summary']}")
            return "\n".join(lines)

        if not (intent["scenario"] or intent["place"]):
            current = ""
            if state.region:
                current = (f"\n\nThe current scenario is **{state.region}**. To change it, say e.g. "
                           "*\"and with dams releasing?\"*, *\"make it 40% more\"* or *\"3 days of rain\"*.")
            return ("Sorry, I didn't understand that. I answer rainfall and flood what-if questions, e.g. "
                    "*\"If rainfall increases by 20% in Kerala, which villages flood?\"*. "
                    "Type **help** to see everything I can do." + current)

        if not state.region:
            if intent["scenario"]:
                return ("Which region should I simulate? I cover **" + ", ".join(geo_data.region_names())
                        + "** (you can also name a district or village, e.g. *Alappuzha* or *Velachery*).")
            return _help_text()

        if not had_region and state.rainfall_mm is None and state.rainfall_change_pct is None:
            state.notes.append("No rainfall amount given, so I used the region's reference heavy-rain spell (+0%).")
        simulate_flood_scenario.call(state.tool_args())
        if artifacts.scenario is None:
            return "I couldn't run that scenario. Try e.g. *Kerala +20% rainfall*."
        return _scenario_answer(artifacts.scenario, state)
