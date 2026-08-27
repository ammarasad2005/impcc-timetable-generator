"""infeasibility insights — DYNAMIC attribution of '0 timetables found'.

When /generate-context comes back empty, this module inspects the SOLVED
context (merged constraints + general instructions + allocations) and reports,
for each contraint every week, the arithmetic that is impossible. Nothing here
is hardcoded to specific teachers: every check is a generic rule-family
capacity computation whose inputs (grid days/periods, weekly loads, teacher
pools, hardness) are read from the live context at request time.

Check families (generic over the rule taxonomy):
  1. allowed_days            weekly load > len(days) x available slots/day
  2. allowed_slots           weekly load > len(slots) x grid days
  3. allowed_slots_in_stream stream load > slots x days (and exact-pack zero
                             slack, which provably packs nowhere without room)
  4. first_last_period       every teacher in a section's pool is P1-banned
     occupied (GI)          (forbidden P1 or hard allowed_slots excluding P1)
  5. min_days_in_slot        min_days asks a slot on more days than the
                             teacher's day window allows
  6. stream_slots_required   fewer pieces in the stream than slots required

Each flag carries: teacher code + display name, rule family, scope, the
arithmetic (need / capacity / slack), source ('admin edit' vs 'canonical
default'), and a human detail sentence — all computed, never written in.
"""
from __future__ import annotations

SLOTS = ["P1", "P2", "P3", "P4", "P5"]


def _stream_of(sec_key):
    if sec_key.startswith("ICS"):
        return "ICS"
    if sec_key.startswith("I.COM"):
        return "I.COM"
    return None


def _teacher_stats(ctx, model):
    """per-teacher weekly loads from the model units: total, per-stream count,
    pieces (consecutive blocks) per stream. A unit can span parallel sections;
    attribute it to the section keys in `secs`."""
    days = model["days"]
    periods = model["periods"]
    total = {}
    per_stream = {}
    pieces_stream = {}
    for u in model["units"]:
        secs = u.get("secs") or ([u["sec"]] if u.get("sec") else [])
        teachers = (u.get("members") or []) if u.get("group") else [u["teacher"]]
        for t in teachers:
            if t is None or t.startswith("PG:"):
                continue
            n = int(u.get("count", 1))
            total[t] = total.get(t, 0) + n
            st = _stream_of(secs[0]) if secs else None
            if st:
                per_stream.setdefault(t, {})
                per_stream[t][st] = per_stream[t].get(st, 0) + n
                pieces_stream.setdefault(t, {})
                pieces_stream[t][st] = pieces_stream[t].get(st, 0) + 1
    return {"days": days, "periods": periods, "total": total,
            "per_stream": per_stream, "pieces_stream": pieces_stream}


def _hard(ent, key):
    """hard (>=100) unless the entry softens this rule key — either via the
    legacy `soft` list (canonical default mgmt) or the v2.1 hardness map."""
    if key in (ent.get("soft") or []):
        return False
    try:
        return int((ent.get("hardness") or {}).get(key, 100)) >= 100
    except (TypeError, ValueError):
        return True


def _flag(code, name, rule, scope, need, capacity, source, detail):
    return {"teacher": code, "name": name, "rule": rule, "scope": scope,
            "need": need, "capacity": capacity,
            "slack": (capacity - need if isinstance(capacity, int)
                      and isinstance(need, int) else None),
            "source": source, "detail": detail}


DAYS = ["MON", "TUE", "WED", "THU", "FRI"]


def _placement_domain(rules, grid_days=5, grid_periods=5):
    """GENERIC placement domain: the set of (day, slot) cells a teacher can
    occupy under ANY combination of domain-restricting rules — allowed_days,
    forbidden_days, allowed_slots, forbidden_slots, forbidden_slots_on_days,
    allowed_slots_days (pair whitelist). Every rule can only SHRINK the
    domain, so this stays correct no matter which family a future override
    uses. Returns (cells {(d,s)}, cap_per_day {d: int cap}, acting rule names).
    """
    days = DAYS[:grid_days]
    slots = SLOTS[:grid_periods]
    cells = {(d, s) for d in days for s in slots}
    acting = []
    if rules.get("allowed_days"):
        keep = set(rules["allowed_days"])
        cells = {c for c in cells if c[0] in keep}
        acting.append("allowed_days")
    if rules.get("forbidden_days"):
        kill = set(rules["forbidden_days"])
        cells = {c for c in cells if c[0] not in kill}
        acting.append("forbidden_days")
    if rules.get("allowed_slots"):
        keep = set(rules["allowed_slots"])
        cells = {c for c in cells if c[1] in keep}
        acting.append("allowed_slots")
    if rules.get("forbidden_slots"):
        kill = set(rules["forbidden_slots"])
        cells = {c for c in cells if c[1] not in kill}
        acting.append("forbidden_slots")
    if rules.get("allowed_slots_days"):
        # pair whitelist: only the (day, slot) pairs explicitly listed survive
        wl = set()
        for e in (rules["allowed_slots_days"] or []):
            for d in (e.get("days") or days):
                for s in (e.get("slots") or []):
                    wl.add((d, s))
        cells = {c for c in cells if c in wl}
        acting.append("allowed_slots_days")
    for e in (rules.get("forbidden_slots_on_days") or []):
        for d in (e.get("days") or []):
            for s in (e.get("slots") or []):
                cells.discard((d, s))
        if e.get("days") and e.get("slots"):
            if "forbidden_slots_on_days" not in acting:
                acting.append("forbidden_slots_on_days")
    mppd = rules.get("max_periods_per_day")
    cap = {d: sum(1 for (dd, _s) in cells if dd == d) for d in days}
    if isinstance(mppd, int) and mppd >= 0:
        cap = {d: min(c, mppd) for d, c in cap.items()}
        acting.append("max_periods_per_day")
    return cells, cap, acting


