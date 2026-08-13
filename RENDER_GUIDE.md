# Deploying the CP-SAT backend to Render (free, no card) — UI Guide

A click-by-click guide using only the **Render web dashboard** (no terminal).
At the end you get a live HTTPS URL that serves the CP-SAT solver.

> ⏱ Time: ~10 minutes. 💰 Cost: $0 (Render free tier, no credit card for this path).
> ⚠️ Render's free tier is **weaker than Cloud Run**: 512 MB RAM + 0.1 shared vCPU, and the
> service **sleeps after 15 minutes of inactivity** (wake-up takes ~30–60 s). For a timetable
> generator used occasionally, this is a fine trade-off for not needing a card.

---

## Part 0 — Sign up (no card)

1. Go to **https://dashboard.render.com**.
2. Click **Get Started** → **Sign up with GitHub** → authorize Render.
3. That's it. You land on the dashboard. (You do **not** add a card; billing is only needed
   for *paid* instances. If Render ever asks for a card during sign-up, see the note in Part 5.)

## Part 1 — Deploy via Blueprint (the easy way)

The repo already contains `render.yaml`, so Render can create the whole service in one step.

1. On the dashboard, click **New +** (top-right) → **Blueprint**.
2. Render asks to connect your GitHub → click **Connect GitHub** → **Authorize Render** →
   choose your account → **Only select repositories** → tick **`impcc-timetable-generator`** → **Install**.
3. Back on Render, pick repository **`ammarasad2005/impcc-timetable-generator`** → **Continue**.
4. Render reads `render.yaml` and shows a preview: one web service named **`impcc-cp-sat`**
   (Docker, free plan). Click **Apply** (or **Create resources**).
5. Render now:
   - builds the image from the `Dockerfile` (first build ~3–5 min — the OR-Tools install is the slow part),
   - starts the service and waits until `/health` returns OK.
6. When it's green, open the service and you'll see the URL at the top:
   ```
   https://impcc-cp-sat.onrender.com
   ```
   **Copy that URL** — this is your `API_URL`.

> From now on, every `git push` to `main` **auto-redeploys** the service.

## Part 2 — Verify it works

1. **Health check** — open `https://impcc-cp-sat.onrender.com/health`
   → you should see `{"ok":true,"service":"impcc-timetable-generator","solver":"cp-sat"}`.
   *(First open right after a sleep may take ~30–60 s — that's the cold start.)*
2. **Test a real solve** — open `https://impcc-cp-sat.onrender.com/docs` (Swagger UI):
   - click **POST /generate** → **Try it out**,
   - body: `{ "time_limit": 20, "n_seeds": 1, "max_solutions": 0 }`,
   - click **Execute**. You'll get ranked solutions with `"best_score": 560`.

## Part 3 — Connect your frontend

- My frontend (`app.js`): set `const API_URL = "https://impcc-cp-sat.onrender.com";` →
  `python3 build_site.py` → redeploy the site to Vercel.
- Your own frontend: `POST {API_URL}/generate` with `{ time_limit, n_seeds, max_solutions }`
  and render `solutions[].timetable`. Contract is in `backend/README.md`.

## Part 4 — Tuning for Render's small free instance

The free tier is **0.1 vCPU / 512 MB**, so:

| Thing | Recommendation | Why |
|---|---|---|
| Solver workers | already set to **4** via `CP_SAT_WORKERS` in `render.yaml` | 8 threads thrash on a 0.1 vCPU slice |
| `time_limit` in requests | **20 s** (not 45) | proves-optimal may not finish on 0.1 vCPU; 20 s reliably returns the **560** best-known anyway |
| `n_seeds` | **1–2** | keeps each call snappy |
| "optimal" flag | treat as *"best found"* if `optimal:false` | the browser shows either state; both return valid 560 timetables |

Cold start: the service sleeps after 15 min idle. First request after that takes ~30–60 s.
If that matters (e.g. demoing to the college), set up a **free keep-alive** that pings `/health`
every 10 min — e.g. **cron-job.org**, **UptimeRobot** (free tier), or **cron-job.org**. Or accept it.

## Part 5 — Troubleshooting

| Symptom | Fix |
|---|---|
| Render asks for a **card** at sign-up / deploy | Some accounts are prompted for verification. If it blocks you, use one of the other no-card hosts instead: **Koyeb** (1 free always-on service, 512 MB, usually no card) or **SnapDeploy** (free Docker, auto-sleep/wake). The same Dockerfile works on both. |
| Build fails | Open the service → **Events/Logs** → read the error. Common: Dockerfile not found (should be at repo root) |
| `404` on `/` | Correct — the API only exists at `/health`, `/generate`, and `/docs` |
| Very slow first request | Cold start after sleep (normal on free). Use a keep-alive ping or wait |
| `502 Bad Gateway` | The service was still waking up / starting. Retry once — Render will finish booting |
| Memory errors in logs | Reduce `CP_SAT_WORKERS` to 2 (edit env var in the service → **Environment**) |
| Want to stop it | Service → **Settings** → **Suspend service** (or delete). Free = $0 either way |

---

## The result

| What | Where |
|---|---|
| Live solver URL | `https://impcc-cp-sat.onrender.com` |
| Health check | `/health` |
| Swagger (click-test) | `/docs` |
| Monthly cost | $0 (free tier, 750 instance-hrs/mo, sleeps when idle) |
| Auto-deploy | every `git push` to `main` |

## If Render doesn't work out — plan B (same Dockerfile, no card)

- **Koyeb** — 1 free web service, **always-on** (no sleep), 512 MB / 0.1 vCPU, usually no card.
- **SnapDeploy** — free Docker containers (512 MB, 0.25 vCPU), auto-sleep/wake, no card.
Both deploy the same repo; ask me and I'll write the equivalent guide/config for either.
