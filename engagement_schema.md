# IMPCC — Engagement (substitute covers for unavailable slot holders)

When a **slot holder is unavailable** (a teacher is away for a whole day, or for a
specific time duration), the college must **"engage" that slot** — put another
professor into the class. This document describes the deterministic **engagement
engine** that computes those covers.

## 1. The two cases

| Case | Tweak | Meaning |
|---|---|---|
| Away the **entire day** | `suspend_teacher` (`days` only) | every one of his periods that day needs a cover |
| Away for a **time duration** | `suspend_teacher_slots` (`days` + `slots`) | only those specific periods need a cover |

An unavailable teacher is blocked **only in his own window**: a teacher who is away
Monday P3 can still cover Monday P1; a teacher away all Monday can still cover Tuesday.

## 2. What the engine guarantees (for every cover)

For each affected cell `(section, day, period)` the **engaging professor** must:

1. **not be the slot holder**, and **not be unavailable himself** at that day+period;
2. **have no class of his own in that slot** — he must be free at that day+period in
   the current timetable (no double-booking); and
3. **satisfy his own constraints** for that day+period:
   - `allowed_slots` / `forbidden_slots`,
   - `allowed_days` / `forbidden_days`,
   - `forbidden_slots_on_days`.

Rules about his *own* teaching pattern (`min_days_in_slot`, `min_days_engaged`,
`subject_slots`, `stream_slots_required`, `subject_forbidden_days`) are **not**
applied to a one-off cover — they describe his weekly load, not his availability.

## 3. Assignment = exact maximum matching

A professor can only be in **one room at a time**, so within a single `(day, period)`
position the covers form a bipartite matching between the affected cells and the
eligible professors. The engine computes an **exact maximum matching per position**
(Kuhn's augmenting-path algorithm), so coverage is provably maximised; any cell with
no eligible professor is reported honestly in `uncovered` (never double-booked).

Positions are processed day-by-day and the **less-loaded** professors are preferred,
so the cover load is spread across the faculty.

## 4. API

`IMPCC_SOLVER.engage(timetable, R, unavailable, opts)` → plan object.

- `timetable` — the `toTimetable()` form: `{ section: 5×5 grid of [subject, teacher] }`.
- `R` — resolved constraints (defaults if omitted).
- `unavailable` — `[{ teacher, days?, slots? }]` (strings or 0–4 indices; omitted = all).
- `opts.roster` — optional substitute pool (replaces the default roster); the UI
  passes the faculty directory.

Returns:

```json
{
  "affected":    [ { "sec","d","s","subj","teacher","codes" } ],
  "assignments": [ { "sec","d","s","subj","teacher","cover","coverCode" } ],
  "uncovered":   [ { "sec","d","s","subj","teacher" } ],
  "covered": 3, "total": 3, "load": { "V1": 1, ... }
}
```

`IMPCC_SOLVER.validateEngagement(timetable, R, assignments, unavailable)` re-checks
all three rules and returns a list of violations (empty = valid).

## 5. How it fits the app

- The **Engagement tab** shows the plan for the currently selected combination,
  derived from the active `Teacher away` tweaks, with a summary (affected / engaged /
  no-cover), a day+period breakdown and a CSV export (`IMPCC_engagement-plan.csv`).
- On the **Sections grid**, cells that need a cover are ringed and badged with the
  cover's name (🟢 `👥 name`) or ⚠ `no cover`.
- **Engagement never modifies the timetable** — it is a pure overlay. It also does
  **not** regenerate; it answers "who covers Prof A's Monday P3 *in this timetable*".
- Tweaks are synced in the published cloud state, so the engagement plan follows the
  admin's tweaks across devices.

## 6. Why engagement exists alongside redistribution

A `suspend_teacher` tweak also feeds `forbidden_slots_on_days` into generation, which
*redistributes* the absent teacher's periods to other days. Redistribution is ideal
for permanent reschedules, but it **fails for full-day absences of a 5-period/week
teacher** (a 5/wk subject must occupy a slot on all five days — block Monday and only
4 days remain, so no valid timetable exists). Engagement covers exactly that gap:
keep the rest of the week untouched and cover the absent periods with substitutes.

## 7. Tests

- `node test_engagement.js` — 37 assertions: full-day, partial-duration, constraint
  filtering (Yasir/Amir/Tanveer/Millat/Husnul), no double-booking, scarcity, parallel
  block, load spreading, determinism, purity, absent-never-covers, 8-seed property sweep.
- `node test_engagement_fuzz.js` — 13 assertions: exact max-matching with a scarce
  pool, busy-pool skipping, constraint filtering, partial-window cover rules, dual
  block, plus ~300 randomized cases (valid + deterministic).
