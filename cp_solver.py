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
import os
from collections import defaultdict
from ortools.sat.python import cp_model

from solver import UNITS, SECTIONS, TEACHER_FULL, DAYS, SLOTS
from solver import SLOT_OF, DAY_OF, resolve_constraints
from solver import validate, score, canonical

# which teachers' units are "big" (single slot, no split)
def slot_domain(u, R=None):
    t = u["teacher"]; subj = u["subject"]
    if t == "PARALLEL":
        return [2, 3]
    r = ((R or {}).get(t) or {}).get("rules") or {}
    if r.get("subject_slots"):
        for e in r["subject_slots"]:
            if e["subject"] == subj:
                return [SLOT_OF[x] for x in e["slots"]]
    dom = [0, 1, 2, 3, 4]
    if r.get("allowed_slots"):
        aset = {SLOT_OF[x] for x in r["allowed_slots"]}
        dom = [x for x in dom if x in aset]
    if r.get("forbidden_slots"):
        fset = {SLOT_OF[x] for x in r["forbidden_slots"]}
        dom = [x for x in dom if x not in fset]
    return dom

def day_domain(u, R=None):
    t = u["teacher"]; subj = u["subject"]
    r = ((R or {}).get(t) or {}).get("rules") or {}
    dom = [0, 1, 2, 3, 4]
    if r.get("allowed_days"):
        aset = {DAY_OF[x] for x in r["allowed_days"]}
        dom = [d for d in dom if d in aset]
    if r.get("forbidden_days"):
        fset = {DAY_OF[x] for x in r["forbidden_days"]}
        dom = [d for d in dom if d not in fset]
    if r.get("subject_forbidden_days"):
        for e in r["subject_forbidden_days"]:
            if e["subject"] == subj:
                fset = {DAY_OF[x] for x in e["days"]}
                dom = [d for d in dom if d not in fset]
    return dom

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

def build(R=None):
    if R is None:
        R = resolve_constraints()
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
        sd = slot_domain(u, R)
        dd = day_domain(u, R)
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

    # ---- rule-driven: slot presence / engagement requirements ----
    for code, entry in R.items():
        rules = entry.get("rules") or {}
        units = [i for i, u in enumerate(UNITS) if u["teacher"] == code]
        for e in (rules.get("min_days_in_slot") or []):
            si = SLOT_OF[e["slot"]]
            terms = [_eq_bool(m, piece_slots[i][p], si, f"mds_{code}_{si}_{i}_{p}")
                     for i in units for p in range(UNITS[i]["count"])]
            if terms:
                m.Add(sum(terms) >= 1)
        for e in (rules.get("stream_slots_required") or []):
            stream = e["stream"]
            sunits = [i for i in units if UNITS[i]["sec"].startswith("ICS" if stream == "ICS" else "I.COM")]
            for sl in e["slots"]:
                si = SLOT_OF[sl]
                terms = [_eq_bool(m, piece_slots[i][p], si, f"ssr_{code}_{si}_{i}_{p}")
                         for i in sunits for p in range(UNITS[i]["count"])]
                if terms:
                    m.Add(sum(terms) >= 1)
        if rules.get("min_days_engaged"):
            need = rules["min_days_engaged"]
            day_bools = []
            for d in range(5):
                db = m.NewBoolVar(f"mde_{code}_{d}")
                terms = [_eq_bool(m, day, d, f"mde_{code}_{d}_{i}_{p}")
                         for i in units for p, day in enumerate(piece_days[i])]
                m.Add(sum(terms) >= 1).OnlyEnforceIf(db)
                m.Add(sum(terms) == 0).OnlyEnforceIf(db.Not())
                day_bools.append(db)
            m.Add(sum(day_bools) >= need)

    # forbidden_slots_on_days: k encodes slot*5+day for every piece
    for code, entry in R.items():
        rules = entry.get("rules") or {}
        for e in (rules.get("forbidden_slots_on_days") or []):
            dset = {DAY_OF[x] for x in e["days"]}
            sset = {SLOT_OF[x] for x in e["slots"]}
            for i, u in enumerate(UNITS):
                if u["teacher"] != code:
                    continue
                for p in range(u["count"]):
                    for d in dset:
                        for s_ in sset:
                            m.Add(piece_keys[i][p] != s_ * 5 + d)

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


def generate_ranked(n_seeds=2, time_per_seed=45, max_solutions=0, constraints=None):
    """API entry point: run CP-SAT over several seeds, return
    (ranked list of (score, grids), any_optimal bool).
    `constraints` (optional) overrides faculty constraints (see constraints_schema.md)."""
    from solver import score as _score, canonical as _canonical, validate as _validate
    R = resolve_constraints(constraints)
    seen = {}
    any_optimal = False
    for seed in range(n_seeds):
        m, slot_of, piece_slots, piece_days, piece_keys = build(R)

        class Collect(cp_model.CpSolverSolutionCallback):
            def __init__(self):
                super().__init__()
                self.found = []
            def on_solution_callback(self):
                try:
                    g = decode(self, slot_of, piece_slots, piece_days, piece_keys)
                    if _validate(g, R)[0]:
                        key = _canonical(g)
                        sc = _score(g)
                        self.found.append((sc, key, g))
                except Exception:
                    pass

        cb = Collect()
        solver = cp_model.CpSolver()
        solver.parameters.random_seed = 1000 + seed
        solver.parameters.max_time_in_seconds = time_per_seed
        # On low-CPU hosts (e.g. Render free tier: 0.1 vCPU) fewer workers is faster.
        solver.parameters.num_search_workers = int(os.environ.get("CP_SAT_WORKERS", "8"))
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
