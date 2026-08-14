# IMPCC — Inter (1st Shift) Weekly Timetable Generator

Automated timetable generator for **Islamabad Model Postgraduate College of Commerce (H-8)**
— Intermediate level (ICS + I.Com), 1st shift.

11 sections · 5 days (Mon–Fri) · 5 periods/day (40 min) · break after 3rd period · 25 periods/section/week.

---

## The score — what it means

Every generated combination **satisfies all hard rules** (faculty constraints, no subject twice in a
day, no teacher double-booked, the Accounting-vs-Economics non-overriding rule, the parallel
Economics/Statistics block, …). The **score only ranks the soft "avoid shuffling" preference**:

```
score = Σ over subjects  (number of distinct period-slots used − 1) × weekly weight
weight:  5 periods/week → 100,000
         4 periods/week →  10,000
         3 periods/week →     100
         2 periods/week →      10
```

- **Lower is better.** A subject that stays in one period-slot all week contributes 0; a 3/wk subject
  split across two slots contributes +100; a 2/wk subject split as 1+1 contributes +10.
- 5/wk and 4/wk subjects are never shuffled (they would cost 100,000 / 10,000 — always avoided).
- The proven minimum is **560** (= four 3-credit subjects split + sixteen 2-credit subjects split).
  The minimum is non-zero because a section's 25 periods can't always tile into 5 slots of exactly
  5 days without splitting a small subject (e.g. I.Com-I's 5,4,4,3,3,2,2,2 needs at least one split).
- The in-browser solver typically lands at **570–580**; the offline CP-SAT pipeline proves **560**.

---

## Quick start

### 1. The website (no installation, runs entirely in the browser)
Open **`index.html`** in any modern browser (or deploy the repo to Vercel). It generates
combinations **live** using a JavaScript port of the solver (`solver.js`) — **no pre-computed data**.

- **Generate / Generate more / Stop** — fresh run, append more (nothing is ever dropped), or stop early.
- **Compute optimal (CP-SAT)** — calls `POST /generate` (same-origin on Vercel, or set
  `window.IMPCC_API_URL`) to merge proven-optimal (score 560) solutions from the CP-SAT backend.
- **Combination** dropdown + ◀ ▶ — every solution is listed with rank, score, and a plain-language
  standing ("tied for best", "near-optimal — 10 points above the best", …); the scorecard shows the
  percentile, score-distribution histogram, and the shuffle breakdown.
- **Sections / Faculty** toggle — per-section grids, or every faculty member's weekly schedule;
  click any teacher card or class cell to open their **personal courses** drawer.
- **Print / PDF** and **CSV export** — for the full combination or a single faculty member.
- Section **preview filter** (all / I.Com / ICS / a single section) and teacher cross-highlighting.

> **Live solver vs offline pipeline.** The browser runs a hand-written two-stage backtracking
> solver (slot packing + day colouring) — a faithful JS port of the same constraint model. It is
> **not** OR-Tools CP-SAT (that C++ library cannot run in a browser); CP-SAT remains the offline
> reference in `cp_solver.py` and is what proves the optimal score of **560**.

### 2. Offline pipeline (Python, proven optimum)
Optional — the offline CP-SAT tooling still exists if you ever need the proven-optimal set
outside the browser. It **generates** its outputs on demand (nothing precomputed is committed):

```bash
pip install -r requirements.txt
python3 gen_all.py            # runs CP-SAT over many seeds → solutions.json
python3 export_xlsx.py        # builds timetables.xlsx (one sheet per combination)
python3 make_report.py        # builds compliance_report.md
```

---

## Files

| File | Purpose |
|---|---|
| `index.html` | **The functional website** — the client's UI design, wired to the real in-browser solver (`solver.js`) + the CP-SAT backend (`POST /generate`, same-origin on Vercel). |
| `solver.js` | JavaScript port of the constraint model — runs live in the browser. |
| `timetable-generator-UI-prototype.html` | The original UI prototype (mock-data demo) the client supplied — the design source. |
| `build_frontend.py` | Re-applies the functional wiring to the prototype (`python3 build_frontend.py [prototype.html]`). |
| `solver.py` | Python data model + (early) constructive solver. |
| `cp_solver.py` | **CP-SAT model** (OR-Tools) — the offline reference solver + `generate_ranked()` API entry point. |
| `gen_all.py` | Offline CP-SAT runner → regenerates `solutions.json` on demand. |
| `export_xlsx.py` | Offline: builds `timetables.xlsx` in the college's template layout. |
| `metrics.py`, `make_report.py` | Offline: shuffle metrics + `compliance_report.md`. |
| `test_solver.js` | Node test harness for `solver.js`. |

---

## Constraints honoured (confirmed with the client)

**From the course allocation sheet:** `-` = subject not offered in that section · Visiting-1/2/3 kept
as labels · ICS-I Section C included · "Economics/Statistics" (ICS-II-B) = either/or option block taught
in parallel rooms (both teachers engaged simultaneously).

**Faculty rules:**
Prof. Muhammad Naeem — Monday P1 & P2 free ·
Prof. Syed Assad Abbas — ICS fills P1 & P2 every day, Business Math in P3, no I.Com on Friday ·
Prof. Babar Jahangir — ICS fills P1 & P2 ·
Prof. Ishfaq Ahmed — P1 ≥ 4 days, never P5 ·
Prof. Dr. Yasir Kareem — only P1, P2, P4 ·
Prof. Abdul Basit — P1 ≥ 4 days, never P5, no fully-off day ·
Prof. Amir Rasheed & Prof. Husnul Amin — never P1, never P5 ·
Prof. Millat Khan — never P1 ·
Prof. Naeem Asghar — never P1, never P2 ·
Prof. Tanveer Ahmed — Thursday & Friday only, P1–P3.

**General instructions:** start 08:30 · 5 × 40-min periods · break 25 min after 3rd period · no subject
twice in a day · high-credit subjects anchored to one slot · Accounting vs Economics non-overriding in I.Com-I.

---

## Optional: run real CP-SAT behind the site (provably optimal)

The website also ships an optional **"Compute optimal (CP-SAT)"** button. Point it at the
FastAPI backend and it fetches the proven-optimal set (score 560) and merges it into the
ranked chooser (union — nothing is dropped).

**Hosting — Vercel (same platform as the frontend):** see `VERCEL_GUIDE.md`.
`api/index.py` + `vercel.json` deploy the CP-SAT solver as a Python serverless function
(1 vCPU / 2 GB / 300 s on Hobby). Note: Hobby is non-commercial.

The frontend defaults to **same-origin** `/generate` (works when the site and the `api/`
functions are deployed together on Vercel). To point at a separately-hosted backend, set
`window.IMPCC_API_URL` before the page scripts run (e.g. in the HTML head).

---

## Requirements

- **Website:** any modern browser (no dependencies).
- **Python pipeline:** Python 3.10+, `ortools>=9.10`, `openpyxl>=3.1` (see `requirements.txt`).
- **JS test harness:** Node.js 18+ (`node test_solver.js`).

---

## Faculty constraints as data + LLM translation

Faculty preferences are **not hard-coded** — they are data (see `constraints_schema.md` for the
full "system language"). A dedicated **⚙ Constraints** page lets you:

- view every faculty member's current rules (the college defaults ship in `default_constraints.json`),
- type a member's plain-language note and press **✦ Translate with AI** — the backend sends it to an
  OpenAI-compatible LLM and returns structured rules (with confidence + notes), which you review and **Apply**,
- download / upload `constraints.json`, or reset to defaults.

Edited constraints **immediately** affect the in-browser solver *and* the CP-SAT backend
(`POST /generate` accepts a `constraints` payload). To enable translation, set these on the backend
(Vercel → Settings → Environment Variables):

| Variable | Example |
|---|---|
| `LLM_API_KEY` | `sk-...` (OpenAI/Groq/OpenRouter key) |
| `LLM_BASE_URL` *(optional)* | `https://api.openai.com/v1` |
| `LLM_MODEL` *(optional)* | `gpt-4o-mini` |

The key stays **server-side** — the browser only calls `POST /translate`.

---

## Supabase: auth + cloud-synced allocation & constraints

A new **🗂 Allocation** page lets management edit the course allocation (teacher + weekly
periods per subject, 25 periods/section required). Allocation **and** constraints are
stored in **Supabase** per signed-in account, so changing devices keeps everything in sync.

- **Project:** `https://xdckubhqhglmorwmxtfs.supabase.co` (region ap-south-1) — table
  `public.workspace(user_id PK→auth.users, allocation jsonb, constraints jsonb, updated_at)`
  with RLS policies so each account only sees its own row.
- **Sign in / Create account** (top-right) uses Supabase Auth (email/password, auto-confirm on).
- When signed in: **Save** (allocation) and every constraint **Apply** upsert to Supabase;
  signing in on any device pulls the shared allocation + constraints back down.
- When signed out: everything still works, saved to localStorage only.
- Both solvers accept the live data: the in-browser generator and the CP-SAT backend
  (`POST /generate` with `sections` + `constraints` payloads).
- `supabase.js` is a dependency-free Supabase client (GoTrue + PostgREST via fetch) — the
  anon key is embedded (public by design; RLS protects data). The service-role key and the
  dashboard PAT are **not** committed.

> **Access model:** public signup is **disabled** — only authorized accounts can reach the
> Supabase-synced data. The admin account is created server-side (currently
> `admin@impcc.com`); additional accounts are added by an admin in Supabase → Authentication.

> **Resource protection:** the expensive backend features require sign-in. `POST /generate`
> (CP-SAT) and `POST /translate` (LLM) reject requests without a valid Supabase session
> (server-side `auth_check.py`); the in-browser JS generator stays free. The UI disables the
> CP-SAT button and blocks Translate until signed in.

---

## Faculty directory

A new **📇 Directory** page makes the faculty roster itself editable data (add, rename,
mark "left", re-activate, remove; each member is Permanent or Visiting). The **Allocation**
teacher pickers and the **Constraints** page both read from this directory, so they stay
consistent as faculty come and go. The roster syncs to Supabase (per signed-in account,
stored in `workspace.faculty`) and falls back to localStorage. Teachers who aren't in the
built-in list still render correctly everywhere — the solver treats their name as the
identity, and every timetable/faculty view falls back to the raw name.

> **Shared (published) data:** allocation, constraints and the faculty directory are a
> **global** state — the signed-in admin's saves are written to a public-read `published`
> table, and **every visitor (signed in or not) loads them on page load**. Generated
> timetable combinations are deliberately **not** shared (they stay per-device). Writes
> remain admin-only via RLS (`anon` can SELECT only).

> **Constraint edits:** constraints are now fully **add / edit / remove** — each rule on
> the Constraints page has ✎ and ✕ controls plus an "＋ Add rule" picker. The override
> model uses an `edits` map where `null` deletes a rule (even a default), so faculty
> preferences can be changed or dropped, not just added. Applying an LLM translation now
> **merges** into the edits instead of replacing the whole set (fixes a case where
> translating one rule silently dropped the others).

---

## Image (PNG → ZIP) exports

Beyond the per-section / per-teacher PNG buttons:

- **Department:** each stream header (I.Com / ICS) has a **ZIP** button — downloads all that
  department's section images, each named `IMPCC_<section>.png`.
- **Whole platform:** the **⇩ All sections (ZIP)** button downloads one zip containing two
  department folders (`I-Com/…`, `ICS/…`), each holding that department's section images.
- **All faculty:** the **⇩ Faculty images (ZIP)** button downloads a zip of every faculty
  member's personal schedule image (`IMPCC_personal-timetable_<name>.png`).

The ZIP is built in-browser with a dependency-free store-method writer (no compression needed
since the PNGs are already compressed) — validated against Python's `zipfile`.

---

## Save & Push timetables (admin-only)

- **💾 Save** (admin, signed-in only): stores the selected combination in the admin's
  account (`saved_timetables`, RLS owner-only). As many as you like; they follow you on
  every device you sign in on. Manage them under the **💾 Saved** tab — Load (bring back
  into the pool), Push, Delete.
- **📣 Push** (admin, signed-in only): publishes ONE combination to a public singleton
  (`pushed_timetable`, RLS public-read / auth-write). It is immediately **viewable on any
  device without signing in** (auto-loaded and selected on page load, marked 📣). Pushing
  another replaces the previous one.
- Saved/pushed combinations are full timetables (score + grids); generated pools stay
  per-device as before.
