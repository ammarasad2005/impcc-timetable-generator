/*
 * context_solver.js — in-browser multi-population timetable solver (context path).
 *
 * The JS mirror of the Python context stack (context_model.py + cp_solver's
 * context path), so the site can generate shift timetables fully client-side:
 *
 *   IMPCC_CANONICAL.solverContext(["inter-1","bs-1"])   // or ["inter-2"]
 *     -> IMPCC_CONTEXT_SOLVER.generateContext(ctx, {timeMs, seed, maxCount})
 *     -> { solutions: [{grids, score, penalty, violations, total}], stats, model }
 *
 * Model semantics (identical to the Python side, see canonical_model.md §9):
 *   - combined classes become dual-section units (one teacher, one room, both
 *     sections, identical cells); parallel groups occupy one slot with all
 *     member teachers busy; day-exclusive pairs never share a day (per section)
 *   - hard rules reject (evaluate.issues); soft rules produce DOCUMENTED
 *     violations with penalties counted into total = shuffle + penalty
 *   - 5/wk + 4/wk courses may split across slots when structurally forced
 *     (candidate tiers try single-slot forms first; the shuffle tiers in the
 *     score keep splits rare); BS day-doubles permitted; inter 2/wk on
 *     consecutive days
 *   - poolSelection() implements the pool rule (>=25 -> top 25; 10-24 -> all
 *     valid; <10 -> pad to 10 with the best documented violators)
 *
 * The in-browser search is a two-stage randomized engine: stage 1 packs
 * columns per section on the fly (global teacher capacities, per-unit slot
 * budgets for tight teachers, engagement-group pruning), stage 2 colors days
 * per slot. STATUS: best-effort. The full shift-1 dataset (7 teachers at
 * 80-88% slot utilization) sits at the edge of heuristic feasibility — the
 * reliable generation path for it is the CP-SAT backend (POST /generate-context,
 * see cp_solver.generate_context). The JS engine handles lighter contexts
 * (single populations, typical utilizations) and keeps improving.
 *
 * Exposes IMPCC_CONTEXT_SOLVER; require()-able in Node.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.IMPCC_CONTEXT_SOLVER = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const SLOT_OF = { P1: 0, P2: 1, P3: 2, P4: 3, P5: 4, P6: 5, P7: 6, P8: 7 };
  const DAY_OF = { MON: 0, TUE: 1, WED: 2, THU: 3, FRI: 4, SAT: 5 };
  const DAY_NAMES = ["MON", "TUE", "WED", "THU", "FRI", "SAT"];
  const PERIOD_LABELS = ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8"];

  const PENALTIES = {
    rule: 5000,            // a soft faculty/GI rule is disobeyed (flat per rule)
    preferFreeSlot: 500,   // each period in a soft-preferred-free slot
    evenDistribution: 100, // each period above the even per-day share
    individualSpread: 200, // teacher in P1 and last period the same week
    nonConsecutive: 100,   // a day-exclusive pair course not on consecutive days
    periodConsistency45: 4500,  // = rule x 90% : count-4/5 class outside the dominant slot (§9)
    periodConsistency3: 3250    // = rule x 65% : count-3 deviation (§9, soft only)
  };

  // ------------------------------------------------------------- helpers
  function mulberry32(seed) {
    let a = seed >>> 0;
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function makeRng(seed) {
    const r = mulberry32(seed);
    return {
      next: r,
      int(n) { return Math.floor(r() * n); },
      shuffle(arr) {
        for (let i = arr.length - 1; i > 0; i--) {
          const j = Math.floor(r() * (i + 1));
          const tmp = arr[i]; arr[i] = arr[j]; arr[j] = tmp;
        }
        return arr;
      }
    };
  }
  function combinations(arr, k) {
    const out = [], idx = [];
    if (k > arr.length) return out;
    function rec(start) {
      if (idx.length === k) { out.push(idx.slice()); return; }
      for (let i = start; i < arr.length; i++) { idx.push(arr[i]); rec(i + 1); idx.pop(); }
    }
    rec(0);
    return out;
  }
  function consecutivePairs(days) {
    const d = days.slice().sort((a, b) => a - b);
    const out = [];
    for (let i = 0; i + 1 < d.length; i++) {
      if (d[i + 1] - d[i] === 1) out.push([d[i], d[i + 1]]);
    }
    return out;
  }
  const slotSet = a => new Set((a || []).map(x => SLOT_OF[x]));
  const daySet = a => new Set((a || []).map(x => DAY_OF[x]));
  function secStream(sec) {
    if (sec.indexOf("I.COM") === 0) return "I.COM";
    if (sec.indexOf("ICS") === 0) return "ICS";
    return null;
  }

  // ------------------------------------------------------------- transform
  function contextToModel(ctx) {
    const grid = ctx.grid || {};
    const D = grid.days || 5, P = grid.periods || 5;
    const n2c = Object.assign({}, ctx.teacherCodes || {});
    const rel = ctx.relationships || {};
    const instr = ctx.instructions || {};
    const meta = ctx.sectionMeta || {};

    const parallelEntry = {};
    for (const g of (rel.parallelGroups || [])) {
      for (const s of (g.sections || [])) parallelEntry[s + "|" + g.course] = g;
    }
    const combinedEntry = {};
    for (const cc of (rel.combinedClasses || [])) {
      combinedEntry[cc.a.section + "|" + cc.a.course] = cc;
      combinedEntry[cc.b.section + "|" + cc.b.course] = cc;
    }

    // resolve a display name OR an already-canonical code
    const resolve = x => (x != null && n2c[x] !== undefined ? n2c[x] : x) || "";

    const sections = [];
    const units = [];
    const consumed = {};

    function unitLevel(secs) {
      const lvls = secs.map(s => (meta[s] || {}).level || "inter");
      return (lvls.length && lvls.every(l => l === "bs")) ? "bs" : "inter";
    }

    for (const secKey of Object.keys(ctx.sections || {})) {
      const m = meta[secKey] || {};
      const level = m.level || "inter";
      const offDays = (m.offDays || []).map(d => DAY_OF[d]);
      const firstLast = !!m.firstLast;
      const effDays = [];
      for (let d = 0; d < D; d++) if (offDays.indexOf(d) < 0) effDays.push(d);
      const subs = [];
      for (const e of ((ctx.sections[secKey] || {}).subjects || [])) {
        const course = e.subject;
        const periods = e.periods | 0;
        subs.push([course, e.teacher || "", periods]);

        const key = secKey + "|" + course;
        if (consumed[key]) continue;
        if (combinedEntry[key]) {
          const cc = combinedEntry[key];
          const other = cc.a.section === secKey ? cc.b : cc.a;
          consumed[key] = true;
          consumed[other.section + "|" + other.course] = true;
          units.push({
            id: units.length, secs: [cc.a.section, cc.b.section],
            courseBySec: {}, courseBySecA: cc.a.section, courseA: cc.a.course,
            courseBySecB: cc.b.section, courseB: cc.b.course,
            teacher: resolve(cc.teacher || e.teacher || ""),
            group: null, members: [], count: periods,
            level: unitLevel([cc.a.section, cc.b.section])
          });
          const du = units[units.length - 1];
          du.courseBySec[cc.a.section] = cc.a.course;
          du.courseBySec[cc.b.section] = cc.b.course;
          continue;
        }
        if (parallelEntry[key]) {
          const g = parallelEntry[key];
          units.push({
            id: units.length, secs: [secKey],
            courseBySec: {}, teacher: "PG:" + g.id, group: g.id,
            members: (g.teachers || []).map(t => resolve(t)),
            count: periods, level: level
          });
          units[units.length - 1].courseBySec[secKey] = course;
          continue;
        }
        units.push({
          id: units.length, secs: [secKey],
          courseBySec: {}, teacher: resolve(e.teacher || ""),
          group: null, members: [], count: periods, level: level
        });
        units[units.length - 1].courseBySec[secKey] = course;
      }
      sections.push({ key: secKey, level: level, offDays: offDays, firstLast: firstLast,
                      effDays: effDays, subs: subs, pop: ((meta[secKey] || {}).pop || null) });
    }

    // day-exclusive pairs — PER SECTION
    const dx = [];
    for (const p of (rel.dayExclusivePairs || [])) {
      for (const section of sections) {
        const secUnits = [];
        for (const course of (p.courses || [])) {
          for (const u of units) {
            if (u.courseBySec[section.key] === course) secUnits.push(u.id);
          }
        }
        if (secUnits.length >= 2) {
          dx.push({ id: p.id + "@" + section.key, units: secUnits,
                    softConsecutiveDays: !!p.softConsecutiveDays });
        }
      }
    }

    const combined = [];
    for (const u of units) if (u.secs.length > 1) combined.push({ id: "cc" + u.id, unit: u.id });

    const metaBySec = {};
    for (const s of sections) metaBySec[s.key] = s;
    return {
      days: D, periods: P, sections: sections, units: units,
      dayExclusive: dx, combined: combined,
      instructions: instr,
      constraints: ctx.constraints || {},
      penalties: Object.assign({}, PENALTIES, ctx.softPenalties || {}),
      _parallelGroups: rel.parallelGroups || [],
      _metaBySec: metaBySec,
      _cohExempt: new Set((ctx._cohExempt || []).map(x => x[0] + "|" + x[1]))
    };
  }

  // ------------------------------------------------------------- domains
  function teacherSlotDomain(teacher, R, P) {
    const entry = (R || {})[teacher] || {};
    const r = entry.rules || {};
    let dom = null, restricted = false;
    if (r.allowed_slots != null && hardnessOfJS(entry, "allowed_slots") === 100) {
      dom = new Set();
      for (const x of r.allowed_slots) { const s = SLOT_OF[x]; if (s < P) dom.add(s); }
      restricted = true;
    }
    if (r.forbidden_slots != null && hardnessOfJS(entry, "forbidden_slots") === 100) {
      if (!dom) { dom = new Set(); for (let s = 0; s < P; s++) dom.add(s); }
      for (const x of r.forbidden_slots) dom.delete(SLOT_OF[x]);
      restricted = true;
    }
    return restricted ? Array.from(dom).sort((a, b) => a - b) : null;
  }

  function unitSlotDomain(u, R, model) {
    const P = model.periods;
    let dom = new Set();
    for (let s = 0; s < P; s++) dom.add(s);
    const rules = u.group ? {} : (((R || {})[u.teacher] || {}) || {}).rules || {};
    if (!u.group) {
      const td = teacherSlotDomain(u.teacher, R, P);
      if (td != null) dom = new Set(td);
    } else {
      const g = model._parallelGroups.filter(x => x.id === u.group)[0];
      if (g) {
        let gdom = (g.slots || []).map(x => SLOT_OF[x]).filter(s => s < P);
        if (!gdom.length) { for (let s = 0; s < P; s++) gdom.push(s); }
        const gset = new Set(gdom);
        for (const mem of u.members) {
          const md = teacherSlotDomain(mem, R, P);
          if (md != null) for (const s of Array.from(gset)) if (md.indexOf(s) < 0) gset.delete(s);
        }
        dom = gset;
      }
    }
    if (!u.group) {
      for (const e of (rules.subject_slots || [])) {
        for (const sec of u.secs) {
          if (u.courseBySec[sec] === e.subject) {
            const allow = slotSet(e.slots);
            for (const s of Array.from(dom)) if (!allow.has(s)) dom.delete(s);
          }
        }
      }
      for (const e of (rules.subject_slot_days || [])) {
        for (const sec of u.secs) {
          if (u.courseBySec[sec] === e.subject) {
            const only = SLOT_OF[e.slot];
            for (const s of Array.from(dom)) if (s !== only) dom.delete(s);
          }
        }
      }
      for (const e of (rules.allowed_slots_in_stream || [])) {
        for (const sec of u.secs) {
          if (secStream(sec) === e.stream) {
            const allow = slotSet(e.slots);
            for (const s of Array.from(dom)) if (!allow.has(s)) dom.delete(s);
          }
        }
      }
    }
    return Array.from(dom).sort((a, b) => a - b);
  }

  function unitDayDomain(u, R, model) {
    const D = model.days;
    let dom = new Set();
    for (let d = 0; d < D; d++) dom.add(d);
    const uEnt = u.group ? {} : ((R || {})[u.teacher] || {});
    const rules = u.group ? {} : (uEnt.rules || {});
    const metaBySec = model._metaBySec || {};
    for (const sec of u.secs) {
      const m = metaBySec[sec] || {};
      for (const d of (m.offDays || [])) dom.delete(d);
    }
    if (!u.group) {
      if (rules.allowed_days != null && hardnessOfJS(uEnt, "allowed_days") === 100) {
        const allow = daySet(rules.allowed_days);
        for (const d of Array.from(dom)) if (!allow.has(d)) dom.delete(d);
      }
      if (rules.forbidden_days != null && hardnessOfJS(uEnt, "forbidden_days") === 100) {
        for (const d of daySet(rules.forbidden_days)) dom.delete(d);
      }
      for (const e of (rules.allowed_days_in_stream || [])) {
        for (const sec of u.secs) {
          if (secStream(sec) === e.stream) {
            const allow = daySet(e.days);
            for (const d of Array.from(dom)) if (!allow.has(d)) dom.delete(d);
          }
        }
      }
      for (const e of (rules.subject_forbidden_days || [])) {
        for (const sec of u.secs) {
          if (u.courseBySec[sec] === e.subject) {
            for (const d of daySet(e.days)) dom.delete(d);
          }
        }
      }
      for (const e of (rules.subject_slot_days || [])) {
        for (const sec of u.secs) {
          if (u.courseBySec[sec] === e.subject) {
            const allow = daySet(e.days);
            for (const d of Array.from(dom)) if (!allow.has(d)) dom.delete(d);
          }
        }
      }
    } else {
      for (const mem of u.members) {
        const mEnt = (R || {})[mem] || {};
        const mr = mEnt.rules || {};
        if (mr.allowed_days != null && hardnessOfJS(mEnt, "allowed_days") === 100) {
          const allow = daySet(mr.allowed_days);
          for (const d of Array.from(dom)) if (!allow.has(d)) dom.delete(d);
        }
        if (mr.forbidden_days != null && hardnessOfJS(mEnt, "forbidden_days") === 100) {
          for (const d of daySet(mr.forbidden_days)) dom.delete(d);
        }
      }
    }
    for (const e of ((model.instructions || {}).subjectForbiddenDays || [])) {
      for (const sec of u.secs) {
        if (u.courseBySec[sec] === e.subject && (!e.scope || secStream(sec) === e.scope)) {
          for (const d of daySet(e.days)) dom.delete(d);
        }
      }
    }
    return Array.from(dom).sort((a, b) => a - b);
  }

  // ------------------------------------------------------------- evaluation
  // =====================================================================
  // teacherRuleFindings — JS mirror of solver-checker parity walk
  // (context_model.teacher_rule_findings). One deterministic implementation
  // of EVERY personal rule kind (personal_constraints_model.md v2) consumed
  // by evaluating and repair analysis. Scope semantics: entries without
  // scope apply everywhere; cell-level scope gates on the section's
  // pop/stream when the signal is known (permissive when unknown).
  // =====================================================================
  function scopeOfEntry(e) {
    const sc = (e && typeof e.scope === "object" && e.scope) || {};
    return sc;
  }
  function hardnessOfJS(entry, kind) {
    // Mirror of solver.py hardness_of: explicit entry.hardness map wins,
    // legacy soft list -> 50, everything else -> 100. (personal_constraints_model §8)
    const h = entry && entry.hardness;
    if (h && typeof h === "object" && Object.prototype.hasOwnProperty.call(h, kind)) {
      const n = parseInt(h[kind], 10);
      return isNaN(n) ? 100 : Math.max(0, Math.min(100, n));
    }
    if (entry && entry.soft && entry.soft.includes(kind)) return 50;
    return 100;
  }

  function scopeCellAppliesJS(e, sec, day, pop, stream) {
    const sc = scopeOfEntry(e);
    const pops = sc.populations, streams = sc.streams, secs = sc.sections, days = sc.days;
    if (pops && pop != null && pops.indexOf(pop) < 0) return false;
    if (streams && stream != null && streams.indexOf(stream) < 0) return false;
    if (secs && sec != null && secs.indexOf(sec) < 0) return false;
    if (days && day != null && !daySet(days).has(typeof day === "string" ? (DAY_OF[day] != null ? DAY_OF[day] : day) : day)) return false;
    if ((pops && pop == null) || (streams && stream == null)) return true; // permissive
    return true;
  }
  function scopeUnitAppliesJS(e, unit, popOf, streamOf) {
    const sc = scopeOfEntry(e);
    if (!sc.populations && !sc.streams && !sc.sections) return true;
    for (const sec of (unit.secs || [])) {
      if (sc.populations && sc.populations.indexOf(popOf(sec)) < 0) return false;
      if (sc.streams && sc.streams.indexOf(streamOf(sec)) < 0) return false;
      if (sc.sections && sc.sections.indexOf(sec) < 0) return false;
    }
    return true;
  }
  function entryDays(e, D) {
    let days = daySet(e.days || []);
    const scd = daySet(scopeOfEntry(e).days || []);
    if (days.size && scd.size) days = new Set([...days].filter(d => scd.has(d)));
    else if (scd.size) days = scd;
    if (!days.size) { days = new Set(); for (let d = 0; d < D; d++) days.add(d); }
    return days;
  }

  function teacherRuleFindings(code, entry, myUnits, cells, popMap, D, P, pen) {
    entry = entry || {};
    const rules = entry.rules || {};
    const softSet = new Set(entry.soft || []);
    // cells: [[d, s, sec, unit], ...]; popMap: {sec -> pop}; returns finding dicts.
    const findings = [];
    const popOf = sec => popMap[sec] != null ? popMap[sec] : null;
    const courseOfU = (u, sec) => (u.courseBySec || {})[sec];
    const applies = (e, d, s, sec, u) => scopeCellAppliesJS(e, sec, DAY_NAMES[d], popOf(sec), secStream(sec));
    const perDay = {}; const perDaySlot = {}; const occSlotsPerDay = {};
    for (const [d, s] of cells) {
      perDay[d] = (perDay[d] || 0) + 1;
      const k = d + "|" + s; perDaySlot[k] = true;
      (occSlotsPerDay[d] = occSlotsPerDay[d] || new Set()).add(s);
    }
    const sortedSlots = pairs => "[" + [...pairs].sort((a, b) => {
      const qa = ("" + a).split("|"), qb = ("" + b).split("|");
      return (+qa[0] - +qb[0]) || (+qa[1] - +qb[1]);
    }).map(k => {
      const q = ("" + k).split("|"); return "'" + DAY_NAMES[+q[0]] + " " + PERIOD_LABELS[+q[1]] + "'";
    }).join(", ") + "]";
    const clOf = pred => cells.filter(c => pred(c[0], c[1], c[2], c[3])).map(c => [c[2], c[0], c[1]]);
    const uidsOf = pred => [...new Set(cells.filter(c => pred(c[0], c[1], c[2], c[3])).map(c => c[3].id))].sort((a, b) => a - b);
    function add(ruleKey, msg, opts) {
      opts = opts || {};
      const h = hardnessOfJS(entry, ruleKey);
      if (h === 0) return;   // inactive: annotation only
      let isSoft = opts.isSoft != null ? !!opts.isSoft : softSet.has(ruleKey);
      let penX = opts.pen != null ? opts.pen : null;
      if (!isSoft && h < 100) {
        isSoft = true;                       // demoted hard kind
        if (penX === null) penX = Math.floor(pen.rule * h / 100);
      } else if (isSoft && h < 100) {
        // native soft (soft list) or soft_* kind — legacy list = h50 (spec §8)
        penX = Math.floor((penX !== null ? penX : pen.rule) * h / 100);
      }
      findings.push({
        rule_key: ruleKey, msg: msg,
        soft: isSoft,
        uids: opts.uids != null ? opts.uids : [...new Set(myUnits.map(u => u.id))].sort((a, b) => a - b),
        cells: opts.cells || [],
        pen: penX
      });
    }

    // ================================ HARD masks ================================
    if (rules.forbidden_slots != null) {
      const fset = slotSet(rules.forbidden_slots);
      const pred = (d, s, sec, u) => fset.has(s) && applies({}, d, s, sec, u);
      const bad = new Set(); for (const [d, s] of cells) if (fset.has(s)) bad.add(s);
      if (bad.size) add("forbidden_slots", "teaches in forbidden slot(s) [" +
        [...bad].sort((a, b) => a - b).map(s => "'" + PERIOD_LABELS[s] + "'").join(", ") + "]",
        { cells: clOf(pred), uids: uidsOf(pred) });
    }
    if (rules.allowed_slots != null) {
      const aset = slotSet(rules.allowed_slots);
      const pred = (d, s, sec, u) => !aset.has(s) && applies({}, d, s, sec, u);
      const bad = new Set(); for (const [d, s] of cells) if (!aset.has(s)) bad.add(s);
      if (bad.size) add("allowed_slots", "teaches outside allowed slots [" +
        [...bad].sort((a, b) => a - b).map(s => "'" + PERIOD_LABELS[s] + "'").join(", ") + "]",
        { cells: clOf(pred), uids: uidsOf(pred) });
    }
    if (rules.forbidden_days != null) {
      const dset = daySet(rules.forbidden_days);
      const pred = (d, s, sec, u) => dset.has(d) && applies({}, d, s, sec, u);
      const bad = new Set(); for (const [d] of cells) if (dset.has(d)) bad.add(d);
      if (bad.size) add("forbidden_days", "teaches on forbidden day(s) [" +
        [...bad].sort((a, b) => a - b).map(d => "'" + DAY_NAMES[d] + "'").join(", ") + "]",
        { cells: clOf(pred), uids: uidsOf(pred) });
    }
    if (rules.allowed_days != null) {
      const aset = daySet(rules.allowed_days);
      const pred = (d, s, sec, u) => !aset.has(d) && applies({}, d, s, sec, u);
      const bad = new Set(); for (const [d] of cells) if (!aset.has(d)) bad.add(d);
      if (bad.size) add("allowed_days", "teaches on non-allowed day(s) [" +
        [...bad].sort((a, b) => a - b).map(d => "'" + DAY_NAMES[d] + "'").join(", ") + "]",
        { cells: clOf(pred), uids: uidsOf(pred) });
    }
    for (const e of (rules.forbidden_slots_on_days || [])) {
      const dset = entryDays(e, D).size && (e.days || scopeOfEntry(e).days) ? entryDays(e, D) : entryDays(e, D);
      const sset = slotSet(e.slots);
      const pred = (d, s, sec, u) => dset.has(d) && sset.has(s) && applies(e, d, s, sec, u);
      const bad = new Set(); for (const [d, s, sec, u] of cells) if (pred(d, s, sec, u)) bad.add(d + "|" + s);
      if (bad.size) add("forbidden_slots_on_days", "teaches in forbidden day/slot " + sortedSlots(bad),
                        { cells: clOf(pred), uids: uidsOf(pred) });
    }
    // positive union-allow windows — grouped per scope signature
    if (rules.allowed_slots_days) {
      const groups = {};
      for (const e of rules.allowed_slots_days) {
        const sc = scopeOfEntry(e);
        const sig = JSON.stringify([sc.populations || [], sc.streams || [], sc.sections || []]);
        (groups[sig] = groups[sig] || []).push(e);
      }
      for (const sig in groups) {
        const es = groups[sig];
        const win = {};   // d -> Set(slots) union across same-scope entries
        for (const e of es) for (const d of entryDays(e, D)) {
          (win[d] = win[d] || new Set()); for (const s of slotSet(e.slots || [])) win[d].add(s);
        }
        const e0 = es[0];
        const pred = (d, s, sec, u) => (!win[d] || !win[d].has(s)) && applies(e0, d, s, sec, u);
        const bad = new Set(); for (const [d, s, sec, u] of cells) if (pred(d, s, sec, u)) bad.add(d + "|" + s);
        if (bad.size) add("allowed_slots_days", "teaches outside the allowed day/slot window " + sortedSlots(bad),
                          { cells: clOf(pred), uids: uidsOf(pred) });
      }
    }
    for (const e of (rules.allowed_slots_in_stream || [])) {
      const sset = slotSet(e.slots);
      const edays = e.days ? daySet(e.days) : null;
      const pred = (d, s, sec, u) => secStream(sec) === e.stream && !sset.has(s) &&
        (!edays || edays.has(d)) && applies(e, d, s, sec, u);
      const bad = new Set(); for (const [d, s, sec, u] of cells) if (pred(d, s, sec, u)) bad.add(d + "|" + s);
      if (bad.size) add("allowed_slots_in_stream", e.stream + " classes outside allowed slots " + sortedSlots(bad),
                        { cells: clOf(pred), uids: uidsOf(pred) });
    }
    for (const e of (rules.allowed_days_in_stream || [])) {
      const dset = daySet(e.days);
      const pred = (d, s, sec, u) => secStream(sec) === e.stream && !dset.has(d) && applies(e, d, s, sec, u);
      const bad = new Set(); for (const [d, s, sec] of cells) if (pred(d, s, sec, cells[0][3])) bad.add(d);
      if (bad.size) add("allowed_days_in_stream", e.stream + " classes on non-allowed day(s) [" +
                        [...bad].sort((a, b) => a - b).map(d => "'" + DAY_NAMES[d] + "'").join(", ") + "]",
                        { cells: clOf(pred), uids: uidsOf(pred) });
    }
    for (const e of (rules.stream_forbidden_days || [])) {
      const dset = daySet(e.days || []);
      const pred = (d, s, sec, u) => secStream(sec) === e.stream && dset.has(d) && applies(e, d, s, sec, u);
      const bad = new Set(); for (const [d, s, sec, u] of cells) if (pred(d, s, sec, u)) bad.add(d);
      if (bad.size) add("stream_forbidden_days", e.stream + " classes on forbidden day(s) [" +
                        [...bad].sort((a, b) => a - b).map(d => "'" + DAY_NAMES[d] + "'").join(", ") + "]",
                        { cells: clOf(pred), uids: uidsOf(pred) });
    }
    for (const e of (rules.allowed_slots_in_sections || [])) {
      const secset = new Set(e.sections || []);
      const dset = e.days ? daySet(e.days) : null;
      const sset = slotSet(e.slots || []);
      const pred = (d, s, sec, u) => secset.has(sec) && !sset.has(s) &&
        (!dset || dset.has(d)) && applies(e, d, s, sec, u);
      const bad = new Set(); for (const [d, s, sec, u] of cells) if (pred(d, s, sec, u)) bad.add(d + "|" + s);
      if (bad.size) add("allowed_slots_in_sections", "section-scoped classes outside allowed window " +
                        sortedSlots(bad), { cells: clOf(pred), uids: uidsOf(pred) });
    }
    for (const e of (rules.allowed_days_in_sections || [])) {
      const secset = new Set(e.sections || []);
      const dset = daySet(e.days || []);
      const pred = (d, s, sec, u) => secset.has(sec) && !dset.has(d) && applies(e, d, s, sec, u);
      const bad = new Set(); for (const [d, s, sec] of cells) if (pred(d, s, sec, cells[0][3])) bad.add(d);
      if (bad.size) add("allowed_days_in_sections", "section-scoped classes on non-allowed day(s) [" +
                        [...bad].sort((a, b) => a - b).map(d => "'" + DAY_NAMES[d] + "'").join(", ") + "]",
                        { cells: clOf(pred), uids: uidsOf(pred) });
    }
    if (rules.allowed_sections) {
      const aset = new Set(rules.allowed_sections);
      const pred = (d, s, sec, u) => !aset.has(sec);
      const bad = new Set(); for (const [d, s, sec] of cells) if (!aset.has(sec)) bad.add(sec);
      if (bad.size) add("allowed_sections", "teaches outside allowed sections [" + [...bad].sort().map(x => "'" + x + "'").join(", ") + "]",
                        { cells: clOf(pred), uids: uidsOf(pred) });
    }
    if (rules.forbidden_sections) {
      const fset = new Set(rules.forbidden_sections);
      const pred = (d, s, sec, u) => fset.has(sec);
      const bad = new Set(); for (const [d, s, sec] of cells) if (fset.has(sec)) bad.add(sec);
      if (bad.size) add("forbidden_sections", "teaches in forbidden sections [" + [...bad].sort().map(x => "'" + x + "'").join(", ") + "]",
                        { cells: clOf(pred), uids: uidsOf(pred) });
    }
    // ---- subject pin kinds (subject_slots unioned per subject; day-scoped ok)
    if (rules.subject_slots) {
      const bySubj = {};
      for (const e of rules.subject_slots) {
        const o = bySubj[e.subject] = bySubj[e.subject] || { win: {}, e: e };
        const ds = e.days ? daySet(e.days) : entryDays(e, D);
        for (const d of ds) { (o.win[d] = o.win[d] || new Set()); for (const s of slotSet(e.slots || [])) o.win[d].add(s); }
      }
      for (const subj in bySubj) {
        const o = bySubj[subj];
        const pred = (d, s, sec, u) => courseOfU(u, sec) === subj &&
          !(o.win[d] && o.win[d].has(s)) && applies(o.e, d, s, sec, u);
        const bad = new Set(); for (const [d, s, sec, u] of cells) if (pred(d, s, sec, u)) bad.add(d + "|" + s);
        if (bad.size) add("subject_slots", subj + " not in allowed slots " + sortedSlots(bad),
                          { cells: clOf(pred), uids: uidsOf(pred) });
      }
    }
    for (const e of (rules.subject_forbidden_days || [])) {
      const dset = daySet(e.days);
      const pred = (d, s, sec, u) => courseOfU(u, sec) === e.subject && dset.has(d) && applies(e, d, s, sec, u);
      const bad = new Set(); for (const [d, s, sec, u] of cells) if (pred(d, s, sec, u)) bad.add(d);
      if (bad.size) add("subject_forbidden_days", e.subject + " on forbidden day(s) [" +
                        [...bad].sort((a, b) => a - b).map(d => "'" + DAY_NAMES[d] + "'").join(", ") + "]",
                        { cells: clOf(pred), uids: uidsOf(pred) });
    }
    if (rules.subject_days_allowed) {
      const bySubj = {};
      for (const e of rules.subject_days_allowed) {
        bySubj[e.subject] = bySubj[e.subject] || new Set();
        for (const d of daySet(e.days)) bySubj[e.subject].add(d);
      }
      for (const subj in bySubj) {
        const dset = bySubj[subj];
        const pred = (d, s, sec, u) => courseOfU(u, sec) === subj && !dset.has(d);
        const bad = new Set(); for (const [d, s, sec, u] of cells) if (pred(d, s, sec, u)) bad.add(d);
        if (bad.size) add("subject_days_allowed", subj + " outside allowed day(s) [" +
                          [...bad].sort((a, b) => a - b).map(d => "'" + DAY_NAMES[d] + "'").join(", ") + "]",
                          { cells: clOf(pred), uids: uidsOf(pred) });
      }
    }
    // subject pins (singular + plural unioned per subject)
    const pins = {};
    for (const e of (rules.subject_slot_days || [])) {
      pins[e.subject] = pins[e.subject] || new Set();
      for (const d of daySet(e.days)) pins[e.subject].add(d + "|" + SLOT_OF[e.slot]);
    }
    for (const e of (rules.subject_slots_days || [])) {
      pins[e.subject] = pins[e.subject] || new Set();
      for (const d of daySet(e.days || [])) for (const s of slotSet(e.slots || [])) pins[e.subject].add(d + "|" + s);
    }
    for (const subj in pins) {
      const win = pins[subj];
      const pred = (d, s, sec, u) => courseOfU(u, sec) === subj && !win.has(d + "|" + s);
      const bad = new Set(); for (const [d, s, sec, u] of cells) if (pred(d, s, sec, u)) bad.add(d + "|" + s);
      if (bad.size) add(rules.subject_slot_days && rules.subject_slot_days.some(x => x.subject === subj)
                        ? "subject_slot_days" : "subject_slots_days",
                        subj + " outside pinned day/slot window " + sortedSlots(bad),
                        { cells: clOf(pred), uids: uidsOf(pred) });
    }

    // ================================ count / engagement ================================
    // NOTE: multi-section units count once per matching section cell — identical
    // to the Python checker.
    for (const e of (rules.min_days_in_slot || [])) {
      const si = SLOT_OF[e.slot];
      const days = new Set();
      for (const [d, s, sec, u] of cells) if (s === si && applies(e, d, s, sec, u)) days.add(d);
      const floor = e.min_days || 1;
      if (days.size < floor) add("min_days_in_slot", e.slot + " engaged only " + days.size +
        " days (<" + floor + ")", {
        cells: cells.filter(c => c[1] === si && applies(e, c[0], c[1], c[2], c[3])).map(c => [c[2], c[0], c[1]])
      });
    }
    if (rules.min_days_engaged) {
      if (Object.keys(perDay).length < rules.min_days_engaged)
        add("min_days_engaged", "engaged only " + Object.keys(perDay).length +
            " days (<" + rules.min_days_engaged + ")");
    }
    const mppd = rules.max_periods_per_day;
    const mppdList = typeof mppd === "number" ? [{ max: mppd }] : (Array.isArray(mppd) ? mppd : []);
    for (const e of mppdList) {
      const cap = e.max; if (cap == null) continue;
      const dsel = entryDays(e, D);
      for (let d = 0; d < D; d++) {
        if (!dsel.has(d)) continue;
        const pred = (d2, s, sec, u) => d2 === d &&
          (!e.stream || secStream(sec) === e.stream) &&
          (!e.sections || e.sections.indexOf(sec) >= 0) && applies(e, d2, s, sec, u);
        const n = cells.filter(c => pred(c[0], c[1], c[2], c[3])).length;
        if (n > cap) add("max_periods_per_day", n + " scoped periods on " + DAY_NAMES[d] + " (>" + cap + ")",
          { cells: cells.filter(c => pred(c[0], c[1], c[2], c[3])).map(c => [c[2], c[0], c[1]]) });
      }
    }
    const minpd = rules.min_periods_per_day;
    const minpdList = typeof minpd === "number" ? [{ min: minpd }] : (Array.isArray(minpd) ? minpd : []);
    for (const e of minpdList) {
      const floor = e.min; if (floor == null) continue;
      const dsel = entryDays(e, D);
      for (let d = 0; d < D; d++) {
        if (!dsel.has(d)) continue;
        const pred = (d2, s, sec, u) => d2 === d &&
          (!e.stream || secStream(sec) === e.stream) &&
          (!e.sections || e.sections.indexOf(sec) >= 0) && applies(e, d2, s, sec, u);
        const n = cells.filter(c => pred(c[0], c[1], c[2], c[3])).length;
        if ((perDay[d] || 0) > 0 && n < floor)
          add("min_periods_per_day", "only " + n + " scoped periods on " + DAY_NAMES[d] + " (<" + floor + ")",
            { cells: cells.filter(c => pred(c[0], c[1], c[2], c[3])).map(c => [c[2], c[0], c[1]]) });
      }
    }
    for (const e of (rules.max_days_in_slot || [])) {
      const si = SLOT_OF[e.slot]; const cap = e.max_days; if (cap == null) continue;
      const days = new Set();
      for (const [d, s, sec, u] of cells) if (s === si && entryDays(e, D).has(d) && applies(e, d, s, sec, u)) days.add(d);
      if (days.size > cap) add("max_days_in_slot", e.slot + " engaged on " + days.size + " days (>" + cap + ")");
    }
    // ---- distribution quotas
    const quotaMatch = (e, d, s, sec, u) => {
      if (e.subject && courseOfU(u, sec) !== e.subject) return false;
      if (e.subjects && e.subjects.indexOf(courseOfU(u, sec)) < 0) return false;
      if (e.stream && secStream(sec) !== e.stream) return false;
      if (e.sections && e.sections.indexOf(sec) < 0) return false;
      if (e.slot && SLOT_OF[e.slot] !== s) return false;
      if (e.days && !daySet(e.days).has(d)) return false;
      return applies(e, d, s, sec, u);
    };
    for (const [key, dir] of [["max_pieces_match", "max"], ["min_pieces_match", "min"]]) {
      for (const e of (rules[key] || [])) {
        const bound = e[dir]; if (bound == null) continue;
        const matching = cells.filter(c => quotaMatch(e, c[0], c[1], c[2], c[3]));
        const n = matching.length;
        const hit = dir === "max" ? n > bound : n < bound;
        if (hit) {
          const sel = Object.keys(e).filter(k => ["scope", "max", "min"].indexOf(k) < 0)
            .map(k => k + "=" + JSON.stringify(e[k])).join(", ");
          add(key, n + " matching pieces [" + sel + "] (" + dir + " " + bound + ")",
              { cells: matching.map(c => [c[2], c[0], c[1]]) });
        }
      }
    }
    // ---- legacy engagement: stream slot required ≥4 days (default), min_days override
    for (const e of (rules.stream_slots_required || [])) {
      const hasStream = myUnits.some(u2 => u2.secs.some(sec2 => secStream(sec2) === e.stream));
      if (!hasStream) continue;
      for (const sl of e.slots) {
        const si = SLOT_OF[sl];
        const edays = entryDays(e, D);
        const days = new Set();
        for (const [d, s, sec, u] of cells)
          if (s === si && secStream(sec) === e.stream && edays.has(d) && applies(e, d, s, sec, u)) days.add(d);
        const floor = e.min_days || 4;
        if (days.size < floor) add("stream_slots_required", e.stream + " " + sl + " engaged only " +
          days.size + " days (<" + floor + ")",
          { cells: cells.filter(c => c[1] === si && secStream(c[2]) === e.stream && applies(e, c[0], c[1], c[2], c[3]))
                        .map(c => [c[2], c[0], c[1]]) });
      }
    }

    // ================================ structure ================================
    if (rules.no_daily_gaps) {
      for (let d = 0; d < D; d++) {
        const sset = occSlotsPerDay[d];
        if (!sset || sset.size < 2) continue;
        const arr = [...sset];
        const lo = Math.min(...arr), hi = Math.max(...arr);
        const gaps = (hi - lo + 1) - sset.size;
        if (gaps) add("no_daily_gaps", gaps + " gap(s) inside " + DAY_NAMES[d] +
          "'s teaching run (P" + (lo + 1) + "–P" + (hi + 1) + ")",
          { cells: cells.filter(c => c[0] === d).map(c => [c[2], c[0], c[1]]) });
      }
    }

    // ================================ SOFT ================================
    if (rules.soft_prefer_free_slots) {
      const sset = slotSet(rules.soft_prefer_free_slots);
      let n = 0; for (const [d, s] of cells) if (sset.has(s)) n++;
      if (n) add("soft_prefer_free_slots", n + " period(s) in preferred-free slots [" +
                 rules.soft_prefer_free_slots.join(",") + "]",
                 { isSoft: true, pen: pen.preferFreeSlot * n,
                   cells: cells.filter(c => sset.has(c[1])).map(c => [c[2], c[0], c[1]]) });
    }
    for (const e of (rules.soft_prefer_free_slots_days || [])) {
      const dset = daySet(e.days); const sset = slotSet(e.slots);
      const n = cells.filter(c => dset.has(c[0]) && sset.has(c[1]) && applies(e, c[0], c[1], c[2], c[3])).length;
      if (n) add("soft_prefer_free_slots_days", n + " period(s) in preferred-free windows " +
                 e.days.join("/") + " " + e.slots.join(","),
                 { isSoft: true, pen: pen.preferFreeSlot * n,
                   cells: cells.filter(c => dset.has(c[0]) && sset.has(c[1]) && applies(e, c[0], c[1], c[2], c[3]))
                               .map(c => [c[2], c[0], c[1]]) });
    }
    if (rules.soft_even_distribution) {
      const total = cells.length;
      const daysUsed = Object.keys(perDay).length || 1;
      const cap = Math.ceil(total / Math.max(1, daysUsed));
      let excess = 0;
      for (const d in perDay) excess += Math.max(0, perDay[d] - cap);
      if (excess) add("soft_even_distribution", excess + " period(s) above the even per-day share",
                      { isSoft: true, pen: pen.evenDistribution * excess });
    }
    if (rules.soft_compact_days) {
      let gaps = 0;
      for (let d = 0; d < D; d++) {
        const sset = occSlotsPerDay[d];
        if (!sset || sset.size < 2) continue;
        const arr = [...sset];
        gaps += (Math.max(...arr) - Math.min(...arr) + 1) - sset.size;
      }
      if (gaps) add("soft_compact_days", gaps + " gap(s) inside teaching days (moves toward compact days)",
                    { isSoft: true, pen: pen.rule * gaps });
    }
    return findings;
  }

  function periodCoherenceFindings(grids, model) {
    // Mirror of context_model.period_coherence_findings (spec §9) — byte-identical msgs.
    // Inter-level only: BS coherence is a silent objective bonus, never a rule (§9 scope).
    const D = model.days, P = model.periods;
    const pen = model.penalties;
    const issues = [], violations = [];
    const byId = {};
    for (const u of model.units) byId[u.id] = u;
    for (const section of model.sections) {
      if ((section.level || "inter") !== "inter") continue;   // BS: bonus only, no findings
      const key = section.key;
      const g = grids[key];
      if (!g) continue;
      const slotsByCourse = {};
      for (let d = 0; d < D; d++) for (let s = 0; s < P; s++) {
        const uid = g[d][s];
        if (uid === null || byId[uid] === undefined) continue;
        const cname = byId[uid].courseBySec[key];
        if (cname === undefined || cname === null) continue;
        (slotsByCourse[cname] = slotsByCourse[cname] || []).push(s);
      }
      for (const cname of Object.keys(slotsByCourse).sort()) {
        const lst = slotsByCourse[cname];
        const total = lst.length;
        if (total < 3) continue;
        const freq = {};
        for (const s of lst) freq[s] = (freq[s] || 0) + 1;
        let best = 0;
        for (const k in freq) if (freq[k] > best) best = freq[k];
        let dom = null;
        for (const k in freq) {
          if (freq[k] === best && (dom === null || (+k) < dom)) dom = +k;
        }
        const dev = total - best;
        const plab = PERIOD_LABELS[dom];
        // structural + sanctioned exemptions (spec §9, mirrors _struct_attain_for):
        // cascade-exempt partitions (from ctx._cohExempt) keep deviations doc-soft.
        const exempt = model._cohExempt || new Set();
        const exKey = key + "|" + cname;
        if (total >= 4 && exempt.has(exKey)) {
          if (dev >= 1) {
            violations.push({ rule: "courseConsistency:" + key + ":" + cname,
              detail: key + " " + cname + ": " + dev + " of " + total + " classes outside dominant period " + plab
                      + " (alignment infeasible — documented exception)",
              penalty: pen["periodConsistency45"] * dev });
          }
          continue;
        }
        if (total >= 4) {
          if (dev >= 2) {
            issues.push(key + " " + cname + ": " + dev + " of " + total + " classes outside one period "
                        + "(dominant " + plab + ") — beyond the allowed 1 tolerance");
          } else if (dev === 1) {
            violations.push({ rule: "courseConsistency:" + key + ":" + cname,
              detail: key + " " + cname + ": 1 class outside dominant period " + plab + " (allowed at most 1)",
              penalty: pen["periodConsistency45"] });
          }
        } else {
          if (dev >= 1) {
            violations.push({ rule: "courseConsistency:" + key + ":" + cname,
              detail: key + " " + cname + ": " + dev + " of 3 classes outside dominant period " + plab,
              penalty: pen["periodConsistency3"] * dev });
          }
        }
      }
    }
    return { issues: issues, violations: violations };
  }

  function evaluate(grids, model) {
    const D = model.days, P = model.periods;
    const issues = [], violations = [];
    const pen = model.penalties;
    const units = model.units;
    const byId = {};
    for (const u of units) byId[u.id] = u;
    const courseOf = (u, sec) => u.courseBySec[sec] || Object.values(u.courseBySec)[0];

    // ---- per-section structural checks
    for (const section of model.sections) {
      const key = section.key;
      const g = grids[key];
      if (!g) { issues.push(key + ": missing grid"); continue; }
      const level = section.level;
      const counts = {};
      for (let d = 0; d < D; d++) {
        if (section.offDays.indexOf(d) >= 0) {
          for (let s = 0; s < P; s++) {
            if (g[d][s] !== null && g[d][s] !== undefined) {
              issues.push(key + ": class on off day " + DAY_NAMES[d]);
            }
          }
          continue;
        }
        const seen = {};
        const occSlots = [];
        for (let s = 0; s < P; s++) if (g[d][s] !== null && g[d][s] !== undefined) occSlots.push(s);
        for (let s = 0; s < P; s++) {
          const uid = g[d][s];
          if (uid === null || uid === undefined) continue;
          const u = byId[uid];
          if (!u) { issues.push(key + ": unknown unit " + uid); continue; }
          const cname = courseOf(u, key);
          counts[cname] = (counts[cname] || 0) + 1;
          const noDup = ((model.instructions.noSameSubjectSameDay || {})[level] !== false);
          if (noDup) {
            if (seen[cname]) issues.push(key + " " + DAY_NAMES[d] + " " + cname + " twice in a day");
            seen[cname] = true;
          }
        }
        if (section.firstLast && level === "bs" && section.effDays.indexOf(d) >= 0) {
          if (occSlots.length && (occSlots.indexOf(0) < 0 || occSlots.indexOf(P - 1) < 0)) {
            issues.push(key + " " + DAY_NAMES[d] + ": first/last period must be occupied");
          }
        }
      }
      for (const sub of section.subs) {
        if ((counts[sub[0]] || 0) !== sub[2]) {
          issues.push(key + " " + sub[0] + " load " + (counts[sub[0]] || 0) + " != " + sub[2]);
        }
      }
      if (level === "inter") {
        let empty = 0;
        for (let d = 0; d < D; d++) for (let s = 0; s < P; s++) {
          if (g[d][s] === null || g[d][s] === undefined) empty++;
        }
        if (empty) issues.push(key + ": " + empty + " empty cells (inter sections fill the grid)");
      }
    }

    // ---- course period-coherence (spec §9)
    const coh = periodCoherenceFindings(grids, model);
    for (const i2 of coh.issues) issues.push(i2);
    for (const v2 of coh.violations) violations.push(v2);

    // ---- teacher occupancy (deduped across dual sections / groups)
    const occ = {};
    for (const u of units) {
      if (!u.group && !u.teacher) {
        issues.push("unit " + u.id + " (" + Object.values(u.courseBySec).join("/") + "): unresolved teacher");
      }
      const cells = new Set();
      for (const sec of u.secs) {
        const g = grids[sec];
        if (!g) continue;
        for (let d = 0; d < D; d++) for (let s = 0; s < P; s++) {
          if (g[d][s] === u.id) cells.add(d + "|" + s);
        }
      }
      const teachers = [u.teacher].concat(u.group ? u.members : []);
      for (const t of teachers) {
        if (t == null || t === "") continue;
        for (const k of cells) {
          const parts = k.split("|");
          (occ[t] = occ[t] || []).push([+parts[0], +parts[1], u.secs[0]]);
        }
      }
    }
    for (const t in occ) {
      const seen = new Set();
      for (const [d, s] of occ[t]) {
        const k = d * P + s;
        if (seen.has(k)) issues.push("teacher " + t + " double-booked " + DAY_NAMES[d] + " " + PERIOD_LABELS[s]);
        seen.add(k);
      }
    }

    // ---- combined classes: identical cell sets in both sections
    for (const cc of model.combined) {
      const u = byId[cc.unit];
      if (!u || u.secs.length !== 2) continue;
      const ca = new Set(), cb = new Set();
      for (let d = 0; d < D; d++) for (let s = 0; s < P; s++) {
        if (grids[u.secs[0]] && grids[u.secs[0]][d][s] === u.id) ca.add(d + "|" + s);
        if (grids[u.secs[1]] && grids[u.secs[1]][d][s] === u.id) cb.add(d + "|" + s);
      }
      if (ca.size !== cb.size || ![...ca].every(k => cb.has(k))) {
        issues.push("combined " + cc.id + ": slot sets differ between " + u.secs[0] + " and " + u.secs[1]);
      }
    }

    // ---- parallel groups: count + single slot
    for (const u of units) {
      if (!u.group) continue;
      const cells = [];
      for (const sec of u.secs) {
        const g = grids[sec];
        if (!g) continue;
        for (let d = 0; d < D; d++) for (let s = 0; s < P; s++) {
          if (g[d][s] === u.id) cells.push([d, s]);
        }
      }
      if (cells.length !== u.count) issues.push("parallel " + u.group + ": " + cells.length + " cells != " + u.count);
      const slots = new Set(cells.map(x => x[1]));
      if (slots.size !== 1) issues.push("parallel " + u.group + ": spans slots " + [...slots].join(","));
    }

    // ---- day-exclusive pairs (per section): disjoint days; soft consecutive
    for (const p of model.dayExclusive) {
      const daysets = [];
      for (const uid of p.units) {
        const u = byId[uid];
        const days = new Set();
        for (const sec of u.secs) {
          const g = grids[sec];
          if (!g) continue;
          for (let d = 0; d < D; d++) for (let s = 0; s < P; s++) {
            if (g[d][s] === uid) days.add(d);
          }
        }
        daysets.push([u, days]);
      }
      for (let i = 0; i < daysets.length; i++) {
        for (let j = i + 1; j < daysets.length; j++) {
          for (const d of daysets[i][1]) {
            if (daysets[j][1].has(d)) {
              issues.push("dayExclusive " + p.id + ": " + courseOf(daysets[i][0], daysets[i][0].secs[0]) +
                          " shares day " + DAY_NAMES[d] + " with " + courseOf(daysets[j][0], daysets[j][0].secs[0]));
            }
          }
        }
      }
      if (p.softConsecutiveDays) {
        for (const [u, days] of daysets) {
          if (u.count === 2 && days.size === 2) {
            const sorted = [...days].sort((a, b) => a - b);
            if (sorted[1] - sorted[0] !== 1) {
              violations.push({
                rule: "dayExclusive:" + p.id,
                detail: courseOf(u, u.secs[0]) + " on non-consecutive days " +
                        DAY_NAMES[sorted[0]] + "," + DAY_NAMES[sorted[1]],
                penalty: pen.nonConsecutive
              });
            }
          }
        }
      }
    }

    // ---- inter 2/wk consecutive days (hard instruction)
    if ((model.instructions.consecutiveFor2pw || {}).inter) {
      for (const u of units) {
        if (u.count !== 2 || u.level !== "inter") continue;
        const days = new Set();
        for (const sec of u.secs) {
          const g = grids[sec];
          if (!g) continue;
          for (let d = 0; d < D; d++) for (let s = 0; s < P; s++) {
            if (g[d][s] === u.id) days.add(d);
          }
        }
        if (days.size === 2) {
          const sorted = [...days].sort((a, b) => a - b);
          if (sorted[1] - sorted[0] !== 1) {
            issues.push(u.secs[0] + " " + courseOf(u, u.secs[0]) + ": 2/wk on non-consecutive days " +
                        DAY_NAMES[sorted[0]] + "," + DAY_NAMES[sorted[1]]);
          }
        }
      }
    }

    // ---- faculty constraints (person-level; soft -> documented violations)
    // One shared deterministic walker implements every personal rule kind
    // (mirror of context_model.teacher_rule_findings; kinds/semantics per
    // personal_constraints_model.md v2).
    const R = model.constraints;
    const popMap = {};
    for (const s of (model.sections || [])) popMap[s.key] = s.pop != null ? s.pop : null;
    for (const code in R) {
      const entry = R[code] || {};
      const rules = entry.rules || {};
      const soft = new Set(entry.soft || []);
      const myUnits = units.filter(u => u.teacher === code || (u.members && u.members.indexOf(code) >= 0));
      if (!myUnits.length) continue;
      const cells = [];
      for (const u of myUnits) {
        for (const sec of u.secs) {
          const g = grids[sec];
          if (!g) continue;
          for (let d = 0; d < D; d++) for (let s = 0; s < P; s++) {
            if (g[d][s] === u.id) cells.push([d, s, sec, u]);
          }
        }
      }
      for (const f of teacherRuleFindings(code, entry, myUnits, cells, popMap, D, P, pen)) {
        if (f.soft) {
          violations.push({ rule: code + ":" + f.rule_key, detail: f.msg,
                            penalty: f.pen != null ? f.pen : pen.rule });
        } else {
          issues.push(code + " " + f.msg);
        }
      }
    }

    // ---- general instructions (institution-level)
    for (const e of ((model.instructions.subjectForbiddenDays) || [])) {
      for (const u of units) {
        for (const sec of u.secs) {
          if (courseOf(u, sec) !== e.subject) continue;
          if (e.scope && secStream(sec) !== e.scope) continue;
          const g = grids[sec];
          if (!g) continue;
          const ds = daySet(e.days);
          for (let d = 0; d < D; d++) for (let s = 0; s < P; s++) {
            if (g[d][s] === u.id && ds.has(d)) {
              issues.push(sec + " " + e.subject + " on forbidden day " + DAY_NAMES[d]);
            }
          }
        }
      }
    }
    for (const e of ((model.instructions.subjectForbiddenSlotDays) || [])) {
      // generalized 'forbid cells' kernel matcher (dynamic rules lower here too)
      const hit = (u, sec) => {
        if (e.subject && courseOf(u, sec) !== e.subject) return false;
        if (e.subjects && e.subjects.length && e.subjects.indexOf(courseOf(u, sec)) < 0) return false;
        if (e.sections && e.sections.length && e.sections.indexOf(sec) < 0) return false;
        if (e.teachers && e.teachers.length) {
          const mems = u.members || [];
          if (e.teachers.indexOf(u.teacher) < 0 && !mems.some(m => e.teachers.indexOf(m) >= 0)) return false;
        }
        if (e.scope && secStream(sec) !== e.scope) return false;
        return true;
      };
      const lbl = [e.subject, (e.subjects || []).join('/'), (e.sections || []).join(','), (e.teachers || []).join(',')]
                  .filter(Boolean).join(' ') || 'cells';
      const ds = (e.days && e.days.length) ? daySet(e.days) : null;
      const ss = (e.slots && e.slots.length) ? slotSet(e.slots) : null;
      for (const u of units) {
        for (const sec of u.secs) {
          if (!hit(u, sec)) continue;
          const g = grids[sec];
          if (!g) continue;
          for (let d = 0; d < D; d++) for (let s = 0; s < P; s++) {
            if (g[d][s] === u.id && (!ds || ds.has(d)) && (!ss || ss.has(s))) {
              issues.push(sec + " " + lbl + " at forbidden window " + DAY_NAMES[d] + " " + PERIOD_LABELS[s]);
            }
          }
        }
      }
    }
    for (const e of ((model.instructions.nonOverriding) || [])) {
      const secs = e.sections, subs = e.subjects;
      for (const x of secs) {
        const gx = grids[x];
        if (!gx) continue;
        let found = false;
        for (let d = 0; d < D && !found; d++) {
          for (let s = 0; s < P && !found; s++) {
            const uid = gx[d][s];
            if (uid === null || uid === undefined) continue;
            const u = byId[uid];
            if (u && courseOf(u, x) === subs[0]) {
              let ok = true;
              for (const y of secs) {
                if (y === x) continue;
                const gy = grids[y];
                if (!gy) continue;
                const uidy = gy[d][s];
                const uy = (uidy === null || uidy === undefined) ? null : byId[uidy];
                if (uy && courseOf(uy, y) === subs[1]) { ok = false; break; }
              }
              if (ok) found = true;
            }
          }
        }
        if (!found) issues.push("non-overriding failed " + x);
      }
    }
    if (model.instructions.softIndividualSpread) {
      for (const t in occ) {
        let hasP1 = false, hasLast = false;
        for (const [d, s] of occ[t]) {
          if (s === 0) hasP1 = true;
          if (s === P - 1) hasLast = true;
        }
        if (hasP1 && hasLast) {
          violations.push({ rule: t + ":soft_individual_spread",
                            detail: "engaged in P1 and " + PERIOD_LABELS[P - 1] + " in the same week",
                            penalty: pen.individualSpread });
        }
      }
    }

    let penalty = 0;
    for (const v of violations) penalty += v.penalty;
    return { issues: issues, violations: violations, penalty: penalty };
  }

  // ------------------------------------------------------------- scoring
  function shuffleScore(grids, model) {
    const D = model.days, P = model.periods;
    const byId = {};
    for (const u of model.units) byId[u.id] = u;
    let pen = 0;
    for (const section of model.sections) {
      const g = grids[section.key];
      if (!g) continue;
      const slotsBy = {};
      for (let d = 0; d < D; d++) {
        for (let s = 0; s < P; s++) {
          const uid = g[d][s];
          if (uid === null || uid === undefined) continue;
          const u = byId[uid];
          const cname = u.courseBySec[section.key] || Object.values(u.courseBySec)[0];
          (slotsBy[cname] = slotsBy[cname] || new Set()).add(s);
        }
      }
      for (const sub of section.subs) {
        const cname = sub[0], count = sub[2];
        const extra = (slotsBy[cname] ? slotsBy[cname].size : 0) - 1;
        if (count === 5) pen += extra * 100000;
        else if (count === 4) pen += extra * 10000;
        else if (count === 3) pen += extra * 100;
        else pen += extra * 10;
      }
    }
    return pen;
  }

  // ------------------------------------------------------------- pool policy
  function poolSelection(solutions, target, cutoff) {
    target = target || 10; cutoff = cutoff || 25;
    const valid = solutions.filter(s => !s.penalty);
    const violators = solutions.filter(s => s.penalty);
    let display;
    if (valid.length >= cutoff) display = valid.slice(0, cutoff);
    else if (valid.length >= target) display = valid.slice();
    else display = valid.concat(violators.slice(0, target - valid.length));
    return {
      display: display,
      counts: {
        valid_found: valid.length, violators_found: violators.length,
        shown: display.length,
        shown_violators: display.filter(s => s.penalty).length
      }
    };
  }

  // ------------------------------------------------------------- search
  // Two-stage design (the classic architecture of solver.js, generalized):
  //   Phase 1 — per-section SLOT PACKING: each unit gets a plan (how many of
  //     its pieces go to which period column) such that every section's
  //     column profile fits (inter: every column exactly full; BS firstLast:
  //     boundary columns exactly full; teacher capacities per column; the
  //     engagement rules supply >= 4 pieces per required slot).
  //   Phase 2 — per-slot DAY COLORING: each piece gets a day (edge coloring
  //     with unit/section/teacher/pair/consecutive/engagement constraints).
  function buildUnitPlans(u, model) {
    const sd = unitSlotDomain(u, model.constraints, model);
    const c = u.count;
    const list = [];
    if (!sd.length) return list;
    const seen = new Set();
    const addPlan = cols => {
      const sorted = cols.slice().sort((a, b) => a[0] - b[0]);
      const key = sorted.map(x => x.join(":")).join("|");
      if (seen.has(key)) return;
      seen.add(key);
      const n = sorted.length;
      const tier = n === 1 ? 0
        : (n === 2 && (c === 2 || c === 3) ? 1
           : (n === 2 ? 2 : 3));
      list.push({ cols: sorted, tier: tier });
    };
    // single slot
    for (const s of sd) addPlan([[s, c]]);
    if (sd.length >= 2) {
      // two-slot splits (all k)
      if (!u.group) {
        for (const sp of combinations(sd, 2)) {
          for (let k = 1; k < c; k++) addPlan([[sp[0], k], [sp[1], c - k]]);
        }
        // multi-way splits with parts of size 1-2 (>= 3 slots): required when
        // columns are tight (more 4/wk courses than free columns; day-domain
        // caps like Naeem's 4-day Monday ban forbid full-column monopolies)
        if (c >= 3 && sd.length >= 3) {
          for (const part of smallPartitions(c)) {
            const m = part.length;
            if (m > sd.length) continue;
            for (const combo of combinations(sd, m)) {
              for (const perm of distinctPermutations(part)) {
                addPlan(combo.map((sl, i) => [sl, perm[i]]));
              }
            }
          }
        }
      } else {
        // parallel groups: single slot only (structurally pinned)
      }
    }
    return list;
  }

  // partitions of c into parts of size 1-3 with at least 3 parts (a part of 3
  // is required for some 5/wk splits, e.g. {P1:3, P3:1, P5:1})
  function smallPartitions(c) {
    const out = [];
    (function rec(remaining, acc) {
      if (remaining === 0) { if (acc.length >= 3) out.push(acc.slice()); return; }
      for (const p of [3, 2, 1]) {
        if (p <= remaining) { acc.push(p); rec(remaining - p, acc); acc.pop(); }
      }
    })(c, []);
    return out;
  }

  function distinctPermutations(arr) {
    const out = [], used = new Set();
    (function rec(rem, acc) {
      if (!rem.length) {
        const key = acc.join(",");
        if (!used.has(key)) { used.add(key); out.push(acc.slice()); }
        return;
      }
      for (let i = 0; i < rem.length; i++) {
        acc.push(rem[i]);
        rec(rem.filter((_, j) => j !== i), acc);
        acc.pop();
      }
    })(arr, []);
    return out;
  }

  function teachersOf(u) {
    return [u.teacher].concat(u.members || []);
  }

  function generateContext(ctx, opts) {
    opts = opts || {};
    const maxCount = opts.maxCount > 0 ? opts.maxCount : Infinity;
    const timeMs = opts.timeMs || 15000;
    const seed = opts.seed || (Date.now() % 2147483647);
    const model = contextToModel(ctx);
    if (!model.sections.length || !model.units.length) {
      return { solutions: [], stats: { attempts: 0, valids: 0, distinct: 0, seed: seed, elapsedMs: 0 }, model: model };
    }
    const rng = makeRng(seed);
    const t0 = Date.now();
    const seen = {};
    const solutions = [];
    let attempts = 0, valids = 0, failures = 0;

    // static plans + day domains (domains never change during the search)
    const plans = {}, dd = {};
    for (const u of model.units) {
      plans[u.id] = buildUnitPlans(u, model);
      dd[u.id] = unitDayDomain(u, model.constraints, model);
      if (!plans[u.id].length || !dd[u.id].length) {
        return { solutions: [], stats: { attempts: 0, valids: 0, distinct: 0, seed: seed,
                                         elapsedMs: 0, infeasibleUnit: u.id }, model: model };
      }
    }

    while (solutions.length < maxCount && Date.now() - t0 < timeMs) {
      attempts++;
      const grids = solveAttempt(model, plans, dd, rng, opts.nodeBudget || 120000, t0, timeMs);
      if (!grids) { failures++; continue; }
      const ev = evaluate(grids, model);
      if (ev.issues.length) { failures++; continue; }
      valids++;
      const key = gridsKey(grids);
      if (seen[key]) continue;
      seen[key] = true;
      const sc = shuffleScore(grids, model);
      solutions.push({ grids: grids, score: sc, penalty: ev.penalty,
                       violations: ev.violations, total: sc + ev.penalty });
    }
    solutions.sort((a, b) => ((a.penalty > 0 ? 1 : 0) - (b.penalty > 0 ? 1 : 0)) || (a.total - b.total));
    return {
      solutions: solutions,
      stats: { attempts: attempts, valids: valids, failures: failures,
               distinct: solutions.length, seed: seed, elapsedMs: Date.now() - t0 },
      model: model
    };
  }

  function solveAttempt(model, plans, dd, rng, nodeBudget, t0, timeMs) {
    const packed = phase1(model, plans, dd, rng, t0, timeMs);
    if (!packed) return null;
    return phase2(model, packed, dd, rng, nodeBudget, t0, timeMs);
  }

  // ------------------------------------------------------------------ phase 1
  // Stage-1 slot packing. Sections are packed one at a time (inter first,
  // randomized within groups); each section's packing is generated ON THE FLY
  // by a randomized unit-plan DFS that checks GLOBAL teacher capacities,
  // day-domain caps and engagement-group targets DURING enumeration (a
  // pre-enumerated sample cannot know the global state). Full backtracking
  // across sections with bounded retries per section.
  function phase1(model, plans, dd, rng, t0, timeMs) {
    const P = model.periods;
    const R = model.constraints;
    const D = model.days;

    const colCap = {};
    for (const s of model.sections) colCap[s.key] = s.effDays.length;
    const fillOf = {};
    for (const s of model.sections) {
      fillOf[s.key] = model.units.reduce(
        (n, u) => n + (u.courseBySec[s.key] !== undefined ? u.count : 0), 0);
    }
    // boundary targets (firstLast BS: col0/colLast must fill exactly)
    const boundaryCols = {};
    for (const s of model.sections) {
      boundaryCols[s.key] = (s.level !== "inter" && s.firstLast) ? [0, P - 1] : [];
    }

    const unitsOf = {};
    for (const u of model.units) for (const sec of u.secs) (unitsOf[sec] = unitsOf[sec] || []).push(u);

    // teacher/dd indices
    const teacherIdx = {};
    let nT = 0;
    for (const u of model.units) {
      for (const t of teachersOf(u)) if (!(t in teacherIdx)) teacherIdx[t] = nT++;
    }
    const ddKeyOf = {}, ddLenOf = {};
    for (const u of model.units) {
      ddKeyOf[u.id] = dd[u.id].join(",");
      ddLenOf[u.id] = dd[u.id].length;
    }

    // tight teachers (>= 70% utilization) — balanced top-down targets
    const totalPieces = new Int32Array(nT);
    const allowedSlots = {};
    for (const u of model.units) {
      const sd = unitSlotDomain(u, R, model);
      for (const t of teachersOf(u)) {
        const ti = teacherIdx[t];
        totalPieces[ti] += u.count;
        if (!allowedSlots[ti]) allowedSlots[ti] = new Set();
        for (const sl of sd) allowedSlots[ti].add(sl);
      }
    }
    const tight = new Uint8Array(nT);
    for (let t = 0; t < nT; t++) if (totalPieces[t] >= 0.7 * D * P) tight[t] = 1;

    // engagement requirements
    const groupList = [];
    for (const code in R) {
      const rules = (R[code] || {}).rules || {};
      const wants = [];
      for (const e of (rules.min_days_in_slot || [])) wants.push({ slot: SLOT_OF[e.slot], need: 4, stream: null });
      for (const e of (rules.stream_slots_required || [])) {
        for (const sl of e.slots) wants.push({ slot: SLOT_OF[sl], need: 4, stream: e.stream });
      }
      for (const w of wants) {
        const elig = model.units.filter(u =>
          u.teacher === code &&
          (!w.stream || u.secs.some(sec => secStream(sec) === w.stream)));
        if (!elig.length) continue;
        groupList.push({ code: code, slot: w.slot, need: w.need, elig: elig });
      }
    }
    const groupOf = {};   // uid -> group indices
    for (let g = 0; g < groupList.length; g++) {
      for (const u of groupList[g].elig) (groupOf[u.id] = groupOf[u.id] || []).push(g);
    }

    // ---- global state
    const tPieces = new Int32Array(nT * P);
    const groupCount = new Int32Array(Math.max(1, groupList.length));
    const planByUnit = {};
    const plannedUnits = new Set();

    // per-attempt randomized targets for tight teachers + a PER-UNIT slot
    // allocation derived from them (coordinated by construction: the units'
    // budgets sum exactly to the teacher target, so any plan choices within
    // budget meet the global capacity). Group-needed slots are allocated to
    // the eligible units first.
    const target = new Int32Array(nT * P);
    const unitAlloc = {};   // uid -> {slot: k}
    for (let t = 0; t < nT; t++) {
      if (!tight[t]) continue;
      const slots = Array.from(allowedSlots[t] || []);
      if (!slots.length) continue;
      const base = Math.floor(totalPieces[t] / slots.length);
      let left = totalPieces[t] - base * slots.length;
      const dist = new Array(P).fill(0);
      for (const sl of slots) dist[sl] = base;
      const order2 = slots.slice();
      rng.shuffle(order2);
      for (let i = 0; i < order2.length && left > 0; i++) {
        const add = Math.min(left, D - base);
        dist[order2[i]] += add;
        left -= add;
      }
      while (left > 0) {
        const sl = order2[rng.int(order2.length)];
        if (dist[sl] < D) { dist[sl]++; left--; } else break;
      }
      for (let sl = 0; sl < P; sl++) target[t * P + sl] = dist[sl];

      // ---- per-unit allocation within the target
      const tUnits = model.units.filter(u => {
        for (const tt of teachersOf(u)) if (teacherIdx[tt] === t) return true;
        return false;
      });
      const rem = dist.slice();
      const allocOf = u => (unitAlloc[u.id] = unitAlloc[u.id] || new Array(P).fill(0));
      let failed = false;
      // group-needed slots first (eligible units)
      for (let g = 0; g < groupList.length && !failed; g++) {
        const grp = groupList[g];
        if (teacherIdx[grp.code] !== t) continue;
        let needLeft = grp.need;
        const elig = tUnits.filter(u => grp.elig.indexOf(u) >= 0);
        rng.shuffle(elig);
        for (const u of elig) {
          if (needLeft <= 0) break;
          const sd = unitSlotDomain(u, R, model);
          if (sd.indexOf(grp.slot) < 0) continue;
          const free = u.count - sumAlloc(allocOf(u));   // unallocated pieces of THIS unit
          const can = Math.min(needLeft, rem[grp.slot], free);
          if (can <= 0) continue;
          allocOf(u)[grp.slot] += can;
          rem[grp.slot] -= can;
          needLeft -= can;
        }
      }
      // remaining pieces: random greedy into remaining target capacity
      const rest = tUnits.slice();
      rng.shuffle(rest);
      for (const u of rest) {
        let c = u.count - (unitAlloc[u.id] ? sumAlloc(unitAlloc[u.id]) : 0);
        const sd = unitSlotDomain(u, R, model);
        const a = allocOf(u);
        while (c > 0) {
          const cand = sd.filter(sl => rem[sl] > 0);
          if (!cand.length) { failed = true; break; }
          const sl = cand[rng.int(cand.length)];
          const take = Math.min(c, rem[sl]);
          a[sl] += take;
          rem[sl] -= take;
          c -= take;
        }
        if (failed) break;
      }
      if (failed) return null;   // unlucky allocation — the attempt restarts
    }

    function sumAlloc(a) {
      let n = 0;
      for (let i = 0; i < a.length; i++) n += a[i];
      return n;
    }

    function capFor(ti, sl) { return tight[ti] ? target[ti * P + sl] : D; }

    function planFitsGlobally(u, plan) {
      const ua = unitAlloc[u.id];
      for (const [sl, k] of plan.cols) {
        // section column capacity (dual units: all their sections)
        for (const sec of u.secs) {
          if ((colUsed[sec][sl] || 0) + k > colCap[sec]) return false;
        }
        // per-unit slot budget for tight teachers (their global coordination)
        if (ua && k > (ua[sl] || 0)) return false;
        for (const t of teachersOf(u)) {
          const ti = teacherIdx[t];
          if (tPieces[ti * P + sl] + k > capFor(ti, sl)) return false;
        }
      }
      return true;
    }

    function applyPlanGlobally(u, plan, sign) {
      for (const [sl, k] of plan.cols) {
        for (const sec of u.secs) colUsed[sec][sl] += sign * k;
        for (const t of teachersOf(u)) tPieces[teacherIdx[t] * P + sl] += sign * k;
        if (groupOf[u.id]) {
          for (const g of groupOf[u.id]) {
            if (u.teacher + "|" + sl === groupList[g].code + "|" + groupList[g].slot) {
              groupCount[g] += sign * k;
            }
          }
        }
      }
      if (sign > 0) { planByUnit[u.id] = plan; plannedUnits.add(u.id); }
      else { delete planByUnit[u.id]; plannedUnits.delete(u.id); }
    }

    function groupFeasible() {
      for (let g = 0; g < groupList.length; g++) {
        const grp = groupList[g];
        if (groupCount[g] >= grp.need) continue;
        let remaining = 0;
        for (const u of grp.elig) {
          if (plannedUnits.has(u.id)) continue;
          remaining += u.count;
        }
        if (groupCount[g] + remaining < grp.need) return false;
      }
      return true;
    }

    const colUsed = {};
    for (const s of model.sections) colUsed[s.key] = new Array(P).fill(0);

    // generate ONE complete packing for a section that fits the current global
    // state (randomized DFS with unit-level MRV inside the section)
    function genSectionPacking(secKey, rng, nodeBudget) {
      const open = unitsOf[secKey].filter(u => !planByUnit[u.id]);
      let nodes = 0;

      // completion is checked on the GLOBAL colUsed (which already includes
      // dual-section units planned from the partner section)
      function completeCheck() {
        let total = 0;
        for (let s = 0; s < P; s++) {
          if (colUsed[secKey][s] > colCap[secKey]) return false;
          total += colUsed[secKey][s];
        }
        if (total !== fillOf[secKey]) return false;
        for (const s of boundaryCols[secKey]) {
          if (colUsed[secKey][s] !== colCap[secKey]) return false;
        }
        return true;
      }

      function orderPlans(u, list) {
        // engagement-group preference + boundary preference + tier + target-balance
        const groups = groupOf[u.id] || [];
        for (const p of list) {
          p._s = p.tier;
          for (const [sl, k] of p.cols) {
            // strong boost: this slot is a required engagement slot still below
            // its need (Assad/Babar ICS P1/P2/P4, Basit/Ishfaq P1...)
            for (const g of groups) {
              const grp = groupList[g];
              if (grp.slot === sl && groupCount[g] < grp.need) p._s -= 5;
            }
            if (boundaryCols[secKey].indexOf(sl) >= 0 && colUsed[secKey][sl] + k <= colCap[secKey]) p._s -= 2;
            for (const t of teachersOf(u)) {
              const ti = teacherIdx[t];
              if (tight[ti] && tPieces[ti * P + sl] + k > target[ti * P + sl] - 1) p._s += 3;
            }
          }
        }
        list.sort((a, b) => a._s - b._s);
        const headN = Math.max(1, Math.ceil(list.length * 0.3));
        const head = list.slice(0, headN);
        rng.shuffle(head);
        for (let i = 0; i < head.length; i++) list[i] = head[i];
      }

      function bt(k) {
        nodes++;
        if (nodes > nodeBudget) return null;
        if (k === open.length) {
          return completeCheck() ? {} : null;
        }
        // order within the section: BIG units first (they need full columns;
        // small units fill the gaps — the classic stage-1 heuristic), then MRV
        let bestU = null, bestList = null;
        const openLeft = open.filter(u => !planByUnit[u.id] && !assign[u.id]);
        if (!openLeft.length) {
          return completeCheck() ? {} : null;
        }
        openLeft.sort((a, b) => (b.count - a.count));
        for (const u of openLeft) {
          const fitting = plans[u.id].filter(p => planFitsGlobally(u, p));
          if (!fitting.length) return null;
          if (!bestList || fitting.length < bestList.length) {
            bestU = u; bestList = fitting;
            if (fitting.length === 1) break;
          }
        }
        if (!bestU) return null;
        orderPlans(bestU, bestList);
        for (const p of bestList) {
          assign[bestU.id] = p;
          applyPlanGlobally(bestU, p, 1);
          // prune early: engagement groups must remain satisfiable
          if (groupFeasible()) {
            const r = bt(k + 1);
            if (r) return r;
          }
          applyPlanGlobally(bestU, p, -1);
          delete assign[bestU.id];
        }
        return null;
      }

      const assign = {};
      const result = bt(0);
      if (!result) return null;
      const out = {};
      for (const uid in assign) out[uid] = assign[uid];
      return out;
    }

    // section order: inter first, then BS; randomized within groups
    const interSecs = model.sections.filter(s => s.level === "inter").map(s => s.key);
    const bsSecs = model.sections.filter(s => s.level !== "inter").map(s => s.key);
    rng.shuffle(interSecs);
    rng.shuffle(bsSecs);
    const order = interSecs.concat(bsSecs);

    let nodes = 0;
    let s1aborted = false;
    function bt(idx, retryBudget) {
      nodes++;
      if (s1aborted) return false;
      if (nodes > 400000) { s1aborted = true; return false; }
      if ((nodes & 63) === 0 && Date.now() - t0 > timeMs) { s1aborted = true; return false; }
      if (idx === order.length) return true;
      const secKey = order[idx];
      // single greedy pass per attempt (retries come from the outer restart
      // loop — cross-section retry trees explode combinatorially)
      for (let attempt = 0; attempt < retryBudget; attempt++) {
        const packing = genSectionPacking(secKey, rng, 25000);
        if (packing) {
          if (groupFeasible() && bt(idx + 1, retryBudget)) return true;
          for (const uid in packing) applyPlanGlobally(byIdOf(model, +uid), packing[uid], -1);
        }
        if (s1aborted) return false;
      }
      return false;
    }

    if (!bt(0, 3)) return null;
    return { planByUnit: planByUnit };
  }

  function byIdOf(model, id) {
    if (!model._byId) {
      model._byId = {};
      for (const u of model.units) model._byId[u.id] = u;
    }
    return model._byId[id];
  }

  // ------------------------------------------------------------------ phase 2
  function phase2(model, packed, dd, rng, nodeBudget, t0, timeMs) {
    const D = model.days, P = model.periods;
    const planByUnit = packed.planByUnit;
    const grids = {};
    for (const s of model.sections) {
      grids[s.key] = Array.from({ length: D }, () => new Array(P).fill(null));
    }
    const usedDays = {};      // uid -> Set (unit-global days; inter + pair units)
    const pairUsed = {};      // pairId -> Set
    const teacherDays = {};   // t -> Set (global coverage for min_days_engaged)
    const teacherColored = {}; // t -> pieces colored
    const teacherTotal = {};  // t -> total pieces
    const pairOf = {};
    for (const p of model.dayExclusive) for (const uid of p.units) pairOf[uid] = p;
    for (const u of model.units) {
      for (const t of teachersOf(u)) {
        teacherTotal[t] = (teacherTotal[t] || 0) + u.count;
      }
    }
    const minEngaged = {};
    for (const code in model.constraints) {
      const v = ((model.constraints[code] || {}).rules || {}).min_days_engaged;
      if (v) minEngaged[code] = v;
    }

    let nodes = 0;

    for (let s = 0; s < P; s++) {
      // edges: unit pieces in this slot
      const edges = [];
      for (const u of model.units) {
        for (const [sl, k] of planByUnit[u.id].cols) {
          if (sl === s) for (let i = 0; i < k; i++) edges.push(u);
        }
      }
      if (!edges.length) continue;
      const secDayUsed = {};   // sec -> Set (days used in THIS slot)
      const tDayUsed = {};     // t -> Set (days used in THIS slot)
      const remaining = new Set(edges.map((_, i) => i));
      const edgeDay = new Array(edges.length).fill(null);

      function edgeDays(u) { return dd[u.id]; }

      function dayOk(u, d) {
        if (dd[u.id].indexOf(d) < 0) return false;
        for (const sec of u.secs) {
          if ((secDayUsed[sec] || (secDayUsed[sec] = new Set())).has(d)) return false;
        }
        for (const t of teachersOf(u)) {
          if ((tDayUsed[t] || (tDayUsed[t] = new Set())).has(d)) return false;
          // hard day+slot bans (Atif/UmairAhmad/Irfan/Naeem-style)
          const tentry = (model.constraints[t] || {});
          if (hardnessOfJS(tentry, "forbidden_slots_on_days") < 100) continue;
          for (const e of ((tentry.rules || {}).forbidden_slots_on_days || [])) {
            if (daySet(e.days).has(d) && slotSet(e.slots).has(s)) return false;
          }
        }
        const p = pairOf[u.id];
        if (p) {
          if (usedDays[u.id] && usedDays[u.id].has(d)) return false;    // pair unit: own days distinct
          if (pairUsed[p.id] && pairUsed[p.id].has(d)) return false;    // disjoint from pair-mates
        } else if (u.level === "inter") {
          if (usedDays[u.id] && usedDays[u.id].has(d)) return false;
        }
        // consecutive days for inter 2/wk units
        if (u.level === "inter" && u.count === 2 &&
            (model.instructions.consecutiveFor2pw || {}).inter) {
          const known = usedDays[u.id];
          if (known && known.size === 1) {
            const d0 = known.values().next().value;
            if (Math.abs(d - d0) !== 1) return false;
          }
        }
        // min_days_engaged forward check
        for (const t of teachersOf(u)) {
          const need = minEngaged[t];
          if (!need) continue;
          const cov = teacherDays[t] || new Set();
          const newCov = cov.has(d) ? cov : new Set(cov).add(d);
          const remainingAfter = teacherTotal[t] - (teacherColored[t] || 0) - 1;
          if (need - newCov.size > remainingAfter) return false;
        }
        return true;
      }

      function applyEdge(u, d, sign) {
        if (sign > 0) {
          (secDayUsed[u.secs[0]] = secDayUsed[u.secs[0]] || new Set()).add(d);
          if (u.secs[1]) (secDayUsed[u.secs[1]] = secDayUsed[u.secs[1]] || new Set()).add(d);
          for (const t of teachersOf(u)) {
            (tDayUsed[t] = tDayUsed[t] || new Set()).add(d);
            (teacherDays[t] = teacherDays[t] || new Set()).add(d);
            teacherColored[t] = (teacherColored[t] || 0) + 1;
          }
          (usedDays[u.id] = usedDays[u.id] || new Set()).add(d);
          const p = pairOf[u.id];
          if (p) (pairUsed[p.id] = pairUsed[p.id] || new Set()).add(d);
          for (const sec of u.secs) grids[sec][d][s] = u.id;
        } else {
          // undo (rare path — recompute lazily is complex; use full recompute)
        }
      }

      // full-recompute undo: simpler and correct (edges per slot are few)
      function stateSnapshot() {
        return {
          secDayUsed: mapClone(secDayUsed), tDayUsed: mapClone(tDayUsed),
          usedDays: mapClone(usedDays), pairUsed: mapClone(pairUsed),
          teacherDays: mapClone(teacherDays), teacherColored: Object.assign({}, teacherColored),
          grids: gridsClone()
        };
      }
      function mapClone(m) {
        const out = {};
        for (const k in m) out[k] = new Set(m[k]);
        return out;
      }
      function gridsClone() {
        const out = {};
        for (const k in grids) out[k] = grids[k].map(r => r.slice());
        return out;
      }
      function stateRestore(snap) {
        for (const k of ["secDayUsed", "tDayUsed", "usedDays", "pairUsed", "teacherDays"]) {
          const target = { secDayUsed: secDayUsed, tDayUsed: tDayUsed, usedDays: usedDays,
                           pairUsed: pairUsed, teacherDays: teacherDays }[k];
          for (const key in target) delete target[key];
          Object.assign(target, snap[k]);
        }
        for (const k in teacherColored) delete teacherColored[k];
        Object.assign(teacherColored, snap.teacherColored);
        for (const k in grids) grids[k] = snap.grids[k];
      }

      function color() {
        nodes++;
        if (nodes > nodeBudget) return "BUDGET";
        if ((nodes & 127) === 0 && Date.now() - t0 > timeMs) return "BUDGET";
        if (remaining.size === 0) return "OK";
        // MRV: uncolored edge with fewest allowed days
        let bestE = -1, bestAllowed = null;
        for (const e of remaining) {
          const u = edges[e];
          const al = edgeDays(u).filter(d => dayOk(u, d));
          if (al.length === 0) return null;
          if (bestAllowed === null || al.length < bestAllowed.length) {
            bestE = e; bestAllowed = al;
            if (al.length === 1) break;
          }
        }
        rng.shuffle(bestAllowed);
        for (const d of bestAllowed) {
          const u = edges[bestE];
          const snap = stateSnapshot();
          applyEdge(u, d, 1);
          remaining.delete(bestE);
          const r = color();
          if (r === "OK") return "OK";
          remaining.add(bestE);
          stateRestore(snap);
          if (r === "BUDGET") return "BUDGET";
        }
        return null;
      }

      if (color() !== "OK") return null;
    }

    // materialize check: every unit placed with its full count
    for (const u of model.units) {
      let cnt = 0;
      for (const sec of u.secs) {
        for (let d = 0; d < D; d++) for (let s = 0; s < P; s++) {
          if (grids[sec][d][s] === u.id) { cnt++; break; }
        }
      }
      if (u.secs.length === 2) {
        // dual unit: count once (identical cells in both sections)
        cnt = 0;
        const g = grids[u.secs[0]];
        for (let d = 0; d < D; d++) for (let s = 0; s < P; s++) if (g[d][s] === u.id) cnt++;
      }
      if (cnt !== u.count) return null;
    }
    return grids;
  }

  // ------------------------------------------------------------- conversion
  function gridsKey(grids) {
    const parts = [];
    for (const key of Object.keys(grids).sort()) {
      for (const row of grids[key]) for (const uid of row) parts.push(uid === null || uid === undefined ? "." : uid);
    }
    return parts.join(",");
  }

  // Per-section display timetable: cells of [course, teacherDisplay]; free BS
  // cells become ["Library Work", ""]. displayOf: code -> display name.
  function modelToTimetable(grids, model, displayOf) {
    const disp = displayOf || (c => c);
    const byId = {};
    for (const u of model.units) byId[u.id] = u;
    const out = {};
    for (const section of model.sections) {
      const g = grids[section.key];
      const rows = [];
      for (let d = 0; d < g.length; d++) {
        const row = [];
        for (let s = 0; s < g[d].length; s++) {
          const uid = g[d][s];
          if (uid === null || uid === undefined) { row.push(["Library Work", ""]); continue; }
          const u = byId[uid];
          const cname = u.courseBySec[section.key] || Object.values(u.courseBySec)[0];
          const tname = u.group ? u.members.map(m => disp(m)).join(" / ") : disp(u.teacher);
          row.push([cname, tname]);
        }
        rows.push(row);
      }
      out[section.key] = rows;
    }
    return out;
  }

  return {
    PENALTIES: PENALTIES,
    contextToModel: contextToModel,
    unitSlotDomain: unitSlotDomain, unitDayDomain: unitDayDomain,
    buildUnitPlans: buildUnitPlans,
    evaluate: evaluate, shuffleScore: shuffleScore, poolSelection: poolSelection,
    generateContext: generateContext, modelToTimetable: modelToTimetable
  };
});
