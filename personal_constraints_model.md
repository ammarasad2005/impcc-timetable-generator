# Personal faculty-constraint kernel (v2)

*Normative spec — every deterministic cause a personal timetable preference can have.
Anything outside this table is honestly `unmapped` (never guessed).*

A teacher's placement space = set of **pieces** occupying **cells** `(day, slot)`
inside **sections** (each section has a population, a level, and a stream).

## 1\. Scope (optional on ANY entry)

`"scope": { "populations": [...], "streams": [...], "sections": [...], "days": [...] }`

* populations → entry applies only while solving those populations (a unit that
  teaches in both is affected while in the scoped pop's context).
* streams / sections → *cell* match: the teacher's piece is constrained/flagged
  only when placed into a section of that stream/key. Domain shrinks apply
  conservatively (the whole unit only when ALL its sections match the scope).
* days → entry applies only on those days ("some xyz days" vs "throughout the
  week" = omit `days`). For window kinds that already carry `days`, list scoping
  and window days intersect.
* An omitted axis = no restriction (backward compatible: today's entries keep
  current semantics exactly).

## 2\. Hard availability masks — piece cells may/may-not land

| key | shape | semantics |
| --- | --- | --- |
| `allowed_days` | `[D]` | piece days ⊆ D |
| `forbidden_days` | `[D]` | piece days ∌ D |
| `allowed_slots` | `[P]` | piece slots ⊆ P |
| `forbidden_slots` | `[P]` | piece slots ∌ P |
| `forbidden_slots_on_days` | `[{days,slots}]` | cells ∌ union of (days×slots) windows |
| `allowed_slots_days` | `[{days,slots}]` | cells ⊆ union of (days×slots) windows **(positive allow ∀)** |
| `allowed_days_in_stream` | `[{stream,days}]` | cells in stream: days ⊆ |
| `stream_forbidden_days` | `[{stream,days}]` | cells in stream: days ∌ *(was display-only → fixed)* |
| `allowed_slots_in_stream` | `[{stream,slots,days?}]` | cells in stream: slots ⊆ P on those days (days = week if omitted) |
| `stream_slots_required` | `[{stream,slots,days?}]` | each listed slot must be occupied in that stream |
| `allowed_slots_in_sections` | `[{sections,slots,days?}]` | cells in listed sections: slots ⊆ P on days |
| `allowed_days_in_sections` | `[{sections,days}]` | cells in listed sections: days ⊆ D |
| `allowed_sections` | `[K]` | ALL of the teacher's pieces land only in sections K |
| `forbidden_sections` | `[K]` | no piece in sections K |
| `subject_slots` | `[{subject,slots,days?}]` | pieces of subject: slots ⊆ P (days-limited if given) |
| `subject_forbidden_days` | `[{subject,days}]` | pieces of subject: days ∌ D |
| `subject_days_allowed` | `[{subject,days}]` | pieces of subject: days ⊆ D |
| `subject_slot_days` (alias →) `subject_slots_days` | `[{subject,slots,days}]` | pieces of subject: cells ⊆ windows (hard pin; singular kept as sugar) |

## 3\. Deterministic counts

| key | shape | semantics |
| --- | --- | --- |
| `min_days_engaged` | `int` | ≥ N distinct days with ≥1 piece |
| `min_days_in_slot` | `[{slot,min_days}]` | ≥ N days occupy that slot |
| `max_days_in_slot` | `[{slot,max_days}]` | ≤ N days occupy that slot |
| `max_periods_per_day` | `int` or `[{max,days?,stream?,sections?}]` | ≤ N pieces/day (scoped variant counts only matching cells) *(was display-only → fixed)* |
| `min_periods_per_day` | `int` or `[{min,days?,stream?,sections?}]` | ≥ N pieces/day (same scoping) |
| `max_pieces_match` | `[{max,subject?,subjects?,stream?,sections?,slot?,days?}]` | **quota:** ≤ N matching pieces per week |
| `min_pieces_match` | `[{min,...}]` | ≥ N matching pieces per week |

## 4\. Structure

| key | shape | semantics |
| --- | --- | --- |
| `allow_same_subject_same_day` | `bool` | the teacher's own units may double a day (opts out of the inter no-double rule) *(was display-only → fixed)* |
| `no_daily_gaps` | `bool` | per day, the teacher's occupied slots form one contiguous run |

## 5\. Soft preferences (penaltyized, never forbidden)

| key | shape | semantics |
| --- | --- | --- |
| `soft_prefer_free_slots` | `[P]` | +penalty per occupied listed slot |
| `soft_prefer_free_slots_days` | `[{days,slots}]` | +penalty per occupied window |
| `soft_even_distribution` | `bool` | +penalty per period above the even per-day share |
| `soft_compact_days` | `bool` | +penalty per gap inside the daily run (soft twin of `no_daily_gaps`) |

## 6\. Deterministic phrase mapping (translation table)

The LLM maps statements *mechanically*; anything unlisted → `unmapped`.

| example phrasing | key / entry |
| --- | --- |
| "never 5th period" / "no last period" | `forbidden_slots: [P5]` |
| "only 1st–3rd periods" | `allowed_slots: [P1,P2,P3]` |
| "never on Friday" | `forbidden_days: [FRI]` |
| "only Thursday and Friday" | `allowed_days: [THU,FRI]` |
| "Monday first two periods free" | `forbidden_slots_on_days` |
| "use only 3rd–5th periods on Fridays" / "arrange his 3,4,5 periods" | `allowed_slots_days` |
| "arrange his 3,4,5 periods in ICS and I.Com" | `allowed_slots_in_stream` ×2 entries |
| "…only in BSAF sections" (slots) | `allowed_slots_in_sections` |
| "his classes may only be in ICS-II-A/B" | `allowed_sections` |
| "BM always 3rd period" (period pin) | `subject_slots` |
| "BM 3rd period only on Mon and Tue" | `subject_slots_days` |
| "PoE only Mon–Wed" | `subject_days_allowed` |
| "never PoE on Friday" | `subject_forbidden_days` |
| "1st period engaged ≥ 4 days" | `min_days_in_slot` |
| "last period at most 2 days a week" | `max_days_in_slot` |
| "never more than 3 classes in a day / only on Friday" | `max_periods_per_day` (scoped) |
| "at least 2 classes every teaching day" | `min_periods_per_day` |
| "no day completely off" | `min_days_engaged: 5` |
| "at most 2 Economics classes in I.Com per week" | `max_pieces_match` |
| "keep 3 of his classes in ICS" | `min_pieces_match` |
| "doubles allowed for me" | `allow_same_subject_same_day` |
| "no gaps between my periods in a day" | `no_daily_gaps` (hard) · `soft_compact_days` (soft) |
| "prefer P3 free" | `soft_prefer_free_slots` (+`_days` window form) |
| "spread my week evenly" | `soft_even_distribution` |

Everything else (seating, room wishes, story-level context) → `unmapped`.

## 7\. Implementation map (kernel parity)

One shared deterministic checker implements every kind; engines consume it:

| engine | enforcement | checker |
| --- | --- | --- |
| `context_model.py` `teacher_rule_findings` | — | source of truth (Python) |
| `context_model.evaluate` | adapter: soft→violations, hard→issues | walker |
| `context_model.analyze_structured` | adapter: hard→`facrule@{code}:{rule_key}` tickets (uids+cells) | walker |
| `cp_solver.build_from_context` | CP-SAT: domains + per-cell masks + count channels + gap triples | — |
| `context_solver.js` (browser) | heuristic search; hard kinds gate via evaluate | JS walker mirror |
| `solver.js` (classic page) | heuristic search | JS classic port |
| `llm_translate.py` | RULE_SPEC + phrase table (this doc's §6 in the prompt); unknown keys dropped with warnings | shape validators |

Semantics are defined CELL-PER-SECTION (a combined unit contributes one cell
per section). Positive windows (`allowed_slots_days`) are COVER-ALL: a piece
must land inside the union of same-scope windows. Entries in the same kind
with equal scope signatures UNION; entries with different scopes group by
scope signature. Per-entry `scope = {populations?, streams?, sections?, days?}`
intersects with the entry's own `days`. Multi-section (combined) units use
the conservative all-sections-match reading for section/stream scope;
single-section units match the checker exactly.
