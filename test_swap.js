// test_swap.js — tests for the interactive multi-cell swap engine (solver.js core).
const IMPCC_SOLVER = require("./solver.js");

let pass = 0, fail = 0;
const failures = [];
function check(n, c, x) { if (c) pass++; else { fail++; failures.push(n + (x ? "  [" + x + "]" : "")); } }

const R = IMPCC_SOLVER.resolveConstraints();
const tt = IMPCC_SOLVER.generate({ maxCount: 1, timeMs: 9000, seed: 5 }).solutions[0].timetable;

// helper: a single-teacher cell at a given (d,s) in a given section
function cell(sec, d, s) { return { sec, d, s }; }
function teacherOf(t, c) { return t[c.sec][c.d][c.s][1]; }

// ---- 1) swapAnalyze: cycles vs chains ----
const A = { sec: "I.COM-I-A", d: 0, s: 0 }, B = { sec: "I.COM-I-A", d: 0, s: 1 }, C = { sec: "I.COM-I-A", d: 0, s: 2 };
let an = IMPCC_SOLVER.swapAnalyze([{ from: A, to: B }, { from: B, to: A }]);
check("2-cycle -> net 0", an.net === 0 && an.circles.length === 1 && an.circles[0].length === 2, "net=" + an.net);
an = IMPCC_SOLVER.swapAnalyze([{ from: A, to: B }]);
check("single move -> net 2", an.net === 2 && an.vacant.length === 1 && an.conflicts.length === 1, "net=" + an.net);
an = IMPCC_SOLVER.swapAnalyze([{ from: A, to: B }, { from: B, to: C }]);
check("2-chain -> net 2", an.net === 2, "net=" + an.net);
an = IMPCC_SOLVER.swapAnalyze([{ from: A, to: B }, { from: B, to: C }, { from: C, to: A }]);
check("3-cycle -> net 0", an.net === 0 && an.circles[0].length === 3, "net=" + an.net);

// ---- 2) swapApply on a same-period cycle: rotate teachers, keep subjects ----
{
  // pick three cells in the SAME period (MON P1) across three sections
  const secs = ["I.COM-I-A", "I.COM-I-B", "I.COM-I-C"];
  const cells3 = secs.map(s => cell(s, 0, 0));
  const tA = teacherOf(tt, cells3[0]), tB = teacherOf(tt, cells3[1]), tC = teacherOf(tt, cells3[2]);
  const k = cells3.map(c => IMPCC_SOLVER.swapKeyOf(c.sec, c.d, c.s));
  const out = IMPCC_SOLVER.swapApply(tt, [[k[0], k[2], k[1]]]); // 0 takes 2, 2 takes 1, 1 takes 0
  check("swapApply: cell0 gets cell1's teacher", out[cells3[0].sec][0][0][1] === tB);
  check("swapApply: cell2 gets cell0's teacher", out[cells3[2].sec][0][0][1] === tA);
  check("swapApply: cell1 gets cell2's teacher", out[cells3[1].sec][0][0][1] === tC);
  let subsOk = true;
  for (const sec in tt) for (let d = 0; d < 5; d++) for (let s = 0; s < 5; s++)
    if (tt[sec][d][s][0] !== out[sec][d][s][0]) subsOk = false;
  check("swapApply: subjects unchanged", subsOk);
  // no double-booking in the result
  let db = 0;
  const seen = {};
  for (const sec in out) for (let d = 0; d < 5; d++) for (let s = 0; s < 5; s++) {
    for (const nm of out[sec][d][s][1].split(" / ")) {
      const code = IMPCC_SOLVER.NAME_TO_CODE[nm] || nm;
      const kk = d + "|" + s + "|" + code;
      if (seen[kk]) db++;
      seen[kk] = 1;
    }
  }
  check("swapApply (same-period): no double-booking", db === 0, "db=" + db);
}

// ---- 3) swapEvaluate: clean same-period swap -> net 0 ----
{
  const ev = IMPCC_SOLVER.swapEvaluate(tt, [{ from: cell("I.COM-I-A", 0, 0), to: cell("I.COM-I-B", 0, 0) }, { from: cell("I.COM-I-B", 0, 0), to: cell("I.COM-I-A", 0, 0) }], R);
  check("swapEvaluate: same-period 2-swap -> net 0", ev.net === 0 && ev.doubleBookings.length === 0, "net=" + ev.net);
}

