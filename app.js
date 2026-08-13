/* app.js — UI for the IMPCC live timetable generator (uses IMPCC_SOLVER global).
 *
 * Generation policy (per client request):
 *   - NO count cutoff: every distinct valid solution is kept and shown.
 *   - Generation is time-bounded; the user can keep extending the run with
 *     "Generate more" — new solutions are appended, never dropped, and the
 *     whole set is re-ranked by score.
 */
(function () {
  "use strict";
  const S = window.IMPCC_SOLVER;
  const $ = s => document.querySelector(s);

  const state = {
    solutions: [],   // [{score, timetable, rank}] ranked by score (asc)
    view: "sec",
    running: false,
    stopRequested: false,
    current: 0,
    runMs: 0,
    generatedMs: 0
  };

  const DAYS = S.DAYS;
  const TIMES = ["08:30-09:10", "09:10-09:50", "09:50-10:30", "10:30-10:55", "10:55-11:35", "11:35-12:15"];
  const PERIODS = ["Period-1", "Period-2", "Period-3", "Break", "Period-4", "Period-5"];
  const EXTEND_MS = 15000;   // each "Generate more" adds this much time

  // CP-SAT backend (optional). Set to your Cloud Run URL to enable the
  // "Compute optimal" button, or inject window.IMPCC_API_URL at page load.
  // Example: "https://impcc-cp-sat-xxxxxxxxxx-uc.a.run.app"
  const API_URL = (typeof window.IMPCC_API_URL === "string" && window.IMPCC_API_URL) || "";

  function sectionTitle(k) {
    const p = k.split("-");
    return p[0] + "-" + p[1] + " (Section-" + p[2] + ")";
  }
  function streamOf(k) { return k.indexOf("I.COM") === 0 ? "com" : "ics"; }

  // ------------------------------------------------------------ ranking info
  // Shuffle breakdown: how many subjects of each weekly-credit tier are split
  // across more than one period-slot (this is exactly what the score penalizes).
  function shuffleBreakdown(tt) {
    const tiers = { 5: 0, 4: 0, 3: 0, 2: 0 };
    for (const sec of S.SECTIONS) {
      const g = tt[sec.key];
      const slots = {};
      for (let d = 0; d < 5; d++) for (let s = 0; s < 5; s++) {
        const name = g[d][s][0];
        (slots[name] = slots[name] || new Set()).add(s);
      }
      for (const [subj, , count] of sec.subs) {
        const n = (slots[subj] || new Set()).size;
        if (n > 1) tiers[count] = (tiers[count] || 0) + 1;
      }
    }
    return tiers;
  }

  // Natural-language description of where this solution stands in the ranked set.
  function describeRank(sol, all) {
    const n = all.length;
    if (n === 0) return "—";
    const best = all[0].score;
    const gap = sol.score - best;
    if (n === 1) return "the only combination generated so far";
    if (gap === 0) {
      const ties = all.filter(s => s.score === best).length;
      return ties > 1 ? `tied for best (${ties} combinations share this score)` : "the best combination";
    }
    let tier;
    if (gap <= 10) tier = "near-optimal";
    else if (gap <= 40) tier = "very good";
    else if (gap <= 150) tier = "good";
    else if (gap <= 300) tier = "fair";
    else tier = "lower-ranked";
    return `${tier} — ${gap} shuffle point${gap === 1 ? "" : "s"} above the best (${best})`;
  }

  function percentile(sol, all) {
    const n = all.length;
    if (n <= 1) return "";
    if (sol.rank === 1) return "better than all the others";
    const pct = Math.round(((n - sol.rank) / (n - 1)) * 100);
    return `better than ${pct}% of the other ${n - 1}`;
  }

  // ------------------------------------------------------------ generation
  function rankAll() {
    state.solutions.sort((a, b) => a.score - b.score);
    state.solutions.forEach((s, i) => { s.rank = i + 1; });
  }

  function startRun() {
    if (state.running) return;
    state.running = true;
    state.stopRequested = false;
    state.runMs = EXTEND_MS;
    state.generatedMs = 0;      // fresh time budget for this run
    $("#genbtn").textContent = "Stop";
    $("#genbtn").classList.add("stop");
    loop();
  }

  function loop() {
    if (state.stopRequested) { finish(); return; }
    const t0 = Date.now();
    const budget = Math.min(700, Math.max(250, state.runMs - state.generatedMs));
    const res = S.generate({ maxCount: 0, timeMs: budget, seed: (Math.random() * 2147483647) | 0 });
    state.generatedMs += Date.now() - t0;

    // merge (dedupe by timetable) — never drop existing ones
    const seen = new Map();
    for (const s of state.solutions) seen.set(JSON.stringify(s.timetable), s);
    for (const sol of res.solutions) {
      const k = JSON.stringify(sol.timetable);
      if (!seen.has(k)) seen.set(k, sol);
    }
    state.solutions = Array.from(seen.values());
    rankAll();
    updateProgress(false);

    if (state.generatedMs >= state.runMs) { finish(); return; }
    setTimeout(loop, 0);
  }

  function finish() {
    state.running = false;
    $("#genbtn").textContent = "Generate more";
    $("#genbtn").classList.remove("stop");
    updateProgress(true);
    populateSelector();
    render(state.current);
  }

  function updateProgress(done) {
    const n = state.solutions.length;
    if (n === 0) { $("#progress").textContent = done ? "no solutions yet" : "searching…"; return; }
    const best = state.solutions[0].score;
    const worst = state.solutions[n - 1].score;
    $("#progress").textContent =
      (done ? "Stopped — " : "Live — ") + n + " valid combination" + (n === 1 ? "" : "s") +
      " found · best score " + best + " · worst " + worst +
      (state.running ? " · generating…" : " · nothing hidden, all ranked");
  }

  function populateSelector() {
    const sel = $("#combo");
    sel.innerHTML = "";
    state.solutions.forEach((s, i) => {
      const o = document.createElement("option");
      o.value = i;
      o.textContent = "#" + s.rank + "  ·  score " + s.score + "  ·  " + describeRank(s, state.solutions);
      sel.appendChild(o);
    });
  }

  // ------------------------------------------------------------ CP-SAT backend
  async function computeOptimal() {
    if (!API_URL) return;
    $("#optbtn").disabled = true;
    $("#optbtn").textContent = "Solving (CP-SAT)…";
    $("#optbadge").textContent = "running CP-SAT on the server…";
    try {
      const r = await fetch(API_URL + "/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ time_limit: 45, n_seeds: 2, max_solutions: 0 })
      });
      if (!r.ok) throw new Error("HTTP " + r.status);
      const data = await r.json();

      // merge into the existing set (union, never drop), then re-rank
      const seen = new Map();
      for (const s of state.solutions) seen.set(JSON.stringify(s.timetable), s);
      let added = 0;
      for (const sol of data.solutions || []) {
        const k = JSON.stringify(sol.timetable);
        if (!seen.has(k)) { seen.set(k, sol); added++; }
      }
      state.solutions = Array.from(seen.values());
      rankAll();
      updateProgress(true);
      populateSelector();
      render(0);

      $("#optbadge").textContent = data.optimal
        ? "CP-SAT: proven optimal — best score " + data.best_score + " (" + (data.total_found || 0) + " solutions; +" + added + " merged)"
        : "CP-SAT: best score " + data.best_score + " (" + (data.total_found || 0) + " solutions; +" + added + " merged)";
    } catch (e) {
      $("#optbadge").textContent = "CP-SAT backend unreachable (" + e.message + ") — using the in-browser solver only.";
    } finally {
      $("#optbtn").disabled = false;
      $("#optbtn").textContent = "Compute optimal (CP-SAT)";
    }
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
    state.current = combo;
    const n = state.solutions.length;
    const best = state.solutions[0].score;
    const b = shuffleBreakdown(sol.timetable);
    const gap = sol.score - best;

    $("#rank").textContent = "Rank #" + sol.rank + " / " + n;
    $("#score").textContent = "score " + sol.score + (gap === 0 ? "  ·  best" : "  ·  +" + gap + " vs best");
    $("#semantic").innerHTML =
      "<b>" + describeRank(sol, state.solutions) + "</b> · " + percentile(sol, state.solutions) +
      "<br>Shuffle detail: " + b[3] + "× 3/wk subjects split · " + b[2] + "× 2/wk subjects split" +
      (b[5] || b[4] ? " · <b>note:</b> " + (b[5] ? b[5] + "× 5/wk " : "") + (b[4] ? b[4] + "× 4/wk " : "") + "split (should not happen)" : "");

    if (state.view === "sec") renderSections(sol); else renderTeachers(sol);
    $("#combo").value = combo;
    $("#prevbtn").disabled = combo <= 0;
    $("#nextbtn").disabled = combo >= n - 1;
  }

  // ------------------------------------------------------------ wiring
  $("#genbtn").addEventListener("click", startRun);
  $("#optbtn").addEventListener("click", computeOptimal);
  if (!API_URL) {
    $("#optbtn").style.display = "none";
    $("#optbadge").textContent = "CP-SAT backend not configured (set API_URL / window.IMPCC_API_URL to enable).";
  }
  $("#combo").addEventListener("change", e => render(+e.target.value));
  $("#prevbtn").addEventListener("click", () => render(state.current - 1));
  $("#nextbtn").addEventListener("click", () => render(state.current + 1));
  $("#btnSec").addEventListener("click", () => {
    state.view = "sec";
    $("#btnSec").classList.add("on"); $("#btnTch").classList.remove("on");
    render(state.current);
  });
  $("#btnTch").addEventListener("click", () => {
    state.view = "tch";
    $("#btnTch").classList.add("on"); $("#btnSec").classList.remove("on");
    render(state.current);
  });
  $("#printbtn").addEventListener("click", () => window.print());

  // kick off
  startRun();
})();
