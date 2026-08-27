"""The canonical IMPCC data model (Python side): load, validate, adapt.

Mirrors canonical.js exactly. The canonical dataset lives in
data/canonical.json (see canonical_model.md): faculty directory with aliases,
subjects registry, per-population allocations, parallel groups, combined
classes, faculty constraints and structured general instructions.

Adapters convert a population's allocation into the formats the Python
solvers already consume:
    canonical.solver_allocation("inter-1")
        -> { "<SECTION>": { "subjects": [ {"subject", "teacher", "periods"}, ... ] } }
           (the external allocation form — full display names; either/or
            parallel pairs render as "A / B")
    canonical.solver_constraints()
        -> { "<code>": { "name", "rules" } }   (the constraints edits model)
"""
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_PATH = os.path.join(_HERE, "data", "canonical.json")

_DATA = None

POPULATIONS = ["inter-1", "bs-1", "inter-2"]
SHIFT1 = ["inter-1", "bs-1"]
SHIFT2 = ["inter-2"]


def load(path=None, data=None):
    """Load (and validate) the canonical dataset from a file or a dict."""
    global _DATA
    if data is None:
        with open(path or _DEFAULT_PATH, encoding="utf-8") as f:
            data = json.load(f)
    issues = validate(data)
    if issues:
        raise ValueError("canonical data invalid: " + "; ".join(issues))
    _DATA = data
    return _DATA


def get():
    if _DATA is None:
        return load()
    return _DATA


# ---------------------------------------------------------------- validation
def validate(data):
    issues = []
    if not isinstance(data, dict):
        return ["data must be an object"]
    faculty = data.get("faculty") or []
    codes = {f.get("code") for f in faculty}
    if any(not f.get("code") or not f.get("name") for f in faculty):
        issues.append("every faculty member needs code + name")
    if len(codes) != len(faculty):
        issues.append("duplicate faculty codes")
    subjects = set(data.get("subjects") or [])
    pops = data.get("populations") or {}
    for pid in POPULATIONS:
        if pid not in pops:
            issues.append("missing population %s" % pid)
            continue
        seen = set()
        for sec in (pops[pid].get("sections") or []):
            if sec["key"] in seen:
                issues.append("%s: duplicate section %s" % (pid, sec["key"]))
            seen.add(sec["key"])
            for e in (sec.get("entries") or []):
                if not e.get("course"):
                    issues.append("%s: entry without course" % sec["key"])
                if not (1 <= int(e.get("periods") or 0) <= 8):
                    issues.append("%s %s: periods must be 1..8" % (sec["key"], e.get("course")))
                if e.get("subject") and e["subject"] not in subjects:
                    issues.append("%s %s: unknown subject %s" % (sec["key"], e.get("course"), e["subject"]))
                if not e.get("parallelGroup") and e.get("teacher") not in codes:
                    issues.append("%s %s: unknown teacher %s" % (sec["key"], e.get("course"), e.get("teacher")))
    for pg in (data.get("parallelGroups") or []):
        for t in (pg.get("teachers") or []):
            if t not in codes:
                issues.append("parallelGroup %s: unknown teacher %s" % (pg.get("id"), t))
    # day-exclusive pairs: each course must exist in at least one section
    for dx in (data.get("dayExclusivePairs") or []):
        for course in (dx.get("courses") or []):
            found = False
            for pid in (data.get("populations") or {}):
                for sec in (data["populations"][pid].get("sections") or []):
                    if any(e.get("course") == course for e in sec.get("entries") or []):
                        found = True
                        break
                if found:
                    break
            if not found:
                issues.append("dayExclusivePair %s: course not found %s" % (dx.get("id"), course))
    for cc in (data.get("combinedClasses") or []):
        for side in ("a", "b"):
            ref = cc[side]
            secs = (pops.get("bs-1") or {}).get("sections") or []
            sec = next((s for s in secs if s["key"] == ref["section"]), None)
            if not sec or not any(e.get("course") == ref["course"] for e in sec.get("entries") or []):
                issues.append("combined %s: missing entry %s / %s" % (cc.get("id"), ref["section"], ref["course"]))
    for code in (data.get("constraints") or {}):
        if code not in codes:
            issues.append("constraints: unknown teacher code %s" % code)
    return issues


