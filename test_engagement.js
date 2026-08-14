// test_engagement.js — extensive tests for the substitute ("engage the slot") engine.
// Run: node test_engagement.js
const IMPCC_SOLVER = require("./solver.js");
const DAYS = IMPCC_SOLVER.DAYS, SLOTS = IMPCC_SOLVER.SLOTS;
const NAME_TO_CODE = IMPCC_SOLVER.NAME_TO_CODE;

let passed = 0, failed = 0;
const failures = [];
function check(name, cond, extra) {
  if (cond) { passed++; }
  else { failed++; failures.push(name + (extra ? "  [" + extra + "]" : "")); }
}

// ---- helpers ---------------------------------------------------------------
function gen(timeMs, seed) {
  const res = IMPCC_SOLVER.generate({ maxCount: 1, timeMs: timeMs || 12000, seed: seed || 1 });
  return res.solutions[0] ? res.solutions[0].timetable : null;
}
function teacherCells(tt, fullName) {
  const out = [];
  for (const sec in tt) for (let d = 0; d < 5; d++) for (let s = 0; s < 5; s++)
    if (tt[sec][d][s][1] === fullName) out.push({ sec, d, s, subj: tt[sec][d][s][0] });
  return out;
}
// full-name string of a cell (as in timetable)
function cellTeacher(tt, sec, d, s) { return tt[sec][d][s][1]; }

// ---- core invariants for ANY engagement result ----------------------------
function assertEngagementValid(tt, R, eng, label) {
  // every affected cell is either covered or listed uncovered (partition)
  check(label + ": affected == covered + uncovered",
    eng.total === eng.affected.length &&
    eng.assignments.length + eng.uncovered.length === eng.affected.length);
  const issues = IMPCC_SOLVER.validateEngagement(tt, R, eng.assignments, eng._unavailable);
  check(label + ": validation passes (" + eng.assignments.length + " covers)",
    issues.length === 0, issues.slice(0, 5).join(" | "));
  // every cover is a different person from the slot holder
  for (const a of eng.assignments) {
    if ((a.coverCode || NAME_TO_CODE[a.cover]) === NAME_TO_CODE[a.teacher]) {
      check(label + ": cover != slot holder", false, a.sec + " " + a.cover);
      return;
    }
  }
  check(label + ": cover != slot holder", true);
  // determinism: same input -> identical output
  const eng2 = IMPCC_SOLVER.engage(tt, R, eng._unavailable);
  check(label + ": deterministic", JSON.stringify(eng.assignments) === JSON.stringify(eng2.assignments));
}

function run(tt, unavailable, R, label) {
  const eng = IMPCC_SOLVER.engage(tt, R, unavailable);
  eng._unavailable = unavailable;
  assertEngagementValid(tt, R, eng, label);
  return eng;
}

const R0 = IMPCC_SOLVER.resolveConstraints();
const tt = gen(12000, 20260814);
check("baseline timetable generated", !!tt);

