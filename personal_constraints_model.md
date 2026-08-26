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

## 8\. Hardness metric (per rule, per teacher) — v2.1

Every rule row carries an edit hardness `h ∈ {0..100}` that the admin can
slide; the AI translator infers the default from the statement's rigidity
keywords ("only" / "never" → 100; "preferably" → 30; "as much as
possible" → 20; "try to avoid" → 40 …).

| h | engine semantics |
| --- | --- |
| 100 | HARD: violating solutions are rejected (CP-SAT hard constraint; checker `issues`). |
| 1..99 | SOFT: violations are documented with penalty `base_penalty × h / 100` (rationale: halving hardness halves the cost of disobeying). |
| 0 | INACTIVE: kept as an annotation; engines skip it entirely (UI shows "off"). |

Wire format: a per-teacher `hardness` object maps rule key → int:

```json
"Tanveer": { "rules": { "allowed_days": ["THU","FRI"], "subject_slots": [{"subject":"Economics","slots":["P3"]}] },
             "hardness": { "allowed_days": 100, "subject_slots": 60 } }
```

Backward compatibility: a teacher entry with the legacy `soft: [keys]`
list and no `hardness` map behaves as if each listed key had hardness 50
and every other key hardness 100. `hardness` always wins when both are
present. All four engines (`cp_solver`, `context_model`, `context_solver.js`,
`solver.js`) read one shared helper semantics: `hardness_of(entry, key)`.

Soft-penalty bases: `rule`=5000, `preferFreeSlot`=500 (per hit),
`evenDistribution`=100 (per excess), mirroring the existing soft layer.
The bool soft kinds keep their bases; hard kinds demoted to h<100 report
against the `rule` base by default.

## 9. Course period-coherence (dominant-slot rule) — v3.1

An invariant orthogonal to personal rules, applying **to INTERMEDIATE-level
sections only**: inside ONE intermediate section, ONE course taught 3+
times a week must sit at (as near as possible) the SAME period every day.
It is checked jointly with each teacher's personal constraints (those stay
dominant — coherence never overrides an h=100 personal rule).

**BS-level scope (locked v3.1):** the whole entropy-minimisation concept
targets intermediate. For BS sections, slot alignment of a 3+/week course
is a bonus only ("if it can be done at any level, it's a plus — never a
requirement"): no floors, no tolerance checks, no documented violations,
no penalties. The solver still steers BS placement softly toward the
dominant slot (at the count-3 weight) so aligned BS solutions win the
ranking whenever they exist at equal cost; checkers stay silent on BS
groups.

| weekly count in an INTERMEDIATE section | floor | tolerance | semantics |
| --- | --- | --- | --- |
| 5 | 4 of 5 in one slot | ≤ 1 class elsewhere, documented soft | hard floor; the single tolerated deviation is charged soft so it is used only when genuinely needed |
| 4 | 3 of 4 in one slot | ≤ 1 class elsewhere, documented soft | same |
| 3 | none | all documented | SOFT only: every deviation from the dominant slot is charged at 65% of the rule base (the solver lines them up unless something else resists) |
| 1–2 | none | none | no check at all |

Grouping is per (section, course) pair: units teaching the same course in
that section are summed; for combined (multi-section) group units each
member section keeps its own course name, so each (sec, course) pair gets
its own dominant-slot constraint on its own piece times.

Penalties (added to the shared `pen` table):
`periodConsistency45` = 5000 × 90/100 = **4500** per class outside the
dominant slot (count 4–5, only reachable for the ≤-1 tolerance);
`periodConsistency3` = 5000 × 65/100 = **3250** per deviation (count 3,
unbounded but soft).

Checker messages (mirrored byte-identically by both JS engines):
- hard: `SEC course: N of C classes outside one period (dominant P1) — beyond the allowed 1 tolerance`
- soft 4/5: `SEC course: 1 class outside dominant period P1 (allowed at most 1)`
- soft 3: `SEC course: N of 3 classes outside dominant period P1`

CP-SAT encoding per group: one IntVar `ds` (dominant slot), per piece a
bool `same_p ⇔ (slot_p = ds)`; hard `Σ same_p ≥ count−1` for counts 4–5;
objective charges `(count − Σ same_p) × weight` in both tiers.

### 9.1 Structural exemption (locked)

The "without defying the teacher's personal constraint" clause makes the
hard floor relax to the STATICALLY ATTAINABLE alignment for each group:
`floor = count − max(1, count − attain)`, where `attain` is the maximum
over slots `s` of the sum-per-unit of `min(count_u, days_u)` with the
unit's personal slot/day domains (cp_solver._unit_slot_domain /
_unit_day_domain). Deviations up to `count − floor` are FORCED by the
personal claims and are never charged; anything beyond stays hard. When
the floor cannot reach 3 the group carries no hard constraint at all —
its placement is steered by the shuffle objective only.

### 9.2 Tier cascade (feasibility, locked) — v3.1

BS groups never carry floors (scope). When the remaining INTERMEDIATE
floors are jointly infeasible under teacher personal rules, the solver
walks the deterministic cascade: all inter floors → none, probes each
tier once (first-hit wins), caches the decision per full data signature,
and persists any dropped groups as `_cohExempt` on the context. A
dropped group's deviations become DOCUMENTED SOFT at
`periodConsistency45` per deviation — solid documentation of the
sanctioned infeasibility, never a silent release. Every dropped-group
deviation message reads:
`SEC course: N of C classes outside dominant period P1 (alignment infeasible — documented exception)`.

### 9.3 Engines

- cp_solver.build_from_context: BS (sec, course) groups never get hard
  floors — only bonus soft steering at `periodConsistency3` weight, and
  checkers never flag them. Inter groups keep hard floors; `coh_off`
  skips a group's hard floor (soft charge stays); generate_context runs
  the 2-tier cascade and stamps `context._cohExempt`.
- context_model.period_coherence_findings: shared by evaluate() and
  analyze_structured(); computes the same structural `attain` (lazy
  import of cp_solver's domain helpers) and applies the same floor
  relaxation — checker and solver can never disagree about the tier.
- context_solver.js periodCoherenceFindings: byte-identical mirror,
  including the `_cohExempt` documented-exception branch.
- solver.py + solver.js classic validate(): same hard messages and
  (soft)-prefixed tolerance notes on the classic grids.
