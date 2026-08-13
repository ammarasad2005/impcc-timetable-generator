/* app.js — UI for the IMPCC live timetable generator (uses IMPCC_SOLVER global). */
(function () {
  "use strict";
  const S = window.IMPCC_SOLVER;
  const $ = s => document.querySelector(s);

  const state = {
    solutions: [],   // [{score, timetable}]
    view: "sec",
    generating: false,
    best: null
  };

  const DAYS = S.DAYS;
  const TIMES = ["08:30-09:10", "09:10-09:50", "09:50-10:30", "10:30-10:55", "10:55-11:35", "11:35-12:15"];
  const PERIODS = ["Period-1", "Period-2", "Period-3", "Break", "Period-4", "Period-5"];

  function sectionTitle(k) {
    const p = k.split("-");
    return p[0] + "-" + p[1] + " (Section-" + p[2] + ")";
  }
  function streamOf(k) { return k.indexOf("I.COM") === 0 ? "com" : "ics"; }

  // ------------------------------------------------------------ generation
  function runGeneration(totalMs, maxCount) {
    if (state.generating) return;
    state.generating = true;
    state.solutions = [];
    const seen = new Map();
    const t0 = Date.now();
    $("#genbtn").disabled = true;
    $("#genbtn").textContent = "Generating…";

    function tick() {
      const budget = Math.min(700, Math.max(250, totalMs - (Date.now() - t0)));
      const res = S.generate({ maxCount: 40, timeMs: budget, seed: (Math.random() * 2147483647) | 0 });
      for (const sol of res.solutions) {
        const key = JSON.stringify(sol.timetable);
        if (!seen.has(key)) seen.set(key, sol);
      }
      state.solutions = Array.from(seen.values()).sort((a, b) => a.score - b.score);
      state.solutions.forEach((s, i) => { s.rank = i + 1; });

      const done = (Date.now() - t0) >= totalMs || state.solutions.length >= maxCount;
      $("#progress").textContent =
        "found " + state.solutions.length + " valid combination" + (state.solutions.length === 1 ? "" : "s") +
        (state.solutions.length ? " · best score " + state.solutions[0].score : "");

      if (done) {
        state.generating = false;
        $("#genbtn").disabled = false;
        $("#genbtn").textContent = "Generate again";
        $("#progress").textContent =
          "Done — " + state.solutions.length + " valid combinations in " +
          ((Date.now() - t0) / 1000).toFixed(1) + "s · best score " +
          (state.solutions[0] ? state.solutions[0].score : "—");
        populateSelector();
        render(0);
      } else {
        setTimeout(tick, 0);
      }
    }
    setTimeout(tick, 30);
  }

  function populateSelector() {
    const sel = $("#combo");
    sel.innerHTML = "";
    state.solutions.forEach((s, i) => {
      const o = document.createElement("option");
      o.value = i;
      o.textContent = "#" + s.rank + " — score " + s.score;
      sel.appendChild(o);
    });
  }

  // ------------------------------------------------------------ rendering
  function renderSections(sol) {
    const grid = $("#grid");
    grid.innerHTML = "";
    grid.className = "grid";
    S.SECTIONS.forEach(sec => {
      const tt = sol.timetable[sec.key];
      const card = document.createElement("div");
      card.className = "card " + streamOf(sec.key);
      let h = "<h2>" + sectionTitle(sec.key) + "</h2><table><thead><tr><th>Days</th>";
      PERIODS.forEach(p => { h += "<th>" + p + "</th>"; });
      h += "</tr><tr>" + TIMES.map(t => "<th>" + t + "</th>").join("") + "</tr></thead><tbody>";
      for (let d = 0; d < 5; d++) {
        const row = tt[d];
        h += "<tr><td class='day'>" + DAYS[d] + "</td>";
        for (let s = 0; s < 5; s++) {
          if (s === 3) { h += "<td class='break-cell'>Break</td>"; continue; }
          const slot = s < 3 ? s : s - 1;
          const subj = row[slot][0], tchr = row[slot][1];
          const par = subj.indexOf("/") >= 0;
          h += "<td" + (par ? " class='par'" : "") + "><span class='subj'>" + subj + "</span><span class='tchr'>" + tchr + "</span></td>";
        }
        h += "</tr>";
      }
      h += "</tbody></table>";
      card.innerHTML = h;
      grid.appendChild(card);
    });
  }

  function renderTeachers(sol) {
    const grid = $("#grid");
    grid.innerHTML = "";
    grid.className = "tgrid";
    const sched = {};
    S.SECTIONS.forEach(sec => {
      const tt = sol.timetable[sec.key];
      for (let d = 0; d < 5; d++) for (let s = 0; s < 5; s++) {
        const subj = tt[d][s][0], t = tt[d][s][1];
        t.split(" / ").forEach(n => {
          n = n.trim();
          (sched[n] = sched[n] || []).push([d, s, sec.key, subj]);
        });
      }
    });
    Object.keys(sched).sort().forEach(name => {
      const rows = sched[name].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
      const card = document.createElement("div");
      card.className = "tcard";
      let h = "<div class='tname'>" + name + "</div><div class='tload'>" + rows.length + " periods/week</div>";
      const rule = S.RULES[name];
      if (rule) h += "<div class='trule'>" + rule + "</div>";
      h += "<ul>";
      rows.forEach(r => {
        h += "<li><span class='dp'>" + DAYS[r[0]] + " P" + (r[1] + 1) + "</span>" + r[2] + " — " + r[3] + "</li>";
      });
      h += "</ul>";
      card.innerHTML = h;
      grid.appendChild(card);
    });
  }

  function render(combo) {
    const sol = state.solutions[combo];
    if (!sol) return;
    $("#rank").textContent = "Rank #" + sol.rank + " / " + state.solutions.length;
    $("#score").textContent = "score " + sol.score + " (lower = better)";
    if (state.view === "sec") renderSections(sol); else renderTeachers(sol);
  }

  // ------------------------------------------------------------ wiring
  $("#genbtn").addEventListener("click", () => runGeneration(12000, 24));
  $("#combo").addEventListener("change", e => render(+e.target.value));
  $("#btnSec").addEventListener("click", () => {
    state.view = "sec";
    $("#btnSec").classList.add("on"); $("#btnTch").classList.remove("on");
    render(+$("#combo").value);
  });
  $("#btnTch").addEventListener("click", () => {
    state.view = "tch";
    $("#btnTch").classList.add("on"); $("#btnSec").classList.remove("on");
    render(+$("#combo").value);
  });
  $("#printbtn").addEventListener("click", () => window.print());

  // kick off
  runGeneration(12000, 24);
})();
