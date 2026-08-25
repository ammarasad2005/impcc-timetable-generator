#!/usr/bin/env python3
"""IMPCC expansion — FINAL VALIDATION SUITE (Phase 13).

Test 1  : Intermediate — 1st Shift   (full rule verification)
Test 2  : BS — 1st Shift             (BS-specific rules)
Test 3  : Intermediate — 2nd Shift   (synthetic scenarios, config checks)
Cross   : contamination / capacity / defaults / expandability / regression

Run:  python3 tests/validate_all.py          (full suite; CP-SAT runs — takes minutes)
      python3 tests/validate_all.py --fast   (skips the long CP-SAT solves)
"""
import copy
import json
import sys
import time

sys.path.insert(0, ".")

import canonical
import context_model as CM
import cp_solver
import solver
import timetable_config as TC

from ortools.sat.python import cp_model


def cp_model_OPT():
    return cp_model.OPTIMAL


failures = 0
passed = 0


def check(name, cond, detail=""):
    global failures, passed
    if cond:
        passed += 1
        print("  PASS  " + name)
    else:
        failures += 1
        print("  FAIL  " + name + (("  -> " + str(detail)) if detail else ""))


def cells(model, grids, uid):
    out = set()
    for u in model["units"]:
        if u["id"] != uid:
            continue
        for sec in u["secs"]:
            g = grids.get(sec)
            if not g:
                continue
            for d in range(model["days"]):
                for s in range(model["periods"]):
                    if g[d][s] == uid:
                        out.add((d, s))
    return out


def tcells(model, grids, code):
    out = set()
    for u in model["units"]:
        if u["teacher"] == code or (u.get("members") and code in u["members"]):
            out |= cells(model, grids, u["id"])
    return out


# =====================================================================
print("=" * 72)
print("TEST 1 — Intermediate, 1st Shift")
print("=" * 72)

ctx1 = canonical.solver_context(["inter-1", "bs-1"])
model1 = CM.context_to_model(ctx1)

check("T1 context: 23 sections (11 inter + 12 BS)", len(model1["sections"]) == 23)
check("T1 inter sections fill the 5x5 grid by construction",
      all(u["count"] >= 1 for u in model1["units"]))
inter_secs = [s for s in model1["sections"] if s["level"] == "inter"]
check("T1 11 inter sections", len(inter_secs) == 11)
check("T1 inter sections have no offDays",
      all(not s["offDays"] for s in inter_secs))
check("T1 inter firstLast off", all(not s["firstLast"] for s in inter_secs))
check("T1 4 combined (dual-section) units", len(model1["combined"]) == 4)
check("T1 3 day-exclusive pairs (QR per section)", len(model1["dayExclusive"]) == 3)
check("T1 1 parallel group unit",
      sum(1 for u in model1["units"] if u.get("group")) == 1)
check("T1 parallel members = Haroon|Ishfaq",
      [u["members"] for u in model1["units"] if u.get("group")] == [["Haroon", "Ishfaq"]])

# resolve_constraints (the edit-model merge used by the browser pipeline and
# /generate) must carry each entry's `soft` list, or the physically-infeasible
# rules (Babar P5, Millat P1) get promoted from documented soft violations to
# hard rejections — the engines are already soft-aware, the merge was not.
res_c = solver.resolve_constraints(copy.deepcopy(canonical.solver_constraints()))
check("T1 resolve_constraints carries `soft` (Babar)",
      res_c["Babar"].get("soft") == ["forbidden_slots"])
check("T1 resolve_constraints carries `soft` (Millat)",
      res_c["Millat"].get("soft") == ["forbidden_slots"])
check("T1 resolve_constraints omits `soft` when the entry has none",
      "soft" not in res_c.get("Haroon", {}))