// ---- 4) swapEvaluate: cross-time swap that double-books is detected ----
{
  const fake = {
    A: [[["E", "Prof. X"], ["M", "Prof. Y"]]],
    B: [[["U", "Prof. Y"], ["P", "Prof. X"]]]
  };
  // swap the two cells of section A: X(P1)->P2, Y(P2)->P1.
  // X already teaches B P2 and Y already teaches B P1 -> both double-booked.
  const ev = IMPCC_SOLVER.swapEvaluate(fake, [
    { from: { sec: "A", d: 0, s: 0 }, to: { sec: "A", d: 0, s: 1 } },
    { from: { sec: "A", d: 0, s: 1 }, to: { sec: "A", d: 0, s: 0 } }
  ], R);
  check("swapEvaluate detects double-bookings", ev.doubleBookings.length === 2 && ev.net === 2, "db=" + ev.doubleBookings.length + " net=" + ev.net);
}

// ---- 5) swapComplete: closes an open chain (same-period: always feasible) ----
{
  const A5 = { sec: "I.COM-I-A", d: 0, s: 0 }, B5 = { sec: "I.COM-I-B", d: 0, s: 0 }, C5 = { sec: "I.COM-I-C", d: 0, s: 0 };
  const res = IMPCC_SOLVER.swapComplete(tt, [{ from: A5, to: B5 }, { from: B5, to: C5 }], R);
  check("swapComplete resolves a chain", res.resolved === true, JSON.stringify(res.unresolved));
  check("swapComplete -> one 3-circle", res.circles.length === 1 && res.circles[0].length === 3, JSON.stringify(res.circles));
  check("swapComplete added one extra move", res.extraMoves.length === 1);
}

// ---- 6) constraint-blocked completion stays unresolved ----
{
  const fakeTT = {
    S1: [[["X", "Prof. Dr. Yasir Kareem"], ["Y", "Prof. Millat Khan"]]],
    S2: [[["Z", "Prof. Abdul Rauf"], ["W", "Prof. Ghulam Jilani"]]]
  };
  // S1P1(Yasir)->S2P1, S2P1(Rauf)->S1P2 ; displaced = Millat (never P1), vacant = S1P1.
  const res = IMPCC_SOLVER.swapComplete(fakeTT, [
    { from: { sec: "S1", d: 0, s: 0 }, to: { sec: "S2", d: 0, s: 0 } },
    { from: { sec: "S2", d: 0, s: 0 }, to: { sec: "S1", d: 0, s: 1 } }
  ], R);
  check("constraint-blocked completion is unresolved", res.resolved === false && res.unresolved.length === 1, JSON.stringify(res.unresolved));
}

// ---- 7) property: swaps preserve teacher loads + subjects across seeds ----
{
  let ok = true;
  for (let seed = 1; seed <= 6 && ok; seed++) {
    const t = IMPCC_SOLVER.generate({ maxCount: 1, timeMs: 8000, seed: seed * 31 }).solutions[0].timetable;
    const pool = [];
    for (const sec in t) for (let d = 0; d < 5; d++) for (let s = 0; s < 5; s++)
      if (t[sec][d][s][1].indexOf(" / ") < 0) pool.push({ sec, d, s });
    const p = pool.slice().sort(() => Math.random() - 0.5).slice(0, 3);
    if (p.length < 3) continue;
    const moves = [{ from: p[0], to: p[1] }, { from: p[1], to: p[2] }, { from: p[2], to: p[0] }];
    const an = IMPCC_SOLVER.swapAnalyze(moves);
    const out = IMPCC_SOLVER.swapApply(t, an.circles);
    const count = (ttt) => { const c = {}; for (const sec in ttt) for (let d = 0; d < 5; d++) for (let s = 0; s < 5; s++) { const n = ttt[sec][d][s][1]; c[n] = (c[n] || 0) + 1; } return c; };
    const c1 = count(t), c2 = count(out);
    for (const n in c1) if (c1[n] !== c2[n]) ok = false;
    for (const sec in t) for (let d = 0; d < 5; d++) for (let s = 0; s < 5; s++)
      if (t[sec][d][s][0] !== out[sec][d][s][0]) ok = false;
  }
  check("property: swaps preserve teacher loads and subjects (6 seeds)", ok);
}

console.log("\nSWAP CORE TESTS: passed " + pass + ", failed " + fail);
if (failures.length) { failures.forEach(f => console.log("  ✗ " + f)); process.exit(1); }
console.log("ALL SWAP CORE TESTS PASSED ✓");
