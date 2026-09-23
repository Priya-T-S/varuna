# What-if flood advisor & threshold alerting

> **Prototype / simulation mode.** No live rain-gauge, IMD or river-gauge feed is connected. Weather and river inputs are operator-provided, simulated or estimated; AI inference and risk analysis run on the supplied conditions. Alerts are automatically generated when the *evaluated* district risk crosses the configured threshold.

This guide covers two things:

- The **What-if** page (`/what-if`). You describe a rainfall situation in plain language, and a Claude-powered advisor simulates it.
- The **alerting** pipeline. It notifies district collectors when flood risk crosses a threshold.

## 1. How a what-if is computed

```
"If rainfall increases by 20% in Kerala, which villages flood?"
        │  Claude (claude-opus-5) maps the text to tool parameters
        ▼
simulate_flood_scenario(region="Kerala", rainfall_change_pct=20, …)
        │
        ├─ rainfall inputs    baseline = region's reference heavy spell (data/geo/regions.json)
        │                     scenario = baseline × (1 + change) + stated conditions
        ├─ fusion AI model    P(heavy rain, 24 h) for baseline and scenario, plus the SHAP delta
        ├─ hydrology model    per village (data/geo/villages.json):
        │                       SCS curve-number runoff (soil × built-up, antecedent moisture)
        │                       × terrain exposure (HAND, river distance, slope)
        │                       + drainage + flood history + AI signal + dam release + high tide
        │                     → flood probability, band, indicative depth, landslide flag,
        │                       and each factor's contribution (additive log-odds)
        └─ past incidents     data/geo/flood_incidents.json, ranked by region, intensity,
                              causes and places hit, each with a "why similar" explanation
        ▼
Answer: What could happen · Why · Past incidents like this · Suggested actions
```

The advisor quotes only numbers returned by its tools. The same structured result drives the map, the village table, the factor bars and the incident cards. The **Scenario controls** panel calls `POST /api/v1/scenarios/simulate` directly, so the simulator also works without an API key.

**Honest limits:**

- The terrain and incident datasets are curated approximations for demonstration. Their disclaimers are in each JSON file.
- The fusion model predicts rainfall, not floods. Its probability can fall when rainfall is pushed beyond the training range. The result flags this, and flood risk then rests on the runoff model.
- Assam flooding is driven largely by upstream Brahmaputra flow, so local-rain results there are a lower bound.

### Enable the advisor

Create an API key at <https://console.anthropic.com> and add it to `backend/.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
CHAT_MODEL=claude-opus-5     # default
CHAT_EFFORT=medium           # low | medium | high; higher is deeper but slower
```

Server-side refusal fallback is on (`fallbacks="default"`), so a policy decline is retried on Anthropic's recommended fallback model. Conversations are stored in the `chat_messages` table, which lets follow-ups ("and if the dams release too?") keep their context.

## 2. Alerting pipeline

```
monitor (every ALERT_SCAN_INTERVAL_MIN)  or  POST /api/v1/alerts/evaluate (observed/forecast rain)
   → scenario engine on current conditions → villages grouped by district
   → district level = worst village band → AlertRule (min level, min prob, cooldown)
   → FloodAlert (message with villages, drivers, similar incident, recommended actions)
   → dispatcher: recipients of that district whose escalation tier ≤ level
        → each subscribed channel concurrently, 3 attempts with back-off
        → AlertDelivery audit rows (targets masked)
   → dashboard SSE feed (toast + browser notification) → one-tap acknowledge link
```

- **Cooldown:** a district is not re-alerted while an alert at the same or a higher level is active and inside the cooldown. An **escalation**, for example high to severe, always goes out and supersedes the previous alert.
- **Escalation tiers:** each recipient has a `min_level`. The seeded directory lists every district collector or deputy commissioner at `high`, and each state's SDMA / EOC at `severe`.
- **Live data:** there is no live rain-gauge feed yet. Unattended scans use current-month climatology, so they only fire in genuinely wet months. Push observations through `POST /alerts/evaluate`, or through the **Evaluate now** panel on `/alerts/settings`.

### Channels (all free)

| Channel | What you need | `.env` keys |
|---|---|---|
| **Telegram** (recommended) | Message **@BotFather**, send `/newbot`, and copy the token. Each officer opens the bot and presses **Start**. Get their `chat.id` from `https://api.telegram.org/bot<TOKEN>/getUpdates`. A control-room group also works: add the bot, and the id is negative. | `TELEGRAM_BOT_TOKEN`, optional `TELEGRAM_DEFAULT_CHAT_ID` (receives every alert) |
| **E-mail** | Gmail: turn on 2-Step Verification, then go to **App passwords** and create one. | `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` |
| **SMS** | Twilio trial (free credit). Verify each recipient's number in the Twilio console. | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_SMS_FROM` |
| **WhatsApp** | Twilio WhatsApp sandbox. Each recipient sends the sandbox's `join <code>` message once. | `TWILIO_WHATSAPP_FROM=whatsapp:+14155238886` (plus the SID and token) |
| Dashboard | Always on: Server-Sent Events feed, toast and browser notification. | — |
| Server log | Always on: every alert is logged. | — |

