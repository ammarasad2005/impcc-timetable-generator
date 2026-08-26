"""
IMPCC timetable generator — CP-SAT model (OR-Tools).

Variables: every subject "unit" (section, subject, teacher, count) is split into
`count` pieces. Each piece has (slot, day). Constraints:
  - section: AllDifferent(keys) over its pieces        -> exact cover of the active grid
  - unit:   AllDifferent(days)                          -> no subject twice in a day
  - teacher:AllDifferent(keys) over all its pieces      -> no double-booking
  - slot/day domains per teacher rules + special structure
Objective: minimize subject-slot shuffling (weighted by weekly credits).

The ACTIVE timetable grid (days x periods, capacity 6x8 — see timetable_config.py)
is selected via solver.set_grid(); the default is the historical 5x5.
"""
import random
import json
import os
from collections import defaultdict
from ortools.sat.python import cp_model

import solver as _solver
from solver import UNITS, SECTIONS, TEACHER_FULL, DAYS, SLOTS
from solver import SLOT_OF, DAY_OF, resolve_constraints
from solver import validate, score, canonical
from context_model import _sec_stream

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
    dom = list(range(_solver.P))
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
    dom = list(range(_solver.D))
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
    Dg, Pg = _solver.D, _solver.P          # active grid (set via solver.set_grid)
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
            if Dg == 5:
                # fast path: 5 pieces must cover all 5 days (current behaviour)
                for d in range(5):
                    k = m.NewIntVar(0, Dg * Pg - 1, f"k_{i}_{d}")
                    m.Add(k == s * Dg + d)
                    pieces.append((s, d, k))
            else:
                # general: 5 pieces on distinct days of the active grid
                days = [m.NewIntVarFromDomain(cp_model.Domain.FromValues(dd), f"d_{i}_{p}")
                        for p in range(5)]
                m.AddAllDifferent(days)
                for p in range(5):
                    k = m.NewIntVar(0, Dg * Pg - 1, f"k_{i}_{p}")
                    m.Add(k == s * Dg + days[p])
                    pieces.append((s, days[p], k))
        elif c == 4:
            s = m.NewIntVarFromDomain(cp_model.Domain.FromValues(sd), f"s_{i}")
            slot_of[i] = s
            days = [m.NewIntVarFromDomain(cp_model.Domain.FromValues(dd), f"d_{i}_{p}") for p in range(4)]
            m.AddAllDifferent(days)
            for p in range(4):
                k = m.NewIntVar(0, Dg * Pg - 1, f"k_{i}_{p}")
                m.Add(k == s * Dg + days[p])
                pieces.append((s, days[p], k))
        elif c == 3:
            slots = [m.NewIntVarFromDomain(cp_model.Domain.FromValues(sd), f"s_{i}_{p}") for p in range(3)]
            days = [m.NewIntVarFromDomain(cp_model.Domain.FromValues(dd), f"d_{i}_{p}") for p in range(3)]
            m.AddAllDifferent(days)
            for p in range(3):
                k = m.NewIntVar(0, Dg * Pg - 1, f"k_{i}_{p}")
                m.Add(k == slots[p] * Dg + days[p])
                pieces.append((slots[p], days[p], k))
        else:  # c == 2
            slots = [m.NewIntVarFromDomain(cp_model.Domain.FromValues(sd), f"s_{i}_{p}") for p in range(2)]
            days = [m.NewIntVarFromDomain(cp_model.Domain.FromValues(dd), f"d_{i}_{p}") for p in range(2)]
            m.Add(days[0] != days[1])
            for p in range(2):
                k = m.NewIntVar(0, Dg * Pg - 1, f"k_{i}_{p}")
                m.Add(k == slots[p] * Dg + days[p])
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
        if not units:
            continue   # teacher has no teaching load in this allocation — nothing to enforce
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
            for d in range(_solver.D):
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
                            m.Add(piece_keys[i][p] != s_ * _solver.D + d)

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
    grids = {s["key"]: [[None] * _solver.P for _ in range(_solver.D)] for s in SECTIONS}
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


def generate_ranked(n_seeds=2, time_per_seed=45, max_solutions=0, constraints=None, sections=None,
                    days=5, periods=5):
    """API entry point: run CP-SAT over several seeds, return
    (ranked list of (score, grids), any_optimal bool).
    `constraints` / `sections` (optional) override faculty constraints and the
    course allocation (see constraints_schema.md). `days`/`periods` select the
    ACTIVE grid (capacity 6x8; default 5x5)."""
    global UNITS, SECTIONS
    _solver.set_grid(days, periods)
    from solver import score as _score, canonical as _canonical, validate as _validate
    R = resolve_constraints(constraints)
    _solver.set_active_sections(sections)
    SECTIONS = _solver.SECTIONS
    UNITS = _solver.UNITS
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


# =====================================================================
# CONTEXT PATH (multi-population solving; see context_model.py)
# =====================================================================
def _teacher_slot_domain(teacher, R, default=None):
    """Hard slot domain for a teacher code (soft rules EXCLUDED — they become
    penalties). Returns None = unrestricted."""
    ent = (R or {}).get(teacher) or {}
    r = ent.get("rules") or {}
    from solver import hardness_of as _h
    dom = set(range(_solver.P)) if default is None else set(default)
    if "allowed_slots" in r and _h(ent, "allowed_slots") == 100:
        dom &= {SLOT_OF[x] for x in r["allowed_slots"]}
    if "forbidden_slots" in r and _h(ent, "forbidden_slots") == 100:
        dom -= {SLOT_OF[x] for x in r["forbidden_slots"]}
    return sorted(dom)


def _unit_slot_domain(u, R, model):
    """Full hard slot domain for a unit (teacher rules + course placement +
    stream scoping + parallel group + member availability)."""
    P = _solver.P
    dom = set(range(P))
    rules = ((R.get(u["teacher"]) or {}).get("rules") or {}) if not u["group"] else {}
    d = _teacher_slot_domain(u["teacher"], R)
    if d is not None and not u["group"]:
        dom &= set(d)
    if u["group"]:
        g = next((g for g in (model.get("_parallel") or []) if g["id"] == u["group"]), None)
        if g:
            gdom = {SLOT_OF[x] for x in (g.get("slots") or [])} or set(range(P))
            for mem in u["members"]:
                md = _teacher_slot_domain(mem, R)
                if md is not None:
                    gdom &= set(md)
            dom &= gdom
    else:
        _ss_by_subj = {}
        for e in (rules.get("subject_slots") or []):
            if e.get("days"):
                continue   # day-scoped pins are encoded at the cell level
            _ss_by_subj.setdefault(e["subject"], set()).update({SLOT_OF[x] for x in e["slots"]})
        for subj, sset in _ss_by_subj.items():
            for sec in u["secs"]:
                if u["courseBySec"].get(sec) == subj:
                    dom &= sset
        for e in (rules.get("subject_slot_days") or []):
            if e.get("days"):
                continue   # day-scoped pin handled cell-level
            for sec in u["secs"]:
                if u["courseBySec"].get(sec) == e["subject"]:
                    dom &= {SLOT_OF[e["slot"]]}
        for e in (rules.get("allowed_slots_in_stream") or []):
            if e.get("days"):
                continue
            for sec in u["secs"]:
                if _sec_stream(sec) == e["stream"]:
                    dom &= {SLOT_OF[x] for x in e["slots"]}
    return sorted(dom)


def _unit_day_domain(u, R, model):
    """Full hard day domain for a unit (off-days + teacher day rules +
    stream-scoped days + GI subject-forbidden days)."""
    D = _solver.D
    dom = set(range(D))
    _ent = (R.get(u["teacher"]) or {})
    rules = (_ent.get("rules") or {}) if not u["group"] else {}
    from solver import hardness_of as _h_
    for sec in u["secs"]:
        m = (model.get("_meta") or {}).get(sec) or {}
        dom -= set(m.get("offDays") or [])
    if not u["group"]:
        if "allowed_days" in rules and _h_(_ent, "allowed_days") == 100:
            dom &= {DAY_OF[x] for x in rules["allowed_days"]}
        if "forbidden_days" in rules and _h_(_ent, "forbidden_days") == 100:
            dom -= {DAY_OF[x] for x in rules["forbidden_days"]}
        for e in (rules.get("allowed_days_in_stream") or []):
            for sec in u["secs"]:
                if _sec_stream(sec) == e["stream"]:
                    dom &= {DAY_OF[x] for x in e["days"]}
        for e in (rules.get("subject_forbidden_days") or []):
            for sec in u["secs"]:
                if u["courseBySec"].get(sec) == e["subject"]:
                    dom -= {DAY_OF[x] for x in e["days"]}
    else:
        for mem in u["members"]:
            from solver import hardness_of as _hm
            ment = (R.get(mem) or {})
            mr = (ment.get("rules") or {})
            if "allowed_days" in mr and _hm(ment, "allowed_days") == 100:
                dom &= {DAY_OF[x] for x in mr["allowed_days"]}
            if "forbidden_days" in mr and _hm(ment, "forbidden_days") == 100:
                dom -= {DAY_OF[x] for x in mr["forbidden_days"]}
    for e in ((model.get("instructions") or {}).get("subjectForbiddenDays") or []):
        for sec in u["secs"]:
            if (u["courseBySec"].get(sec) == e.get("subject")
                    and (not e.get("scope") or _sec_stream(sec) == e["scope"])):
                dom -= {DAY_OF[x] for x in e["days"]}
    return sorted(dom)


