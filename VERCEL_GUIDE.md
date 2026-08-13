# Deploying the CP-SAT backend to Vercel — UI Guide

A click-by-click guide using only the **Vercel web dashboard** (no terminal).
At the end you get a live HTTPS URL that serves the CP-SAT solver on the same
platform as your frontend.

> ⏱ Time: ~5 minutes. 💰 Cost: $0 on the Hobby plan (free tier).
> ⚠️ **Important:** Vercel's Hobby (free) plan is for **personal, non-commercial** use.
> You and the principal have already discussed and accepted this for this project —
> just be aware a paid/commercial project is technically expected to use Pro ($20/mo).
> Compute reality (your criterion): Vercel Hobby gives each function **1 vCPU + 2 GB RAM
> and up to 300 s** — far more per-request compute than Render's free 0.1 vCPU, so
> CP-SAT solves ~10× faster here.

---

## Part 0 — What's already in the repo

| File | Purpose |
|---|---|
| `api/index.py` | FastAPI app (the function Vercel runs) — `POST /generate`, `GET /health`, `GET /docs` |
| `vercel.json` | rewrites `/generate` & `/health` to the function; `maxDuration: 300`, `memory: 1024 MB`, and `includeFiles` so `cp_solver.py`/`solver.py` get bundled |
| `requirements.txt` | `ortools` + `fastapi` (Vercel installs these at build) |

## Part 1 — Deploy

1. Go to **https://vercel.com** → sign in (same account as your frontend).
2. Click **Add New…** → **Project**.
3. **Import Git Repository** → if your GitHub isn't linked yet, click **Import Third-Party Git Repository** (or **Connect GitHub**) → authorize → pick **`ammarasad2005/impcc-timetable-generator`**.
4. On the **Configure Project** screen:
   - **Framework Preset:** choose **Other** (it's a static site + Python functions, not a Next.js app).
   - **Root Directory:** leave as `.` (do **not** set it to `api/` — the function imports `cp_solver.py` from the root).
   - **Build Command / Output Directory / Install Command:** leave empty — no build step; Vercel auto-installs `requirements.txt` for the Python function.
5. (Optional) **Environment Variables** → add `CP_SAT_WORKERS` = `4` (fewer solver threads for the 1-vCPU function — slightly less memory churn).
6. Click **Deploy**.
7. When it finishes, Vercel shows your URL:
   ```
   https://impcc-timetable-generator-XXXXXXXX.vercel.app
   ```
   **Copy that URL** — this is your `API_URL` base.

> Every `git push` to `main` auto-redeploys.

## Part 2 — Verify

1. **Health:** open `https://YOUR-URL.vercel.app/health`
   → `{"ok":true,"service":"impcc-timetable-generator","solver":"cp-sat"}`
2. **Swagger:** open `https://YOUR-URL.vercel.app/docs`
   → click **POST /generate** → **Try it out** → **Execute** (default body is fine)
   → you'll see ranked solutions with `"best_score": 560`.
3. **Quick curl (optional):**
   ```bash
   curl -X POST https://YOUR-URL.vercel.app/generate \
     -H "Content-Type: application/json" \
     -d '{"time_limit":20,"n_seeds":1,"max_solutions":0}'
   ```

> If `/health` returns 404, the rewrite didn't apply — use the raw path
> `/api/index/health` and `/api/index/generate` (same contract, longer URL).

## Part 3 — Connect your frontend

- **My frontend (`app.js`):** set `const API_URL = "https://YOUR-URL.vercel.app"` →
  `python3 build_site.py` → redeploy the site.
- **Your own frontend:** `POST {API_URL}/generate` with `{ time_limit, n_seeds, max_solutions }`
  and render `solutions[].timetable` (5 rows × 5 cells per section; break sits between
  cell index 2 and 3). Full contract in `backend/README.md`.

## Part 4 — Tuning & limits (Hobby)

| Setting | Value | Why |
|---|---|---|
| `maxDuration` | 300 s | already in `vercel.json` — a 20 s solve fits with huge headroom |
| `memory` | 1024 MB | already set; Hobby allows up to 2048 MB |
| `time_limit` in requests | **20 s** (default in `api/index.py`) | 20 s reliably returns the **560** best-known on 1 vCPU |
| `n_seeds` | 1 | keeps each call ~20 s |
| Monthly CPU budget | roughly a few CPU-hours + 1M invocations | a 20 s solve ≈ 20 CPU-seconds → hundreds of solves/month, plenty for a college |
| Cold start | ~1–3 s | Python boot + ortools import; no "sleep" like Render |

If a solve ever needs more than 300 s (it won't for this model), that's the point where
Cloud Run's 900 s / Render's no-hard-cap would matter.

## Part 5 — Troubleshooting

| Symptom | Fix |
|---|---|
| `MODULE_NOT_FOUND: cp_solver` in logs | `includeFiles` in `vercel.json` must list `cp_solver.py` and `solver.py` — verify it wasn't removed |
| `404` on `/health` | rewrites not applied → use `/api/index/health` directly, or check `vercel.json` deployed |
| `504 FUNCTION_INVOCATION_TIMEOUT` | solve exceeded `maxDuration`. Lower `time_limit` to 20, `n_seeds` to 1 |
| Function killed (memory) | lower `CP_SAT_WORKERS` to 2 via Environment Variables |
| "Python version not supported" | add `"runtime": "python3.12"`? Not needed — Vercel defaults are fine; if you see this, set Python 3.12 in Project → Settings → General |
| Want only the backend (no static `index.html` at `/`) | Deploy the repo as-is (the static page at `/` is harmless), or delete `index.html`/`app.js`/`solver.js` from the deployed branch |

## The result

| What | Where |
|---|---|
| Live solver URL | `https://YOUR-URL.vercel.app` |
| Health check | `/health` |
| Swagger (click-test) | `/docs` |
| Monthly cost | $0 (Hobby — non-commercial) |
| Auto-deploy | every `git push` to `main` |

---

### Backups (if Vercel ever doesn't suit)

The same backend is also ready for:
- **Render** (`render.yaml` + `RENDER_GUIDE.md`) — free, no card, but 0.1 vCPU (slower).
- **Google Cloud Run** (`deploy.sh` + `backend/README.md` + `DEPLOY_UI_GUIDE.md`) — fastest free tier, needs a physical bank card.
