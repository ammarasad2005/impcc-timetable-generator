"""
IMPCC Inter (1st Shift) timetable generator — v3.

Model + section-aware slot assignment + global backtracking fill +
validator + scorer. Randomized for variety.
"""
import random
import itertools
import copy
from collections import defaultdict

DAYS = ["MON", "TUE", "WED", "THU", "FRI"]
SLOTS = ["P1", "P2", "P3", "P4", "P5"]

# ---- timetable grid: capacity vs active configuration (see timetable_config.py) ----
# Capacity (reserved maximum) is 6 days x 8 periods. The ACTIVE grid is data:
# set_grid(days, periods) selects it; the default remains the historical 5x5.
DAY_NAMES = ["MON", "TUE", "WED", "THU", "FRI", "SAT"]
PERIOD_LABELS = ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8"]
D = 5   # active day count
P = 5   # active period count


def set_grid(days=5, periods=5):
    """Select the ACTIVE timetable grid (<= capacity 6x8)."""
    global D, P, DAYS, SLOTS
    D = max(1, min(6, int(days)))
    P = max(1, min(8, int(periods)))
    DAYS = DAY_NAMES[:D]
    SLOTS = PERIOD_LABELS[:P]
    return D, P

def S(key, subs):
    return {"key": key, "subs": subs}

SECTIONS = [
    S("I.COM-I-A", [
        ("English", "UmairAbid", 4), ("Urdu", "Basit", 4),
        ("Tarjama-tul-Quran", "V1", 2), ("Islamic Education", "V2", 2),
        ("Principles of Accounting", "Sikhani", 5),
        ("Principles of Economics", "Yasir", 3),
        ("Principles of Commerce", "Naeem", 3),
        ("Business Mathematics", "Assad", 2)]),
    S("I.COM-I-B", [
        ("English", "UmairAbid", 4), ("Urdu", "Basit", 4),
        ("Tarjama-tul-Quran", "V1", 2), ("Islamic Education", "V2", 2),
        ("Principles of Accounting", "Sikhani", 5),
        ("Principles of Economics", "Yasir", 3),
        ("Principles of Commerce", "Naeem", 3),
        ("Business Mathematics", "Assad", 2)]),
    S("I.COM-I-C", [
        ("English", "UmairAbid", 4), ("Urdu", "Basit", 4),
        ("Tarjama-tul-Quran", "V1", 2), ("Islamic Education", "V2", 2),
        ("Principles of Accounting", "Sikhani", 5),
        ("Principles of Economics", "Yasir", 3),
        ("Principles of Commerce", "Millat", 3),
        ("Business Mathematics", "Najam", 2)]),
    S("I.COM-II-A", [
        ("English", "Amir", 4), ("Urdu", "Ehsam", 4),
        ("Tarjama-tul-Quran", "V1", 2), ("Pakistan Studies", "Jilani", 2),
        ("Principles of Accounting", "Naeem", 5),
        ("Commercial Geography", "Husnul", 3),
        ("Computer Studies", "Faisal", 3),
        ("Statistics", "Tanveer", 2)]),
    S("I.COM-II-B", [
        ("English", "Amir", 4), ("Urdu", "Ehsam", 4),
        ("Tarjama-tul-Quran", "V1", 2), ("Pakistan Studies", "Jilani", 2),
        ("Principles of Accounting", "Naeem", 5),
        ("Commercial Geography", "Husnul", 3),
        ("Banking", "Millat", 3),
        ("Statistics", "Tanveer", 2)]),
    S("I.COM-II-C", [
        ("English", "Amir", 4), ("Urdu", "Ehsam", 4),
        ("Tarjama-tul-Quran", "V1", 2), ("Pakistan Studies", "Jilani", 2),
        ("Principles of Accounting", "Naeem", 5),
        ("Commercial Geography", "Husnul", 3),
        ("Banking", "Millat", 3),
        ("Statistics", "Tanveer", 2)]),
    S("ICS-I-A", [
        ("English", "Noor", 4), ("Urdu", "Rauf", 4),
        ("Tarjama-tul-Quran", "V2", 2), ("Islamic Education", "V1", 2),
        ("Computer Science", "Babar", 4), ("Mathematics", "Assad", 5),
        ("Physics", "V3", 4)]),
    S("ICS-I-B", [
        ("English", "Noor", 4), ("Urdu", "Rauf", 4),
        ("Tarjama-tul-Quran", "V2", 2), ("Islamic Education", "V1", 2),
        ("Computer Science", "Babar", 4), ("Mathematics", "Assad", 5),
        ("Physics", "V3", 4)]),
    S("ICS-I-C", [
        ("English", "Noor", 4), ("Urdu", "Rauf", 4),
        ("Tarjama-tul-Quran", "V2", 2), ("Islamic Education", "V1", 2),
        ("Computer Science", "Babar", 4), ("Mathematics", "Assad", 5),
        ("Statistics", "Ishfaq", 4)]),
    S("ICS-II-A", [
        ("English", "UmairAbid", 4), ("Urdu", "Rauf", 4),
        ("Tarjama-tul-Quran", "V2", 2), ("Pakistan Studies", "Jilani", 2),
        ("Computer Science", "Faisal", 4), ("Mathematics", "Najam", 5),
        ("Statistics", "Ishfaq", 4)]),
    S("ICS-II-B", [
        ("English", "UmairAbid", 4), ("Urdu", "Rauf", 4),
        ("Tarjama-tul-Quran", "V2", 2), ("Pakistan Studies", "Jilani", 2),
        ("Computer Science", "Faisal", 4), ("Mathematics", "Najam", 5),
        ("Economics/Statistics", "PARALLEL", 4)]),
]

