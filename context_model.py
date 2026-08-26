"""Context model: transforms a solve context (population(s) + rules) into the
solver's unit model and evaluates solutions against it — context-aware
validation with documented soft-constraint violations.

A solve context is built by canonical.py's solver_context() from the canonical
dataset (one context per SHIFT: shift 1 = inter-1 + bs-1 solved jointly; shift
2 = inter-2 alone). Schema:

{
  "grid": {"days": 5, "periods": 5},
  "sections": {SEC: {"subjects": [{"subject", "teacher", "periods"}, ...]}},
  "sectionMeta": {SEC: {"level": "inter"|"bs", "offDays": ["FRI"], "firstLast": true}},
  "relationships": {
    "parallelGroups":  [{id, course, periods, sections, teachers, slots}],
    "dayExclusivePairs": [{id, courses, softConsecutiveDays}],
    "combinedClasses":  [{id, teacher, a: {section, course}, b: {section, course}}],
  },
  "instructions": {
    "noSameSubjectSameDay": {"inter": true, "bs": false},
    "consecutiveFor2pw":    {"inter": true, "bs": false},
    "nonOverriding":   [{"sections": [...], "subjects": [A, B]}],
    "subjectForbiddenDays": [{"subject", "days", "scope"}],
    "softIndividualSpread": true,
  },
  "constraints": {code: {"name", "rules", "soft": [rule keys]}},
  "teacherCodes": {display name -> code},
  "softPenalties": {rule: 5000, preferFreeSlot: 500, evenDistribution: 100,
                    individualSpread: 200, nonConsecutive: 100},
}

Hard constraints produce `issues` (solution rejected). Soft constraints produce
documented `violations` with penalties that count toward the total score.
"""
import json as _json
import solver as _solver
from solver import SLOT_OF, DAY_OF, _slotset, _dayset

_ALL_CODES = None


def _resolve_teacher(x):
    """Resolve a display name OR an already-canonical code to its code."""
    global _ALL_CODES
    if _ALL_CODES is None:
        import canonical as _c
        _ALL_CODES = {f["code"] for f in _c.get()["faculty"]}
    if x in _ALL_CODES:
        return x
    import canonical as _c
    # unknown display name -> the name itself is its own teacher code (same as
    # the in-browser solver's resolve(): context_solver.js `n2c[x] ?? x`).
    # Returning None here would crash CP-SAT's teacher-keyed constraints
    # (None.startswith) on allocations whose teachers are outside the
    # canonical faculty registry.
    return _c.name_to_code().get(x, x)


# default soft-constraint penalty weights
PENALTIES = {
    "rule": 5000,            # a soft faculty/GI rule is disobeyed (flat per rule)
    "preferFreeSlot": 500,   # each period in a soft-preferred-free slot
    "evenDistribution": 100, # each period above the even per-day share
    "individualSpread": 200, # teacher in P1 and last period the same week
    "nonConsecutive": 100,   # a day-exclusive pair course not on consecutive days
}


# ---------------------------------------------------------------- transform
def _sec_stream(sec_key):
    if sec_key.startswith("I.COM"):
        return "I.COM"
    if sec_key.startswith("ICS"):
        return "ICS"
    return None


def context_to_model(ctx):
    """Build the solver-side unit model from a solve context.

    Returns a dict:
      days, periods, sections[{key, level, offDays, firstLast, subs, effDays}],
      units[{id, secs[], courseBySec, teacher, group, members, count, level}],
      dayExclusive[{id, units[], softConsecutiveDays}],
      combined[{id, unit}],
      constraints, penalties
    """
    grid = ctx.get("grid") or {}
    D = int(grid.get("days", 5))
    P = int(grid.get("periods", 5))
    _solver.set_grid(D, P)

    n2c = dict(ctx.get("teacherCodes") or {})
    code_of = lambda name: n2c.get(name, name)

    rel = ctx.get("relationships") or {}
    parallel = {(g["id"]): g for g in (rel.get("parallelGroups") or [])}
    combined_list = rel.get("combinedClasses") or []
    pairs_list = rel.get("dayExclusivePairs") or []
    instr = ctx.get("instructions") or {}
    meta = ctx.get("sectionMeta") or {}

    # index parallel-group entries by (section, course)
    parallel_entry = {}
    for g in (rel.get("parallelGroups") or []):
        for s in g["sections"]:
            parallel_entry[(s, g["course"])] = g

    # index combined entries by (section, course)
    combined_entry = {}
    for cc in combined_list:
        combined_entry[(cc["a"]["section"], cc["a"]["course"])] = cc
        combined_entry[(cc["b"]["section"], cc["b"]["course"])] = cc

    sections = []
    units = []
    consumed = set()   # (section, course) entries merged into a dual unit

    def unit_level(secs):
        # a dual-section unit's level: 'bs' if ALL sections are BS, else 'inter'
        lvls = [ (meta.get(s) or {}).get("level", "inter") for s in secs ]
        return "bs" if lvls and all(l == "bs" for l in lvls) else "inter"

    for sec_key, sec_data in (ctx.get("sections") or {}).items():
        m = meta.get(sec_key) or {}
        level = m.get("level", "inter")
        off_days = [DAY_OF[d] for d in (m.get("offDays") or [])]
        first_last = bool(m.get("firstLast"))
        eff_days = [d for d in range(D) if d not in off_days]
        subs = []
        for e in (sec_data.get("subjects") or []):
            course = e["subject"]
            periods = int(e.get("periods") or 0)
            subs.append([course, e.get("teacher") or "", periods])

            key = (sec_key, course)
            if key in consumed:
                continue   # merged into a dual unit from the other side
            if key in combined_entry:
                cc = combined_entry[key]
                other = cc["b"] if cc["a"]["section"] == sec_key else cc["a"]
                consumed.add(key)
                consumed.add((other["section"], other["course"]))
                units.append({
                    "id": len(units), "secs": [cc["a"]["section"], cc["b"]["section"]],
                    "courseBySec": {cc["a"]["section"]: cc["a"]["course"],
                                    cc["b"]["section"]: cc["b"]["course"]},
                    "teacher": _resolve_teacher(cc.get("teacher") or e.get("teacher") or ""),
                    "group": None, "members": [], "count": periods,
                    "level": unit_level([cc["a"]["section"], cc["b"]["section"]]),
                })
                continue
            if key in parallel_entry:
                g = parallel_entry[key]
                units.append({
                    "id": len(units), "secs": [sec_key],
                    "courseBySec": {sec_key: course},
                    "teacher": "PG:" + g["id"], "group": g["id"],
                    "members": [code_of(t) if isinstance(t, str) and t in n2c.values() else t
                                for t in g["teachers"]],
                    "count": periods, "level": level,
                })
                continue
            units.append({
                "id": len(units), "secs": [sec_key],
                "courseBySec": {sec_key: course},
                "teacher": _resolve_teacher(e.get("teacher") or ""),
                "group": None, "members": [], "count": periods, "level": level,
            })
        sections.append({
            "key": sec_key, "level": level, "offDays": off_days,
            "firstLast": first_last, "effDays": eff_days, "subs": subs,
            "pop": m.get("pop"),
        })

    # link day-exclusive pairs to unit ids — PER SECTION (the pair rule applies
    # wherever both courses co-exist in one section, not across sections)
    dx = []
    for p in pairs_list:
        for section in sections:
            sec_units = []
            for course in p["courses"]:
                for u in units:
                    if u["courseBySec"].get(section["key"]) == course:
                        sec_units.append(u["id"])
            if len(sec_units) >= 2:
                dx.append({"id": p["id"] + "@" + section["key"], "units": sec_units,
                           "softConsecutiveDays": bool(p.get("softConsecutiveDays"))})

    # combined units index
    combined_idx = []
    for u in units:
        if len(u["secs"]) > 1:
            combined_idx.append({"id": "cc%d" % u["id"], "unit": u["id"]})

    return {
        "days": D, "periods": P,
        "sections": sections, "units": units,
        "dayExclusive": dx, "combined": combined_idx,
        "instructions": instr,
        "constraints": ctx.get("constraints") or {},
        "penalties": dict(PENALTIES, **(ctx.get("softPenalties") or {})),
        # parallel-group definitions (cp_solver._unit_slot_domain consumes them
        # via model["_parallel"] — without this the member availability shrinks
        # silently no-op for PG:* units)
        "_parallel": rel.get("parallelGroups") or [],
    }


