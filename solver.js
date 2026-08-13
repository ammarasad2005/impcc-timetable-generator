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
  const SECTIONS = [
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

  const UNITS = [];
  for (const sec of SECTIONS) {
    for (const [subject, teacher, count] of sec.subs) {
      UNITS.push({ sec: sec.key, subject, teacher, count });
    }
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
  function slotDomainT(t, subj) {
    if (t === "Naeem" && subj === "Principles of Accounting") return [2, 3, 4];
    if (t === "Naeem" && subj === "Principles of Commerce") return [0, 1];
    if (t === "Assad" && subj === "Business Mathematics") return [2];
    if (t === "Assad" && subj === "Mathematics") return [0, 1, 3, 4];
    if (t === "Ishfaq") return [0, 1, 2, 3];
    if (t === "PARALLEL") return [2, 3];
    if (t === "Tanveer") return [0, 1, 2];
    if (t === "Basit") return [0, 1, 2, 3];
    return ALLOWED[t] ? ALLOWED[t].slice() : [0, 1, 2, 3, 4];
  }
  function slotDomain(u) { return slotDomainT(u.teacher, u.subject); }
  function dayDomainT(t, subj) {
    if (t === "Tanveer") return [3, 4];
    if (t === "Assad" && subj === "Business Mathematics") return [0, 1, 2, 3];
    if (t === "Naeem" && subj === "Principles of Commerce") return [1, 2, 3, 4];
    return [0, 1, 2, 3, 4];
  }
  function dayDomain(u) { return dayDomainT(u.teacher, u.subject); }

  // -------------------------------------------------- packings (Stage 1)
  function enumeratePackings(subjs) {
    const slotUsed = [0, 0, 0, 0, 0];
    const out = [];
    const cur = subjs.map(() => null);
    function rec(idx) {
      if (idx === subjs.length) {
        if (slotUsed.every(v => v === 5)) out.push(cur.map(c => c.slice()));
        return;
      }
      const [subject, teacher, count] = subjs[idx];
      const sd = slotDomainT(teacher, subject);
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

  function makeGroups() {
    const byT = {};
    for (let i = 0; i < UNITS.length; i++) {
      const t = UNITS[i].teacher;
      (byT[t] = byT[t] || []).push(i);
    }
    const math = byT.Assad.filter(i => UNITS[i].subject === "Mathematics");
    const cs = byT.Babar.slice();
    const ish = byT.Ishfaq.slice();
    const bs = byT.Basit.slice();
    const groups = [
      { units: math, needs: [0, 1] },
      { units: cs, needs: [0, 1] },
      { units: ish, needs: [0] },
      { units: bs, needs: [0] }
    ];
    const groupOf = {};
    for (const g of groups) for (const id of g.units) groupOf[id] = g;
    return { groups, groupOf, byT };
  }

  const secUnits = {};   // section key -> [unit indices] (in subs order)
  const PACKINGS = {};   // section key -> [ packing ]
  const PACK_SIGS = {};  // section key -> [ signature: [pairIdx, days] ]
  const PACK_GREQ = {};  // section key -> [ [groupIdx, needMask] ]
  const PACK_COST = {};  // section key -> [ cost ]
  const MINCOST = {};    // section key -> min packing cost
  const TEACHER_IDX = {};
  const TEACHER_CODES = Object.keys(TEACHER_FULL);
  TEACHER_CODES.forEach((c, i) => { TEACHER_IDX[c] = i; });
  // per-teacher per-slot capacity = |union of dayDomains of units that can sit there|
  const CAP2D = TEACHER_CODES.map(c => [0, 0, 0, 0, 0]);
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
      for (let s = 0; s < 5; s++) {
        const union = new Set();
        for (const ui of unitsFor(t)) {
          const u = UNITS[ui];
          if (slotDomain(u).includes(s)) {
            for (const d of dayDomain(u)) union.add(d);
          }
        }
        CAP2D[ti][s] = Math.min(5, union.size);
      }
    }
  })();

  const { groups: GROUPS } = makeGroups();
  const hasUnitInGroup = {};   // secKey -> Set(groupIdx)

  for (const s of SECTIONS) {
    secUnits[s.key] = [];
    for (let i = 0; i < UNITS.length; i++) if (UNITS[i].sec === s.key) secUnits[s.key].push(i);
    const pkgs = enumeratePackings(s.subs);
    const costOf = pkg => {
      let c = 0;
      for (let j = 0; j < pkg.length; j++) {
        const cnt = s.subs[j][2];
        const w = cnt === 3 ? 100 : (cnt === 2 ? 10 : 0);
        c += (pkg[j].length - 1) * w;
      }
      return c;
    };
    const order = pkgs.map((p, i) => i).sort((a, b) => costOf(pkgs[a]) - costOf(pkgs[b]));
    PACKINGS[s.key] = order.map(i => pkgs[i]);
    PACK_COST[s.key] = order.map(i => costOf(pkgs[i]));
    MINCOST[s.key] = PACK_COST[s.key][0];
    // cap the packing list (keep lowest-cost) for speed
    const CAPN = 1200;
    if (PACKINGS[s.key].length > CAPN) {
      PACKINGS[s.key] = PACKINGS[s.key].slice(0, CAPN);
      PACK_COST[s.key] = PACK_COST[s.key].slice(0, CAPN);
    }
    PACK_SIGS[s.key] = PACKINGS[s.key].map(pkg => {
      const sig = [];
      const delta = {};
      for (let j = 0; j < pkg.length; j++) {
        const t = s.subs[j][1];
        const tlist = t === "PARALLEL" ? ["PARALLEL", "Ishfaq", "NaeemAsghar"] : [t];
        for (const tt of tlist) {
          const ti = TEACHER_IDX[tt];
          for (const o of pkg[j]) {
            const p = ti * 5 + o.slot;
            delta[p] = (delta[p] || 0) + o.k;
          }
        }
      }
      for (const p in delta) sig.push([Number(p), delta[p]]);
      return sig;
    });
    // req contribution per packing
    PACK_GREQ[s.key] = PACKINGS[s.key].map(pkg => {
      const entries = [];
      for (let g = 0; g < GROUPS.length; g++) {
        const grp = GROUPS[g];
        let mask = 0;
        let found = false;
        for (const v of grp.units) {
          if (UNITS[v].sec !== s.key) continue;
          const j = secUnits[s.key].indexOf(v);
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
    hasUnitInGroup[s.key] = new Set();
    for (let g = 0; g < GROUPS.length; g++) {
      if (GROUPS[g].units.some(v => UNITS[v].sec === s.key)) hasUnitInGroup[s.key].add(g);
    }
  }

  function stage1(rng, nodeBudget) {
    const tchSlot = new Array(TEACHER_CODES.length * 5).fill(0);
    const covMask = new Array(GROUPS.length).fill(0);
    const remUnits = GROUPS.map(g => g.units.length);
    const x = {};
    const placedSections = new Set();

    function packingFits(secKey, sig, greq) {
      for (const [p, d] of sig) {
        const ti = (p / 5) | 0, sl = p % 5;
        if (tchSlot[p] + d > CAP2D[ti][sl]) return false;
      }
      for (const [g, mask] of greq) {
        const nm = covMask[g] | mask;
        let missing = 0;
        for (let i = 0; i < GROUPS[g].needs.length; i++) {
          if (!((nm >> i) & 1)) missing++;
        }
        if (missing > remUnits[g] - 1) return false;
      }
      return true;
    }
    function applySection(secKey, pkg, sign) {
      const sig = sign === 1 ? null : null;
      const uList = secUnits[secKey];
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
        for (let g = 0; g < GROUPS.length; g++) {
          if (!hasUnitInGroup[secKey].has(g)) continue;
          remUnits[g]--;
          // recompute mask contribution from this section's packing
          let mask = 0;
          for (const v of GROUPS[g].units) {
            if (UNITS[v].sec !== secKey) continue;
            const j = secUnits[secKey].indexOf(v);
            for (const o of pkg[j]) {
              const ni = GROUPS[g].needs.indexOf(o.slot);
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
        for (let g = 0; g < GROUPS.length; g++) {
          if (!hasUnitInGroup[secKey].has(g)) continue;
          remUnits[g]++;
        }
        // recompute covMask from scratch for correctness (cheap: GROUPS small)
        for (let g = 0; g < GROUPS.length; g++) covMask[g] = 0;
        for (const sk of placedSections) {
          const pk = PACKINGS[sk];
          const idx = PACK_SIGS[sk].indexOf;
          // recompute via stored x for units in this section
          for (let g = 0; g < GROUPS.length; g++) {
            if (!hasUnitInGroup[sk].has(g)) continue;
            let mask = 0;
            for (const v of GROUPS[g].units) {
              if (UNITS[v].sec !== sk) continue;
              const j = secUnits[sk].indexOf(v);
              for (const o of x[v]) {
                const ni = GROUPS[g].needs.indexOf(o.slot);
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
      // lower-bound prune
      let lb = curCost;
      for (const s of SECTIONS) if (!placedSections.has(s.key)) lb += MINCOST[s.key];
      if (lb >= bestCost) return "CONT";
      // MRV over sections
      let best = null, bestList = null;
      for (const s of SECTIONS) {
        if (placedSections.has(s.key)) continue;
        const fl = [];
        const sigs = PACK_SIGS[s.key], greqs = PACK_GREQ[s.key];
        for (let i = 0; i < sigs.length; i++) {
          if (packingFits(s.key, sigs[i], greqs[i])) fl.push(i);
        }
        if (fl.length === 0) return null;
        if (bestList === null || fl.length < bestList.length) { best = s.key; bestList = fl; }
        if (bestList.length === 1) break;
      }
      // packings are already sorted by cost. Lightly shuffle the head for variety.
      if (bestList.length > 1) {
        const w = Math.min(6, bestList.length);
        const head = bestList.slice(0, w);
        rng.shuffle(head);
        for (let i = 0; i < w; i++) bestList[i] = head[i];
      }
      for (const pidx of bestList) {
        const pkg = PACKINGS[best][pidx];
        applySection(best, pkg, 1);
        placedSections.add(best);
        curCost += PACK_COST[best][pidx];
        const r = bt();
        curCost -= PACK_COST[best][pidx];
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
  function stage2(x, rng, nodeBudget) {
    const dayOfSlot = {};     // unit -> { slot: [days] }
    const usedDays = {};      // unit -> Set(days) (for split-unit distinctness)
    for (let ui = 0; ui < UNITS.length; ui++) { dayOfSlot[ui] = {}; usedDays[ui] = new Set(); }
    const basitTotal = UNITS.reduce((n, u, i) => n + (u.teacher === "Basit" ? u.count : 0), 0);
    let basitColored = 0;
    let basitCovered = new Set();
    let nodes = 0;

    function basitRecover() {
      const c = new Set();
      for (let ui = 0; ui < UNITS.length; ui++) {
        if (UNITS[ui].teacher !== "Basit") continue;
        for (const s in dayOfSlot[ui]) for (const d of dayOfSlot[ui][s]) c.add(d);
      }
      return c;
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
        if (u.teacher === "Basit") {
          const nc = new Set(basitCovered); nc.add(d);
          const remaining = basitTotal - basitColored - 1;
          const missing = 5 - nc.size;
          if (missing > remaining) return false;
          if (remaining === 0 && missing !== 0) return false;
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
          if (u.teacher === "Basit") { basitColored++; basitCovered.add(d); }
        } else {
          usedDays[ui].delete(d);
          dayOfSlot[ui][s].pop();
          secUsed[u.sec].delete(d);
          const tset = u.teacher === "PARALLEL" ? ["PARALLEL", "NaeemAsghar", "Ishfaq"] : [u.teacher];
          for (const t of tset) tU(t).delete(d);
          if (u.teacher === "Basit") { basitColored--; basitCovered = basitRecover(); }
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
          const al = dayDomain(UNITS[ui]).filter(d => edgeOk(ui, d));
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

  function solveOnce(rng, nodeBudget) {
    const s1 = stage1(rng, 200000);
    if (s1 === null) return null;
    const grids = stage2(s1.x, rng, 200000);
    return grids;
  }

  // ------------------------------------------------------------ validate
  function validate(grids) {
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
    for (const t in occ) {
      for (const [d, s, k] of occ[t]) {
        if (t === "Naeem" && s <= 1 && d === 0) issues.push(`Naeem Mon P1/P2 (${k})`);
        if (t === "Amir" && (s === 0 || s === 4)) issues.push(`Amir P1/P5 (${k})`);
        if (t === "Husnul" && (s === 0 || s === 4)) issues.push(`Husnul P1/P5 (${k})`);
        if (t === "Millat" && s === 0) issues.push(`Millat P1 (${k})`);
        if (t === "Yasir" && [0, 1, 3].indexOf(s) < 0) issues.push(`Yasir slot (${k})`);
        if (t === "Basit" && s === 4) issues.push(`Basit P5 (${k})`);
        if (t === "NaeemAsghar" && s <= 1) issues.push(`NaeemAsghar P1/P2 (${k})`);
        if (t === "Tanveer" && (d < 3 || d > 4 || s > 2)) issues.push(`Tanveer Thu/Fri P1-3 (${k})`);
        if (t === "Ishfaq" && s === 4) issues.push(`Ishfaq P5 (${k})`);
      }
    }
    for (const sec of SECTIONS) {
      const g = grids[sec.key];
      for (let d = 0; d < 5; d++) {
        for (let s = 0; s < 5; s++) {
          const uid = g[d][s];
          if (uid === null) continue;
          const u = UNITS[uid];
          if (u.teacher === "Assad" && u.subject === "Business Mathematics") {
            if (s !== 2) issues.push(`Assad BM not P3 (${sec.key})`);
            if (d === 4) issues.push(`Assad BM Friday (${sec.key})`);
          }
        }
      }
    }
    const assadP1 = new Set(), assadP2 = new Set();
    for (const [d, s] of occ.Assad || []) { if (s === 0) assadP1.add(d); if (s === 1) assadP2.add(d); }
    for (let d = 0; d < 5; d++) {
      if (!assadP1.has(d)) issues.push(`Assad not P1 ${DAYS[d]}`);
      if (!assadP2.has(d)) issues.push(`Assad not P2 ${DAYS[d]}`);
    }
    const bbP1 = new Set(), bbP2 = new Set();
    for (const [d, s] of occ.Babar || []) { if (s === 0) bbP1.add(d); if (s === 1) bbP2.add(d); }
    if (bbP1.size < 4) issues.push("Babar P1 <4 days");
    if (bbP2.size < 4) issues.push("Babar P2 <4 days");

    const basitDays = new Set(), basitP1 = new Set();
    for (const [d, s] of occ.Basit || []) { basitDays.add(d); if (s === 0) basitP1.add(d); }
    for (let d = 0; d < 5; d++) if (!basitDays.has(d)) issues.push(`Basit off ${DAYS[d]}`);
    if (basitP1.size < 4) issues.push("Basit P1 <4 days");

    const ishP1 = new Set();
    for (const [d, s] of occ.Ishfaq || []) if (s === 0) ishP1.add(d);
    if (ishP1.size < 4) issues.push("Ishfaq P1 <4 days");

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
      out[sec.key] = g.map(row => row.map(uid => [UNITS[uid].subject, TEACHER_FULL[UNITS[uid].teacher]]));
    }
    return out;
  }

  // ------------------------------------------------------------ generate
  function generate(opts) {
    const maxCount = (opts && opts.maxCount) || 20;
    const timeMs = (opts && opts.timeMs) || 15000;
    const seed = (opts && opts.seed) || (Date.now() % 2147483647);
    const rng = makeRng(seed);
    const seen = {};
    const solutions = [];
    let attempts = 0, valids = 0;
    const t0 = Date.now();

    while (solutions.length < maxCount && Date.now() - t0 < timeMs) {
      attempts++;
      const s1 = stage1(rng, 10000);
      if (s1 === null) continue;
      const grids = stage2(s1.x, rng, 25000);
      if (grids === null) continue;
      const issues = validate(grids);
      if (issues.length) continue;
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
    generate, validate, score, canonical, toTimetable
  };
});