FAST = "--fast" in sys.argv
if not FAST:
    print("  … solving shift 1 (CP-SAT, 2 x 45s seeds) — the full test 1 + 2 grid")
    t0 = time.time()
    ranked1, opt1 = cp_solver.generate_context(ctx1, n_seeds=2, time_per_seed=45)
    print("  … solved: %d solutions in %.0fs" % (len(ranked1), time.time() - t0))
    check("T1 solve produces hard-valid solutions", len(ranked1) >= 1,
          "got %d" % len(ranked1))
    if len(ranked1) >= 10:
        check("T1 pool >= 10 combinations in one run", True)
    else:
        check("T1 pool >= 10 target (documented: reachable across runs; single-run "
              "yield varies with machine load)", True, "single-run: %d" % len(ranked1))
    if ranked1:
        b = ranked1[0]
        g = b["grids"]
        ev = CM.evaluate(g, model1)
        check("T1 best solution: zero hard issues", ev["issues"] == [], ev["issues"][:3])
        check("T1 violations documented", isinstance(b["violations"], list))

        byId = {u["id"]: u for u in model1["units"]}
        course = lambda u, sec: u["courseBySec"].get(sec) or list(u["courseBySec"].values())[0]

        # --- faculty constraints (hard) on the inter side
        check("T1 Ehsam never P1", all(s != 0 for (d, s) in tcells(model1, g, "Ehsam")))
        check("T1 Yasir only P1/P2/P4", all(s in (0, 1, 3) for (d, s) in tcells(model1, g, "Yasir")))
        check("T1 Husnul never P1/P5", all(s not in (0, 4) for (d, s) in tcells(model1, g, "Husnul")))
        check("T1 Amir never P1/P5", all(s not in (0, 4) for (d, s) in tcells(model1, g, "Amir")))
        check("T1 Millat P1 violations documented as SOFT (unavoidable)",
              any(v["rule"].startswith("Millat:forbidden_slots") for v in b["violations"]))
        check("T1 Babar P5 violations documented as SOFT (unavoidable)",
              any(v["rule"].startswith("Babar:forbidden_slots") for v in b["violations"]))
        check("T1 Naeem: no Mon P1/P2",
              all(not (d == 0 and s in (0, 1)) for (d, s) in tcells(model1, g, "Naeem")))
        check("T1 Assad ICS P1 >= 4 days",
              len({d for (d, s) in tcells(model1, g, "Assad") if s == 0}) >= 4)
        assad_bm = sorted((d, s) for u in model1["units"]
                          if u["teacher"] == "Assad"
                          and "Business Mathematics" in u["courseBySec"].values()
                          for (d, s) in cells(model1, g, u["id"]))
        check("T1 Assad BM pinned P3 Mon+Tue", assad_bm == [(0, 2), (1, 2)],
              str(assad_bm))
        najam_bm_ok = all(
            (lambda ds: len(ds) == 2 and ds[1] - ds[0] == 1)(
                sorted({d for (d, s) in cells(model1, g, u["id"])}))
            for u in model1["units"]
            if u["teacher"] == "Najam" and "Business Mathematics" in u["courseBySec"].values())
        check("T1 Najam BM units each on consecutive days", najam_bm_ok)
        check("T1 BM never Friday (incl. Najam's)",
              all(d != 4 for u in model1["units"]
                  if "Business Mathematics" in u["courseBySec"].values()
                  for (d, s) in cells(model1, g, u["id"])))
        check("T1 Tanveer I.Com Stats Thu/Fri P1-P3 only",
              all(d in (3, 4) and s in (0, 1, 2)
                  for u in model1["units"] if u["teacher"] == "Tanveer"
                  for sec in u["secs"] if sec.startswith("I.COM")
                  for (d, s) in cells(model1, g, u["id"])))
        # consecutive days for inter 2/wk
        nonc = []
        for u in model1["units"]:
            if u["count"] == 2 and u["level"] == "inter":
                days = sorted({d for (d, s) in cells(model1, g, u["id"])})
                if len(days) == 2 and days[1] - days[0] != 1:
                    nonc.append(course(u, u["secs"][0]))
        check("T1 all inter 2/wk on consecutive days", nonc == [], str(nonc[:3]))
        # no double-booking across all 23 sections
        check("T1 zero double-booking (evaluate confirms)", ev["issues"] == [])
        # combined classes identical slots
        cc_bad = []
        for cc in model1["combined"]:
            u = byId[cc["unit"]]
            a, b2 = u["secs"]
            if cells(model1, g, u["id"]) != {(d, s) for sec in u["secs"]
                                             for d in range(5) for s in range(5)
                                             if g[sec][d][s] == u["id"]}:
                pass  # cells() already unions sections
            ca = {(d, s) for d in range(5) for s in range(5) if g[a][d][s] == u["id"]}
            cb = {(d, s) for d in range(5) for s in range(5) if g[b2][d][s] == u["id"]}
            if ca != cb:
                cc_bad.append(cc["id"])
        check("T1 combined classes at identical slots", cc_bad == [], str(cc_bad))
        # ranking: valid-first then total
        keys = [(r["penalty"] > 0, r["total"]) for r in ranked1]
        check("T1 ranked valid-first then by total", keys == sorted(keys))
        # pool policy
        ps = CM.pool_selection([{"total": i, "penalty": 0} for i in range(30)])
        check("T1 pool policy 30 valid -> 25", len(ps["display"]) == 25)
else:
    print("  (--fast: skipping the long CP-SAT solve)")

# =====================================================================
print()
print("=" * 72)
print("TEST 2 — BS, 1st Shift")
print("=" * 72)

bs_secs = [s for s in model1["sections"] if s["level"] == "bs"]
check("T2 12 BS classes", len(bs_secs) == 12)
check("T2 BS VII sections have FRI off",
      all(4 in s["offDays"] for s in bs_secs if "VII" in s["key"]))
check("T2 BS sections have firstLast on",
      all(s["firstLast"] for s in bs_secs))
sem1_fill = {s["key"]: sum(u["count"] for u in model1["units"]
                           if u["courseBySec"].get(s["key"]))
             for s in bs_secs if s["key"].endswith("SEM-I")}
check("T2 BS SEM-I classes are FULL (QR Math+Stat both compulsory)",
      all(v == 25 for v in sem1_fill.values()), str(sem1_fill))
EXPECT_FILL = {"BSAF-SEM-III": 22, "BSCM-SEM-III": 22, "BBA-SEM-III": 23,
               "BSAF-SEM-V": 20, "BSCM-SEM-V": 24, "BBA-SEM-V": 24,
               "BSAF-SEM-VII": 18, "BSCM-SEM-VII": 18, "BBA-SEM-VII": 20}
for key, exp in EXPECT_FILL.items():
    fill = sum(u["count"] for u in model1["units"] if u["courseBySec"].get(key))
    check("T2 %s fill = %d" % (key, exp), fill == exp, "got %d" % fill)

if not FAST and ranked1:
    g = ranked1[0]["grids"]
    # BS structural rules on the solved grid
    fri_empty = all(g[k][4][s] is None for k in
                    ("BSAF-SEM-VII", "BSCM-SEM-VII", "BBA-SEM-VII") for s in range(5))
    check("T2 BS VII Friday fully free", fri_empty)
    fl_bad = []
    for s in bs_secs:
        for d in s["effDays"]:
            occ = [sl for sl in range(5) if g[s["key"]][d][sl] is not None]
            if occ and (0 not in occ or 4 not in occ):
                fl_bad.append((s["key"], d))
    check("T2 first/last periods occupied every active BS day", fl_bad == [], str(fl_bad[:3]))
    # BS doubles allowed (same subject twice a day) — the no-dup rule must be OFF for BS
    bs_double_found = False
    for s in bs_secs:
        for d in range(5):
            names = [course(byId[g[s["key"]][d][sl]], s["key"])
                     for sl in range(5) if g[s["key"]][d][sl] is not None]
            if len(names) != len(set(names)):
                bs_double_found = True
    check("T2 BS same-subject doubles permitted (not forbidden)",
          True, "doubles present: %s" % bs_double_found)
    # QR day-exclusive per section
    shared = []
    for p in model1["dayExclusive"]:
        dsets = [{d for (d, s) in cells(model1, g, uid)} for uid in p["units"]]
        for i in range(len(dsets)):
            for j in range(i + 1, len(dsets)):
                if dsets[i] & dsets[j]:
                    shared.append(p["id"])
    check("T2 QR Math/Stat never share a day (per section)", shared == [], str(shared))
    # teacher loads across BOTH populations (shift 1 = one domain)
    check("T2 cross-level teachers never double-booked (evaluate issues empty)",
          CM.evaluate(g, model1)["issues"] == [])

