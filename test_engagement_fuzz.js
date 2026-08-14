// test_engagement_fuzz.js — synthetic edge cases + randomized fuzz for the
// substitute engine. Run: node test_engagement_fuzz.js
const IMPCC_SOLVER = require("./solver.js");
const NAME_TO_CODE = IMPCC_SOLVER.NAME_TO_CODE;
const R0 = IMPCC_SOLVER.resolveConstraints();

let passed = 0, failed = 0;
const failures = [];
function check(name, cond, extra) {
  if (cond) passed++;
  else { failed++; failures.push(name + (extra ? "  [" + extra + "]" : "")); }
}

const FULL = IMPCC_SOLVER.TEACHER_FULL;
// a few handy full names
const N = (c) => FULL[c];

// =====================================================================
// SYNTHETIC 1 — exact maximum matching with a scarce pool
// =====================================================================
// 3 sections all need a cover at MON P1 (three different absent teachers).
// Only 2 substitutes exist in the pool -> maximum effort = cover 2, report 1.
{
  const tt = {
    S1: [[[ "A", N("Naeem") ]], ],
    S2: [[[ "B", N("Assad") ]], ],
    S3: [[[ "C", N("Babar") ]], ],
  };
  // fill nothing else: busy at MON P1 = {Naeem, Assad, Babar}
  const unavailable = [
    { teacher: N("Naeem"), days: ["MON"] },
    { teacher: N("Assad"), days: ["MON"] },
    { teacher: N("Babar"), days: ["MON"] },
  ];
  const pool = [N("V1"), N("V2")];
  const e = IMPCC_SOLVER.engage(tt, R0, unavailable, { roster: pool });
  check("S1: 3 cells, 2 substitutes -> covered 2", e.covered === 2, "covered=" + e.covered);
  check("S1: uncovered 1 (honest report)", e.uncovered.length === 1, JSON.stringify(e.uncovered));
  check("S1: no cover double-assigned at same period",
    new Set(e.assignments.map(a => a.cover)).size === e.assignments.length);
  check("S1: validation clean",
    IMPCC_SOLVER.validateEngagement(tt, R0, e.assignments, unavailable).length === 0);
}

// =====================================================================
// SYNTHETIC 2 — plenty of substitutes -> every cell covered
// =====================================================================
{
  const tt = {
    S1: [[[ "A", N("Naeem") ]], ],
    S2: [[[ "B", N("Assad") ]], ],
    S3: [[[ "C", N("Babar") ]], ],
  };
  const unavailable = [
    { teacher: N("Naeem"), days: ["MON"] },
    { teacher: N("Assad"), days: ["MON"] },
    { teacher: N("Babar"), days: ["MON"] },
  ];
  const pool = [N("V1"), N("V2"), N("V3"), N("Millat"), N("Amir")];
  const e = IMPCC_SOLVER.engage(tt, R0, unavailable, { roster: pool });
  check("S2: 3 cells, 5 substitutes -> covered 3", e.covered === 3, "covered=" + e.covered);
  check("S2: uncovered 0", e.uncovered.length === 0);
}

// =====================================================================
// SYNTHETIC 3 — a pool member who IS busy at that slot is skipped
// =====================================================================
{
  const tt = {
    S1: [[[ "A", N("Naeem") ]], ],
    S2: [[[ "B", N("V1") ]], ],        // V1 already has a class at MON P1
  };
  const unavailable = [{ teacher: N("Naeem"), days: ["MON"] }];
  const pool = [N("V1"), N("V2")];
  const e = IMPCC_SOLVER.engage(tt, R0, unavailable, { roster: pool });
  check("S3: busy pool member skipped -> cover is V2",
    e.assignments.length === 1 && e.assignments[0].cover === N("V2"),
    JSON.stringify(e.assignments));
}

// =====================================================================
// SYNTHETIC 4 — constraint filtering within the pool
// =====================================================================
{
  // Amir "never P1 · never P5" -> must not be chosen to cover MON P1
  const tt = {
    S1: [[[ "A", N("Naeem") ]], ],
  };
  const unavailable = [{ teacher: N("Naeem"), days: ["MON"] }];
  const pool = [N("Amir")];           // only candidate, but forbidden at P1
  const e = IMPCC_SOLVER.engage(tt, R0, unavailable, { roster: pool });
  check("S4: constraint-violating candidate skipped -> uncovered",
    e.covered === 0 && e.uncovered.length === 1, JSON.stringify(e));
}

// =====================================================================
// SYNTHETIC 5 — an unavailable teacher is never a substitute for others
// =====================================================================
{
  // Millat is on leave MON; Naeem also absent MON P2. Millat must not cover.
  const tt = {
    S1: [[ , [ "A", N("Naeem") ]], ],      // S1 MON P2 = Naeem (affected)
  };
  const unavailable = [
    { teacher: N("Naeem"), days: ["MON"], slots: ["P2"] },
    { teacher: N("Millat"), days: ["MON"] },   // Millat away all Monday
  ];
  const pool = [N("Millat"), N("V1")];
  const e = IMPCC_SOLVER.engage(tt, R0, unavailable, { roster: pool });
  check("S5: unavailable teacher never covers -> V1 chosen",
    e.assignments.length === 1 && e.assignments[0].cover === N("V1"),
    JSON.stringify(e.assignments));
}