To finish setup:

1. Restart the backend.
2. Open **Alerts → Recipients & channels**. Each configured channel shows as *active*.
3. Fill in a collector's contact details and tick their channels.
4. Press **Send test**. The result lists every delivery as sent, failed or skipped, with the reason.

For the **Acknowledge** buttons in Telegram, e-mail and WhatsApp to work from a phone, `PUBLIC_BASE_URL` must be reachable from the internet, for example through an ngrok or cloudflared tunnel to port 8000. Telegram only shows inline buttons for public URLs. With a localhost URL, the link is included as text instead.

## 3. What every warning carries

- **Flood probability, model confidence, last data update and horizon.** Confidence (High/Medium/Low) comes from the fusion model. The horizon is the AI's 24-hour window, plus when the flood projection peaks. Freshness is the time the rainfall input was observed or entered, together with its `data_mode`:
  - `observed`: entered by an operator;
  - `climatology`: the automatic monitor;
  - `demo`: a demo scenario;
  - `scenario`: a what-if run;
  - `test`: a test alert.
- **"Why {level} risk?":** up to 6 short bullets, covering rain, soil state, river rise, terrain, dam or tide, the past incident, and the AI signal. **River rise is a modelled estimate from the runoff model and is labelled "modelled". No gauge feed is connected.** *View full explanation* opens the SHAP contributions and the village factors.
- **Risk timeline:** Now → +6 h → +12 h → +24 h → +48 h. When the rain spell lasts longer, an end-of-rain point is added. This is a hydrological projection from the rainfall scenario, not an AI output.
- **Recommended actions:** decision support, never automatic. Ticking an action records it in the audit trail.
- **Lifecycle:** Detected → Generated → Reviewed → Sent → Acknowledged → Resolved. Alerts are auto-approved by rule, and the trail says so. Operators can review, change severity (a reason is required), add notes and resolve. Every event records the time, the actor ("Acting as" name) and details. Escalations link to the alert they replace.

## 4. Transparency pages

- **Status** (`/status`):
  - component health, including the AI model, the rainfall data mode and freshness, and river data (always "Simulated");
  - notifications and the monitor;
  - a data-source table that labels each input as live, manual, historical, modelled, simulated or demo;
  - **Simulate a failure** switches (stale rainfall feed, AI model down, notification provider down) that demonstrate the fallback banners.
- **Model** (`/model`): the evaluation exactly as recorded in `ai_models/saved_models/model_info.json`:
  - heavy-rain recall, missed-event rate, precision and false-alarm rate;
  - the confusion matrix and dataset;
  - the report's own limitations.
- **Header:** separate *AI / Weather / River* status pills, and a banner when anything is degraded or the connection drops.
- **Demo:** Overview → **Run demo scenario** runs *Extreme Kerala rainfall* (350 mm / 3 d, saturated) or the *Mumbai 26 July replay* through the real pipeline and animates each stage.

## 5. API summary

| Method & path | Purpose |
|---|---|
| `POST /api/v1/scenarios/simulate` | Deterministic what-if (`region`, `rainfall_change_pct` or `rainfall_mm`, `duration_days`, `antecedent`, `dam_release`, `high_tide`, `district`) |
| `POST /api/v1/chat` · `GET /api/v1/chat/{session_id}` | Advisor conversation and transcript (503 if no key is configured) |
| `GET /api/v1/geo/regions` · `/geo/villages` · `/geo/incidents` | Reference data |
| `GET /api/v1/alerts` · `/alerts/recent` · `/alerts/{id}` | Alerts with delivery status |
| `GET /api/v1/alerts/stream` | Live SSE feed |
| `POST /api/v1/alerts/evaluate` | Evaluate a region now, optionally with observed rain |
| `POST /api/v1/alerts/test` | Send a realistic `[TEST]` alert |
| `POST /api/v1/alerts/{id}/acknowledge` · `GET /alerts/{id}/ack?token=` | Acknowledge from the dashboard, or from the signed link inside messages |
| `GET /api/v1/alerts/providers` | Channel configuration status |
| `/api/v1/recipients` · `/api/v1/alert-rules` | CRUD |
| `GET /api/v1/alerts/{id}/events` · `POST /alerts/{id}/review` · `/severity` · `/resolve` · `/note` | Audit trail and lifecycle actions |
| `GET /api/v1/system/status` · `/system/data-sources` · `/system/current-risk` | Health, data provenance, map snapshot |
| `GET/POST /api/v1/system/faults` | Demo failure switches |
| `POST /api/v1/demo/run` | One-click demo scenario |
| `GET /api/v1/predictions/model-performance` | Recorded evaluation plus derived warning metrics |

## 6. Storage

The default database is SQLite at `backend/varuna.db`, created on first start with seeded recipients and a global rule. Set `USE_POSTGRES=true` (docker-compose does this) or `DATABASE_URL` to use PostgreSQL. The ORM tables (`flood_alerts`, `alert_recipients`, `alert_rules`, `alert_deliveries`, `chat_messages`) are created automatically and do not clash with `database/schema.sql`.