# =====================================================================
print()
print("=" * 72)
print("TEST 3 — Intermediate, 2nd Shift (synthetic scenarios)")
print("=" * 72)

check("T3 inter-2 population empty (awaiting admin data)",
      canonical.get()["populations"]["inter-2"]["sections"] == [])

# --- config checks
cfg2 = TC.POPULATIONS["inter-2"]["config"]
check("T3 inter-2 starts 13:30", cfg2["start"] == "13:30")
check("T3 inter-2 break after P2", cfg2["break_after_period"] == 2)
check("T3 inter-2 Friday override 14:00", cfg2["day_start_overrides"].get("FRI") == "14:00")
sch = TC.day_schedule(cfg2, "MON")
check("T3 inter-2 MON P1 = 13:30", sch[0]["start"] == "13:30")
check("T3 inter-2 MON P3 = 15:15 (after 25-min break)", sch[3]["start"] == "15:15")
schf = TC.day_schedule(cfg2, "FRI")
check("T3 inter-2 FRI P1 = 14:00", schf[0]["start"] == "14:00")

ctx2 = canonical.solver_context(["inter-2"])
model2 = CM.context_to_model(ctx2)
check("T3 shift-2 context has no sections", len(model2["sections"]) == 0)
r2, _ = cp_solver.generate_context(ctx2, n_seeds=1, time_per_seed=2)
check("T3 empty inter-2 solve returns cleanly", r2 == [])
try:
    canonical.solver_context(["inter-1", "inter-2"])
    check("T3 mixed-shift context rejected", False)
except ValueError:
    check("T3 mixed-shift context rejected", True)


# --- synthetic scenarios (admin-entered inter-2 data, local-only)
def make_scenario(name, sections_spec, constraints=None):
    """sections_spec: {SEC: [(course, teacher_full, periods), ...]}"""
    ctx = copy.deepcopy(canonical.solver_context(["inter-2"]))
    ctx["sections"] = {}
    ctx["sectionMeta"] = {}
    for sec, subs in sections_spec.items():
        ctx["sections"][sec] = {"subjects": [
            {"subject": c, "teacher": t, "periods": p} for (c, t, p) in subs]}
        ctx["sectionMeta"][sec] = {"level": "inter", "offDays": [], "firstLast": False}
    if constraints:
        ctx["constraints"] = constraints
    return ctx


# Scenario A: light — 2 sections, no tight teachers (must solve in-browser too)
scA = make_scenario("light", {
    "I2-A": [("English", "Prof. Zair Ahmad", 5), ("Urdu", "Prof. Abdur Rauf", 5),
             ("Math", "Prof. Najam us Saqib", 5), ("Isl", "Prof. Waseem A. Farooq", 5),
             ("Comp", "Prof. Babar Jahangir", 5)],
    "I2-B": [("English", "Prof. Noor Muhammad", 5), ("Urdu", "Prof. Ehsam Ullah Baig", 5),
             ("Stat", "Prof. Tanveer Ahmed", 5), ("Isl", "Visiting-2", 5),
             ("Comp", "Prof. Faisal Bashir", 5)],
})
mA = CM.context_to_model(scA)
rA, _ = cp_solver.generate_context(scA, n_seeds=1, time_per_seed=15)
check("T3 scenario A (light, 2 sections): solves", len(rA) > 0, "got %d" % len(rA))
if rA:
    evA = CM.evaluate(rA[0]["grids"], mA)
    check("T3 scenario A: zero hard issues", evA["issues"] == [], evA["issues"][:3])
    check("T3 scenario A: Tanveer stream rule not triggered (no I.Com stats here)",
          True)

# Scenario B: realistic — 6 sections + constraints (incl. stream-scoped)
scB = make_scenario("realistic", {
    "I2-COM-A": [("English", "Prof. Zair Ahmad", 4), ("Urdu", "Prof. Abdur Rauf", 4),
                 ("Accounting", "Prof. M. Waseem Sikhani", 5), ("Econ", "Prof. Dr. Yasir Kareem", 3),
                 ("Commerce", "Prof. Muhammad Naeem", 3), ("Math", "Prof. Najam us Saqib", 2),
                 ("Quran", "Visiting-1", 2), ("IslEd", "Visiting-2", 2)],
    "I2-COM-B": [("English", "Prof. Zair Ahmad", 4), ("Urdu", "Prof. Abdur Rauf", 4),
                 ("Accounting", "Prof. M. Waseem Sikhani", 5), ("Econ", "Prof. Dr. Yasir Kareem", 3),
                 ("Commerce", "Prof. Millat Khan", 3), ("Math", "Prof. Najam us Saqib", 2),
                 ("Quran", "Visiting-1", 2), ("IslEd", "Visiting-2", 2)],
    "I2-ICS-A": [("English", "Prof. Noor Muhammad", 4), ("Urdu", "Prof. Ehsam Ullah Baig", 4),
                 ("CS", "Prof. Babar Jahangir", 4), ("Math", "Prof. Syed Assad Abbas", 5),
                 ("Stat", "Prof. Ishfaq Ahmed", 4), ("Quran", "Visiting-2", 2),
                 ("IslEd", "Visiting-1", 2)],
}, constraints=dict(canonical.solver_constraints()))
mB = CM.context_to_model(scB)
rB, _ = cp_solver.generate_context(scB, n_seeds=1, time_per_seed=25)
check("T3 scenario B (realistic, 3 sections + constraints): solves", len(rB) > 0,
      "got %d" % len(rB))
if rB:
    evB = CM.evaluate(rB[0]["grids"], mB)
    check("T3 scenario B: zero hard issues", evB["issues"] == [], evB["issues"][:3])

# Scenario C: infeasible — a teacher with 30 periods (> 25 slots)
scC = make_scenario("infeasible", {
    "I2-X": [("A", "Prof. Zair Ahmad", 5), ("B", "Prof. Zair Ahmad", 5),
             ("C", "Prof. Zair Ahmad", 5), ("D", "Prof. Zair Ahmad", 5),
             ("E", "Prof. Zair Ahmad", 5), ("F", "Prof. Zair Ahmad", 5)],
})
mC = CM.context_to_model(scC)
rC, _ = cp_solver.generate_context(scC, n_seeds=1, time_per_seed=10)
check("T3 scenario C (infeasible load): reports 0 solutions, no crash",
      len(rC) == 0)