if (tt) {
  // =====================================================================
  // CASE 1 — full-day unavailability of a HIGH-LOAD teacher (5/wk subject)
  // =====================================================================
  // Naeem teaches Principles of Accounting 5 periods/wk to I.COM-II-A/B/C.
  // Under the old redistribution model a full Monday block is INFEASIBLE.
  // Engagement must keep the timetable and cover Monday's 3 periods.
  const naeem = "Prof. Muhammad Naeem";
  const naeemMon = teacherCells(tt, naeem).filter(c => c.d === 0);
  check("CASE1: Naeem has Monday cells", naeemMon.length > 0);
  const eng1 = run(tt, [{ teacher: naeem, days: ["MON"] }], R0, "CASE1 full-day (Naeem MON)");
  check("CASE1: every Monday cell engaged", eng1.uncovered.length === 0, JSON.stringify(eng1.uncovered));
  check("CASE1: cover count == Naeem's Monday cells", eng1.covered === naeemMon.length,
    "covered=" + eng1.covered + " expected=" + naeemMon.length);
  // the rest of the timetable is untouched (engagement does not move other periods)
  let untouched = true;
  for (const c of teacherCells(tt, naeem)) if (c.d !== 0) untouched = untouched && tt[c.sec][c.d][c.s][1] === naeem;
  check("CASE1: other days untouched", untouched);

  // =====================================================================
  // CASE 2 — partial-duration unavailability (specific periods on a day)
  // =====================================================================
  // Naeem unavailable MON P3 only → exactly the MON P3 cells are engaged.
  const naeemMonP3 = teacherCells(tt, naeem).filter(c => c.d === 0 && c.s === 2);
  const eng2 = run(tt, [{ teacher: naeem, days: ["MON"], slots: ["P3"] }], R0, "CASE2 partial (Naeem MON P3)");
  check("CASE2: affected == Naeem's MON P3 cells", eng2.affected.length === naeemMonP3.length,
    "affected=" + eng2.affected.length + " expected=" + naeemMonP3.length);
  check("CASE2: all engaged", eng2.uncovered.length === 0);
  // a cell NOT in the window must not be engaged
  const outOfWindow = teacherCells(tt, naeem).filter(c => !(c.d === 0 && c.s === 2));
  const engagedSet = new Set(eng2.assignments.map(a => a.sec + "|" + a.d + "|" + a.s));
  let noExtra = true;
  for (const c of outOfWindow) if (engagedSet.has(c.sec + "|" + c.d + "|" + c.s)) noExtra = false;
  check("CASE2: no out-of-window cells engaged", noExtra);

  // =====================================================================
  // CASE 3 — a teacher with restrictive constraints NEVER gets a cover that
  //          violates them (Yasir only P1/P2/P4 · Amir never P1/P5 · Tanveer Thu/Fri)
  // =====================================================================
  // make MANY teachers unavailable on MANY windows and check every cover obeys
  // the cover's own constraints via validateEngagement (already asserted inside run()).
  const manyWindows = [
    { teacher: naeem, days: ["MON"] },
    { teacher: "Prof. Dr. Yasir Kareem", days: ["MON", "TUE"], slots: ["P3"] },   // Yasir can never cover P3
    { teacher: "Prof. Amir Rasheed", days: ["WED", "THU"], slots: ["P1", "P5"] }, // Amir can never cover P1/P5
    { teacher: "Prof. Tanveer Ahmed", days: ["MON", "WED"] },                     // Tanveer only Thu/Fri
    { teacher: "Prof. Millat Khan", days: ["FRI"], slots: ["P1"] },               // Millat never P1
    { teacher: "Prof. Husnul Amin", days: ["TUE"], slots: ["P1", "P5"] },         // Husnul never P1/P5
  ];
  run(tt, manyWindows, R0, "CASE3 many windows");
  // spot-check: no Yasir cover at P3 / on MON,TUE
  const eng3 = IMPCC_SOLVER.engage(tt, R0, manyWindows);
  let yasirBad = 0, amirBad = 0, tanveerBad = 0;
  for (const a of eng3.assignments) {
    if (a.cover === "Prof. Dr. Yasir Kareem" && (a.s === 2)) yasirBad++;
    if (a.cover === "Prof. Amir Rasheed" && (a.s === 0 || a.s === 4)) amirBad++;
    if (a.cover === "Prof. Tanveer Ahmed" && (a.d < 3)) tanveerBad++;
  }
  check("CASE3: Yasir never covers P3", yasirBad === 0, "violations=" + yasirBad);
  check("CASE3: Amir never covers P1/P5", amirBad === 0, "violations=" + amirBad);
  check("CASE3: Tanveer never covers Mon-Wed", tanveerBad === 0, "violations=" + tanveerBad);

  // =====================================================================
  // CASE 4 — "does not have a class of himself in that slot" (no double booking)
  // =====================================================================
  // Exhaustive: for EVERY assignment, the cover must be free (not teaching) at that
  // day+slot in the original timetable. (validateEngagement checks this; assert here too.)
  const eng4 = IMPCC_SOLVER.engage(tt, R0, [{ teacher: naeem, days: ["MON", "TUE", "WED", "THU", "FRI"] }]);
  let doubleBooked = 0;
  for (const a of eng4.assignments) {
    const cc = NAME_TO_CODE[a.cover] || a.cover;
    let busy = false;
    for (const sec in tt) for (let d = 0; d < 5; d++) for (let s = 0; s < 5; s++) {
      const names = tt[sec][d][s][1].split(" / ").map(n => NAME_TO_CODE[n] || n);
      if (d === a.d && s === a.s && names.indexOf(cc) >= 0) busy = true;
    }
    if (busy) doubleBooked++;
  }
  check("CASE4: zero double-booked covers across a full-week suspension", doubleBooked === 0,
    "doubleBooked=" + doubleBooked + " of " + eng4.assignments.length);

  // =====================================================================
  // CASE 5 — maximum effort when substitutes are scarce
  // =====================================================================
  // Suspend EVERY teacher on Monday so almost nobody is free to cover → verify the
  // engine still covers the maximum possible and reports the rest honestly.
  const allTeachers = Object.keys(IMPCC_SOLVER.TEACHER_FULL).filter(c => c !== "PARALLEL")
    .map(c => IMPCC_SOLVER.TEACHER_FULL[c]);
  // everyone unavailable on MON except a single volunteer (V1)
  const scarce = allTeachers.filter(n => n !== "Visiting-1").map(n => ({ teacher: n, days: ["MON"] }));
  const eng5 = IMPCC_SOLVER.engage(tt, R0, scarce);
  // affected = every MON cell whose teacher is in `scarce` (all 11 sections have a MON teacher who is unavailable except cells taught by V1)
  const monCellsAll = [];
  for (const sec in tt) for (let s = 0; s < 5; s++) monCellsAll.push({ sec, s, subj: tt[sec][0][s][0], teacher: tt[sec][0][s][1] });
  const scarceSet = new Set(scarce.map(w => w.teacher));
  const affectedExpected = monCellsAll.filter(c => {
    return c.teacher.split(" / ").some(n => scarceSet.has(n));
  });
  check("CASE5: affected matches the scarce set", eng5.affected.length === affectedExpected.length,
    "affected=" + eng5.affected.length + " expected=" + affectedExpected.length);
  check("CASE5: no double-booking even when scarce",
    IMPCC_SOLVER.validateEngagement(tt, R0, eng5.assignments, scarce).length === 0);
  // the single free teacher (V1) can cover at most ONE cell per MON period
  // because a person cannot be in two rooms at once → coverage is capped honestly.
  check("CASE5: coverage never exceeds legal matching", eng5.covered <= 5,
    "covered=" + eng5.covered + " (V1 can be in only one room per period)");

  // =====================================================================
  // CASE 6 — dual PARALLEL block handled correctly
  // =====================================================================
  const parallelName = "Prof. Naeem Asghar / Prof. Ishfaq Ahmed";
  const parCells = teacherCells(tt, parallelName);
  if (parCells.length) {
    // suspend BOTH halves: use the dual label as the unavailable teacher
    const eng6 = run(tt, [{ teacher: parallelName, days: ["MON", "TUE"] }], R0, "CASE6 parallel dual");
    check("CASE6: parallel cells affected", eng6.affected.length >= 4, "affected=" + eng6.affected.length);
    // a cover for a parallel cell must be a single person, free at that slot
    const issues6 = IMPCC_SOLVER.validateEngagement(tt, R0, eng6.assignments, [{ teacher: parallelName, days: ["MON", "TUE"] }]);
    check("CASE6: parallel covers valid", issues6.length === 0, issues6.join(" | "));
  } else {
    check("CASE6: parallel cells exist in this seed", false, "no PARALLEL cells — pick another seed");
  }

  // =====================================================================
  // CASE 7 — spread the load: no single professor is dumped on
  // =====================================================================
  const eng7 = IMPCC_SOLVER.engage(tt, R0, [{ teacher: naeem, days: ["MON", "TUE", "WED", "THU", "FRI"] }]);
  const loads = Object.values(eng7.load);
  const maxLoad = loads.length ? Math.max.apply(null, loads) : 0;
  check("CASE7: max covers per substitute is reasonable (<=3)", maxLoad <= 3,
    "maxLoad=" + maxLoad + " loadMap=" + JSON.stringify(eng7.load));

  // =====================================================================
  // CASE 8 — determinism + property test across many seeds
  // =====================================================================
  const R = R0;
  let propertyOk = true, propDetail = "";
  for (let seed = 1; seed <= 8; seed++) {
    const t = gen(9000, seed * 7 + 1);
    if (!t) continue;
    const windows = [
      { teacher: naeem, days: ["MON"] },
      { teacher: "Prof. Syed Assad Abbas", days: ["MON", "TUE"], slots: ["P3", "P4"] },
      { teacher: "Prof. Abdul Basit", days: ["FRI"] },
      { teacher: "Prof. Ishfaq Ahmed", days: ["WED"], slots: ["P1", "P5"] },
    ];
    const e = IMPCC_SOLVER.engage(t, R, windows);
    const iss = IMPCC_SOLVER.validateEngagement(t, R, e.assignments, windows);
    if (iss.length) { propertyOk = false; propDetail = "seed " + seed + ": " + iss[0]; }
    const e2 = IMPCC_SOLVER.engage(t, R, windows);
    if (JSON.stringify(e.assignments) !== JSON.stringify(e2.assignments)) {
      propertyOk = false; propDetail = "seed " + seed + ": non-deterministic";
    }
  }
  check("CASE8: property test across 8 seeds (validity + determinism)", propertyOk, propDetail);

  // =====================================================================
  // CASE 9 — engagement does NOT modify the original timetable (pure overlay)
  // =====================================================================
  const before = JSON.stringify(tt);
  IMPCC_SOLVER.engage(tt, R0, [{ teacher: naeem, days: ["MON"] }]);
  check("CASE9: original timetable untouched by engage()", JSON.stringify(tt) === before);

  // =====================================================================
  // CASE 10 — absent teacher never chosen as a cover for anyone else
  // =====================================================================
  const eng10 = IMPCC_SOLVER.engage(tt, R0, [
    { teacher: naeem, days: ["MON"] },
    { teacher: "Prof. Syed Assad Abbas", days: ["MON"] },
  ]);
  let absentCover = 0;
  for (const a of eng10.assignments) {
    if (a.cover === naeem || a.cover === "Prof. Syed Assad Abbas") absentCover++;
  }
  check("CASE10: unavailable teachers never used as covers", absentCover === 0,
    "offenders=" + absentCover);
}

// =====================================================================
// SUMMARY
// =====================================================================
console.log("\n==================== ENGAGEMENT TEST RESULTS ====================");
console.log("passed: " + passed + "   failed: " + failed);
if (failures.length) {
  console.log("\nFAILURES:");
  failures.forEach(f => console.log("  ✗ " + f));
  process.exit(1);
} else {
  console.log("ALL TESTS PASSED ✓");
}
