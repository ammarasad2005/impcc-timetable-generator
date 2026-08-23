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
    """Faculty constraints -> the solver's edits-model form (person-level)."""
    return {code: {"name": c["name"], "rules": c["rules"]}
            for code, c in (get().get("constraints") or {}).items()}


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