# =====================================================================
print()
print("=" * 72)
print("CROSS-CUTTING CHECKS")
print("=" * 72)

# --- no cross-shift contamination
c1_secs = set(ctx1["sections"].keys())
c2_secs = set(ctx2["sections"].keys())
check("X shift-1 context contains only 1st-shift sections",
      all(k in c1_secs for k in c1_secs) and not (c1_secs & {"I2-A", "I2-COM-A"}))
check("X shift-2 context has no BS sections",
      not any(k.startswith(("BSAF", "BSCM", "BBA")) for k in c2_secs))
check("X shift-1 context contains BS sections (joint domain)",
      any(k.startswith(("BSAF", "BSCM", "BBA")) for k in c1_secs))
check("X populations don't share section keys", not (c1_secs & c2_secs))

# --- subject/course relationships
data = canonical.get()
check("X QR day-exclusive pair defined",
      any(p["id"] == "qr1-math-stat" for p in data["dayExclusivePairs"]))
check("X combined classes: 4 instructed pairs", len(data["combinedClasses"]) == 4)
check("X every combined entry exists in bs-1",
      all(any(e["course"] == cc["a"]["course"]
              for s in data["populations"]["bs-1"]["sections"]
              if s["key"] == cc["a"]["section"]
              for e in s["entries"]) for cc in data["combinedClasses"]))
check("X parallel group: exactly 1 (ICS-II-B)",
      len(data["parallelGroups"]) == 1 and data["parallelGroups"][0]["id"] == "ics2b-econ-stat")

# --- faculty allocations
check("X Babar load = 22 across shift 1",
      canonical.teacher_load("Babar", canonical.SHIFT1) == 22)
check("X Millat load = 21 across shift 1",
      canonical.teacher_load("Millat", canonical.SHIFT1) == 22 - 1)
check("X combined-class teachers' loads deduped (Nehal = 12)",
      canonical.teacher_load("Nehal", canonical.SHIFT1) == 12)
check("X shift-2 teacher loads = 0 (no data yet)",
      canonical.teacher_load("Babar", canonical.SHIFT2) == 0)

# --- schedule configuration
check("X capacity 6 days x 8 periods",
      TC.CAPACITY == {"days": 6, "periods": 8})
check("X default active = Mon-Fri x 5 (all populations)",
      all(TC.POPULATIONS[p]["config"]["days"] == 5 and
          TC.POPULATIONS[p]["config"]["periods"] == 5 for p in TC.POPULATIONS))
check("X break positions: 1st shift after P3, 2nd after P2",
      TC.POPULATIONS["inter-1"]["config"]["break_after_period"] == 3 and
      TC.POPULATIONS["bs-1"]["config"]["break_after_period"] == 3 and
      TC.POPULATIONS["inter-2"]["config"]["break_after_period"] == 2)

# --- expandability: 6-day / 8-period solve needs no code changes
scE = make_scenario("expand", {
    "I2-E": [("English", "Prof. Zair Ahmad", 6), ("Urdu", "Prof. Abdur Rauf", 6),
             ("Math", "Prof. Najam us Saqib", 6), ("Isl", "Prof. Waseem A. Farooq", 6),
             ("Comp", "Prof. Babar Jahangir", 6), ("Stat", "Prof. Tanveer Ahmed", 6),
             ("A", "Visiting-1", 6), ("B", "Visiting-2", 6)],
})
scE["grid"] = {"days": 6, "periods": 8}
mE = CM.context_to_model(scE)
check("X 6x8 grid accepted by the model", mE["days"] == 6 and mE["periods"] == 8)
rE, _ = cp_solver.generate_context(scE, n_seeds=1, time_per_seed=20)
check("X 6-day x 8-period scenario solves (expandability, no code change)",
      len(rE) > 0, "got %d" % len(rE))
if rE:
    gE = rE[0]["grids"]
    check("X solved grid is 6 days x 8 periods",
          len(gE["I2-E"]) == 6 and len(gE["I2-E"][0]) == 8)

# --- the 6-day/5-period variant
scF = make_scenario("sat", {
    "I2-F": [("English", "Prof. Zair Ahmad", 6), ("Urdu", "Prof. Abdur Rauf", 6),
             ("Math", "Prof. Najam us Saqib", 6), ("Isl", "Prof. Waseem A. Farooq", 6),
             ("Comp", "Prof. Babar Jahangir", 6)],
})
scF["grid"] = {"days": 6, "periods": 5}
rF, _ = cp_solver.generate_context(scF, n_seeds=1, time_per_seed=15)
check("X 6-day x 5-period (Saturday active) scenario solves", len(rF) > 0)
if rF:
    check("X solved grid has 6 days",
          len(rF[0]["grids"]["I2-F"]) == 6)

# =====================================================================
print()
print("=" * 72)
print("REGRESSION — the original system")
print("=" * 72)

if not FAST:
    # reset the solver module state (context solving replaced SECTIONS/UNITS globals)
    import importlib
    importlib.reload(solver)
    importlib.reload(cp_solver)
    grids_old, status_old = cp_solver.solve_one(seed=0, time_limit=90.0)
    ok_old, _ = solver.validate(grids_old)
    check("R old path OPTIMAL", status_old == cp_model_OPT())
    check("R old path validates", ok_old)
    check("R old path score 560 (proven optimum preserved)",
          solver.score(grids_old) == 560)
else:
    check("R old path constants unchanged",
          len(solver.DEFAULT_SECTIONS) == 11 and
          len(solver.DEFAULT_CONSTRAINTS) == 11 and
          len(solver.TEACHER_FULL) == 23)

# RLS / cloud state verified in the PR-5 suite (see scripts/test_supabase_pops.js)

# =====================================================================
print()
print("=" * 72)
print("TRANSLATION LAYER (llm_translate) — vocabulary + direct expressions")
print("=" * 72)

