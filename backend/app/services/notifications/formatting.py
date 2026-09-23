"""Per-channel message rendering (SMS is short, e-mail is a full report)."""

from __future__ import annotations

from html import escape

from app.services.notifications.base import AlertPayload, RecipientTarget

LEVEL_ICON = {"severe": "\U0001F534", "high": "\U0001F7E0", "moderate": "\U0001F7E1", "low": "\U0001F7E2"}
LEVEL_COLOR = {"severe": "#b91c1c", "high": "#c2410c", "moderate": "#a16207", "low": "#15803d"}


def _is_public(url: str | None) -> bool:
    return bool(url) and not any(h in url for h in ("localhost", "127.0.0.1", "0.0.0.0"))


def _villages_line(alert: AlertPayload, limit: int = 4) -> str:
    return ", ".join(
        f"{v['name']} ({v['band']}, {v['probability']:.0%})" for v in alert.villages[:limit]
    )


def _why_lines(alert: AlertPayload, limit: int = 5) -> list[str]:
    """Compact reasons; falls back to the long driver sentences for older alerts."""
    if alert.why:
        return [w["text"] for w in alert.why[:limit]]
    return list(alert.drivers[:3])


def _peak_text(alert: AlertPayload) -> str | None:
    peak = alert.peak
    if not peak:
        return None
    when = "now" if peak["offset_h"] == 0 else f"around +{peak['offset_h']} h"
    return f"Peak risk {when} ({peak['band']}, {peak['probability']:.0%})"


def _timeline_text(alert: AlertPayload) -> str | None:
    if not alert.timeline:
        return None
    def when(p: dict) -> str:
        if p["offset_h"] == 0:
            return "Now"
        return f"+{p['offset_h']}h" + (" (end of rain)" if p.get("beyond_window") else "")

    return " → ".join(f"{when(p)} {p['band'].capitalize()}" for p in alert.timeline)


def sms_text(alert: AlertPayload, recipient: RecipientTarget) -> str:
    """Plain text, kept under ~3 SMS segments."""
    peak = alert.peak
    text = (
        f"VARUNA AI FLOOD ALERT [{alert.level.upper()}] {alert.district}, {alert.region}. "
        f"{alert.rain_event_mm:.0f}mm/{alert.rain_duration_days}d expected. "
        f"At risk: {_villages_line(alert, 3)}. "
        + (f"Peak +{peak['offset_h']}h. " if peak and peak["offset_h"] else "")
        + (f"Action: {alert.actions[0]['text']}. " if alert.actions else "")
        + f"Valid till {alert.valid_until:%d %b %H:%M} UTC."
    )
    if recipient.ack_url and _is_public(recipient.ack_url):
        text += f" Ack: {recipient.ack_url}"
    return text[:450]


def whatsapp_text(alert: AlertPayload, recipient: RecipientTarget) -> str:
    icon = LEVEL_ICON.get(alert.level, "")
    lines = [
        f"{icon} *VARUNA AI - {alert.level.upper()} FLOOD ALERT*",
        f"*District:* {alert.district} ({alert.region})",
        f"*Rain:* {alert.rain_event_mm:.0f} mm over {alert.rain_duration_days} day(s)",
        f"*Flood probability:* up to {alert.flood_probability:.0%}"
        + (f" · model confidence {alert.confidence_label}" if alert.confidence_label else ""),
    ]
    if _timeline_text(alert):
        lines.append(f"*Outlook:* {_timeline_text(alert)}")
    lines += [
        "",
        "*Villages at risk*",
        *[f"- {v['name']}: {v['band']} ({v['probability']:.0%}, ~{v['depth_m']} m)" for v in alert.villages[:5]],
        "",
        f"*Why {alert.level} risk?*",
        *[f"- {line}" for line in _why_lines(alert)],
    ]
    if alert.actions:
        lines += ["", "*Suggested actions (decision support)*", *[f"{i}. {a['text']}" for i, a in enumerate(alert.actions[:4], 1)]]
    lines += ["", f"Valid until {alert.valid_until:%d %b %Y %H:%M} UTC"]
    if recipient.ack_url:
        lines.append(f"Acknowledge: {recipient.ack_url}")
    return "\n".join(lines)


