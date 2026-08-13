"""
IMPCC Inter timetable generator — CP-SAT model (OR-Tools).

Variables: every subject "unit" (section, subject, teacher, count) is split into
`count` pieces. Each piece has (slot, day). Constraints:
  - section: AllDifferent(keys) over its 25 pieces  -> exact cover of the 5x5 grid
  - unit:   AllDifferent(days)                       -> no subject twice in a day
  - teacher:AllDifferent(keys) over all its pieces   -> no double-booking
  - slot/day domains per teacher rules + special structure
Objective: minimize subject-slot shuffling (weighted by weekly credits).
"""
import random
import json
from collections import defaultdict
from ortools.sat.python import cp_model

from solver import UNITS, SECTIONS, TEACHER_FULL, ALLOWED, DAYS, SLOTS
from solver import validate, score, canonical

# which teachers' units are "big" (single slot, no split)
def slot_domain(u):
    t = u["teacher"]; subj = u["subject"]
    if t == "Naeem" and subj == "Principles of Accounting":
        return [2, 3, 4]
    if t == "Naeem" and subj == "Principles of Commerce":
        return [0, 1]
    if t == "Assad" and subj == "Business Mathematics":
        return [2]
    if t == "Assad" and subj == "Mathematics":
        return [0, 1, 3, 4]
    if t == "Ishfaq":
        return [0, 1, 2, 3]
    if t == "PARALLEL":
        return [2, 3]
    if t == "Tanveer":
        return [0, 1, 2]
    if t == "Basit":
        return [0, 1, 2, 3]
    return list(ALLOWED.get(t, [0, 1, 2, 3, 4]))

def day_domain(u):
    t = u["teacher"]; subj = u["subject"]
    if t == "Tanveer":
        return [3, 4]
    if t == "Assad" and subj == "Business Mathematics":
        return [0, 1, 2, 3]          # P3, never Friday
    if t == "Naeem" and subj == "Principles of Commerce":
        return [1, 2, 3, 4]          # never Monday (P1/P2 free)
    return [0, 1, 2, 3, 4]

def _eq_bool(m, a, val, name):
    v = m.NewBoolVar(name)
    m.Add(a == val).OnlyEnforceIf(v)
    m.Add(a != val).OnlyEnforceIf(v.Not())
    return v

def _neq_bool(m, a, b, name):
    v = m.NewBoolVar(name)
    m.Add(a != b).OnlyEnforceIf(v)
    m.Add(a == b).OnlyEnforceIf(v.Not())
    return v