# ---------------------------------------------------------------- directory
def directory():
    return get()["faculty"]


def name_to_code():
    m = {}
    for f in directory():
        m[f["name"]] = f["code"]
        for a in (f.get("aliases") or []):
            m[a] = f["code"]
    return m


def code_of(name):
    return name_to_code().get(name)


def display_name(code):
    for f in directory():
        if f["code"] == code:
            return f["name"]
    return code


# ---------------------------------------------------------------- adapters
def solver_allocation(population_id):
    """A population's allocation -> the solver's EXTERNAL allocation form."""
    data = get()
    pop = (data["populations"].get(population_id) or {}).get("sections") or []
    out = {}
    for sec in pop:
        subjects = []
        for e in sec["entries"]:
            if e.get("parallelGroup"):
                pg = next(g for g in data["parallelGroups"] if g["id"] == e["parallelGroup"])
                teacher = " / ".join(display_name(t) for t in pg["teachers"])
            else:
                teacher = display_name(e["teacher"])
            subjects.append({"subject": e["course"], "teacher": teacher, "periods": e["periods"]})
        out[sec["key"]] = {"subjects": subjects}
    return out


def solver_constraints():
    """Faculty constraints -> the solver's edits-model form (person-level).
    Carries the `soft` list and the v2.1 `hardness` map (cleaned at ingest)."""
    return {code: clean_faculty_entry(c) for code, c in (get().get("constraints") or {}).items()}


def merge_constraint_overrides(base, overrides):
    """Apply the admin's LIVE constraint edits (shared global row payload) over
    the canonical-resolved `base` — mirror of solver.js resolveConstraints:
    each override entry carries `edits` (legacy `rules` treated as edits),
    null values REMOVE the rule, `hardness` merges per-key (present rules
    only, clamped 0..100), `soft` overrides when non-empty, `natural` kept.
    Without this, the server CP-SAT path would run on the repo-baked
    constraint snapshot regardless of the admin's edits (the stale-Yasir bug).
    """
    import copy
    out = {}
    for code, e in (base or {}).items():
        out[code] = {"name": e.get("name") or code,
                     "rules": copy.deepcopy(e.get("rules") or {}),
                     "soft": list(e.get("soft") or []),
                     "hardness": dict(e.get("hardness") or {})}
    n2c = name_to_code()
    for key, entry in (overrides or {}).items():
        if not isinstance(entry, dict):
            continue
        code = n2c.get(key, key)
        edits = entry.get("edits") if isinstance(entry.get("edits"), dict) else entry.get("rules") or {}
        ent = out.get(code) or {"name": entry.get("name") or key, "rules": {},
                                "soft": [], "hardness": {}}
        if entry.get("name"):
            ent["name"] = entry["name"]
        if entry.get("natural"):
            ent["natural"] = entry["natural"]
        for rk, v in edits.items():
            if v is None:
                ent["rules"].pop(rk, None)
                ent["hardness"].pop(rk, None)
            else:
                ent["rules"][rk] = v
        for hk, hv in (entry.get("hardness") or {}).items():
            if hk not in ent["rules"]:
                continue
            try:
                ent["hardness"][hk] = max(0, min(100, int(hv)))
            except (TypeError, ValueError):
                pass
        if isinstance(entry.get("soft"), list) and entry["soft"]:
            ent["soft"] = list(entry["soft"])
        out[code] = ent
    # shape-wall the merged set so malformed wire values never reach the engine
    return {code: clean_faculty_entry(e) for code, e in out.items()}