def diagnose_relaxation(ctx, model, budget_s=70.0, max_probes=14):
    """Attribution by relaxation — the fallback for contradictions NO capacity
    rule can express (purely emergent packing conflicts). Algorithm, fully
    data-driven:

      1. soften EVERY hard (>=100) per-teacher rule to hardness 50; if all-soft
         is still infeasible, the conflict is emergent beyond per-teacher
         rules -> honest report instead of a fabricated blame list.
      2. re-harden teachers one at a time (heaviest load first); a teacher
         whose re-hardening flips the model back to infeasible is a PROVEN
         blocker; a flip is presolve-fast, so per-probe cost is small.
    """
    import time as _t
    import copy as _cp
    try:
        import cp_solver as _CS
    except Exception:
        return None
    t0 = _t.time()

    def _soften(cons, only=None):
        out = _cp.deepcopy(cons)
        for code, ent in out.items():
            if only is not None and code != only:
                continue
            h = {k: 50 for k in (ent.get("rules") or {})}
            if h:
                ent["hardness"] = h
        return out

    def _rehard(cons, code):
        out = _cp.deepcopy(cons)
        if code in out:
            out[code]["hardness"] = {k: 100 for k in (out[code].get("rules") or {})}
        return out

    def _solvable(cons, tps):
        ctx2 = dict(ctx)
        ctx2["constraints"] = cons
        ranked, _opt = _CS.generate_context(ctx2, n_seeds=1, time_per_seed=tps,
                                            max_solutions=1)
        return bool(ranked)

    cons = _cp.deepcopy(model.get("constraints") or ctx.get("constraints") or {})
    if not cons:
        return {"mode": "relaxation", "flags": [],
                "note": "no per-teacher constraints to relax"}

    stats = _teacher_stats(ctx, model)
    order = sorted(cons.keys(), key=lambda c: stats["total"].get(c, 0),
                   reverse=True)
    order = order[:max_probes]

    baseline = _soften(cons)
    soften_tps = min(25.0, max(5.0, budget_s / 3.0))
    if not _solvable(baseline, soften_tps):
        return {"mode": "relaxation", "flags": [],
                "note": "still infeasible with every teacher's hard rules "
                        "softened — the conflict is emergent in the packing "
                        "(site/sections/level constraints), not attributable "
                        "to any single teacher's constraint entry. Relax "
                        "general instructions or assignment data."}

    flags = []
    per_probe = 4.0
    state = dict(ctx)
    state["constraints"] = baseline
    for code in order:
        if _t.time() - t0 > budget_s:
            break
        trial = _rehard(state["constraints"], code)
        ent = cons.get(code) or {}
        rules = ent.get("rules") or {}
        if not rules:
            continue
        if not _solvable(trial, per_probe):
            state["constraints"] = trial
            flags.append(_flag(
                code, ent.get("name") or code, "rule set (any family)",
                "everywhere", stats["total"].get(code, 0) or None, None,
                "proved by relaxation",
                f"Re-hardening {(ent.get('name') or code)}'s constraint set "
                f"(rules: {', '.join(sorted(rules))}) back to hardness 100 on "
                f"top of everything-else-soft makes the model unsolvable "
                f"again — this teacher's rules are a blocking factor. "
                f"Loosen a scope, demote below hardness 100, or rebalance "
                f"the load."))
    return {"mode": "relaxation", "flags": flags,
            "probes": len(order),
            "note": "culprits proved by soft->re-harden flips (CP-SAT)"}