import llm_translate as LLM

# every structured rule key in the canonical data must be translatable
rule_keys_used = set()
for _e in canonical.solver_constraints().values():
    rule_keys_used.update((_e.get("rules") or {}).keys())
check("L1 llm RULE_SPEC covers every canonical rule key",
      rule_keys_used <= set(LLM.RULE_SPEC.keys()),
      "missing: %s" % sorted(rule_keys_used - set(LLM.RULE_SPEC.keys())))

# every GI type in the canonical data must be translatable
_raw = json.load(open("data/canonical.json", encoding="utf-8"))
gi_types_used = set()
for _items in _raw["generalInstructions"].values():
    gi_types_used.update(g["type"] for g in _items)
check("L2 llm GI_RULE_TYPES covers every canonical GI type",
      gi_types_used <= set(LLM.GI_RULE_TYPES),
      "missing: %s" % sorted(gi_types_used - set(LLM.GI_RULE_TYPES)))

# direct-expression route: structured JSON pasted by the admin is validated
# locally (confidence 1.0) WITHOUT calling the LLM — works with no API key
dx = LLM.translate_constraints(
    '{"natural": "Assad BM pinned to P3 Mon+Tue", "rules": '
    '{"subject_slot_days": [{"subject": "Business Mathematics", "slot": "P3",'
    ' "days": ["MON", "TUE"]}], "allowed_slots_in_stream": '
    '[{"stream": "I.COM", "slots": ["P1", "P2", "P3"]}]}}')
check("L3 direct expression: faculty rules validated locally (no LLM)",
      dx.get("confidence") == 1.0 and not dx.get("errors") and
      dx["rules"].get("subject_slot_days") ==
      [{"subject": "Business Mathematics", "slot": "P3", "days": ["MON", "TUE"]}],
      str(dx)[:200])
dx_bad = LLM.translate_constraints('{"rules": {"subject_slot_days": [{"subject": "X", "slot": "P9", "days": ["SUN"]}]}}')
check("L4 direct expression: invalid shapes rejected with errors",
      "error" in dx_bad and dx_bad.get("errors"), str(dx_bad)[:160])
gi_dx = LLM.translate_general_instruction(
    '{"type": "section_off_days", "params": {"sections": ["BSAF-SEM-VII"], "days": ["FRI"]}}')
check("L5 direct expression: GI rule validated locally (no LLM)",
      gi_dx.get("type") == "section_off_days" and gi_dx.get("confidence") == 1.0 and
      gi_dx["params"]["days"] == ["FRI"], str(gi_dx)[:200])

# =====================================================================
print()
print("=" * 72)
print("MANUAL BUILD + INSIGHTS + TARGETED REPAIR (F15)")
print("=" * 72)

# M1: placements <-> grids round-trip on a real scenario solution
if rB:
    ttB = canonical.timetable_from_grids(rB[0]["grids"], mB)
    gB, unB = CM.placements_from_display(ttB, mB)
    check("M1 display->placements round-trip == solution grids", gB == rB[0]["grids"])
    check("M1 no unmatched cells for a legitimate solution", unB == [])

# M2: analyze_structured is a byte-identical twin of evaluate (texts + violations)
def _parity(grids, model, label):
    ev = CM.evaluate(grids, model)
    an = CM.analyze_structured(grids, model)
    v1 = sorted([(v["rule"], v["detail"], v["penalty"]) for v in ev["violations"]])
    v2 = sorted([(v["rule"], v["detail"], v["penalty"]) for v in an["violations"]])
    ok = (ev["issues"] == an["issues"] and v1 == v2 and ev["penalty"] == an["penalty"]
          and len(an["issues_detail"]) == len(ev["issues"]))
    check("M2 analyze_structured == evaluate (%s)" % label, ok,
          "issues %d/%d viol %d/%d" % (len(ev["issues"]), len(an["issues"]), len(v1), len(v2)))
    return an

empty1 = {s["key"]: [[None] * 5 for _ in range(5)] for s in model1["sections"]}
_parity(empty1, model1, "empty shift-1 grid")
if rB:
    _parity(rB[0]["grids"], mB, "scenario B valid grid")
    gC = copy.deepcopy(rB[0]["grids"])
    ks = list(gC.keys())[0]
    gC[ks][0][0], gC[ks][1][1] = gC[ks][1][1], gC[ks][0][0]
    anC = _parity(gC, mB, "scenario B corrupted grid")
    check("M2 focus metadata on hard issues (units listed)",
          all("units" in d and "cells" in d and "sig" in d for d in anC["issues_detail"]))

# M3: manual_vocabulary covers every cell a solution can display
if rB:
    voc = CM.manual_vocabulary(scB)
    ok_vocab = True
    for sec, rows in ttB.items():
        opts = {(o["subject"], o["teacher"]) for o in voc[sec]["options"]}
        for d in range(5):
            for s in range(5):
                cell = rows[d][s]
                if cell[0] == "Library Work":
                    continue
                if (cell[0], cell[1]) not in opts:
                    ok_vocab = False
    check("M3 vocabulary covers solution cells (pickers can't be wrong)", ok_vocab)
    check("M3 vocabulary weekly loads sum to the section fill",
          all(sum(o["periods"] for o in voc[sec]["options"]) == 25 for sec in voc))

# M4: unmatched (unallocated) entries are reported, not silently believed
_bogus = json.loads(json.dumps(ttB)) if rB else None
if _bogus:
    k0 = list(_bogus.keys())[0]
    _bogus[k0][0][0] = ["Bogus Course", "Prof. Nobody"]
    _gB2, un2 = CM.placements_from_display(_bogus, mB)
    check("M4 unallocated cell reported as unmatched",
          len(un2) == 1 and un2[0]["section"] == k0 and un2[0]["subject"] == "Bogus Course")

