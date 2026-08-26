/*
 * canonical.js — the canonical IMPCC data model: load, validate, adapt.
 *
 * The canonical dataset (data.js / IMPCC_DATA, generated from
 * data/canonical.json — see canonical_model.md) is the single source of truth
 * for the college's timetable data:
 *
 *   faculty directory (codes, names, levels, aliases)
 *   subjects registry
 *   per-population allocations  (inter-1 · bs-1 · inter-2)
 *   parallel groups             (either/or blocks, both teachers occupied)
 *   combined classes            (co-taught section pairs at identical slots)
 *   faculty constraints         (person-level, rule vocabulary + natural text)
 *   general instructions        (structured, per population, natural text kept)
 *
 * Adapters convert a population's allocation into the exact formats the
 * solvers already consume:
 *   IMPCC_CANONICAL.solverAllocation("inter-1")
 *     -> { "<SECTION>": { subjects: [{subject, teacher, periods}, ...] }, ... }
 *        (the external allocation form — full teacher display names; the
 *         either/or parallel pair is rendered as "A / B")
 *   IMPCC_CANONICAL.solverConstraints()
 *     -> { "<code>": { name, rules } }   (the constraints edits model)
 *
 * Teacher name resolution goes through the directory (aliases included), and
 * IMPCC_SOLVER.extendTeachers() registers any canonical faculty the solver's
 * built-in roster does not know yet, so new members resolve to stable codes.
 *
 * Exposes IMPCC_CANONICAL; also require()-able in Node.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.IMPCC_CANONICAL = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  let DATA = null;

  // ------------------------------------------------------------ loading
  function load(data) {
    const issues = validate(data);
    if (issues.length) throw new Error("canonical data invalid: " + issues.join("; "));
    DATA = data;
    return DATA;
  }
  function get() {
    if (!DATA) {
      if (typeof IMPCC_DATA !== "undefined") return load(IMPCC_DATA);
      throw new Error("canonical data not loaded — include data.js or call load()");
    }
    return DATA;
  }

  // ------------------------------------------------------------ validation
  function validate(data) {
    const issues = [];
    if (!data || typeof data !== "object") return ["data must be an object"];
    const codes = new Set((data.faculty || []).map(f => f.code));
    if ((data.faculty || []).some(f => !f.code || !f.name))
      issues.push("every faculty member needs code + name");
    const dup = {};
    for (const f of (data.faculty || [])) {
      if (dup[f.code]) issues.push("duplicate faculty code " + f.code);
      dup[f.code] = 1;
    }
    const subjects = new Set(data.subjects || []);
    const pops = data.populations || {};
    for (const pid of ["inter-1", "bs-1", "inter-2"]) {
      if (!pops[pid]) { issues.push("missing population " + pid); continue; }
      const seen = new Set();
      for (const sec of (pops[pid].sections || [])) {
        if (seen.has(sec.key)) issues.push(pid + ": duplicate section " + sec.key);
        seen.add(sec.key);
        for (const e of (sec.entries || [])) {
          if (!e.course) issues.push(sec.key + ": entry without course");
          if (!(e.periods >= 1 && e.periods <= 8))
            issues.push(sec.key + " " + e.course + ": periods must be 1..8");
          if (e.subject && !subjects.has(e.subject))
            issues.push(sec.key + " " + e.course + ": unknown subject " + e.subject);
          if (!e.parallelGroup && !codes.has(e.teacher))
            issues.push(sec.key + " " + e.course + ": unknown teacher " + e.teacher);
        }
      }
    }
    for (const pg of (data.parallelGroups || [])) {
      for (const t of (pg.teachers || []))
        if (!codes.has(t)) issues.push("parallelGroup " + pg.id + ": unknown teacher " + t);
    }
    // day-exclusive pairs: each course must exist in at least one section of
    // its population; wherever both co-exist the rule applies
    for (const dx of (data.dayExclusivePairs || [])) {
      for (const course of (dx.courses || [])) {
        let found = false;
        for (const pid in (data.populations || {})) {
          for (const sec of ((data.populations[pid] || {}).sections || [])) {
            if ((sec.entries || []).some(e => e.course === course)) { found = true; break; }
          }
          if (found) break;
        }
        if (!found) issues.push("dayExclusivePair " + dx.id + ": course not found " + course);
      }
    }
    for (const cc of (data.combinedClasses || [])) {
      for (const side of ["a", "b"]) {
        const ref = cc[side];
        const pop = (pops["bs-1"] || {}).sections || [];
        const sec = pop.find(s => s.key === ref.section);
        if (!sec || !(sec.entries || []).some(e => e.course === ref.course))
          issues.push("combined " + cc.id + ": missing entry " + ref.section + " / " + ref.course);
      }
    }
    for (const code in (data.constraints || {})) {
      if (!codes.has(code)) issues.push("constraints: unknown teacher code " + code);
    }
    return issues;
  }

  // ------------------------------------------------------------ directory
  function directory() { return get().faculty; }
  function nameToCode() {
    const map = {};
    for (const f of directory()) {
      map[f.name] = f.code;
      for (const a of (f.aliases || [])) map[a] = f.code;
    }
    return map;
  }
  function codeOf(name) { return nameToCode()[name] || null; }
  function displayName(code) {
    const f = directory().find(x => x.code === code);
    return f ? f.name : code;
  }

  // ------------------------------------------------------------ adapters
  // A population's allocation -> the solver's EXTERNAL allocation form
  // (full display names; parallel pair rendered "A / B").
  function solverAllocation(populationId) {
    const data = get();
    const pop = (data.populations[populationId] || {}).sections || [];
    const out = {};
    for (const sec of pop) {
      const subjects = [];
      for (const e of sec.entries) {
        let teacher;
        if (e.parallelGroup) {
          const pg = data.parallelGroups.find(g => g.id === e.parallelGroup);
          teacher = pg.teachers.map(displayName).join(" / ");
        } else {
          teacher = displayName(e.teacher);
        }
        subjects.push({ subject: e.course, teacher: teacher, periods: e.periods });
      }
      out[sec.key] = { subjects: subjects };
    }
    return out;
  }

  // Faculty constraints -> the solver's edits-model form (person-level).
  function solverConstraints() {
    const out = {};
    for (const code in (get().constraints || {})) {
      const c = get().constraints[code];
      out[code] = { name: c.name, rules: c.rules, soft: c.soft || [] };
    }
    return out;
  }

  // Register canonical faculty the solver doesn't know (new members) so that
  // full display names resolve to codes inside IMPCC_SOLVER.
  function extendSolver(SOLVER) {
    if (!SOLVER || typeof SOLVER.extendTeachers !== "function") return false;
    const extra = {};
    for (const f of directory()) extra[f.code] = f.name;
    SOLVER.extendTeachers(extra);
    return true;
  }

  // ------------------------------------------------------------ helpers
  function sectionFill(populationId, sectionKey) {
    // Teaching cells a section occupies on the active grid (either/or groups
    // count once). Compare against days*periods for free-cell analysis.
    const data = get();
    const sec = ((data.populations[populationId] || {}).sections || [])
      .find(s => s.key === sectionKey);
    if (!sec) return null;
    let fill = 0;
    const counted = new Set();
    for (const e of sec.entries) {
      if (e.parallelGroup) {
        if (counted.has(e.parallelGroup)) continue;
        const pg = data.parallelGroups.find(g => g.id === e.parallelGroup);
        fill += pg.periods;
        counted.add(e.parallelGroup);
      } else {
        fill += e.periods;
      }
    }
    return fill;
  }

  function teacherLoad(teacherCode, populationIds) {
    // Periods/week for one teacher across the given populations (shift 1 =
    // ["inter-1", "bs-1"]). Either/or groups count for EVERY member teacher;
    // combined classes (co-taught pairs at identical slots) count ONCE per group.
    const data = get();
    let load = 0;
    const countedCombined = new Set();
    for (const pid of (populationIds || [])) {
      for (const sec of ((data.populations[pid] || {}).sections || [])) {
        for (const e of sec.entries) {
          if (e.parallelGroup) {
            const pg = data.parallelGroups.find(g => g.id === e.parallelGroup);
            if (pg.teachers.indexOf(teacherCode) >= 0) load += pg.periods;
          } else if (e.teacher === teacherCode) {
            if (e.combinedWith) {
              if (countedCombined.has(e.combinedWith)) continue;   // co-taught: occupied once
              countedCombined.add(e.combinedWith);
            }
            load += e.periods;
          }
        }
      }
    }
    return load;
  }

  // ------------------------------------------------- solve context builder
  function _pops() {
    if (typeof IMPCC_POPULATIONS !== "undefined") return IMPCC_POPULATIONS;
    if (typeof require === "function") {
      try { return require("./populations.js"); } catch (e) {}
    }
    throw new Error("populations registry not loaded - include populations.js before canonical.js");
  }

  function _populationLevel(pid) {
    const lvl = ((get().populations[pid] || {}).level);
    if (lvl) return lvl;
    return pid === "bs-1" ? "bs" : "inter";
  }

  // Collect the enabled general instructions of the given populations, by rule type.
  function _giRules(pids) {
    const data = get();
    const out = {};
    for (const pid of pids) {
      const list = (data.generalInstructions || {})[pid] || [];
      for (const gi of list) {
        if (gi.enabled === false) continue;
        (out[gi.type] = out[gi.type] || []).push(gi);
      }
    }
    return out;
  }

  // Build a solve context for ONE shift (shift 1: ["inter-1","bs-1"] jointly;
  // shift 2: ["inter-2"]). Mirrors canonical.py solver_context() exactly.
  function solverContext(populationIds) {
    const POPS = _pops();
    const pids = (populationIds || []).slice();
    const shifts = {};
    for (const p of pids) {
      const entry = POPS.POPULATIONS[p];
      if (entry) shifts[entry.shift] = true;
    }
    if (Object.keys(shifts).length !== 1) {
      throw new Error("a solve context spans exactly ONE shift (shift 1 = inter-1 + bs-1; shift 2 = inter-2)");
    }
    const cfg = POPS.POPULATIONS[pids[0]].config;
    const grid = { days: cfg.days, periods: cfg.periods };

    const gi = _giRules(pids);
    const data = get();

    const sections = {};
    const sectionMeta = {};
    for (const pid of pids) {
      const alloc = solverAllocation(pid);
      Object.assign(sections, alloc);
      const level = _populationLevel(pid);
      for (const key in alloc) sectionMeta[key] = { level: level, offDays: [], firstLast: false, pop: pid };
    }

    const noSame = { inter: !!gi.no_same_subject_same_day, bs: !gi.same_subject_same_day_allowed };
    const consec = { inter: !!gi.consecutive_days_for_2pw, bs: false };
    for (const e of (gi.section_off_days || [])) {
      for (const key of ((e.params || {}).sections || [])) {
        if (sectionMeta[key]) sectionMeta[key].offDays = sectionMeta[key].offDays.concat((e.params || {}).days || []);
      }
    }
    if (gi.first_last_period_occupied) {
      for (const key in sectionMeta) if (sectionMeta[key].level === "bs") sectionMeta[key].firstLast = true;
    }

    return {
      grid: grid,
      sections: sections,
      sectionMeta: sectionMeta,
      relationships: {
        parallelGroups: data.parallelGroups || [],
        dayExclusivePairs: data.dayExclusivePairs || [],
        combinedClasses: data.combinedClasses || []
      },
      instructions: {
        noSameSubjectSameDay: noSame,
        consecutiveFor2pw: consec,
        nonOverriding: (gi.non_overriding || []).filter(e => e.params).map(e => ({
          sections: e.params.sections, subjects: e.params.subjects })),
        subjectForbiddenDays: (gi.subject_forbidden_days || []).filter(e => e.params).map(e => ({
          subject: e.params.subject, days: e.params.days || [], scope: e.params.scope })),
        subjectForbiddenSlotDays: (gi.subject_forbidden_slots_on_days || []).filter(e => e.params).map(e => ({
          subject: e.params.subject, days: e.params.days || [], slots: e.params.slots || [], scope: e.params.scope,
          subjects: e.params.subjects, sections: e.params.sections, teachers: e.params.teachers })),
        softIndividualSpread: !!gi.soft_individual_spread
      },
      constraints: solverConstraints(),
      teacherCodes: nameToCode()
    };
  }

  return {
    load: load, get: get, validate: validate,
    directory: directory, nameToCode: nameToCode, codeOf: codeOf, displayName: displayName,
    solverAllocation: solverAllocation, solverConstraints: solverConstraints,
    solverContext: solverContext,
    extendSolver: extendSolver, sectionFill: sectionFill, teacherLoad: teacherLoad,
    POPULATIONS: ["inter-1", "bs-1", "inter-2"],
    SHIFT1: ["inter-1", "bs-1"], SHIFT2: ["inter-2"]
  };
});
