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
Open **`index.html`** in any modern browser. It generates combinations **live** using a JavaScript
port of the solver (`solver.js`) — there is **no pre-computed data** inside.

- **No cutoff, nothing hidden** — every distinct valid combination found is kept, shown in the
  chooser, and ranked by score. Generation is time-bounded (a batch ≈ 15 s); press
  **"Generate more"** to keep growing the set (it appends, never drops), or **"Stop"** to end early.
- **Combination** dropdown (plus ◀ ▶ navigation) — every solution is listed with its rank, score,
  and a plain-language description (e.g. *"tied for best"*, *"near-optimal — 10 points above the
  best"*). The panel above the grids repeats this with a percentile and the exact shuffle breakdown.
- **Sections / Teachers** toggle — view the grid per section, or every faculty member's weekly
  schedule alongside their personal constraint.
- **Print / PDF** — clean paper output for the college.

> **Live solver vs offline pipeline.** The browser runs a hand-written two-stage backtracking
> solver (slot packing + day colouring) — a faithful JS port of the same constraint model. It is
> **not** OR-Tools CP-SAT (that C++ library cannot run in a browser); CP-SAT remains the offline
> reference in `cp_solver.py` and is what proves the optimal score of **560**.

### 2. Offline pipeline (Python, proven optimum)
```bash
pip install -r requirements.txt
python3 gen_all.py            # regenerate solutions.json (CP-SAT, provably optimal)
python3 export_xlsx.py        # timetables.xlsx (one sheet per combination)
python3 make_report.py        # compliance_report.md
```

---

## Files

| File | Purpose |
|---|---|
| `index.html` | **Live** website (self-contained: solver + UI inlined). |
| `solver.js` | JavaScript port of the constraint model — runs in the browser. |
| `app.js` | Website UI (generation loop, views, print). |
| `build_site.py` | Inlines `solver.js` + `app.js` into `index.html`. |
| `solver.py` | Python data model + (early) constructive solver. |
| `cp_solver.py` | **CP-SAT model** (OR-Tools) — the offline reference solver. |
| `gen_all.py` | Runs CP-SAT over many seeds → `solutions.json`. |
| `export_xlsx.py` | Builds `timetables.xlsx` in the college's template layout. |
| `metrics.py`, `make_report.py` | Shuffle metrics + `compliance_report.md`. |
| `solutions.json` | 88 pre-computed combinations (best = 560, proven optimal). |
| `timetables.xlsx` | Excel: all 88 combos + Summary + Teacher Schedule. |
| `compliance_report.md` | Constraint checklist + ranking report. |
| `analysis_notes.md` | Working notes from the requirement-analysis phase. |
| `source_allocation.xlsx` | The original college input file (course allocations, instructions, faculty constraints, template). |
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

## Requirements

- **Website:** any modern browser (no dependencies).
- **Python pipeline:** Python 3.10+, `ortools>=9.10`, `openpyxl>=3.1` (see `requirements.txt`).
- **JS test harness:** Node.js 18+ (`node test_solver.js`).