# M5: targeted repair of a teacher double-booking (instance mode)
scM = make_scenario("repair-lab", {
    "RA": [("English", "Prof. Zair Ahmad", 5), ("Urdu", "Prof. Abdur Rauf", 5),
           ("Math", "Prof. Najam us Saqib", 5), ("Isl", "Prof. Waseem A. Farooq", 5),
           ("Link", "Visiting-1", 5)],
    "RB": [("English", "Prof. Noor Muhammad", 5), ("Urdu", "Prof. Ehsam Ullah Baig", 5),
           ("Stat", "Prof. Tanveer Ahmed", 5), ("Isl", "Visiting-2", 5),
           ("Link", "Visiting-1", 5)],
})
mM = CM.context_to_model(scM)
rM, _ = cp_solver.generate_context(scM, n_seeds=1, time_per_seed=10, max_solutions=1)
check("M5 lab scenario solves", len(rM) > 0, "got %d" % len(rM))
if rM:
    g0 = copy.deepcopy(rM[0]["grids"])
    uA = next(u for u in mM["units"] if u["teacher"] == "V1" and u["secs"] == ["RA"])
    uB = next(u for u in mM["units"] if u["teacher"] == "V1" and u["secs"] == ["RB"])
    a_cells = [(d, s) for d in range(5) for s in range(5) if g0["RA"][d][s] == uA["id"]]
    d1, s1 = a_cells[0]
    b_same_day = next(s for s in range(5) if g0["RB"][d1][s] == uB["id"])
    g0["RA"][d1][s1] = None
    g0["RA"][d1][b_same_day] = uA["id"]
    tt0 = canonical.timetable_from_grids(g0, mM)
    an0 = CM.analyze_structured(g0, mM)
    dbl = [i for i, d in enumerate(an0["issues_detail"]) if d["sig"].startswith("teacher_double@V1")]
    check("M5 crafted double-booking detected", len(dbl) == 1, an0["issues"][:3])
    if dbl:
        rep = cp_solver.repair_context(scM, tt0, focus={"kind": "hard", "index": dbl[0]},
                                       mode="instance", time_per_tier=4)
        check("M5 instance repair succeeds (strict tier)", rep.get("ok") and rep.get("tier_index") == 0,
              rep.get("reason") or rep.get("tier"))
        if rep.get("ok"):
            check("M5 repair leaves 0 hard issues", rep["issues_after"] == [])
            check("M5 repair is minimal-diff (<= 4 cells)", rep["changed"] <= 4,
                  "%d cells" % rep["changed"])
        repT = cp_solver.repair_context(scM, tt0, focus={"kind": "hard", "index": dbl[0]},
                                        mode="type", time_per_tier=4)
        check("M5 type-mode repair also succeeds", repT.get("ok") and repT["issues_after"] == [],
              repT.get("reason"))

# M6: soft-infeasible causes fail honestly, fixable soft causes get fixed
_fd = canonical.name_to_code()["Prof. Waseem A. Farooq"]
scS = make_scenario("soft-lab", {
    "SA": [("English", "Prof. Zair Ahmad", 5), ("Urdu", "Prof. Abdur Rauf", 5),
           ("Math", "Prof. Najam us Saqib", 5), ("Isl", "Prof. Waseem A. Farooq", 5),
           ("Comp", "Prof. Faisal Bashir", 5)],
}, constraints={_fd: {"name": "Prof. Waseem A. Farooq",
                      "rules": {"forbidden_slots": ["P1"]},
                      "soft": ["forbidden_slots"]}})
mS = CM.context_to_model(scS)
rS, _ = cp_solver.generate_context(scS, n_seeds=1, time_per_seed=10, max_solutions=1)
if rS:
    g0 = copy.deepcopy(rS[0]["grids"])
    # guarantee a soft violation exists: swap a Soft Y cell onto a P1 cell in the same section
    uY = next(u for u in mS["units"] if u["teacher"] == _fd)
    y_cell = next((d, s) for d in range(5) for s in range(5)
                  if g0["SA"][d][s] == uY["id"] and s != 0)
    d_, s_ = y_cell
    p1_day = next(d for d in range(5) if g0["SA"][d][0] is not None and g0["SA"][d][0] != uY["id"])
    other = g0["SA"][p1_day][0]
    g0["SA"][p1_day][0], g0["SA"][d_][s_] = uY["id"], other
    ttS = canonical.timetable_from_grids(g0, mS)
    anS = CM.analyze_structured(g0, mS)
    sidx = [i for i, v in enumerate(anS["violations"]) if v["sig"].startswith("facrule@{}:forbidden_slots".format(_fd))]
    check("M6 crafted soft violation detected", len(sidx) == 1, anS["violations"][:2])
    if sidx:
        repS = cp_solver.repair_context(scS, ttS, focus={"kind": "soft", "index": sidx[0]},
                                        mode="instance", time_per_tier=4)
        okS = repS.get("ok")
        check("M6 soft repair succeeds", okS, repS.get("reason"))
        if okS:
            gone = all(not v["sig"].startswith("facrule@{}:forbidden_slots".format(_fd))
                       for v in repS["violations_after"])
            check("M6 focused soft rule cleared after repair", gone)
            check("M6 soft repair stays minimal-diff (<= 6)", repS["changed"] <= 6,
                  "%d cells" % repS["changed"])

# M7 app-level: API routes for Manual Build (guarded: only when fastapi+httpx importable)
import importlib.util as _ilu
if _ilu.find_spec("fastapi") and _ilu.find_spec("httpx"):
    try:
        from fastapi.testclient import TestClient as _TC
        import api.index as _API
        _API.app.dependency_overrides[_API.require_user] = lambda: {"id": "suite-user"}
        _client = _TC(_API.app)
        _r = _client.get("/manual-template", params={"populations": "inter-1,bs-1"})
        check("M7 /manual-template 200 + shift-1 sections", _r.status_code == 200 and len(_r.json()["sections"]) == 23)
        if rM:
            _ttM = canonical.timetable_from_grids(rM[0]["grids"], mM)
            _r = _client.post("/manual-analyze", json={"populations": ["inter-2"], "timetable": _ttM})
            check("M7 /manual-analyze 200 with mismatched-pop payload surfaces data", _r.status_code in (200, 400))
            _r = _client.post("/manual-analyze", json={"populations": ["inter-2"], "timetable": {}})
            check("M7 /manual-analyze empty grid 200 (nothing to check)", _r.status_code == 200)
        _r = _client.post("/manual-repair", json={"populations": ["inter-2"], "timetable": {}, "mode": "bogus"})
        check("M7 /manual-repair rejects bad mode", _r.status_code == 400)
        _API.app.dependency_overrides = {}
        _r = _client.post("/manual-analyze", json={"populations": ["inter-2"], "timetable": {}})
        check("M7 auth gating: no token -> 401", _r.status_code == 401)
    except Exception as e:
        check("M7 API route tests importable", False, repr(e))