def build_from_context(model, objective="default", collect=None, coh_off=None):
    from solver import _slotset, _dayset, SLOT_OF, DAY_OF, hardness_of  # local (mirrors soft_raise)
    """CP-SAT model for a context model (context_model.context_to_model output).

    objective="default" sets the classic shuffle+soft objective. objective="none"
    leaves the objective unset so a caller (e.g. targeted repair) can install its
    own; when a `collect` dict is passed it receives the internal presolve
    structures (soft_terms, teacher_keys, section_keys)."""
    Dg, Pg = _solver.D, _solver.P
    R = model["constraints"]
    pen = model["penalties"]
    m = cp_model.CpModel()

    model["_meta"] = {s["key"]: s for s in model["sections"]}
    model["_parallel"] = model.get("_parallel") or []

    piece_slots, piece_days, piece_keys = {}, {}, {}
    section_keys = defaultdict(list)
    teacher_keys = defaultdict(list)
    soft_terms = []

    for u in model["units"]:
        i = u["id"]
        c = u["count"]
        sd = _unit_slot_domain(u, R, model)
        dd = _unit_day_domain(u, R, model)
        if not sd or not dd:
            return None
        allow_double_days = (u["level"] == "bs")

        # General piece encoding: every piece gets an independent slot var;
        # days stay distinct per unit. Splitting a 5/wk or 4/wk course across
        # slots is structurally allowed (BS sections can hold more 4/wk
        # courses than period columns; day+slot bans can make full-column
        # monopolies infeasible) — the shuffle tiers in the objective
        # (100000/10000 per extra slot) keep single-slot forms strongly
        # preferred whenever feasible.
        slots = [m.NewIntVarFromDomain(cp_model.Domain.FromValues(sd), f"cs_{i}_{p}")
                 for p in range(c)]
        days = [m.NewIntVarFromDomain(cp_model.Domain.FromValues(dd), f"cd_{i}_{p}")
                for p in range(c)]
        if c == 2 and allow_double_days:
            same_slot = m.NewBoolVar(f"ss_{i}")
            m.Add(slots[0] == slots[1]).OnlyEnforceIf(same_slot)
            m.Add(slots[0] != slots[1]).OnlyEnforceIf(same_slot.Not())
            m.Add(days[0] != days[1]).OnlyEnforceIf(same_slot)
        elif c == 3 and allow_double_days:
            pass   # BS 3/wk may double in a day (section cells stay distinct)
        else:
            m.AddAllDifferent(days)
        if c == 2 and not allow_double_days and u["level"] == "inter" \
                and (model["instructions"].get("consecutiveFor2pw") or {}).get("inter"):
            diff = m.NewIntVar(-Dg, Dg, f"cons_{i}")
            m.Add(diff == days[1] - days[0])
            ab = m.NewIntVar(0, Dg, f"consab_{i}")
            m.AddAbsEquality(ab, diff)
            m.Add(ab == 1)

        if u["group"]:
            for p in range(1, c):
                m.Add(slots[p] == slots[0])   # an either/or block occupies ONE slot
        piece_slots[i] = slots
        piece_days[i] = days
        piece_keys[i] = []
        for p in range(c):
            k = m.NewIntVar(0, Dg * Pg - 1, f"ck_{i}_{p}")
            m.Add(k == slots[p] * Dg + days[p])
            piece_keys[i].append(k)

        for sec in u["secs"]:
            section_keys[sec].extend(piece_keys[i])
        teachers = [u["teacher"]] + (u["members"] if u["group"] else [])
        for t in teachers:
            teacher_keys[t].extend(piece_keys[i])

        # ---- day+slot combination bans and pinned subject-days (model-level)
        for t in teachers:
            entry = R.get(t) or {}
            trules = entry.get("rules") or {}
            for e in (trules.get("forbidden_slots_on_days") or []):
                h = hardness_of(entry, "forbidden_slots_on_days")
                if h == 0:
                    continue
                sc = e.get("scope") or {}
                if sc.get("streams") and not any(_sec_stream(sec) in sc["streams"] for sec in u["secs"]):
                    continue
                if sc.get("sections") and not any(sec in sc["sections"] for sec in u["secs"]):
                    continue
                if sc.get("populations") and not any(((model.get("_meta") or {}).get(sec) or {}).get("pop") in sc["populations"] for sec in u["secs"]):
                    continue
                dset = {DAY_OF[x] for x in e["days"]}
                if sc.get("days"):
                    dset &= _dayset(sc["days"])
                sset = {SLOT_OF[x] for x in e["slots"]}
                for p in range(c):
                    for d in sorted(dset):
                        for s_ in sorted(sset):
                            if h == 100:
                                m.Add(piece_keys[i][p] != s_ * Dg + d)
                            else:
                                soft_terms.append((int(pen["rule"] * h / 100),
                                                   _eq_bool(m, piece_keys[i][p], s_ * Dg + d,
                                                            f"fsod_soft_{i}_{p}_{d}_{s_}")))

        # ---- soft slot rules (excluded from domains; penalized here)
        if not u["group"]:
            entry = R.get(u["teacher"]) or {}
            soft = set(entry.get("soft") or [])
            rules = entry.get("rules") or {}
            if rules.get("forbidden_slots"):
                hfs = hardness_of(entry, "forbidden_slots")
                if 0 < hfs < 100:
                    fset = {SLOT_OF[x] for x in rules["forbidden_slots"]}
                    bools = [_eq_bool(m, slots[p], s_, f"sf_{i}_{p}_{s_}")
                             for p in range(c) for s_ in sorted(fset)]
                    if bools:
                        anyb = m.NewBoolVar(f"sfany_{i}")
                        m.AddMaxEquality(anyb, bools)
                        soft_terms.append((int(pen["rule"] * hfs / 100), anyb))
            if rules.get("soft_prefer_free_slots"):
                hspf = hardness_of(entry, "soft_prefer_free_slots")
                if hspf > 0:
                    w = int(pen["preferFreeSlot"] * hspf / 100)
                    fset = {SLOT_OF[x] for x in rules["soft_prefer_free_slots"]}
                    for p in range(c):
                        for s_ in sorted(fset):
                            soft_terms.append((w,
                                               _eq_bool(m, slots[p], s_, f"spf_{i}_{p}_{s_}")))

    for sec, keys in section_keys.items():
        if len(keys) >= 2:
            m.AddAllDifferent(keys)
    for t, keys in teacher_keys.items():
        if len(keys) >= 2:
            m.AddAllDifferent(keys)

    # ---- first/last period occupied (BS sections, non-off days)
    for section in model["sections"]:
        if not section["firstLast"] or section["level"] != "bs":
            continue
        keys = section_keys.get(section["key"]) or []
        for d in section["effDays"]:
            for sl in (0, Pg - 1):
                target = sl * Dg + d
                bools = [_eq_bool(m, k, target, f"fl_{section['key']}_{d}_{sl}_{j}")
                         for j, k in enumerate(keys)]
                if bools:
                    m.Add(sum(bools) >= 1)

    # ---- day-exclusive pairs (per section): pair day-vars all distinct
    for p in model["dayExclusive"]:
        dayvars = [dv for uid in p["units"] for dv in piece_days[uid]]
        if len(dayvars) >= 2:
            m.AddAllDifferent(dayvars)
        if p["softConsecutiveDays"]:
            for uid in p["units"]:
                u = next(x for x in model["units"] if x["id"] == uid)
                if u["count"] == 2:
                    diff = m.NewIntVar(-Dg, Dg, f"dxc_{uid}")
                    m.Add(diff == piece_days[uid][1] - piece_days[uid][0])
                    ab = m.NewIntVar(0, Dg, f"dxcab_{uid}")
                    m.AddAbsEquality(ab, diff)
                    nb = m.NewBoolVar(f"dxnc_{uid}")
                    m.Add(ab != 1).OnlyEnforceIf(nb)
                    m.Add(ab == 1).OnlyEnforceIf(nb.Not())
                    soft_terms.append((pen["nonConsecutive"], nb))

        # hardness gate: 100 = hard mask, 1..99 = demote to a scaled soft term,
    # 0 = inactive (personal_constraints_model.md §8)
    def _h100(entry, kind):
        return hardness_of(entry, kind) == 100
    def _hoff(entry, kind):
        return hardness_of(entry, kind) == 0
    def _hval(entry, kind):
        return hardness_of(entry, kind)

