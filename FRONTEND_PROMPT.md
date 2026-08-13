# PROMPT — IMPCC Timetable Generator (Demo Prototype)

Build a **non-functional interactive demo** of a college timetable generator website. All behavior is **simulated with realistic mock data** — no real solver or backend. Controls must feel real: clicking updates the screen with plausible results. **You have total creative freedom over design** — I specify only functionality.

## Product context
Weekly class timetables for **Islamabad Model Postgraduate College of Commerce (H-8)** — **IMPCC** — **Intermediate, 1st shift**, streams **ICS & I.Com**.
- **11 sections:** I.COM-I (A,B,C), I.COM-II (A,B,C), ICS-I (A,B,C), ICS-II (A,B).
- **5 days** (Mon–Fri), **5 periods/day** (40 min), **break after the 3rd period**. Timings: P1 08:30–09:10 · P2 09:10–09:50 · P3 09:50–10:30 · Break 10:30–10:55 · P4 10:55–11:35 · P5 11:35–12:15.
- Every cell shows a **subject + teacher**. Placeholder teachers: **Visiting-1 / Visiting-2 / Visiting-3**.
- In **ICS-II (Section-B)** one cell is **"Economics / Statistics"** taught by **"Prof. Naeem Asghar / Prof. Ishfaq Ahmed"** (an either/or block taught in parallel rooms).

## Core concept
The site generates **many valid combinations, keeps all of them, and ranks them by a score**. **Score: lower = better** — it penalizes subjects moving between period-slots across the week (weights: 5/wk→100,000 · 4/wk→10,000 · 3/wk→100 · 2/wk→10). Proven best = **560**; typical results **570–580**. Show each combination's **numeric score, rank, and plain-language standing** ("tied for best", "near-optimal — 10 points above the best", "better than 85% of the others") plus a breakdown like "4 × 3/wk split · 16 × 2/wk split".

## Screens
1. **Sections view (default):** 11 section cards; each a grid of rows MON–FRI × columns Period-1/2/3/**Break**/Period-4/5. Break column visually distinct. I.Com vs ICS distinguishable. Cells show subject + teacher.
2. **Teachers view (toggle):** per-faculty cards with name, weekly period count, personal constraint, and a schedule list (Day · Period · Section · Subject). Constraint texts:
   - Muhammad Naeem — "Mon P1 & P2 free"
   - Syed Assad Abbas — "ICS fills P1 & P2 daily · Bus-Math in P3 · no I.Com Friday"
   - Babar Jahangir — "ICS fills P1 & P2 daily"
   - Ishfaq Ahmed — "P1 on 4+ days · never P5"
   - Dr. Yasir Kareem — "only P1, P2, P4"
   - Abdul Basit — "P1 on 4+ days · never P5 · no fully-free day"
   - Amir Rasheed — "never P1 · never P5"
   - Husnul Amin — "never P1 · never P5"
   - Millat Khan — "never P1"
   - Naeem Asghar — "never P1 · never P2"
   - Tanveer Ahmed — "Thu & Fri only · P1–P3"
   - Visiting-1/2/3 — "placeholder visiting faculty"

## Controls bar (persistent)
**Generate** · **Generate more / Stop** (one toggling button; results accumulate, nothing dropped) · **Compute optimal (CP-SAT)** · **combination dropdown** ("#2 · score 570 · tied for best") · **◀ ▶ arrows** · **Print/PDF** · **rank & score badges**.

## Status / feedback
- Live progress readout ("Live — 41 valid combinations · best score 570 · generating…").
- **Semantic ranking panel** (rank vs total, score, gap to best, percentile, shuffle breakdown).
- **CP-SAT status line** with 4 states: "running CP-SAT…" · "CP-SAT: proven optimal — best score 560" · "CP-SAT backend unreachable — using in-browser generation only" · "CP-SAT backend not configured".
- **Notes/help section**: what the score means, what the break is, what "Economics / Statistics" is, what Visiting-1/2/3 are, and that every combination satisfies all faculty and general constraints.

## Interaction flow (simulate)
1. Load → auto-generate with progress indicator.
2. ~20–40 mock combos appear (mostly 570–580, a few 760–900; best 570).
3. Dropdown/arrows switch the displayed timetable; badges + panel update.
4. "Generate more" appends & re-ranks; "Stop" ends early.
5. "Compute optimal" → brief loading → badge "proven optimal — best score 560" + merges a few mock solutions.
6. Print/PDF triggers the browser print dialog.
7. Sections/Teachers toggle keeps the selected combination.

## States to represent
Loading/generating · results · empty · backend unreachable / not configured (CP-SAT button only) · print-friendly.

## Future API contract (mock only)
- `GET /health` → `{"ok": true}`
- `POST /generate` body `{"time_limit":45,"n_seeds":2,"max_solutions":0}` → `{"solver":"cp-sat","solutions":[{"score":560,"timetable":{"I.COM-I-A":[["English","Prof. …"], …], …}}],"total_found":88,"optimal":true,"best_score":560,"meta":{"days":["MON","TUE","WED","THU","FRI"],"slots":["P1","P2","P3","P4","P5"],"section_order":["I.COM-I-A","I.COM-I-B","I.COM-I-C","I.COM-II-A","I.COM-II-B","I.COM-II-C","ICS-I-A","ICS-I-B","ICS-I-C","ICS-II-A","ICS-II-B"]}}`
- Each section timetable is 5 rows × 5 cells; the break is not a cell (it sits between cell index 2 and 3).

## Exclude
No real solving/backend/persistence · no login/auth · no design constraints.