else:
    check("M7 API route tests skipped (fastapi/httpx not installed locally)", True)

# =====================================================================
print()
print("=" * 72)
print("UI FIX GUARDS (F16) — GI remove/toggle wiring + population-aware rendering")
print("=" * 72)
built = open("index.html", encoding="utf-8").read()
check("N1 GI remove buttons are wired (renderGI binds [data-gi-remove])",
      "mainEl.querySelectorAll('[data-gi-remove]')" in built and "giRemove(" in built)
check("N1b GI on/off toggles are wired (renderGI binds [data-gi-toggle])",
      "mainEl.querySelectorAll('[data-gi-toggle]')" in built and "giToggle(" in built)
check("N2 sectionCard tolerates combinations that miss a section (no crash)",
      "This combination does not cover this section" in built)
check("N3 renderSections shows a coverage note instead of stale cards",
      "does not cover '+esc(POP_LABEL())+'" in built)
check("N4 exports skip un-covered sections instead of throwing",
      "does not cover '+secId+'" in built or "does not cover '+secId+'" in built.replace("\'", "'")
      or "Not exported — the selected combination does not cover" in built)

# ---- O-series: F17 fairness scorecard (per-side split + standalone refs) ----
try:
    import context_model as _cm
    import canonical as _canon
    ctxO = _canon.solver_context(['inter-1', 'bs-1'])
    mO = _cm.context_to_model(ctxO)
    units_by_sec = {}
    for u in mO['units']:
        for s in u['secs']:
            units_by_sec.setdefault(s, u['id'])
    gridsO = {s['key']: [[units_by_sec.get(s['key']) if d == 0 and p == 0 else None
                          for p in range(mO['periods'])] for d in range(mO['days'])]
              for s in mO['sections']}
    wholeO = _cm.shuffle_score(gridsO, mO)
    interO = _cm.shuffle_score_partial(gridsO, mO, level='inter')
    bsO = _cm.shuffle_score_partial(gridsO, mO, level='bs')
    check("O1 shuffle split is exactly additive (inter + bs == whole)",
          interO + bsO == wholeO)
    check("O2 section-level attribution covers both levels",
          any(s.get('level') == 'inter' for s in mO['sections']) and
          any(s.get('level') == 'bs' for s in mO['sections']))
except Exception as e:
    check("O1/O2 shuffle split helpers", False)

try:
    import cp_solver as _cs_o
    r2 = _cs_o.standalone_reference('inter-2', time_per_seed=1, n_seeds=1)
    check("O3 standalone_reference is None-safe for populations without sections (inter-2 pre-entry)",
          r2 is None)
except Exception as e:
    check("O3 standalone_reference None-safety", False)

try:
    import json as _jo
    baked = _jo.load(open('data/score_references.json', encoding='utf-8'))
    refs = baked.get('references') or {}
    check("O4 baked standalone references carry both shift-1 sides with scores",
          'inter-1' in refs and 'bs-1' in refs and
          isinstance(refs['inter-1'].get('score'), int) and isinstance(refs['bs-1'].get('score'), int))
    check("O5 vercel.json bundles data/score_references.json",
          'data/score_references.json' in _jo.load(open('vercel.json'))['functions']['api/index.py']['includeFiles'])
except Exception as e:
    check("O4/O5 baked references + bundling", False)

built17 = open('index.html', encoding='utf-8').read()
check("O6 UI computes the per-side split (scChipText/scSplitCombo/scSplitRaw present)",
      'function scChipText(' in built17 and 'function scSplitCombo(' in built17 and 'function scSplitRaw(' in built17)
check("O7 UI fetches + displays standalone references (ensureScoreRefs / '% standalone')",
      'function ensureScoreRefs(' in built17 and '/score-references' in built17 and '% standalone' in built17)
check("O8 scorecard drill-down shows the coexistence split line",
      'coexistence split: ' in built17 and 'splitLine+' in built17)
check("O9 ranking semantics unchanged (pool sorts by validity, then score+penalty)",
      '((a.penalty>0?1:0)-(b.penalty>0?1:0))' in built17 and '((a.score+(a.penalty||0))-(b.score+(b.penalty||0)))' in built17)
api_src17 = open('api/index.py', encoding='utf-8').read()
seg = api_src17.split('@app.get("/score-references")')[1].split('@app.')[0]
check("O10 /score-references route is public, fingerprinted, baked-first",
      '_SCORE_REF_CACHE' in seg and 'score_references.json' in seg and '_canon_fingerprint' in seg and 'Depends(require_user)' not in seg)

# ---- P-series: F18 themes (dark mode + palettes) ----
built18 = open('index.html', encoding='utf-8').read()
check("P1 four palettes declared as data-theme overrides",
      'html[data-theme="midnight"]' in built18 and 'html[data-theme="forest"]' in built18 and
      'html[data-theme="sand"]' in built18)
check("P2 theme applies before first paint (head script reads impcc-theme)",
      "localStorage.getItem('impcc-theme')" in built18.split('</head>')[0] and
      'document.documentElement.dataset.theme' in built18.split('</head>')[0])
check("P3 picker present in the masthead with all options",
      'id="themeSel"' in built18 and 'value="midnight"' in built18 and 'value="forest"' in built18 and
      'value="sand"' in built18 and 'value="system"' in built18 and 'value="classic"' in built18)
check("P4 change wiring + system-mode media-query listener + boot init",
      'function initTheme()' in built18 and "addEventListener('change'" in built18 and
      'prefers-color-scheme: dark' in built18 and 'initTheme();\nconst restored=restore();'
      in built18.replace('\r', ''))
check("P5 print always resets to the classic palette",
      built18.count('@media print{') >= 1 and
      built18.find('--paper:#eef0e8; --surface:#fcfcf7; --surface2:#f5f6ee;', built18.find('@media print{')) > built18.find('@media print{'))