def model_section_fill(model, section):
    """Cells a section occupies (dual units count in both of their sections)."""
    fill = 0
    for u in model["units"]:
        if section["key"] in u["courseBySec"]:
            fill += u["count"]
    return fill


# ---------------------------------------------------------------- evaluation
def _dyn_cells_hit(e, u, sec):
    """Generalized forbid-cells matcher (dynamic/custom rules lower to the
    same entries). Match by subject / subjects / sections / teachers (own or
    parallel-group membership), optional scope; empty days/slots = all."""
    if e.get("subject") and u["courseBySec"].get(sec) != e["subject"]:
        return False
    if e.get("subjects") and u["courseBySec"].get(sec) not in (e["subjects"] or []):
        return False
    if e.get("sections") and sec not in (e["sections"] or []):
        return False
    if e.get("teachers"):
        if u.get("teacher") not in e["teachers"] and not set(u.get("members") or []).intersection(e["teachers"]):
            return False
    if e.get("scope") and _sec_stream(sec) != e["scope"]:
        return False
    return True


def _dyn_label(e):
    bits = []
    if e.get("subject"): bits.append(str(e["subject"]))
    if e.get("subjects"): bits.append("/".join(map(str, e["subjects"])))
    if e.get("sections"): bits.append(",".join(map(str, e["sections"])))
    if e.get("teachers"): bits.append(",".join(map(str, e["teachers"])))
    return " ".join(bits) or "cells"

def _sorted_slots(bad):
    return [(_solver.DAYS[d] + " " + _solver.SLOTS[s]) for (d, s) in sorted(set(bad))]


def _scope_signature(e):
    sc = (e.get("scope") if isinstance(e, dict) else None) or {}
    return (tuple(sorted(sc.get("populations") or [])),
            tuple(sorted(sc.get("streams") or [])),
            tuple(sorted(sc.get("sections") or [])))


