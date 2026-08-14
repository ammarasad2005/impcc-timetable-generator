/*
 * solver.js — IMPCC Inter (1st Shift) timetable generator (in-browser).
 *
 * A faithful JavaScript port of the CP-SAT model in cp_solver.py (same data,
 * same slot/day domains, same structural rules, same validator and the same
 * shuffle score). The search is a randomized backtracking solver with
 * minimum-remaining-values (MRV) ordering and forward checking. It runs fully
 * client-side — no server, no precomputed data.
 *
 * Exposes IMPCC_SOLVER.generate(opts); also require()-able in Node.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.IMPCC_SOLVER = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const DAYS = ["MON", "TUE", "WED", "THU", "FRI"];
  const SLOTS = ["P1", "P2", "P3", "P4", "P5"];

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
      out[code] = { name: entry.name || (out[code] && out[code].name) || k, rules: base };
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
    const r = R && R[t] && R[t].rules;
    if (r && r.subject_slots) {
      const m = r.subject_slots.find(e => e.subject === subj);
      if (m) return m.slots.map(x => SLOT_OF[x]);
    }
    let dom = [0, 1, 2, 3, 4];
    if (r && r.allowed_slots)   dom = dom.filter(x => _slotSet(r.allowed_slots).has(x));
    if (r && r.forbidden_slots) dom = dom.filter(x => !_slotSet(r.forbidden_slots).has(x));
    return dom;
  }
  function slotDomain(u, R) { return slotDomainT(u.teacher, u.subject, R); }
  function dayDomainT(t, subj, R) {
    const r = R && R[t] && R[t].rules;
    let dom = [0, 1, 2, 3, 4];
    if (r && r.allowed_days)   dom = dom.filter(d => _daySet(r.allowed_days).has(d));
    if (r && r.forbidden_days) dom = dom.filter(d => !_daySet(r.forbidden_days).has(d));
    if (r && r.subject_forbidden_days) {
      const m = r.subject_forbidden_days.find(e => e.subject === subj);
      if (m) dom = dom.filter(d => !_daySet(m.days).has(d));
    }
    return dom;
  }
  function dayDomain(u, R) { return dayDomainT(u.teacher, u.subject, R); }

  // -------------------------------------------------- packings (Stage 1)
  function enumeratePackings(subjs, R) {
    const slotUsed = [0, 0, 0, 0, 0];
    const out = [];
    const cur = subjs.map(() => null);
    function rec(idx) {
      if (idx === subjs.length) {
        if (slotUsed.every(v => v === 5)) out.push(cur.map(c => c.slice()));
        return;
      }
      const [subject, teacher, count] = subjs[idx];
      const sd = slotDomainT(teacher, subject, R);
      for (const s of sd) {
        if (slotUsed[s] + count <= 5) {
          slotUsed[s] += count; cur[idx] = [{ slot: s, k: count }];
          rec(idx + 1); slotUsed[s] -= count;
        }
      }
      if (count === 3) {
        for (const s1 of sd) for (const s2 of sd) {
          if (s2 <= s1) continue;
          if (slotUsed[s1] + 2 <= 5 && slotUsed[s2] + 1 <= 5) {
            slotUsed[s1] += 2; slotUsed[s2] += 1;
            cur[idx] = [{ slot: s1, k: 2 }, { slot: s2, k: 1 }];
            rec(idx + 1); slotUsed[s1] -= 2; slotUsed[s2] -= 1;
          }
        }
        for (const s1 of sd) for (const s2 of sd) for (const s3 of sd) {
          if (s2 <= s1 || s3 <= s2) continue;
          if (slotUsed[s1] + 1 <= 5 && slotUsed[s2] + 1 <= 5 && slotUsed[s3] + 1 <= 5) {
            slotUsed[s1]++; slotUsed[s2]++; slotUsed[s3]++;
            cur[idx] = [{ slot: s1, k: 1 }, { slot: s2, k: 1 }, { slot: s3, k: 1 }];
            rec(idx + 1); slotUsed[s1]--; slotUsed[s2]--; slotUsed[s3]--;
          }
        }
      } else if (count === 2) {
        for (const s1 of sd) for (const s2 of sd) {
          if (s2 <= s1) continue;
          if (slotUsed[s1] + 1 <= 5 && slotUsed[s2] + 1 <= 5) {
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
    const CAP2D = TEACHER_CODES.map(c => [0, 0, 0, 0, 0]);
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
        for (let sl = 0; sl < 5; sl++) {
          const union = new Set();
          for (const ui of unitsFor(t)) {
            const u = UNITS[ui];
            if (slotDomain(u, R).includes(sl)) for (const d of dayDomain(u, R)) union.add(d);
          }
          CAP2D[ti][sl] = Math.min(5, union.size);
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
              const pk = ti * 5 + o.slot;
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
    const tchSlot = new Array(TEACHER_CODES.length * 5).fill(0);
    const covMask = new Array(S.GROUPS.length).fill(0);
    const remUnits = S.GROUPS.map(g => g.units.length);
    const x = {};
    const placedSections = new Set();

    function packingFits(secKey, sig, greq) {
      for (const [p, d] of sig) {
        const ti = (p / 5) | 0, sl = p % 5;
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
            for (const o of pkg[j]) tchSlot[ti * 5 + o.slot] += o.k;
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
            for (const o of pkg[j]) tchSlot[ti * 5 + o.slot] -= o.k;
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

    for (let s = 0; s < 5; s++) {
      if (!btSlot(s)) return null;
    }

    // materialize grids
    const grids = {};
    for (const sec of SECTIONS) grids[sec.key] = Array.from({ length: 5 }, () => new Array(5).fill(null));
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
  function validate(grids, R) {
    if (!R) R = resolveConstraints();
    const issues = [];
    for (const sec of SECTIONS) {
      const g = grids[sec.key];
      const counts = {};
      for (let d = 0; d < 5; d++) {
        const seen = new Set();
        for (let s = 0; s < 5; s++) {
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
    }
    const occ = {};
    for (const sec of SECTIONS) {
      const g = grids[sec.key];
      for (let d = 0; d < 5; d++) {
        for (let s = 0; s < 5; s++) {
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
        const k = d * 5 + s;
        if (seen.has(k)) issues.push(`teacher ${t} double-booked ${DAYS[d]} ${SLOTS[s]}`);
        seen.add(k);
      }
    }
    // rule-driven checks (availability + engagement + placement), per current R
    for (const t in occ) {
      const rr = R[t] && R[t].rules;
      if (!rr) continue;
      const as = rr.allowed_slots ? _slotSet(rr.allowed_slots) : null;
      const fs = rr.forbidden_slots ? _slotSet(rr.forbidden_slots) : null;
      const ad = rr.allowed_days ? _daySet(rr.allowed_days) : null;
      const fd = rr.forbidden_days ? _daySet(rr.forbidden_days) : null;
      for (const [d, s, k] of occ[t]) {
        if (as && !as.has(s)) issues.push(`${t} slot not allowed ${SLOTS[s]} (${k})`);
        if (fs && fs.has(s)) issues.push(`${t} forbidden slot ${SLOTS[s]} (${k})`);
        if (ad && !ad.has(d)) issues.push(`${t} day not allowed ${DAYS[d]} (${k})`);
        if (fd && fd.has(d)) issues.push(`${t} forbidden day ${DAYS[d]} (${k})`);
        if (rr.forbidden_slots_on_days) for (const e of rr.forbidden_slots_on_days) {
          if (_daySet(e.days).has(d) && _slotSet(e.slots).has(s)) issues.push(`${t} forbidden ${DAYS[d]} ${SLOTS[s]} (${k})`);
        }
      }
      if (rr.min_days_in_slot) for (const e of rr.min_days_in_slot) {
        const days = new Set(occ[t].filter(x => x[1] === SLOT_OF[e.slot]).map(x => x[0]));
        if (days.size < (e.min_days || 1)) issues.push(`${t} ${e.slot} only ${days.size} days (<${e.min_days})`);
      }
      if (rr.min_days_engaged) {
        const days = new Set(occ[t].map(x => x[0]));
        if (days.size < rr.min_days_engaged) issues.push(`${t} engaged only ${days.size} days (<${rr.min_days_engaged})`);
      }
      if (rr.stream_slots_required) for (const e of rr.stream_slots_required) for (const sl of e.slots) {
        const days = new Set(occ[t].filter(x => x[1] === SLOT_OF[sl]).map(x => x[0]));
        if (days.size < 4) issues.push(`${t} ${e.stream} ${sl} only ${days.size} days`);
      }
    }
    // subject placement rules
    for (const sec of SECTIONS) {
      const g = grids[sec.key];
      for (let d = 0; d < 5; d++) for (let s = 0; s < 5; s++) {
        const uid = g[d][s];
        if (uid === null) continue;
        const u = UNITS[uid];
        const rr = R[u.teacher] && R[u.teacher].rules;
        if (!rr) continue;
        if (rr.subject_slots) for (const e of rr.subject_slots) {
          if (e.subject === u.subject && !_slotSet(e.slots).has(s)) issues.push(`${u.teacher} ${u.subject} not in ${e.slots.join("/")} (${sec.key})`);
        }
        if (rr.subject_forbidden_days) for (const e of rr.subject_forbidden_days) {
          if (e.subject === u.subject && _daySet(e.days).has(d)) issues.push(`${u.teacher} ${u.subject} on ${DAYS[d]} (${sec.key})`);
        }
      }
    }

    const par = occ.PARALLEL || [];
    if (par.length !== 4) issues.push(`parallel size ${par.length}`);
    const parSlots = new Set(par.map(x => x[1]));
    if (parSlots.size !== 1 || (!parSlots.has(2) && !parSlots.has(3))) issues.push(`parallel slot ${[...parSlots]}`);
    const parKeys = new Set(par.map(x => x[0] * 5 + x[1]));
    for (const [d, s, k] of occ.Ishfaq || []) {
      if (parKeys.has(d * 5 + s) && k !== "ICS-II-B") issues.push("Ishfaq clash parallel");
    }
    for (const [d, s] of occ.NaeemAsghar || []) {
      if (!parKeys.has(d * 5 + s)) issues.push("NaeemAsghar outside parallel");
    }

    const com1 = ["I.COM-I-A", "I.COM-I-B", "I.COM-I-C"];
    for (const x of com1) {
      const gx = grids[x];
      let found = false;
      for (let d = 0; d < 5 && !found; d++) {
        for (let s = 0; s < 5 && !found; s++) {
          if (UNITS[gx[d][s]].subject === "Principles of Accounting") {
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
      const slotsBySubj = {};
      for (let d = 0; d < 5; d++) {
        for (let s = 0; s < 5; s++) {
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
      for (let d = 0; d < 5; d++) {
        for (let s = 0; s < 5; s++) {
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
      const days = _normIdx(w.days, DAY_OF, [0, 1, 2, 3, 4]);
      const slots = _normIdx(w.slots, SLOT_OF, [0, 1, 2, 3, 4]);
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
      for (let d = 0; d < 5; d++) for (let s = 0; s < 5; s++) {
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
      for (let d = 0; d < 5; d++) for (let s = 0; s < 5; s++) {
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
    // a cover must not himself be unavailable at that day+period
    const blocked = {};
    for (const w of (unavailable || [])) {
      if (!w || !w.teacher) continue;
      const codes = codesOfFullName(w.teacher);
      const days = _normIdx(w.days, DAY_OF, [0, 1, 2, 3, 4]);
      const slots = _normIdx(w.slots, SLOT_OF, [0, 1, 2, 3, 4]);
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
      for (let d = 0; d < 5; d++) for (let s = 0; s < 5; s++) {
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
      for (let d = 0; d < 5; d++) for (let s = 0; s < 5; s++) {
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
      for (let d = 0; d < 5; d++) for (let s = 0; s < 5; s++) {
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
    return { circles: ev2.circles, extraMoves, resolved: false, unresolved, remaining: ev2.doubleBookings.concat(ev2.constraintViolations) };
  }

  // ------------------------------------------------------------ generate
  let _Key = null, _STATIC = null;
  function generate(opts) {
    // No hard count cutoff by default: keep every distinct valid solution
    // until the time budget is exhausted. Pass maxCount>0 only to cap explicitly.
    const maxCount = (opts && opts.maxCount > 0) ? opts.maxCount : Infinity;
    const timeMs = (opts && opts.timeMs) || 15000;
    const seed = (opts && opts.seed) || (Date.now() % 2147483647);
    const R = resolveConstraints(opts && opts.constraints);
    const SECTIONS2 = normalizeSections(opts && opts.sections);
    const key = JSON.stringify(SECTIONS2) + "|" + JSON.stringify(R);
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
    SLOT_OF, DAY_OF, DEFAULT_CONSTRAINTS, NAME_TO_CODE, resolveConstraints,
    DEFAULT_SECTIONS, normalizeSections, buildUnits,
    generate, validate, score, canonical, toTimetable, locksOk,
    engage, validateEngagement, codesOfFullName, substituteEligible,
    swapKeyOf, parseSwapKey, swapAnalyze, swapEvaluate, swapApply, swapComplete
  };
});
