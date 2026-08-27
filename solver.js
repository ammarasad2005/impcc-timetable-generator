/*
 * solver.js — IMPCC timetable generator (in-browser).
 *
 * A faithful JavaScript port of the CP-SAT model in cp_solver.py (same data,
 * same slot/day domains, same structural rules, same validator and the same
 * shuffle score). The search is a randomized backtracking solver with
 * minimum-remaining-values (MRV) ordering and forward checking. It runs fully
 * client-side — no server, no precomputed data.
 *
 * The timetable grid is parameterized: generate({days, periods}) selects the
 * active grid (capacity 6 days x 8 periods — see populations.js). The default
 * is the historical 5x5 so existing callers behave exactly as before. Sections
 * must fill the active grid exactly (partial fill arrives with the BS support).
 *
 * Exposes IMPCC_SOLVER.generate(opts); also require()-able in Node.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.IMPCC_SOLVER = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // ------------------------------------------------------------- grid
  // Capacity (reserved maximum): 6 days x 8 periods (see populations.js).
  // The ACTIVE grid is data: generate({days, periods}) selects it. The default
  // remains the historical 5 x 5 so every existing caller is unaffected.
  const DAY_NAMES = ["MON", "TUE", "WED", "THU", "FRI", "SAT"];
  const PERIOD_LABELS = ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8"];
  let DAYS = DAY_NAMES.slice(0, 5);        // active day names (set by generate)
  let SLOTS = PERIOD_LABELS.slice(0, 5);   // active period labels (set by generate)
  let D = 5;                               // active day count
  let P = 5;                               // active period count

  // ---------------------------------------------------------------- data
  let SECTIONS = [
    { key: "I.COM-I-A", subs: [
      ["English", "UmairAbid", 4], ["Urdu", "Basit", 4],
      ["Tarjama-tul-Quran", "V1", 2], ["Islamic Education", "V2", 2],
      ["Principles of Accounting", "Sikhani", 5],
      ["Principles of Economics", "Yasir", 3],
      ["Principles of Commerce", "Naeem", 3],
      ["Business Mathematics", "Assad", 2]] },
    { key: "I.COM-I-B", subs: [
      ["English", "UmairAbid", 4], ["Urdu", "Basit", 4],
      ["Tarjama-tul-Quran", "V1", 2], ["Islamic Education", "V2", 2],
      ["Principles of Accounting", "Sikhani", 5],
      ["Principles of Economics", "Yasir", 3],
      ["Principles of Commerce", "Naeem", 3],
      ["Business Mathematics", "Assad", 2]] },
    { key: "I.COM-I-C", subs: [
      ["English", "UmairAbid", 4], ["Urdu", "Basit", 4],
      ["Tarjama-tul-Quran", "V1", 2], ["Islamic Education", "V2", 2],
      ["Principles of Accounting", "Sikhani", 5],
      ["Principles of Economics", "Yasir", 3],
      ["Principles of Commerce", "Millat", 3],
      ["Business Mathematics", "Najam", 2]] },
    { key: "I.COM-II-A", subs: [
      ["English", "Amir", 4], ["Urdu", "Ehsam", 4],
      ["Tarjama-tul-Quran", "V1", 2], ["Pakistan Studies", "Jilani", 2],
      ["Principles of Accounting", "Naeem", 5],
      ["Commercial Geography", "Husnul", 3],
      ["Computer Studies", "Faisal", 3],
      ["Statistics", "Tanveer", 2]] },
    { key: "I.COM-II-B", subs: [
      ["English", "Amir", 4], ["Urdu", "Ehsam", 4],
      ["Tarjama-tul-Quran", "V1", 2], ["Pakistan Studies", "Jilani", 2],
      ["Principles of Accounting", "Naeem", 5],
      ["Commercial Geography", "Husnul", 3],
      ["Banking", "Millat", 3],
      ["Statistics", "Tanveer", 2]] },
    { key: "I.COM-II-C", subs: [
      ["English", "Amir", 4], ["Urdu", "Ehsam", 4],
      ["Tarjama-tul-Quran", "V1", 2], ["Pakistan Studies", "Jilani", 2],
      ["Principles of Accounting", "Naeem", 5],
      ["Commercial Geography", "Husnul", 3],
      ["Banking", "Millat", 3],
      ["Statistics", "Tanveer", 2]] },
    { key: "ICS-I-A", subs: [
      ["English", "Noor", 4], ["Urdu", "Rauf", 4],
      ["Tarjama-tul-Quran", "V2", 2], ["Islamic Education", "V1", 2],
      ["Computer Science", "Babar", 4], ["Mathematics", "Assad", 5],
      ["Physics", "V3", 4]] },
    { key: "ICS-I-B", subs: [
      ["English", "Noor", 4], ["Urdu", "Rauf", 4],
      ["Tarjama-tul-Quran", "V2", 2], ["Islamic Education", "V1", 2],
      ["Computer Science", "Babar", 4], ["Mathematics", "Assad", 5],
      ["Physics", "V3", 4]] },
    { key: "ICS-I-C", subs: [
      ["English", "Noor", 4], ["Urdu", "Rauf", 4],
      ["Tarjama-tul-Quran", "V2", 2], ["Islamic Education", "V1", 2],
      ["Computer Science", "Babar", 4], ["Mathematics", "Assad", 5],
      ["Statistics", "Ishfaq", 4]] },
    { key: "ICS-II-A", subs: [
      ["English", "UmairAbid", 4], ["Urdu", "Rauf", 4],
      ["Tarjama-tul-Quran", "V2", 2], ["Pakistan Studies", "Jilani", 2],
      ["Computer Science", "Faisal", 4], ["Mathematics", "Najam", 5],
      ["Statistics", "Ishfaq", 4]] },
    { key: "ICS-II-B", subs: [
      ["English", "UmairAbid", 4], ["Urdu", "Rauf", 4],
      ["Tarjama-tul-Quran", "V2", 2], ["Pakistan Studies", "Jilani", 2],
      ["Computer Science", "Faisal", 4], ["Mathematics", "Najam", 5],
      ["Economics/Statistics", "PARALLEL", 4]] }
  ];

  // The default course allocation (deep copy). `generate({sections})` can override it.
  const DEFAULT_SECTIONS = JSON.parse(JSON.stringify(SECTIONS));

  const TEACHER_FULL = {
    Sikhani: "Prof. M. Waseem Sikhani",
    Naeem: "Prof. Muhammad Naeem",
    UmairAbid: "Prof. Syed Umair Abid",
    Rauf: "Prof. Abdul Rauf",
    Assad: "Prof. Syed Assad Abbas",
    Basit: "Prof. Abdul Basit",
    Najam: "Prof. Najam us Saqib",
    Amir: "Prof. Amir Rasheed",
    Ehsam: "Prof. Ehsam Ullah Baig",
    Noor: "Prof. Noor Muhammad",
    Babar: "Prof. Babar Jahangir",
    Faisal: "Prof. Faisal Bashir",
    Jilani: "Prof. Ghulam Jilani",
    Yasir: "Prof. Dr. Yasir Kareem",
    Millat: "Prof. Millat Khan",
    Husnul: "Prof. Husnul Amin",
    Ishfaq: "Prof. Ishfaq Ahmed",
    NaeemAsghar: "Prof. Naeem Asghar",
    Tanveer: "Prof. Tanveer Ahmed",
    V1: "Visiting-1", V2: "Visiting-2", V3: "Visiting-3",
    PARALLEL: "Prof. Naeem Asghar / Prof. Ishfaq Ahmed"
  };

  const ALLOWED = {
    Yasir: [0, 1, 3],
    Amir: [1, 2, 3],
    Husnul: [1, 2, 3],
    Millat: [1, 2, 3, 4],
    Basit: [0, 1, 2, 3],
    Tanveer: [0, 1, 2],
    NaeemAsghar: [2, 3, 4],
    PARALLEL: [2, 3]
  };

  const RULES = {
    "Prof. Muhammad Naeem": "Mon P1 & P2 free",
    "Prof. Syed Assad Abbas": "ICS fills P1 & P2 daily · Bus-Math in P3 · no I.Com Friday",
    "Prof. Babar Jahangir": "ICS fills P1 & P2 daily",
    "Prof. Ishfaq Ahmed": "P1 ≥ 4 days · never P5",
    "Prof. Dr. Yasir Kareem": "only P1, P2, P4",
    "Prof. Abdul Basit": "P1 ≥ 4 days · never P5 · no day off",
    "Prof. Amir Rasheed": "never P1 · never P5",
    "Prof. Husnul Amin": "never P1 · never P5",
    "Prof. Millat Khan": "never P1",
    "Prof. Naeem Asghar": "never P1 · never P2",
    "Prof. Tanveer Ahmed": "Thu & Fri only · P1–P3",
    "Visiting-1": "placeholder visiting faculty",
    "Visiting-2": "placeholder visiting faculty",
    "Visiting-3": "placeholder visiting faculty"
  };

  // --------------------------------------------------- constraints (data)
  const SLOT_OF = { P1:0, P2:1, P3:2, P4:3, P5:4 };
  const DAY_OF  = { MON:0, TUE:1, WED:2, THU:3, FRI:4 };

  // Faculty constraints as DATA (see constraints_schema.md). Keyed by teacher code.
  // Editing these (or passing custom constraints to generate()) changes behaviour.
  const DEFAULT_CONSTRAINTS = {
    Yasir:  { name:"Prof. Dr. Yasir Kareem", rules:{ allowed_slots:["P1","P2","P4"] } },
    Amir:   { name:"Prof. Amir Rasheed",     rules:{ forbidden_slots:["P1","P5"] } },
    Husnul: { name:"Prof. Husnul Amin",      rules:{ forbidden_slots:["P1","P5"] } },
    Millat: { name:"Prof. Millat Khan",      rules:{ forbidden_slots:["P1"] } },
    Basit:  { name:"Prof. Abdul Basit",      rules:{ forbidden_slots:["P5"],
              min_days_in_slot:[{slot:"P1",min_days:4}], min_days_engaged:5 } },
    NaeemAsghar:{ name:"Prof. Naeem Asghar", rules:{ forbidden_slots:["P1","P2"] } },
    Tanveer:{ name:"Prof. Tanveer Ahmed",    rules:{ allowed_days:["THU","FRI"], allowed_slots:["P1","P2","P3"] } },
    Ishfaq: { name:"Prof. Ishfaq Ahmed",     rules:{ forbidden_slots:["P5"],
              min_days_in_slot:[{slot:"P1",min_days:4}] } },
    Naeem:  { name:"Prof. Muhammad Naeem",   rules:{
              forbidden_slots_on_days:[{days:["MON"],slots:["P1","P2"]}],
              subject_slots:[{subject:"Principles of Accounting",slots:["P3","P4","P5"]},
                             {subject:"Principles of Commerce",slots:["P1","P2"]}],
              subject_forbidden_days:[{subject:"Principles of Commerce",days:["MON"]}] } },
    Assad:  { name:"Prof. Syed Assad Abbas", rules:{
              subject_slots:[{subject:"Business Mathematics",slots:["P3"]},
                             {subject:"Mathematics",slots:["P1","P2","P4","P5"]}],
              subject_forbidden_days:[{subject:"Business Mathematics",days:["FRI"]}],
              stream_slots_required:[{stream:"ICS",slots:["P1","P2"]}] } },
    Babar:  { name:"Prof. Babar Jahangir",   rules:{ stream_slots_required:[{stream:"ICS",slots:["P1","P2"]}] } }
  };

  const NAME_TO_CODE = {};
  for (const code in TEACHER_FULL) if (code !== "PARALLEL") NAME_TO_CODE[TEACHER_FULL[code]] = code;

  // Register additional faculty (e.g. the canonical directory's new members)
  // so full display names resolve to their codes. Teaching roster as DATA.
  function extendTeachers(map) {
    for (const code in (map || {})) {
      if (code === "PARALLEL" || TEACHER_FULL[code]) continue;
      TEACHER_FULL[code] = map[code];
      NAME_TO_CODE[map[code]] = code;
    }
    return TEACHER_FULL;
  }

  // Admin rename (e.g. visiting placeholder "Visiting-1" -> "Prof. Green"):
  // keep ONE identity — mutate BOTH maps in place so every existing reference
  // (constraints keyed by name or code, sheets, tweak payloads) keeps binding.
  function renameTeacher(oldName, newName) {
    const code = NAME_TO_CODE[oldName];
    if (!code || code === "PARALLEL") return null;
    if (NAME_TO_CODE[newName] && NAME_TO_CODE[newName] !== code) return null;
    delete NAME_TO_CODE[oldName];
    NAME_TO_CODE[newName] = code;
    TEACHER_FULL[code] = newName;
    return code;
  }

  const _slotSet = a => new Set((a||[]).map(x => SLOT_OF[x]));
  const _daySet  = a => new Set((a||[]).map(x => DAY_OF[x]));

  function resolveConstraints(C){
    // Start from the college defaults, then merge per-teacher overrides.
    // An override carries `edits` (rule key -> value). A value of null REMOVES that
    // rule, so defaults can be deleted, not just added to. Legacy `rules` is treated
    // as edits (keys added/overwritten).
    const out = {};
    for (const code in DEFAULT_CONSTRAINTS)
      out[code] = { name: DEFAULT_CONSTRAINTS[code].name,
                    rules: JSON.parse(JSON.stringify(DEFAULT_CONSTRAINTS[code].rules)) };
    if (C) for (const k in C) {
      const code = NAME_TO_CODE[k] || k;
      const entry = C[k] || {};
      const edits = entry.edits || entry.rules || {};
      const base = (out[code] && out[code].rules) ? JSON.parse(JSON.stringify(out[code].rules)) : {};
      for (const rk in edits) {
        const v = edits[rk];
        if (v === null || v === undefined) delete base[rk]; else base[rk] = v;
      }
      // carry the `soft` list (rule keys enforced as documented soft violations,
      // not hard rejections) so the context engine can honour it; override wins,
      // else inherit the base entry's list.
      const soft = entry.soft || (out[code] && out[code].soft) || [];
      out[code] = { name: entry.name || (out[code] && out[code].name) || k, rules: base };
      if (soft.length) out[code].soft = soft.slice();
      // v2.1 hardness map: defaults merged with the override (per-key, clamped)
      const hardM = Object.assign({},
        (DEFAULT_CONSTRAINTS[code] && DEFAULT_CONSTRAINTS[code].hardness) || {},
        entry.hardness || {});
      const hard = {};
      for (const hk in hardM) {
        if (!(hk in base)) continue;
        const n = parseInt(hardM[hk], 10);
        if (isNaN(n)) continue;
        hard[hk] = Math.max(0, Math.min(100, n));
      }
      if (Object.keys(hard).length) out[code].hardness = hard;
    }
    return out;
  }

  let UNITS = [];
  function buildUnits(secs) {
    const out = [];
    for (const sec of secs) {
      for (const [subject, teacher, count] of sec.subs) {
        out.push({ sec: sec.key, subject, teacher, count });
      }
    }
    return out;
  }
  UNITS = buildUnits(SECTIONS);

  // Convert the external allocation form (full teacher names) into solver sections.
  // External form: { "I.COM-I-A": { "subjects": [ {subject, teacher, periods}, ... ] }, ... }
  function normalizeSections(alloc) {
    if (!alloc) return JSON.parse(JSON.stringify(DEFAULT_SECTIONS));
    const out = [];
    for (const sec of DEFAULT_SECTIONS) {
      const a = alloc[sec.key];
      let subs;
      if (a && Array.isArray(a.subjects)) {
        subs = a.subjects.map(e => {
          const code = (typeof e.teacher === "string" && e.teacher.indexOf("/") >= 0)
            ? "PARALLEL"
            : (NAME_TO_CODE[e.teacher] || e.teacher || "Staff");
          return [e.subject, code, Math.max(1, Math.min(5, e.periods | 0))];
        });
      } else {
        subs = JSON.parse(JSON.stringify(sec.subs));
      }
      out.push({ key: sec.key, subs });
    }
    return out;
  }

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
      choice(arr) { return arr[Math.floor(r() * arr.length)]; },
      shuffle(arr) {
        for (let i = arr.length - 1; i > 0; i--) {
          const j = Math.floor(r() * (i + 1));
          [arr[i], arr[j]] = [arr[j], arr[i]];
        }
        return arr;
      }
    };
  }
  function combinations(arr, k) {
    const out = [];
    const idx = [];
    function rec(start) {
      if (idx.length === k) { out.push(idx.slice()); return; }
      for (let i = start; i < arr.length; i++) { idx.push(arr[i]); rec(i + 1); idx.pop(); }
    }
    rec(0);
    return out;
  }

  // ------------------------------------------------------------- domains
  function slotDomainT(t, subj, R) {
    if (t === "PARALLEL") return [2, 3];                       // structural option block
    const ent = R && R[t] ? R[t] : null;
    const r = ent && ent.rules;
    const _hard = k => !ent || hardnessOfFac(ent, k) === 100;
    if (r && r.subject_slots && _hard("subject_slots")) {
      const m = r.subject_slots.find(e => e.subject === subj);
      if (m) return m.slots.map(x => SLOT_OF[x]);
    }
    let dom = [];
    for (let i = 0; i < P; i++) dom.push(i);
    if (r && r.allowed_slots && _hard("allowed_slots"))
      dom = dom.filter(x => _slotSet(r.allowed_slots).has(x));
    if (r && r.forbidden_slots && _hard("forbidden_slots"))
      dom = dom.filter(x => !_slotSet(r.forbidden_slots).has(x));
    return dom;
  }
  function slotDomain(u, R) { return slotDomainT(u.teacher, u.subject, R); }
  function dayDomainT(t, subj, R) {
    const ent = R && R[t] ? R[t] : null;
    const r = ent && ent.rules;
    const _hard = k => !ent || hardnessOfFac(ent, k) === 100;
    let dom = [];
    for (let i = 0; i < D; i++) dom.push(i);
    if (r && r.allowed_days && _hard("allowed_days"))
      dom = dom.filter(d => _daySet(r.allowed_days).has(d));
    if (r && r.forbidden_days && _hard("forbidden_days"))
      dom = dom.filter(d => !_daySet(r.forbidden_days).has(d));
    if (r && r.subject_forbidden_days && _hard("subject_forbidden_days")) {
      const m = r.subject_forbidden_days.find(e => e.subject === subj);
      if (m) dom = dom.filter(d => !_daySet(m.days).has(d));
    }
    return dom;
  }
  function dayDomain(u, R) { return dayDomainT(u.teacher, u.subject, R); }

  // -------------------------------------------------- packings (Stage 1)
  function enumeratePackings(subjs, R) {
    const slotUsed = new Array(P).fill(0);
    const out = [];
    const cur = subjs.map(() => null);
    function rec(idx) {
      if (idx === subjs.length) {
        if (slotUsed.every(v => v === D)) out.push(cur.map(c => c.slice()));
        return;
      }
      const [subject, teacher, count] = subjs[idx];
      const sd = slotDomainT(teacher, subject, R);
      for (const s of sd) {
        if (slotUsed[s] + count <= D) {
          slotUsed[s] += count; cur[idx] = [{ slot: s, k: count }];
          rec(idx + 1); slotUsed[s] -= count;
        }
      }
      if (count === 3) {
        for (const s1 of sd) for (const s2 of sd) {
          if (s2 <= s1) continue;
          if (slotUsed[s1] + 2 <= D && slotUsed[s2] + 1 <= D) {
            slotUsed[s1] += 2; slotUsed[s2] += 1;
            cur[idx] = [{ slot: s1, k: 2 }, { slot: s2, k: 1 }];
            rec(idx + 1); slotUsed[s1] -= 2; slotUsed[s2] -= 1;
          }
        }
        for (const s1 of sd) for (const s2 of sd) for (const s3 of sd) {
          if (s2 <= s1 || s3 <= s2) continue;
          if (slotUsed[s1] + 1 <= D && slotUsed[s2] + 1 <= D && slotUsed[s3] + 1 <= D) {
            slotUsed[s1]++; slotUsed[s2]++; slotUsed[s3]++;
            cur[idx] = [{ slot: s1, k: 1 }, { slot: s2, k: 1 }, { slot: s3, k: 1 }];
            rec(idx + 1); slotUsed[s1]--; slotUsed[s2]--; slotUsed[s3]--;
          }
        }
      } else if (count === 2) {
        for (const s1 of sd) for (const s2 of sd) {
          if (s2 <= s1) continue;
          if (slotUsed[s1] + 1 <= D && slotUsed[s2] + 1 <= D) {
            slotUsed[s1]++; slotUsed[s2]++;
            cur[idx] = [{ slot: s1, k: 1 }, { slot: s2, k: 1 }];
            rec(idx + 1); slotUsed[s1]--; slotUsed[s2]--;
          }
        }
      }
    }
    rec(0);
    return out;
  }

  function makeGroups(R) {
    const byT = {};
    for (let i = 0; i < UNITS.length; i++) {
      const t = UNITS[i].teacher;
      (byT[t] = byT[t] || []).push(i);
    }
    const groups = [];
    for (const code in (R || {})) {
      const rules = (R[code] && R[code].rules) || {};
      if (rules.min_days_in_slot) {
        for (const e of rules.min_days_in_slot) {
          const units = (byT[code] || []).slice();
          if (units.length) groups.push({ units, needs: [SLOT_OF[e.slot]] });
        }
      }
      if (rules.stream_slots_required) {
        for (const e of rules.stream_slots_required) {
          const units = (byT[code] || []).filter(i => {
            const key = UNITS[i].sec;
            return e.stream === "ICS" ? key.indexOf("ICS") === 0 : key.indexOf("I.COM") === 0;
          });
          if (units.length) groups.push({ units, needs: e.slots.map(x => SLOT_OF[x]) });
        }
      }
    }
    const groupOf = {};
    for (const g of groups) for (const id of g.units) groupOf[id] = g;
    return { groups, groupOf, byT };
  }

  const TEACHER_CODES = Object.keys(TEACHER_FULL);
  const TEACHER_IDX = {};
  TEACHER_CODES.forEach((c, i) => { TEACHER_IDX[c] = i; });

  // All per-constraint-set precomputation. Cached by generate() per R.
  function buildStatic(R) {
    const secUnits = {};
    const PACKINGS = {}, PACK_SIGS = {}, PACK_GREQ = {}, PACK_COST = {}, MINCOST = {};
    const CAP2D = TEACHER_CODES.map(c => new Array(P).fill(0));
    const GROUPS = makeGroups(R).groups;
    const hasUnitInGroup = {};

    (function computeCaps() {
      const byT = {};
      for (let i = 0; i < UNITS.length; i++) {
        const t = UNITS[i].teacher;
        (byT[t] = byT[t] || []).push(i);
      }
      const unitsFor = t => {
        const u = (byT[t] || []).slice();
        if (t === "Ishfaq" || t === "NaeemAsghar") for (const p of (byT.PARALLEL || [])) u.push(p);
        return u;
      };
      for (let ti = 0; ti < TEACHER_CODES.length; ti++) {
        const t = TEACHER_CODES[ti];
        for (let sl = 0; sl < P; sl++) {
          const union = new Set();
          for (const ui of unitsFor(t)) {
            const u = UNITS[ui];
            if (slotDomain(u, R).includes(sl)) for (const d of dayDomain(u, R)) union.add(d);
          }
          CAP2D[ti][sl] = Math.min(D, union.size);
        }
      }
    })();

    for (const sec of SECTIONS) {
      secUnits[sec.key] = [];
      for (let i = 0; i < UNITS.length; i++) if (UNITS[i].sec === sec.key) secUnits[sec.key].push(i);
      const pkgs = enumeratePackings(sec.subs, R);
      const costOf = pkg => {
        let c = 0;
        for (let j = 0; j < pkg.length; j++) {
          const cnt = sec.subs[j][2];
          const w = cnt === 3 ? 100 : (cnt === 2 ? 10 : 0);
          c += (pkg[j].length - 1) * w;
        }
        return c;
      };
      const order = pkgs.map((p, i) => i).sort((a, b) => costOf(pkgs[a]) - costOf(pkgs[b]));
      PACKINGS[sec.key] = order.map(i => pkgs[i]);
      PACK_COST[sec.key] = order.map(i => costOf(pkgs[i]));
      MINCOST[sec.key] = PACK_COST[sec.key][0];
      const CAPN = 1200;
      if (PACKINGS[sec.key].length > CAPN) {
        PACKINGS[sec.key] = PACKINGS[sec.key].slice(0, CAPN);
        PACK_COST[sec.key] = PACK_COST[sec.key].slice(0, CAPN);
      }
      PACK_SIGS[sec.key] = PACKINGS[sec.key].map(pkg => {
        const sig = [];
        const delta = {};
        for (let j = 0; j < pkg.length; j++) {
          const t = sec.subs[j][1];
          const tlist = t === "PARALLEL" ? ["PARALLEL", "Ishfaq", "NaeemAsghar"] : [t];
          for (const tt of tlist) {
            const ti = TEACHER_IDX[tt];
            for (const o of pkg[j]) {
              const pk = ti * P + o.slot;
              delta[pk] = (delta[pk] || 0) + o.k;
            }
          }
        }
        for (const pk in delta) sig.push([Number(pk), delta[pk]]);
        return sig;
      });
      PACK_GREQ[sec.key] = PACKINGS[sec.key].map(pkg => {
        const entries = [];
        for (let g = 0; g < GROUPS.length; g++) {
          const grp = GROUPS[g];
          let mask = 0;
          let found = false;
          for (const v of grp.units) {
            if (UNITS[v].sec !== sec.key) continue;
            const j = secUnits[sec.key].indexOf(v);
            if (j < 0) continue;
            for (const o of pkg[j]) {
              const ni = grp.needs.indexOf(o.slot);
              if (ni >= 0) mask |= (1 << ni);
              found = true;
            }
          }
          if (found) entries.push([g, mask]);
        }
        return entries;
      });
      hasUnitInGroup[sec.key] = new Set();
      for (let g = 0; g < GROUPS.length; g++)
        if (GROUPS[g].units.some(v => UNITS[v].sec === sec.key)) hasUnitInGroup[sec.key].add(g);
    }
    return { secUnits, PACKINGS, PACK_SIGS, PACK_GREQ, PACK_COST, MINCOST, CAP2D, GROUPS, hasUnitInGroup };
  }

  function stage1(rng, nodeBudget, R, S) {
    const tchSlot = new Array(TEACHER_CODES.length * P).fill(0);
    const covMask = new Array(S.GROUPS.length).fill(0);
    const remUnits = S.GROUPS.map(g => g.units.length);
    const x = {};
    const placedSections = new Set();

    function packingFits(secKey, sig, greq) {
      for (const [p, d] of sig) {
        const ti = (p / P) | 0, sl = p % P;
        if (tchSlot[p] + d > S.CAP2D[ti][sl]) return false;
      }
      for (const [g, mask] of greq) {
        const nm = covMask[g] | mask;
        let missing = 0;
        for (let i = 0; i < S.GROUPS[g].needs.length; i++) {
          if (!((nm >> i) & 1)) missing++;
        }
        if (missing > remUnits[g] - 1) return false;
      }
      return true;
    }
    function applySection(secKey, pkg, sign) {
      const uList = S.secUnits[secKey];
      if (sign === 1) {
        for (let j = 0; j < uList.length; j++) {
          const ui = uList[j];
          x[ui] = pkg[j].map(o => ({ slot: o.slot, k: o.k }));
          const tlist = UNITS[ui].teacher === "PARALLEL" ? ["PARALLEL", "Ishfaq", "NaeemAsghar"] : [UNITS[ui].teacher];
          for (const tt of tlist) {
            const ti = TEACHER_IDX[tt];
            for (const o of pkg[j]) tchSlot[ti * P + o.slot] += o.k;
          }
        }
        for (let g = 0; g < S.GROUPS.length; g++) {
          if (!S.hasUnitInGroup[secKey].has(g)) continue;
          remUnits[g]--;
          let mask = 0;
          for (const v of S.GROUPS[g].units) {
            if (UNITS[v].sec !== secKey) continue;
            const j = S.secUnits[secKey].indexOf(v);
            for (const o of pkg[j]) {
              const ni = S.GROUPS[g].needs.indexOf(o.slot);
              if (ni >= 0) mask |= (1 << ni);
            }
          }
          covMask[g] |= mask;
        }
      } else {
        for (let j = 0; j < uList.length; j++) {
          const ui = uList[j];
          const tlist = UNITS[ui].teacher === "PARALLEL" ? ["PARALLEL", "Ishfaq", "NaeemAsghar"] : [UNITS[ui].teacher];
          for (const tt of tlist) {
            const ti = TEACHER_IDX[tt];
            for (const o of pkg[j]) tchSlot[ti * P + o.slot] -= o.k;
          }
          delete x[ui];
        }
        for (let g = 0; g < S.GROUPS.length; g++) {
          if (!S.hasUnitInGroup[secKey].has(g)) continue;
          remUnits[g]++;
        }
        for (let g = 0; g < S.GROUPS.length; g++) covMask[g] = 0;
        for (const sk of placedSections) {
          for (let g = 0; g < S.GROUPS.length; g++) {
            if (!S.hasUnitInGroup[sk].has(g)) continue;
            let mask = 0;
            for (const v of S.GROUPS[g].units) {
              if (UNITS[v].sec !== sk) continue;
              const j = S.secUnits[sk].indexOf(v);
              for (const o of x[v]) {
                const ni = S.GROUPS[g].needs.indexOf(o.slot);
                if (ni >= 0) mask |= (1 << ni);
              }
            }
            covMask[g] |= mask;
          }
        }
      }
    }

    let nodes = 0;
    let bestCost = Infinity;
    let bestX = null;
    let curCost = 0;
    const snapshot = () => {
      const cp = {};
      for (const k in x) cp[k] = x[k].map(o => ({ slot: o.slot, k: o.k }));
      return cp;
    };

    function bt() {
      nodes++;
      if (nodes > nodeBudget) return "BUDGET";
      if (placedSections.size === SECTIONS.length) {
        if (curCost < bestCost) { bestCost = curCost; bestX = snapshot(); }
        return "CONT";
      }
      let lb = curCost;
      for (const sec of SECTIONS) if (!placedSections.has(sec.key)) lb += S.MINCOST[sec.key];
      if (lb >= bestCost) return "CONT";
      let best = null, bestList = null;
      for (const sec of SECTIONS) {
        if (placedSections.has(sec.key)) continue;
        const fl = [];
        const sigs = S.PACK_SIGS[sec.key], greqs = S.PACK_GREQ[sec.key];
        for (let i = 0; i < sigs.length; i++) {
          if (packingFits(sec.key, sigs[i], greqs[i])) fl.push(i);
        }
        if (fl.length === 0) return null;
        if (bestList === null || fl.length < bestList.length) { best = sec.key; bestList = fl; }
        if (bestList.length === 1) break;
      }
      if (bestList.length > 1) {
        const w = Math.min(6, bestList.length);
        const head = bestList.slice(0, w);
        rng.shuffle(head);
        for (let i = 0; i < w; i++) bestList[i] = head[i];
      }
      for (const pidx of bestList) {
        const pkg = S.PACKINGS[best][pidx];
        applySection(best, pkg, 1);
        placedSections.add(best);
        curCost += S.PACK_COST[best][pidx];
        const r = bt();
        curCost -= S.PACK_COST[best][pidx];
        placedSections.delete(best);
        applySection(best, pkg, -1);
        if (r === "BUDGET") return "BUDGET";
      }
      return "CONT";
    }
    const rr = bt();
    if (bestX === null) return null;
    return { x: bestX, cost: bestCost };
  }

  function splitCount(pkg) {
    let n = 0;
    for (const p of pkg) if (p.length > 1) n++;
    return n;
  }

  // Stage 2: assign concrete days per (unit, slot) via per-slot bipartite
  // edge coloring. Returns grids or null.
  function stage2(x, rng, nodeBudget, R) {
    const dayOfSlot = {};     // unit -> { slot: [days] }
    const usedDays = {};      // unit -> Set(days) (for split-unit distinctness)
    for (let ui = 0; ui < UNITS.length; ui++) { dayOfSlot[ui] = {}; usedDays[ui] = new Set(); }
    const eng = {};   // teacher code -> { minDays, total, colored, covered }
    for (const code in R) {
      const rules = (R[code] && R[code].rules) || {};
      if (rules.min_days_engaged) {
        const total = UNITS.reduce((n, u) => n + (u.teacher === code ? u.count : 0), 0);
        if (total > 0) eng[code] = { minDays: rules.min_days_engaged, total, colored: 0, covered: new Set() };
      }
    }
    let nodes = 0;

    function engRecover() {
      for (const code in eng) {
        const c = new Set();
        for (let ui = 0; ui < UNITS.length; ui++) {
          if (UNITS[ui].teacher !== code) continue;
          for (const s in dayOfSlot[ui]) for (const d of dayOfSlot[ui][s]) c.add(d);
        }
        eng[code].covered = c;
      }
    }

    function btSlot(s) {
      // build edges (unit ids with multiplicity)
      const edges = [];
      for (let ui = 0; ui < UNITS.length; ui++) {
        for (const o of x[ui]) {
          if (o.slot !== s) continue;
          for (let e = 0; e < o.k; e++) edges.push(ui);
        }
      }
      if (edges.length === 0) return true;

      const secUsed = {}, tchUsed = {};
      for (const sec of SECTIONS) secUsed[sec.key] = new Set();
      function tU(t) { return (tchUsed[t] = tchUsed[t] || new Set()); }

      function edgeOk(ui, d) {
        const u = UNITS[ui];
        if (usedDays[ui].has(d)) return false;
        if (secUsed[u.sec].has(d)) return false;
        const tset = u.teacher === "PARALLEL" ? ["PARALLEL", "NaeemAsghar", "Ishfaq"] : [u.teacher];
        for (const t of tset) if (tU(t).has(d)) return false;
        const rr = R[u.teacher] && R[u.teacher].rules;
        if (rr && rr.forbidden_slots_on_days) {
          for (const e of rr.forbidden_slots_on_days) {
            if (_daySet(e.days).has(d) && _slotSet(e.slots).has(s)) return false;
          }
        }
        if (eng[u.teacher]) {
          const e = eng[u.teacher];
          const nc = new Set(e.covered); nc.add(d);
          const remaining = e.total - e.colored - 1;
          const missing = Math.max(0, e.minDays - nc.size);
          if (missing > remaining) return false;
          if (remaining === 0 && nc.size < e.minDays) return false;
        }
        return true;
      }
      function applyEdge(ui, d, sign) {
        const u = UNITS[ui];
        if (sign === 1) {
          usedDays[ui].add(d);
          (dayOfSlot[ui][s] = dayOfSlot[ui][s] || []).push(d);
          secUsed[u.sec].add(d);
          const tset = u.teacher === "PARALLEL" ? ["PARALLEL", "NaeemAsghar", "Ishfaq"] : [u.teacher];
          for (const t of tset) tU(t).add(d);
          if (eng[u.teacher]) { eng[u.teacher].colored++; eng[u.teacher].covered.add(d); }
        } else {
          usedDays[ui].delete(d);
          dayOfSlot[ui][s].pop();
          secUsed[u.sec].delete(d);
          const tset = u.teacher === "PARALLEL" ? ["PARALLEL", "NaeemAsghar", "Ishfaq"] : [u.teacher];
          for (const t of tset) tU(t).delete(d);
          if (eng[u.teacher]) { eng[u.teacher].colored--; } engRecover();
        }
      }

      const remaining = new Set(edges.map((_, i) => i));

      function color() {
        nodes++;
        if (nodes > nodeBudget) return "BUDGET";
        if (remaining.size === 0) return "OK";
        // dynamic MRV: pick uncolored edge with fewest allowed days
        let bestE = -1, bestAllowed = null;
        for (const e of remaining) {
          const ui = edges[e];
          const al = dayDomain(UNITS[ui], R).filter(d => edgeOk(ui, d));
          if (al.length === 0) return null;               // forward check
          if (bestAllowed === null || al.length < bestAllowed.length) { bestE = e; bestAllowed = al; }
          if (bestAllowed.length === 1) break;
        }
        rng.shuffle(bestAllowed);
        for (const d of bestAllowed) {
          const ui = edges[bestE];
          applyEdge(ui, d, 1);
          remaining.delete(bestE);
          const r = color();
          if (r === "OK") return "OK";
          remaining.add(bestE);
          applyEdge(ui, d, -1);
          if (r === "BUDGET") return "BUDGET";
        }
        return null;
      }
      return color() === "OK";
    }

    for (let s = 0; s < P; s++) {
      if (!btSlot(s)) return null;
    }

    // materialize grids
    const grids = {};
    for (const sec of SECTIONS) grids[sec.key] = Array.from({ length: D }, () => new Array(P).fill(null));
    for (let ui = 0; ui < UNITS.length; ui++) {
      const sec = UNITS[ui].sec;
      for (const s in dayOfSlot[ui]) {
        for (const d of dayOfSlot[ui][s]) {
          grids[sec][d][Number(s)] = ui;
        }
      }
    }
    return grids;
  }

  // ---- locks: force/forbid specific (subject,teacher) at a cell ----
  function locksOk(grids, locks) {
    if (!locks || !locks.length) return true;
    for (const L of locks) {
      const uid = grids[L.sec][L.d][L.s];
      if (L.mode === "force") {
        if (uid === null) return false;
        const u = UNITS[uid];
        if (u.subject !== L.subject) return false;
        const tn = TEACHER_FULL[u.teacher] || u.teacher;
        if (tn !== L.teacher) return false;
      } else { // forbid
        if (uid === null) continue;
        const u = UNITS[uid];
        const tn = TEACHER_FULL[u.teacher] || u.teacher;
        if (u.subject === L.subject && tn === L.teacher) return false;
      }
    }
    return true;
  }

  // ------------------------------------------------------------ validate

  // =====================================================================
  function hardnessOfFac(entry, kind) {
    // Mirror of solver.py hardness_of (personal_constraints_model §8).
    const h = entry && entry.hardness;
    if (h && typeof h === "object" && Object.prototype.hasOwnProperty.call(h, kind)) {
      const n = parseInt(h[kind], 10);
      return isNaN(n) ? 100 : Math.max(0, Math.min(100, n));
    }
    if (entry && entry.soft && entry.soft.includes(kind)) return 50;
    return 100;
  }

  // facultyRuleFindings — classic port of the shared personal-rule walker
  // (identical kinds/semantics to context_solver.js / context_model.py).
  // Classic sections carry no pop; pop-scoped entries stay permissive here.
  // =====================================================================
  function secStream(sec) {
    if (sec.indexOf("I.COM") === 0) return "I.COM";
    if (sec.indexOf("ICS") === 0) return "ICS";
    return null;
  }
  // =====================================================================
  // facultyRuleFindings — JS mirror of solver-checker parity walk
  // (context_model.teacher_rule_findings). One deterministic implementation
  // of EVERY personal rule kind (personal_constraints_model.md v2) consumed
  // by evaluating and repair analysis. Scope semantics: entries without
  // scope apply everywhere; cell-level scope gates on the section's
  // pop/stream when the signal is known (permissive when unknown).
  // =====================================================================
  function scopeOfFac(e) {
    const sc = (e && typeof e.scope === "object" && e.scope) || {};
    return sc;
  }
  function scopeCellAppliesFac(e, sec, day, pop, stream) {
    const sc = scopeOfFac(e);
    const pops = sc.populations, streams = sc.streams, secs = sc.sections, days = sc.days;
    if (pops && pop != null && pops.indexOf(pop) < 0) return false;
    if (streams && stream != null && streams.indexOf(stream) < 0) return false;
    if (secs && sec != null && secs.indexOf(sec) < 0) return false;
    if (days && day != null && !_daySet(days).has(typeof day === "string" ? (DAY_OF[day] != null ? DAY_OF[day] : day) : day)) return false;
    if ((pops && pop == null) || (streams && stream == null)) return true; // permissive
    return true;
  }
  function scopeUnitAppliesFac(e, unit, popOf, streamOf) {
    const sc = scopeOfFac(e);
    if (!sc.populations && !sc.streams && !sc.sections) return true;
    for (const sec of (unit.secs || [])) {
      if (sc.populations && sc.populations.indexOf(popOf(sec)) < 0) return false;
      if (sc.streams && sc.streams.indexOf(streamOf(sec)) < 0) return false;
      if (sc.sections && sc.sections.indexOf(sec) < 0) return false;
    }
    return true;
  }
  function facEntryDays(e, D) {
    let days = _daySet(e.days || []);
    const scd = _daySet(scopeOfFac(e).days || []);
    if (days.size && scd.size) days = new Set([...days].filter(d => scd.has(d)));
    else if (scd.size) days = scd;
    if (!days.size) { days = new Set(); for (let d = 0; d < D; d++) days.add(d); }
    return days;
  }

  function facultyRuleFindings(code, facEntry, myUnits, cells, popMap, D, P, penFac) {
    facEntry = facEntry || {};
    const rules = facEntry.rules || {};
    const softSet = new Set(facEntry.soft || []);
    // cells: [[d, s, sec, unit], ...]; popMap: {sec -> pop}; returns finding dicts.
    const findings = [];
    const popOf = sec => popMap[sec] != null ? popMap[sec] : null;
    const courseOfU = (u, sec) => (u.courseBySec || {})[sec];
    const applies = (e, d, s, sec, u) => scopeCellAppliesFac(e, sec, DAY_NAMES[d], popOf(sec), secStream(sec));
    const perDay = {}; const perDaySlot = {}; const occSlotsPerDay = {};
    for (const [d, s] of cells) {
      perDay[d] = (perDay[d] || 0) + 1;
      const k = d + "|" + s; perDaySlot[k] = true;
      (occSlotsPerDay[d] = occSlotsPerDay[d] || new Set()).add(s);
    }
    const sortedSlots = pairs => "[ " + [...pairs].sort().map(k => {
      const q = ("" + k).split("|"); return DAY_NAMES[+q[0]] + " " + PERIOD_LABELS[+q[1]];
    }).join(", ") + " ]";
    const clOf = pred => cells.filter(c => pred(c[0], c[1], c[2], c[3])).map(c => [c[2], c[0], c[1]]);
    const uidsOf = pred => [...new Set(cells.filter(c => pred(c[0], c[1], c[2], c[3])).map(c => c[3].id))].sort((a, b) => a - b);
    function add(ruleKey, msg, opts) {
      opts = opts || {};
      const hf = hardnessOfFac(facEntry, ruleKey);
      if (hf === 0) return;                    // inactive: annotation only
      let isSoft = opts.isSoft != null ? !!opts.isSoft : softSet.has(ruleKey);
      let penX = opts.pen != null ? opts.pen : null;
      if (!isSoft && hf < 100) {
        isSoft = true;                         // demoted hard kind
        if (penX === null && penFac && penFac.rule != null) penX = Math.floor(penFac.rule * hf / 100);
      } else if (isSoft && hf < 100) {
        penX = Math.floor((penX !== null ? penX : penFac.rule) * hf / 100);
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
      const fset = _slotSet(rules.forbidden_slots);
      const pred = (d, s, sec, u) => fset.has(s) && applies({}, d, s, sec, u);
      const bad = new Set(); for (const [d, s] of cells) if (fset.has(s)) bad.add(s);
      if (bad.size) add("forbidden_slots", "teaches in forbidden slot(s) [" +
        [...bad].map(s => PERIOD_LABELS[s]).join(",") + "]", { cells: clOf(pred), uids: uidsOf(pred) });
    }
    if (rules.allowed_slots != null) {
      const aset = _slotSet(rules.allowed_slots);
      const pred = (d, s, sec, u) => !aset.has(s) && applies({}, d, s, sec, u);
      const bad = new Set(); for (const [d, s] of cells) if (!aset.has(s)) bad.add(s);
      if (bad.size) add("allowed_slots", "teaches outside allowed slots [" +
        [...bad].map(s => PERIOD_LABELS[s]).join(",") + "]", { cells: clOf(pred), uids: uidsOf(pred) });
    }
    if (rules.forbidden_days != null) {
      const dset = _daySet(rules.forbidden_days);
      const pred = (d, s, sec, u) => dset.has(d) && applies({}, d, s, sec, u);
      const bad = new Set(); for (const [d] of cells) if (dset.has(d)) bad.add(d);
      if (bad.size) add("forbidden_days", "teaches on forbidden day(s) [" +
        [...bad].map(d => DAY_NAMES[d]).join(",") + "]", { cells: clOf(pred), uids: uidsOf(pred) });
    }
    if (rules.allowed_days != null) {
      const aset = _daySet(rules.allowed_days);
      const pred = (d, s, sec, u) => !aset.has(d) && applies({}, d, s, sec, u);
      const bad = new Set(); for (const [d] of cells) if (!aset.has(d)) bad.add(d);
      if (bad.size) add("allowed_days", "teaches on non-allowed day(s) [" +
        [...bad].map(d => DAY_NAMES[d]).join(",") + "]", { cells: clOf(pred), uids: uidsOf(pred) });
    }
    for (const e of (rules.forbidden_slots_on_days || [])) {
      const dset = facEntryDays(e, D).size && (e.days || scopeOfFac(e).days) ? facEntryDays(e, D) : facEntryDays(e, D);
      const sset = _slotSet(e.slots);
      const pred = (d, s, sec, u) => dset.has(d) && sset.has(s) && applies(e, d, s, sec, u);
      const bad = new Set(); for (const [d, s, sec, u] of cells) if (pred(d, s, sec, u)) bad.add(d + "|" + s);
      if (bad.size) add("forbidden_slots_on_days", "teaches in forbidden day/slot " + sortedSlots(bad),
                        { cells: clOf(pred), uids: uidsOf(pred) });
    }
    // positive union-allow windows — grouped per scope signature
    if (rules.allowed_slots_days) {
      const groups = {};
      for (const e of rules.allowed_slots_days) {
        const sc = scopeOfFac(e);
        const sig = JSON.stringify([sc.populations || [], sc.streams || [], sc.sections || []]);
        (groups[sig] = groups[sig] || []).push(e);
      }
      for (const sig in groups) {
        const es = groups[sig];
        const win = {};   // d -> Set(slots) union across same-scope entries
        for (const e of es) for (const d of facEntryDays(e, D)) {
          (win[d] = win[d] || new Set()); for (const s of _slotSet(e.slots || [])) win[d].add(s);
        }
        const e0 = es[0];
        const pred = (d, s, sec, u) => (!win[d] || !win[d].has(s)) && applies(e0, d, s, sec, u);
        const bad = new Set(); for (const [d, s, sec, u] of cells) if (pred(d, s, sec, u)) bad.add(d + "|" + s);
        if (bad.size) add("allowed_slots_days", "teaches outside the allowed day/slot window " + sortedSlots(bad),
                          { cells: clOf(pred), uids: uidsOf(pred) });
      }
    }
    for (const e of (rules.allowed_slots_in_stream || [])) {
      const sset = _slotSet(e.slots);
      const edays = e.days ? _daySet(e.days) : null;
      const pred = (d, s, sec, u) => secStream(sec) === e.stream && !sset.has(s) &&
        (!edays || edays.has(d)) && applies(e, d, s, sec, u);
      const bad = new Set(); for (const [d, s, sec, u] of cells) if (pred(d, s, sec, u)) bad.add(d + "|" + s);
      if (bad.size) add("allowed_slots_in_stream", e.stream + " classes outside allowed slots " + sortedSlots(bad),
                        { cells: clOf(pred), uids: uidsOf(pred) });
    }
    for (const e of (rules.allowed_days_in_stream || [])) {
      const dset = _daySet(e.days);
      const pred = (d, s, sec, u) => secStream(sec) === e.stream && !dset.has(d) && applies(e, d, s, sec, u);
      const bad = new Set(); for (const [d, s, sec] of cells) if (pred(d, s, sec, cells[0][3])) bad.add(d);
      if (bad.size) add("allowed_days_in_stream", e.stream + " classes on non-allowed day(s) [" +
                        [...bad].map(d => DAY_NAMES[d]).join(",") + "]",
                        { cells: clOf(pred), uids: uidsOf(pred) });
    }
    for (const e of (rules.stream_forbidden_days || [])) {
      const dset = _daySet(e.days || []);
      const pred = (d, s, sec, u) => secStream(sec) === e.stream && dset.has(d) && applies(e, d, s, sec, u);
      const bad = new Set(); for (const [d, s, sec, u] of cells) if (pred(d, s, sec, u)) bad.add(d);
      if (bad.size) add("stream_forbidden_days", e.stream + " classes on forbidden day(s) [" +
                        [...bad].map(d => DAY_NAMES[d]).join(",") + "]",
                        { cells: clOf(pred), uids: uidsOf(pred) });
    }
    for (const e of (rules.allowed_slots_in_sections || [])) {
      const secset = new Set(e.sections || []);
      const dset = e.days ? _daySet(e.days) : null;
      const sset = _slotSet(e.slots || []);
      const pred = (d, s, sec, u) => secset.has(sec) && !sset.has(s) &&
        (!dset || dset.has(d)) && applies(e, d, s, sec, u);
      const bad = new Set(); for (const [d, s, sec, u] of cells) if (pred(d, s, sec, u)) bad.add(d + "|" + s);
      if (bad.size) add("allowed_slots_in_sections", "section-scoped classes outside allowed window " +
                        sortedSlots(bad), { cells: clOf(pred), uids: uidsOf(pred) });
    }
    for (const e of (rules.allowed_days_in_sections || [])) {
      const secset = new Set(e.sections || []);
      const dset = _daySet(e.days || []);
      const pred = (d, s, sec, u) => secset.has(sec) && !dset.has(d) && applies(e, d, s, sec, u);
      const bad = new Set(); for (const [d, s, sec] of cells) if (pred(d, s, sec, cells[0][3])) bad.add(d);
      if (bad.size) add("allowed_days_in_sections", "section-scoped classes on non-allowed day(s) [" +
                        [...bad].map(d => DAY_NAMES[d]).join(",") + "]",
                        { cells: clOf(pred), uids: uidsOf(pred) });
    }
    if (rules.allowed_sections) {
      const aset = new Set(rules.allowed_sections);
      const pred = (d, s, sec, u) => !aset.has(sec);
      const bad = new Set(); for (const [d, s, sec] of cells) if (!aset.has(sec)) bad.add(sec);
      if (bad.size) add("allowed_sections", "teaches outside allowed sections [" + [...bad].join(",") + "]",
                        { cells: clOf(pred), uids: uidsOf(pred) });
    }
    if (rules.forbidden_sections) {
      const fset = new Set(rules.forbidden_sections);
      const pred = (d, s, sec, u) => fset.has(sec);
      const bad = new Set(); for (const [d, s, sec] of cells) if (fset.has(sec)) bad.add(sec);
      if (bad.size) add("forbidden_sections", "teaches in forbidden sections [" + [...bad].join(",") + "]",
                        { cells: clOf(pred), uids: uidsOf(pred) });
    }
    // ---- subject pin kinds (subject_slots unioned per subject; day-scoped ok)
    if (rules.subject_slots) {
      const bySubj = {};
      for (const e of rules.subject_slots) {
        const o = bySubj[e.subject] = bySubj[e.subject] || { win: {}, e: e };
        const ds = e.days ? _daySet(e.days) : facEntryDays(e, D);
        for (const d of ds) { (o.win[d] = o.win[d] || new Set()); for (const s of _slotSet(e.slots || [])) o.win[d].add(s); }
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
      const dset = _daySet(e.days);
      const pred = (d, s, sec, u) => courseOfU(u, sec) === e.subject && dset.has(d) && applies(e, d, s, sec, u);
      const bad = new Set(); for (const [d, s, sec, u] of cells) if (pred(d, s, sec, u)) bad.add(d);
      if (bad.size) add("subject_forbidden_days", e.subject + " on forbidden day(s) [" +
                        [...bad].map(d => DAY_NAMES[d]).join(",") + "]",
                        { cells: clOf(pred), uids: uidsOf(pred) });
    }
    if (rules.subject_days_allowed) {
      const bySubj = {};
      for (const e of rules.subject_days_allowed) {
        bySubj[e.subject] = bySubj[e.subject] || new Set();
        for (const d of _daySet(e.days)) bySubj[e.subject].add(d);
      }
      for (const subj in bySubj) {
        const dset = bySubj[subj];
        const pred = (d, s, sec, u) => courseOfU(u, sec) === subj && !dset.has(d);
        const bad = new Set(); for (const [d, s, sec, u] of cells) if (pred(d, s, sec, u)) bad.add(d);
        if (bad.size) add("subject_days_allowed", subj + " outside allowed day(s) [" +
                          [...bad].map(d => DAY_NAMES[d]).join(",") + "]",
                          { cells: clOf(pred), uids: uidsOf(pred) });
      }
    }
    // subject pins (singular + plural unioned per subject)
    const pins = {};
    for (const e of (rules.subject_slot_days || [])) {
      pins[e.subject] = pins[e.subject] || new Set();
      for (const d of _daySet(e.days)) pins[e.subject].add(d + "|" + SLOT_OF[e.slot]);
    }
    for (const e of (rules.subject_slots_days || [])) {
      pins[e.subject] = pins[e.subject] || new Set();
      for (const d of _daySet(e.days || [])) for (const s of _slotSet(e.slots || [])) pins[e.subject].add(d + "|" + s);
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
      const dsel = facEntryDays(e, D);
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
      const dsel = facEntryDays(e, D);
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
      for (const [d, s, sec, u] of cells) if (s === si && facEntryDays(e, D).has(d) && applies(e, d, s, sec, u)) days.add(d);
      if (days.size > cap) add("max_days_in_slot", e.slot + " engaged on " + days.size + " days (>" + cap + ")");
    }
    // ---- distribution quotas
    const quotaMatch = (e, d, s, sec, u) => {
      if (e.subject && courseOfU(u, sec) !== e.subject) return false;
      if (e.subjects && e.subjects.indexOf(courseOfU(u, sec)) < 0) return false;
      if (e.stream && secStream(sec) !== e.stream) return false;
      if (e.sections && e.sections.indexOf(sec) < 0) return false;
      if (e.slot && SLOT_OF[e.slot] !== s) return false;
      if (e.days && !_daySet(e.days).has(d)) return false;
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
        const edays = facEntryDays(e, D);
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
      const sset = _slotSet(rules.soft_prefer_free_slots);
      let n = 0; for (const [d, s] of cells) if (sset.has(s)) n++;
      if (n) add("soft_prefer_free_slots", n + " period(s) in preferred-free slots [" +
                 rules.soft_prefer_free_slots.join(",") + "]",
                 { isSoft: true, pen: penFac.preferFreeSlot * n,
                   cells: cells.filter(c => sset.has(c[1])).map(c => [c[2], c[0], c[1]]) });
    }
    for (const e of (rules.soft_prefer_free_slots_days || [])) {
      const dset = _daySet(e.days); const sset = _slotSet(e.slots);
      const n = cells.filter(c => dset.has(c[0]) && sset.has(c[1]) && applies(e, c[0], c[1], c[2], c[3])).length;
      if (n) add("soft_prefer_free_slots_days", n + " period(s) in preferred-free windows " +
                 e.days.join("/") + " " + e.slots.join(","),
                 { isSoft: true, pen: penFac.preferFreeSlot * n,
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
                      { isSoft: true, pen: penFac.evenDistribution * excess });
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
                    { isSoft: true, pen: penFac.rule * gaps });
    }
    return findings;
  }


  function validate(grids, R) {
    if (!R) R = resolveConstraints();
    const issues = [];
    const g0 = grids[SECTIONS[0].key];
    const Dg = g0.length, Pg = g0[0].length;   // infer grid dims from the data
    for (const sec of SECTIONS) {
      const g = grids[sec.key];
      const counts = {};
      for (let d = 0; d < Dg; d++) {
        const seen = new Set();
        for (let s = 0; s < Pg; s++) {
          const uid = g[d][s];
          if (uid === null) { issues.push(`${sec.key}: empty day${d} slot${s}`); continue; }
          const u = UNITS[uid];
          counts[u.subject] = (counts[u.subject] || 0) + 1;
          if (seen.has(u.subject)) issues.push(`${sec.key} ${DAYS[d]} ${u.subject} twice`);
          seen.add(u.subject);
        }
      }
      for (const [subject, , count] of sec.subs) {
        if ((counts[subject] || 0) !== count) issues.push(`${sec.key} ${subject} load ${counts[subject]} != ${count}`);
      }
      // ---- course period-coherence (spec §9): 3+/week course sits at ONE dominant period
      for (const cname in counts) {
        const lst = [];
        for (let d = 0; d < Dg; d++) for (let s = 0; s < Pg; s++) {
          const uid = grids[sec.key][d][s];
          if (uid !== null && UNITS[uid].subject === cname) lst.push(s);
        }
        const total = lst.length;
        if (total < 3) continue;
        const freq = {};
        for (const s of lst) freq[s] = (freq[s] || 0) + 1;
        let best = 0;
        for (const k in freq) if (freq[k] > best) best = freq[k];
        let dom = null;
        for (const k in freq) if (freq[k] === best && (dom === null || (+k) < dom)) dom = +k;
        const dev = total - best;
        const plab = SLOTS[dom];
        if (total >= 4) {
          if (dev >= 2) {
            issues.push(`${sec.key} ${cname}: ${dev} of ${total} classes outside one period ` +
                        `(dominant ${plab}) — beyond the allowed 1 tolerance`);
          } else if (dev === 1) {
            issues.push(`(soft) ${sec.key} ${cname}: 1 class outside dominant period ${plab} (allowed at most 1)`);
          }
        } else if (dev >= 1) {
          issues.push(`(soft) ${sec.key} ${cname}: ${dev} of 3 classes outside dominant period ${plab}`);
        }
      }
    }
    const occ = {};
    for (const sec of SECTIONS) {
      const g = grids[sec.key];
      for (let d = 0; d < Dg; d++) {
        for (let s = 0; s < Pg; s++) {
          const uid = g[d][s];
          if (uid === null) continue;
          const t = UNITS[uid].teacher;
          (occ[t] = occ[t] || []).push([d, s, sec.key]);
        }
      }
    }
    for (const t in occ) {
      const seen = new Set();
      for (const [d, s] of occ[t]) {
        const k = d * Pg + s;
        if (seen.has(k)) issues.push(`teacher ${t} double-booked ${DAYS[d]} ${SLOTS[s]}`);
        seen.add(k);
      }
    }
    // rule-driven checks (availability + engagement + placement), per current R —
    // one shared walker implements every personal-rule kind (taxonomy v2);
    // hard findings become issues, soft findings surface as documented notes.
    {
      const Rr = R || resolveConstraints();
      const penFac = { rule: 5000, preferFreeSlot: 500, evenDistribution: 100 };
      // build per-teacher unit shims + cells from occ
      const unitsByT = {};
      for (let ui = 0; ui < UNITS.length; ui++) {
        const u = UNITS[ui];
        if (u.teacher === "PARALLEL") continue;
        const shim = { id: ui, teacher: u.teacher, members: [], secs: [u.sec],
                       subject: u.subject, courseBySec: {} };
        shim.courseBySec[u.sec] = u.subject;
        (unitsByT[u.teacher] = unitsByT[u.teacher] || []).push(shim);
      }
      const shimOf = (ui) => {
        for (const t in unitsByT) for (const sh of unitsByT[t]) if (sh.id === ui) return sh;
        return null;
      };
      for (const t in occ) {
        if (t === "PARALLEL") continue;
        const entry = Rr[t] || {};
        const rules = entry.rules || {};
        const softSet = new Set(entry.soft || []);
        const myUnits = unitsByT[t] || [];
        if (!myUnits.length) continue;
        const cells = [];
        for (const [d, s, secKey] of occ[t]) {
          const uid = grids[secKey][d][s];
          if (uid === null) continue;
          const sh = shimOf(uid);
          if (sh && sh.teacher === t) cells.push([d, s, secKey, sh]);
        }
        const facEntry = { rules: rules, soft: entry.soft, hardness: entry.hardness };
        for (const f of facultyRuleFindings(t, facEntry, myUnits, cells, {}, Dg, Pg, penFac)) {
          issues.push((f.soft ? "(soft) " : "") + t + " " + f.msg);
        }
      }
    }
    const par = occ.PARALLEL || [];
    if (par.length !== 4) issues.push(`parallel size ${par.length}`);
    const parSlots = new Set(par.map(x => x[1]));
    if (parSlots.size !== 1 || (!parSlots.has(2) && !parSlots.has(3))) issues.push(`parallel slot ${[...parSlots]}`);
    const parKeys = new Set(par.map(x => x[0] * Pg + x[1]));
    for (const [d, s, k] of occ.Ishfaq || []) {
      if (parKeys.has(d * Pg + s) && k !== "ICS-II-B") issues.push("Ishfaq clash parallel");
    }
    for (const [d, s] of occ.NaeemAsghar || []) {
      if (!parKeys.has(d * Pg + s)) issues.push("NaeemAsghar outside parallel");
    }

    const com1 = ["I.COM-I-A", "I.COM-I-B", "I.COM-I-C"];
    for (const x of com1) {
      const gx = grids[x];
      let found = false;
      for (let d = 0; d < Dg && !found; d++) {
        for (let s = 0; s < Pg && !found; s++) {
          if (gx[d][s] !== null && UNITS[gx[d][s]].subject === "Principles of Accounting") {
            let okall = true;
            for (const y of com1) {
              if (y === x) continue;
              if (UNITS[grids[y][d][s]].subject === "Principles of Economics") { okall = false; break; }
            }
            if (okall) found = true;
          }
        }
      }
      if (!found) issues.push(`non-overriding failed ${x}`);
    }
    return issues;
  }

  // ------------------------------------------------------------- scoring
  function score(grids) {
    let pen = 0;
    for (const sec of SECTIONS) {
      const g = grids[sec.key];
      const Dg = g.length, Pg = g[0].length;
      const slotsBySubj = {};
      for (let d = 0; d < Dg; d++) {
        for (let s = 0; s < Pg; s++) {
          const uid = g[d][s];
          if (uid !== null) (slotsBySubj[UNITS[uid].subject] = slotsBySubj[UNITS[uid].subject] || new Set()).add(s);
        }
      }
      for (const [subject, , count] of sec.subs) {
        const extra = (slotsBySubj[subject] ? slotsBySubj[subject].size : 0) - 1;
        if (count === 5) pen += extra * 100000;
        else if (count === 4) pen += extra * 10000;
        else if (count === 3) pen += extra * 100;
        else pen += extra * 10;
      }
    }
    return pen;
  }

  function canonical(grids) {
    const parts = [];
    for (const sec of SECTIONS) {
      const g = grids[sec.key];
      const Dg = g.length, Pg = g[0].length;
      for (let d = 0; d < Dg; d++) {
        for (let s = 0; s < Pg; s++) {
          const u = UNITS[g[d][s]];
          parts.push(`${sec.key}|${d}|${s}|${u.subject}|${u.teacher}`);
        }
      }
    }
    return parts.join("|");
  }

  function toTimetable(grids) {
    const out = {};
    for (const sec of SECTIONS) {
      const g = grids[sec.key];
      out[sec.key] = g.map(row => row.map(uid => [UNITS[uid].subject, TEACHER_FULL[UNITS[uid].teacher] || UNITS[uid].teacher]));
    }
    return out;
  }

  // ------------------------------------------------------------ engagement
  // Deterministic substitute engine ("engage the slot").
  //
  // Given a concrete timetable (the toTimetable() form), the resolved constraints
  // and a list of unavailable windows { teacher, days?, slots? }, it finds — for
  // every cell whose slot holder is unavailable in that window — an "engaging
  // professor" (substitute) who satisfies ALL of:
  //   1. is NOT the slot holder (and not otherwise unavailable),
  //   2. has NO class of his own in that day+period (no double-booking), and
  //   3. satisfies his own availability constraints for that day+period
  //      (allowed/forbidden days & slots, and forbidden_slots_on_days).
  //
  // Coverage is MAXIMISED with an exact maximum bipartite matching per day×period
  // position (a professor can only be in one room at a time), while the cover load
  // is spread across the faculty (less-loaded teachers are preferred). Cells with
  // no eligible substitute are reported in `uncovered` rather than double-booked.
  function codesOfFullName(name) {
    if (!name) return [];
    return String(name).split(" / ").map(function (n) {
      return NAME_TO_CODE[n] || n.trim();
    });
  }
  function _normIdx(v, map, all) {
    if (v == null) return all.slice();
    const out = [];
    for (const x of v) {
      if (typeof x === "number") out.push(x);
      else if (map[x] != null) out.push(map[x]);
    }
    return out;
  }
  function substituteEligible(code, d, s, R) {
    const r = (R && R[code] && R[code].rules) || {};
    if (r.allowed_slots && !_slotSet(r.allowed_slots).has(s)) return false;
    if (r.forbidden_slots && _slotSet(r.forbidden_slots).has(s)) return false;
    if (r.allowed_days && !_daySet(r.allowed_days).has(d)) return false;
    if (r.forbidden_days && _daySet(r.forbidden_days).has(d)) return false;
    if (r.forbidden_slots_on_days) {
      for (const e of r.forbidden_slots_on_days) {
        if (_daySet(e.days).has(d) && _slotSet(e.slots).has(s)) return false;
      }
    }
    return true;
  }
  function engage(timetable, R, unavailable, opts) {
    R = R || resolveConstraints();
    opts = opts || {};
    const secKeys = Object.keys(timetable || {});
    // infer grid dims from the timetable itself
    let Dg = 5, Pg = 5;
    for (const sec of secKeys) {
      const g = timetable[sec];
      if (g && g.length) { Dg = g.length; Pg = g[0].length; break; }
    }
    const allDays = []; for (let i = 0; i < Dg; i++) allDays.push(i);
    const allSlots = []; for (let i = 0; i < Pg; i++) allSlots.push(i);
    // Substitute pool: default to the college roster; `opts.roster` REPLACES it
    // (so callers can pass a custom pool, e.g. directory faculty or a test subset).
    let roster;
    if (Array.isArray(opts.roster)) {
      roster = [];
      for (const nm of opts.roster) {
        const c = NAME_TO_CODE[nm] || String(nm);
        if (roster.indexOf(c) < 0) roster.push(c);
      }
    } else {
      roster = [];
      for (const code in TEACHER_FULL) if (code !== "PARALLEL") roster.push(code);
    }

    // 1) blocked (teacher,day,slot) triples from the unavailable windows
    const blocked = {};
    for (const w of (unavailable || [])) {
      if (!w || !w.teacher) continue;
      const codes = codesOfFullName(w.teacher);
      const days = _normIdx(w.days, DAY_OF, allDays);
      const slots = _normIdx(w.slots, SLOT_OF, allSlots);
      for (const c of codes) for (const d of days) for (const s of slots)
        blocked[c + "|" + d + "|" + s] = true;
    }

    // 2) who is busy at each day×slot (their own class)
    const busy = {};
    function markBusy(d, s, code) {
      const k = d + "|" + s;
      (busy[k] = busy[k] || new Set()).add(code);
    }
    for (const sec of secKeys) {
      const g = timetable[sec];
      if (!g) continue;
      for (let d = 0; d < Dg; d++) for (let s = 0; s < Pg; s++) {
        const cell = g[d] && g[d][s];
        if (!cell) continue;
        for (const c of codesOfFullName(cell[1])) markBusy(d, s, c);
      }
    }

    // 3) affected cells (slot holder unavailable at that day+period)
    const affected = [];
    for (const sec of secKeys) {
      const g = timetable[sec];
      if (!g) continue;
      for (let d = 0; d < Dg; d++) for (let s = 0; s < Pg; s++) {
        const cell = g[d] && g[d][s];
        if (!cell) continue;
        const codes = codesOfFullName(cell[1]);
        const hit = codes.some(function (c) { return blocked[c + "|" + d + "|" + s]; });
        if (hit) affected.push({ sec: sec, d: d, s: s, subj: cell[0], teacher: cell[1], codes: codes });
      }
    }

    // 4) group affected cells by day×slot position, in a deterministic order
    const byPos = {};
    for (const a of affected) {
      const k = a.d + "|" + a.s;
      (byPos[k] = byPos[k] || []).push(a);
    }
    const positions = Object.keys(byPos).sort(function (a, b) {
      const pa = a.split("|").map(Number), pb = b.split("|").map(Number);
      return pa[0] - pb[0] || pa[1] - pb[1];
    });

    const load = {};   // code -> total covers assigned so far (for spreading)

    function candidateOrder(d, s, cellCodes) {
      const list = [];
      const busyHere = busy[d + "|" + s] || new Set();
      for (const code of roster) {
        if (busyHere.has(code)) continue;            // has own class in this slot
        if (blocked[code + "|" + d + "|" + s]) continue; // himself unavailable here
        if (cellCodes.indexOf(code) >= 0) continue;  // is the slot holder
        if (!substituteEligible(code, d, s, R)) continue;  // own constraints
        list.push(code);
      }
      list.sort(function (a, b) {
        const la = load[a] || 0, lb = load[b] || 0;
        if (la !== lb) return la - lb;
        const na = TEACHER_FULL[a] || a, nb = TEACHER_FULL[b] || b;
        return na < nb ? -1 : na > nb ? 1 : 0;
      });
      return list;
    }

    // Exact maximum matching at one position (Kuhn's augmenting path)
    function maxMatch(cells) {
      const candPerCell = cells.map(function (cell) {
        return candidateOrder(cell.d, cell.s, cell.codes);
      });
      const taken = {};      // code -> cell index
      function tryK(cellIdx, seen) {
        for (let ci = 0; ci < candPerCell[cellIdx].length; ci++) {
          const code = candPerCell[cellIdx][ci];
          if (seen.has(code)) continue;
          seen.add(code);
          if (!(code in taken) || tryK(taken[code], seen)) {
            taken[code] = cellIdx;
            return true;
          }
        }
        return false;
      }
      // match the most-constrained cells first (MRV) for a provably maximum match
      const order = cells.map(function (_, i) { return i; }).sort(function (a, b) {
        return candPerCell[a].length - candPerCell[b].length;
      });
      for (const i of order) {
        if (candPerCell[i].length) tryK(i, new Set());
      }
      return taken; // code -> cell index
    }

    const assignments = [];
    const uncovered = [];
    for (const k of positions) {
      const cells = byPos[k];
      const m = maxMatch(cells);
      for (let i = 0; i < cells.length; i++) {
        const cell = cells[i];
        let coverCode = null;
        for (const code in m) if (m[code] === i) { coverCode = code; break; }
        if (coverCode != null) {
          load[coverCode] = (load[coverCode] || 0) + 1;
          assignments.push({ sec: cell.sec, d: cell.d, s: cell.s, subj: cell.subj,
            teacher: cell.teacher, cover: TEACHER_FULL[coverCode] || coverCode, coverCode: coverCode });
        } else {
          uncovered.push({ sec: cell.sec, d: cell.d, s: cell.s, subj: cell.subj, teacher: cell.teacher });
        }
      }
    }

    return {
      affected: affected,
      assignments: assignments,
      uncovered: uncovered,
      covered: assignments.length,
      total: affected.length,
      load: load
    };
  }

  function validateEngagement(timetable, R, assignments, unavailable) {
    R = R || resolveConstraints();
    const issues = [];
    // infer grid dims from the timetable itself
    let Dg = 5, Pg = 5;
    for (const sec of Object.keys(timetable || {})) {
      const g = timetable[sec];
      if (g && g.length) { Dg = g.length; Pg = g[0].length; break; }
    }
    const allDays = []; for (let i = 0; i < Dg; i++) allDays.push(i);
    const allSlots = []; for (let i = 0; i < Pg; i++) allSlots.push(i);
    // a cover must not himself be unavailable at that day+period
    const blocked = {};
    for (const w of (unavailable || [])) {
      if (!w || !w.teacher) continue;
      const codes = codesOfFullName(w.teacher);
      const days = _normIdx(w.days, DAY_OF, allDays);
      const slots = _normIdx(w.slots, SLOT_OF, allSlots);
      for (const c of codes) for (const d of days) for (const s of slots)
        blocked[c + "|" + d + "|" + s] = true;
    }
    const busy = {};
    function markBusy(d, s, code) {
      const k = d + "|" + s;
      (busy[k] = busy[k] || new Set()).add(code);
    }
    for (const sec of Object.keys(timetable || {})) {
      const g = timetable[sec];
      if (!g) continue;
      for (let d = 0; d < Dg; d++) for (let s = 0; s < Pg; s++) {
        const cell = g[d] && g[d][s];
        if (!cell) continue;
        for (const c of codesOfFullName(cell[1])) markBusy(d, s, c);
      }
    }
    const atPos = {};
    for (const a of (assignments || [])) {
      const k = a.d + "|" + a.s;
      (atPos[k] = atPos[k] || []).push(a);
    }
    for (const a of (assignments || [])) {
      const coverCode = a.coverCode || NAME_TO_CODE[a.cover] || a.cover;
      const busyHere = busy[a.d + "|" + a.s] || new Set();
      const original = codesOfFullName(a.teacher);
      if (original.indexOf(coverCode) >= 0)
        issues.push(a.sec + " " + DAYS[a.d] + " " + SLOTS[a.s] + ": cover is the slot holder");
      if (busyHere.has(coverCode))
        issues.push(a.sec + " " + DAYS[a.d] + " " + SLOTS[a.s] + ": cover " + a.cover + " has own class in that slot");
      if (blocked[coverCode + "|" + a.d + "|" + a.s])
        issues.push(a.sec + " " + DAYS[a.d] + " " + SLOTS[a.s] + ": cover " + a.cover + " is himself unavailable then");
      if (!substituteEligible(coverCode, a.d, a.s, R))
        issues.push(a.sec + " " + DAYS[a.d] + " " + SLOTS[a.s] + ": cover " + a.cover + " violates own constraints");
    }
    for (const k in atPos) {
      const seen = new Set();
      for (const a of atPos[k]) {
        const coverCode = a.coverCode || NAME_TO_CODE[a.cover] || a.cover;
        if (seen.has(coverCode))
          issues.push(DAYS[a.d] + " " + SLOTS[a.s] + ": cover " + a.cover + " assigned twice at the same period");
        seen.add(coverCode);
      }
    }
    return issues;
  }

  // ------------------------------------------------------------ swapping
  // Interactive multi-cell swaps. A swap is a set of directed moves (cell X -> cell Y
  // means "the teacher at X goes to Y's cell"). Moves form chains and circles:
  //   - a complete circle (each cell gives and receives exactly once) = 0 disruptions;
  //   - an open chain leaves a vacant cell (head) and a double-teacher cell (tail) =
  //     net disruptions = vacant + conflicts = 2 per open chain.
  function swapKeyOf(sec, d, s) { return sec + "|" + d + "|" + s; }
  function parseSwapKey(k) {
    const p = String(k).split("|");
    return { sec: p[0], d: +p[1], s: +p[2] };
  }
  function swapAnalyze(moves) {
    const out = {}, inn = {};
    for (const m of (moves || [])) {
      const f = swapKeyOf(m.from.sec, m.from.d, m.from.s);
      const t = swapKeyOf(m.to.sec, m.to.d, m.to.s);
      out[f] = t; inn[t] = f;
    }
    const visited = {};
    const chains = [], circles = [];
    for (const f in out) {                       // chain heads have no incoming
      if (visited[f] || inn[f]) continue;
      const chain = []; let cur = f;
      while (cur && !visited[cur]) { visited[cur] = true; chain.push(cur); cur = out[cur]; }
      chains.push(chain);
    }
    for (const f in out) {                       // remaining nodes are cycles
      if (visited[f]) continue;
      const circle = []; let cur = f;
      while (cur && !visited[cur]) { visited[cur] = true; circle.push(cur); cur = out[cur]; }
      circles.push(circle);
    }
    const vacant = chains.map(c => c[0]);
    const conflicts = chains.map(c => c[c.length - 1]);
    return { out, inn, chains, circles, vacant, conflicts, net: vacant.length + conflicts.length };
  }
  // Full evaluation against a concrete timetable: adds double-bookings (a teacher
  // landing on a period where they already teach another class outside the swap) and
  // constraint violations to the structural disruptions.
  function swapEvaluate(timetable, moves, R) {
    const a = swapAnalyze(moves);
    R = R || resolveConstraints();
    const involved = {};
    for (const m of moves) {
      involved[swapKeyOf(m.from.sec, m.from.d, m.from.s)] = 1;
      involved[swapKeyOf(m.to.sec, m.to.d, m.to.s)] = 1;
    }
    const busy = {};
    for (const sec in timetable) {
      const g = timetable[sec]; if (!g) continue;
      const Dg = g.length, Pg = g[0].length;
      for (let d = 0; d < Dg; d++) for (let s = 0; s < Pg; s++) {
        const cell = g[d] && g[d][s]; if (!cell) continue;
        for (const code of codesOfFullName(cell[1])) {
          const k = d + "|" + s;
          (busy[k] = busy[k] || {});
          (busy[k][code] = busy[k][code] || []).push(sec);
        }
      }
    }
    const doubleBookings = [], constraintViolations = [];
    for (const m of moves) {
      const fromCell = timetable[m.from.sec] && timetable[m.from.sec][m.from.d] && timetable[m.from.sec][m.from.d][m.from.s];
      if (!fromCell) continue;
      const codes = codesOfFullName(fromCell[1]);
      const slot = m.to.d + "|" + m.to.s;
      const here = busy[slot] || {};
      for (const code of codes) {
        const sections = here[code] || [];
        for (const sec of sections) {
          const cellKey = swapKeyOf(sec, m.to.d, m.to.s);
          if (!involved[cellKey]) doubleBookings.push({ code: code, cell: swapKeyOf(m.to.sec, m.to.d, m.to.s), other: cellKey });
        }
        if (code && !substituteEligible(code, m.to.d, m.to.s, R)) {
          constraintViolations.push({ code: code, cell: swapKeyOf(m.to.sec, m.to.d, m.to.s) });
        }
      }
    }
    const net = a.vacant.length + a.conflicts.length + doubleBookings.length;
    return Object.assign(a, { doubleBookings, constraintViolations, net });
  }
  // Rotate teachers along each circle ("X takes Y's place"): each cell receives the
  // teacher of its predecessor in the circle. Subjects stay with their cells.
  function swapApply(timetable, circles) {
    const tt = JSON.parse(JSON.stringify(timetable));
    for (const circle of circles) {
      const teachers = circle.map(k => {
        const p = parseSwapKey(k);
        return tt[p.sec][p.d][p.s][1];
      });
      for (let i = 0; i < circle.length; i++) {
        const p = parseSwapKey(circle[i]);
        tt[p.sec][p.d][p.s][1] = teachers[(i - 1 + circle.length) % circle.length];
      }
    }
    return tt;
  }
  // Close open chains with the fewest extra moves: match each chain-tail's displaced
  // teacher to a vacant head (maximum bipartite matching), avoiding double-bookings and
  // respecting each teacher's own constraints.
  function swapComplete(timetable, moves, R) {
    R = R || resolveConstraints();
    const ev = swapEvaluate(timetable, moves, R);
    if (ev.net === 0) return { circles: ev.circles, extraMoves: [], resolved: true, unresolved: [] };
    const busy = {};
    for (const sec in timetable) {
      const g = timetable[sec]; if (!g) continue;
      const Dg = g.length, Pg = g[0].length;
      for (let d = 0; d < Dg; d++) for (let s = 0; s < Pg; s++) {
        const cell = g[d] && g[d][s]; if (!cell) continue;
        for (const code of codesOfFullName(cell[1])) {
          const k = d + "|" + s;
          (busy[k] = busy[k] || {});
          (busy[k][code] = busy[k][code] || []).push(sec);
        }
      }
    }
    const involved = {};
    for (const m of moves) {
      involved[swapKeyOf(m.from.sec, m.from.d, m.from.s)] = 1;
      involved[swapKeyOf(m.to.sec, m.to.d, m.to.s)] = 1;
    }
    function freeAt(code, d, s) {
      const list = (busy[d + "|" + s] || {})[code] || [];
      return list.every(sec => involved[swapKeyOf(sec, d, s)]);
    }
    const displaced = ev.conflicts.map(function (k) {
      const p = parseSwapKey(k);
      const cell = timetable && timetable[p.sec] && timetable[p.sec][p.d] && timetable[p.sec][p.d][p.s];
      const codes = cell ? codesOfFullName(cell[1]) : [];
      return { key: k, code: codes.length === 1 ? codes[0] : null, sec: p.sec, d: p.d, s: p.s };
    });
    const vacant = ev.vacant.map(function (k) {
      const p = parseSwapKey(k);
      return { key: k, sec: p.sec, d: p.d, s: p.s };
    });
    const edges = displaced.map(function (dp) {
      return vacant.map(function (vc) {
        return (dp.code && substituteEligible(dp.code, vc.d, vc.s, R) && freeAt(dp.code, vc.d, vc.s)) ? 1 : 0;
      });
    });
    const matchVacant = new Array(vacant.length).fill(-1);
    const takenDisp = new Array(displaced.length).fill(-1);
    function tryK(i, seen) {
      for (let j = 0; j < vacant.length; j++) {
        if (!edges[i][j] || seen.has(j)) continue;
        seen.add(j);
        if (matchVacant[j] === -1 || tryK(matchVacant[j], seen)) { matchVacant[j] = i; takenDisp[i] = j; return true; }
      }
      return false;
    }
    const order = displaced.map((_, i) => i).sort((x, y) => {
      return edges[x].reduce((p, q) => p + q, 0) - edges[y].reduce((p, q) => p + q, 0);
    });
    for (const i of order) if (edges[i].reduce((p, q) => p + q, 0) > 0) tryK(i, new Set());
    const extraMoves = [], unresolved = [];
    for (let i = 0; i < displaced.length; i++) {
      if (takenDisp[i] >= 0) {
        extraMoves.push({
          from: { sec: displaced[i].sec, d: displaced[i].d, s: displaced[i].s },
          to: { sec: vacant[takenDisp[i]].sec, d: vacant[takenDisp[i]].d, s: vacant[takenDisp[i]].s }
        });
      } else unresolved.push(displaced[i]);
    }
    const all = moves.concat(extraMoves);
    const ev2 = swapEvaluate(timetable, all, R);
    if (ev2.net === 0) return { circles: ev2.circles, extraMoves, resolved: true, unresolved: [] };
    return { circles: ev2.circles, extraMoves, resolved: false, unresolved, remainingNet: ev2.net, remaining: ev2.doubleBookings.concat(ev2.constraintViolations) };
  }

  // ------------------------------------------------------------ generate
  let _Key = null, _STATIC = null;
  function generate(opts) {
    // No hard count cutoff by default: keep every distinct valid solution
    // until the time budget is exhausted. Pass maxCount>0 only to cap explicitly.
    //
    // Grid: `days` (1..6) and `periods` (1..8) select the ACTIVE timetable grid
    // (capacity 6x8, see populations.js). Default = the historical 5x5, so all
    // existing callers are unaffected. NOTE: sections must fill the whole active
    // grid exactly (days*periods periods per section) — partial fill arrives with
    // the BS expansion; a mismatch yields zero solutions.
    const days = Math.max(1, Math.min(6, (opts && opts.days) || 5));
    const periods = Math.max(1, Math.min(8, (opts && opts.periods) || 5));
    D = days; P = periods;
    DAYS = DAY_NAMES.slice(0, D);
    SLOTS = PERIOD_LABELS.slice(0, P);
    const maxCount = (opts && opts.maxCount > 0) ? opts.maxCount : Infinity;
    const timeMs = (opts && opts.timeMs) || 15000;
    const seed = (opts && opts.seed) || (Date.now() % 2147483647);
    const R = resolveConstraints(opts && opts.constraints);
    const SECTIONS2 = normalizeSections(opts && opts.sections);
    const key = days + "x" + periods + "|" + JSON.stringify(SECTIONS2) + "|" + JSON.stringify(R);
    if (_Key !== key) {
      SECTIONS = SECTIONS2;
      UNITS = buildUnits(SECTIONS);
      _Key = key;
      _STATIC = buildStatic(R);
    }
    let STATIC = _STATIC;
    const rng = makeRng(seed);
    const seen = {};
    const solutions = [];
    let attempts = 0, valids = 0;
    const t0 = Date.now();

    while (solutions.length < maxCount && Date.now() - t0 < timeMs) {
      attempts++;
      const s1 = stage1(rng, 10000, R, STATIC);
      if (s1 === null) continue;
      const grids = stage2(s1.x, rng, 25000, R);
      if (grids === null) continue;
      const issues = validate(grids, R);
      if (issues.length) continue;
      if (opts && opts.locks && opts.locks.length && !locksOk(grids, opts.locks)) continue;
      valids++;
      const key = canonical(grids);
      if (!seen[key]) {
        seen[key] = true;
        solutions.push({ score: score(grids), timetable: toTimetable(grids) });
      }
    }
    solutions.sort((a, b) => a.score - b.score);
    solutions.forEach((s, i) => { s.rank = i + 1; });
    return {
      solutions,
      stats: { attempts, valids, distinct: solutions.length, seed, elapsedMs: Date.now() - t0 },
      meta: { days: DAYS, slots: SLOTS, section_order: SECTIONS.map(s => s.key) }
    };
  }

  return {
    DAYS, SLOTS, SECTIONS, TEACHER_FULL, RULES, UNITS,
    CAPACITY: { days: 6, periods: 8 }, DAY_NAMES, PERIOD_LABELS,
    SLOT_OF, DAY_OF, DEFAULT_CONSTRAINTS, NAME_TO_CODE, resolveConstraints, extendTeachers, renameTeacher,
    DEFAULT_SECTIONS, normalizeSections, buildUnits,
    generate, validate, score, canonical, toTimetable, locksOk,
    engage, validateEngagement, codesOfFullName, substituteEligible,
    swapKeyOf, parseSwapKey, swapAnalyze, swapEvaluate, swapApply, swapComplete
  };
});