def clean_faculty_entry(c):
    """Shape wall for one teacher's constraint record: unknown rule keys are
    dropped, the v2.1 hardness map is reduced to present rule keys and clamped
    to ints 0..100. Keeps the legacy `soft` list verbatim (legacy compat:
    listed keys behave like hardness 50)."""
    from llm_translate import _validate_rules
    rules, _errs, warnings = _validate_rules(c.get("rules") or {})
    hard = {}
    for k, v in (c.get("hardness") or {}).items():
        if k not in rules:
            continue
        try:
            hard[k] = max(0, min(100, int(v)))
        except (TypeError, ValueError):
            continue
    returns_ = {"name": c["name"], "rules": rules,
                "soft": c.get("soft") or [], "hardness": hard}
    return returns_


# ---------------------------------------------------------------- helpers
def section_fill(population_id, section_key):
    """Teaching cells a section occupies (either/or groups count once)."""
    data = get()
    sec = next((s for s in (data["populations"].get(population_id) or {}).get("sections") or []
                if s["key"] == section_key), None)
    if not sec:
        return None
    fill = 0
    counted = set()
    for e in sec["entries"]:
        if e.get("parallelGroup"):
            if e["parallelGroup"] in counted:
                continue
            pg = next(g for g in data["parallelGroups"] if g["id"] == e["parallelGroup"])
            fill += pg["periods"]
            counted.add(e["parallelGroup"])
        else:
            fill += e["periods"]
    return fill


def teacher_load(teacher_code, population_ids=None):
    """Periods/week for one teacher across populations. Either/or groups count
    for EVERY member teacher (both are occupied simultaneously); combined
    classes (co-taught pairs at identical slots) count ONCE per group."""
    data = get()
    load = 0
    counted_combined = set()
    for pid in (population_ids or []):
        for sec in (data["populations"].get(pid) or {}).get("sections") or []:
            for e in sec["entries"]:
                if e.get("parallelGroup"):
                    pg = next(g for g in data["parallelGroups"] if g["id"] == e["parallelGroup"])
                    if teacher_code in pg["teachers"]:
                        load += pg["periods"]
                elif e["teacher"] == teacher_code:
                    if e.get("combinedWith"):
                        if e["combinedWith"] in counted_combined:
                            continue   # co-taught: occupied once
                        counted_combined.add(e["combinedWith"])
                    load += e["periods"]
    return load


# ---------------------------------------------------------------- solve context
def _gi_rules(populations):
    """Collect enabled general instructions from the given populations,
    keyed by rule type."""
    data = get()
    out = {}
    for pid in populations:
        for gi in ((data["populations"].get(pid) or {}).get("generalInstructions")
                   or data.get("generalInstructions", {}).get(pid) or []):
            if not gi.get("enabled", True):
                continue
            out.setdefault(gi["type"], []).append(gi)
    return out


def _population_level(pid):
    lvl = (get()["populations"].get(pid) or {}).get("level")
    if lvl:
        return lvl
    return "bs" if pid == "bs-1" else "inter"


BUILTIN_GI_TYPES = {
    "no_same_subject_same_day", "same_subject_same_day_allowed", "avoid_shuffling",
    "non_overriding", "consecutive_days_for_2pw", "subject_forbidden_days",
    "section_off_days", "first_last_period_occupied", "combined_classes",
    "soft_individual_spread", "subject_forbidden_slots_on_days",
}


def _rule_registry(overrides=None):
    """Dynamic-rule definitions: admin's live registry (sent per request) on
    top of the bundled seed. Everything is validated kernel-only upstream."""
    reg = {}
    seed = get().get("ruleRegistry") or []
    for d in seed:
        if isinstance(d, dict) and d.get("id"):
            reg[d["id"]] = dict(d)
    ov = (overrides or {}).get("rule_registry") or {}
    if isinstance(ov, dict):
        for k, d in ov.items():
            if isinstance(d, dict) and (d.get("id") == k or not d.get("id")) and d.get("enabled", True):
                dd = dict(d)
                dd["id"] = k
                reg[k] = dd
    return reg


