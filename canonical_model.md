# IMPCC — Canonical Data Model

The college's timetable data as **one canonical dataset** (`data/canonical.json`,
mirrored to the browser as generated `data.js`). Every admin surface (the
structured UI forms) reads and writes this model; the solvers consume it through
adapters. This document defines the schema.

The dataset was seeded **once** from the college's source files
(`Intermediate-Allocation-2026-27-Ist Shift-1.xlsx`, `BS Course Allocation.xlsx`);
from that point on the data lives in the system and evolves through the UI +
Supabase (the Excel files are not a recurring format). Regenerate `data.js`
after editing the JSON: `python3 tools/gen_data_js.py`.

## 1. Top-level shape

```json
{
  "version": 1,
  "subjects":   ["Commerce", "English", ...],
  "faculty":    [ {"code", "name", "level", "aliases"} ],
  "populations": {
    "inter-1":  { "sections": [ ... ] },
    "bs-1":     { "sections": [ ... ] },
    "inter-2":  { "sections": [ ] }
  },
  "parallelGroups":   [ ... ],
  "combinedClasses":  [ ... ],
  "constraints":      { "<code>": {"name", "rules", "natural"} },
  "generalInstructions": { "inter-1": [...], "bs-1": [...], "inter-2": [...] }
}
```

Populations: `inter-1` + `bs-1` share shift 1 (**one solver domain** — a teacher
may teach both levels in shift 1, so their schedule must not clash across
levels); `inter-2` is shift 2, an operationally independent system. Schedule
parameters (active days/periods, start times incl. the 2nd-shift Friday 14:00
override, break positions) live in the population registry
(`populations.js` / `timetable_config.py`, PR-1).

## 2. Faculty directory

```json
{ "code": "Tanveer", "name": "Prof. Tanveer Ahmed",
  "level": "both", "aliases": ["Prof. Tanvir Ahmed"] }
```

- `code` — the stable internal identifier (shared with the solvers).
- `level` — `"inter"` | `"bs"` | `"both"` | `null` (unknown). Informational for
  the directory; constraints are **person-level** (apply wherever the person
  teaches), per the confirmed decision.
- `aliases` — every spelling variant found in the sources. Alias resolution is
  deterministic: the UI's name autocomplete and the adapters resolve any alias
  to the one canonical entity — duplicates are impossible by construction.

44 members. Codes for pre-existing members match the solvers' built-in roster;
new members register via `IMPCC_SOLVER.extendTeachers()` / `solver.extend_teachers()`.

## 3. Subject → Course → Offering