def build():
    m = cp_model.CpModel()
    slot_of = {}     # unit -> (single slot var) for count>=4, else None
    piece_slots = {} # unit -> list of slot vars per piece
    piece_days = {}  # unit -> list of day vars per piece
    piece_keys = {}  # unit -> list of key vars per piece

    section_keys = defaultdict(list)
    teacher_keys = defaultdict(list)

    # special teacher alias for the parallel block
    for i, u in enumerate(UNITS):
        c = u["count"]
        sd = slot_domain(u)
        dd = day_domain(u)
        pieces = []

        if c == 5:
            s = m.NewIntVarFromDomain(cp_model.Domain.FromValues(sd), f"s_{i}")
            slot_of[i] = s
            for d in range(5):
                k = m.NewIntVar(0, 24, f"k_{i}_{d}")
                m.Add(k == s * 5 + d)
                pieces.append((s, d, k))
        elif c == 4:
            s = m.NewIntVarFromDomain(cp_model.Domain.FromValues(sd), f"s_{i}")
            slot_of[i] = s
            days = [m.NewIntVarFromDomain(cp_model.Domain.FromValues(dd), f"d_{i}_{p}") for p in range(4)]
            m.AddAllDifferent(days)
            for p in range(4):
                k = m.NewIntVar(0, 24, f"k_{i}_{p}")
                m.Add(k == s * 5 + days[p])
                pieces.append((s, days[p], k))
        elif c == 3:
            slots = [m.NewIntVarFromDomain(cp_model.Domain.FromValues(sd), f"s_{i}_{p}") for p in range(3)]
            days = [m.NewIntVarFromDomain(cp_model.Domain.FromValues(dd), f"d_{i}_{p}") for p in range(3)]
            m.AddAllDifferent(days)
            for p in range(3):
                k = m.NewIntVar(0, 24, f"k_{i}_{p}")
                m.Add(k == slots[p] * 5 + days[p])
                pieces.append((slots[p], days[p], k))
        else:  # c == 2
            slots = [m.NewIntVarFromDomain(cp_model.Domain.FromValues(sd), f"s_{i}_{p}") for p in range(2)]
            days = [m.NewIntVarFromDomain(cp_model.Domain.FromValues(dd), f"d_{i}_{p}") for p in range(2)]
            m.Add(days[0] != days[1])
            for p in range(2):
                k = m.NewIntVar(0, 24, f"k_{i}_{p}")
                m.Add(k == slots[p] * 5 + days[p])
                pieces.append((slots[p], days[p], k))

        piece_slots[i] = [p[0] for p in pieces]
        piece_days[i] = [p[1] for p in pieces]
        piece_keys[i] = [p[2] for p in pieces]

        section_keys[u["sec"]].extend(piece_keys[i])
        teacher_keys[u["teacher"]].extend(piece_keys[i])
        if u["teacher"] == "PARALLEL":
            teacher_keys["Ishfaq"].extend(piece_keys[i])
            teacher_keys["NaeemAsghar"].extend(piece_keys[i])

    # section coverage
    for sec in SECTIONS:
        m.AddAllDifferent(section_keys[sec["key"]])
    # teacher non-overlap
    for t, keys in teacher_keys.items():
        if len(keys) >= 2:
            m.AddAllDifferent(keys)

    # ---- structural: early-slot fill rules ----
    math_units = [i for i, u in enumerate(UNITS)
                  if u["teacher"] == "Assad" and u["subject"] == "Mathematics"]
    cs_units = [i for i, u in enumerate(UNITS)
                if u["teacher"] == "Babar" and u["subject"] == "Computer Science"]
    ish_units = [i for i, u in enumerate(UNITS)
                 if u["teacher"] == "Ishfaq"]
    basit_units = [i for i, u in enumerate(UNITS)
                   if u["teacher"] == "Basit"]

    m.Add(sum(_eq_bool(m, slot_of[i], 0, f"as_p1_{i}") for i in math_units) >= 1)
    m.Add(sum(_eq_bool(m, slot_of[i], 1, f"as_p2_{i}") for i in math_units) >= 1)
    m.Add(sum(_eq_bool(m, slot_of[i], 0, f"bb_p1_{i}") for i in cs_units) >= 1)
    m.Add(sum(_eq_bool(m, slot_of[i], 1, f"bb_p2_{i}") for i in cs_units) >= 1)
    m.Add(sum(_eq_bool(m, slot_of[i], 0, f"is_p1_{i}") for i in ish_units) >= 1)
    m.Add(sum(_eq_bool(m, slot_of[i], 0, f"bs_p1_{i}") for i in basit_units) >= 1)

    # Basit: engaged every day
    for d in range(5):
        m.Add(sum(_eq_bool(m, day, d, f"bs_d{d}_{i}_{p}")
                  for i in basit_units for p, day in enumerate(piece_days[i])) >= 1)

    # ---- objective: minimize shuffling ----
    obj = []
    for i, u in enumerate(UNITS):
        c = u["count"]
        if c == 3:
            for p in range(3):
                for q in range(p + 1, 3):
                    obj.append(_neq_bool(m, piece_slots[i][p], piece_slots[i][q], f"ne3_{i}_{p}_{q}") * 100)
        elif c == 2:
            obj.append(_neq_bool(m, piece_slots[i][0], piece_slots[i][1], f"ne2_{i}") * 10)
    m.Minimize(sum(obj))
    return m, slot_of, piece_slots, piece_days, piece_keys

def decode(solver, slot_of, piece_slots, piece_days, piece_keys):
    grids = {s["key"]: [[None] * 5 for _ in range(5)] for s in SECTIONS}
    for i, u in enumerate(UNITS):
        for p in range(u["count"]):
            s = solver.Value(piece_slots[i][p])
            d = solver.Value(piece_days[i][p])
            grids[u["sec"]][d][s] = i
    return grids

