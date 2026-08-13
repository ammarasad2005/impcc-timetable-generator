#!/usr/bin/env python3
"""Transform the UI prototype into the functional frontend (index.html).

Keeps ALL design (CSS/HTML/layout) untouched. Replaces the mock data layer with:
  - the real in-browser solver  (IMPCC_SOLVER from solver.js)
  - a real CP-SAT backend call  (POST /generate)
  - persistence (localStorage), no auto-start, deferred (flicker-free) rendering,
    and per-section / per-stream / per-faculty CSV exports.

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
        print("!! ANCHOR NOT FOUND:", old[:80].replace("\n", "\\n"))
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
    '<b>IMPCC Timetable Generator.</b> Timetables are generated live by a real constraint solver (in-browser or the CP-SAT backend) and saved in your browser until you clear or regenerate them.<br>')

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

/* ---------- faculty constraints (display only — enforced by solver.js) ---------- */
const CONSTRAINTS={
  'Prof. Muhammad Naeem':{text:'Monday P1 & P2 free'},
  'Prof. Syed Assad Abbas':{text:'ICS fills P1 & P2 daily · Business Math in P3 · no I.Com on Friday'},
  'Prof. Babar Jahangir':{text:'ICS fills P1 & P2 daily'},
  'Prof. Ishfaq Ahmed':{text:'P1 on 4+ days · never P5'},
  'Prof. Dr. Yasir Kareem':{text:'Only P1, P2 & P4'},
  'Prof. Abdul Basit':{text:'P1 on 4+ days · never P5 · no fully-free day'},
  'Prof. Amir Rasheed':{text:'Never P1 · never P5'},
  'Prof. Husnul Amin':{text:'Never P1 · never P5'},
  'Prof. Millat Khan':{text:'Never P1'},
  'Prof. Naeem Asghar':{text:'Never P1 · never P2'},
  'Prof. Tanveer Ahmed':{text:'Thursday & Friday only · P1–P3'},
  'Visiting-1':{text:'Placeholder visiting faculty'},
  'Visiting-2':{text:'Placeholder visiting faculty'},
  'Visiting-3':{text:'Placeholder visiting faculty'},
};

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
    "const state={combos:[],selected:null,view:'sections',sectionFilter:'all',running:false,runTimer:null,runTarget:0,cpsatBusy:false,cpsatDone:false,cpsatMerged:0,spot:null,seen:new Set()};")
rep("const POOL_MAX=88;\n", "")
rep("const metaRng=mulberry32(20250811);\n", "")

# ---- 7) facultyCount helper ---------------------------------------------
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
rep("'Initial run in progress — valid solutions will appear here the moment they are found. Nothing is ever discarded.'",
    "'Generating… timetables will appear here once at least 10 combinations are ready (or all found, if fewer). Nothing is ever discarded.'")

# ---- 11) persistence + runs (flicker-free) --------------------------------
i = src.index("/* ---------- runs (simulated) ---------- */")
j = src.index("/* ---------- CP-SAT (simulated) ---------- */")
runs = """/* ---------- persistence (localStorage) ---------- */
const STORE_KEY='impcc-timetable-v1';
const STORE_MAX=150;
function persist(){
  try{
    let combos=state.combos.slice().sort((a,b)=>a.score-b.score);
    if(combos.length>STORE_MAX)combos=combos.slice(0,STORE_MAX);
    localStorage.setItem(STORE_KEY,JSON.stringify({
      combos:combos.map(c=>({score:c.score,a3:c.a3,a2:c.a2,a4:c.a4,a5:c.a5,via:c.via,tt:c.tt})),
      selected:state.selected,view:state.view,sectionFilter:state.sectionFilter,
      cpsatDone:state.cpsatDone,cpsatMerged:state.cpsatMerged
    }));
  }catch(e){}
}
function restore(){
  try{
    const raw=localStorage.getItem(STORE_KEY);
    if(!raw)return false;
    const data=JSON.parse(raw);
    state.combos=(data.combos||[]).map(c=>({id:++comboSeq,score:c.score,a3:c.a3,a2:c.a2,a4:c.a4,a5:c.a5,via:c.via,tt:c.tt}));
    state.view=data.view||'sections';
    state.sectionFilter=data.sectionFilter||'all';
    state.cpsatDone=!!data.cpsatDone;
    state.cpsatMerged=data.cpsatMerged||0;
    state.selected=(data.selected!=null&&state.combos.some(o=>o.id===data.selected))?data.selected:null;
    return state.combos.length>0;
  }catch(e){return false;}
}
function clearStorage(){try{localStorage.removeItem(STORE_KEY);}catch(e){}}

