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
    return _c.name_to_code().get(x)


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
    }


def model_section_fill(model, section):
    """Cells a section occupies (dual units count in both of their sections)."""
    fill = 0
    for u in model["units"]:
        if section["key"] in u["courseBySec"]:
            fill += u["count"]
    return fill


# ---------------------------------------------------------------- evaluation
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

    # ---- faculty constraints (person-level; soft rules -> violations)
    R = model["constraints"]
    for code, entry in R.items():
        rules = (entry or {}).get("rules") or {}
        soft = set((entry or {}).get("soft") or [])
        my_units = [u for u in units if u["teacher"] == code or (u["members"] and code in u["members"])]
        if not my_units:
            continue
        # collect this teacher's cells (own name; parallel group cells count for members too)
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
        seen_ds = set()
        per_day = {}
        for (d, s, sec, u) in cells:
            seen_ds.add((d, s))
            per_day[d] = per_day.get(d, 0) + 1

        def flag(msg, rule_key, is_soft):
            if is_soft:
                violations.append({"rule": f"{code}:{rule_key}", "detail": msg,
                                   "penalty": pen["rule"]})
            else:
                issues.append(f"{code} {msg}")

        # availability
        fs = _slotset(rules.get("forbidden_slots")) if rules.get("forbidden_slots") is not None else None
        if fs is not None:
            bad = sorted({s for (d, s, sec, u) in cells if s in fs})
            if bad:
                flag(f"teaches in forbidden slot(s) {[_solver.SLOTS[s] for s in bad]}", "forbidden_slots", "forbidden_slots" in soft)
        as_ = _slotset(rules.get("allowed_slots")) if rules.get("allowed_slots") is not None else None
        if as_ is not None:
            bad = sorted({s for (d, s, sec, u) in cells if s not in as_})
            if bad:
                flag(f"teaches outside allowed slots {[_solver.SLOTS[s] for s in bad]}", "allowed_slots", "allowed_slots" in soft)
        fd = _dayset(rules.get("forbidden_days")) if rules.get("forbidden_days") is not None else None
        if fd is not None:
            bad = sorted({d for (d, s, sec, u) in cells if d in fd})
            if bad:
                flag(f"teaches on forbidden day(s) {[_solver.DAYS[d] for d in bad]}", "forbidden_days", "forbidden_days" in soft)
        ad = _dayset(rules.get("allowed_days")) if rules.get("allowed_days") is not None else None
        if ad is not None:
            bad = sorted({d for (d, s, sec, u) in cells if d not in ad})
            if bad:
                flag(f"teaches on non-allowed day(s) {[_solver.DAYS[d] for d in bad]}", "allowed_days", "allowed_days" in soft)
        for e in (rules.get("forbidden_slots_on_days") or []):
            dset, sset = _dayset(e["days"]), _slotset(e["slots"])
            bad = sorted({(d, s) for (d, s, sec, u) in cells if d in dset and s in sset})
            if bad:
                flag(f"teaches in forbidden day/slot {[_solver.DAYS[d] + ' ' + _solver.SLOTS[s] for (d, s) in bad]}",
                     "forbidden_slots_on_days", "forbidden_slots_on_days" in soft)
        # stream-scoped availability (only the units in that stream)
        for e in (rules.get("allowed_slots_in_stream") or []):
            sset = _slotset(e["slots"])
            bad = sorted({s for (d, s, sec, u) in cells
                          if _sec_stream(sec) == e["stream"] and s not in sset})
            if bad:
                flag(f"{e['stream']} classes outside allowed slots {[_solver.SLOTS[s] for s in bad]}",
                     "allowed_slots_in_stream", "allowed_slots_in_stream" in soft)
        for e in (rules.get("allowed_days_in_stream") or []):
            dset = _dayset(e["days"])
            bad = sorted({d for (d, s, sec, u) in cells
                          if _sec_stream(sec) == e["stream"] and d not in dset})
            if bad:
                flag(f"{e['stream']} classes on non-allowed day(s) {[_solver.DAYS[d] for d in bad]}",
                     "allowed_days_in_stream", "allowed_days_in_stream" in soft)
        # engagement requirements
        for e in (rules.get("min_days_in_slot") or []):
            si = SLOT_OF[e["slot"]]
            days = {d for (d, s, sec, u) in cells if s == si}
            if len(days) < (e.get("min_days") or 1):
                flag(f"{e['slot']} engaged only {len(days)} days (<{e.get('min_days')})",
                     "min_days_in_slot", "min_days_in_slot" in soft)
        if rules.get("min_days_engaged"):
            if len(per_day) < rules["min_days_engaged"]:
                flag(f"engaged only {len(per_day)} days (<{rules['min_days_engaged']})",
                     "min_days_engaged", "min_days_engaged" in soft)
        for e in (rules.get("stream_slots_required") or []):
            # the stream must exist in this context — otherwise vacuous
            if not any(_sec_stream(sec) == e["stream"]
                       for u in my_units for sec in u["secs"]):
                continue
            for sl in e["slots"]:
                si = SLOT_OF[sl]
                days = {d for (d, s, sec, u) in cells
                        if s == si and _sec_stream(sec) == e["stream"]}
                if len(days) < 4:
                    flag(f"{e['stream']} {sl} engaged only {len(days)} days (<4)",
                         "stream_slots_required", "stream_slots_required" in soft)
        # subject placement (per unit, by course)
        for e in (rules.get("subject_slots") or []):
            for (d, s, sec, u) in cells:
                if course_of(u, sec) == e["subject"] and s not in _slotset(e["slots"]):
                    flag(f"{e['subject']} not in {e['slots']} ({sec})", "subject_slots", "subject_slots" in soft)
        for e in (rules.get("subject_forbidden_days") or []):
            for (d, s, sec, u) in cells:
                if course_of(u, sec) == e["subject"] and d in _dayset(e["days"]):
                    flag(f"{e['subject']} on {_solver.DAYS[d]} ({sec})", "subject_forbidden_days",
                         "subject_forbidden_days" in soft)
        for e in (rules.get("subject_slot_days") or []):
            sset = _slotset([e["slot"]])
            dset = _dayset(e["days"])
            for (d, s, sec, u) in cells:
                if course_of(u, sec) == e["subject"] and (s not in sset or d not in dset):
                    flag(f"{e['subject']} must be {e['slot']} on {'/'.join(e['days'])} ({sec})",
                         "subject_slot_days", "subject_slot_days" in soft)
        # soft-only rules
        if rules.get("soft_prefer_free_slots"):
            sset = _slotset(rules["soft_prefer_free_slots"])
            n = sum(1 for (d, s, sec, u) in cells if s in sset)
            if n:
                violations.append({"rule": f"{code}:soft_prefer_free_slots",
                                   "detail": f"{n} period(s) in preferred-free slots "
                                             f"{rules['soft_prefer_free_slots']}",
                                   "penalty": pen["preferFreeSlot"] * n})
        if rules.get("soft_even_distribution"):
            total = len(cells)
            cap = -(-total // max(1, len(per_day) or 1))   # ceil(total / days used)
            excess = sum(max(0, c - cap) for c in per_day.values())
            if excess:
                violations.append({"rule": f"{code}:soft_even_distribution",
                                   "detail": f"{excess} period(s) above the even per-day share",
                                   "penalty": pen["evenDistribution"] * excess})

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

    # ---- faculty constraints (person-level; soft rules -> violations)
    R = model["constraints"]
    for code, entry in R.items():
        rules = (entry or {}).get("rules") or {}
        soft = set((entry or {}).get("soft") or [])
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
        seen_ds = set()
        per_day = {}
        for (d, s, sec, u) in cells:
            seen_ds.add((d, s))
            per_day[d] = per_day.get(d, 0) + 1

        def flag(msg, rule_key, is_soft, uids=None, clist=None):
            if is_soft:
                violations.append({"rule": f"{code}:{rule_key}", "detail": msg,
                                   "penalty": pen["rule"],
                                   "sig": f"facrule@{code}:{rule_key}",
                                   "units": list(uids or [u2["id"] for u2 in my_units]),
                                   "cells": list(clist or [])})
            else:
                _issue(f"{code} {msg}", f"facrule@{code}:{rule_key}",
                       uids if uids is not None else [u2["id"] for u2 in my_units],
                       clist or [])

        fs = _slotset(rules.get("forbidden_slots")) if rules.get("forbidden_slots") is not None else None
        if fs is not None:
            bad = sorted({s for (d, s, sec, u) in cells if s in fs})
            if bad:
                uids = sorted({u["id"] for (d, s, sec, u) in cells if s in fs})
                flag(f"teaches in forbidden slot(s) {[_solver.SLOTS[s] for s in bad]}", "forbidden_slots",
                     "forbidden_slots" in soft, uids,
                     [C(sec, d, s) for (d, s, sec, u) in cells if s in fs])
        as_ = _slotset(rules.get("allowed_slots")) if rules.get("allowed_slots") is not None else None
        if as_ is not None:
            bad = sorted({s for (d, s, sec, u) in cells if s not in as_})
            if bad:
                uids = sorted({u["id"] for (d, s, sec, u) in cells if s not in as_})
                flag(f"teaches outside allowed slots {[_solver.SLOTS[s] for s in bad]}", "allowed_slots",
                     "allowed_slots" in soft, uids,
                     [C(sec, d, s) for (d, s, sec, u) in cells if s not in as_])
        fd = _dayset(rules.get("forbidden_days")) if rules.get("forbidden_days") is not None else None
        if fd is not None:
            bad = sorted({d for (d, s, sec, u) in cells if d in fd})
            if bad:
                uids = sorted({u["id"] for (d, s, sec, u) in cells if d in fd})
                flag(f"teaches on forbidden day(s) {[_solver.DAYS[d] for d in bad]}", "forbidden_days",
                     "forbidden_days" in soft, uids,
                     [C(sec, d, s) for (d, s, sec, u) in cells if d in fd])
        ad = _dayset(rules.get("allowed_days")) if rules.get("allowed_days") is not None else None
        if ad is not None:
            bad = sorted({d for (d, s, sec, u) in cells if d not in ad})
            if bad:
                uids = sorted({u["id"] for (d, s, sec, u) in cells if d not in ad})
                flag(f"teaches on non-allowed day(s) {[_solver.DAYS[d] for d in bad]}", "allowed_days",
                     "allowed_days" in soft, uids,
                     [C(sec, d, s) for (d, s, sec, u) in cells if d not in ad])
        for e in (rules.get("forbidden_slots_on_days") or []):
            dset, sset = _dayset(e["days"]), _slotset(e["slots"])
            bad = sorted({(d, s) for (d, s, sec, u) in cells if d in dset and s in sset})
            if bad:
                uids = sorted({u["id"] for (d, s, sec, u) in cells if d in dset and s in sset})
                flag(f"teaches in forbidden day/slot {[_solver.DAYS[d] + ' ' + _solver.SLOTS[s] for (d, s) in bad]}",
                     "forbidden_slots_on_days", "forbidden_slots_on_days" in soft, uids,
                     [C(sec, d, s) for (d, s, sec, u) in cells if d in dset and s in sset])
        for e in (rules.get("allowed_slots_in_stream") or []):
            sset = _slotset(e["slots"])
            bad = sorted({s for (d, s, sec, u) in cells
                          if _sec_stream(sec) == e["stream"] and s not in sset})
            if bad:
                uids = sorted({u["id"] for (d, s, sec, u) in cells
                               if _sec_stream(sec) == e["stream"] and s not in sset})
                flag(f"{e['stream']} classes outside allowed slots {[_solver.SLOTS[s] for s in bad]}",
                     "allowed_slots_in_stream", "allowed_slots_in_stream" in soft, uids,
                     [C(sec, d, s) for (d, s, sec, u) in cells
                      if _sec_stream(sec) == e["stream"] and s not in sset])
        for e in (rules.get("allowed_days_in_stream") or []):
            dset = _dayset(e["days"])
            bad = sorted({d for (d, s, sec, u) in cells
                          if _sec_stream(sec) == e["stream"] and d not in dset})
            if bad:
                uids = sorted({u["id"] for (d, s, sec, u) in cells
                               if _sec_stream(sec) == e["stream"] and d not in dset})
                flag(f"{e['stream']} classes on non-allowed day(s) {[_solver.DAYS[d] for d in bad]}",
                     "allowed_days_in_stream", "allowed_days_in_stream" in soft, uids,
                     [C(sec, d, s) for (d, s, sec, u) in cells
                      if _sec_stream(sec) == e["stream"] and d not in dset])
        for e in (rules.get("min_days_in_slot") or []):
            si = SLOT_OF[e["slot"]]
            days = {d for (d, s, sec, u) in cells if s == si}
            if len(days) < (e.get("min_days") or 1):
                flag(f"{e['slot']} engaged only {len(days)} days (<{e.get('min_days')})",
                     "min_days_in_slot", "min_days_in_slot" in soft)
        if rules.get("min_days_engaged"):
            if len(per_day) < rules["min_days_engaged"]:
                flag(f"engaged only {len(per_day)} days (<{rules['min_days_engaged']})",
                     "min_days_engaged", "min_days_engaged" in soft)
        for e in (rules.get("stream_slots_required") or []):
            if not any(_sec_stream(sec) == e["stream"]
                       for u in my_units for sec in u["secs"]):
                continue
            for sl in e["slots"]:
                si = SLOT_OF[sl]
                days = {d for (d, s, sec, u) in cells
                        if s == si and _sec_stream(sec) == e["stream"]}
                if len(days) < 4:
                    flag(f"{e['stream']} {sl} engaged only {len(days)} days (<4)",
                         "stream_slots_required", "stream_slots_required" in soft)
        for e in (rules.get("subject_slots") or []):
            for (d, s, sec, u) in cells:
                if course_of(u, sec) == e["subject"] and s not in _slotset(e["slots"]):
                    flag(f"{e['subject']} not in {e['slots']} ({sec})", "subject_slots",
                         "subject_slots" in soft, [u["id"]], [C(sec, d, s)])
        for e in (rules.get("subject_forbidden_days") or []):
            for (d, s, sec, u) in cells:
                if course_of(u, sec) == e["subject"] and d in _dayset(e["days"]):
                    flag(f"{e['subject']} on {_solver.DAYS[d]} ({sec})", "subject_forbidden_days",
                         "subject_forbidden_days" in soft, [u["id"]], [C(sec, d, s)])
        for e in (rules.get("subject_slot_days") or []):
            sset = _slotset([e["slot"]])
            dset = _dayset(e["days"])
            for (d, s, sec, u) in cells:
                if course_of(u, sec) == e["subject"] and (s not in sset or d not in dset):
                    flag(f"{e['subject']} must be {e['slot']} on {'/'.join(e['days'])} ({sec})",
                         "subject_slot_days", "subject_slot_days" in soft,
                         [u["id"]], [C(sec, d, s)])
        if rules.get("soft_prefer_free_slots"):
            sset = _slotset(rules["soft_prefer_free_slots"])
            n = sum(1 for (d, s, sec, u) in cells if s in sset)
            if n:
                violations.append({"rule": f"{code}:soft_prefer_free_slots",
                                   "detail": f"{n} period(s) in preferred-free slots "
                                             f"{rules['soft_prefer_free_slots']}",
                                   "penalty": pen["preferFreeSlot"] * n,
                                   "sig": f"softpref@{code}",
                                   "units": sorted({u["id"] for (d, s, sec, u) in cells if s in sset}),
                                   "cells": [C(sec, d, s) for (d, s, sec, u) in cells if s in sset]})
        if rules.get("soft_even_distribution"):
            total = len(cells)
            cap = -(-total // max(1, len(per_day) or 1))
            excess = sum(max(0, c - cap) for c in per_day.values())
            if excess:
                violations.append({"rule": f"{code}:soft_even_distribution",
                                   "detail": f"{excess} period(s) above the even per-day share",
                                   "penalty": pen["evenDistribution"] * excess,
                                   "sig": f"softeven@{code}",
                                   "units": [u2["id"] for u2 in my_units],
                                   "cells": [C(*t) for u2 in my_units for t in _unit_cells(u2)]})

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
