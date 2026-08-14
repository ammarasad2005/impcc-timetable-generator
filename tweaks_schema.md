# IMPCC — Tweak Schema (manual adjustments: temporary & permanent)

Faculty come and go; a lecture may be cancelled, moved, or covered by someone else.
A **tweak** expresses such an adjustment as data, with a **time window**, so the system
can (a) apply it while it's relevant, (b) revert automatically when it expires, and
(c) re-optimize the timetable around it.

## 1. Case taxonomy (the "why")

**Temporary — a person:**
- "Prof. Naeem is on leave today / tomorrow / this week / Mon–Tue."
- "Prof. Basit can't make it for the first two periods on Friday."

**Temporary — a place / event:**
- "Computer lab unavailable this week." → block the lab subjects.
- "Exam on Wednesday." → block a whole section's day.

**Temporary — recurring (every week):**
- "Prof. Y has a meeting every Wednesday P4." → weekly slot block.

**Permanent:**
- "Prof. X has left the college." → permanent unavailability (then reassign their
  subjects in the Allocation page, or drop the subject).
- A permanent schedule change → that's a *constraint* edit (Constraints page), not a tweak.

## 2. Tweak JSON (the "system language")

```json
{
  "kind": "permanent" | "temporary",
  "window": { "type": "dates", "from": "2026-08-14", "to": "2026-08-16" },   // temporary only
  "recurring": false,                                   // true = every week
  "effect": {
    "type": "suspend_teacher" | "suspend_teacher_slots" | "block_section_slots",
    "teacher": "Prof. Muhammad Naeem",
    "section": "ICS-I-A",
    "slots": ["P1", "P2"],
    "days": ["MON", "TUE"]
  },
  "natural": "original plain-language statement",
  "notes": "interpretation note",
  "created_at": "…"
}
```

- `suspend_teacher` — the teacher teaches nothing on the window days.
- `suspend_teacher_slots` — the teacher is unavailable only in `slots` on `days`.
- `block_section_slots` — a whole section is free/blocked in `slots` on `days`
  (mapped to every teacher of that section).

## 3. The deterministic layer

An active tweak becomes a **constraint** at generation time:

| Tweak | Solver rule |
|---|---|
| suspend_teacher (day D) | that teacher → `forbidden_slots_on_days: [{days:[D], slots:[P1..P5]}]` |
| suspend_teacher_slots (D, S) | that teacher → `forbidden_slots_on_days: [{days:[D], slots:S}]` |
| block_section_slots (sec, D, S) | every teacher of that section → `forbidden_slots_on_days: [{days:[D], slots:S}]` |

The solver then **re-organizes the remaining timetable to the best valid combination**
while honouring those rules — e.g. a teacher absent on Monday simply has their subject's
periods redistributed to the other four days.

**Window evaluation:** a temporary tweak is *active* when today is inside `[from, to]`;
an expired tweak stops affecting generation automatically (the original timetable
returns). `recurring` tweaks are always active on their days. Permanent = always.

## 4. Manual cell edits (locks) + re-optimization

The admin can also edit the current timetable cell by cell. Each edit is a **lock**:

```json
{ "sec": "I.COM-I-A", "d": 3, "s": 0, "mode": "force" | "forbid",
  "subject": "English", "teacher": "Prof. Syed Umair Abid" }
```

- `force` — this cell must be exactly that subject+teacher.
- `forbid` — that subject+teacher must NOT be in this cell ("remove his lecture").

"Re-optimize" re-runs the solver keeping every lock, producing the **best possible valid
combinations** that respect the edits (sections stay full — a removed lecture is
redistributed, not deleted).

> **Note:** the timetable model fills all 25 periods per section (no built-in "study
> hall"). So "remove a lecture" means *reschedule it elsewhere* / *free the teacher*, not
> leave an empty slot. If a genuinely empty period is wanted (no cover available), that is
> an allocation change (lower the subject's weekly periods in the Allocation page).

## 5. Engaging the vacated slot (substitutes)

Redistribution moves the absent teacher's periods to other days. The **Engagement**
layer instead keeps the current timetable and finds an *engaging professor* (a
substitute) for each affected period — required when a teacher is away for a whole
day (redistribution of a 5/week subject is infeasible). A cover must have **no class
of his own in that slot**, must **satisfy his own constraints**, and coverage is
**maximised** (exact matching per day×period). See `engagement_schema.md`.

## 6. The semantic layer

`POST /translate-tweak` sends the plain-language statement to the LLM with this schema and
returns `{ kind, window, recurring, effect, natural, notes, confidence, unmapped }` —
mirroring the constraints translator. Relative dates ("today", "tomorrow", "this week")
are resolved server-side against the current date.