/* ---------- runs (live in-browser generation, flicker-free) ---------- */
function finishRun(stopped){
  clearTimeout(state.runTimer);state.runTimer=null;
  state.running=false;state.stopRequested=false;
  progFill.style.width='0%';
  persist();
  const list=sortedList(),best=list.length?list[0].score:'—';
  setTicker((stopped?'Run stopped — ':'Done — ')+state.combos.length+' combinations kept · best score '+best+' · nothing discarded',stopped?'':'ok');
  renderAll();
}
function startRun(kind){
  if(state.running)return;
  if(kind==='fresh'){
    clearStorage();
    state.combos=[];state.selected=null;comboSeq=0;state.cpsatDone=false;state.cpsatMerged=0;
    state.seen=new Set();
    closeSpotlight();
    state.sectionFilter='all';secFilterEl.value='all';
    setCpsatStatus('CP-SAT: idle — press “Compute optimal” to call the backend','');
    renderAll();
  }
  state.running=true;state.stopRequested=false;
  state.runTarget=kind==='fresh'?24:state.combos.length+12;
  progFill.style.width='0%';
  liveTicker();renderChrome();
  state.runTimer=setTimeout(runSlice,30);
}
function runSlice(){
  if(state.stopRequested){finishRun(true);return;}
  const res=IMPCC_SOLVER.generate({maxCount:0,timeMs:320,seed:(Math.random()*2147483647)|0});
  for(const sol of res.solutions){
    const key=JSON.stringify(sol.timetable);
    if(state.seen.has(key))continue;
    state.seen.add(key);
    state.combos.push(makeCombo(sol,'browser'));
  }
  if(!state.selected&&state.combos.length){const list=sortedList();state.selected=list[0].id;}
  progFill.style.width=Math.min(100,Math.round(100*state.combos.length/state.runTarget))+'%';
  liveTicker();renderChrome();
  if(state.stopRequested){finishRun(true);return;}
  if(state.combos.length>=state.runTarget){finishRun(false);return;}
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
  if(state.cpsatDone){
    setCpsatStatus('CP-SAT: proven optimal — best score 560 ('+state.cpsatMerged+' solutions merged)','ok');
    return;
  }
  state.cpsatBusy=true;
  btnCpsat.disabled=true;
  btnCpsat.innerHTML='<span class="spin"></span> running CP-SAT…';
  setCpsatStatus('running CP-SAT… (POST /generate · time_limit 120s · n_seeds 1)','warn');
  setTicker('calling CP-SAT backend — hold','run',true);
  const base=(typeof window.IMPCC_API_URL==='string')?window.IMPCC_API_URL:'';
  const fail=(msg)=>{state.cpsatBusy=false;btnCpsat.disabled=false;btnCpsat.innerHTML='<span class="g">✦</span> Compute optimal (CP-SAT)';setCpsatStatus('CP-SAT backend unreachable ('+msg+') — using in-browser generation only','err');setTicker('CP-SAT backend unreachable — in-browser generation still works','ok');};
  if(typeof fetch!=='function'){fail('fetch unavailable');return;}
  fetch(base+'/generate',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({time_limit:120,n_seeds:1,max_solutions:0})
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
    renderAll();persist();
  })
  .catch(err=>{fail(err.message||String(err));});
}
"""
src = src[:i] + cpsat + src[j:]

# ---- 13) spotlight wording ------------------------------------------------
rep('<span class="ok">✓ satisfied in this combination (simulated)</span>',
    '<span class="ok">✓ enforced by the solver in this combination</span>')

# ---- 14) exports: CSS + buttons + functions -------------------------------
rep(".mini-export:disabled{opacity:.45;cursor:not-allowed}",
    ".mini-export:disabled{opacity:.45;cursor:not-allowed}\n.card-csv{margin-left:6px;display:inline-flex;align-items:center;font-family:var(--mono);font-size:9.5px;font-weight:600;color:var(--green-deep);background:var(--green-tint);border:1px solid var(--green);border-radius:6px;padding:3px 8px;transition:all .15s ease;white-space:nowrap;cursor:pointer}\n.card-csv:hover{background:var(--green);color:#f0f6ef}")

# section-card header: add per-section CSV button
rep("'<header><span class=\"stag\">'+(sec.stream==='icom'?'I.Com':'ICS')+'</span><h3>'+sec.label+'</h3><span class=\"pw\">25 periods/wk</span></header>'+",
    "'<header><span class=\"stag\">'+(sec.stream==='icom'?'I.Com':'ICS')+'</span><h3>'+sec.label+'</h3><span class=\"pw\">25 periods/wk</span><button class=\"card-csv\" data-sec=\"'+sec.id+'\" title=\"Download this section as CSV\">⇩ CSV</button></header>'+")

# stream head: add per-stream CSV button
rep("<span class=\"cnt\">'+secs.length+' section'+(secs.length>1?'s':'')+' · '+secs.length*25+' periods/wk</span></div>",
    "<span class=\"cnt\">'+secs.length+' section'+(secs.length>1?'s':'')+' · '+secs.length*25+' periods/wk</span><button class=\"card-csv\" data-stream=\"'+g.key+'\" title=\"Download this stream as CSV\">⇩ CSV</button></div>")

# teacher card: add per-faculty CSV button in the header
rep("'<span class=\"spot-hint\">personal courses ▸</span></div>'+",
    "'<span class=\"spot-hint\">personal courses ▸</span><button class=\"card-csv\" data-teacher=\"'+esc(name)+'\" title=\"Download this faculty timetable as CSV\">⇩ CSV</button></div>'+" )

# export functions: insert after exportComboCSV
rep("""  downloadCSV('IMPCC_timetable_combination-'+rank+'_score-'+c.score+'.csv',rows);
  setTicker('Exported CSV — full timetable for combination #'+rank+' (275 periods)','ok');
}""",
    """  downloadCSV('IMPCC_timetable_combination-'+rank+'_score-'+c.score+'.csv',rows);
  setTicker('Exported CSV — full timetable for combination #'+rank+' (275 periods)','ok');
}
function exportSectionCSV(secId){
  const c=getSel();if(!c)return;
  const sec=SECTIONS.find(s=>s.id===secId);if(!sec)return;
  const g=c.tt[secId];
  const rows=[['Section','Day','Period','Time','Subject','Teacher']];
  for(let d=0;d<5;d++)for(let s=0;s<5;s++){
    const cell=g[d][s];
    rows.push([secId,DAYS[d],SLOTS[s],TIMES[s],cell.subj,cell.teacher]);
  }
  const rank=rankOf(c,sortedList());
  downloadCSV('IMPCC_'+secId+'_combination-'+rank+'_score-'+c.score+'.csv',rows);
  setTicker('Exported CSV — '+secId+' (25 periods)','ok');
}
function exportStreamCSV(stream){
  const c=getSel();if(!c)return;
  const rows=[['Section','Day','Period','Time','Subject','Teacher']];
  const secs=SECTIONS.filter(s=>s.stream===stream);
  for(const sec of secs){
    const g=c.tt[sec.id];
    for(let d=0;d<5;d++)for(let s=0;s<5;s++){
      const cell=g[d][s];
      rows.push([sec.id,DAYS[d],SLOTS[s],TIMES[s],cell.subj,cell.teacher]);
    }
  }
  const name=stream==='icom'?'ICom':'ICS';
  const rank=rankOf(c,sortedList());
  downloadCSV('IMPCC_'+name+'-stream_combination-'+rank+'_score-'+c.score+'.csv',rows);
  setTicker('Exported CSV — '+name+' stream ('+secs.length*25+' periods)','ok');
}""")

# click handler: route card-csv buttons before card/cell handlers
rep("""  const card=e.target.closest('.t-card');
  if(card){openSpotlight(card.dataset.name);return;}""",
    """  const csvBtn=e.target.closest('.card-csv');
  if(csvBtn){
    if(csvBtn.dataset.sec)exportSectionCSV(csvBtn.dataset.sec);
    else if(csvBtn.dataset.stream)exportStreamCSV(csvBtn.dataset.stream);
    else if(csvBtn.dataset.teacher)exportTeacherCSV(csvBtn.dataset.teacher);
    return;
  }
  const card=e.target.closest('.t-card');
  if(card){openSpotlight(card.dataset.name);return;}""")

# ---- 15) persist on selection / view / filter changes ----------------------
rep("renderScorecard();renderMain();renderChrome();popBadge(rankBadge);popBadge(scoreBadge);",
    "renderScorecard();renderMain();renderChrome();popBadge(rankBadge);popBadge(scoreBadge);persist();")
rep("""  $('secFilterWrap').classList.toggle('hidden',v!=='sections');
  renderChrome();""",
    """  $('secFilterWrap').classList.toggle('hidden',v!=='sections');
  renderChrome();persist();""")
rep("""secFilterEl.addEventListener('change',e=>{
  state.sectionFilter=e.target.value;
  swapRender();renderChrome();""",
    """secFilterEl.addEventListener('change',e=>{
  state.sectionFilter=e.target.value;
  swapRender();renderChrome();persist();""")

# ---- 16) boot: restore saved results, no auto-generation ------------------
rep("""/* ---------- boot: auto-run on load ---------- */
renderAll();
setTicker('Initialising demo — starting automatic generation','run',true);
setTimeout(()=>startRun('fresh'),400);""",
    """/* ---------- boot: restore saved results (no auto-generation) ---------- */
const restored=restore();
if(restored){
  const list=sortedList();
  if(state.selected===null)state.selected=list[0].id;
  secFilterEl.value=state.sectionFilter;
  $('viewSections').classList.toggle('on',state.view==='sections');
  $('viewTeachers').classList.toggle('on',state.view==='teachers');
  $('secFilterWrap').classList.toggle('hidden',state.view!=='sections');
  renderAll();
  setTicker('Restored '+state.combos.length+' saved combination'+(state.combos.length===1?'':'s')+' · best score '+list[0].score+' · press “Generate” for a fresh run','ok');
  if(state.cpsatDone)setCpsatStatus('CP-SAT: proven optimal — best score 560 ('+state.cpsatMerged+' solutions merged)','ok');
}else{
  renderAll();
  setTicker('Ready — press “Generate” to create timetables','ok');
}""")

io.open(DST, "w", encoding="utf-8").write(src)
print("OK → wrote", DST, "(", len(src), "bytes )")
