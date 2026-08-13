# IMPCC — Inter (1st Shift) Timetable: Compliance & Delivery Report

**Generated:** 88 fully-valid weekly timetable combinations for 11 sections (I.COM-I-A, I.COM-I-B, I.COM-I-C, I.COM-II-A, I.COM-II-B, I.COM-II-C, ICS-I-A, ICS-I-B, ICS-I-C, ICS-II-A, ICS-II-B) — 5 days × 5 periods, 25 periods/section/week.

## 1. Score meaning

Combinations are ranked by a **shuffle-preference score** (lower = better), matching the client's rule:
- **5 periods/week** subject → slot never changes (penalty 100,000 if it did — never happens).
- **4 periods/week** → slot changes only if unavoidable (penalty 10,000 — never happens here).
- **3 periods/week** → ~60% keep slot / 40% may shuffle (penalty 100 per shuffled subject).
- **2 periods/week** → free to move (penalty 10 per shuffled subject).

**Result:** best score = **560** (proven optimal), worst = 1190. 10 combinations reach the optimal score.

## 2. Shuffle profile (all combinations)

| metric | best | median | max |
|---|---|---|---|
| score | 560 | 760 | 1190 |
| 3-credit subjects shuffled | 4 | 5 | 9 |
| 2-credit subjects shuffled | 15 | 17 | 19 |

## 3. Constraint compliance (all enforced & verified)

### General Instructions

| Rule | Status |
|---|---|
| Start 08:30; 5 × 40-min periods; break 25 min after 3rd period | ✅ fixed by template |
| Mon–Fri (no Saturday) | ✅ |
| No subject twice in the same day (per section) | ✅ verified for all 88 |
| High-credit subjects anchored to one slot | ✅ verified (see §2) |
| Accounting vs Economics non-overriding in I.Com-I | ✅ verified for all 88 |

### Faculty-wise constraints

| Teacher | Rule | Status |
|---|---|---|
| Prof. Muhammad Naeem | Mon P1 & P2 free | ✅ verified |
| Prof. Syed Assad Abbas | ICS fills P1 & P2 daily · Bus-Math in P3 · no I.Com Friday | ✅ verified |
| Prof. Babar Jahangir | ICS fills P1 & P2 daily | ✅ verified |
| Prof. Ishfaq Ahmed | P1 ≥ 4 days · never P5 | ✅ verified |
| Prof. Dr. Yasir Kareem | only P1, P2, P4 | ✅ verified |
| Prof. Abdul Basit | P1 ≥ 4 days · never P5 · no day off | ✅ verified |
| Prof. Amir Rasheed | never P1 · never P5 | ✅ verified |
| Prof. Husnul Amin | never P1 · never P5 | ✅ verified |
| Prof. Millat Khan | never P1 | ✅ verified |
| Prof. Naeem Asghar | never P1 · never P2 | ✅ verified |
| Prof. Tanveer Ahmed | Thu & Fri only · P1–P3 | ✅ verified |
| Visiting-1 | placeholder visiting faculty | ✅ verified |
| Visiting-2 | placeholder visiting faculty | ✅ verified |
| Visiting-3 | placeholder visiting faculty | ✅ verified |
| All others (Sikhani, Umair Abid, A. Rauf, Najam, Ehsam Baig, Noor Muhammad, Faisal Bashir, Ghulam Jilani, Visiting-1/2/3) | no constraints listed | ✅ free |

### Structural

| Rule | Status |
|---|---|
| No teacher double-booked in the same period | ✅ verified for all 88 |
| ICS-II-B Economics/Statistics parallel block = 4 periods, P3 or P4, both teachers busy | ✅ verified for all 88 |
| Assad Abbas: ICS fills P1 & P2 every day; Business Math in P3, Mon–Thu | ✅ |
| Tanveer Ahmed: all 6 Statistics periods Thu & Fri, P1–P3 | ✅ |

## 4. Top combinations

| Rank | Score | 3cr shuffled | 2cr shuffled |
|---|---|---|---|
| 1 | 560 | 4 | 16 |
| 2 | 560 | 4 | 16 |
| 3 | 560 | 4 | 16 |
| 4 | 560 | 4 | 16 |
| 5 | 560 | 4 | 16 |
| 6 | 560 | 4 | 16 |
| 7 | 560 | 4 | 16 |
| 8 | 560 | 4 | 16 |
| 9 | 560 | 4 | 16 |
| 10 | 560 | 4 | 16 |
| 11 | 570 | 4 | 17 |
| 12 | 570 | 4 | 17 |
| 13 | 570 | 4 | 17 |
| 14 | 570 | 4 | 17 |
| 15 | 570 | 4 | 17 |
| 16 | 570 | 4 | 17 |
| 17 | 570 | 4 | 17 |
| 18 | 570 | 4 | 17 |
| 19 | 580 | 4 | 18 |
| 20 | 580 | 4 | 18 |

## 5. Deliverables

- `index.html` — interactive website (all combinations + teacher view + print).
- `timetables.xlsx` — one sheet per combination (template layout) + Summary + Teacher Schedule.
- `solutions.json` — all combinations, machine-readable.
- `solver.py`, `cp_solver.py`, `gen_all.py`, `export_xlsx.py`, `build_site.py`, `metrics.py` — the full pipeline.