# ---- engagement requirements (distinct-DAY semantics via piece keys)
    for code, entry in R.items():
        rules = (entry or {}).get("rules") or {}
        units_of = [u for u in model["units"] if u["teacher"] == code]
        if not units_of and not any(u["group"] and code in u["members"] for u in model["units"]):
            continue
        for e in (rules.get("min_days_in_slot") or []):
            si = SLOT_OF[e["slot"]]
            need = int(e.get("min_days") or 1)
            daybools = []
            for d in range(Dg):
                db = m.NewBoolVar(f"mds2_{code}_{si}_{d}")
                terms = [_eq_bool(m, piece_keys[u["id"]][p], si * Dg + d,
                                  f"mds2t_{code}_{si}_{d}_{u['id']}_{p}")
                         for u in units_of for p in range(u["count"])]
                if not terms:
                    continue
                m.Add(sum(terms) >= 1).OnlyEnforceIf(db)
                m.Add(sum(terms) == 0).OnlyEnforceIf(db.Not())
                daybools.append(db)
            if daybools:
                m.Add(sum(daybools) >= need)
        for e in (rules.get("stream_slots_required") or []):
            # stream must EXIST in this context (a shift-2 scenario without ICS
            # sections cannot satisfy an ICS stream requirement — skip it)
            stream_units = [u for u in units_of
                            if any(_sec_stream(sec) == e["stream"] for sec in u["secs"])]
            if not stream_units:
                continue
            for sl in e["slots"]:
                si = SLOT_OF[sl]
                daybools = []
                for d in range(Dg):
                    db = m.NewBoolVar(f"ssr2_{code}_{si}_{d}")
                    terms = [_eq_bool(m, piece_keys[u["id"]][p], si * Dg + d,
                                      f"ssr2t_{code}_{si}_{d}_{u['id']}_{p}")
                             for u in units_of
                             if any(_sec_stream(s) == e["stream"] for s in u["secs"])
                             for p in range(u["count"])]
                    if not terms:
                        continue
                    m.Add(sum(terms) >= 1).OnlyEnforceIf(db)
                    m.Add(sum(terms) == 0).OnlyEnforceIf(db.Not())
                    daybools.append(db)
                if daybools:
                    m.Add(sum(daybools) >= 4)
        if rules.get("min_days_engaged"):
            need = rules["min_days_engaged"]
            daybools = []
            for d in range(Dg):
                db = m.NewBoolVar(f"mde2_{code}_{d}")
                terms = [_eq_bool(m, dv, d, f"mde2t_{code}_{d}_{u['id']}_{p}")
                         for u in units_of for p, dv in enumerate(piece_days[u["id"]])]
                if not terms:
                    continue
                m.Add(sum(terms) >= 1).OnlyEnforceIf(db)
                m.Add(sum(terms) == 0).OnlyEnforceIf(db.Not())
                daybools.append(db)
            if daybools:
                m.Add(sum(daybools) >= need)

    # ---- non-overriding (institution rule, encoded: for each section X there
    # is a cell where X has subject A while the paired sections do NOT have
    # subject B at the same cell)
    for e in ((model.get("instructions") or {}).get("nonOverriding") or []):
        secs, subs = e["sections"], e["subjects"]
        units_of = {}
        for sec in secs:
            for sub in subs:
                units_of[(sec, sub)] = [u for u in model["units"]
                                        if u["courseBySec"].get(sec) == sub]
        for x_sec in secs:
            cell_ok = []
            for d in range(Dg):
                for sl in range(Pg):
                    target = sl * Dg + d
                    has_a = [_eq_bool(m, piece_keys[u["id"]][p], target,
                                      f"nov_{x_sec}_a_{d}_{sl}_{u['id']}_{p}")
                             for u in units_of.get((x_sec, subs[0]), [])
                             for p in range(u["count"])]
                    if not has_a:
                        continue
                    ba = m.NewBoolVar(f"novb_{x_sec}_{d}_{sl}")
                    m.AddMaxEquality(ba, has_a)
                    nb = []
                    for y_sec in secs:
                        if y_sec == x_sec:
                            continue
                        for u in units_of.get((y_sec, subs[1]), []):
                            for p in range(u["count"]):
                                nb.append(_eq_bool(m, piece_keys[u["id"]][p], target,
                                                   f"nov_{x_sec}_{y_sec}_{d}_{sl}_{u['id']}_{p}").Not())
                    ok = m.NewBoolVar(f"novok_{x_sec}_{d}_{sl}")
                    m.AddBoolAnd([ba] + nb).OnlyEnforceIf(ok)
                    m.AddBoolOr([ba.Not()] + [b.Not() for b in nb]).OnlyEnforceIf(ok.Not())
                    cell_ok.append(ok)
            if cell_ok:
                m.Add(sum(cell_ok) >= 1)

    # ---- subject x day x slot forbidden windows (institution rule, e.g.
    # "Physics must not be scheduled in the last two periods on Friday"):
    # a hard ban — the unit's pieces may never sit in those exact cells.
    # generalized 'forbid cells' kernel: match by subject(s) and/or sections
    # and/or teacher code(s), optional stream scope, over a days x slots window
    # (empty day/slot lists mean 'all'). DYNAMIC custom rules from the admin
    # registry lower to entries of this same list (see solver_context), so they
    # are real constraints here, not display-only text.
    for e in ((model.get("instructions") or {}).get("subjectForbiddenSlotDays") or []):

        def _dyn_hit(u, sec, e=e):
            if e.get("subject") and u["courseBySec"].get(sec) != e.get("subject"):
                return False
            if e.get("subjects") and u["courseBySec"].get(sec) not in e["subjects"]:
                return False
            if e.get("sections") and sec not in e["sections"]:
                return False
            if e.get("teachers") and u.get("teacher") not in e["teachers"] \
                    and not set(u.get("members") or []).intersection(e["teachers"]):
                return False
            if e.get("scope") and _sec_stream(sec) != e["scope"]:
                return False
            return True

        dset = _dayset(e.get("days") or [d for d in range(Dg)])
        sset = _slotset(e.get("slots") or ["P%d" % (s + 1) for s in range(Pg)])
        for u in model["units"]:
            secs = [sec for sec in u["secs"] if _dyn_hit(u, sec)]
            if not secs:
                continue
            for p in range(u["count"]):
                for d in dset:
                    for sl in sset:
                        m.Add(piece_keys[u["id"]][p] != sl * Dg + d)

    # =================================================================
    # EXTENDED PERSONAL RULES (personal_constraints_model.md v2): every
    # taxonomy-v2 kind not expressible in the legacy slot/day domains lands
    # here — day×slot windows, section/stream-scoped masks, distribution
    # quotas, per-day count bounds, gap structure, and the new soft kinds.
    # Units with multiple sections SHARE piece vars across sections, so a
    # section-scoped test uses the conservative all-sections-match reading
    # (scope_unit_applies); single-section units match the checker exactly.
    # =================================================================
    from solver import scope_unit_applies as _sua
    pop_map = {s["key"]: s.get("pop") for s in model.get("sections", [])}
    _pop_of = lambda sec: pop_map.get(sec)

    def _e_days(e, Dg_=Dg):
        """Entry day set with scope.days intersecting literal days; empty = all."""
        days = _dayset(e.get("days") or [])
        scd = _dayset(((e.get("scope") or {}).get("days")) or [])
        if days and scd:
            days &= scd
        elif scd:
            days = scd
        return days if days else set(range(Dg_))

    def _unit_in_scope(e, u):
        return _sua(e, u, _pop_of, _sec_stream)

    for code, entry in R.items():
        trules = (entry or {}).get("rules") or {}
        units_of = [u for u in model["units"]
                    if u["teacher"] == code or (u["group"] and code in (u["members"] or []))]
        own_units = [u for u in model["units"] if u["teacher"] == code]
        if not units_of:
            continue

        def _ban_keys(u, keys):
            for p in range(u["count"]):
                for kval in keys:
                    m.Add(piece_keys[u["id"]][p] != kval)

        # ---- positive day×slot window: only these (day,slot) cells allowed
        # (cover-all: pieces must land INSIDE the union of same-scope windows)
        if _h100(entry, "allowed_slots_days"):
            wgroups = {}
            for e in (trules.get("allowed_slots_days") or []):
                sc = e.get("scope") or {}
                sig = (tuple(sorted(sc.get("populations") or [])),
                       tuple(sorted(sc.get("streams") or [])),
                       tuple(sorted(sc.get("sections") or [])))
                wgroups.setdefault(sig, []).append(e)
            for sig, es in wgroups.items():
                win = set()
                for e in es:
                    for d in _e_days(e):
                        for sl in _slotset(e.get("slots") or []):
                            win.add((d, sl))
                for u in units_of:
                    if _unit_in_scope(es[0], u):
                        _ban_keys(u, [sl * Dg + d for d in range(Dg) for sl in range(Pg)
                                      if (d, sl) not in win])

        # ---- windows/allow-days restricted to given sections
        for e in (trules.get("allowed_slots_in_sections") or []):
            if not _h100(entry, "allowed_slots_in_sections"):
                continue
            secset = set(e.get("sections") or [])
            dset = _e_days(e)
            sset = _slotset(e.get("slots") or [])
            for u in units_of:
                if all(sec in secset for sec in u["secs"]):
                    _ban_keys(u, [sl * Dg + d for d in dset for sl in range(Pg) if sl not in sset])
        for e in (trules.get("allowed_days_in_sections") or []):
            if not _h100(entry, "allowed_days_in_sections"):
                continue
            secset = set(e.get("sections") or [])
            dset = _e_days(e)
            for u in units_of:
                if all(sec in secset for sec in u["secs"]):
                    _ban_keys(u, [sl * Dg + d for d in range(Dg) if d not in dset
                                  for sl in range(Pg)])

        # ---- stream-scoped day bans (new kind)
        for e in (trules.get("stream_forbidden_days") or []):
            if not _h100(entry, "stream_forbidden_days"):
                continue
            dset = _e_days(e) if e.get("days") else _dayset(e.get("days") or [])
            if not dset:
                dset = set(range(Dg))
            for u in units_of:
                if all(_sec_stream(sec) == e["stream"] for sec in u["secs"]):
                    _ban_keys(u, [sl * Dg + d for d in dset for sl in range(Pg)])

        # ---- subject × days allowed (union per subject across entries)
        subj_days_allow = {}
        for e in (trules.get("subject_days_allowed") or []):
            subj_days_allow.setdefault(e["subject"], set()).update(_dayset(e.get("days") or []))
        if _h100(entry, "subject_days_allowed"):
            for subj, dset in subj_days_allow.items():
                for u in units_of:
                    if any(u["courseBySec"].get(sec) == subj for sec in u["secs"]):
                        _ban_keys(u, [sl * Dg + d for d in range(Dg) if d not in dset
                                      for sl in range(Pg)])

        # ---- subject day×slot pins (union per subject across both pin kinds)
        pins = {}
        if _h100(entry, "subject_slot_days"):
            for e in (trules.get("subject_slot_days") or []):
                days = _e_days(e) if e.get("days") else set(range(Dg))
                pins.setdefault(e["subject"], set()).update(
                    (d, SLOT_OF[e["slot"]]) for d in days)
        if _h100(entry, "subject_slots_days"):
            for e in (trules.get("subject_slots_days") or []):
                days = _e_days(e) if e.get("days") else set(range(Dg))
                pins.setdefault(e["subject"], set()).update(
                    (d, sl) for d in days for sl in _slotset(e.get("slots") or []))
        if pins:
            for subj, win in pins.items():
                for u in units_of:
                    if any(u["courseBySec"].get(sec) == subj for sec in u["secs"]):
                        _ban_keys(u, [sl * Dg + d for d in range(Dg) for sl in range(Pg)
                                      if (d, sl) not in win])
        # ---- subject_slots entries that carry day scoping
        pins2 = {}
        for e in (trules.get("subject_slots") or []):
            if e.get("days"):
                pins2.setdefault(e["subject"], set()).update(
                    (d, sl) for d in _dayset(e["days"]) for sl in _slotset(e.get("slots") or []))
        for subj, win in pins2.items():
            for u in units_of:
                if any(u["courseBySec"].get(sec) == subj for sec in u["secs"]):
                    dayset = {d for (d, _) in win}
                    _ban_keys(u, [sl * Dg + d for d in dayset for sl in range(Pg)
                                  if (d, sl) not in win])
        # ---- allowed_slots_in_stream entries carrying day scoping
        for e in (trules.get("allowed_slots_in_stream") or []):
            if not e.get("days") or not _h100(entry, "allowed_slots_in_stream"):
                continue   # pure-slot form already handled by the slot domain
            dset = _dayset(e["days"])
            sset = _slotset(e.get("slots") or [])
            for u in units_of:
                if all(_sec_stream(sec) == e["stream"] for sec in u["secs"]):
                    _ban_keys(u, [sl * Dg + d for d in dset for sl in range(Pg) if sl not in sset])

        # ---- section allow/deny (unit-level; conservative for joint units)
        if _h100(entry, "allowed_sections") and isinstance(trules.get("allowed_sections"), list) \
                and trules["allowed_sections"]:
            allow = set(trules["allowed_sections"])
            for u in units_of:
                if any(sec not in allow for sec in u["secs"]):
                    return None   # unit needs a section the teacher may not teach
        if _h100(entry, "forbidden_sections") and isinstance(trules.get("forbidden_sections"), list) \
                and trules["forbidden_sections"]:
            deny = set(trules["forbidden_sections"])
            for u in units_of:
                if any(sec in deny for sec in u["secs"]):
                    return None

        # ================= count / engagement channels =================
        def _day_count_terms(us, d, slot=None):
            terms = []
            for u in us:
                for p in range(u["count"]):
                    if slot is None:
                        terms.append(_eq_bool(m, piece_days[u["id"]][p], d,
                                              f"dcnt_{code}_{d}_{u['id']}_{p}"))
                    else:
                        terms.append(_eq_bool(m, piece_keys[u["id"]][p], slot * Dg + d,
                                              f"dcnts_{code}_{d}_{slot}_{u['id']}_{p}"))
            return terms

        # max_periods_per_day: int or [{max, days?, stream?, sections?, scope?}]
        mppd = trules.get("max_periods_per_day")
        mppd_list = ([{"max": mppd}] if isinstance(mppd, int)
                     else (mppd if isinstance(mppd, list) else []))
        if _h100(entry, "max_periods_per_day"):
            for e in mppd_list:
                cap = e.get("max")
                if cap is None:
                    continue
                us = ([u for u in own_units if _unit_in_scope(e, u)]
                      if any(e.get(k) for k in ("stream", "sections", "scope")) else own_units)
                for d in sorted(_e_days(e)):
                    terms = _day_count_terms(us, d)
                    if terms:
                        m.Add(sum(terms) <= cap)

        # =========================================================
        # DEMOTED KINDS (1 <= hardness < 100): charge the checker-visible
        # breach magnitude with a hardness-scaled penalty (the ranked total
        # in generate_context re-derives the exact penalty via evaluate();
        # these terms only steer the search).
        # =========================================================
        def _soft_w(kind, base="rule"):
            return int(pen[base] * _hval(entry, kind) / 100)

        if 0 < _hval(entry, "max_periods_per_day") < 100:
            for e in ([{"max": mppd}] if isinstance(trules.get("max_periods_per_day"), int)
                      else (trules.get("max_periods_per_day") or [])):
                cap = e.get("max")
                if cap is None:
                    continue
                for d in sorted(_e_days(e)):
                    terms = _day_count_terms(own_units, d)
                    if not terms:
                        continue
                    ex = m.NewIntVar(0, len(terms), f"mppdx_{code}_{d}")
                    m.Add(ex >= sum(terms) - cap)
                    m.Add(ex >= 0)
                    soft_terms.append((_soft_w("max_periods_per_day"), ex))
        if 0 < _hval(entry, "min_periods_per_day") < 100:
            for e in ([{"min": trules.get("min_periods_per_day")}] if isinstance(trules.get("min_periods_per_day"), int)
                      else (trules.get("min_periods_per_day") or [])):
                floor = e.get("min")
                if floor is None:
                    continue
                for d in sorted(_e_days(e)):
                    terms = _day_count_terms(own_units, d)
                    if not terms:
                        continue
                    cnt = m.NewIntVar(0, len(terms), f"minpdx_c_{code}_{d}")
                    m.Add(cnt == sum(terms))
                    work = m.NewBoolVar(f"minpdx_w_{code}_{d}")
                    m.Add(cnt >= 1).OnlyEnforceIf(work)
                    m.Add(cnt == 0).OnlyEnforceIf(work.Not())
                    sh = m.NewIntVar(0, 8, f"minpdx_s_{code}_{d}")
                    m.Add(sh >= floor - cnt)
                    m.Add(sh >= 0)
                    m.Add(sh == 0).OnlyEnforceIf(work.Not())
                    soft_terms.append((_soft_w("min_periods_per_day"), sh))
        if 0 < _hval(entry, "max_days_in_slot") < 100:
            for e in (trules.get("max_days_in_slot") or []):
                si = SLOT_OF[e["slot"]]
                cap = e.get("max_days")
                if cap is None:
                    continue
                dbs = []
                for d in sorted(_e_days(e)):
                    terms = _day_count_terms(units_of, d, slot=si)
                    if not terms:
                        continue
                    db = m.NewBoolVar(f"mdslx_{code}_{si}_{d}")
                    m.Add(sum(terms) >= 1).OnlyEnforceIf(db)
                    m.Add(sum(terms) == 0).OnlyEnforceIf(db.Not())
                    dbs.append(db)
                if dbs:
                    ex = m.NewIntVar(0, len(dbs), f"mdslx_{code}_{si}")
                    m.Add(ex >= sum(dbs) - cap)
                    m.Add(ex >= 0)
                    soft_terms.append((_soft_w("max_days_in_slot"), ex))
        if 0 < _hval(entry, "allowed_slots_days") < 100:
            wgroups = {}
            for e2 in (trules.get("allowed_slots_days") or []):
                sc = e2.get("scope") or {}
                sig = (tuple(sorted(sc.get("populations") or [])),
                       tuple(sorted(sc.get("streams") or [])),
                       tuple(sorted(sc.get("sections") or [])))
                wgroups.setdefault(sig, []).append(e2)
            for sig, es in wgroups.items():
                win = set()
                for e2 in es:
                    for d in _e_days(e2):
                        for sl in _slotset(e2.get("slots") or []):
                            win.add((d, sl))
                for u in units_of:
                    if not _unit_in_scope(es[0], u):
                        continue
                    for p in range(u["count"]):
                        for d in range(Dg):
                            for sl in range(Pg):
                                if (d, sl) not in win:
                                    soft_terms.append((_soft_w("allowed_slots_days"),
                                                     _eq_bool(m, piece_keys[u["id"]][p], sl * Dg + d,
                                                              f"asdx_{code}_{u['id']}_{p}_{d}_{sl}")))
        for key, is_max in (("max_pieces_match", True), ("min_pieces_match", False)):
            hv = _hval(entry, key)
            if not (0 < hv < 100):
                continue
            for e in (trules.get(key) or []):
                bnd = e.get("max" if is_max else "min")
                if bnd is None:
                    continue
                us = _quota_units(e)
                if e.get("slot") or e.get("days"):
                    dset = _e_days(e)
                    sls = _slotset([e["slot"]]) if e.get("slot") else set(range(Pg))
                    terms = []
                    for u in us:
                        for p in range(u["count"]):
                            ors = [_eq_bool(m, piece_keys[u["id"]][p], sl * Dg + d,
                                            f"quox_{code}_{key}_{u['id']}_{p}_{d}_{sl}")
                                   for d in sorted(dset) for sl in sorted(sls)]
                            b = m.NewBoolVar(f"quoxb_{code}_{key}_{u['id']}_{p}")
                            m.AddMaxEquality(b, ors)
                            terms.append(b)
                    expr = sum(terms)
                else:
                    expr = sum(u["count"] for u in us)
                if is_max:
                    ex = m.NewIntVar(0, 99, f"quox_{code}_{key}")
                    m.Add(ex >= expr - bnd)
                    m.Add(ex >= 0)
                else:
                    ex = m.NewIntVar(0, 99, f"quox_{code}_{key}")
                    m.Add(ex >= bnd - expr)
                    m.Add(ex >= 0)
                soft_terms.append((_soft_w(key), ex))

        # min_periods_per_day gated by actually engaged that day
        minpd = trules.get("min_periods_per_day")
        minpd_list = ([{"min": minpd}] if isinstance(minpd, int)
                      else (minpd if isinstance(minpd, list) else []))
        if _h100(entry, "min_periods_per_day"):
            for e in minpd_list:
                floor = e.get("min")
                if floor is None:
                    continue
                us = ([u for u in own_units if _unit_in_scope(e, u)]
                      if any(e.get(k) for k in ("stream", "sections", "scope")) else own_units)
                for d in sorted(_e_days(e)):
                    terms = _day_count_terms(us, d)
                    if not terms:
                        continue
                    cnt = m.NewIntVar(0, len(terms), f"minpd_c_{code}_{d}")
                    m.Add(cnt == sum(terms))
                    work = m.NewBoolVar(f"minpd_w_{code}_{d}")
                    m.Add(cnt >= 1).OnlyEnforceIf(work)
                    m.Add(cnt == 0).OnlyEnforceIf(work.Not())
                    m.Add(cnt >= floor).OnlyEnforceIf(work)

        # max_days_in_slot: [{slot, max_days, days?, scope?}]
        if _h100(entry, "max_days_in_slot"):
            for e in (trules.get("max_days_in_slot") or []):
                si = SLOT_OF[e["slot"]]
                cap = e.get("max_days")
                if cap is None:
                    continue
                daybools = []
                for d in sorted(_e_days(e)):
                    terms = _day_count_terms(units_of, d, slot=si)
                    if not terms:
                        continue
                    db = m.NewBoolVar(f"mdsl_{code}_{si}_{d}")
                    m.Add(sum(terms) >= 1).OnlyEnforceIf(db)
                    m.Add(sum(terms) == 0).OnlyEnforceIf(db.Not())
                    daybools.append(db)
                if daybools:
                    m.Add(sum(daybools) <= cap)

        # ---- distribution quotas over the teacher's week
        def _quota_units(e):
            out = []
            for u in own_units:
                subs = {u["courseBySec"].get(sec) for sec in u["secs"]}
                if e.get("subject") and e["subject"] not in subs:
                    continue
                if e.get("subjects") and not subs.intersection(e["subjects"]):
                    continue
                if e.get("stream") and not all(_sec_stream(sec) == e["stream"] for sec in u["secs"]):
                    continue
                if e.get("sections") and not all(sec in (e["sections"] or []) for sec in u["secs"]):
                    continue
                if not _unit_in_scope(e, u):
                    continue
                out.append(u)
            return out

        for key, is_max in (("max_pieces_match", True), ("min_pieces_match", False)):
            if not _h100(entry, key):
                continue
            for e in (trules.get(key) or []):
                bnd = e.get("max" if is_max else "min")
                if bnd is None:
                    continue
                us = _quota_units(e)
                if e.get("slot") or e.get("days"):
                    dset = _e_days(e)
                    sls = _slotset([e["slot"]]) if e.get("slot") else set(range(Pg))
                    terms = []
                    for u in us:
                        for p in range(u["count"]):
                            ors = [_eq_bool(m, piece_keys[u["id"]][p], sl * Dg + d,
                                            f"quo_{code}_{key}_{u['id']}_{p}_{d}_{sl}")
                                   for d in sorted(dset) for sl in sorted(sls)]
                            b = m.NewBoolVar(f"quob_{code}_{key}_{u['id']}_{p}")
                            m.AddMaxEquality(b, ors)
                            terms.append(b)
                    expr = sum(terms)
                else:
                    expr = sum(u["count"] for u in us)   # fully static count
                m.Add(expr <= bnd) if is_max else m.Add(expr >= bnd)

        # ---- no free holes inside a teaching day (rare; bigger encoding)
        if trules.get("no_daily_gaps") and _h100(entry, "no_daily_gaps"):
            for d in range(Dg):
                occ = {}
                for sl in range(Pg):
                    terms = [_eq_bool(m, piece_keys[u["id"]][p], sl * Dg + d,
                                      f"ng_{code}_{d}_{sl}_{u['id']}_{p}")
                             for u in own_units for p in range(u["count"])]
                    if terms:
                        b = m.NewBoolVar(f"ngb_{code}_{d}_{sl}")
                        m.AddMaxEquality(b, terms)
                        occ[sl] = b
                for a in range(Pg):
                    for c in range(a + 2, Pg):
                        if a not in occ or c not in occ:
                            continue
                        both = m.NewBoolVar(f"ngboth_{code}_{d}_{a}_{c}")
                        m.AddBoolAnd([occ[a], occ[c]]).OnlyEnforceIf(both)
                        m.AddBoolOr([occ[a].Not(), occ[c].Not()]).OnlyEnforceIf(both.Not())
                        for bslot in range(a + 1, c):
                            if bslot in occ:
                                m.AddImplication(both, occ[bslot])

        # no_daily_gaps demoted to soft -> same gap-sum encoding as soft_compact_days
        if trules.get("no_daily_gaps") and 0 < _hval(entry, "no_daily_gaps") < 100:
            wng = _soft_w("no_daily_gaps")
            for d in range(Dg):
                occ = {}
                for sl in range(Pg):
                    terms = [_eq_bool(m, piece_keys[u["id"]][p], sl * Dg + d,
                                      f"ngx_{code}_{d}_{sl}_{u['id']}_{p}")
                             for u in own_units for p in range(u["count"])]
                    if terms:
                        b = m.NewBoolVar(f"ngxb_{code}_{d}_{sl}")
                        m.AddMaxEquality(b, terms)
                        occ[sl] = b
                if not occ:
                    continue
                cnt_d = m.NewIntVar(0, Pg, f"ngxn_{code}_{d}")
                m.Add(cnt_d == sum(occ.values()))
                work = m.NewBoolVar(f"ngxw_{code}_{d}")
                m.Add(cnt_d >= 1).OnlyEnforceIf(work)
                m.Add(cnt_d == 0).OnlyEnforceIf(work.Not())
                lo = m.NewIntVar(0, Pg - 1, f"ngxl_{code}_{d}")
                hi = m.NewIntVar(0, Pg - 1, f"ngxh_{code}_{d}")
                for sl, b in occ.items():
                    m.Add(lo <= sl).OnlyEnforceIf(b)
                    m.Add(hi >= sl).OnlyEnforceIf(b)
                m.Add(lo == 0).OnlyEnforceIf(work.Not())
                m.Add(hi == 0).OnlyEnforceIf(work.Not())
                gap = m.NewIntVar(0, Pg, f"ngxg_{code}_{d}")
                m.Add(gap >= hi - lo + 1 - cnt_d)
                m.Add(gap >= 0)
                soft_terms.append((wng, gap))

    # =========================================================
    # COURSE PERIOD-COHERENCE (spec §9) — per (section, course) with count >= 3:
    #   count 5   -> hard floor: >= 4 pieces in one dominant slot; dev 1 soft 4500
    #   count 4   -> hard floor: >= 3 aligned;                  dev 1 soft 4500
    #   count 3   -> soft only: doc + charge 3250 per deviation (no floor)
    #   count 1..2  -> no rule at all
    # Structural exemption (§9): a teacher's personal rules can make the floor
    # unattainable (e.g. day-pinned to 2 days) — the floor relaxes to the
    # statically attainable alignment, deviations beyond that stay hard.
    # Piece slots are shared per unit; combined units appear in each member
    # section's course group separately (each keeps its own ds).
    # coh_off: iterable of (sec, course) keys whose HARD floor is skipped
    # (tier-cascade fallback used by generate_context; soft charge stays).
    # =========================================================
    coh_off_set = set(coh_off or [])
    _coh_groups = {}
    for u in model["units"]:
        for sec in u["secs"]:
            c = u["courseBySec"].get(sec)
            if c is None:
                continue
            _coh_groups.setdefault((sec, c), set()).add(u["id"])
    build_from_context._last_coh_keys = []
    _lvl_of_sec = {s["key"]: (s.get("level") or "inter") for s in model["sections"]}
    for (sec, course), uids in sorted(_coh_groups.items()):
        is_inter = _lvl_of_sec.get(sec, "inter") == "inter"
        members = [u for u in model["units"] if u["id"] in sorted(uids)]
        pieces = [(u["id"], p) for u in members for p in range(u["count"])]
        cnt = len(pieces)
        if cnt < 3:
            continue
        build_from_context._last_coh_keys.append((sec, course))
        # static attainable alignment: max over slots s of sum-min(count,ndays)
        attain = 0
        for s in range(Pg):
            reach = 0
            for u in members:
                if s in _unit_slot_domain(u, R, model):
                    reach += min(u["count"], len(_unit_day_domain(u, R, model)))
            attain = max(attain, reach)
        forced = cnt - min(cnt, attain)
        floor = cnt - max(1, forced)
        if floor < 3:
            continue   # nothing above 3-in-one-slot attainable — leave it to the soft shuffle
        ds = m.NewIntVar(0, Pg - 1, f"cohds_{sec}_{course}")
        sames = []
        for (uid, p) in pieces:
            b = m.NewBoolVar(f"cohs_{sec}_{course}_{uid}_{p}")
            m.Add(piece_slots[uid][p] == ds).OnlyEnforceIf(b)
            m.Add(piece_slots[uid][p] != ds).OnlyEnforceIf(b.Not())
            sames.append(b)
        dev = m.NewIntVar(0, cnt, f"cohdev_{sec}_{course}")
        m.Add(dev == cnt - sum(sames))
        if cnt >= 4:
            if is_inter and (sec, course) not in coh_off_set:
                m.Add(sum(sames) >= floor)   # hard floor (inter only): at most (cnt-floor) deviations
            if is_inter:
                ch = m.NewIntVar(0, cnt, f"cohch_{sec}_{course}")
                m.Add(ch >= dev - forced)    # charge only deviations beyond the forced floor
                soft_terms.append((int(pen["periodConsistency45"]), ch))
            else:
                # BS: bonus alignment only — soft steer at the count-3 rate, no
                # hard floor, nothing documented (§9 scope: "a plus, never a requirement")
                soft_terms.append((int(pen["periodConsistency3"]), dev))
        else:
            soft_terms.append((int(pen["periodConsistency3"]), dev))

    # ---- soft: individual spread + even distribution
    if model["instructions"].get("softIndividualSpread"):
        for t, keys in teacher_keys.items():
            if t.startswith("PG:"):
                continue
            p1terms = [_eq_bool(m, k, d, f"sp1_{t}_{d}_{j}")
                       for d in range(Dg) for j, k in enumerate(keys)]
            plterms = [_eq_bool(m, k, (Pg - 1) * Dg + d, f"spl_{t}_{d}_{j}")
                       for d in range(Dg) for j, k in enumerate(keys)]
            if p1terms and plterms:
                b1 = m.NewBoolVar(f"sp1b_{t}")
                m.AddMaxEquality(b1, p1terms)
                b2 = m.NewBoolVar(f"splb_{t}")
                m.AddMaxEquality(b2, plterms)
                both = m.NewBoolVar(f"spb_{t}")
                m.AddBoolAnd([b1, b2]).OnlyEnforceIf(both)
                m.AddBoolOr([b1.Not(), b2.Not()]).OnlyEnforceIf(both.Not())
                soft_terms.append((pen["individualSpread"], both))
    for code, entry in R.items():
        rules = (entry or {}).get("rules") or {}
        if not rules.get("soft_even_distribution"):
            continue
        hsed = hardness_of(entry, "soft_even_distribution")
        if hsed == 0:
            continue
        units_of = [u for u in model["units"] if u["teacher"] == code]
        if not units_of:
            continue
        total = sum(u["count"] for u in units_of)
        cap = -(-total // max(1, Dg))
        vw = int(pen["evenDistribution"] * hsed / 100)
        for d in range(Dg):
            terms = [_eq_bool(m, dv, d, f"sed_{code}_{d}_{u['id']}_{p}")
                     for u in units_of for p, dv in enumerate(piece_days[u["id"]])]
            if not terms:
                continue
            ex = m.NewIntVar(0, total, f"sede_{code}_{d}")
            m.Add(ex >= sum(terms) - cap)
            soft_terms.append((vw, ex))

    # ---- new soft kinds (taxonomy v2)
    for code, entry in R.items():
        rules = (entry or {}).get("rules") or {}
        units_of = [u for u in model["units"] if u["teacher"] == code
                    or (u["group"] and code in (u["members"] or []))]
        if not units_of:
            continue
        for e in (rules.get("soft_prefer_free_slots_days") or []):
            hspfd = hardness_of(entry, "soft_prefer_free_slots_days")
            if hspfd == 0:
                continue
            w = int(pen["preferFreeSlot"] * hspfd / 100)
            dset = _dayset(e.get("days") or [])
            sset = _slotset(e.get("slots") or [])
            for u in units_of:
                for p in range(u["count"]):
                    for d in sorted(dset):
                        for sl in sorted(sset):
                            soft_terms.append((w,
                                               _eq_bool(m, piece_keys[u["id"]][p], sl * Dg + d,
                                                        f"spfd_{code}_{u['id']}_{p}_{d}_{sl}")))
        if rules.get("soft_compact_days"):
            hsccd = hardness_of(entry, "soft_compact_days")
            if hsccd == 0:
                continue
            wcd = int(pen["rule"] * hsccd / 100)
            # penalise interior holes per worked day (checker reports the exact
            # gap count; the optimiser uses the same width-minus-count proxy)
            for d in range(Dg):
                occ = {}
                for sl in range(Pg):
                    terms = [_eq_bool(m, piece_keys[u["id"]][p], sl * Dg + d,
                                      f"sccd_{code}_{d}_{sl}_{u['id']}_{p}")
                             for u in units_of for p in range(u["count"])]
                    if terms:
                        b = m.NewBoolVar(f"sccb_{code}_{d}_{sl}")
                        m.AddMaxEquality(b, terms)
                        occ[sl] = b
                if not occ:
                    continue
                cnt_d = m.NewIntVar(0, Pg, f"sccn_{code}_{d}")
                m.Add(cnt_d == sum(occ.values()))
                work = m.NewBoolVar(f"sccw_{code}_{d}")
                m.Add(cnt_d >= 1).OnlyEnforceIf(work)
                m.Add(cnt_d == 0).OnlyEnforceIf(work.Not())
                lo = m.NewIntVar(0, Pg - 1, f"sccl_{code}_{d}")
                hi = m.NewIntVar(0, Pg - 1, f"scch_{code}_{d}")
                for sl, b in occ.items():
                    m.Add(lo <= sl).OnlyEnforceIf(b)
                    m.Add(hi >= sl).OnlyEnforceIf(b)
                m.Add(lo == 0).OnlyEnforceIf(work.Not())
                m.Add(hi == 0).OnlyEnforceIf(work.Not())
                gap = m.NewIntVar(0, Pg, f"sccg_{code}_{d}")
                m.Add(gap >= hi - lo + 1 - cnt_d)
                m.Add(gap >= 0)
                soft_terms.append((wcd, gap))

    # ---- objective: shuffle + soft penalties
    obj = []
    for u in model["units"]:
        i, c = u["id"], u["count"]
        if c >= 3:
            for p in range(c):
                for q in range(p + 1, c):
                    w = 100000 if c == 5 else (10000 if c == 4 else 100)
                    obj.append(_neq_bool(m, piece_slots[i][p], piece_slots[i][q],
                                         f"cne_{i}_{p}_{q}") * w)
        elif c == 2:
            obj.append(_neq_bool(m, piece_slots[i][0], piece_slots[i][1], f"cne2_{i}") * 10)
    for weight, var in soft_terms:
        obj.append(var * weight)
    if objective == "default":
        m.Minimize(sum(obj))
    if collect is not None:
        collect["soft_terms"] = soft_terms
        collect["teacher_keys"] = teacher_keys
        collect["section_keys"] = section_keys
    return m, piece_slots, piece_days, piece_keys


def decode_context(solver, model, piece_slots, piece_days):
    grids = {s["key"]: [[None] * _solver.P for _ in range(_solver.D)] for s in model["sections"]}
    for u in model["units"]:
        i = u["id"]
        for p in range(u["count"]):
            s_ = solver.Value(piece_slots[i][p])
            d_ = solver.Value(piece_days[i][p])
            for sec in u["secs"]:
                grids[sec][d_][s_] = i
    return grids


def standalone_reference(population, time_per_seed=45, n_seeds=1):
    """Solve ONE population alone (no cross-population coupling) and return its
    best-known standalone figures for the fairness scorecard:
    {population, score, total, penalty, optimal}.

    None if the population has no sections yet (e.g. inter-2 before data entry).
    """
    import canonical
    import context_model as CM

    ctx = canonical.solver_context([population])
    model = CM.context_to_model(ctx)
    if not model["sections"]:
        return None
    ranked, optimal = generate_context(ctx, n_seeds=n_seeds, time_per_seed=time_per_seed, max_solutions=0)
    if not ranked:
        return None
    # fairness reference = the best SHUFFLE SCORE this population reaches alone.
    # Prefer fully-valid solutions (no soft penalties); only fall back to the
    # best total otherwise, and say so in the record.
    import context_model as CM
    model = CM.context_to_model(ctx)   # fresh model (grids get consumed per call)
    def own(g):
        m = CM.context_to_model(ctx)
        return CM.shuffle_score_partial(g, m)
    valid = [s for s in ranked if not s.get("penalty")]
    if valid:
        s = min(valid, key=lambda s: own(s["grids"]))
        fallback = False
    else:
        s = min(ranked, key=lambda s: own(s["grids"]))   # reference tracks the SCORE, not the total
        fallback = True
    return {"population": population, "score": own(s["grids"]),
            "total": s["total"], "penalty": s["penalty"], "optimal": bool(optimal),
            "allPenalized": fallback, "solutionsConsidered": len(ranked)}


_COH_TIER_CACHE = {}


def generate_context(context, n_seeds=2, time_per_seed=45, max_solutions=0):
    """Solve a context (canonical.solver_context output). Returns (ranked, any_optimal):
    ranked = list of {grids, score, penalty, violations, total}, best first.
    Each solution is validated by context_model.evaluate — issues reject,
    violations are documented + penalized into the total."""
    import context_model as CM
    model = CM.context_to_model(context)
    if not model["sections"]:
        return [], False   # nothing to solve (e.g. inter-2 before data entry)
    results = {}
    any_optimal = False

    # ==========================================================
    # Coherence demotion (spec §9.2): run with all INTERMEDIATE floors hard;
    # BS groups never carry floors. If CP-SAT proves INFEASIBLE for a seed
    # (the sanctioned infeasibility case), demote that pack's floors to soft,
    # persist it as context._cohExempt + data-signature cache, and re-solve.
    # ==========================================================
    model.setdefault("_coh_exempt", set())

    import hashlib, json as _json
    _sig_j = _json.dumps(
        {"secs": [(s["key"], sorted(s.get("effDays", s.get("activeDays", []) or [])))
                  for s in model["sections"]],
         "units": sorted((u["id"], u["teacher"], tuple(sorted(u["secs"])), u["count"],
                          (u["courseBySec"] or {}).get(u["secs"][0]))
                         for u in model["units"]),
         "R": model.get("constraints")},
        sort_keys=True, default=str)
    _popsig = (tuple(sorted(s["key"] for s in model["sections"])),
               hashlib.sha1(_sig_j.encode()).hexdigest()[:12])
    active_off = frozenset(_COH_TIER_CACHE.get(_popsig, ()))
    _all_inter_keys = frozenset(
        k for k in getattr(build_from_context, "_last_coh_keys", [])
        if {s["key"]: (s.get("level") or "inter") for s in model["sections"]}.get(k[0], "inter") == "inter")
    # pre-populate: _last_coh_keys only fills on build — build once cheaply
    if active_off or True:
        _ = build_from_context(model)
        _all_inter_keys = frozenset(
            k for k in getattr(build_from_context, "_last_coh_keys", [])
            if (model_sections_lvl := {s["key"]: (s.get("level") or "inter")
                                       for s in model["sections"]}).get(k[0], "inter") == "inter")
    for k in active_off:
        model["_coh_exempt"].add(k)
    if active_off:
        context["_cohExempt"] = sorted(map(list, active_off))

    for seed in range(n_seeds):
        built = build_from_context(model, coh_off=active_off)
        if built is None:
            return [], False
        m, piece_slots, piece_days, piece_keys = built

        class Collect(cp_model.CpSolverSolutionCallback):
            def __init__(self):
                super().__init__()
                self.found = []
            def on_solution_callback(self):
                try:
                    g = decode_context(self, model, piece_slots, piece_days)
                    ev = CM.evaluate(g, model)
                    if ev["issues"]:
                        return
                    key = _json_key(g)
                    if key in results:
                        return
                    sc = CM.shuffle_score(g, model)
                    results[key] = {
                        "grids": g, "score": sc,
                        "penalty": ev["penalty"], "violations": ev["violations"],
                        "total": sc + ev["penalty"],
                    }
                except Exception:
                    pass

        cb = Collect()
        solver = cp_model.CpSolver()
        solver.parameters.random_seed = 1000 + seed
        solver.parameters.max_time_in_seconds = time_per_seed
        solver.parameters.num_search_workers = int(os.environ.get("CP_SAT_WORKERS", "8"))
        status = solver.Solve(m, cb)
        if status == cp_model.INFEASIBLE and not active_off and _all_inter_keys:
            # sanctioned infeasibility (spec §9.2): inter floors cannot all hold
            # jointly — demote them to documented-soft and re-solve this seed once.
            active_off = _all_inter_keys
            for k in active_off:
                model["_coh_exempt"].add(k)
            context["_cohExempt"] = sorted(map(list, active_off))
            _COH_TIER_CACHE[_popsig] = active_off
            rebuilt = build_from_context(model, coh_off=active_off)
            if rebuilt is not None:
                m, piece_slots, piece_days, piece_keys = rebuilt
                cb = Collect()
                solver = cp_model.CpSolver()
                solver.parameters.random_seed = 1000 + seed
                solver.parameters.max_time_in_seconds = time_per_seed
                solver.parameters.num_search_workers = int(os.environ.get("CP_SAT_WORKERS", "8"))
                status = solver.Solve(m, cb)
        if status == cp_model.OPTIMAL:
            any_optimal = True

    ranked = sorted(results.values(), key=lambda x: (x["penalty"] > 0, x["total"]))
    if max_solutions and max_solutions > 0:
        ranked = ranked[:max_solutions]
    return ranked, any_optimal


def _json_key(grids):
    import json as _j
    return _j.dumps({k: [x for row in v for x in row] for k, v in grids.items()},
                    sort_keys=True)


# ---------------------------------------------------------------- targeted repair
def _slot_domain_vals(m, var):
    """Flatten an IntVar's domain to a python list of ints."""
    return list(var.Proto().domain)


def _restrict_to(m, var, keep, name):
    m.AddLinearExpressionInDomain(var, cp_model.Domain.FromValues(sorted(keep)))


def _soft_fix_constraints(m, model, piece_slots, piece_days, picked):
    """Hard constraints that erase ONE soft violation card (by family).

    picked: a structured violation ({rule, sig, units, ...}) from
    context_model.analyze_structured. Returns a human note of what was
    enforced, or None when the family is objective-handled only."""
    i = None  # silence linters
    sig = picked.get("sig") or ""
    rule = picked.get("rule") or ""
    units = {u["id"]: u for u in model["units"]}
    focus = set(picked.get("units") or [])
    R = model["constraints"]

    teacher_of = None
    fam, _, rest = sig.partition("@")
    key = rest
    if sig.startswith("facrule@"):
        code, _, rule_key = rest.partition(":")
        teacher_of, fam_key = code, rule_key
    elif sig.startswith("softpref@"):
        teacher_of, fam_key = rest, "soft_prefer_free_slots"
    elif sig.startswith("softspread@"):
        teacher_of, fam_key = rest, "soft_individual_spread"
    elif sig.startswith("softeven@"):
        teacher_of, fam_key = rest, "soft_even_distribution"
    elif sig.startswith("soft_dayex@"):
        return None   # consecutive-day prefs stay objective-
    else:
        return None
    if teacher_of not in R:
        return None
    rules = (R.get(teacher_of) or {}).get("rules") or {}
    my = [u for u in model["units"]
          if u["teacher"] == teacher_of or (u["members"] and teacher_of in u["members"])]
    if not my:
        return None

    def ban_pairs(units_list, dayset, slotset, tag):
        for u in units_list:
            i = u["id"]
            for p in range(u["count"]):
                for d in dayset:
                    for s in slotset:
                        b1 = _eq_bool(m, piece_days[i][p], d, f"fx_{tag}_{i}_{p}_{d}_{s}")
                        b2 = _eq_bool(m, piece_slots[i][p], s, f"fs_{tag}_{i}_{p}_{d}_{s}")
                        m.AddBoolOr([b1.Not(), b2.Not()])

    def slots_keep(units_list, allowed, tag):
        for u in units_list:
            i = u["id"]
            for p in range(u["count"]):
                base = list(piece_slots[i][p].Proto().domain)
                _restrict_to(m, piece_slots[i][p], {v for v in base if v in allowed}, f"rk_{tag}_{i}_{p}")

    def days_keep(units_list, allowed, tag, units_by_stream=None, stream=None):
        for u in units_list:
            i = u["id"]
            for p in range(u["count"]):
                base = list(piece_days[i][p].Proto().domain)
                _restrict_to(m, piece_days[i][p], {v for v in base if v in allowed}, f"rd_{tag}_{i}_{p}")

    from solver import _slotset, _dayset, SLOT_OF
    if fam_key == "forbidden_slots" and rules.get("forbidden_slots"):
        ban_pairs(my, list(range(model["days"])), _slotset(rules["forbidden_slots"]), "fs")
        return "soft forbidden slots cleared for %s" % teacher_of
    if fam_key == "allowed_slots" and rules.get("allowed_slots"):
        slots_keep(my, _slotset(rules["allowed_slots"]), "as")
        return "soft allowed-slots restored for %s" % teacher_of
    if fam_key == "forbidden_days" and rules.get("forbidden_days"):
        ban_pairs(my, _dayset(rules["forbidden_days"]), list(range(model["periods"])), "fd")
        return "soft forbidden days cleared for %s" % teacher_of
    if fam_key == "allowed_days" and rules.get("allowed_days"):
        days_keep(my, _dayset(rules["allowed_days"]), "ad")
        return "soft allowed-days restored for %s" % teacher_of
    if fam_key == "forbidden_slots_on_days":
        for e in (rules.get("forbidden_slots_on_days") or []):
            ban_pairs(my, _dayset(e["days"]), _slotset(e["slots"]), "fsd")
        return "soft day/slot bans cleared for %s" % teacher_of
    if fam_key == "allowed_slots_in_stream":
        for e in (rules.get("allowed_slots_in_stream") or []):
            us = [u for u in my if any(_sec_stream(sec) == e["stream"] for sec in u["secs"])]
            slots_keep(us, _slotset(e["slots"]), "ass")
        return "soft stream slot windows restored for %s" % teacher_of
    if fam_key == "allowed_days_in_stream":
        for e in (rules.get("allowed_days_in_stream") or []):
            us = [u for u in my if any(_sec_stream(sec) == e["stream"] for sec in u["secs"])]
            days_keep(us, _dayset(e["days"]), "ads")
        return "soft stream day windows restored for %s" % teacher_of
    if fam_key == "subject_slots":
        for e in (rules.get("subject_slots") or []):
            us = [u for u in my if any(c == e["subject"] for c in u["courseBySec"].values())]
            slots_keep(us, _slotset(e["slots"]), "ss")
        return "soft subject slot windows restored for %s" % teacher_of
    if fam_key == "subject_forbidden_days":
        for e in (rules.get("subject_forbidden_days") or []):
            us = [u for u in my if any(c == e["subject"] for c in u["courseBySec"].values())]
            ban_pairs(us, _dayset(e["days"]), list(range(model["periods"])), "sfd")
        return "soft subject day bans cleared for %s" % teacher_of
    if fam_key == "subject_slot_days":
        for e in (rules.get("subject_slot_days") or []):
            us = [u for u in my if any(c == e["subject"] for c in u["courseBySec"].values())]
            slots_keep(us, {SLOT_OF[e["slot"]]}, "ssd")
            days_keep(us, _dayset(e["days"]), "ssd")
        return "soft subject slot/day pin restored for %s" % teacher_of
    if fam_key == "soft_prefer_free_slots" and rules.get("soft_prefer_free_slots"):
        ban_pairs(my, list(range(model["days"])), _slotset(rules["soft_prefer_free_slots"]), "spf")
        return "preferred-free slots vacated for %s" % teacher_of
    if fam_key == "min_days_in_slot":
        for e in (rules.get("min_days_in_slot") or []):
            si = SLOT_OF[e["slot"]]
            dayflags = []
            for d in range(model["days"]):
                pflags = [_eq_bool(m, piece_slots[u["id"]][p], si, f"mds_{u['id']}_{p}_{d}")
                          for u in my for p in range(u["count"])]
                df = m.NewBoolVar(f"mdf_{si}_{d}")
                m.AddMaxEquality(df, pflags)
                dayflags.append(df)
            m.Add(sum(dayflags) >= (e.get("min_days") or 1))
        return "minimum engagement days restored for %s" % teacher_of
    if fam_key == "min_days_engaged":
        dayflags = []
        for d in range(model["days"]):
            pflags = [_eq_bool(m, piece_days[u["id"]][p], d, f"mde_{u['id']}_{p}_{d}")
                      for u in my for p in range(u["count"])]
            df = m.NewBoolVar(f"mdef_{d}")
            m.AddMaxEquality(df, pflags)
            dayflags.append(df)
        m.Add(sum(dayflags) >= rules["min_days_engaged"])
        return "minimum days engaged restored for %s" % teacher_of
    if fam_key == "stream_slots_required":
        for e in (rules.get("stream_slots_required") or []):
            us = [u for u in my if any(_sec_stream(sec) == e["stream"] for sec in u["secs"])]
            if not us:
                continue
            for sl in e["slots"]:
                si = SLOT_OF[sl]
                dayflags = []
                for d in range(model["days"]):
                    pflags = [_eq_bool(m, piece_slots[u["id"]][p], si, f"ssr_{u['id']}_{p}_{d}")
                              for u in us for p in range(u["count"])]
                    df = m.NewBoolVar(f"ssrf_{si}_{d}")
                    m.AddMaxEquality(df, pflags)
                    dayflags.append(df)
                m.Add(sum(dayflags) >= 4)
        return "stream slot engagement restored for %s" % teacher_of
    if fam_key == "soft_individual_spread":
        p1 = [_eq_bool(m, piece_slots[u["id"]][p], 0, f"ssp1_{u['id']}_{p}")
              for u in my for p in range(u["count"])]
        pl = [_eq_bool(m, piece_slots[u["id"]][p], model["periods"] - 1, f"sspl_{u['id']}_{p}")
              for u in my for p in range(u["count"])]
        b1, b2 = m.NewBoolVar("ssb1"), m.NewBoolVar("ssb2")
        m.AddMaxEquality(b1, p1)
        m.AddMaxEquality(b2, pl)
        m.AddBoolOr([b1.Not(), b2.Not()])
        return "P1/last-period spread removed for %s" % teacher_of
    return None   # soft_even_distribution & friends: objective-handled only


def repair_context(context, timetable, focus=None, mode="instance",
                   time_per_tier=12, workers=None):
    """Targeted repair of a manually-entered timetable (a full shift).

    context:    canonical.solver_context(populations)
    timetable:  {section: dayRows[[subject, teacher]]} display cells
    focus:      {"kind": "hard"|"soft", "index": int} — the insight being fixed
                (None = repair all hard issues)
    mode:       "instance" (only the focused card's units freed first) or
                "type" (all cards of the same signature freed at once)

    All structural/hard constraints stay infeasible-hard; the entered grid is
    pinned cell-by-cell and only units implicated in the focus (and their
    neighbourhood, escalating through tiers) may move. The objective is
    minimal diff: every cell kept at its entered position costs 0.

    Returns {"ok": bool, ...repaired timetable, diff report, before/after
    metrics...} or {"ok": False, "reason": ...} when all tiers are infeasible.
    """
    import time as _time
    import context_model as CM
    import canonical as _canon
    t0 = _time.time()
    model = CM.context_to_model(context)
    grids0, unmatched = CM.placements_from_display(timetable, model)
    ev0 = CM.analyze_structured(grids0, model)
    Dg, Pg = model["days"], model["periods"]

    # per-unit entered placements (deduped over the unit's sections)
    entered = {}
    stray_free = set()
    for u in model["units"]:
        cells = set()
        for sec in u["secs"]:
            g = grids0.get(sec) or []
            for d in range(Dg):
                for s in range(Pg):
                    if d < len(g) and s < len(g[d]) and g[d][s] == u["id"]:
                        cells.add((d, s))
        entered[u["id"]] = sorted(cells)

    hard_units = set()
    for det in ev0["issues_detail"]:
        hard_units.update(det["units"])

    picked = None
    focus_units = set()
    if focus:
        kind = (focus or {}).get("kind", "hard")
        pool = ev0["violations"] if kind == "soft" else ev0["issues_detail"]
        try:
            idx = int(focus.get("index", 0))
        except Exception:
            idx = -1
        if 0 <= idx < len(pool):
            picked = pool[idx]
            focus_units = set(picked.get("units") or [])
            if mode == "type":
                sig = picked.get("sig")
                for it in pool:
                    if it.get("sig") == sig:
                        focus_units.update(it.get("units") or [])

    def neighbors(seed):
        out = set(seed)
        teachers = {model["units"][i]["teacher"] for i in seed}
        secs = set()
        for i in seed:
            secs.update(model["units"][i]["secs"])
        for u in model["units"]:
            if u["id"] in out:
                continue
            if u["teacher"] in teachers or any(s in secs for s in u["secs"]):
                out.add(u["id"])
        return out

    tiers = []
    tier1 = set(focus_units) | hard_units | stray_free
    tiers.append(("strict", tier1))
    tiers.append(("local", neighbors(tier1)))
    tiers.append(("open", {u["id"] for u in model["units"]}))
    tier_budgets = [time_per_tier, time_per_tier + 5, time_per_tier * 2]
    tier_names = ["strict (focused cells only)", "local (involved teachers & sections)",
                  "open (min-diff re-solve of the shift)"]

    score0 = CM.shuffle_score(grids0, model)
    diff0 = None
    for tnum, (tname, free) in enumerate(tiers):
        collect = {}
        built = build_from_context(model, objective="none", collect=collect)
        if built is None:
            continue
        m, piece_slots, piece_days, piece_keys = built
        chg_terms = []
        auto_freed = []
        for u in model["units"]:
            i = u["id"]
            cells = entered[i]
            complete = len(cells) == u["count"]
            must_free = i in free
            wgt = 1 if i in focus_units else (3 if i in hard_units else (
                  6 if tname == "local" else (20 if tname == "open" else 3)))
            if complete:
                # defensive precheck: never pin a piece outside the solver's own domains
                sd = _unit_slot_domain(u, model["constraints"], model)
                dd = _unit_day_domain(u, model["constraints"], model)
                if any(s not in sd or d not in dd for (d, s) in cells):
                    must_free = True
                    if i not in free:
                        auto_freed.append(i)
            if complete and not must_free:
                for p, (d, s) in enumerate(cells):
                    m.Add(piece_days[i][p] == d)
                    m.Add(piece_slots[i][p] == s)
            elif complete:
                for p, (d, s) in enumerate(cells):
                    chg = m.NewBoolVar(f"chg_{i}_{p}")
                    m.Add(piece_days[i][p] == d).OnlyEnforceIf(chg.Not())
                    m.Add(piece_slots[i][p] == s).OnlyEnforceIf(chg.Not())
                    chg_terms.append((wgt, chg))
            # units with incomplete/over-complete entered placements float free

        fix_note = None
        if picked and focus and (focus or {}).get("kind") == "soft":
            fix_note = _soft_fix_constraints(m, model, piece_slots, piece_days, picked)

        obj = [chg * (100 * w) for (w, chg) in chg_terms]
        for wgt, var in (collect.get("soft_terms") or []):
            obj.append(var * min(wgt, 300))
        m.Minimize(sum(obj) if obj else 0)

        solver = cp_model.CpSolver()
        solver.parameters.random_seed = 1000
        solver.parameters.max_time_in_seconds = tier_budgets[tnum]
        solver.parameters.num_search_workers = int(
            workers or os.environ.get("CP_SAT_WORKERS", "8"))
        status = solver.Solve(m)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            continue
        grids1 = decode_context(solver, model, piece_slots, piece_days)
        ev1 = CM.analyze_structured(grids1, model)
        if ev1["issues"]:
            continue   # do not ship an invalid repair; escalate the tier

        tt1 = _canon.timetable_from_grids(grids1, model)
        diff = []
        for section in model["sections"]:
            k = section["key"]
            rows0 = timetable.get(k) or []
            rows1 = tt1.get(k) or []
            for d in range(Dg):
                r0 = rows0[d] if d < len(rows0) else []
                r1 = rows1[d] if d < len(rows1) else []
                for s in range(Pg):
                    before = r0[s] if s < len(r0) else ["", ""]
                    after = r1[s] if s < len(r1) else ["", ""]
                    b = [(before[0] or "").strip() if len(before) > 0 else "",
                         (before[1] or "").strip() if len(before) > 1 else ""]
                    b = [x if x and not x.lower().startswith("library") else "" for x in b]
                    a2 = [x if x and not x.lower().startswith("library") else "" for x in after]
                    if b != a2:
                        diff.append({"section": k, "day": d, "slot": s,
                                     "before": before, "after": after})
        return {
            "ok": True,
            "tier": tier_names[tnum], "tier_index": tnum,
            "elapsed": round(_time.time() - t0, 1),
            "changed": len(diff), "diff": diff,
            "timetable": tt1,
            "unmatched": unmatched,
            "issues_before": ev0["issues"],
            "issues_after": ev1["issues"],
            "violations_before": ev0["violations"],
            "violations_after": ev1["violations"],
            "penalty_before": ev0["penalty"], "penalty_after": ev1["penalty"],
            "score_before": score0, "score_after": CM.shuffle_score(grids1, model),
            "auto_freed": auto_freed,
            "fix_enforced": fix_note,
            "mode": mode,
            "focus": (picked or {}).get("text") or (picked or {}).get("detail"),
        }
    return {"ok": False, "reason": "repair infeasible at every tier",
            "elapsed": round(_time.time() - t0, 1),
            "issues_before": ev0["issues"],
            "violations_before": ev0["violations"],
            "penalty_before": ev0["penalty"], "score_before": score0,
            "unmatched": unmatched}
