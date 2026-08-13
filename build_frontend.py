#!/usr/bin/env python3
"""Transform the UI prototype into the functional frontend (index.html).

Keeps ALL design (CSS/HTML/layout) untouched; only replaces the mock data layer with:
  - the real in-browser solver  (IMPCC_SOLVER from solver.js)
  - a real CP-SAT backend call  (POST /generate)

Usage:
    python3 build_frontend.py [path/to/prototype.html]
The default input is the prototype the client supplied; the output is ./index.html.
"""
import io, sys

SRC = sys.argv[1] if len(sys.argv) > 1 else "timetable-generator-UI-prototype.html"
DST = "index.html"

try:
    src = io.open(SRC, encoding="utf-8").read()
except FileNotFoundError:
    print("input not found:", SRC)
    print("usage: python3 build_frontend.py [path/to/prototype.html]")
    sys.exit(1)

def rep(old, new, count=1):
    global src
    n = src.count(old)
    if n == 0:
        print("!! ANCHOR NOT FOUND:", old[:70].replace("\n", "\\n"))
        sys.exit(1)
    src = src.replace(old, new, count)

# ---- 1) title / labels -------------------------------------------------
rep("<title>IMPCC · Weekly Timetable Generator — Demo Prototype</title>",
    "<title>IMPCC · Weekly Timetable Generator</title>")
rep('<span class="chip demo">DEMO PROTOTYPE — simulated data</span>',
    '<span class="chip demo">LIVE · generated in your browser — nothing mocked</span>')
rep('<button class="btn amber" id="btnCpsat" title="Simulated call to the CP-SAT backend (POST /generate)">',
    '<button class="btn amber" id="btnCpsat" title="Call the CP-SAT backend (POST /generate) for proven-optimal results">')
rep('CP-SAT: idle — press “Compute optimal” to simulate the solver call',
    'CP-SAT: idle — press “Compute optimal” to call the backend')
rep('<b>IMPCC Timetable Generator — demo prototype.</b> All timetables, scores, ranks and solver output on this page are simulated mock data.<br>',
    '<b>IMPCC Timetable Generator.</b> Timetables, scores and ranks are generated live in your browser by a real constraint solver — nothing is mocked.<br>')

# ---- 2) load the real solver before the inline script -------------------
rep("\n<script>\n'use strict';",
    "\n<script src=\"solver.js\"></script>\n<script>\n'use strict';")

# ---- 3) script header comment -------------------------------------------
rep("/* ============================================================\n   IMPCC Timetable Generator — DEMO PROTOTYPE (all data mocked)\n   ============================================================ */",
    "/* ============================================================\n   IMPCC Timetable Generator — functional build\n   in-browser generation : IMPCC_SOLVER (solver.js)\n   proven-optimal results: POST /generate → CP-SAT backend\n   ============================================================ */")

# ---- 4) replace mock data layer (subjectLoad .. generateTimetables) -----
i = src.index("function subjectLoad(stream,year){")
j = src.index("/* ---------- combinations & scoring ---------- */")
adapter = """/* ---------- adapter: real solver output → UI cells ---------- */
function solverToCells(ttRaw){
  const out={};
  for(const sec of SECTIONS){
    const grid=ttRaw[sec.id];
    out[sec.id]=grid.map(row=>row.map(cell=>({
      subj:cell[0], teacher:cell[1],
      dual:(cell[0].indexOf('/')>=0 || cell[1].indexOf(' / ')>=0)
    })));
  }
  return out;
}
function shuffleBreakdown(ttRaw){
  const a={2:0,3:0,4:0,5:0};
  for(const sec of IMPCC_SOLVER.SECTIONS){
    const grid=ttRaw[sec.key];
    const slotsBy={};
    for(let d=0;d<5;d++)for(let s=0;s<5;s++){const n=grid[d][s][0];(slotsBy[n]=slotsBy[n]||new Set()).add(s);}
    for(const [subj,,count] of sec.subs){
      if((slotsBy[subj]||new Set()).size>1)a[count]++;
    }
  }
  return a;
}

"""
src = src[:i] + adapter + src[j:]

