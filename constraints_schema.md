# IMPCC — Faculty Constraint Schema (the "system language")

Every faculty preference is stored as **data**, not code. This document defines the exact
JSON vocabulary that (a) the LLM translates natural language into and (b) the solver enforces.

---

## 1. Top-level shape

Constraints are keyed by a stable **teacher code** (internal) with a display name attached:

```json
{
  "Basit": {
    "name": "Prof. Abdul Basit",
    "natural": "1st period must be engaged 4 days a week, last period must be free, no day must be completely off",
    "rules": { "...": "..." }
  }
}
```

- `name` — display name (shown in the UI).
- `natural` — the original natural-language statement (for auditability).
- `rules` — the structured constraints (section 2).

Teacher codes and their names live in `TEACHER_FULL` (`solver.js`); the full roster is:
`Sikhani, Naeem, UmairAbid, Rauf, Assad, Basit, Najam, Amir, Ehsam, Noor, Babar, Faisal,
Jilani, Yasir, Millat, Husnul, Ishfaq, NaeemAsghar, Tanveer, V1, V2, V3`.

---

## 2. Rule vocabulary

Slots: `P1 P2 P3 P4 P5` · Days: `MON TUE WED THU FRI` · Streams: `I.COM` / `ICS`.

### 2.1 Availability (most common — "faculty come and go")

| Key | Type | Meaning |
|---|---|---|
| `allowed_slots` | `["P1","P2","P4"]` | The ONLY periods they may teach. Overrides all defaults. |
| `forbidden_slots` | `["P5"]` | Periods they must never teach (e.g. "never the last period"). |
| `allowed_days` | `["THU","FRI"]` | The ONLY days they may teach (e.g. "only Thu & Fri"). |
| `forbidden_days` | `["FRI"]` | Days they must never teach. |
| `forbidden_slots_on_days` | `[{"days":["MON"],"slots":["P1","P2"]}]` | Combined day+slot ban (e.g. "Monday P1 & P2 free"). |

### 2.2 Engagement (how often they must teach)

| Key | Type | Meaning |
|---|---|---|
| `min_days_in_slot` | `[{"slot":"P1","min_days":4}]` | Must teach in that period on ≥N distinct days (e.g. "1st period engaged 4 days a week"). |
| `min_days_engaged` | `5` | Must teach on ≥N distinct days per week (`5` = "no completely free day"). |
| `max_periods_per_day` | `3` | Never teach more than N periods in a single day. |

### 2.3 Placement (subject / stream rules — advanced)

| Key | Type | Meaning |
|---|---|---|
| `subject_slots` | `[{"subject":"Business Mathematics","slots":["P3"]}]` | Pin a specific subject into specific periods. |
| `subject_forbidden_days` | `[{"subject":"Principles of Commerce","days":["MON"]}]` | Forbid a subject on specific days. |
| `stream_slots_required` | `[{"stream":"ICS","slots":["P1","P2"]}]` | Must occupy those periods in that stream (e.g. "ICS fills P1 & P2"). |
| `stream_forbidden_days` | `[{"stream":"I.COM","days":["FRI"]}]` | No classes of that stream on those days. |

---

## 3. The defaults (current college constraints, as data)

`default_constraints.json` in this repo is the same set the solver ships with. Example:

```json
{
  "Basit": {
    "name": "Prof. Abdul Basit",
    "rules": { "forbidden_slots": ["P5"], "min_days_in_slot": [{"slot":"P1","min_days":4}], "min_days_engaged": 5 }
  },
  "Tanveer": {
    "name": "Prof. Tanveer Ahmed",
    "rules": { "allowed_days": ["THU","FRI"], "allowed_slots": ["P1","P2","P3"] }
  }
}
```

---

## 4. Translation pipeline (natural language → this schema)

1. The user types/pastes the faculty member's **raw natural-language constraint** on the
   **Constraints** page.
2. The frontend `POST /translate` to the backend with `{ "text": "...", "teacher": "Prof. X" }`.
3. The backend sends the text to the LLM with a system prompt that:
   - defines the schema above (with the exact slot/day/stream vocabulary),
   - gives few-shot examples for every rule type,
   - requires it to return **only JSON** matching the schema,
   - maps synonyms to canonical keys ("must be free" → `forbidden_slots`, "only Thursday
     Friday" → `allowed_days`, "no day off" → `min_days_engaged: 5`, "must take 1st period
     4 days" → `min_days_in_slot`, …),
   - marks anything it cannot express with `unmapped` and explains why,
   - returns a `confidence` (0–1) and `notes`.
4. The backend **validates** the JSON against the schema, normalizes it, and returns it.
5. The user **reviews and approves**; the approved rules are saved (localStorage) and passed
   to the solver on every generation run.

### Example LLM exchange

Input: `"He can only come on Thursday and Friday, in the first three periods, and never the last period."`

Output:
```json
{
  "teacher": "Prof. Tanveer Ahmed",
  "natural": "He can only come on Thursday and Friday, in the first three periods, and never the last period.",
  "rules": {
    "allowed_days": ["THU","FRI"],
    "allowed_slots": ["P1","P2","P3"]
  },
  "confidence": 0.97,
  "unmapped": [],
  "notes": "Interpreted 'first three periods' as P1–P3; 'never the last period' is redundant with allowed_slots."
}
```

---

## 5. Solver behaviour

- `resolveConstraints(custom)` merges `DEFAULT_CONSTRAINTS` with the user's set, then every
  stage of the solver (slot domains, day domains, requirement groups, day-colouring, and the
  final validator) reads **only** from the merged rules.
- Editing or removing a rule therefore *immediately* changes generation — e.g. deleting
  `"forbidden_slots":["P5"]` for Prof. Basit lets him teach P5, and the validator no longer
  flags it.
- Unknown/unsupported rule keys are ignored with a warning (never silently enforced).


---

## 6. Overrides: add, modify, OR remove rules

A faculty override is an **edits map** keyed by teacher code:

```json
{ "Basit": { "name": "Prof. Abdul Basit",
             "edits": { "forbidden_slots": null,            // null = REMOVE this rule entirely
                        "min_days_engaged": 3,               // change a value
                        "forbidden_days": ["FRI"] } } }      // add a new rule
```

Merge rule (applied by `resolveConstraints` in both solvers):

    effective = defaults ∪ edits        (a null value deletes that rule key)

- `null` removes a rule even if it exists in the college defaults.
- Editing a key overwrites its value; omitting a key leaves the default untouched.
- A legacy override with `rules` (instead of `edits`) is treated as edits, so older
  saved data upgrades automatically and no longer wipes unrelated rules.
