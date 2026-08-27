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
        if rules.get("allowed_days") is not None and load:
            d = len([x for x in (rules.get("allowed_days") or []) if x])
            cap = d * periods
            if load > cap:
                flags.append(_flag(
                    code, name, "allowed_days", "everywhere", load, cap, src,
                    f"{name} teaches {load} classes/week but the day window "
                    f"({', '.join(rules['allowed_days'])}) only provides "
                    f"{cap} slot-days ({d} days x {periods} slots)."))

        # (2) allowed_slots window vs weekly load
        if rules.get("allowed_slots") is not None and load:
            s = len([x for x in (rules.get("allowed_slots") or []) if x])
            cap = s * days
            if load > cap:
                flags.append(_flag(
                    code, name, "allowed_slots", "everywhere", load, cap, src,
                    f"{name} teaches {load} classes/week but the slot window "
                    f"({', '.join(rules['allowed_slots'])}) only provides "
                    f"{cap} placements ({s} slots x {days} days)."))

        # (3) allowed_slots_in_stream vs stream load (+ exact-pack)
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

        # (4) min_days_in_slot asks for days outside the day window
        daywin = None
        if rules.get("allowed_days"):
            daywin = len(rules["allowed_days"])
        for e in (rules.get("min_days_in_slot") or []):
            md = int(e.get("min_days") or 0)
            if daywin is not None and md > daywin:
                flags.append(_flag(
                    code, name, "min_days_in_slot", e.get("slot"), md, daywin,
                    src,
                    f"{name} must engage {e.get('slot')} on {md} days but the "
                    f"day window only has {daywin} days."))

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

    def _p1_banned(code):
        ent = cons.get(code) or {}
        rules = ent.get("rules") or {}
        fs = rules.get("forbidden_slots")
        if fs and "P1" in fs and _hard(ent, "forbidden_slots"):
            return True
        al = rules.get("allowed_slots")
        if al is not None and "P1" not in al and _hard(ent, "allowed_slots"):
            return True
        return False

    # (6) GI first_last_period_occupied: sections the GI marks as
    #     first/last-occupied whose teacher pool has NOBODY P1-eligible
    #     (read from the RESOLVED sectionMeta — exactly what the solver
    #     enforces, whatever GI merge produced it).
    sec_meta = ctx.get("sectionMeta") or {}
    sec_pool = {}
    for u in model["units"]:
        secs = u.get("secs") or ([u["sec"]] if u.get("sec") else [])
        for sec in secs:
            pool = sec_pool.setdefault(sec, set())
            if u.get("group"):
                for m_ in (u.get("members") or []):
                    pool.add(m_)
            elif u["teacher"]:
                pool.add(u["teacher"])
    for key, m in sec_meta.items():
        if not m.get("firstLast"):
            continue
        pool = {t for t in (sec_pool.get(key) or set()) if t
                and not t.startswith("PG:")}
        if pool and all(_p1_banned(t) for t in pool):
            names = ", ".join(sorted(
                (cons.get(t) or {}).get("name") or t for t in pool))
            flags.append(_flag(
                "", key, "first_last_period_occupied (GI)", key, 1, 0,
                "gi rule",
                f"A general instruction requires period 1 to be occupied in "
                f"{key} every day, but every teacher in {key}'s pool "
                f"({names}) is banned from period 1 at hard level — no one "
                f"is left to occupy it. Reassign one {key} class to a "
                f"P1-eligible teacher, or soften one pool teacher's P1 ban."))

    return {"flags": flags,
            "loads": {t: stats["total"][t] for t in sorted(stats["total"])},
            "grid": {"days": days, "periods": periods}}
