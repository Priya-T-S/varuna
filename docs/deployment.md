# Deployment

Two pieces, one public URL. The backend runs on any Docker host — Hugging
Face Spaces (free, sleeps when idle) or Railway (paid, always on):

- **Frontend** (React/Vite) on **Vercel** — static, fast, free.
- **Backend** (FastAPI + PyTorch + SHAP) on **Hugging Face Spaces** (Docker) —
  needs a long-running process and ~400 MB RAM.
- `vercel.json` proxies `/api/*` from the Vercel domain to the Space, so the
  browser only ever talks to one origin (no CORS setup, no mixed URLs).

## Why not everything on Vercel

Vercel's Python functions cap at 250 MB unzipped; `torch` alone is ~540 MB
installed. The backend also runs a background alert monitor and an SSE feed,
which serverless functions cannot keep alive. Render's free tier (512 MB RAM)
is too close to the ~390 MB the loaded models already occupy, and Railway has
no free tier, so Spaces (16 GB, free) is the comfortable default.

## 1. Backend on Hugging Face Spaces

1. https://huggingface.co/new-space → name `varuna-backend`, SDK **Docker**
   (blank template), visibility public, hardware **CPU basic (free)**.
2. Create a **write token** at https://huggingface.co/settings/tokens.
3. From the repo root, in Git Bash:

   ```bash
   scripts/deploy_to_hf.sh <your-hf-username>
   ```

   It asks for your username and that token. Re-run it after any change on
   `main` to redeploy. Add `--dry-run` to build the branch without pushing.

   The script exists because a Space rejects files over 10 MB unless they use
   Git LFS, and `rainfall_model_v1.pkl` is 28 MB. It rebuilds an orphan `space`
   branch that stores the model files as LFS objects and adds the YAML front
   matter a Space needs in its README, then force-pushes that branch to the
   Space's `main`. Your GitHub history is untouched.

4. The first build takes ~10 minutes (PyTorch). Watch the Space's **Logs** tab.
   Then check `https://<username>-varuna-backend.hf.space/api/v1/health` and
   `/api/v1/predictions/model-info`, which should report `"model_loaded": true`.

Optional Space **Settings → Variables and secrets**:

| Name | Value | Effect |
|---|---|---|
| `ANTHROPIC_API_KEY` | your key | What-if chat uses Claude instead of offline mode |
| `TELEGRAM_BOT_TOKEN`, `SMTP_*`, `TWILIO_*` | provider credentials | Real alert delivery |
| `PUBLIC_BASE_URL` | the Space URL | Working one-tap acknowledge links |
| `CORS_ORIGINS` | your Vercel URL | Only needed if the frontend calls the Space directly |

The Space's disk is ephemeral: alerts and chat history (SQLite at `/tmp`) reset
on every restart. Set `DATABASE_URL` to a hosted Postgres to keep them.

### Alternative: backend on Railway

Paid (a one-time trial credit, then ~$5/month) but it never sleeps, redeploys
on every GitHub push and supports a custom domain.

1. https://railway.app → **New Project → Deploy from GitHub repo** → this repo.
   Railway detects the root `Dockerfile`; no build settings needed.
2. **Settings → Networking → Generate Domain**. Railway sets `$PORT`, which the
   image already honours.
3. Same variables as the Spaces table above, under **Variables**.
4. Check `https://<domain>/api/v1/health`, then use that host in `vercel.json`.

## 2. Frontend on Vercel

1. In `vercel.json`, replace `REPLACE-WITH-YOUR-BACKEND-HOST` with the Space
   host, e.g. `<your-hf-username>-varuna-backend.hf.space` (no `https://`, no
   trailing slash).
   Commit and push.
2. https://vercel.com/new → import `Priya-T-S/varuna` → **Root Directory:
   leave as the repo root** (`vercel.json` builds `frontend/` itself) → Deploy.
3. Open the Vercel URL. The dashboard, forecasts, what-if and alerts all work
   through `/api` on that same domain.

Leave `VITE_API_URL` **unset** on Vercel so requests stay same-origin and go
through the proxy.

## Notes

- **First request after idle is slow.** A free Space sleeps after ~48 h
  unused; the next request wakes it (~30 s), and the frontend's 20 s timeout
  may show an error once. Open the health URL before a demo.
- **Live alert feed through the proxy.** SSE (`/api/v1/alerts/stream`) works
  but is buffered by some proxies. If the "Live" indicator stays off in
  production, set `VITE_API_URL` to the Space URL on Vercel and add that Vercel
  URL to `CORS_ORIGINS` on the Space; the feed then connects directly.
- **`backend/Dockerfile` vs the root `Dockerfile`.** The one in `backend/`
  ships only the API (used by `deployment/docker-compose.yml`, where models are
  mounted). The root `Dockerfile` bundles `ai_models/`, `explainability/`,
  `config/` and `data/geo/`, which is what a standalone host needs.
- **Local development is unchanged:** `uvicorn app.main:app --reload` in
  `backend/`, `npm run dev` in `frontend/`.