TEACHER_FULL = {
    "Sikhani": "Prof. M. Waseem Sikhani",
    "Naeem": "Prof. Muhammad Naeem",
    "UmairAbid": "Prof. Syed Umair Abid",
    "Rauf": "Prof. Abdul Rauf",
    "Assad": "Prof. Syed Assad Abbas",
    "Basit": "Prof. Abdul Basit",
    "Najam": "Prof. Najam us Saqib",
    "Amir": "Prof. Amir Rasheed",
    "Ehsam": "Prof. Ehsam Ullah Baig",
    "Noor": "Prof. Noor Muhammad",
    "Babar": "Prof. Babar Jahangir",
    "Faisal": "Prof. Faisal Bashir",
    "Jilani": "Prof. Ghulam Jilani",
    "Yasir": "Prof. Dr. Yasir Kareem",
    "Millat": "Prof. Millat Khan",
    "Husnul": "Prof. Husnul Amin",
    "Ishfaq": "Prof. Ishfaq Ahmed",
    "NaeemAsghar": "Prof. Naeem Asghar",
    "Tanveer": "Prof. Tanveer Ahmed",
    "V1": "Visiting-1",
    "V2": "Visiting-2",
    "V3": "Visiting-3",
    "PARALLEL": "Prof. Naeem Asghar / Prof. Ishfaq Ahmed",
}

ALLOWED = {
    "Yasir": {0, 1, 3},
    "Amir": {1, 2, 3},
    "Husnul": {1, 2, 3},
    "Millat": {1, 2, 3, 4},
    "Basit": {0, 1, 2, 3},
    "Tanveer": {0, 1, 2},
    "NaeemAsghar": {2, 3, 4},
    "PARALLEL": {2, 3},
}