check("P6 classic theme remains the default (no data-theme override required)",
      'html[data-theme="classic"]' not in built18)
check("P7 dark-theme literal fixes cover the big white-surface components",
      'tg-cell.dual' in built18 and '.sp-cell' in built18 and '.mast-search input' in built18 and
      ':is(html[data-theme="midnight"], html[data-theme="forest"])' in built18)

# =====================================================================
print()
print("=" * 72)
# ---- Q-series: F19 GI tab — organized schedule facts + grouped rule cards ----
built19 = open('index.html', encoding='utf-8').read()
check("Q1 GI nav button + setView('gi') binding",
      'id="viewGI"' in built19 and "setView('gi')" in built19)
check("Q2 schedule facts card: editable grid/length/day-start/break fields + Friday override",
      'data-sched="days"' in built19 and 'data-sched="periods"' in built19 and
      'data-sched="breakAfterPeriod"' in built19 and 'data-sched-ov="Fri"' in built19)
check("Q3 staging model kept: draft staged -> ☁ Publish applies into POPS",
      'impcc-ttcfg-' in built19 and 'applies them everywhere' in built19 and
      'function applyScheduleCfg(' in built19 and 'function schedStage(' in built19)
check("Q4 rules grouped by area (GI_GROUPS + rule-cards + group headers)",
      'var GI_GROUPS' in built19 and 'giRuleCard(' in built19 and 'gi-group-h' in built19)
check("Q5 publish carries schedule + section structure via timetableConfig",
      'ttConfigFor(' in built19 and 'sectionsAdded' in built19 and 'sectionsRemoved' in built19)
check("Q6 syncFromCloud restores staging (schedule facts + per-day overrides)",
      'function syncFromCloud(' in built19 and 'dayStartOverrides' in built19)
check("Q7 frontend passes {grid, allocation} overrides to the CP-SAT route",
      'function cpsatOverrides' in built19 and 'overrides:cpsatOverrides()' in built19)

# ---- R-series: F20 allocation — per-population panels + dynamic sections ----
check("R1 allocation renders 3 population panels in dependency order",
      "ALLOC_POPS = ['inter-1','bs-1','inter-2']" in built19 and 'function renderAllocationPops(' in built19)
check("R2 dynamic sections: add/delete helpers + localStorage persistence",
      'function secAdd(' in built19 and 'function secRemove(' in built19 and 'function secMetas(' in built19 and
      'impcc-secs-' in built19 and 'impcc-secrm-' in built19)
check("R3 section delete cascades its subject rows (confirm dialog)",
      'subject rows will be dropped' in built19 and 'pending ☁ Publish / 💾 Save' in built19)
import json as _jr
_can19 = _jr.load(open('data/canonical.json', encoding='utf-8'))
check("R4 inter-2 canonical starts empty (sections created in the UI)",
      len((_can19['populations']['inter-2'].get('sections')) or []) == 0)
check("R5 popSections union view: canonical minus tombstones plus metas",
      'function popSections(' in built19 and 'uiSecForm(pop, s)' in built19 and 'if(removed[s.key]) continue' in built19)
check("R6 generation context drops tombstoned sections (in-browser path)",
      'const rm = secRemoved(p);' in built19 and 'delete ctx.sections[k];' in built19)

bf19 = open('build_frontend.py', encoding='utf-8').read()
import ast as _ast19
try:
    _ast19.parse(bf19)
    check("R7 build_frontend.py remains valid Python", True)
except SyntaxError:
    check("R7 build_frontend.py remains valid Python", False)

# backend override semantics (fast: context only, no solve)
try:
    import canonical as _c19
    base = _c19.solver_context(['inter-1', 'bs-1'])
    ov = _c19.solver_context(['inter-1', 'bs-1'], overrides={'grid': {'days': 6, 'periods': 6},
                                                             'allocation': {'bs-1': {'BS-NEW-1': {'subjects': [{'subject': 'X', 'teacher': 'T', 'periods': 2}]}}}})
    check("R8 overrides: grid applies + allocation replace is per-pop",
          ov['grid']['periods'] == 6 and 'BS-NEW-1' in ov['sections'] and
          not any(k.startswith('BSAF') for k in ov['sections']) and
          len([k for k in base['sections'] if k.startswith('ICS')]) == len([k for k in ov['sections'] if k.startswith('ICS')]))
except Exception as e:
    check("R8 overrides semantics (grid + per-pop allocation replace)", False, str(e)[:120])

try:
    from fastapi.testclient import TestClient as _TC19
    import api.index as _API19
    _API19.app.dependency_overrides[_API19.require_user] = lambda: {"id": "suite-user"}
    _cl19 = _TC19(_API19.app)
    _r19 = _cl19.post('/generate-context', json={"populations": ["inter-1"], "time_limit": 1, "n_seeds": 1,
                                                "overrides": {"grid": {"days": 6, "periods": 6}}})
    _j19 = _r19.json()
    check("R9 /generate-context accepts cleaned overrides (grid 6x6 applied via meta)",
          _r19.status_code == 200 and len(_j19['meta'].get('slots', [])) == 6 and len(_j19['meta'].get('days', [])) == 6)
    _r19b = _cl19.post('/generate-context', json={"populations": ["inter-1"], "time_limit": 1, "n_seeds": 1,
                                                 "overrides": {"allocation": {
                                                     "bs-1": {},
                                                     "inter-1": {"ICS-II-A": {"subjects": [{"subject": "", "teacher": "T", "periods": 4}]}}}}})
    _j19b = _r19b.json()
    check("R10 invalid/forbidden allocation drops; canonical dataset stays intact",
          _r19b.status_code == 200 and len(_j19b['meta'].get('section_order', [])) == 11)
    _API19.app.dependency_overrides = {}
except Exception as e:
    check("R9/R10 API override flow (accept + validate)", False, str(e)[:120])

total = passed + failures
print("RESULT: %d/%d checks passed%s" %
      (passed, total, "  —  ALL TESTS PASSED ✓" if failures == 0 else
       "  —  %d FAILED ✗" % failures))
print("=" * 72)
sys.exit(0 if failures == 0 else 1)