def _lower_dyn_entry(e, defn, n2c):
    """Compile one dynamic-rule entry into the generalized window-ban
    instruction (the forbid_cells kernel). Params map 1:1 onto matcher
    fields; teacher names resolve to codes; no generated code executes."""
    p = e.get("params") or {}
    out = {"dsl": (defn.get("label") or e.get("type", "custom"))}
    if p.get("subject"):
        out["subject"] = str(p["subject"])
    if isinstance(p.get("subjects"), list) and p["subjects"]:
        out["subjects"] = [str(x) for x in p["subjects"]]
    if isinstance(p.get("sections"), list) and p["sections"]:
        out["sections"] = [str(x) for x in p["sections"]]
    if isinstance(p.get("teachers"), list) and p["teachers"]:
        out["teachers"] = [n2c.get(str(t), str(t)) for t in p["teachers"]]
    if p.get("stream"):
        out["scope"] = str(p["stream"])
    if isinstance(p.get("days"), list) and p["days"]:
        out["days"] = [str(x).upper() for x in p["days"]]
    if isinstance(p.get("slots"), list) and p["slots"]:
        out["slots"] = [str(x).upper() for x in p["slots"]]
    return out


def solver_context(population_ids, overrides=None):
    """Build a solve context for one SHIFT's populations (shift 1: ["inter-1",
    "bs-1"] solved jointly; shift 2: ["inter-2"]). Schedule configs come from
    timetable_config.POPULATIONS; behavioural rules are derived from the
    structured general instructions; relationships + constraints come from the
    canonical dataset.

    Returns the context dict consumed by context_model.context_to_model().
    """
    import timetable_config as TC
    data = get()
    pids = list(population_ids or [])
    shifts = {TC.POPULATIONS[p]["shift"] for p in pids if p in TC.POPULATIONS}
    if len(shifts) != 1:
        raise ValueError("a solve context spans exactly ONE shift "
                         "(shift 1 = inter-1 + bs-1; shift 2 = inter-2)")

    ov = dict(overrides or {})

    # grid: both shift-1 populations share one time grid; the admin may submit
    # an edited schedule (days/periods) for generation
    cfg = TC.POPULATIONS[pids[0]]["config"]
    grid = {"days": cfg["days"], "periods": cfg["periods"]}
    if isinstance(ov.get("grid"), dict):
        try:
            grid["days"] = int(ov["grid"].get("days", grid["days"]))
            grid["periods"] = int(ov["grid"].get("periods", grid["periods"]))
        except (TypeError, ValueError):
            pass

    _dyn_reg = _rule_registry(ov)
    gi = _gi_rules(pids)

    # the admin's CURRENT per-population general-instruction lists override the
    # bundled canonical rules, per TYPE (an admin type replaces every canonical
    # entry of that type across the whole context — mirrors buildShiftContext)
    if isinstance(ov.get("general_instructions"), dict):
        # a passed population's admin list is AUTHORITATIVE for that population
        # (full replacement of its canonical rules); populations not passed keep
        # the bundled canonical set. (Mirrors what the frontend sends back         # from giByPop.)
        per_pop_gi = {pid: _gi_rules([pid]) for pid in pids}
        admin_map = {}
        for pid in pids:
            raw_list = ov["general_instructions"].get(pid)
            if isinstance(raw_list, list):
                admin_map[pid] = [dict(e) for e in raw_list
                                  if isinstance(e, dict) and e.get("type") and e.get("enabled", True)]
        if admin_map:
            merged = {}
            for pid in pids:
                if pid in admin_map:
                    for e in admin_map[pid]:
                        merged.setdefault(e["type"], []).append(e)
                else:
                    for t, entries in per_pop_gi[pid].items():
                        merged.setdefault(t, []).extend(entries)
            gi = merged

    sections = {}
    section_meta = {}
    pop_keys = {}
    for pid in pids:
        alloc = solver_allocation(pid)
        pop_keys[pid] = set(alloc.keys())
        sections.update(alloc)
        level = _population_level(pid)
        for key in alloc:
            section_meta[key] = {"level": level, "pop": pid, "offDays": [], "firstLast": False}

    # the admin's CURRENT per-population allocation (incl. sections created or
    # deleted in the UI) replaces the bundled canonical allocation per passed pop
    if isinstance(ov.get("allocation"), dict):
        for pid, a in ov["allocation"].items():
            if pid not in pids or not isinstance(a, dict):
                continue
            level = _population_level(pid)
            for key in pop_keys.get(pid, set()):
                sections.pop(key, None)
                section_meta.pop(key, None)
            for key, rows in a.items():
                sections[key] = rows
                section_meta[key] = {"level": level, "pop": pid, "offDays": [], "firstLast": False}

    # instructions -> section meta + behavioural flags
    no_same = {"inter": bool(gi.get("no_same_subject_same_day")),
               "bs": not bool(gi.get("same_subject_same_day_allowed"))}
    consec = {"inter": bool(gi.get("consecutive_days_for_2pw")),
              "bs": bool(gi.get("consecutive_days_for_2pw")) and False}
    for e in gi.get("section_off_days", []):
        for key in (e["params"] or {}).get("sections", []):
            if key in section_meta:
                section_meta[key]["offDays"] = (section_meta[key]["offDays"] or []) + \
                    list((e["params"] or {}).get("days", []))
    if gi.get("first_last_period_occupied"):
        for key, m in section_meta.items():
            if m["level"] == "bs":
                m["firstLast"] = True

    instructions = {
        "noSameSubjectSameDay": no_same,
        "consecutiveFor2pw": consec,
        "nonOverriding": [
            {"sections": e["params"]["sections"], "subjects": e["params"]["subjects"]}
            for e in gi.get("non_overriding", []) if e.get("params")
        ],
        "subjectForbiddenDays": [
            {"subject": e["params"].get("subject"), "days": e["params"].get("days", []),
             "scope": e["params"].get("scope")}
            for e in gi.get("subject_forbidden_days", []) if e.get("params")
        ],
        "subjectForbiddenSlotDays": [
            {"subject": e["params"].get("subject"), "days": e["params"].get("days", []),
             "slots": e["params"].get("slots", []), "scope": e["params"].get("scope")}
            for e in gi.get("subject_forbidden_slots_on_days", []) if e.get("params")
        ] + [
            _lower_dyn_entry(e, _dyn_reg.get(e["type"]) or {}, name_to_code())
            for _t, _entries in gi.items() if _t not in BUILTIN_GI_TYPES
            for e in (_entries or [])
            if e.get("type") in _dyn_reg and e.get("enabled", True) is not False
        ],
        "softIndividualSpread": bool(gi.get("soft_individual_spread")),
    }

    relationships = {
        "parallelGroups": data.get("parallelGroups") or [],
        "dayExclusivePairs": data.get("dayExclusivePairs") or [],
        "combinedClasses": data.get("combinedClasses") or [],
    }

    return {
        "grid": grid,
        "sections": sections,
        "sectionMeta": section_meta,
        "relationships": relationships,
        "instructions": instructions,
        "constraints": merge_constraint_overrides(
            solver_constraints(), ov.get("constraints")),
        "teacherCodes": name_to_code(),
        "softPenalties": dict(ov).get("softPenalties", {}),
    }


# ---------------------------------------------------------------- manual entry
def timetable_from_grids(grids, model):
    """Context grids (unit ids per cell) -> {section: dayRows[[subject, teacher]]}.

    Display form of a solution: course names per section; parallel groups render
    their members joined with ' / '; empty cells become ["Library Work", ""].
    (Same rendering as the API's /generate-context response.)"""
    units = {u["id"]: u for u in model["units"]}
    D, P = model["days"], model["periods"]
    out = {}
    for section in model["sections"]:
        key = section["key"]
        g = grids.get(key) or []
        rows = []
        for d in range(D):
            row = []
            for s in range(P):
                uid = g[d][s] if d < len(g) and s < len(g[d]) else None
                if uid is None:
                    row.append(["Library Work", ""])
                    continue
                u = units[uid]
                cname = u["courseBySec"].get(key) or list(u["courseBySec"].values())[0]
                if u["group"]:
                    tname = " / ".join(display_name(t) for t in u["members"])
                else:
                    tname = display_name(u["teacher"])
                row.append([cname, tname])
            rows.append(row)
        out[key] = rows
    return out
