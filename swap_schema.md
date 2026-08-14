# IMPCC — Interactive Swapping (multi-cell, perfect circles)

Teachers sometimes **mutually swap their periods** — permanently or for a tenure. The
swap feature does this *without* re-optimizing the whole timetable: it is a local
permutation applied directly to the selected combination.

## 1. What a swap is

A swap is a set of directed moves — *"cell X → cell Y"* means the **teacher** at X goes
to Y's cell (sections and subjects stay with their cells). Moves form **chains and
circles**:

- **Perfect circle** (every cell gives and receives exactly once) → **0 disruptions**.
  e.g. *a takes c's place, c takes b's place, b takes a's place*.
- **Open chain** → leaves a **vacant** cell (head) and a **double-teacher** cell (tail)
  = 2 disruptions per chain.
- **Multiple circles** are allowed.

Disruptions also include **double-bookings** (a teacher landing on a period where they
already teach another class outside the swap). A teacher's own availability-rule
violations are reported as warnings.

`net disruptions = vacant + conflicts + double-bookings`.

## 2. Interaction (no live preview)

- **⇄ Swap** toggles swap mode (Sections view). Cells become draggable.
- **Drag** cell A onto cell B, or **tap** A then tap B. The move is recorded and
  disruptions are computed — but the grid **preview never changes**: only badges/rings
  animate (⇄ circle = green, ⚠ vacant/conflict = amber, →/← chain = gray).
- The HUD shows `⇄ N moves · disruptions M` live.
- **Apply swap**:
  - **net 0** → applies directly: teachers rotate along the circles, a new combination
    is created (the original stays in the pool), score unchanged.
  - **net ≠ 0** → a dialog shows *"Net disruptions: N — needs re-optimizing"* and a
    **targeted optimization** closes the chains with the fewest extra cells (maximum
    matching of displaced teachers to vacant heads, honouring constraints and avoiding
    double-bookings), bringing disruptions to 0.

## 3. Engine (solver.js)

- `swapAnalyze(moves)` — graph structure: chains, circles, vacant, conflicts.
- `swapEvaluate(timetable, moves, R)` — adds double-bookings + constraint violations.
- `swapApply(timetable, circles)` — rotates teachers (subjects unchanged).
- `swapComplete(timetable, moves, R)` — closes open chains via max bipartite matching.

All deterministic, all Node-tested (`test_swap.js`, 16 assertions; plus jsdom UI tests).

## 4. Integration

- A swapped combination is a normal combination (marked ⇄) — saveable, pushable, and a
  version remembers it via the `actions.swaps` snapshot.
- The shared PARALLEL block (dual teacher) is excluded from swaps.
