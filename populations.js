/*
 * populations.js — timetable populations & schedule configuration (the domain model).
 *
 * The college runs three timetable populations:
 *   inter-1 : Intermediate, 1st shift          (shift 1)
 *   bs-1    : BS departments, 1st shift        (shift 1 — same time grid as inter-1)
 *   inter-2 : Intermediate, 2nd shift          (shift 2 — runs entirely after shift 1)
 *
 * Shift 1 populations share ONE time grid and are solved as one domain (faculty may
 * teach both Inter and BS in shift 1 — their schedule must not clash across levels).
 * Shift 2 is an operationally independent system: its own allocation, constraints,
 * optimization domain and timetable state.
 *
 * TIMETABLE CAPACITY vs ACTIVE CONFIGURATION
 *   capacity = 6 days (Mon–Sat) × 8 periods  — the reserved maximum the model supports
 *   active   = the admin-controlled effective schedule (defaults: Mon–Fri × 5 periods)
 * The active configuration is data: days/periods can be extended later (e.g. activate
 * Saturday or a 6th period) without any architectural change.
 *
 * BREAKS are NOT global: each population configures its own break (position after a
 * period + duration). 1st shift: break after the 3rd period; 2nd shift: after the 2nd.
 * The Friday start time for the 2nd shift (14:00) is a per-day override.
 *
 * Exposes IMPCC_POPULATIONS; also require()-able in Node.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.IMPCC_POPULATIONS = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // Reserved maximum capacity of the timetable model.
  const CAPACITY = { days: 6, periods: 8 };
  const DAY_NAMES = ["MON", "TUE", "WED", "THU", "FRI", "SAT"];
  // Period labels up to capacity; the active grid uses the first `periods` of them.
  const PERIOD_LABELS = ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8"];

  const PERIOD_DURATION_MIN = 40;   // every teaching period is 40 minutes
  const BREAK_DURATION_MIN = 25;    // every break is 25 minutes (may move/change per population)

  // Default schedule configuration per population. `days`/`periods` are ACTIVE counts
  // (≤ capacity); `breakAfterPeriod` is the period index (1-based ordinal) after which
  // the break sits; `dayStartOverrides` holds per-day start times (e.g. FRI 14:00 for
  // the 2nd shift).
  const POPULATIONS = {
    "inter-1": {
      label: "Intermediate — 1st Shift",
      short: "Inter-1",
      shift: 1,
      level: "intermediate",
      config: {
        days: 5, periods: 5,
        start: "08:30",
        dayStartOverrides: {},
        breakAfterPeriod: 3,
        periodMinutes: PERIOD_DURATION_MIN,
        breakMinutes: BREAK_DURATION_MIN
      }
    },
    "bs-1": {
      label: "BS Departments — 1st Shift",
      short: "BS-1",
      shift: 1,
      level: "bs",
      config: {
        days: 5, periods: 5,
        start: "08:30",
        dayStartOverrides: {},
        breakAfterPeriod: 3,
        periodMinutes: PERIOD_DURATION_MIN,
        breakMinutes: BREAK_DURATION_MIN
      }
    },
    "inter-2": {
      label: "Intermediate — 2nd Shift",
      short: "Inter-2",
      shift: 2,
      level: "intermediate",
      config: {
        days: 5, periods: 5,
        start: "13:30",
        dayStartOverrides: { FRI: "14:00" },   // Friday classes start at 2:00 PM
        breakAfterPeriod: 2,                    // break after the 2nd period in the 2nd shift
        periodMinutes: PERIOD_DURATION_MIN,
        breakMinutes: BREAK_DURATION_MIN
      }
    }
  };

  function parseHM(hm) {
    const p = String(hm || "08:30").split(":");
    return { h: parseInt(p[0], 10) || 0, m: parseInt(p[1], 10) || 0 };
  }
  function fmtHM(mins) {
    const h = Math.floor(mins / 60), m = mins % 60;
    return (h < 10 ? "0" : "") + h + ":" + (m < 10 ? "0" : "") + m;
  }

  // Validate an active config against capacity and internal consistency.
  // Returns a list of error strings (empty = valid).
  function validateConfig(cfg) {
    const errs = [];
    cfg = cfg || {};
    const days = cfg.days || 5, periods = cfg.periods || 5;
    if (days < 1 || days > CAPACITY.days) errs.push("days must be 1.." + CAPACITY.days);
    if (periods < 1 || periods > CAPACITY.periods) errs.push("periods must be 1.." + CAPACITY.periods);
    const bp = cfg.breakAfterPeriod || 0;
    if (bp < 1 || bp >= periods) errs.push("breakAfterPeriod must be 1.." + (periods - 1));
    const st = parseHM(cfg.start);
    if (st.h === 0 && st.m === 0) errs.push("start time required");
    for (const d in (cfg.dayStartOverrides || {})) {
      if (DAY_NAMES.indexOf(d) < 0) errs.push("unknown day override " + d);
    }
    return errs;
  }

  // Wall-clock schedule for one day: an array of period entries
  //   [{ period: "P1", start: "08:30", end: "09:10" }, ...]
  // plus a `break` entry placed after `breakAfterPeriod` periods.
  // `day` is a day name (MON..SAT) used to resolve per-day start overrides.
  function daySchedule(cfg, day) {
    const c = cfg || POPULATIONS["inter-1"].config;
    const start = (c.dayStartOverrides && c.dayStartOverrides[day]) || c.start || "08:30";
    const st = parseHM(start);
    const per = c.periodMinutes || PERIOD_DURATION_MIN;
    const brk = c.breakMinutes || BREAK_DURATION_MIN;
    const bp = c.breakAfterPeriod || 0;   // break sits after this many periods
    const out = [];
    let t = st.h * 60 + st.m;
    const periods = c.periods || 5;
    for (let i = 1; i <= periods; i++) {
      out.push({ period: PERIOD_LABELS[i - 1], start: fmtHM(t), end: fmtHM(t + per) });
      t += per;
      if (i === bp && i < periods) {
        out.push({ break: true, start: fmtHM(t), end: fmtHM(t + brk), after: PERIOD_LABELS[i - 1] });
        t += brk;
      }
    }
    return out;
  }

  // Convenience: the break window of a config (null when no break is configured).
  function breakWindow(cfg, day) {
    const sch = daySchedule(cfg, day);
    for (const e of sch) if (e.break) return e;
    return null;
  }

  // The active grid (day names + period labels) implied by a config.
  function activeGrid(cfg) {
    const c = cfg || POPULATIONS["inter-1"].config;
    return {
      days: DAY_NAMES.slice(0, c.days || 5),
      periods: PERIOD_LABELS.slice(0, c.periods || 5)
    };
  }

  // Populations grouped by shift (a shift's populations share one time grid / solver domain).
  function populationsOfShift(shift) {
    const out = [];
    for (const id in POPULATIONS) if (POPULATIONS[id].shift === shift) out.push(id);
    return out;
  }

  return {
    CAPACITY, DAY_NAMES, PERIOD_LABELS,
    PERIOD_DURATION_MIN, BREAK_DURATION_MIN,
    POPULATIONS,
    validateConfig, daySchedule, breakWindow, activeGrid, populationsOfShift
  };
});