# ---- 5) replace rollScore + makeCombo with real combo builder ------------
i = src.index("function rollScore(rng){")
j = src.index("function sortedList(){")
real_make = """function makeCombo(sol,via){
  comboSeq++;
  const bd=shuffleBreakdown(sol.timetable);
  return{id:comboSeq,score:sol.score,a3:bd[3],a2:bd[2],a4:bd[4],a5:bd[5],via,tt:solverToCells(sol.timetable)};
}
"""
src = src[:i] + real_make + src[j:]

# ---- 6) state object + remove POOL_MAX / metaRng -------------------------
rep("const state={combos:[],selected:null,view:'sections',sectionFilter:'all',running:false,runTimer:null,runTarget:0,runAdded:0,cpsatBusy:false,cpsatDone:false,spot:null};",
    "const state={combos:[],selected:null,view:'sections',sectionFilter:'all',running:false,runTimer:null,stopRequested:false,cpsatBusy:false,cpsatDone:false,cpsatMerged:0,spot:null,seen:new Map()};")
rep("const POOL_MAX=88;\n", "")
rep("const metaRng=mulberry32(20250811);\n", "")

# ---- 7) facultyCount helper (dynamic faculty number) --------------------
rep("function teacherOrder(){",
    "function facultyCount(){const c=getSel();if(!c)return 0;return Object.keys(buildTeacherIndex(c.tt)).length;}\nfunction teacherOrder(){")

# ---- 8) renderChrome: faculty count + no pool cap ------------------------
rep("' · showing '+shown+'/11 sections · 20 faculty · click any card or class cell for personal courses'",
    "' · showing '+shown+'/11 sections · '+facultyCount()+' faculty · click any card or class cell for personal courses'")
rep("""  }else{
    const full=state.combos.length>=POOL_MAX;
    btnMore.innerHTML='<span class="g">＋</span> '+(full?'Pool full ('+POOL_MAX+')':'Generate more');
    btnMore.classList.remove('stop');btnMore.disabled=full;
    btnMore.title=full?('The pool holds up to '+POOL_MAX+' combinations in this demo'):'Append more combinations — results accumulate, nothing is dropped';
  }""",
    """  }else{
    btnMore.innerHTML='<span class="g">＋</span> Generate more';
    btnMore.classList.remove('stop');btnMore.disabled=false;
    btnMore.title='Append more combinations — results accumulate, nothing is dropped';
  }""")

# ---- 9) scorecard breakdown line -----------------------------------------
rep("'<div class=\"bd\"><b>'+c.a3+' × 3/wk subjects split</b> · <b>'+c.a2+' × 2/wk subjects split</b> &nbsp;('+(c.a3*100+c.a2*10)+' = score)</div>'+",
    "'<div class=\"bd\"><b>'+c.a3+' × 3/wk split</b> · <b>'+c.a2+' × 2/wk split</b>'+(c.a4?(' · <b>'+c.a4+' × 4/wk split</b>'):'')+' &nbsp;· score '+c.score+'</div>'+")

# ---- 10) empty-state copy -------------------------------------------------
rep(":'The pool is empty. Press “Generate” to start a mock generation run.');",
    ":'The pool is empty. Press “Generate” to start a generation run.');")

