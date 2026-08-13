# IMPCC Timetable Generator — Backend (CP-SAT on Cloud Run)

FastAPI service that wraps the CP-SAT model (`cp_solver.py`) so the frontend can fetch
**provably-optimal** timetables (best score 560) instead of the in-browser solver's
near-optimal 570–580.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness check |
| POST | `/generate` | run CP-SAT, return ranked valid timetables |

### POST /generate

```json
{ "time_limit": 45, "n_seeds": 2, "max_solutions": 0 }
```

- `time_limit` — seconds per CP-SAT seed. **45 s proves optimality** (verified offline).
- `n_seeds` — randomized optimization seeds to diversify the solution set.
- `max_solutions` — cap on returned list (0 = no cap).

Response:

```json
{
  "solver": "cp-sat",
  "solutions": [ { "score": 560, "timetable": { "I.COM-I-A": [ ["English", "Prof. …"], … ], … } } ],
  "total_found": 88,
  "optimal": true,
  "best_score": 560,
  "elapsed_seconds": 92.4,
  "meta": { "days": ["MON", …], "slots": ["P1", …], "section_order": [ … ] }
}
```

## Deploy to Render (free, no credit card)

The repo root has `render.yaml` + `RENDER_GUIDE.md`. One-click deploy:
**Render dashboard → New + → Blueprint → connect GitHub → pick this repo → Apply.**

- Free tier: 512 MB RAM, 0.1 vCPU, sleeps after 15 min idle (cold start ~30–60 s).
- `render.yaml` sets `CP_SAT_WORKERS=4` (fewer solver threads for the small instance).
- Recommended request body on Render: `{ "time_limit": 20, "n_seeds": 1, "max_solutions": 0 }`.

## Deploy to Google Cloud Run

```bash
# one-time: install gcloud CLI, then
gcloud auth login
gcloud projects create impcc-timetable   # or use an existing project
gcloud beta billing projects link impcc-timetable --billing-account=XXXXXX-XXXXXX-XXXXXX

# deploy
PROJECT_ID=impcc-timetable ./deploy.sh
```

`deploy.sh` uses free-tier-friendly settings: `--region us-central1`, `--min-instances 0`
(scale to zero → no idle cost), 2 vCPU, 2 GiB, max 3 instances.

## Cost (free tier)

Cloud Run free tier, per **calendar month** (resets on the 1st), per billing account:

| Resource | Free / month | This workload per "generate" call |
|---|---|---|
| Requests | 2,000,000 | 1 |
| vCPU-seconds | 180,000 | ~60–90 (2 seeds × 45 s on 2 vCPU) |
| GiB-seconds | 360,000 | ~30–60 |

→ roughly **2,000–3,000 optimal generations per month for $0**.

Caveats:
- Billing must be **enabled with a card** (no charge while inside the free tier).
- Keep `--region us-central1` (free tier is priced on that region).
- Keep `--min-instances 0` (idle = free; expect a ~2–5 s cold start on the first call).
- Set a **budget alert** in GCP as a safety net.

## Run locally

```bash
pip install -r backend/requirements.txt
uvicorn backend.main:app --host 0.0.0.0 --port 8080
# http://localhost:8080/docs  (Swagger UI)
```

## Wire it to the frontend

Open `app.js` and set

```js
const API_URL = "https://YOUR-CLOUD-RUN-URL.a.run.app";
```

(or inject `window.IMPCC_API_URL` before the page's scripts). The frontend then shows a
**"Compute optimal (CP-SAT)"** button that fetches the proven-optimal set and merges it
into the ranked chooser. If the API is unreachable, the site keeps working with the
in-browser solver.
