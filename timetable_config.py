"""Timetable populations & schedule configuration (the domain model) — Python side.

Mirrors populations.js exactly (same registry, same computation) so the frontend,
the offline pipeline and the FastAPI backend share one source of truth.

Populations:
  inter-1 : Intermediate, 1st shift   (shift 1)
  bs-1    : BS departments, 1st shift (shift 1 — same time grid as inter-1, one solver domain)
  inter-2 : Intermediate, 2nd shift   (shift 2 — independent system)

Capacity (reserved maximum): 6 days x 8 periods.
Active (admin-configurable, defaults): Mon-Fri x 5 periods.
Breaks are configured per population (1st shift: after P3; 2nd shift: after P2;
2nd shift Friday starts at 14:00).
"""
import datetime as _dt

CAPACITY = {"days": 6, "periods": 8}
DAY_NAMES = ["MON", "TUE", "WED", "THU", "FRI", "SAT"]
PERIOD_LABELS = ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8"]

PERIOD_DURATION_MIN = 40
BREAK_DURATION_MIN = 25

POPULATIONS = {
    "inter-1": {
        "label": "Intermediate — 1st Shift",
        "short": "Inter-1",
        "shift": 1,
        "level": "intermediate",
        "config": {
            "days": 5, "periods": 5,
            "start": "08:30",
            "day_start_overrides": {},
            "break_after_period": 3,
            "period_minutes": PERIOD_DURATION_MIN,
            "break_minutes": BREAK_DURATION_MIN,
        },
    },
    "bs-1": {
        "label": "BS Departments — 1st Shift",
        "short": "BS-1",
        "shift": 1,
        "level": "bs",
        "config": {
            "days": 5, "periods": 5,
            "start": "08:30",
            "day_start_overrides": {},
            "break_after_period": 3,
            "period_minutes": PERIOD_DURATION_MIN,
            "break_minutes": BREAK_DURATION_MIN,
        },
    },
    "inter-2": {
        "label": "Intermediate — 2nd Shift",
        "short": "Inter-2",
        "shift": 2,
        "level": "intermediate",
        "config": {
            "days": 5, "periods": 5,
            "start": "13:30",
            "day_start_overrides": {"FRI": "14:00"},   # Friday starts at 2:00 PM
            "break_after_period": 2,                    # break after the 2nd period
            "period_minutes": PERIOD_DURATION_MIN,
            "break_minutes": BREAK_DURATION_MIN,
        },
    },
}


def _parse_hm(hm):
    h, m = str(hm or "08:30").split(":")
    return int(h), int(m)


def _fmt_hm(mins):
    return "%02d:%02d" % (mins // 60, mins % 60)


def validate_config(cfg):
    """Validate an active config; returns a list of errors (empty = valid)."""
    cfg = cfg or {}
    errs = []
    days = cfg.get("days", 5)
    periods = cfg.get("periods", 5)
    if not (1 <= days <= CAPACITY["days"]):
        errs.append("days must be 1..%d" % CAPACITY["days"])
    if not (1 <= periods <= CAPACITY["periods"]):
        errs.append("periods must be 1..%d" % CAPACITY["periods"])
    bp = cfg.get("break_after_period", 0)
    if not (1 <= bp < periods):
        errs.append("break_after_period must be 1..%d" % (periods - 1))
    try:
        _parse_hm(cfg.get("start"))
    except Exception:
        errs.append("start time required")
    for d in (cfg.get("day_start_overrides") or {}):
        if d not in DAY_NAMES:
            errs.append("unknown day override %s" % d)
    return errs


def day_schedule(cfg, day=None):
    """Wall-clock schedule for one day: list of period/break entries.

    Entries: {"period": "P1", "start": "08:30", "end": "09:10"} and one
    {"break": True, "start": ..., "end": ..., "after": "P3"} when a break is configured.
    """
    cfg = cfg or POPULATIONS["inter-1"]["config"]
    overrides = cfg.get("day_start_overrides") or {}
    start = overrides.get(day) or cfg.get("start", "08:30")
    h, m = _parse_hm(start)
    per = cfg.get("period_minutes", PERIOD_DURATION_MIN)
    brk = cfg.get("break_minutes", BREAK_DURATION_MIN)
    bp = cfg.get("break_after_period", 0)
    periods = cfg.get("periods", 5)
    out = []
    t = h * 60 + m
    for i in range(1, periods + 1):
        out.append({"period": PERIOD_LABELS[i - 1], "start": _fmt_hm(t), "end": _fmt_hm(t + per)})
        t += per
        if i == bp and i < periods:
            out.append({"break": True, "start": _fmt_hm(t), "end": _fmt_hm(t + brk),
                        "after": PERIOD_LABELS[i - 1]})
            t += brk
    return out


def break_window(cfg, day=None):
    for e in day_schedule(cfg, day):
        if e.get("break"):
            return e
    return None


def active_grid(cfg):
    """The active grid (day names + period labels) implied by a config."""
    cfg = cfg or POPULATIONS["inter-1"]["config"]
    return {
        "days": DAY_NAMES[: cfg.get("days", 5)],
        "periods": PERIOD_LABELS[: cfg.get("periods", 5)],
    }


def populations_of_shift(shift):
    return [pid for pid, p in POPULATIONS.items() if p["shift"] == shift]