// =====================================================================
// SYNTHETIC 6 — partial-duration unavailability only blocks its own periods
// =====================================================================
{
  // Jilani (no constraints) unavailable only MON P3. He MAY cover MON P1.
  const tt = {
    S1: [[[ "A", N("Naeem") ], , [ "C", N("Babar") ]], ],  // P1 Naeem, P3 Babar
  };
  const unavailable = [
    { teacher: N("Naeem"), days: ["MON"], slots: ["P1"] },
    { teacher: N("Babar"), days: ["MON"], slots: ["P3"] },
    { teacher: N("Jilani"), days: ["MON"], slots: ["P3"] }, // away only P3
  ];
  const pool = [N("Jilani"), N("V1")];
  const e = IMPCC_SOLVER.engage(tt, R0, unavailable, { roster: pool });
  const jilaniCoversP1 = e.assignments.some(a => a.cover === N("Jilani") && a.s === 0);
  const jilaniCoversP3 = e.assignments.some(a => a.cover === N("Jilani") && a.s === 2);
  check("S6: partially-unavailable teacher can cover outside his window", jilaniCoversP1);
  check("S6: ...but not inside it", !jilaniCoversP3);
}

// =====================================================================
// SYNTHETIC 7 — dual (PARALLEL) teacher string blocks both people
// =====================================================================
{
  const dual = N("PARALLEL"); // "Prof. Naeem Asghar / Prof. Ishfaq Ahmed"
  const tt = {
    S1: [[[ "Econ", dual ]], ],
  };
  // suspend only Ishfaq (one half) -> the shared period still needs a cover
  const e = IMPCC_SOLVER.engage(tt, R0, [{ teacher: N("Ishfaq"), days: ["MON"] }], { roster: [N("V1")] });
  check("S7: suspending one half of a dual block engages the shared period",
    e.affected.length === 1 && e.covered === 1, JSON.stringify(e));
}

// =====================================================================
// FUZZ — numerous randomized cases (the "observe the behaviour" sweep)
// =====================================================================
{
  const rng = mulberry32(99);
  function randTeacher() {
    const codes = Object.keys(FULL).filter(c => c !== "PARALLEL");
    return FULL[codes[Math.floor(rng() * codes.length)]];
  }
  function randSubset(arr, maxN) {
    const n = 1 + Math.floor(rng() * Math.min(maxN, arr.length));
    const copy = arr.slice();
    for (let i = copy.length - 1; i > 0; i--) { const j = Math.floor(rng() * (i + 1)); [copy[i], copy[j]] = [copy[j], copy[i]]; }
    return copy.slice(0, n);
  }
  let fuzzOk = true, fuzzDetail = "";
  let fuzzRuns = 0, fuzzAffected = 0, fuzzCovered = 0;
  for (let seed = 1; seed <= 12 && fuzzOk; seed++) {
    const res = IMPCC_SOLVER.generate({ maxCount: 1, timeMs: 9000, seed: seed * 131 + 7 });
    if (!res.solutions.length) continue;
    const tt = res.solutions[0].timetable;
    for (let i = 0; i < 25 && fuzzOk; i++) {
      const unavailable = [];
      const howMany = 1 + Math.floor(rng() * 3);
      for (let k = 0; k < howMany; k++) {
        unavailable.push({
          teacher: randTeacher(),
          days: randSubset(["MON", "TUE", "WED", "THU", "FRI"], 3),
          slots: randSubset(["P1", "P2", "P3", "P4", "P5"], 3),
        });
      }
      const e = IMPCC_SOLVER.engage(tt, R0, unavailable);
      fuzzRuns++; fuzzAffected += e.affected.length; fuzzCovered += e.covered;
      const iss = IMPCC_SOLVER.validateEngagement(tt, R0, e.assignments, unavailable);
      if (iss.length) { fuzzOk = false; fuzzDetail = "seed " + seed + " iter " + i + ": " + iss[0]; break; }
      if (e.assignments.length + e.uncovered.length !== e.affected.length) {
        fuzzOk = false; fuzzDetail = "seed " + seed + " iter " + i + ": partition mismatch"; break;
      }
      const e2 = IMPCC_SOLVER.engage(tt, R0, unavailable);
      if (JSON.stringify(e.assignments) !== JSON.stringify(e2.assignments)) {
        fuzzOk = false; fuzzDetail = "seed " + seed + " iter " + i + ": non-deterministic"; break;
      }
    }
  }
  check("FUZZ: " + fuzzRuns + " randomized cases all valid & deterministic (" +
    fuzzAffected + " affected, " + fuzzCovered + " covered, " +
    (fuzzAffected - fuzzCovered) + " uncovered)", fuzzOk, fuzzDetail);
}

// local mulberry32 (self-contained)
function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// =====================================================================
console.log("\n================== ENGAGEMENT FUZZ / EDGE RESULTS ==================");
console.log("passed: " + passed + "   failed: " + failed);
if (failures.length) {
  console.log("\nFAILURES:");
  failures.forEach(f => console.log("  ✗ " + f));
  process.exit(1);
} else {
  console.log("ALL FUZZ / EDGE TESTS PASSED ✓");
}