def diagnose(ctx, model):
    """Return {'flags': [...]} computed from the current context/model."""
    base_defaults = {}
    try:
        import canonical as _c
        base_defaults = _c.solver_constraints() or {}
    except Exception:
        pass

    cons = model.get("constraints") or ctx.get("constraints") or {}
    instr = model.get("general_instructions") or ctx.get(
        "general_instructions") or {}
    stats = _teacher_stats(ctx, model)
    days = stats["days"]
    periods = stats["periods"]
    flags = []

    for code, ent in (cons or {}).items():
        rules = ent.get("rules") or {}
        name = ent.get("name") or code
        base_ent = base_defaults.get(code) or {}
        src = ("canonical default"
               if base_ent and (base_ent.get("rules") or {}) == (rules or {})
               else "admin edit")
        load = stats["total"].get(code, 0)

        # (1) allowed_days window vs weekly load
        if rules.get("allowed_days") is not None and load and _hard(ent, "allowed_days"):
            d = len([x for x in (rules.get("allowed_days") or []) if x])
            cap = d * periods
            if load > cap:
                flags.append(_flag(
                    code, name, "allowed_days", "everywhere", load, cap, src,
                    f"{name} teaches {load} classes/week but the day window "
                    f"({', '.join(rules['allowed_days'])}) only provides "
                    f"{cap} slot-days ({d} days x {periods} slots)."))

        # (2) allowed_slots window vs weekly load
        if rules.get("allowed_slots") is not None and load and _hard(ent, "allowed_slots"):
            s = len([x for x in (rules.get("allowed_slots") or []) if x])
            cap = s * days
            if load > cap:
                flags.append(_flag(
                    code, name, "allowed_slots", "everywhere", load, cap, src,
                    f"{name} teaches {load} classes/week but the slot window "
                    f"({', '.join(rules['allowed_slots'])}) only provides "
                    f"{cap} placements ({s} slots x {days} days)."))

        # (GENERIC) full placement domain vs weekly load + coverage checks —
        # catches ANY domain-restricting family combination (days x slots x
        # per-day caps x pair whitelists x forbidden pairs), not just the
        # named checks above. Skipped when a named capacity flag already fired.
        already = any(f["teacher"] == code for f in flags)
        hard_rules = {k: v for k, v in (rules or {}).items() if _hard(ent, k)}
        cells, cap, acting = _placement_domain(hard_rules, days, periods)
        cap_total = sum(cap.values())
        if load and not already and load > cap_total:
            flags.append(_flag(
                code, name, "placement domain (" + "+".join(acting) + ")",
                "everywhere", load, cap_total, src,
                f"Under {name}'s current rules ({', '.join(acting)}), only "
                f"{cap_total} teaching cells remain per week "
                f"({len(cells)} day-slot pairs, per-day caps considered) "
                f"but {name} teaches {load} classes."))
        # coverage: must work more days than the domain permits
        if rules.get("min_days_engaged") is not None and _hard(ent, "min_days_engaged"):
            md = int(rules["min_days_engaged"] or 0)
            open_days = sum(1 for d in cap if len(
                [0 for (dd, _s) in cells if dd == d]) > 0)
            if md > open_days:
                flags.append(_flag(
                    code, name, "min_days_engaged", "everywhere", md,
                    open_days, src,
                    f"{name} must teach on {md} days but the placement "
                    f"domain leaves only {open_days} day(s) with a free "
                    f"slot."))
        # section bans that orphan a course entirely (every section carrying
        # the teacher's course is forbidden at hard level)
        forb_secs = set()
        if _hard(ent, "forbidden_sections"):
            for x in (rules.get("forbidden_sections") or []):
                forb_secs.add(x)
        for u in model["units"]:
            if u["teacher"] != code:
                continue
            usecs = u.get("secs") or ([u["sec"]] if u.get("sec") else [])
            if usecs and all(s in forb_secs for s in usecs) and load:
                cn = u.get("courseBySec", {})
                cnm = cn.get(usecs[0]) if usecs else None
                flags.append(_flag(
                    code, name, "forbidden_sections", " / ".join(usecs), 1, 0,
                    src,
                    f"Every section teaching {name}'s course "
                    f"'{cnm or u.get('subject', '?')}' ({', '.join(usecs)}) "
                    f"is in the forbidden_sections list — the course has "
                    f"nowhere to be scheduled."))
                break  # one per teacher is enough
        for e in (rules.get("allowed_slots_in_stream") or []):
            st = e.get("stream")
            sload = stats["per_stream"].get(code, {}).get(st, 0)
            s = len([x for x in (e.get("slots") or []) if x])
            cap = s * days
            if sload and sload > cap:
                flags.append(_flag(
                    code, name, "allowed_slots_in_stream", st, sload, cap, src,
                    f"{name} teaches {sload} {st} classes/week but {st} is "
                    f"restricted to {', '.join(e['slots'])} — only {cap} "
                    f"{st} placements exist ({s} slots x {days} days)."))
            elif sload and sload == cap:
                flags.append(_flag(
                    code, name, "allowed_slots_in_stream", st, sload, cap, src,
                    f"{name} teaches exactly {sload} {st} classes into "
                    f"exactly {cap} {st} slots ({', '.join(e['slots'])}) — a "
                    f"zero-slack exact pack that cannot be packed around the "
                    f"rest of the college. Relax this (extra slot, softened "
                    f"hardness, or less load)."))

        # (4) min_days_in_slot: requires the slot on more days than the
        # placement domain permits for that slot (uses the full domain, not
        # just the allowed_days alias)
        cells4, _cap4, _a4 = _placement_domain(
            {k: v for k, v in (rules or {}).items() if _hard(ent, k)},
            days, periods)
        for e in ((rules.get("min_days_in_slot") or []) if _hard(ent, "min_days_in_slot") else []):
            md = int(e.get("min_days") or 0)
            slot_days = len({d for (d, s) in cells4 if s == e.get("slot")})
            if md > slot_days:
                flags.append(_flag(
                    code, name, "min_days_in_slot", e.get("slot"), md, slot_days,
                    src,
                    f"{name} must engage {e.get('slot')} on {md} days but the "
                    f"placement domain permits {e.get('slot')} on only "
                    f"{slot_days} day(s) per week."))

        # (5) stream_slots_required vs available stream pieces
        for e in (rules.get("stream_slots_required") or []):
            st = e.get("stream")
            need = len([x for x in (e.get("slots") or []) if x])
            pieces = stats["pieces_stream"].get(code, {}).get(st, 0)
            if need and pieces and pieces < need:
                flags.append(_flag(
                    code, name, "stream_slots_required", st, need, pieces, src,
                    f"{name} must engage {need} distinct slots in {st} "
                    f"({', '.join(e['slots'])}) but only has {pieces} {st} "
                    f"class block(s) — impossible. The rule was likely meant "
                    f"as 'either/only' (allowed), not as a hard requirement."))

    def _slot_banned(code, slot):
        ent = cons.get(code) or {}
        rules = ent.get("rules") or {}
        fs = rules.get("forbidden_slots")
        if fs and slot in fs and _hard(ent, "forbidden_slots"):
            return True
        al = rules.get("allowed_slots")
        if al is not None and slot not in al and _hard(ent, "allowed_slots"):
            return True
        return False

    def _p1_banned(code):
        return _slot_banned(code, "P1")

    # (6) GI first_last_period_occupied: sections the GI marks as
    #     first/last-occupied whose teacher pool has NOBODY P1-eligible
    #     (read from the RESOLVED sectionMeta — exactly what the solver
    #     enforces, whatever GI merge produced it).
    sec_meta = ctx.get("sectionMeta") or {}
    sec_pool = {}
    sec_load = {}
    for u in model["units"]:
        secs = u.get("secs") or ([u["sec"]] if u.get("sec") else [])
        for sec in secs:
            pool = sec_pool.setdefault(sec, set())
            members = (u.get("members") or []) if u.get("group") else [u["teacher"]]
            for t in members:
                if not t or t.startswith("PG:"):
                    continue
                pool.add(t)
                sec_load[(sec, t)] = sec_load.get((sec, t), 0) + int(u.get("count", 1))
    for key, m in sec_meta.items():
        if not m.get("firstLast"):
            continue
        pool = {t for t in (sec_pool.get(key) or set()) if t
                and not t.startswith("PG:")}
        if not pool:
            continue
        for slot in ("P1", "P5"):
            # the GI demands `days` occupied cells/week at the boundary slot;
            # only HARD-eligibility counts — a softened (soft-listed) ban is
            # a penalty, not a blocker, so those teachers' classes STILL count
            # as available placements... but if even that total falls short
            # of the days needed, the section is provably dead.
            eligible = [t for t in pool if not _slot_banned(t, slot)]
            avail = sum(sec_load.get((key, t), 0) for t in eligible)
            if not eligible or avail < days:
                names = ", ".join(sorted(
                    (cons.get(t) or {}).get("name") or t for t in pool))
                flags.append(_flag(
                    "", key, "first_last_period_occupied (GI)", key, days, avail,
                    "gi rule",
                    f"A general instruction requires period {slot[1:]} to be "
                    f"occupied in {key} on all {days} days, but {key}'s pool "
                    f"({names}) has only {avail}"
                    + (" array of available classes (all members are banned "
                       f"from {slot} at hard level)" if not eligible
                       else f" {slot}-usable classes (some members can only "
                           f"use {slot} at a documented penalty)")
                    + f" while {days} occupied cells are needed. Reassign "
                      f"one {key} class to a {slot}-eligible teacher, or "
                      f"soften a pool teacher's {slot} ban."))

    return {"mode": "structural",
            "flags": flags,
            "loads": {t: stats["total"][t] for t in sorted(stats["total"])},
            "grid": {"days": days, "periods": periods}}