**Subject** is the category (the college's own controlled vocabulary, 16
entries — the union of the Inter Subject column and the BS sheet's dropdown).
**Course** is the specific taught course ("Principles of Accounting",
"AF-121 Introduction to Commerce"). An **offering** places a course with a
faculty member in a section:

```json
{ "course": "Fundamentals of Accounting", "courseCode": "AF-122",
  "subject": "Commerce", "teacher": "Irfan", "periods": 4,
  "category": "Major", "subcat": "CRC", "ch": 3,
  "parallelGroup": null, "combinedWith": null }
```

- Inter sections: `key` (`I.COM-I-A`), `label`, `program` (`I.COM`/`ICS`), `year`.
- BS classes: `key` (`BSAF-SEM-I`), `program` (`BSAF`/`BSCM`/`BBA`), `semester`
  (`I`/`III`/`VII` — odd semesters run in fall). BS extras: `courseCode`,
  `category` (Major/General/ID/CP), `subcat`, `ch` (credit hours).
- **Partial fill**: BS classes occupy 18–24 of the 25 active cells (free cells
  become "Library Work" per the BS rules; first/last active periods must stay
  occupied). BS SEM-I classes fill all 25 (QR Math + Stat both count).
  Inter sections fill all 25.

## 4. Course relationships

Two structural relationships link courses (both are data; solvers enforce them
from PR-3 on):

### 4.1 Parallel groups — either/or blocks

```json
{ "id": "ics2b-econ-stat", "course": "Economics/Statistics", "periods": 4,
  "sections": ["ICS-II-B"], "teachers": ["Haroon", "Ishfaq"] }
```

Students choose ONE stream; both teachers are occupied simultaneously (two
rooms); the section grid uses `periods` cells **once**. Exactly one group
exists: ICS-II-B Economics/Statistics (Haroon | Ishfaq, 4/wk).

> Resolved interpretation: the BS **Quantitative Reasoning-I** 4a/4b pair is
> **NOT** a parallel group — both courses are compulsory (see 4.2).

### 4.2 Day-exclusive pairs — compulsory courses that never share a day

```json
{ "id": "qr1-math-stat",
  "courses": ["Quantitative Reasoning-I (Math)", "Quantitative Reasoning-I (Stat)"],
  "softConsecutiveDays": true }
```

QR-I Math (Najam, 2/wk) and QR-I Stat (Tanveer, 2/wk) are **both compulsory**
for every BS SEM-I class: Math runs on 2 days, Stat on 2 days, and the pair
**never shares a day** (hard rule — a day with one contains none of the other).
Each course preferably sits on two **consecutive** days (soft preference).
Both courses count toward the section grid normally, so SEM-I classes fill
all 25 cells. The rule applies to every section offering both courses.

## 5. Combined classes

```json
{ "id": "cc-fr1", "teacher": "Nehal",
  "a": {"section": "BSAF-SEM-VII", "course": "Financial Reporting-I"},
  "b": {"section": "BSCM-SEM-VII", "course": "Advanced Accounting Problems-I"} }
```

The four instructed BSAF-VII × BSCM-VII pairs: one teacher, one room, both
classes, identical slots. Both sections' entries carry `combinedWith: <id>`.

## 6. Faculty constraints (person-level)

Keyed by teacher code, the existing rule vocabulary (`constraints_schema.md`)
plus extensions enforced by the solver from PR-3 on:
`subject_slot_days` (subject pinned to a slot on specific days),
`soft_even_distribution`, `soft_prefer_free_slots`, `allow_same_subject_same_day`.
The `natural` array preserves the college's original statements verbatim —
traceability from structured rule back to source text.

## 7. General instructions (per population)

Structured rules with the natural text preserved:

```json
{ "id": "gi-i1-bmfri", "type": "subject_forbidden_days", "enabled": true,
  "params": {"subject": "Business Mathematics", "days": ["FRI"], "scope": "I.COM"},
  "natural": "Classes on Friday: Business Mathematics in I.Com must not be set on Friday" }
```

Rule types: `no_same_subject_same_day` · `same_subject_same_day_allowed` ·
`avoid_shuffling` (the score) · `non_overriding` · `consecutive_days_for_2pw` ·
`subject_forbidden_days` · `section_off_days` · `first_last_period_occupied`
(+ Library Work labeling) · `combined_classes` · `soft_individual_spread`.
Schedule parameters are NOT instructions — they live in the population configs.
The admin UI for these (structured editors + NL translate) arrives with the GI
page; the data shape is final.

## 8. Adapters (canonical → solvers)

`canonical.js` / `canonical.py`:
- `solverAllocation(population)` — the external allocation form with full
  display names (parallel pairs render "A / B"); solvers resolve names→codes
  (after `extendTeachers`/`extend_teachers` registered the directory).
- `solverConstraints()` — the constraints edits-model form.
- `sectionFill`, `teacherLoad(code, populations)` — grid-fill and load analysis
  (either/or groups count for every member teacher; combined classes count
  once per group; day-exclusive pairs count normally for both courses).

Solving the **new** dataset (partial fill, new rules, generalized parallel
groups) is the solver-extension PR; until then the solvers' built-in defaults
(the previous dataset) remain the live path and the regression fixture
(proven optimum 560).

## 9. Solving the canonical model (PR-3)

`canonical.solver_context(populations)` builds a **solve context** for one shift
(shift 1 = `["inter-1", "bs-1"]` solved jointly — one solver domain, cross-level
teachers cannot clash; shift 2 = `["inter-2"]`, operationally independent).
`context_model.context_to_model(ctx)` transforms it into the unit model:
combined pairs become **dual-section units** (one teacher, one room, both
sections, identical cells), parallel groups become group units (all member
teachers occupied), day-exclusive pairs link per section.

`cp_solver.generate_context(ctx)` solves with CP-SAT:

- **General piece encoding** — every piece has an independent slot var; days
  stay distinct per unit. Splitting a 5/wk or 4/wk course across slots is
  structurally allowed (BS sections can hold more 4/wk courses than period
  columns; day+slot bans can make full-column monopolies infeasible) — the
  shuffle tiers in the objective (100000/10000/100/10) keep single-slot forms
  strongly preferred whenever feasible. Parallel groups are pinned to ONE slot.
- **Hard rules** encoded: off-days, teacher availability (slots/days/day+slot
  bans), stream-scoped availability (Tanveer's I.Com Thu/Fri P1–P3),
  subject placement (`subject_slots`, `subject_forbidden_days`,
  `subject_slot_days`), engagement minimums (distinct-day semantics),
  `stream_slots_required` (≥4 distinct days per slot), inter 2/wk consecutive
  days, day-exclusive pairs, BS first/last period occupied, section loads,
  teacher non-overlap across ALL sections of the shift, non-overriding,
  same-subject-same-day (inter only).
- **Soft rules** (the `soft` list per constraint entry) are excluded from hard
  domains and become objective penalties; Babar's P5-free and Millat's P1-free
  are soft-marked (physically infeasible as hard with the current loads) —
  every solution documents these violations. Soft preferences
  (`soft_prefer_free_slots`, `soft_even_distribution`, individual spread,
  QR consecutive days) are penalized in the objective too.
- Every solution is re-checked by `context_model.evaluate` — hard `issues`
  reject; soft `violations` are **documented per combination** (rule, detail,
  penalty) and summed into `total = shuffle + penalty`. Ranking: fully-valid
  first, then by total.
- `context_model.pool_selection(solutions)` implements the pool rule:
  ≥25 valid → top 25 · 10–24 valid → all valid · <10 valid → pad to 10 with
  the best documented violators.

The old single-population path (`generate_ranked` / `POST /generate`) is
untouched and still proves the old dataset's optimum of 560. The new dataset's
optimum is inherently larger (some 5/wk splitting is structurally forced by
Naeem's Monday P1/P2 ban interacting with the I.COM-II column space) — the
score compares solutions within the dataset, not against 560.

New endpoint: `POST /generate-context` (auth-gated) —
`{populations, time_limit, n_seeds, max_solutions}` → ranked solutions with
`score`, `penalty`, `violations`, `total`, and per-section timetables ("Library
Work" fills free BS cells).

## 10. The in-browser engine (PR-3b)

`context_solver.js` mirrors the context stack in the browser
(`IMPCC_CONTEXT_SOLVER`): `contextToModel`, `evaluate`, `shuffleScore`,
`poolSelection`, `modelToTimetable` are exact ports — verified against the
Python implementation on a CP-SAT solution fixture (identical penalty,
violation multiset and shuffle score). `canonical.js` gains
`solverContext(populationIds)` (the mirror of `solver_context`).

The in-browser SEARCH is a two-stage randomized engine: stage 1 packs each
section's columns on the fly (global teacher capacities, per-unit slot budgets
for tight teachers — randomized top-down allocation with engagement-group
awareness — and group pruning inside the generation DFS), stage 2 colors days
per slot with unit/section/teacher/pair/consecutive/engagement constraints.
**Status: best-effort.** The full shift-1 dataset (7 teachers at 80–88% slot
utilization) sits at the edge of heuristic feasibility — the reliable
generation path for it is the CP-SAT backend (`POST /generate-context`).
The JS engine handles lighter contexts (verified on the I.COM-II trio and
synthetic contexts) and keeps improving.