def telegram_html(alert: AlertPayload, recipient: RecipientTarget) -> str:
    icon = LEVEL_ICON.get(alert.level, "")
    e = escape
    parts = [
        f"{icon} <b>VARUNA AI · {e(alert.level.upper())} FLOOD ALERT</b>",
        f"<b>{e(alert.district)}</b>, {e(alert.region)}",
        "",
        f"🌧 <b>{alert.rain_event_mm:.0f} mm</b> over {alert.rain_duration_days} day(s)"
        + (f" · AI heavy-rain probability {alert.rain_probability:.0%}" if alert.rain_probability is not None else ""),
        f"🌊 Flood probability up to <b>{alert.flood_probability:.0%}</b>"
        + (f" · confidence {e(alert.confidence_label)}" if alert.confidence_label else ""),
    ]
    if _timeline_text(alert):
        parts.append(f"📈 {e(_timeline_text(alert))}")
    parts += [
        "",
        "<b>Villages at risk</b>",
        *[
            f"• {e(v['name'])}: <b>{e(v['band'])}</b> {v['probability']:.0%} (~{v['depth_m']} m)"
            for v in alert.villages[:6]
        ],
        "",
        f"<b>Why {e(alert.level)} risk?</b>",
        *[f"• {e(line)}" for line in _why_lines(alert)],
    ]
    if alert.actions:
        parts += ["", "<b>Suggested actions</b> <i>(decision support)</i>",
                  *[f"{i}. {e(a['text'])}" for i, a in enumerate(alert.actions[:4], 1)]]
    parts += ["", f"<i>Valid until {alert.valid_until:%d %b %Y %H:%M} UTC · alert #{alert.id}</i>"]
    if recipient.ack_url and not _is_public(recipient.ack_url):
        parts.append(f"Acknowledge: {e(recipient.ack_url)}")
    return "\n".join(parts)


def telegram_buttons(alert: AlertPayload, recipient: RecipientTarget) -> dict | None:
    """Inline buttons; Telegram rejects non-public URLs, so only add public ones."""
    row = []
    if recipient.ack_url and _is_public(recipient.ack_url):
        row.append({"text": "✅ Acknowledge", "url": recipient.ack_url})
    if _is_public(alert.dashboard_url):
        row.append({"text": "🗺 Open dashboard", "url": alert.dashboard_url})
    return {"inline_keyboard": [row]} if row else None


def email_subject(alert: AlertPayload) -> str:
    return f"[VARUNA AI] {alert.level.upper()} flood alert: {alert.district}, {alert.region}"


