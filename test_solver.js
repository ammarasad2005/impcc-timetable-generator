// Node test harness for solver.js
const S = require("./solver.js");

const t0 = Date.now();
const res = S.generate({ maxCount: 25, timeMs: 20000, seed: 12345 });
const dt = Date.now() - t0;

console.log("elapsed(ms):", res.stats.elapsedMs, "| attempts:", res.stats.attempts,
            "| fills:", res.stats.fills, "| valid:", res.stats.valids, "| distinct:", res.stats.distinct);
console.log("scores:", res.solutions.map(s => s.score));

// double-check validity independently: reconstruct grids from timetable and validate
let allOk = true;
for (const sol of res.solutions) {
  // rebuild grid (sec -> day -> slot -> unit index) by matching subject+teacher back
  // simpler: call the internal validate via re-decoding is hard without unit refs,
  // so instead verify the structure here.
  const tt = sol.timetable;
  const seenTeacher = new Set();
  let ok = true;
  for (const key of res.meta.section_order) {
    const grid = tt[key];
    const perSubject = {};
    for (let d = 0; d < 5; d++) {
      const daySubj = new Set();
      for (let s = 0; s < 5; s++) {
        const [subj, tch] = grid[d][s];
        perSubject[subj] = (perSubject[subj] || 0) + 1;
        if (daySubj.has(subj)) { ok = false; console.log("TWICE", key, d, subj); }
        daySubj.add(subj);
        const tk = d + "-" + s + "-" + tch;
        if (seenTeacher.has(tk)) { ok = false; console.log("CLASH", tch, d, s); }
        seenTeacher.add(tk);
      }
    }
    // subject counts
    for (const subj of Object.keys(perSubject)) {
      if (perSubject[subj] !== 5 && !(perSubject[subj] === 4 || perSubject[subj] === 3 || perSubject[subj] === 2)) {
        ok = false; console.log("BAD COUNT", key, subj, perSubject[subj]);
      }
    }
  }
  if (!ok) allOk = false;
}
console.log("structure check all OK:", allOk);

if (res.solutions.length) {
  console.log("\nBest solution, ICS-II-B (parallel block) rows:");
  const tt = res.solutions[0].timetable["ICS-II-B"];
  tt.forEach((row, d) => console.log(" ", S.DAYS[d], row.map(c => c[0].padEnd(18)).join(" | ")));
}