def teacher_rule_findings(code, entry, my_units, cells, pop_of, D, P, pen):
    """Shared deterministic walk over ONE teacher's taught cells against the
    full personal-constraint taxonomy (personal_constraints_model.md).

    `entry` = the teacher's record {rules:{...}, soft:[...], hardness:{...}};
    hardness 100 = hard mask, 1..99 = soft (penalty × h/100), 0 = inactive (§8).
    `cells` = list of (d, s, sec, u) — the teacher's occupied cells (ints d,s).
    Returns finding dicts: {rule_key, msg, soft, uids, cells, pen}.
    evaluate() AND the repair analyzer both consume this — one implementation
    of every personal rule kind, so semantics can never drift apart."""
    from solver import scope_cell_applies, hardness_of
    entry = entry or {}
    rules = entry.get("rules") or {}
    soft = set(entry.get("soft") or [])
    findings = []

    def course(u, sec):
        return u["courseBySec"].get(sec) or list(u["courseBySec"].values())[0]

    def _label(d):
        return _solver.DAYS[d]

    def scoped_days(e):
        sc = (e.get("scope") if isinstance(e, dict) else None) or {}
        return _dayset(sc.get("days") or [])

    def applies(e, d, s, sec, u):
        return scope_cell_applies(e, sec=sec, day=_label(d),
                                  pop=pop_of.get(sec), stream=_sec_stream(sec))

    def _cl(pred):
        """(sec, d, s)-cells matching a (d, s, sec, u) predicate."""
        return [(sec, d, s) for (d, s, sec, u) in cells if pred(d, s, sec, u)]

    def _uids(pred):
        return sorted({u["id"] for (d, s, sec, u) in cells if pred(d, s, sec, u)})

    def add(rule_key, msg, clist=None, uids=None, is_soft=None, pen_=None):
        h = hardness_of(entry, rule_key)
        if h == 0:
            return   # inactive: kept as an admin annotation only
        is_soft_ = (rule_key in soft) if is_soft is None else bool(is_soft)
        if not is_soft_ and h < 100:
            is_soft_ = True                       # demoted to a soft finding
            if pen_ is None:
                pen_ = int(pen["rule"] * h / 100)
        elif is_soft_ and h < 100:
            # native soft (in `soft` list) or soft_* kind: scale the penalty too —
            # legacy soft list behaves like explicit h=50 (spec §8)
            pen_ = int((pen_ if pen_ is not None else pen["rule"]) * h / 100)
        findings.append({
            "rule_key": rule_key, "msg": msg,
            "soft": is_soft_,
            "uids": uids if uids is not None else sorted({u["id"] for u in my_units}),
            "cells": list(clist or []), "pen": pen_})

    # ---------------- day-slot presence summaries used by several kinds
    per_day = {}
    occ_slots_per_day = {}
    for (d, s, sec, u) in cells:
        per_day[d] = per_day.get(d, 0) + 1
        occ_slots_per_day.setdefault(d, set()).add(s)

    # ================================ HARD masks ================================
    fs = _slotset(rules.get("forbidden_slots")) if rules.get("forbidden_slots") is not None else None
    if fs is not None:
        pred = lambda d, s, sec, u: s in fs
        bad = sorted({s for (d, s, sec, u) in cells if s in fs})
        if bad:
            add("forbidden_slots", f"teaches in forbidden slot(s) {[_solver.SLOTS[s] for s in bad]}",
                _cl(pred), _uids(pred))
    asl = _slotset(rules.get("allowed_slots")) if rules.get("allowed_slots") is not None else None
    if asl is not None:
        pred = lambda d, s, sec, u: s not in asl
        bad = sorted({s for (d, s, sec, u) in cells if s not in asl})
        if bad:
            add("allowed_slots", f"teaches outside allowed slots {[_solver.SLOTS[s] for s in bad]}",
                _cl(pred), _uids(pred))
    fd = _dayset(rules.get("forbidden_days")) if rules.get("forbidden_days") is not None else None
    if fd is not None:
        pred = lambda d, s, sec, u: d in fd
        bad = sorted({d for (d, s, sec, u) in cells if d in fd})
        if bad:
            add("forbidden_days", f"teaches on forbidden day(s) {[_label(d) for d in bad]}",
                _cl(pred), _uids(pred))
    ad = _dayset(rules.get("allowed_days")) if rules.get("allowed_days") is not None else None
    if ad is not None:
        pred = lambda d, s, sec, u: d not in ad
        bad = sorted({d for (d, s, sec, u) in cells if d not in ad})
        if bad:
            add("allowed_days", f"teaches on non-allowed day(s) {[_label(d) for d in bad]}",
                _cl(pred), _uids(pred))
    for e in (rules.get("forbidden_slots_on_days") or []):
        dset = _dayset(e["days"]) & scoped_days(e) if scoped_days(e) else _dayset(e["days"])
        sset = _slotset(e["slots"])
        pred = lambda d, s, sec, u: d in dset and s in sset and applies(e, d, s, sec, u)
        bad = sorted({(d, s) for (d, s, sec, u) in cells if pred(d, s, sec, u)})
        if bad:
            add("forbidden_slots_on_days", f"teaches in forbidden day/slot {_sorted_slots(bad)}",
                _cl(pred), _uids(pred))
    if rules.get("allowed_slots_days"):          # positive union-allow windows
        groups = {}
        for e in rules["allowed_slots_days"]:
            sig = _scope_signature(e)
            groups.setdefault(sig, []).append(e)
        for sig, es in groups.items():
            win = {}
            for e in es:
                sd = scoped_days(e)
                ds = (_dayset(e.get("days") or []) or set(range(D))) & (sd or set(range(D)))
                for d in ds:
                    win.setdefault(d, set()).update(_slotset(e.get("slots") or []))
            e0 = es[0]
            pred = lambda d, s, sec, u, w=win, e=e0: (d not in w or s not in w[d]) and applies(e, d, s, sec, u)
            bad = sorted({(d, s) for (d, s, sec, u) in cells if pred(d, s, sec, u)})
            if bad:
                add("allowed_slots_days", f"teaches outside the allowed day/slot window {_sorted_slots(bad)}",
                    _cl(pred), _uids(pred))
    for e in (rules.get("allowed_slots_in_stream") or []):
        sset = _slotset(e["slots"])
        sd = scoped_days(e)
        pred = lambda d, s, sec, u: (_sec_stream(sec) == e["stream"] and s not in sset
                                     and (not sd or d in sd) and applies(e, d, s, sec, u))
        bad = sorted({(d, s) for (d, s, sec, u) in cells if pred(d, s, sec, u)})
        if bad:
            add("allowed_slots_in_stream", f"{e['stream']} classes outside allowed slots {_sorted_slots(bad)}",
                _cl(pred), _uids(pred))
    for e in (rules.get("allowed_days_in_stream") or []):
        dset = _dayset(e["days"])
        pred = lambda d, s, sec, u: (_sec_stream(sec) == e["stream"] and d not in dset
                                     and applies(e, d, s, sec, u))
        bad = sorted({d for (d, s, sec, u) in cells if pred(d, s, sec, u)})
        if bad:
            add("allowed_days_in_stream", f"{e['stream']} classes on non-allowed day(s) {[_label(d) for d in bad]}",
                _cl(pred), _uids(pred))
    for e in (rules.get("stream_forbidden_days") or []):
        dset = _dayset(e["days"]) - (set(range(D)) - scoped_days(e) if scoped_days(e) else set())
        pred = lambda d, s, sec, u: (_sec_stream(sec) == e["stream"] and d in dset
                                     and applies(e, d, s, sec, u))
        bad = sorted({d for (d, s, sec, u) in cells if pred(d, s, sec, u)})
        if bad:
            add("stream_forbidden_days", f"{e['stream']} classes on forbidden day(s) {[_label(d) for d in bad]}",
                _cl(pred), _uids(pred))
    for e in (rules.get("allowed_slots_in_sections") or []):
        sset = _slotset(e.get("slots") or [])
        secs = e.get("sections") or []
        sd = scoped_days(e)
        pred = lambda d, s, sec, u: (sec in secs and s not in sset and (not sd or d in sd)
                                     and applies(e, d, s, sec, u))
        bad = sorted({(d, s) for (d, s, sec, u) in cells if pred(d, s, sec, u)})
        if bad:
            add("allowed_slots_in_sections",
                f"classes in {','.join(secs)} outside allowed slots {_sorted_slots(bad)}",
                _cl(pred), _uids(pred))
    for e in (rules.get("allowed_days_in_sections") or []):
        dset = _dayset(e["days"])
        secs = e.get("sections") or []
        pred = lambda d, s, sec, u: (sec in secs and d not in dset and applies(e, d, s, sec, u))
        bad = sorted({d for (d, s, sec, u) in cells if pred(d, s, sec, u)})
        if bad:
            add("allowed_days_in_sections",
                f"classes in {','.join(secs)} on non-allowed day(s) {[_label(d) for d in bad]}",
                _cl(pred), _uids(pred))
    asx = set(rules.get("allowed_sections") or [])
    if asx:
        pred = lambda d, s, sec, u: sec not in asx
        bad = sorted({sec for (d, s, sec, u) in cells if sec not in asx})
        if bad:
            add("allowed_sections", f"teaches outside allowed sections {bad}", _cl(pred), _uids(pred))
    fsx = set(rules.get("forbidden_sections") or [])
    if fsx:
        pred = lambda d, s, sec, u: sec in fsx
        bad = sorted({sec for (d, s, sec, u) in cells if sec in fsx})
        if bad:
            add("forbidden_sections", f"teaches in forbidden sections {bad}", _cl(pred), _uids(pred))
    if rules.get("subject_slots"):               # per-subject slot allows (union by subject)
        by_subj = {}
        for e in rules["subject_slots"]:
            sd = scoped_days(e)
            by_subj.setdefault(e["subject"], {}).setdefault("win", {})
            ds = _dayset(e.get("days") or []) or (sd or set(range(D)))
            sset = _slotset(e.get("slots") or [])
            by_subj[e["subject"]].setdefault("e", e)
            for d in ds:
                by_subj[e["subject"]]["win"].setdefault(d, set()).update(sset)
        for subj, wn in by_subj.items():
            win, e = wn["win"], wn["e"]
            pred = lambda d, s, sec, u, sub=subj, w=win, e=e: (course(u, sec) == sub and s not in w.get(d, set())
                                         and applies(e, d, s, sec, u))
            bad = sorted({(d, s) for (d, s, sec, u) in cells if pred(d, s, sec, u)})
            if bad:
                add("subject_slots", f"{subj} not in allowed slots {_sorted_slots(bad)}",
                    _cl(pred), _uids(pred))
    for e in (rules.get("subject_forbidden_days") or []):
        dset = _dayset(e["days"]) - (set(range(D)) - scoped_days(e) if scoped_days(e) else set())
        pred = lambda d, s, sec, u: (course(u, sec) == e["subject"] and d in dset
                                     and applies(e, d, s, sec, u))
        bad = sorted({d for (d, s, sec, u) in cells if pred(d, s, sec, u)})
        if bad:
            add("subject_forbidden_days", f"{e['subject']} on forbidden day(s) {[_label(d) for d in bad]}",
                _cl(pred), _uids(pred))
    if rules.get("subject_days_allowed"):
        by_subj = {}
        for e in rules["subject_days_allowed"]:
            by_subj.setdefault(e["subject"], set()).update(_dayset(e["days"]))
        for subj, dset in by_subj.items():
            pred = lambda d, s, sec, u, sub=subj, ds=dset: course(u, sec) == sub and d not in ds
            bad = sorted({d for (d, s, sec, u) in cells if pred(d, s, sec, u)})
            if bad:
                add("subject_days_allowed", f"{subj} outside allowed day(s) {[_label(d) for d in bad]}",
                    _cl(pred), _uids(pred))
    # subject pins — singular legacy + plural windows, unioned per subject
    pins = {}
    for e in (rules.get("subject_slot_days") or []):
        pins.setdefault(e["subject"], set()).update(
            (d, s) for d in _dayset(e["days"]) for s in _slotset([e["slot"]]))
    for e in (rules.get("subject_slots_days") or []):
        pins.setdefault(e["subject"], set()).update(
            (d, s) for d in _dayset(e.get("days") or []) for s in _slotset(e.get("slots") or []))
    for subj, win in pins.items():
        pred = lambda d, s, sec, u, w=win, sub=subj: course(u, sec) == sub and (d, s) not in w
        bad = sorted({(d, s) for (d, s, sec, u) in cells if pred(d, s, sec, u)})
        if bad:
            add("subject_slot_days" if any(x.get("slot") for x in (rules.get("subject_slot_days") or []) if x.get("subject") == subj)
                else "subject_slots_days",
                f"{subj} outside pinned day/slot window {_sorted_slots(bad)}",
                _cl(pred), _uids(pred))

    # ================================ Deterministic counts ================================
    for e in (rules.get("min_days_in_slot") or []):
        si = SLOT_OF[e["slot"]]
        days = {d for (d, s, sec, u) in cells if s == si and applies(e, d, s, sec, u)}
        if len(days) < (e.get("min_days") or 1):
            add("min_days_in_slot", f"{e['slot']} engaged only {len(days)} days (<{e.get('min_days')})",
                clist=[(sec, d, s) for (d, s, sec, u) in cells if s == si and applies(e, d, s, sec, u)])
    for e in (rules.get("max_days_in_slot") or []):
        si = SLOT_OF[e["slot"]]
        days = {d for (d, s, sec, u) in cells if s == si and applies(e, d, s, sec, u)}
        if len(days) > (e.get("max_days") or 0):
            add("max_days_in_slot", f"{e['slot']} straight into {len(days)} days (>{e.get('max_days')})",
                clist=[(sec, d, s) for (d, s, sec, u) in cells if s == si and applies(e, d, s, sec, u)])
    if rules.get("min_days_engaged"):
        if len(per_day) < rules["min_days_engaged"]:
            add("min_days_engaged", f"engaged only {len(per_day)} days (<{rules['min_days_engaged']})",
                clist=[(sec, d, s) for (d, s, sec, u) in cells])
    mppd = rules.get("max_periods_per_day")
    if isinstance(mppd, int):
        for d, c in per_day.items():
            if c > mppd:
                add("max_periods_per_day", f"{c} periods on {_label(d)} (>{mppd})",
                    clist=[(sec, d2, s) for (d2, s, sec, u) in cells if d2 == d])
    for e in (mppd if isinstance(mppd, list) else []):
        cap = e.get("max")
        sd = scoped_days(e)
        for d, c in per_day.items():
            if sd and d not in sd:
                continue
            if e.get("days") and d not in _dayset(e["days"]):
                continue
            def _mpred(d2, s, sec, u, d=d, e=e):
                if d2 != d:
                    return False
                if e.get("stream") and _sec_stream(sec) != e["stream"]:
                    return False
                if e.get("sections") and sec not in (e.get("sections") or []):
                    return False
                return applies(e, d2, s, sec, u)
            n = sum(1 for (d2, s, sec, u) in cells if _mpred(d2, s, sec, u))
            if cap is not None and n > cap:
                add("max_periods_per_day", f"{n} scoped periods on {_label(d)} (>{cap})",
                    clist=[(sec, d2, s) for (d2, s, sec, u) in cells if _mpred(d2, s, sec, u)])
    mppd_min = rules.get("min_periods_per_day")
    min_list = ([{"min": mppd_min}] if isinstance(mppd_min, int)
                else (mppd_min if isinstance(mppd_min, list) else []))
    for e in min_list:
        floor = e.get("min")
        if floor is None:
            continue
        sd = scoped_days(e)
        for d, c in per_day.items():
            if sd and d not in sd:
                continue
            if e.get("days") and d not in _dayset(e["days"]):
                continue
            def _npred(d2, s, sec, u, d=d, e=e):
                if d2 != d:
                    return False
                if e.get("stream") and _sec_stream(sec) != e["stream"]:
                    return False
                if e.get("sections") and sec not in (e.get("sections") or []):
                    return False
                return applies(e, d2, s, sec, u)
            n = sum(1 for (d2, s, sec, u) in cells if _npred(d2, s, sec, u))
            if per_day.get(d, 0) > 0 and n < floor:
                add("min_periods_per_day", f"only {n} scoped periods on {_label(d)} (<{floor})",
                    clist=[(sec, d2, s) for (d2, s, sec, u) in cells if _npred(d2, s, sec, u)])

    # ---- distribution quotas (max/min pieces matching a selector)
    def _quota_matches(e, d, s, sec, u):
        if e.get("subject") and course(u, sec) != e["subject"]:
            return False
        if e.get("subjects") and course(u, sec) not in (e["subjects"] or []):
            return False
        if e.get("stream") and _sec_stream(sec) != e["stream"]:
            return False
        if e.get("sections") and sec not in (e.get("sections") or []):
            return False
        if e.get("slot") and SLOT_OF.get(e["slot"]) != s:
            return False
        if e.get("days") and d not in _dayset(e["days"]):
            return False
        return applies(e, d, s, sec, u)

    for key, cmp_dir in (("max_pieces_match", "max"), ("min_pieces_match", "min")):
        for e in (rules.get(key) or []):
            bound = e.get("max" if cmp_dir == "max" else "min")
            if bound is None:
                continue
            n = sum(1 for (d, s, sec, u) in cells if _quota_matches(e, d, s, sec, u))
            hit = (n > bound) if cmp_dir == "max" else (n < bound)
            if hit:
                sel = ", ".join(f"{k}={v}" for k, v in e.items() if k not in ("scope", "max", "min"))
                add(key, f"{n} matching pieces [{sel}] ({cmp_dir} {bound})",
                    clist=[(sec, d, s) for (d, s, sec, u) in cells if _quota_matches(e, d, s, sec, u)])

    # ---- engagement requirements
    for e in (rules.get("stream_slots_required") or []):
        # the stream must exist for this teacher — otherwise vacuous
        if not any(_sec_stream(sec) == e["stream"] for u in my_units for sec in u["secs"]):
            continue
        sd = scoped_days(e)
        for sl in e["slots"]:
            si = SLOT_OF[sl]
            days = {d for (d, s, sec, u) in cells
                    if s == si and _sec_stream(sec) == e["stream"]
                    and (not sd or d in sd) and applies(e, d, s, sec, u)}
            floor = 4 if not e.get("min_days") else e["min_days"]
            if len(days) < floor:
                add("stream_slots_required", f"{e['stream']} {sl} engaged only {len(days)} days (<{floor})",
                    clist=[(sec, d, s) for (d, s, sec, u) in cells
                           if s == si and _sec_stream(sec) == e["stream"] and applies(e, d, s, sec, u)])

    # ---- structure: no free holes inside a teaching day
    if rules.get("no_daily_gaps"):
        for d, sset in sorted(occ_slots_per_day.items()):
            if len(sset) < 2:
                continue
            lo, hi = min(sset), max(sset)
            gaps = (hi - lo + 1) - len(sset)
            if gaps:
                add("no_daily_gaps", f"{gaps} gap(s) inside {_label(d)}'s teaching run "
                    f"(P{lo+1}–P{hi+1})",
                    clist=[(sec, d2, s) for (d2, s, sec, u) in cells if d2 == d])

    # ================================ SOFT preferences ================================
    if rules.get("soft_prefer_free_slots"):
        sset = _slotset(rules["soft_prefer_free_slots"])
        n = sum(1 for (d, s, sec, u) in cells if s in sset)
        if n:
            add("soft_prefer_free_slots", f"{n} period(s) in preferred-free slots "
                f"{rules['soft_prefer_free_slots']}", is_soft=True, pen_=pen["preferFreeSlot"] * n,
                clist=[(sec, d, s) for (d, s, sec, u) in cells if s in sset])
    for e in (rules.get("soft_prefer_free_slots_days") or []):
        dset = _dayset(e["days"])
        sset = _slotset(e["slots"])
        n = sum(1 for (d, s, sec, u) in cells if d in dset and s in sset and applies(e, d, s, sec, u))
        if n:
            add("soft_prefer_free_slots_days", f"{n} period(s) in preferred-free windows "
                f"{'/'.join(e['days'])} {','.join(e['slots'])}", is_soft=True, pen_=pen["preferFreeSlot"] * n,
                clist=[(sec, d, s) for (d, s, sec, u) in cells if d in dset and s in sset and applies(e, d, s, sec, u)])
    if rules.get("soft_even_distribution"):
        total = len(cells)
        used = max(1, len(per_day) or 1)
        cap = -(-total // used)
        excess = sum(max(0, c - cap) for c in per_day.values())
        if excess:
            add("soft_even_distribution", f"{excess} period(s) above the even per-day share",
                is_soft=True, pen_=pen["evenDistribution"] * excess)
    if rules.get("soft_compact_days"):
        gaps = 0
        for d, sset in sorted(occ_slots_per_day.items()):
            if len(sset) >= 2:
                lo, hi = min(sset), max(sset)
                gaps += (hi - lo + 1) - len(sset)
        if gaps:
            add("soft_compact_days", f"{gaps} gap(s) inside teaching days (moves toward compact days)",
                is_soft=True, pen_=pen["rule"] * gaps)
    return findings


def evaluate(grids, model):
    """Validate a solution (grids: unit ids per section cell) against the model.

    Returns {"issues": [...], "violations": [...], "penalty": int}.
    issues non-empty => structurally invalid (rejected).
    violations document disobeyed SOFT constraints (+ penalties).
    """
    D = model["days"]; P = model["periods"]
    issues, violations = [], []
    pen = model["penalties"]
    units = model["units"]
    by_id = {u["id"]: u for u in units}

    def course_of(u, sec):
        return u["courseBySec"].get(sec) or list(u["courseBySec"].values())[0]

    # ---- per-section structural checks
    for section in model["sections"]:
        key = section["key"]
        g = grids.get(key)
        if g is None:
            issues.append(f"{key}: missing grid")
            continue
        level = section["level"]
        counts = {}
        for d in range(D):
            if d in section["offDays"]:
                for s in range(P):
                    if g[d][s] is not None:
                        issues.append(f"{key}: class on off day {_solver.DAYS[d]}")
                continue
            seen = set()
            occ_slots = [s for s in range(P) if g[d][s] is not None]
            for s in range(P):
                uid = g[d][s]
                if uid is None:
                    continue
                u = by_id.get(uid)
                if u is None:
                    issues.append(f"{key}: unknown unit {uid}")
                    continue
                cname = course_of(u, key)
                counts[cname] = counts.get(cname, 0) + 1
                no_dup = (model["instructions"].get("noSameSubjectSameDay") or {}).get(level, True)
                if no_dup:
                    if cname in seen:
                        issues.append(f"{key} {_solver.DAYS[d]} {cname} twice in a day")
                    seen.add(cname)
            if section["firstLast"] and level == "bs" and (
                    section["effDays"] and d in section["effDays"]):
                if occ_slots and (0 not in occ_slots or (P - 1) not in occ_slots):
                    issues.append(f"{key} {_solver.DAYS[d]}: first/last period must be occupied")
        # exact load per course
        for cname, tlabel, cnt in section["subs"]:
            if counts.get(cname, 0) != cnt:
                issues.append(f"{key} {cname} load {counts.get(cname, 0)} != {cnt}")
        # inter sections must fill the whole grid
        if level == "inter":
            empty = sum(1 for d in range(D) for s in range(P) if g[d][s] is None)
            if empty:
                issues.append(f"{key}: {empty} empty cells (inter sections fill the grid)")

    # ---- teacher occupancy (deduped for dual-section/parallel units)
    occ = {}   # code -> list of [d, s, sec, countOnce]
    for u in units:
        if not u["group"] and not u["teacher"]:
            issues.append(f"unit {u['id']} ({list(u['courseBySec'].values())}): unresolved teacher")
        cells = set()
        for sec in u["secs"]:
            g = grids.get(sec)
            if not g:
                continue
            for d in range(D):
                for s in range(P):
                    if g[d][s] == u["id"]:
                        cells.add((d, s))
        teachers = [u["teacher"]] + (u["members"] if u["group"] else [])
        for t in teachers:
            if t is None:
                continue
            for (d, s) in cells:
                occ.setdefault(t, []).append([d, s, u["secs"][0]])
    for t, lst in occ.items():
        seen = set()
        for (d, s, k) in lst:
            if (d * P + s) in seen:
                issues.append(f"teacher {t} double-booked {_solver.DAYS[d]} {_solver.SLOTS[s]}")
            seen.add(d * P + s)

    # ---- combined classes: identical (day,slot) sets in both sections
    for cc in model["combined"]:
        u = by_id[cc["unit"]]
        if len(u["secs"]) != 2:
            continue
        a, b = u["secs"]
        ca = {(d, s) for d in range(D) for s in range(P)
              if grids.get(a) and grids[a][d][s] == u["id"]}
        cb = {(d, s) for d in range(D) for s in range(P)
              if grids.get(b) and grids[b][d][s] == u["id"]}
        if ca != cb:
            issues.append(f"combined {cc['id']}: slot sets differ between {a} and {b}")

    # ---- parallel groups: single slot, within group slots; members occupied there
    for u in units:
        if not u["group"]:
            continue
        cells = [(d, s) for sec in u["secs"]
                 for d in range(D) for s in range(P)
                 if grids.get(sec) and grids[sec][d][s] == u["id"]]
        slots = {s for (_, s) in cells}
        if len(cells) != u["count"]:
            issues.append(f"parallel {u['group']}: {len(cells)} cells != {u['count']}")
        if len(slots) != 1:
            issues.append(f"parallel {u['group']}: spans slots {sorted(slots)}")

    # ---- day-exclusive pairs
    for p in model["dayExclusive"]:
        uids = p["units"]
        daysets = []
        for uid in uids:
            u = by_id[uid]
            days = {d for sec in u["secs"] for d in range(D)
                    for s in range(P)
                    if grids.get(sec) and grids[sec][d][s] == uid}
            daysets.append((u, days))
        for i in range(len(daysets)):
            for j in range(i + 1, len(daysets)):
                shared = daysets[i][1] & daysets[j][1]
                if shared:
                    issues.append(f"dayExclusive {p['id']}: {course_of(daysets[i][0], daysets[i][0]['secs'][0])} "
                                  f"shares day(s) {sorted(shared)} with {course_of(daysets[j][0], daysets[j][0]['secs'][0])}")
        if p["softConsecutiveDays"]:
            for u, days in daysets:
                if u["count"] == 2 and len(days) == 2:
                    d0, d1 = sorted(days)
                    if d1 - d0 != 1:
                        cname = course_of(u, u["secs"][0])
                        violations.append({"rule": f"dayExclusive:{p['id']}",
                                           "detail": f"{cname} on non-consecutive days {_solver.DAYS[d0]},{_solver.DAYS[d1]}",
                                           "penalty": pen["nonConsecutive"]})

    # ---- consecutive days for 2/wk inter units
    for u in units:
        lvl = u["level"]
        if u["count"] != 2 or lvl != "inter":
            continue
        if not (model["instructions"].get("consecutiveFor2pw") or {}).get("inter", False):
            continue
        days = {d for sec in u["secs"] for d in range(D) for s in range(P)
                if grids.get(sec) and grids[sec][d][s] == u["id"]}
        if len(days) == 2:
            d0, d1 = sorted(days)
            if d1 - d0 != 1:
                issues.append(f"{u['secs'][0]} {course_of(u, u['secs'][0])}: "
                              f"2/wk on non-consecutive days {_solver.DAYS[d0]},{_solver.DAYS[d1]}")

    # ---- faculty constraints (person-level; soft rules -> violations) —
    # the same shared walker as evaluate(): repair tickets come from identical logic.
    R = model["constraints"]
    pop_of = {s["key"]: s.get("pop") for s in model.get("sections", [])}
    for code, entry in R.items():
        my_units = [u for u in units if u["teacher"] == code or (u["members"] and code in u["members"])]
        if not my_units:
            continue
        cells = []
        for u in my_units:
            for sec in u["secs"]:
                g = grids.get(sec)
                if not g:
                    continue
                for d in range(D):
                    for s in range(P):
                        if g[d][s] == u["id"]:
                            cells.append((d, s, sec, u))

        for f in teacher_rule_findings(code, entry, my_units, cells, pop_of, D, P, pen):
            if f["soft"]:
                violations.append({"rule": f"{code}:{f['rule_key']}", "detail": f["msg"],
                                   "penalty": f["pen"] if f["pen"] is not None else pen["rule"]})
            else:
                issues.append(f"{code} {f['msg']}")

    # ---- general instructions (institution-level)
    for e in (model["instructions"].get("subjectForbiddenDays") or []):
        for u in units:
            for sec in u["secs"]:
                if course_of(u, sec) != e["subject"]:
                    continue
                scope = e.get("scope")
                if scope and _sec_stream(sec) != scope:
                    continue
                g = grids.get(sec)
                if not g:
                    continue
                dset = _dayset(e["days"])
                for d in range(D):
                    for s in range(P):
                        if g[d][s] == u["id"] and d in dset:
                            issues.append(f"{sec} {e['subject']} on forbidden day {_solver.DAYS[d]}")

    for e in (model["instructions"].get("subjectForbiddenSlotDays") or []):
        for u in units:
            for sec in u["secs"]:
                if not _dyn_cells_hit(e, u, sec):
                    continue
                g = grids.get(sec)
                if not g:
                    continue
                dset = _dayset(e.get("days") or [d for d in range(D)])
                sset = _slotset(e.get("slots") or ["P%d" % (s + 1) for s in range(P)])
                for d in range(D):
                    for s in range(P):
                        if g[d][s] == u["id"] and d in dset and s in sset:
                            issues.append(f"{sec} {_dyn_label(e)} at forbidden window {_solver.DAYS[d]} {_solver.SLOTS[s]}")
    for e in (model["instructions"].get("nonOverriding") or []):
        secs = e["sections"]
        subs = e["subjects"]
        for x in secs:
            gx = grids.get(x)
            if not gx:
                continue
            found = False
            for d in range(D):
                for s in range(P):
                    uid = gx[d][s]
                    if uid is None:
                        continue
                    u = by_id.get(uid)
                    if u and course_of(u, x) == subs[0]:
                        ok = True
                        for y in secs:
                            if y == x:
                                continue
                            gy = grids.get(y)
                            if not gy:
                                continue
                            uidy = gy[d][s]
                            uy = by_id.get(uidy) if uidy is not None else None
                            if uy and course_of(uy, y) == subs[1]:
                                ok = False
                                break
                        if ok:
                            found = True
                            break
                if found:
                    break
            if not found:
                issues.append(f"non-overriding failed {x}")
    # soft individual spread: teacher with P1 usage also teaching the last period
    if model["instructions"].get("softIndividualSpread"):
        for t, lst in occ.items():
            slots = {s for (d, s, k) in lst}
            if 0 in slots and (P - 1) in slots:
                violations.append({"rule": f"{t}:soft_individual_spread",
                                   "detail": f"engaged in P1 and {_solver.SLOTS[P-1]} in the same week",
                                   "penalty": pen["individualSpread"]})

    return {"issues": issues, "violations": violations,
            "penalty": sum(v["penalty"] for v in violations)}


def shuffle_score(grids, model):
    """Shuffle penalty (the classic score) under a context model."""
    return shuffle_score_partial(grids, model)


def shuffle_score_partial(grids, model, level=None):
    """Same terms as shuffle_score, restricted to sections of one level
    ('inter' / 'bs'). The shuffle score is exactly additive per section, so
    inter + bs == whole for shift-1 solutions — a fair per-side breakdown."""
    pen = 0
    units = {u["id"]: u for u in model["units"]}
    for section in model["sections"]:
        if level is not None and section.get("level") != level:
            continue
        g = grids.get(section["key"])
        if not g:
            continue
        D, P = model["days"], model["periods"]
        slots_by = {}
        for d in range(D):
            for s in range(P):
                uid = g[d][s]
                if uid is None:
                    continue
                u = units[uid]
                cname = u["courseBySec"].get(section["key"]) or list(u["courseBySec"].values())[0]
                slots_by.setdefault(cname, set()).add(s)
        for cname, tlabel, count in section["subs"]:
            extra = len(slots_by.get(cname, set())) - 1
            if count == 5:
                pen += extra * 100000
            elif count == 4:
                pen += extra * 10000
            elif count == 3:
                pen += extra * 100
            else:
                pen += extra * 10
    return pen


# ---------------------------------------------------------------- pool policy
def pool_selection(solutions, target=10, cutoff=25):
    """The Q3 pool rule.

    solutions: ranked list (best first) of {total, penalty, violations, ...}
      where penalty == 0 means a fully-valid solution.
    Returns {display, counts}:
      - >= cutoff fully-valid  -> top `cutoff` valid only
      - target..cutoff valid   -> ALL valid only (no padding)
      - < target valid         -> all valid + best violators up to `target`
                                  (each documents its violated constraints)
    """
    valid = [s for s in solutions if not s.get("penalty")]
    violators = [s for s in solutions if s.get("penalty")]
    if len(valid) >= cutoff:
        display = valid[:cutoff]
    elif len(valid) >= target:
        display = valid
    else:
        display = valid + violators[: target - len(valid)]
    return {
        "display": display,
        "counts": {
            "valid_found": len(valid), "violators_found": len(violators),
            "shown": len(display),
            "shown_violators": sum(1 for s in display if s.get("penalty")),
        },
    }


# ---------------------------------------------------------------- manual entry
def manual_vocabulary(ctx):
    """Per-section entry vocabulary for the Manual Build view.

    {KEY: {"level": ..., "offDays": [...], "firstLast": bool,
           "options": [{"subject", "teacher", "periods"}]}}
    Every display cell a section may legitimately hold (derived from the solve
    context; parallel groups render 'A / B')."""
    import canonical as _canon
    model = context_to_model(ctx)
    out = {}
    for section in model["sections"]:
        key = section["key"]
        opts = []
        seen = set()
        for u in model["units"]:
            if key not in u["courseBySec"]:
                continue
            course = u["courseBySec"][key]
            if course in seen:
                continue
            seen.add(course)
            if u["group"]:
                tname = " / ".join(_canon.display_name(t) for t in u["members"])
            else:
                tname = _canon.display_name(u["teacher"])
            opts.append({"subject": course, "teacher": tname, "periods": u["count"]})
        out[key] = {
            "level": section["level"],
            "offDays": [_solver.DAYS[d] for d in section["offDays"]],
            "firstLast": section["firstLast"],
            "options": sorted(opts, key=lambda o: o["subject"]),
        }
    return out


def placements_from_display(tt, model):
    """{section: dayRows[[subject, teacher]]} -> (grids, unmatched).

    grids: unit ids per cell (None = free/'Library Work'/blank). Cells that do
    not match any legitimate (subject, teacher) pair for their section are
    listed in 'unmatched' (and treated as empty in grids)."""
    import canonical as _canon
    look = {}
    for u in model["units"]:
        if u["group"]:
            tname = " / ".join(_canon.display_name(t) for t in u["members"])
        else:
            tname = _canon.display_name(u["teacher"])
        for sk, course in u["courseBySec"].items():
            look.setdefault(sk, {}).setdefault((course, tname), u["id"])
    D, P = model["days"], model["periods"]
    grids, unmatched = {}, []
    for section in model["sections"]:
        sk = section["key"]
        g = [[None] * P for _ in range(D)]
        rows = tt.get(sk) or []
        for d in range(min(len(rows), D)):
            row = rows[d] or []
            for s in range(min(len(row), P)):
                cell = row[s] or ["", ""]
                subj = (cell[0] or "").strip() if len(cell) > 0 else ""
                teacher = (cell[1] or "").strip() if len(cell) > 1 else ""
                if not subj or subj.lower().startswith("library"):
                    continue
                uid = (look.get(sk) or {}).get((subj, teacher))
                if uid is None:
                    unmatched.append({"section": sk, "day": d, "slot": s,
                                      "subject": subj, "teacher": teacher})
                else:
                    g[d][s] = uid
        grids[sk] = g
    return grids, unmatched


# ---------------------------------------------------------------- structured analysis
def analyze_structured(grids, model):
    """Structure-preserving twin of evaluate().

    Returns {"issues":[str...], "issues_detail":[{text,sig,units,cells}...],
             "violations":[{rule,detail,penalty,sig,units,cells}...],
             "penalty": int}.
    The 'issues' texts and the (rule, detail, penalty) of every violation are
    byte-identical to evaluate() output for the same grid (guarded by the
    test suite) — everything ELSE in the detail fields is additive metadata
    for the Manual Build 'insights' cards and targeted repair focusing."""

    def C(sec, d, s):
        return {"section": sec, "day": d, "slot": s}

    D = model["days"]; P = model["periods"]
    issues, det_i = [], []
    violations = []
    pen = model["penalties"]
    units = model["units"]
    by_id = {u["id"]: u for u in units}

    def course_of(u, sec):
        return u["courseBySec"].get(sec) or list(u["courseBySec"].values())[0]

    def _issue(text, sig, uids=None, cells=None):
        issues.append(text)
        det_i.append({"text": text, "sig": sig, "units": list(uids or []),
                      "cells": list(cells or [])})

    def _unit_cells(u):
        return [(sec, d, s) for sec in u["secs"]
                for d in range(D) for s in range(P)
                if grids.get(sec) and grids[sec][d][s] == u["id"]]

    # ---- per-section structural checks
    for section in model["sections"]:
        key = section["key"]
        g = grids.get(key)
        if g is None:
            _issue(f"{key}: missing grid", f"data@missing_grid:{key}")
            continue
        level = section["level"]
        counts = {}
        for d in range(D):
            if d in section["offDays"]:
                for s in range(P):
                    if g[d][s] is not None:
                        _issue(f"{key}: class on off day {_solver.DAYS[d]}",
                               f"section_offday@{key}:{d}", [g[d][s]],
                               [C(key, d, s2) for s2 in range(P) if g[d][s2] is not None])
                continue
            seen = set()
            occ_slots = [s for s in range(P) if g[d][s] is not None]
            for s in range(P):
                uid = g[d][s]
                if uid is None:
                    continue
                u = by_id.get(uid)
                if u is None:
                    _issue(f"{key}: unknown unit {uid}", f"data@unknown_unit:{key}",
                           None, [C(key, d, s)])
                    continue
                cname = course_of(u, key)
                counts[cname] = counts.get(cname, 0) + 1
                no_dup = (model["instructions"].get("noSameSubjectSameDay") or {}).get(level, True)
                if no_dup:
                    if cname in seen:
                        dup_units = [by_id[g[d][x]] for x in range(P)
                                     if g[d][x] is not None and by_id.get(g[d][x])
                                     and course_of(by_id[g[d][x]], key) == cname]
                        _issue(f"{key} {_solver.DAYS[d]} {cname} twice in a day",
                               f"sameday@{key}:{cname}:{d}",
                               [u2["id"] for u2 in dup_units],
                               [C(key, d, x) for x in range(P) if g[d][x] is not None
                                and by_id.get(g[d][x]) and course_of(by_id[g[d][x]], key) == cname])
                    seen.add(cname)
            if section["firstLast"] and level == "bs" and (
                    section["effDays"] and d in section["effDays"]):
                if occ_slots and (0 not in occ_slots or (P - 1) not in occ_slots):
                    _issue(f"{key} {_solver.DAYS[d]}: first/last period must be occupied",
                           f"firstlast@{key}:{d}", None, [])
        for cname, tlabel, cnt in section["subs"]:
            if counts.get(cname, 0) != cnt:
                uids = [u["id"] for u in units if u["courseBySec"].get(key) == cname]
                _issue(f"{key} {cname} load {counts.get(cname, 0)} != {cnt}",
                       f"load@{key}:{cname}", uids,
                       [C(*t) for u in units if u["courseBySec"].get(key) == cname
                        for t in _unit_cells(u)])
        if level == "inter":
            empty = sum(1 for d in range(D) for s in range(P) if g[d][s] is None)
            if empty:
                _issue(f"{key}: {empty} empty cells (inter sections fill the grid)",
                       f"data@empty:{key}", None,
                       [C(key, d, s) for d in range(D) for s in range(P) if g[d][s] is None])

    # ---- teacher occupancy (deduped for dual-section/parallel units)
    occ = {}
    occ_units = {}
    for u in units:
        if not u["group"] and not u["teacher"]:
            _issue(f"unit {u['id']} ({list(u['courseBySec'].values())}): unresolved teacher",
                   f"data@unresolved:{u['id']}", [u["id"]], [])
        cells = set()
        for sec in u["secs"]:
            g = grids.get(sec)
            if not g:
                continue
            for d in range(D):
                for s in range(P):
                    if g[d][s] == u["id"]:
                        cells.add((d, s))
        teachers = [u["teacher"]] + (u["members"] if u["group"] else [])
        for t in teachers:
            if t is None:
                continue
            for (d, s) in cells:
                occ.setdefault(t, []).append([d, s, u["secs"][0]])
                occ_units.setdefault(t, {}).setdefault((d, s), set()).add(u["id"])
    for t, lst in occ.items():
        seen = set()
        flagged = False
        for (d, s, k) in lst:
            if (d * P + s) in seen:
                flagged = True
                uids = sorted(occ_units[t][(d, s)])
                secs = sorted({by_id[uid]["secs"][0] for uid in uids})
                cells = []
                for uid in uids:
                    u = by_id[uid]
                    cells.append(C(u["secs"][0], d, s))
                _issue(f"teacher {t} double-booked {_solver.DAYS[d]} {_solver.SLOTS[s]}",
                       f"teacher_double@{t}", uids,
                       [C(sec2, d, s) for sec2 in secs])
            seen.add(d * P + s)

    # ---- combined classes: identical (day,slot) sets in both sections
    for cc in model["combined"]:
        u = by_id[cc["unit"]]
        if len(u["secs"]) != 2:
            continue
        a, b = u["secs"]
        ca = {(d, s) for d in range(D) for s in range(P)
              if grids.get(a) and grids[a][d][s] == u["id"]}
        cb = {(d, s) for d in range(D) for s in range(P)
              if grids.get(b) and grids[b][d][s] == u["id"]}
        if ca != cb:
            cells = ([C(a, d, s) for (d, s) in sorted(ca | cb)] +
                     [C(b, d, s) for (d, s) in sorted(ca | cb)])
            _issue(f"combined {cc['id']}: slot sets differ between {a} and {b}",
                   f"combined@{cc['id']}", [u["id"]], cells)

    # ---- parallel groups: single slot, within group slots; members occupied there
    for u in units:
        if not u["group"]:
            continue
        cells = [(d, s) for sec in u["secs"]
                 for d in range(D) for s in range(P)
                 if grids.get(sec) and grids[sec][d][s] == u["id"]]
        slots = {s for (_, s) in cells}
        if len(cells) != u["count"]:
            _issue(f"parallel {u['group']}: {len(cells)} cells != {u['count']}",
                   f"parallel@{u['group']}", [u["id"]],
                   [C(sec, d, s) for sec in u["secs"] for (d, s) in cells])
        if len(slots) != 1:
            _issue(f"parallel {u['group']}: spans slots {sorted(slots)}",
                   f"parallel@{u['group']}", [u["id"]],
                   [C(sec, d, s) for sec in u["secs"] for (d, s) in cells])

    # ---- day-exclusive pairs
    for p in model["dayExclusive"]:
        uids = p["units"]
        daysets = []
        for uid in uids:
            u = by_id[uid]
            days = {d for sec in u["secs"] for d in range(D)
                    for s in range(P)
                    if grids.get(sec) and grids[sec][d][s] == uid}
            daysets.append((u, days))
        for i in range(len(daysets)):
            for j in range(i + 1, len(daysets)):
                shared = daysets[i][1] & daysets[j][1]
                if shared:
                    _issue(f"dayExclusive {p['id']}: {course_of(daysets[i][0], daysets[i][0]['secs'][0])} "
                           f"shares day(s) {sorted(shared)} with {course_of(daysets[j][0], daysets[j][0]['secs'][0])}",
                           f"dayex@{p['id']}",
                           [daysets[i][0]["id"], daysets[j][0]["id"]],
                           [C(daysets[i][0]["secs"][0], d, s) for d in sorted(shared)
                            for s in range(P)
                            if any(grids.get(sec) and grids[sec][d][s] == daysets[i][0]["id"]
                                   for sec in daysets[i][0]["secs"])] +
                           [C(daysets[j][0]["secs"][0], d, s) for d in sorted(shared)
                            for s in range(P)
                            if any(grids.get(sec) and grids[sec][d][s] == daysets[j][0]["id"]
                                   for sec in daysets[j][0]["secs"])])
        if p["softConsecutiveDays"]:
            for u, days in daysets:
                if u["count"] == 2 and len(days) == 2:
                    d0, d1 = sorted(days)
                    if d1 - d0 != 1:
                        cname = course_of(u, u["secs"][0])
                        violations.append({"rule": f"dayExclusive:{p['id']}",
                                           "detail": f"{cname} on non-consecutive days {_solver.DAYS[d0]},{_solver.DAYS[d1]}",
                                           "penalty": pen["nonConsecutive"],
                                           "sig": f"soft_dayex@{p['id']}:{cname}",
                                           "units": [u["id"]],
                                           "cells": [C(*t) for t in _unit_cells(u)]})

    # ---- consecutive days for 2/wk inter units
    for u in units:
        lvl = u["level"]
        if u["count"] != 2 or lvl != "inter":
            continue
        if not (model["instructions"].get("consecutiveFor2pw") or {}).get("inter", False):
            continue
        days = {d for sec in u["secs"] for d in range(D) for s in range(P)
                if grids.get(sec) and grids[sec][d][s] == u["id"]}
        if len(days) == 2:
            d0, d1 = sorted(days)
            if d1 - d0 != 1:
                _issue(f"{u['secs'][0]} {course_of(u, u['secs'][0])}: "
                       f"2/wk on non-consecutive days {_solver.DAYS[d0]},{_solver.DAYS[d1]}",
                       f"twopw@{u['id']}", [u["id"]],
                       [C(*t) for t in _unit_cells(u)])

    # ---- faculty constraints (person-level; soft rules -> violations) —
    # same shared walker as evaluate(): repair tickets come from identical logic.
    R = model["constraints"]
    pop_of = {s["key"]: s.get("pop") for s in model.get("sections", [])}
    for code, entry in R.items():
        my_units = [u for u in units if u["teacher"] == code or (u["members"] and code in u["members"])]
        if not my_units:
            continue
        cells = []
        for u in my_units:
            for sec in u["secs"]:
                g = grids.get(sec)
                if not g:
                    continue
                for d in range(D):
                    for s in range(P):
                        if g[d][s] == u["id"]:
                            cells.append((d, s, sec, u))
        for f in teacher_rule_findings(code, entry, my_units, cells, pop_of, D, P, pen):
            uids = f["uids"]
            clist = [C(sec, d, s) for (sec, d, s) in f["cells"]]
            if f["soft"]:
                violations.append({"rule": f"{code}:{f['rule_key']}", "detail": f["msg"],
                                   "penalty": f["pen"] if f["pen"] is not None else pen["rule"],
                                   "sig": f"facrule@{code}:{f['rule_key']}",
                                   "units": uids, "cells": clist})
            else:
                _issue(f"{code} {f['msg']}", f"facrule@{code}:{f['rule_key']}", uids, clist)

    # ---- general instructions (institution-level)
    for e in (model["instructions"].get("subjectForbiddenDays") or []):
        for u in units:
            for sec in u["secs"]:
                if course_of(u, sec) != e["subject"]:
                    continue
                scope = e.get("scope")
                if scope and _sec_stream(sec) != scope:
                    continue
                g = grids.get(sec)
                if not g:
                    continue
                dset = _dayset(e["days"])
                bad_cells = [(d, s) for d in range(D) for s in range(P)
                             if g[d][s] == u["id"] and d in dset]
                for (d, s) in bad_cells:
                    _issue(f"{sec} {e['subject']} on forbidden day {_solver.DAYS[d]}",
                           f"gi_sfbd@{e['subject']}|{scope}", [u["id"]],
                           [C(sec, d, s)])

    for e in (model["instructions"].get("subjectForbiddenSlotDays") or []):
        for u in units:
            for sec in u["secs"]:
                if not _dyn_cells_hit(e, u, sec):
                    continue
                g = grids.get(sec)
                if not g:
                    continue
                scope = e.get("scope")
                dset = _dayset(e.get("days") or [d for d in range(D)])
                sset = _slotset(e.get("slots") or ["P%d" % (s + 1) for s in range(P)])
                bad_cells = [(d, s) for d in range(D) for s in range(P)
                             if g[d][s] == u["id"] and d in dset and s in sset]
                for (d, s) in bad_cells:
                    _issue(f"{sec} {_dyn_label(e)} at forbidden window {_solver.DAYS[d]} {_solver.SLOTS[s]}",
                           f"gi_sfsd@{_dyn_label(e)}|{scope}", [u["id"]],
                           [C(sec, d, s)])
    for e in (model["instructions"].get("nonOverriding") or []):
        secs = e["sections"]
        subs = e["subjects"]
        for x in secs:
            gx = grids.get(x)
            if not gx:
                continue
            found = False
            for d in range(D):
                for s in range(P):
                    uid = gx[d][s]
                    if uid is None:
                        continue
                    u = by_id.get(uid)
                    if u and course_of(u, x) == subs[0]:
                        ok = True
                        for y in secs:
                            if y == x:
                                continue
                            gy = grids.get(y)
                            if not gy:
                                continue
                            uidy = gy[d][s]
                            uy = by_id.get(uidy) if uidy is not None else None
                            if uy and course_of(uy, y) == subs[1]:
                                ok = False
                                break
                        if ok:
                            found = True
                            break
                if found:
                    break
            if not found:
                xids = [u2["id"] for u2 in units if u2["courseBySec"].get(x) == subs[0]]
                _issue(f"non-overriding failed {x}", f"gi_no@{x}", xids, [])
    if model["instructions"].get("softIndividualSpread"):
        for t, lst in occ.items():
            slots = {s for (d, s, k) in lst}
            if 0 in slots and (P - 1) in slots:
                tuids = sorted({uid for (d, s) in
                                ({(dd, ss) for (dd, ss, k) in lst if ss == 0} |
                                 {(dd, ss) for (dd, ss, k) in lst if ss == P - 1})
                                for uid in occ_units.get(t, {}).get((d, s), set())})
                violations.append({"rule": f"{t}:soft_individual_spread",
                                   "detail": f"engaged in P1 and {_solver.SLOTS[P-1]} in the same week",
                                   "penalty": pen["individualSpread"],
                                   "sig": f"softspread@{t}",
                                   "units": tuids,
                                   "cells": [C(k, d, s) for (d, s, k) in lst
                                             if s == 0 or s == P - 1]})

    return {"issues": issues, "issues_detail": det_i,
            "violations": violations,
            "penalty": sum(v["penalty"] for v in violations)}