def email_html(alert: AlertPayload, recipient: RecipientTarget) -> str:
    e = escape
    color = LEVEL_COLOR.get(alert.level, "#334155")
    rows = "".join(
        f"<tr><td style='padding:6px 10px;border-bottom:1px solid #e2e8f0'>{e(v['name'])}</td>"
        f"<td style='padding:6px 10px;border-bottom:1px solid #e2e8f0;text-transform:capitalize'>{e(v['band'])}</td>"
        f"<td style='padding:6px 10px;border-bottom:1px solid #e2e8f0;text-align:right'>{v['probability']:.0%}</td>"
        f"<td style='padding:6px 10px;border-bottom:1px solid #e2e8f0;text-align:right'>{v['depth_m']} m</td>"
        f"<td style='padding:6px 10px;border-bottom:1px solid #e2e8f0;font-size:12px;color:#475569'>"
        f"{e('; '.join(v.get('reasons', [])[:2]))}</td></tr>"
        for v in alert.villages[:10]
    )
    drivers = "".join(f"<li>{e(d)}</li>" for d in _why_lines(alert, 6))
    band_bg = {"low": "#dcfce7", "moderate": "#fef3c7", "high": "#ffedd5", "severe": "#fee2e2"}
    timeline = "".join(
        f"<td style='padding:8px;text-align:center;background:{band_bg.get(p['band'], '#f1f5f9')};border:2px solid #fff'>"
        f"<div style='font-size:11px;color:#475569'>{'Now' if p['offset_h'] == 0 else '+' + str(p['offset_h']) + ' h'}</div>"
        f"<div style='font-weight:700;text-transform:capitalize'>{e(p['band'])}</div>"
        f"<div style='font-size:12px'>{p['probability']:.0%}</div></td>"
        for p in alert.timeline
    )
    timeline_html = (
        f"<h3 style='margin:20px 0 6px'>Risk outlook (next 48 h)</h3><table style='width:100%;border-collapse:collapse'><tr>{timeline}</tr></table>"
        "<p style='font-size:11px;color:#64748b;margin:4px 0 0'>Hydrological projection from the rainfall scenario; the AI rain probability covers the next 24 h.</p>"
        if timeline else ""
    )
    actions_html = (
        "<h3 style='margin:20px 0 6px'>Suggested actions <span style='font-weight:400;font-size:13px;color:#64748b'>(decision support, not automatic commands)</span></h3><ol style='margin:0;padding-left:20px'>"
        + "".join(f"<li>{e(a['text'])} <span style='color:#64748b;font-size:12px'>({e(a['priority'])} · {e(a['owner'])})</span></li>" for a in alert.actions[:6])
        + "</ol>"
        if alert.actions else ""
    )
    incident = ""
    if alert.similar_incident:
        inc = alert.similar_incident
        incident = (
            f"<h3 style='margin:20px 0 6px'>Similar past incident</h3>"
            f"<p style='margin:0'><b>{e(inc['name'])}</b> ({e(inc['date'])}): {e(inc.get('summary', ''))}</p>"
        )
    ack = (
        f"<p style='margin-top:20px'><a href='{e(recipient.ack_url)}' style='background:{color};color:#fff;"
        f"padding:10px 18px;border-radius:6px;text-decoration:none;font-weight:600'>Acknowledge alert</a></p>"
        if recipient.ack_url else ""
    )
    return f"""<!doctype html><html><body style="margin:0;background:#f1f5f9;font-family:Segoe UI,Arial,sans-serif;color:#0f172a">
<div style="max-width:680px;margin:0 auto;padding:24px">
 <div style="background:{color};color:#fff;padding:16px 20px;border-radius:10px 10px 0 0">
  <div style="font-size:12px;letter-spacing:.08em;opacity:.9">VARUNA AI · EARLY WARNING</div>
  <div style="font-size:22px;font-weight:700;margin-top:4px">{e(alert.level.upper())} flood alert: {e(alert.district)}</div>
  <div style="opacity:.9">{e(alert.region)} · alert #{alert.id}</div>
 </div>
 <div style="background:#fff;padding:20px;border-radius:0 0 10px 10px">
  <p style="margin-top:0">Dear {e(recipient.name)},</p>
  <p>{e(alert.message)}</p>
  <table style="width:100%;border-collapse:collapse;margin:8px 0 4px">
   <tr><td style="padding:4px 0;color:#475569">Expected rainfall</td><td><b>{alert.rain_event_mm:.0f} mm</b> over {alert.rain_duration_days} day(s)</td></tr>
   <tr><td style="padding:4px 0;color:#475569">Max flood probability</td><td><b>{alert.flood_probability:.0%}</b>{" · model confidence " + e(alert.confidence_label) if alert.confidence_label else ""}</td></tr>
   {"<tr><td style='padding:4px 0;color:#475569'>AI heavy-rain probability (24 h)</td><td><b>" + f"{alert.rain_probability:.0%}" + "</b></td></tr>" if alert.rain_probability is not None else ""}
   <tr><td style="padding:4px 0;color:#475569">Valid until</td><td>{alert.valid_until:%d %b %Y %H:%M} UTC</td></tr>
  </table>
  <h3 style="margin:20px 0 6px">Villages at risk</h3>
  <table style="width:100%;border-collapse:collapse;font-size:14px">
   <tr style="background:#f8fafc;text-align:left"><th style="padding:6px 10px">Village</th><th style="padding:6px 10px">Band</th><th style="padding:6px 10px;text-align:right">Prob.</th><th style="padding:6px 10px;text-align:right">Depth</th><th style="padding:6px 10px">Main reasons</th></tr>
   {rows}
  </table>
  {timeline_html}
  <h3 style="margin:20px 0 6px">Why {e(alert.level)} risk?</h3><ul style="margin:0;padding-left:20px">{drivers}</ul>
  {actions_html}
  {incident}
  {ack}
  <p style="font-size:12px;color:#64748b;margin-top:24px">Generated by VARUNA AI from the fusion rainfall model and a village runoff/terrain model.
  Figures are decision support, not a substitute for field verification. Dashboard: {e(alert.dashboard_url)}</p>
 </div>
</div></body></html>"""