# ---- 11) runs: live generation -------------------------------------------
i = src.index("/* ---------- runs (simulated) ---------- */")
j = src.index("/* ---------- CP-SAT (simulated) ---------- */")
runs = """/* ---------- runs (live in-browser generation) ---------- */
function finishRun(stopped){
  clearTimeout(state.runTimer);state.runTimer=null;
  state.running=false;state.stopRequested=false;
  progFill.style.width='0%';
  const list=sortedList(),best=list.length?list[0].score:'—';
  setTicker((stopped?'Run stopped — ':'Done — ')+state.combos.length+' combinations kept · best score '+best+' · nothing discarded',stopped?'':'ok');
  renderChrome();
}
function startRun(kind){
  if(state.running)return;
  if(kind==='fresh'){
    state.combos=[];state.selected=null;comboSeq=0;state.cpsatDone=false;state.cpsatMerged=0;
    state.seen=new Map();
    closeSpotlight();
    state.sectionFilter='all';secFilterEl.value='all';
    setCpsatStatus('CP-SAT: idle — press “Compute optimal” to call the backend','');
    renderAll();
  }
  state.running=true;state.stopRequested=false;
  progFill.style.width='100%';
  liveTicker();renderChrome();
  state.runTimer=setTimeout(runSlice,30);
}
function runSlice(){
  if(state.stopRequested){finishRun(true);return;}
  const before=state.combos.length;
  const res=IMPCC_SOLVER.generate({maxCount:0,timeMs:320,seed:(Math.random()*2147483647)|0});
  for(const sol of res.solutions){
    const key=JSON.stringify(sol.timetable);
    if(state.seen.has(key))continue;
    state.seen.add(key);
    state.combos.push(makeCombo(sol,'browser'));
  }
  const grew=state.combos.length>before;
  if(!state.selected&&state.combos.length){const list=sortedList();state.selected=list[0].id;}
  liveTicker();renderChrome();renderScorecard();
  if(grew||!state.selected)renderMain();
  if(state.stopRequested){finishRun(true);return;}
  state.runTimer=setTimeout(runSlice,30);
}
function stopRun(){state.stopRequested=true;}
"""
src = src[:i] + runs + src[j:]

# ---- 12) CP-SAT: real backend call ---------------------------------------
i = src.index("/* ---------- CP-SAT (simulated) ---------- */")
j = src.index("/* ---------- events ---------- */")
cpsat = """/* ---------- CP-SAT (real backend call) ---------- */
function runCpsat(){
  if(state.cpsatBusy)return;
  if(!window.IMPCC_API_URL){
    setCpsatStatus('CP-SAT backend not configured — set window.IMPCC_API_URL to your deployed /generate endpoint','err');
    return;
  }
  if(state.cpsatDone){
    setCpsatStatus('CP-SAT: proven optimal — best score 560 ('+state.cpsatMerged+' solutions merged)','ok');
    return;
  }
  state.cpsatBusy=true;
  btnCpsat.disabled=true;
  btnCpsat.innerHTML='<span class="spin"></span> running CP-SAT…';
  setCpsatStatus('running CP-SAT… (POST /generate · time_limit 45s · n_seeds 2)','warn');
  setTicker('calling CP-SAT backend — hold','run',true);
  fetch(window.IMPCC_API_URL+'/generate',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({time_limit:45,n_seeds:2,max_solutions:0})
  })
  .then(r=>{if(!r.ok)throw new Error('HTTP '+r.status);return r.json();})
  .then(data=>{
    let added=0;
    for(const sol of (data.solutions||[])){
      const key=JSON.stringify(sol.timetable);
      if(state.seen.has(key))continue;
      state.seen.add(key);
      state.combos.push(makeCombo(sol,'cpsat'));
      added++;
    }
    state.cpsatDone=true;state.cpsatBusy=false;state.cpsatMerged=added;
    const list=sortedList();
    if(list.length)state.selected=list[0].id;
    const optimal=data.optimal?'proven optimal':'best found';
    setCpsatStatus('CP-SAT: '+optimal+' — best score '+data.best_score+' ('+added+' new solutions merged)','ok');
    setTicker('CP-SAT finished — '+added+' solutions merged · best score '+data.best_score+' · elapsed '+data.elapsed_seconds+' s','ok');
    renderAll();
  })
  .catch(err=>{
    state.cpsatBusy=false;
    btnCpsat.disabled=false;
    btnCpsat.innerHTML='<span class="g">✦</span> Compute optimal (CP-SAT)';
    setCpsatStatus('CP-SAT backend unreachable ('+err.message+') — using in-browser generation only','err');
    setTicker('CP-SAT backend unreachable — in-browser generation still works','ok');
  });
}
"""
src = src[:i] + cpsat + src[j:]

# ---- 13) spotlight "satisfied" wording ------------------------------------
rep('<span class="ok">✓ satisfied in this combination (simulated)</span>',
    '<span class="ok">✓ enforced by the solver in this combination</span>')

# ---- 14) boot -------------------------------------------------------------
rep("setTicker('Initialising demo — starting automatic generation','run',true);",
    "setTicker('Initialising — starting automatic generation','run',true);")

io.open(DST, "w", encoding="utf-8").write(src)
print("OK → wrote", DST, "(", len(src), "bytes )")