SLOT_OF = {"P1": 0, "P2": 1, "P3": 2, "P4": 3, "P5": 4}
DAY_OF = {"MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4}

# Faculty constraints as DATA (see constraints_schema.md). Keyed by teacher code.
DEFAULT_CONSTRAINTS = {
    "Yasir":  {"name": "Prof. Dr. Yasir Kareem", "rules": {"allowed_slots": ["P1", "P2", "P4"]}},
    "Amir":   {"name": "Prof. Amir Rasheed",     "rules": {"forbidden_slots": ["P1", "P5"]}},
    "Husnul": {"name": "Prof. Husnul Amin",      "rules": {"forbidden_slots": ["P1", "P5"]}},
    "Millat": {"name": "Prof. Millat Khan",      "rules": {"forbidden_slots": ["P1"]}},
    "Basit":  {"name": "Prof. Abdul Basit",      "rules": {"forbidden_slots": ["P5"],
                "min_days_in_slot": [{"slot": "P1", "min_days": 4}], "min_days_engaged": 5}},
    "NaeemAsghar": {"name": "Prof. Naeem Asghar", "rules": {"forbidden_slots": ["P1", "P2"]}},
    "Tanveer": {"name": "Prof. Tanveer Ahmed",   "rules": {"allowed_days": ["THU", "FRI"],
                "allowed_slots": ["P1", "P2", "P3"]}},
    "Ishfaq":  {"name": "Prof. Ishfaq Ahmed",    "rules": {"forbidden_slots": ["P5"],
                "min_days_in_slot": [{"slot": "P1", "min_days": 4}]}},
    "Naeem":   {"name": "Prof. Muhammad Naeem",  "rules": {
                "forbidden_slots_on_days": [{"days": ["MON"], "slots": ["P1", "P2"]}],
                "subject_slots": [{"subject": "Principles of Accounting", "slots": ["P3", "P4", "P5"]},
                                  {"subject": "Principles of Commerce", "slots": ["P1", "P2"]}],
                "subject_forbidden_days": [{"subject": "Principles of Commerce", "days": ["MON"]}]}},
    "Assad":   {"name": "Prof. Syed Assad Abbas", "rules": {
                "subject_slots": [{"subject": "Business Mathematics", "slots": ["P3"]},
                                  {"subject": "Mathematics", "slots": ["P1", "P2", "P4", "P5"]}],
                "subject_forbidden_days": [{"subject": "Business Mathematics", "days": ["FRI"]}],
                "stream_slots_required": [{"stream": "ICS", "slots": ["P1", "P2"]}]}},
    "Babar":   {"name": "Prof. Babar Jahangir",  "rules": {"stream_slots_required": [{"stream": "ICS", "slots": ["P1", "P2"]}]}},
}

NAME_TO_CODE = {}
for _code, _full in TEACHER_FULL.items():
    if _code != "PARALLEL":
        NAME_TO_CODE[_full] = _code


def extend_teachers(mapping):
    """Register additional faculty (e.g. the canonical directory's new members)
    so full display names resolve to their codes. Teaching roster as DATA."""
    for code, full in (mapping or {}).items():
        if code == "PARALLEL" or code in TEACHER_FULL:
            continue
        TEACHER_FULL[code] = full
        NAME_TO_CODE[full] = code
    return TEACHER_FULL

def resolve_constraints(C=None):
    """Merge per-teacher overrides onto the defaults.

    Each override carries `edits` (rule key -> value); a value of None REMOVES that rule,
    so defaults can be deleted, not just added to. Legacy `rules` is treated as edits.
    """
    import json as _json
    out = {}
    for code, entry in DEFAULT_CONSTRAINTS.items():
        out[code] = {"name": entry["name"], "rules": _json.loads(_json.dumps(entry["rules"]))}
    if C:
        for k, v in C.items():
            code = NAME_TO_CODE.get(k, k)
            entry = v or {}
            edits = entry.get("edits") or entry.get("rules") or {}
            base = _json.loads(_json.dumps((out.get(code) or {}).get("rules") or {}))
            for rk, rv in edits.items():
                if rv is None:
                    base.pop(rk, None)
                else:
                    base[rk] = rv
            out[code] = {"name": entry.get("name") or (out.get(code) or {}).get("name") or k,
                         "rules": base}
            # carry the `soft` list (rule keys enforced as documented soft
            # violations, not hard rejections) so the context engine can honour
            # it; the override's list wins, else inherit the base entry's.
            soft = entry.get("soft")
            if soft is None:
                soft = (out.get(code) or {}).get("soft") or []
            if soft:
                out[code]["soft"] = list(soft)
            # v2.1 hardness map: defaults' map, merged with the override's
            # (per-key, clamped 0..100; only keys that survive in `rules`).
            hard = dict((DEFAULT_CONSTRAINTS.get(code) or {}).get("hardness") or {})
            hard.update(entry.get("hardness") or {})
            hard = {k: max(0, min(100, int(v))) for k, v in hard.items()
                    if k in base and str(v).lstrip("-").isdigit()}
            if hard:
                out[code]["hardness"] = hard
    return out

def scope_of(e):
    """Optional per-entry scope (populations / streams / sections / days).
    Missing axes = unrestricted (today's entries keep current semantics)."""
    sc = (e or {}).get("scope") or {}
    return sc if isinstance(sc, dict) else {}


def scope_cell_applies(e, sec=None, day=None, pop=None, stream=None):
    """Does a scoped entry apply to one placement CANDIDATE cell?
    Example: a rule scoped streams=['ICS'] restricts only cells in ICS
    sections; days scoping restricts which days the window applies to."""
    sc = scope_of(e)
    pops = sc.get("populations")
    if pops and pop is not None and pop not in pops:
        return False
    streams = sc.get("streams")
    if streams and stream is not None and stream not in streams:
        return False
    secs = sc.get("sections")
    if secs and sec is not None and sec not in secs:
        return False
    days = sc.get("days")
    if days and day is not None and DAY_OF.get(day, day) not in _dayset(days):
        return False
    if (pops and pop is None) or (streams and stream is None):
        # cell signal incomplete (e.g. combined unit spans pops) — be permissive
        return True
    return True


def scope_unit_applies(e, unit, pop_of, stream_of):
    """Conservative check for WHOLE-UNIT domain shrinks: a scoped rule binds
    the unit only when every one of its sections satisfies the scoped axes."""
    sc = scope_of(e)
    if not sc.get("populations") and not sc.get("streams") and not sc.get("sections"):
        return True
    for sec in (unit.get("secs") or []):
        if sc.get("populations") and pop_of(sec) not in sc["populations"]:
            return False
        if sc.get("streams") and stream_of(sec) not in sc["streams"]:
            return False
        if sc.get("sections") and sec not in sc["sections"]:
            return False
    return True


def _windows_by_day(entries, def_days, def_slots):
    """Merge positive window entries (unscoped day sets inherited) into
    {day: allowed_slots} unions — for slots_days-style masks. Entries whose
    span omits `days` apply to every available day."""
    by_day = {}
    for e in (entries or []):
        days = _dayset((e or {}).get("days") or []) or set(def_days)
        slots = _slotset((e or {}).get("slots") or def_slots)
        for d in days:
            by_day.setdefault(d, set()).update(slots)
    return by_day


def _match_dyn_matchers(mu, u, sec=None):
    """Shared matcher for the min/max pieces-match quotas: all present
    matcher fields must hold (subject(s), stream, sections, slot, days are dynamic
    and thus evaluated per placement in the caller)."""
    if mu.get("subject") and (u.get("courseBySec") or {}).get(sec) != mu["subject"]:
        return False
    if mu.get("subjects") and (u.get("courseBySec") or {}).get(sec) not in (mu["subjects"] or []):
        return False
    if mu.get("sections") and sec is not None and sec not in (mu["sections"] or []):
        return False
    return True


def hardness_of(entry, kind):
    """0..100 rigidity of ONE rule kind for a teacher (personal_constraints_model
    §8). 100=hard mask; 1..99=soft with penalty scaled by h/100; 0=inactive.
    Legacy compatibility: a `soft` list maps listed kinds to 50; an explicit
    `hardness` map entry always wins; everything else defaults to 100.
    Soft-native kinds (soft_*) read their own hardness the same way — they're
    findings-soft by nature, with hardness scaling their penalty."""
    h = (entry or {}).get("hardness")
    if isinstance(h, dict) and kind in h:
        try:
            n = int(h[kind])
            return max(0, min(100, n))
        except (TypeError, ValueError):
            return 100
    if kind in set((entry or {}).get("soft") or []):
        return 50
    return 100


def _slotset(a):
    return {SLOT_OF[x] for x in (a or [])}

def _dayset(a):
    return {DAY_OF[x] for x in (a or [])}

DEFAULT_SECTIONS = copy.deepcopy(SECTIONS)

def build_units(secs):
    out = []
    for sec in secs:
        for subj, teacher, count in sec["subs"]:
            out.append({"sec": sec["key"], "subject": subj,
                        "teacher": teacher, "count": count})
    return out

UNITS = build_units(SECTIONS)

def normalize_sections(alloc=None):
    """External allocation form -> solver sections (teacher names -> codes)."""
    if not alloc:
        return copy.deepcopy(DEFAULT_SECTIONS)
    out = []
    for sec in DEFAULT_SECTIONS:
        a = alloc.get(sec["key"]) if isinstance(alloc, dict) else None
        if a and isinstance(a.get("subjects"), list):
            subs = []
            for e in a["subjects"]:
                t = e.get("teacher") or "Staff"
                code = "PARALLEL" if ("/" in str(t)) else NAME_TO_CODE.get(t, t)
                subs.append([e.get("subject"), code, max(1, min(5, int(e.get("periods") or 1)))])
        else:
            subs = copy.deepcopy(sec["subs"])
        out.append({"key": sec["key"], "subs": subs})
    return out

def set_active_sections(alloc=None):
    global SECTIONS, UNITS
    SECTIONS = normalize_sections(alloc)
    UNITS = build_units(SECTIONS)

SEC_MAP = {s["key"]: s for s in SECTIONS}

# ------------------------------------------------------------------
# SLOT ASSIGNMENT
# ------------------------------------------------------------------
def assign_slots(rng):
    slot = {}; days = {}; locked = {}
    used_teacher = defaultdict(set)   # count>=4 units
    used_section = defaultdict(set)   # count>=4 subjects
    by_teacher = defaultdict(list)
    for i, u in enumerate(UNITS):
        by_teacher[u["teacher"]].append(i)

    domains = {}
    order_big = []

    def add_dom(ui, dom):
        domains[ui] = list(dom)
        if UNITS[ui]["count"] >= 4:
            order_big.append(ui)

    # ---- fixed small/subject specials (not part of big backtracking) ----
    comm = [i for i in by_teacher["Naeem"] if UNITS[i]["subject"] == "Principles of Commerce"]
    rng.shuffle(comm)
    for j, ui in enumerate(comm):
        slot[ui] = [0, 1][j]; days[ui] = {1, 2, 3, 4}; locked[ui] = True

    bm = [i for i in by_teacher["Assad"] if UNITS[i]["subject"] == "Business Mathematics"]
    rng.shuffle(bm); bmds = [{0, 1}, {2, 3}]; rng.shuffle(bmds)
    for j, ui in enumerate(bm):
        slot[ui] = 2; days[ui] = bmds[j]; locked[ui] = True

    tv = list(by_teacher["Tanveer"]); rng.shuffle(tv)
    for j, ui in enumerate(tv):
        slot[ui] = j; days[ui] = {3, 4}; locked[ui] = True

    # ---- big-subject slot domains ----
    acct = [i for i in by_teacher["Naeem"] if UNITS[i]["subject"] == "Principles of Accounting"]
    for ui in acct:
        add_dom(ui, [2, 3, 4])

    for ui in by_teacher["PARALLEL"]:
        add_dom(ui, [2, 3])

    math = [i for i in by_teacher["Assad"] if UNITS[i]["subject"] == "Mathematics"]
    rng.shuffle(math)
    for j, ui in enumerate(math):
        add_dom(ui, [0, 1] if j < 2 else [3, 4])

    cs = list(by_teacher["Babar"]); rng.shuffle(cs)
    for j, ui in enumerate(cs):
        add_dom(ui, [0, 1] if j < 2 else [2, 3, 4])

    ish = list(by_teacher["Ishfaq"]); rng.shuffle(ish)
    add_dom(ish[0], [0]); add_dom(ish[1], [1])

    bs = list(by_teacher["Basit"]); rng.shuffle(bs)
    add_dom(bs[0], [0])
    for ui in bs[1:]:
        add_dom(ui, [0, 1, 2, 3])

    for t, unit_ids in by_teacher.items():
        if t in ("Naeem", "Assad", "Babar", "Ishfaq", "PARALLEL", "Tanveer", "Basit"):
            continue
        dom = ALLOWED.get(t, [0, 1, 2, 3, 4])
        for ui in unit_ids:
            if UNITS[ui]["count"] >= 4:
                add_dom(ui, dom)

    order_big.sort(key=lambda i: len(domains[i]))

    def bt(k):
        if k == len(order_big):
            return True
        ui = order_big[k]; u = UNITS[ui]
        cands = [s for s in domains[ui]
                 if s not in used_teacher[u["teacher"]] and s not in used_section[u["sec"]]]
        rng.shuffle(cands)
        for s in cands:
            slot[ui] = s
            used_teacher[u["teacher"]].add(s); used_section[u["sec"]].add(s)
            if bt(k + 1):
                return True
            used_teacher[u["teacher"]].remove(s); used_section[u["sec"]].remove(s)
        slot.pop(ui, None)
        return False

    if not bt(0):
        return None
    for ui in order_big:
        days[ui] = None; locked[ui] = True

    # ---- soft primary slots for remaining 3/2-credit units ----
    for i, u in enumerate(UNITS):
        if i in slot:
            continue
        allowed = list(ALLOWED.get(u["teacher"], [0, 1, 2, 3, 4]))
        busy = used_section[u["sec"]] | used_teacher.get(u["teacher"], set())
        pref = [s for s in allowed if s not in busy]
        pool = pref if pref else allowed
        slot[i] = rng.choice(pool)
        days[i] = None
        locked[i] = False

    parallel_slot = slot[by_teacher["PARALLEL"][0]]
    return slot, days, locked, parallel_slot

# ------------------------------------------------------------------
# GLOBAL FILL
# ------------------------------------------------------------------
def gen_candidates(ui, slot, days, locked, rng):
    u = UNITS[ui]; c = u["count"]; p = slot[ui]; t = u["teacher"]
    allow = set(ALLOWED.get(t, [0, 1, 2, 3, 4]))
    if locked[ui]:
        allow = {p}

    def d_ok(s, d):
        al = days.get(ui)
        if al is not None and d not in al:
            return False
        if t == "Naeem" and s in (0, 1) and d == 0:
            return False
        if t == "Tanveer" and d not in (3, 4):
            return False
        if t == "NaeemAsghar" and s in (0, 1):
            return False
        return True

    daylist = {s: [d for d in range(D) if d_ok(s, d)] for s in allow}
    cands = []
    if c == 5:
        if len(daylist[p]) == D:
            cands.append(tuple((p, d) for d in range(D)))
    elif c == 4:
        for combo in itertools.combinations(daylist[p], 4):
            cands.append(tuple((p, d) for d in combo))
    elif c == 3:
        order_s = [p] + [x for x in allow if x != p]
        for s in order_s:
            for combo in itertools.combinations(daylist[s], 3):
                cands.append(tuple((s, d) for d in combo))
        for s1 in allow:
            for s2 in allow:
                if s2 <= s1:
                    continue
                for d1c in itertools.combinations(daylist[s1], 2):
                    for d2 in daylist[s2]:
                        if d2 not in d1c:
                            cands.append(tuple([(s1, d) for d in d1c] + [(s2, d2)]))
    else:
        order_s = [p] + [x for x in allow if x != p]
        for s in order_s:
            for combo in itertools.combinations(daylist[s], 2):
                cands.append(tuple((s, d) for d in combo))
        for s1 in allow:
            for s2 in allow:
                if s2 <= s1:
                    continue
                for d1 in daylist[s1]:
                    for d2 in daylist[s2]:
                        if d2 != d1:
                            cands.append(((s1, d1), (s2, d2)))
    cands.sort(key=lambda cd: 0 if all(cs == p for cs, _ in cd) else 1)
    return cands

def can_place(ui, cells, grids, busy, sec_day_subj):
    sec = UNITS[ui]["sec"]; t = UNITS[ui]["teacher"]; subj = UNITS[ui]["subject"]
    extras = ("NaeemAsghar", "Ishfaq") if t == "PARALLEL" else ()
    days_used = set()
    for (s, d) in cells:
        if grids[sec][d][s] is not None:
            return False
        if (d, s) in busy[t]:
            return False
        for e in extras:
            if (d, s) in busy[e]:
                return False
        days_used.add(d)
    for d in days_used:
        if subj in sec_day_subj[sec][d]:
            return False
    return True

def place(ui, cells, grids, busy, sec_day_subj):
    sec = UNITS[ui]["sec"]; t = UNITS[ui]["teacher"]
    extras = ("NaeemAsghar", "Ishfaq") if t == "PARALLEL" else ()
    for (s, d) in cells:
        grids[sec][d][s] = ui
        busy[t].add((d, s))
        for e in extras:
            busy[e].add((d, s))
        sec_day_subj[sec][d].add(UNITS[ui]["subject"])

def unplace(ui, cells, grids, busy, sec_day_subj):
    sec = UNITS[ui]["sec"]; t = UNITS[ui]["teacher"]
    extras = ("NaeemAsghar", "Ishfaq") if t == "PARALLEL" else ()
    for (s, d) in cells:
        grids[sec][d][s] = None
        busy[t].discard((d, s))
        for e in extras:
            busy[e].discard((d, s))
        sec_day_subj[sec][d].discard(UNITS[ui]["subject"])

def solve_once(slot, days, locked, rng, node_budget=600000):
    grids = {s["key"]: [[None] * P for _ in range(D)] for s in SECTIONS}
    busy = defaultdict(set)
    sec_day_subj = defaultdict(lambda: [set() for _ in range(D)])

    order = list(range(len(UNITS)))
    rng.shuffle(order)
    order.sort(key=lambda i: -UNITS[i]["count"])
    cand_cache = [gen_candidates(i, slot, days, locked, rng) for i in range(len(UNITS))]
    nodes = [0]

    def backtrack(idx):
        nodes[0] += 1
        if nodes[0] > node_budget:
            return "BUDGET"
        if idx == len(order):
            return "OK"
        ui = order[idx]
        for cd in cand_cache[ui]:
            if can_place(ui, cd, grids, busy, sec_day_subj):
                place(ui, cd, grids, busy, sec_day_subj)
                r = backtrack(idx + 1)
                if r == "OK":
                    return "OK"
                unplace(ui, cd, grids, busy, sec_day_subj)
                if r == "BUDGET":
                    return "BUDGET"
        return None

    if backtrack(0) != "OK":
        return None
    return grids

# ------------------------------------------------------------------
# VALIDATION & SCORING
# ------------------------------------------------------------------
def validate(grids, R=None):
    if R is None:
        R = resolve_constraints()
    issues = []
    g0 = grids[SECTIONS[0]["key"]]
    Dg, Pg = len(g0), len(g0[0])   # infer grid dims from the data
    for sec in SECTIONS:
        g = grids[sec["key"]]
        counts = defaultdict(int)
        for d in range(Dg):
            seen = set()
            for s in range(Pg):
                uid = g[d][s]
                if uid is None:
                    issues.append(f"{sec['key']}: empty day{d} slot{s}")
                    continue
                u = UNITS[uid]
                counts[u["subject"]] += 1
                if u["subject"] in seen:
                    issues.append(f"{sec['key']} {DAYS[d]} {u['subject']} twice")
                seen.add(u["subject"])
        for subj, teacher, count in sec["subs"]:
            if counts[subj] != count:
                issues.append(f"{sec['key']} {subj} load {counts[subj]} != {count}")
        # ---- course period-coherence (spec §9, classic-grid mirror of context_model)
        for cname, total in counts.items():
            if total < 3:
                continue
            slots = [s for d in range(Dg) for s in range(Pg)
                     if g[d][s] is not None and UNITS[g[d][s]]["subject"] == cname]
            freq = {}
            for s in slots:
                freq[s] = freq.get(s, 0) + 1
            best = max(freq.values())
            dom = min(s for s, v in freq.items() if v == best)
            dev = total - best
            plab = SLOTS[dom]
            if total >= 4:
                if dev >= 2:
                    issues.append(f"{sec['key']} {cname}: {dev} of {total} classes outside one period "
                                  f"(dominant {plab}) — beyond the allowed 1 tolerance")
                elif dev == 1:
                    issues.append(f"(soft) {sec['key']} {cname}: 1 class outside dominant period "
                                  f"{plab} (allowed at most 1)")
            elif dev >= 1:
                issues.append(f"(soft) {sec['key']} {cname}: {dev} of 3 classes outside dominant period {plab}")

    occ = defaultdict(list)
    for sec in SECTIONS:
        g = grids[sec["key"]]
        for d in range(Dg):
            for s in range(Pg):
                uid = g[d][s]
                if uid is None:
                    continue
                occ[UNITS[uid]["teacher"]].append((d, s, sec["key"]))

    for t, lst in occ.items():
        seen = set()
        for (d, s, k) in lst:
            if (d * Pg + s) in seen:
                issues.append(f"teacher {t} double-booked {DAYS[d]} {SLOTS[s]}")
            seen.add(d * Pg + s)

    # rule-driven checks (availability + engagement + placement), per current R
    for t, lst in occ.items():
        rr = (R.get(t) or {}).get("rules")
        if not rr:
            continue
        aset = _slotset(rr.get("allowed_slots")) if rr.get("allowed_slots") is not None else None
        fset = _slotset(rr.get("forbidden_slots")) if rr.get("forbidden_slots") is not None else None
        aday = _dayset(rr.get("allowed_days")) if rr.get("allowed_days") is not None else None
        fday = _dayset(rr.get("forbidden_days")) if rr.get("forbidden_days") is not None else None
        for (d, s, k) in lst:
            if aset is not None and s not in aset:
                issues.append(f"{t} slot not allowed {SLOTS[s]} ({k})")
            if fset is not None and s in fset:
                issues.append(f"{t} forbidden slot {SLOTS[s]} ({k})")
            if aday is not None and d not in aday:
                issues.append(f"{t} day not allowed {DAYS[d]} ({k})")
            if fday is not None and d in fday:
                issues.append(f"{t} forbidden day {DAYS[d]} ({k})")
            for e in (rr.get("forbidden_slots_on_days") or []):
                if d in _dayset(e["days"]) and s in _slotset(e["slots"]):
                    issues.append(f"{t} forbidden {DAYS[d]} {SLOTS[s]} ({k})")
        for e in (rr.get("min_days_in_slot") or []):
            days = {d for (d, s, k) in lst if s == SLOT_OF[e["slot"]]}
            if len(days) < (e.get("min_days") or 1):
                issues.append(f"{t} {e['slot']} only {len(days)} days (<{e.get('min_days') or 1})")
        if rr.get("min_days_engaged"):
            days = {d for (d, s, k) in lst}
            if len(days) < rr["min_days_engaged"]:
                issues.append(f"{t} engaged only {len(days)} days (<{rr['min_days_engaged']})")
        for e in (rr.get("stream_slots_required") or []):
            for sl in e["slots"]:
                days = {d for (d, s, k) in lst if s == SLOT_OF[sl]}
                if len(days) < 4:
                    issues.append(f"{t} {e['stream']} {sl} only {len(days)} days")

    # subject placement rules
    for sec in SECTIONS:
        g = grids[sec["key"]]
        for d in range(Dg):
            for s in range(Pg):
                uid = g[d][s]
                if uid is None:
                    continue
                u = UNITS[uid]
                rr = (R.get(u["teacher"]) or {}).get("rules")
                if not rr:
                    continue
                for e in (rr.get("subject_slots") or []):
                    if e["subject"] == u["subject"] and s not in _slotset(e["slots"]):
                        issues.append(f"{u['teacher']} {u['subject']} not in {e['slots']} ({sec['key']})")
                for e in (rr.get("subject_forbidden_days") or []):
                    if e["subject"] == u["subject"] and d in _dayset(e["days"]):
                        issues.append(f"{u['teacher']} {u['subject']} on {DAYS[d]} ({sec['key']})")

    par = occ["PARALLEL"]
    if len(par) != 4:
        issues.append(f"parallel size {len(par)}")
    par_slots = {s for (d, s, k) in par}
    if len(par_slots) != 1 or list(par_slots)[0] not in (2, 3):
        issues.append(f"parallel slot {par_slots}")
    par_ds = {(d, s) for (d, s, k) in par}
    for (d, s, k) in occ["Ishfaq"]:
        if (d, s) in par_ds and k != "ICS-II-B":
            issues.append("Ishfaq clash parallel")
    for (d, s, k) in occ["NaeemAsghar"]:
        if (d, s) not in par_ds:
            issues.append("NaeemAsghar outside parallel")

    com1 = ["I.COM-I-A", "I.COM-I-B", "I.COM-I-C"]
    for x in com1:
        gx = grids[x]
        found = False
        for d in range(Dg):
            for s in range(Pg):
                uid = gx[d][s]
                if uid is None:
                    continue
                if UNITS[uid]["subject"] == "Principles of Accounting":
                    ok_all = True
                    for y in com1:
                        if y == x:
                            continue
                        uidy = grids[y][d][s]
                        if uidy is not None and UNITS[uidy]["subject"] == "Principles of Economics":
                            ok_all = False
                            break
                    if ok_all:
                        found = True
                        break
            if found:
                break
        if not found:
            issues.append(f"non-overriding failed {x}")

    hard = [i for i in issues if not str(i).startswith("(soft)")]
    return len(hard) == 0, issues

def score(grids):
    pen = 0
    for sec in SECTIONS:
        g = grids[sec["key"]]
        Dg, Pg = len(g), len(g[0])
        slots_by_subj = defaultdict(set)
        for d in range(Dg):
            for s in range(Pg):
                uid = g[d][s]
                if uid is not None:
                    slots_by_subj[UNITS[uid]["subject"]].add(s)
        for subj, teacher, count in sec["subs"]:
            extra = len(slots_by_subj[subj]) - 1
            if count == 5:
                pen += extra * 100000
            elif count == 4:
                pen += extra * 10000
            elif count == 3:
                pen += extra * 100
            else:
                pen += extra * 10
    return pen

def canonical(grids):
    parts = []
    for sec in SECTIONS:
        g = grids[sec["key"]]
        Dg, Pg = len(g), len(g[0])
        for d in range(Dg):
            for s in range(Pg):
                u = UNITS[g[d][s]]
                parts.append(f"{sec['key']}|{d}|{s}|{u['subject']}|{u['teacher']}")
    return "|".join(parts)

def generate(n_attempts, seed=1, budget=600000, days=5, periods=5):
    set_grid(days, periods)
    rng = random.Random(seed)
    solutions = {}
    attempts = valid = fill_fail = no_slot = 0
    while attempts < n_attempts and len(solutions) < 300:
        attempts += 1
        res = assign_slots(rng)
        if res is None:
            no_slot += 1
            continue
        slot, days, locked, par = res
        grids = solve_once(slot, days, locked, rng, budget)
        if grids is None:
            fill_fail += 1
            continue
        ok, issues = validate(grids)
        if ok:
            valid += 1
            key = canonical(grids)
            if key not in solutions:
                solutions[key] = (score(grids), grids)
    return solutions, attempts, valid, fill_fail, no_slot

if __name__ == "__main__":
    import sys
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    sols, attempts, valid, ff, ns = generate(n, seed=42)
    print(f"attempts={attempts} valid={valid} distinct={len(sols)} fill_fail={ff} no_slot={ns}")
    ranked = sorted(sols.values(), key=lambda x: x[0])
    for sc, g in ranked[:10]:
        print("score", sc)