def solve_one(seed=0, time_limit=30.0):
    m, slot_of, piece_slots, piece_days, piece_keys = build()
    solver = cp_model.CpSolver()
    solver.parameters.random_seed = seed
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = 8
    status = solver.Solve(m)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None, status
    return decode(solver, slot_of, piece_slots, piece_days, piece_keys), status

if __name__ == "__main__":
    import sys, time
    t0 = time.time()
    grids, status = solve_one(seed=int(sys.argv[1]) if len(sys.argv) > 1 else 0)
    print("status:", status, "time:", round(time.time() - t0, 2))
    if grids is None:
        print("NO SOLUTION")
        sys.exit(1)
    ok, issues = validate(grids)
    print("validate:", ok)
    if not ok:
        for it in issues[:20]:
            print("  ", it)
    else:
        print("score:", score(grids))
        for sec in SECTIONS:
            g = grids[sec["key"]]
            print(f"\n{sec['key']}")
            for d in range(5):
                row = []
                for s in range(5):
                    u = UNITS[g[d][s]]
                    row.append(f"{u['subject'][:12]:12s}")
                print("  " + " | ".join(row))

def generate_many(n_seeds=12, time_per_seed=15, verbose=True):
    """Run several randomized optimization seeds, collect distinct valid solutions,
    return sorted list of (score, grids)."""
    from solver import score as _score, canonical as _canonical, validate as _validate
    seen = {}
    for seed in range(n_seeds):
        m, slot_of, piece_slots, piece_days, piece_keys = build()
        class Collect(cp_model.CpSolverSolutionCallback):
            def __init__(self):
                super().__init__()
                self.found = []
            def on_solution_callback(self):
                try:
                    g = decode(self, slot_of, piece_slots, piece_days, piece_keys)
                    if _validate(g)[0]:
                        key = _canonical(g)
                        sc = _score(g)
                        self.found.append((sc, key, g))
                except Exception:
                    pass
        cb = Collect()
        solver = cp_model.CpSolver()
        solver.parameters.random_seed = 1000 + seed
        solver.parameters.max_time_in_seconds = time_per_seed
        solver.parameters.num_search_workers = 8
        status = solver.Solve(m, cb)
        for sc, key, g in cb.found:
            if key not in seen:
                seen[key] = (sc, g)
        if verbose:
            best = min((s for s, _, _ in cb.found), default=None)
            print(f"seed {seed}: {len(cb.found)} found, total distinct={len(seen)}, "
                  f"best_this={best} status={status}")
    ranked = sorted(seen.values(), key=lambda x: x[0])
    return ranked


def generate_ranked(n_seeds=2, time_per_seed=45, max_solutions=0):
    """API entry point: run CP-SAT over several seeds, return
    (ranked list of (score, grids), any_optimal bool).
    `max_solutions` caps the returned list (0 = no cap)."""
    from solver import score as _score, canonical as _canonical, validate as _validate
    seen = {}
    any_optimal = False
    for seed in range(n_seeds):
        m, slot_of, piece_slots, piece_days, piece_keys = build()

        class Collect(cp_model.CpSolverSolutionCallback):
            def __init__(self):
                super().__init__()
                self.found = []
            def on_solution_callback(self):
                try:
                    g = decode(self, slot_of, piece_slots, piece_days, piece_keys)
                    if _validate(g)[0]:
                        key = _canonical(g)
                        sc = _score(g)
                        self.found.append((sc, key, g))
                except Exception:
                    pass

        cb = Collect()
        solver = cp_model.CpSolver()
        solver.parameters.random_seed = 1000 + seed
        solver.parameters.max_time_in_seconds = time_per_seed
        solver.parameters.num_search_workers = 8
        status = solver.Solve(m, cb)
        if status == cp_model.OPTIMAL:
            any_optimal = True
        for sc, key, g in cb.found:
            if key not in seen:
                seen[key] = (sc, g)

    ranked = sorted(seen.values(), key=lambda x: x[0])
    if max_solutions and max_solutions > 0:
        ranked = ranked[:max_solutions]
    return ranked, any_optimal
