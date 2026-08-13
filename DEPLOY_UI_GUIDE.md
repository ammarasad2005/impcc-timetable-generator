# Deploying the CP-SAT backend to Google Cloud Run — UI Guide

A click-by-click guide using **only the Google Cloud Console** (no `gcloud` CLI needed).
At the end you will have a live HTTPS URL that serves the CP-SAT solver.

> ⏱ Total time: ~15–20 minutes (most of it is the one-time account/billing setup).
> 💰 Cost: **$0/month** for this workload (stays inside Cloud Run's free tier).
> 🔑 One-time requirement: a credit/debit card (required to enable billing — you are **not charged** while inside the free tier).

---

## Part 0 — One-time setup (skip if already done)

### Step 0.1 — Create a Google Cloud account
1. Go to **https://console.cloud.google.com**
2. Sign in with a Google account (your personal Gmail is fine).
3. If it's your first time, you may be offered a **$300 / 90-day free trial** — accept it (harmless; the free tier below applies permanently after it too).

### Step 0.2 — Create a project
1. In the top bar, click the **project selector** (it shows something like "No organization" / "My First Project").
2. Click **NEW PROJECT**.
3. **Project name:** `impcc-timetable` (anything you like).
   - Note the auto-generated **Project ID** (e.g. `impcc-timetable-123456`) — you'll see it later, but you don't need to type it anywhere in this UI guide.
4. Click **CREATE**.
5. When it's ready, make sure the new project is selected in the top bar (the blue banner usually shows "Select project" → click it → choose your project).

### Step 0.3 — Enable billing (card required)
Cloud Run needs billing **enabled** even though the free tier means $0 for us.

1. In the top-left **☰ (hamburger) menu** → **Billing**.
2. Click **Link a billing account**.
3. If you have no billing account yet → click **Create billing account**:
   - Account type: **Google Cloud Billing account** (Individual is fine).
   - Country, currency, and **credit/debit card** details → **SUBMIT AND ENABLE BILLING**.
4. Confirm the account now shows as "Linked" on the Billing page.

> You won't be charged: Cloud Run's free tier (2M requests, 180k vCPU-sec, 360k GiB-sec per calendar month) absorbs this project's usage many times over. We'll set a budget alert in Part 4 so you get an email long before anything could ever be billed.

---

## Part 1 — Deploy the backend (the main event)

### Step 1.1 — Open Cloud Run
1. ☰ menu → **Cloud Run** (it's under "Serverless"). If you see a search box, just type **Cloud Run**.
2. First visit: if asked to **enable the Cloud Run API**, click **ENABLE** (wait ~30 s).
3. On the **Services** page, click **Deploy container** (or **CREATE SERVICE**).

### Step 1.2 — Choose "continuous deployment from GitHub"
In the **Create service** form:

1. Under **Deployment platform**, keep **Cloud Run service**.
2. Choose **Continuously deploy new revisions from a source repository** (this makes Cloud Run *build* your Dockerfile automatically — no terminal needed).
3. Click **SET UP WITH CLOUD BUILD**.

### Step 1.3 — Connect your GitHub repo
1. In the panel that opens, the **repository provider** defaults to **GitHub**.
2. Click **Authenticate** (or **Connect**), then **Authorize** Google Cloud on GitHub.
3. GitHub asks to install the **Google Cloud Build** app → choose your account → **Only select repositories** → pick **`impcc-timetable-generator`** → **Install & Authorize**.
4. Back in the Cloud Run panel:
   - **Repository:** `ammarasad2005/impcc-timetable-generator` (if it's not listed yet, click **Manage connected repositories** and add it).
5. **Build Configuration:**
   - **Branch:** `^main$` (the default regex is fine).
   - **Build Type:** **Dockerfile**.
   - **Dockerfile location / Source location:** `Dockerfile` (it's at the repo root — leave the default).
6. Click **SAVE** (or **Next**). The form reloads and the **Source repository** section now shows your repo + branch.

### Step 1.4 — Configure the service
Now fill in the rest of the **Create service** form:

| Setting | Value | Why |
|---|---|---|
| **Service name** | `impcc-cp-sat` | visible in the URL |
| **Region** | `us-central1` (Iowa) | ⚠️ the **free tier is priced on this region** — don't change it |
| **Authentication** | **Allow unauthenticated invocations** | your website must call it without a login |
| **Container → CPU** | **2** | CP-SAT solves faster with 2 vCPU |
| **Container → Memory** | **2 GiB** | plenty for the solver |
| **Container → Port** | `8080` | matches the Dockerfile's `EXPOSE` |
| **Autoscaling → Minimum instances** | **0** | scale-to-zero → $0 when idle |
| **Autoscaling → Maximum instances** | **3** | safety cap |
| **Autoscaling → Max concurrent requests per instance** | **1** | one heavy CP-SAT solve per instance at a time (CPU-bound workload) |
| **Request timeout** | **300 seconds** | a full optimal solve can take ~45–90 s; give it headroom |

> "CPU allocation" — keep the default (**CPU only allocated during request processing**). That's the request-based billing mode that gets the free tier.

### Step 1.5 — Deploy
1. Click **CREATE**.
2. Cloud Build now compiles your Dockerfile and deploys. You'll see progress on the **Service details** page (first build takes ~2–4 minutes; the OR-Tools install is the slow part).
3. When finished, a ✅ and a green checkmark appear next to the service name, with a URL at the top like:
   ```
   https://impcc-cp-sat-XXXXXXXXXX-uc.a.run.app
   ```
4. **Copy that URL** — this is your `API_URL`.

> From now on, **every push to `main` on GitHub automatically rebuilds and redeploys** the service. That's a feature — update the code, push, done.

---

## Part 2 — Verify it works

### 2.1 Health check (in your browser)
Open:
```
https://YOUR-URL.a.run.app/health
```
You should see: `{"ok":true,"service":"impcc-timetable-generator","solver":"cp-sat"}`

### 2.2 Test a real solve — the easy (UI) way
FastAPI ships an interactive docs page — perfect for a no-curl test:

1. Open **`https://YOUR-URL.a.run.app/docs`** (Swagger UI).
2. Click **POST /generate** → **Try it out**.
3. Leave the default body (or set `"time_limit": 45`), click **Execute**.
4. You'll get back the ranked solutions JSON with `"optimal": true` and `"best_score": 560`.

### 2.3 (Optional) From a terminal
```bash
curl -X POST https://YOUR-URL.a.run.app/generate \
  -H "Content-Type: application/json" \
  -d '{"time_limit":45,"n_seeds":2,"max_solutions":0}'
```

---

## Part 3 — Connect your frontend

### If you're keeping my frontend (`app.js`)
1. Open `app.js`, find `const API_URL = ...`, and set:
   ```js
   const API_URL = "https://YOUR-URL.a.run.app";
   ```
2. Run `python3 build_site.py` to rebuild `index.html`, then redeploy to Vercel.

### If you're building your own frontend
Just `POST` to `{API_URL}/generate` with:
```json
{ "time_limit": 45, "n_seeds": 2, "max_solutions": 0 }
```
and render the `solutions[].timetable` (5 rows × 5 cells per section; break sits between cell index 2 and 3). See `backend/README.md` for the full contract.

---

## Part 4 — Cost safety (set this up, 2 minutes)

### Budget alert
1. ☰ menu → **Billing** → **Budgets & alerts**.
2. Click **CREATE BUDGET**.
   - **Scope:** your billing account; **Projects:** select `impcc-timetable` (optional).
   - **Amount:** `$5`.
   - **Actions:** tick **Email alerts to billing admins and users**.
   - **Threshold rules:** 50%, 90%, 100%.
3. Click **SAVE**.

You'll get an email if monthly spend ever approaches $5 — for this workload it never will, but it's the correct safety net.

### Check spend anytime
☰ → **Billing** → **Billing overview** shows your current month's charges (expect $0.00).

---

## Part 5 — Troubleshooting

| Symptom | Fix |
|---|---|
| "Enable the Cloud Run API" error | ☰ → **APIs & Services** → search **Cloud Run API** → **ENABLE** (also enable **Cloud Build API** and **Artifact Registry API** if prompted) |
| GitHub repo doesn't appear | In the connect panel, click **Manage connected repositories** → re-authorize → make sure you granted the **Google Cloud Build** app access to `impcc-timetable-generator` |
| Build fails | ☰ → **Cloud Build** → **History** → click the failed build → read the error. Common: Dockerfile path wrong (should be `Dockerfile` at root) |
| First request is slow (~3–5 s) | Normal **cold start** — the instance scales to zero when idle and spins up on demand. Keep `min-instances = 0` (free). |
| 504 Gateway Timeout | Increase **Request timeout** (we already set 300 s) and make sure `max-concurrency = 1` so a solve isn't starved |
| `{"detail":"Not Found"}` | You're hitting a wrong path — the API is at `/health` and `/generate` only |
| Service requiring login | You forgot **Allow unauthenticated invocations** — edit the service → **Security** tab → re-enable it |
| Want to pause everything | Cloud Run → select service → **DELETE SERVICE** (free tier means idle costs $0, so you can also just leave it) |

---

## The result

| What | Where |
|---|---|
| Live solver URL | `https://YOUR-URL.a.run.app` |
| Health check | `/health` |
| Swagger (click-test) | `/docs` |
| Monthly cost | $0 (free tier, calendar-month reset) |
| Auto-deploy | every `git push` to `main` |
