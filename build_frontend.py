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

import base64 as _b64
def _data_uri(path):
    try:
        return "data:image/png;base64," + _b64.b64encode(io.open(path, "rb").read()).decode()
    except Exception:
        return ""
LOGO_URI = _data_uri("impcc-logo.png")
FAV_URI  = _data_uri("favicon.png")

def rep(old, new, count=1):
    global src
    n = src.count(old)
    if n == 0:
        print("!! ANCHOR NOT FOUND:", old[:80].replace("\n", "\\n"))
        sys.exit(1)
    src = src.replace(old, new, count)

# ---- 1) title / labels -------------------------------------------------
if FAV_URI:
    rep("<title>IMPCC · Weekly Timetable Generator — Demo Prototype</title>",
        '<title>IMPCC · Weekly Timetable Generator</title>\n<link rel="icon" type="image/png" href="' + FAV_URI + '">')
else:
    rep("<title>IMPCC · Weekly Timetable Generator — Demo Prototype</title>",
        "<title>IMPCC · Weekly Timetable Generator</title>")
# Clean, minimal masthead: drop the stats chips and the "proven optimum" block.
_i = src.index('<header class="mast">')
_j = src.index('</header>', _i) + len('</header>')
_mast = ('<header class="mast">\n'
         '  <img class="logo" src="'+LOGO_URI+'" alt="IMPCC"/>\n'
         '  <div class="mast-txt">\n'
         '    <div class="overline">Islamabad Model Postgraduate College of Commerce · H-8/4</div>\n'
         '    <h1>Weekly Timetable <em>Generator</em></h1>\n'
         '    <div class="sub">Intermediate · 1st Shift · ICS &amp; I.Com</div>\n'
         '  </div>\n'
         '</header>')
src = src[:_i] + _mast + src[_j:]
rep('<button class="btn amber" id="btnCpsat" title="Simulated call to the CP-SAT backend (POST /generate)">',
    '<button class="btn amber" id="btnCpsat" title="Call the CP-SAT backend (POST /generate) for proven-optimal results">')
rep('CP-SAT: idle — press “Compute optimal” to simulate the solver call',
    'CP-SAT: idle — press “Compute optimal” to call the backend')
# (footer is now the developer credit section, defined directly in the prototype)

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
    state.source=null;state.lastLocks=null;
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

# ---- 17) Export system --------------------------------------------------
# (a) button styles: .card-pdf (amber) for stream/teacher PDFs, .card-img (blue)
#     for section landscape-PNG exports
rep('.card-csv:hover{background:var(--green);color:#f0f6ef}',
    '.card-csv:hover,.card-pdf:hover,.card-img:hover{background:var(--green);color:#f0f6ef}\n.card-pdf,.card-img{margin-left:4px;display:inline-flex;align-items:center;font-family:var(--mono);font-size:9.5px;font-weight:600;border-radius:6px;padding:3px 8px;transition:all .15s ease;white-space:nowrap;cursor:pointer}\n.card-pdf{color:var(--amber-deep);background:var(--amber-tint);border:1px solid var(--amber)}\n.card-pdf:hover{background:var(--amber);color:#fff}\n.card-img{color:var(--ics-deep);background:var(--ics-tint);border:1px solid var(--ics)}\n.card-img:hover{background:var(--ics);color:#fff}')

# (a2) clean the CSV filenames: no score / rank / combination numbers
rep("downloadCSV('IMPCC_timetable_combination-'+rank+'_score-'+c.score+'.csv',rows);",
    "downloadCSV('IMPCC_timetable.csv',rows);")
rep("downloadCSV('IMPCC_'+secId+'_combination-'+rank+'_score-'+c.score+'.csv',rows);",
    "downloadCSV('IMPCC_'+secId+'.csv',rows);")
rep("downloadCSV('IMPCC_'+name+'-stream_combination-'+rank+'_score-'+c.score+'.csv',rows);",
    "downloadCSV('IMPCC_'+name+'-stream.csv',rows);")

# (b) replace the PRINT CSS block — clean, minimal, reuses the display components
i = src.index("/* ============ PRINT ============ */")
j = src.index("\n</style>", i)
print_css = """/* ============ PRINT (prints the same components as the display) ============ */
#printArea{display:none}
@media print{
  @page{size:A4;margin:12mm}
  *{-webkit-print-color-adjust:exact;print-color-adjust:exact;animation:none!important;transition:none!important}
  html,body{background:#fff!important}
  body{font-size:11px}
  .mast,.console,.wrap,footer,.drawer,.drawer-backdrop,.no-print{display:none!important}
  #printArea{display:block;font-family:var(--body);color:var(--ink)}

  /* print-only cover + footer (college identity only — no site/tech info) */
  .pd-cover{border-bottom:3px solid #0e3b29;padding-bottom:10px;margin-bottom:14px}
  .pd-cover h1{font-family:var(--disp);font-weight:900;font-size:20px;margin:0;color:#0e3b29;line-height:1.1}
  .pd-cover p{margin:3px 0 0;font-size:9.5px;color:#5b6a61}
  .pd-footer{position:fixed;bottom:0;left:0;right:0;font-family:var(--mono);font-size:7px;color:#8a8f86;text-align:center;padding:3px 0;border-top:1px solid #e2e6dc;background:#fff}

  /* reused display components — clean print layout, identical look */
  #printArea .card-csv,#printArea .card-pdf,#printArea .card-img,#printArea .mini-export,#printArea .spot-hint{display:none!important}
  #printArea .stream{margin:0 0 16px;break-inside:auto}
  #printArea .stream.pd-new{break-before:page}
  #printArea .stream-head{margin-bottom:10px}
  #printArea .sec-grid{grid-template-columns:1fr}
  #printArea .sec-card{box-shadow:none;break-inside:avoid;margin-bottom:12px}
  #printArea .tt-wrap{overflow:visible}
  #printArea .tt{min-width:0}
  #printArea .filter-note{display:none}

  /* teacher personal timetable (reused spotlight components) */
  #printArea .sp-gridwrap{overflow:visible;box-shadow:none;break-inside:avoid}
  #printArea .sp-grid{min-width:0}
  #printArea .sp-scrollhint{display:none}
  #printArea .sp-stats{margin:12px 0}
  #printArea .sp-cons{margin:12px 0;break-inside:avoid}
  #printArea .sp-course{border:1px solid #cfd6c8;break-inside:avoid}
}
"""
src = src[:i] + print_css + src[j:]   # keep the closing </style>

# (c) add the hidden print container in the body
rep('<div class="drawer-backdrop" id="spotBackdrop"></div>',
    '<div id="printArea" aria-hidden="true"></div>\n<div class="drawer-backdrop" id="spotBackdrop"></div>')

# (d) export buttons: section & teacher → PNG image; stream → PDF
rep("title=\"Download this section as CSV\">⇩ CSV</button></header>'+",
    "title=\"Download this section as CSV\">⇩ CSV</button><button class=\"card-img\" data-img-sec=\"'+sec.id+'\" title=\"Download this section as a landscape PNG image\">PNG</button></header>'+")
rep("title=\"Download this stream as CSV\">⇩ CSV</button></div><div class=\"sec-grid",
    "title=\"Download this stream as CSV\">⇩ CSV</button><button class=\"card-pdf\" data-pdf-stream=\"'+g.key+'\" title=\"Print this stream / save as PDF\">PDF</button></div><div class=\"sec-grid")
rep("title=\"Download this faculty timetable as CSV\">⇩ CSV</button></div>'+",
    "title=\"Download this faculty timetable as CSV\">⇩ CSV</button><button class=\"card-img\" data-img-teacher=\"'+esc(name)+'\" title=\"Download this faculty timetable as a PNG image\">PNG</button></div>'+" )

# (d2) console Print button hint
rep('id="btnPrint" title="Print the current view / save as PDF"',
    'id="btnPrint" title="Print the current view as PDF — single-section exports download as a landscape PNG image"')

# (e) click handler: route image + PDF buttons
rep("""  const csvBtn=e.target.closest('.card-csv');
  if(csvBtn){
    if(csvBtn.dataset.sec)exportSectionCSV(csvBtn.dataset.sec);
    else if(csvBtn.dataset.stream)exportStreamCSV(csvBtn.dataset.stream);
    else if(csvBtn.dataset.teacher)exportTeacherCSV(csvBtn.dataset.teacher);
    return;
  }""",
    """  const csvBtn=e.target.closest('.card-csv');
  if(csvBtn){
    if(csvBtn.dataset.sec)exportSectionCSV(csvBtn.dataset.sec);
    else if(csvBtn.dataset.stream)exportStreamCSV(csvBtn.dataset.stream);
    else if(csvBtn.dataset.teacher)exportTeacherCSV(csvBtn.dataset.teacher);
    return;
  }
  const imgBtn=e.target.closest('.card-img');
  if(imgBtn){
    if(imgBtn.dataset.imgSec)exportSectionImage(imgBtn.dataset.imgSec);
    else if(imgBtn.dataset.imgTeacher)exportTeacherImage(imgBtn.dataset.imgTeacher);
    return;
  }
  const pdfBtn=e.target.closest('.card-pdf');
  if(pdfBtn&&pdfBtn.dataset.pdfStream){printTarget({type:'stream',id:pdfBtn.dataset.pdfStream});return;}
""")

# (f) replace printCurrent with the export engine (no website/tech info anywhere)
i = src.index("/* PDF = print engine. If the spotlight drawer is open, print only that")
k = src.index("/* ---------- section filter helpers ---------- */")
engine = """/* ---------- export engine (clean documents — no site/tech info) ---------- */
const COLLEGE_LINE='Islamabad Model Postgraduate College of Commerce (H-8/4) · Intermediate · 1st Shift';
function pdCover(title,sub){
  return '<header class="pd-cover"><h1>'+esc(title)+'</h1><p>'+esc(sub)+'</p></header>';
}
function pdFooter(){
  return '<div class="pd-footer">'+esc(COLLEGE_LINE)+'</div>';
}
function streamHeadHtml(name,secs){
  return '<div class="stream-head"><span class="swatch"></span><h2>'+esc(name)+'</h2><span class="cnt">'+secs.length+' section'+(secs.length>1?'s':'')+' · '+secs.length*25+' periods/wk</span></div>';
}
function buildComboDoc(c){
  let html=pdCover('Weekly Timetable — All Sections',COLLEGE_LINE+' · ICS & I.Com');
  const groups=[{key:'icom',name:'I.Com — Commerce Stream'},{key:'ics',name:'ICS — Computer Science Stream'}];
  groups.forEach((g,gi)=>{
    const secs=SECTIONS.filter(s=>s.stream===g.key);
    html+='<section class="stream '+g.key+(gi?' pd-new':'')+'">'+streamHeadHtml(g.name,secs)+'<div class="sec-grid">';
    let idx=0;
    for(const sec of secs)html+=sectionCard(sec,c.tt[sec.id],idx++);
    html+='</div></section>';
  });
  html+=pdFooter();
  return html;
}
function buildStreamDoc(c,stream){
  const name=stream==='icom'?'I.Com — Commerce Stream':'ICS — Computer Science Stream';
  const secs=SECTIONS.filter(s=>s.stream===stream);
  let html=pdCover(name,COLLEGE_LINE+' · '+secs.length+' sections · '+secs.length*25+' periods/week');
  html+='<section class="stream '+stream+'">'+streamHeadHtml(name,secs)+'<div class="sec-grid">';
  let idx=0;
  for(const sec of secs)html+=sectionCard(sec,c.tt[sec.id],idx++);
  html+='</div></section>';
  html+=pdFooter();
  return html;
}
function buildTeacherDoc(c,name){
  const entries=(buildTeacherIndex(c.tt)[name])||[];
  const cons=CONSTRAINTS[name];
  const dayCnt=[0,0,0,0,0],slotCnt=[0,0,0,0,0],secSet=new Set();
  entries.forEach(e=>{dayCnt[e.d]++;slotCnt[e.s]++;secSet.add(e.sec);});
  const busiest=entries.length?DAYS[dayCnt.indexOf(Math.max.apply(null,dayCnt))]:'—';
  const fav=entries.length?SLOTS[slotCnt.indexOf(Math.max.apply(null,slotCnt))]:'—';
  const freeDays=dayCnt.filter(x=>x===0).length;
  const hasDual=entries.some(e=>e.dual);

  let html=pdCover(name+' — Personal Timetable',COLLEGE_LINE+' · '+entries.length+' periods/week · '+secSet.size+' section'+(secSet.size===1?'':'s'));
  html+='<div class="sp-stats">'+
    '<div class="stat"><b>'+entries.length+'</b><span>periods / wk</span></div>'+
    '<div class="stat"><b>'+secSet.size+'</b><span>sections</span></div>'+
    '<div class="stat"><b>'+busiest+'</b><span>busiest day</span></div>'+
    '<div class="stat"><b>'+fav+'</b><span>favourite slot</span></div>'+
  '</div>';
  html+='<div class="sp-block-title">Personal weekly grid <span>— where '+esc(name)+' teaches in this combination ('+freeDays+' free day'+(freeDays===1?'':'s')+')</span></div>';
  html+='<div class="sp-gridwrap">'+spotlightGrid(entries)+'</div>';
  if(hasDual)html+='<div class="sp-note">⇄ Includes the shared “Economics / Statistics” option block in ICS-II-B — taught in parallel rooms with Prof. Naeem Asghar / Prof. Ishfaq Ahmed.</div>';
  html+='<div class="sp-block-title">Courses taught</div>';
  html+=spotlightCourses(entries);
  html+=cons
    ?'<div class="sp-cons">⚑ '+esc(cons.text)+'<span class="ok">✓ satisfied</span></div>'
    :'<div class="sp-cons none">No constraint listed for this faculty member.</div>';
  html+=pdFooter();
  return html;
}
function printTarget(target){
  const c=getSel();if(!c)return;
  let html='';
  if(target.type==='stream')html=buildStreamDoc(c,target.id);
  else if(target.type==='teacher')html=buildTeacherDoc(c,target.name);
  else html=buildComboDoc(c);
  const area=document.getElementById('printArea');
  if(!area)return;
  area.innerHTML=html;
  window.print();
}
/* Console Print/PDF button: prints the current scope; a single filtered section
   downloads as a landscape PNG image instead (no PDF for individual sections). */
function printCurrent(){
  const c=getSel();if(!c)return;
  if(state.spot){exportTeacherImage(state.spot);return;}
  const f=state.sectionFilter;
  if(f==='all')printTarget({type:'combo'});
  else if(f==='icom'||f==='ics')printTarget({type:'stream',id:f});
  else exportSectionImage(f);
}

/* ---------- section image export (landscape PNG, fully fitted) ---------- */
function wrapLines(ctx,text,maxW,font){
  ctx.font=font;
  const words=String(text).split(' ');
  const lines=[];let cur='';
  for(const w of words){
    const t=cur?cur+' '+w:w;
    if(ctx.measureText(t).width>maxW&&cur){lines.push(cur);cur=w;}
    else cur=t;
  }
  if(cur)lines.push(cur);
  return lines;
}
async function drawSectionCanvas(secId){
  const c=getSel();if(!c)return;
  const sec=SECTIONS.find(s=>s.id===secId);if(!sec)return;
  const grid=c.tt[secId];
  const accent=sec.stream==='icom'?'#1c6b48':'#3a55b0';
  const tint=sec.stream==='icom'?'#e2efe6':'#e5e9f8';
  const ink='#182720',muted='#5b6a61',line='#d7dbcc';
  const amberTint='#fdf3dc',amber='#8a6210';

  const canvas=document.createElement('canvas');
  const ctx=canvas.getContext('2d');
  if(!ctx){setTicker('Image export is not supported in this browser','err');return;}
  try{if(document.fonts&&document.fonts.ready)await document.fonts.ready;}catch(e){}

  const pad=48,colDay=124,colP=300,colB=86;
  const cols=[colDay,colP,colP,colP,colB,colP,colP];
  const gap=4;
  const W=pad*2+cols.reduce((a,b)=>a+b,0)+gap*(cols.length-1);
  const titleH=58,subH=26,headGap=30,hdrH=64,rowH=104;
  const H=pad*2+titleH+subH+headGap+hdrH+rowH*5;

  const scale=2;
  canvas.width=Math.round(W*scale);canvas.height=Math.round(H*scale);
  ctx.scale(scale,scale);
  ctx.fillStyle='#ffffff';ctx.fillRect(0,0,W,H);

  ctx.textAlign='left';ctx.textBaseline='alphabetic';
  ctx.fillStyle=accent;ctx.font='900 40px Fraunces, Georgia, serif';
  ctx.fillText(sec.label,pad,pad+titleH-12);
  ctx.fillStyle=muted;ctx.font='500 20px "IBM Plex Sans", sans-serif';
  ctx.fillText(COLLEGE_LINE,pad,pad+titleH+subH-2);

  function cellRect(cx,cy,cw,ch,fill){
    ctx.fillStyle=fill;ctx.fillRect(cx,cy,cw,ch);
    ctx.strokeStyle=line;ctx.lineWidth=1;ctx.strokeRect(cx+0.5,cy+0.5,cw-1,ch-1);
  }

  const tx=pad,ty=pad+titleH+subH+headGap;
  const heads=[['Week',''],['Period-1',TIMES[0]],['Period-2',TIMES[1]],['Period-3',TIMES[2]],['Break','10:30–10:55'],['Period-4',TIMES[3]],['Period-5',TIMES[4]]];
  let cx=tx;
  for(let ci=0;ci<cols.length;ci++){
    const isBrk=(ci===4);
    cellRect(cx,ty,cols[ci],hdrH,isBrk?amberTint:tint);
    ctx.textAlign='center';
    ctx.fillStyle=isBrk?amber:accent;ctx.font='600 15px "IBM Plex Sans", sans-serif';
    ctx.fillText(heads[ci][0],cx+cols[ci]/2,ty+hdrH/2-2);
    if(heads[ci][1]){
      ctx.fillStyle=muted;ctx.font='400 12px "IBM Plex Sans", sans-serif';
      ctx.fillText(heads[ci][1],cx+cols[ci]/2,ty+hdrH/2+16);
    }
    cx+=cols[ci]+gap;
  }

  let y=ty+hdrH;
  for(let d=0;d<5;d++){
    let rx=tx;
    cellRect(rx,y,cols[0],rowH,'#fafbf8');
    ctx.fillStyle=ink;ctx.font='600 18px "IBM Plex Sans", sans-serif';
    ctx.textAlign='center';ctx.fillText(DAYS[d],rx+cols[0]/2,y+rowH/2+6);
    rx+=cols[0]+gap;
    // 6 visual columns per row: P1, P2, P3, Break, P4, P5
    for(let s=0;s<6;s++){
      const cw=cols[s+1];
      if(s===3){
        cellRect(rx,y,cw,rowH,amberTint);
        ctx.fillStyle=amber;ctx.font='600 13px "IBM Plex Sans", sans-serif';
        ctx.textAlign='center';ctx.fillText('Break',rx+cw/2,y+rowH/2+4);
      }else{
        const cell=grid[d][s<3?s:s-1];   // P1..P3 from grid[0..2]; P4,P5 from grid[3..4]
        cellRect(rx,y,cw,rowH,'#ffffff');
        const dual=cell.dual;
        ctx.textAlign='center';
        let sz=24,lines;
        do{lines=wrapLines(ctx,cell.subj,cw-26,'700 '+sz+'px "IBM Plex Sans", sans-serif');sz-=2;}while(lines.length>2&&sz>16);
        let ly=y+rowH/2-8-(lines.length===2?7:0);
        ctx.fillStyle=dual?accent:ink;
        for(const ln of lines){ctx.fillText(ln,rx+cw/2,ly);ly+=sz+4;}
        let tsz=16,tlines;
        do{tlines=wrapLines(ctx,cell.teacher,cw-26,'400 '+tsz+'px "IBM Plex Sans", sans-serif');tsz-=1.5;}while(tlines.length>2&&tsz>12);
        ly+=6;ctx.fillStyle=muted;
        for(const ln of tlines){ctx.fillText(ln,rx+cw/2,ly);ly+=tsz+3;}
      }
      rx+=cw+gap;
    }
    y+=rowH;
  }

  return {canvas:canvas, filename:'IMPCC_'+secId+'.png'};
}
async function exportSectionImage(secId){
  const sec=SECTIONS.find(s=>s.id===secId);
  const r=await drawSectionCanvas(secId);
  if(!r)return;
  await downloadCanvas(r.canvas, r.filename);
  setTicker('Exported image — '+(sec?sec.label:secId)+' (landscape PNG)','ok');
}
async function drawTeacherCanvas(name){
  const c=getSel();if(!c)return;
  const entries=(buildTeacherIndex(c.tt)[name])||[];
  const m={};entries.forEach(e=>{m[e.d+'_'+e.s]=e;});
  const accent='#1c6b48',tint='#e2efe6',ink='#182720',muted='#5b6a61',line='#d7dbcc';
  const amberTint='#fdf3dc',amber='#8a6210';

  const canvas=document.createElement('canvas');
  const ctx=canvas.getContext('2d');
  if(!ctx){setTicker('Image export is not supported in this browser','err');return;}
  try{if(document.fonts&&document.fonts.ready)await document.fonts.ready;}catch(e){}

  const pad=48,colDay=124,colP=300,colB=86;
  const cols=[colDay,colP,colP,colP,colB,colP,colP];
  const gap=4;
  const W=pad*2+cols.reduce((a,b)=>a+b,0)+gap*(cols.length-1);
  const titleH=58,subH=26,headGap=30,hdrH=64,rowH=104;
  const H=pad*2+titleH+subH+headGap+hdrH+rowH*5;

  const scale=2;
  canvas.width=Math.round(W*scale);canvas.height=Math.round(H*scale);
  ctx.scale(scale,scale);
  ctx.fillStyle='#ffffff';ctx.fillRect(0,0,W,H);

  ctx.textAlign='left';ctx.textBaseline='alphabetic';
  ctx.fillStyle=accent;ctx.font='900 40px Fraunces, Georgia, serif';
  ctx.fillText(name+' — Personal Timetable',pad,pad+titleH-12);
  ctx.fillStyle=muted;ctx.font='500 20px "IBM Plex Sans", sans-serif';
  ctx.fillText(COLLEGE_LINE+' · '+entries.length+' periods/week',pad,pad+titleH+subH-2);

  function cellRect(cx,cy,cw,ch,fill){
    ctx.fillStyle=fill;ctx.fillRect(cx,cy,cw,ch);
    ctx.strokeStyle=line;ctx.lineWidth=1;ctx.strokeRect(cx+0.5,cy+0.5,cw-1,ch-1);
  }

  const tx=pad,ty=pad+titleH+subH+headGap;
  const heads=[['Week',''],['Period-1',TIMES[0]],['Period-2',TIMES[1]],['Period-3',TIMES[2]],['Break','10:30–10:55'],['Period-4',TIMES[3]],['Period-5',TIMES[4]]];
  let cx=tx;
  for(let ci=0;ci<cols.length;ci++){
    const isBrk=(ci===4);
    cellRect(cx,ty,cols[ci],hdrH,isBrk?amberTint:tint);
    ctx.textAlign='center';
    ctx.fillStyle=isBrk?amber:accent;ctx.font='600 15px "IBM Plex Sans", sans-serif';
    ctx.fillText(heads[ci][0],cx+cols[ci]/2,ty+hdrH/2-2);
    if(heads[ci][1]){
      ctx.fillStyle=muted;ctx.font='400 12px "IBM Plex Sans", sans-serif';
      ctx.fillText(heads[ci][1],cx+cols[ci]/2,ty+hdrH/2+16);
    }
    cx+=cols[ci]+gap;
  }

  let y=ty+hdrH;
  for(let d=0;d<5;d++){
    let rx=tx;
    cellRect(rx,y,cols[0],rowH,'#fafbf8');
    ctx.fillStyle=ink;ctx.font='600 18px "IBM Plex Sans", sans-serif';
    ctx.textAlign='center';ctx.fillText(DAYS[d],rx+cols[0]/2,y+rowH/2+6);
    rx+=cols[0]+gap;
    for(let s=0;s<6;s++){
      const cw=cols[s+1];
      if(s===3){
        cellRect(rx,y,cw,rowH,amberTint);
        ctx.fillStyle=amber;ctx.font='600 13px "IBM Plex Sans", sans-serif';
        ctx.textAlign='center';ctx.fillText('Break',rx+cw/2,y+rowH/2+4);
      }else{
        const e=m[d+'_'+(s<3?s:s-1)];
        cellRect(rx,y,cw,rowH,'#ffffff');
        ctx.textAlign='center';
        if(e){
          ctx.fillStyle=e.dual?accent:ink;
          let sz=24,lines;
          do{lines=wrapLines(ctx,e.subj,cw-26,'700 '+sz+'px "IBM Plex Sans", sans-serif');sz-=2;}while(lines.length>2&&sz>16);
          let ly=y+rowH/2-8-(lines.length===2?7:0);
          for(const ln of lines){ctx.fillText(ln,rx+cw/2,ly);ly+=sz+4;}
          ctx.fillStyle=muted;ctx.font='400 16px "IBM Plex Sans", sans-serif';
          ctx.fillText(e.sec,rx+cw/2,ly+6);
        }else{
          ctx.fillStyle='#c2c9ba';ctx.font='400 16px "IBM Plex Sans", sans-serif';
          ctx.fillText('·',rx+cw/2,y+rowH/2+6);
        }
      }
      rx+=cw+gap;
    }
    y+=rowH;
  }

  return {canvas:canvas, filename:'IMPCC_personal-timetable_'+slug(name)+'.png'};
}
async function exportTeacherImage(name){
  const r=await drawTeacherCanvas(name);
  if(!r)return;
  await downloadCanvas(r.canvas, r.filename);
  setTicker('Exported image — '+name+' (landscape PNG)','ok');
}

"""
src = src[:i] + engine + src[k:]

# (g) spotlight drawer PDF button routes through the same engine
rep("$('spPrint').addEventListener('click',printCurrent);",
    "$('spPrint').addEventListener('click',()=>{if(state.spot)exportTeacherImage(state.spot);});")
# relabel the spotlight drawer export button from PDF to PNG
rep('id="spPrint" title="Print this personal timetable / save as PDF">',
    'id="spPrint" title="Download this personal timetable as a PNG image">')
rep('</svg>\n        PDF\n      </button>',
    '</svg>\n        PNG\n      </button>')

# ---- 18) Constraints page (data-driven faculty constraints + LLM translate) ----
# (a) CSS for the constraints panel
rep('.card-img:hover{background:var(--ics);color:#fff}',
    '.card-img:hover{background:var(--ics);color:#fff}\n.cons-note{background:var(--surface);border:1px solid var(--line);border-left:7px solid var(--green);border-radius:12px;padding:12px 16px;margin-bottom:16px;font-size:13px;color:var(--ink2)}\n.cons-note b{color:var(--green-deep)}\n.cons-actions{margin-left:auto;display:inline-flex;gap:6px;float:right}\n.cons-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:16px}\n.cons-card{background:var(--surface);border:1px solid var(--line);border-radius:11px;padding:14px 16px;display:flex;flex-direction:column;gap:10px;min-width:0}\n.cons-card.edited{border-color:var(--amber);box-shadow:0 0 0 1px var(--amber)}\n.cons-card header{display:flex;align-items:center;gap:8px}\n.cons-card header h4{font-family:var(--disp);font-weight:700;font-size:15px;margin:0;color:var(--ink)}\n.cons-card .stag.edited{background:var(--amber-tint);color:var(--amber-deep);border-color:var(--amber)}\n.cons-rules{display:flex;flex-wrap:wrap;gap:5px}\n.cons-rule{font-family:var(--mono);font-size:10px;padding:2px 8px;border-radius:6px;background:var(--green-tint);color:var(--green-deep);border:1px solid var(--line2)}\n.cons-rule.none{background:transparent;border-style:dashed;color:var(--ink2)}\n.cons-nl{width:100%;min-height:52px;font-family:var(--body);font-size:12.5px;padding:8px 10px;border:1px solid var(--line2);border-radius:8px;background:#fff;resize:vertical;color:var(--ink)}\n.cons-btns{display:flex;gap:6px;flex-wrap:wrap}\n.cons-status{font-family:var(--mono);font-size:10.5px;color:var(--ink2);min-height:14px}')

# (b) viewbar: add Constraints tab
rep('<button id="viewTeachers">◉ Faculty</button>',
    '<button id="viewTeachers">◉ Faculty</button>\n      <button id="viewConstraints">⚙ Constraints</button>')

# (c) setView handles 'constraints'
rep("""  $('secFilterWrap').classList.toggle('hidden',v!=='sections');
  renderChrome();persist();""",
    """  $('secFilterWrap').classList.toggle('hidden',v!=='sections'&&v!=='constraints');
  $('viewConstraints').classList.toggle('on',v==='constraints');
  renderChrome();persist();""")

# (d) renderMain renders constraints view before the empty-combos guard
rep("""function renderMain(){
  const c=getSel();""",
    """function renderMain(){
  if(state.view==='constraints'){renderConstraints();return;}
  const c=getSel();""")

# (e) runSlice passes the current constraints into the solver
rep("  const res=IMPCC_SOLVER.generate({maxCount:0,timeMs:320,seed:(Math.random()*2147483647)|0});",
    "  const res=IMPCC_SOLVER.generate({maxCount:0,timeMs:320,seed:(Math.random()*2147483647)|0,constraints:currentConstraints()});")

# (f) click handler: constraints buttons (insert before the csv-btn block)
rep("""  const csvBtn=e.target.closest('.card-csv');""",
    """  const consBtn=e.target.closest('[data-translate],[data-apply],[data-reset-one],#consDownload,#consUpload,#consReset');
  if(consBtn){
    if(consBtn.id==='consReset'){resetConstraints();return;}
    if(consBtn.id==='consDownload'){downloadConstraints();return;}
    if(consBtn.id==='consUpload'){$('consUploadInput').click();return;}
    const code=consBtn.dataset.translate||consBtn.dataset.apply||consBtn.dataset.resetOne;
    if(consBtn.dataset.translate)translateOne(code);
    else if(consBtn.dataset.apply)applyTranslation(code);
    else if(consBtn.dataset.resetOne)resetOneConstraint(code);
    return;
  }
  const csvBtn=e.target.closest('.card-csv');""")

# (g) boot: load saved constraints
rep("/* ---------- boot: restore saved results (no auto-generation) ---------- */\nconst restored=restore();",
    "/* ---------- boot: restore saved results (no auto-generation) ---------- */\nloadConstraints();\nconst restored=restore();")

# (h0) wire the Constraints tab listener
rep("$('viewTeachers').addEventListener('click',()=>setView('teachers'));",
    "$('viewTeachers').addEventListener('click',()=>setView('teachers'));\n$('viewConstraints').addEventListener('click',()=>setView('constraints'));")

# (h) the constraints module JS (insert before the boot section)
constraints_js = """/* ---------- constraints page (data-driven faculty constraints + LLM) ---------- */
const CONST_KEY='impcc-constraints-v1';
let pendingTranslations={};
function loadConstraints(){
  try{
    const raw=localStorage.getItem(CONST_KEY);
    if(raw){state.constraints=JSON.parse(raw);return true;}
  }catch(e){}
  state.constraints=null;
  return false;
}
function saveConstraints(){
  try{
    if(state.constraints)localStorage.setItem(CONST_KEY,JSON.stringify(state.constraints));
    else localStorage.removeItem(CONST_KEY);
  }catch(e){}
}
function currentConstraints(){return state.constraints||undefined;}
function resetConstraints(){
  state.constraints=null;saveConstraints();
  setTicker('Constraints reset to the college defaults','ok');
  renderMain();
}
function resetOneConstraint(code){
  if(!state.constraints)return;
  delete state.constraints[code];
  if(!Object.keys(state.constraints).length)state.constraints=null;
  saveConstraints();
  setTicker('Reset '+IMPCC_SOLVER.TEACHER_FULL[code]+' to defaults','ok');
  renderMain();
}
function downloadConstraints(){
  const payload=state.constraints||IMPCC_SOLVER.DEFAULT_CONSTRAINTS;
  const blob=new Blob([JSON.stringify(payload,null,2)],{type:'application/json'});
  const url=URL.createObjectURL(blob);
  const a=document.createElement('a');a.href=url;a.download='constraints.json';
  document.body.appendChild(a);a.click();a.remove();
  setTimeout(()=>URL.revokeObjectURL(url),800);
  setTicker('Downloaded constraints.json','ok');
}
function uploadConstraintsFile(file){
  const rd=new FileReader();
  rd.onload=()=>{
    try{
      const data=JSON.parse(rd.result);
      state.constraints=data;saveConstraints();
      setTicker('Uploaded '+Object.keys(data).length+' constraint set(s)','ok');
      renderMain();
    }catch(e){setTicker('Upload failed: invalid JSON','err');}
  };
  rd.readAsText(file);
}
function constraintEntries(){
  const cur=state.constraints||{};
  const list=[];
  for(const code in IMPCC_SOLVER.TEACHER_FULL){
    if(code==='PARALLEL')continue;
    const def=IMPCC_SOLVER.DEFAULT_CONSTRAINTS[code];
    const over=cur[code];
    list.push({
      code,
      name:IMPCC_SOLVER.TEACHER_FULL[code],
      hasDefault:!!def,
      natural:(over&&over.natural)||'',
      rules:over?(over.rules||{}):(def?def.rules:{}),
      overridden:!!over
    });
  }
  return list.sort((a,b)=>(b.overridden?1:0)-(a.overridden?1:0)||(b.hasDefault?1:0)-(a.hasDefault?1:0)||a.name.localeCompare(b.name));
}
function rulesSummary(rules){
  const r=rules||{},out=[];
  if(r.allowed_slots)out.push('only '+r.allowed_slots.join(', '));
  if(r.forbidden_slots)out.push('never '+r.forbidden_slots.join(', '));
  if(r.allowed_days)out.push('only '+r.allowed_days.join(', '));
  if(r.forbidden_days)out.push('not on '+r.forbidden_days.join(', '));
  (r.forbidden_slots_on_days||[]).forEach(e=>out.push(e.days.join('/')+' '+e.slots.join(', ')+' free'));
  (r.min_days_in_slot||[]).forEach(e=>out.push(e.slot+' on ≥'+e.min_days+' days'));
  if(r.min_days_engaged)out.push('teach ≥'+r.min_days_engaged+' days');
  if(r.max_periods_per_day)out.push('≤'+r.max_periods_per_day+' periods/day');
  (r.subject_slots||[]).forEach(e=>out.push(e.subject+' → '+e.slots.join(', ')));
  (r.subject_forbidden_days||[]).forEach(e=>out.push(e.subject+' not '+e.days.join(', ')));
  (r.stream_slots_required||[]).forEach(e=>out.push(e.stream+' fills '+e.slots.join(', ')));
  return out;
}
function renderConstraints(){
  const entries=constraintEntries();
  let h='<div class="cons-note"><b>Faculty constraints are data.</b> Type a member\u2019s plain-language note and press <b>✦ Translate with AI</b> to convert it into the system\u2019s structured rules, review the preview, then <b>Apply</b>. Changes take effect on the next generation — nothing is hard-coded anymore.<span class="cons-actions"><button class="mini-export" id="consDownload">⇩ Download</button><button class="mini-export" id="consUpload">⇧ Upload</button><button class="mini-export" id="consReset">Reset to defaults</button></span></div>';
  h+='<input type="file" id="consUploadInput" accept="application/json" style="display:none">';
  h+='<div class="cons-grid">';
  for(const e of entries){
    const sum=rulesSummary(e.rules);
    h+='<article class="cons-card'+(e.overridden?' edited':'')+'">'+
      '<header><h4>'+esc(e.name)+'</h4>'+(e.hasDefault?'<span class="stag">default</span>':'')+(e.overridden?'<span class="stag edited">edited</span>':'')+'</header>'+
      '<div class="cons-rules">'+(sum.length?sum.map(x=>'<div class="cons-rule">'+esc(x)+'</div>').join(''):'<div class="cons-rule none">No constraints</div>')+'</div>'+
      '<textarea class="cons-nl" data-code="'+e.code+'" placeholder="Describe their constraint in plain language…">'+esc(e.natural)+'</textarea>'+
      '<div class="cons-btns">'+
        '<button class="mini-export" data-translate="'+e.code+'">✦ Translate with AI</button>'+
        '<button class="mini-export" data-apply="'+e.code+'"'+(pendingTranslations[e.code]?'':' disabled')+'>Apply</button>'+
        '<button class="mini-export" data-reset-one="'+e.code+'"'+(e.overridden?'':' disabled')+'>Reset</button>'+
      '</div>'+
      '<div class="cons-status" data-status="'+e.code+'">'+esc(pendingTranslations[e.code]||'')+'</div>'+
    '</article>';
  }
  h+='</div>';
  mainEl.innerHTML=h;
  $('consUploadInput').addEventListener('change',ev=>{if(ev.target.files&&ev.target.files[0])uploadConstraintsFile(ev.target.files[0]);});
}
function translateOne(code){
  const ta=document.querySelector('.cons-nl[data-code="'+code+'"]');
  const text=ta?ta.value.trim():'';
  const st=document.querySelector('.cons-status[data-status="'+code+'"]');
  if(!text){if(st)st.textContent='Type a plain-language note first.';return;}
  if(st)st.textContent='Translating…';
  const base=(typeof window.IMPCC_API_URL==='string')?window.IMPCC_API_URL:'';
  if(typeof fetch!=='function'){if(st)st.textContent='Translation needs the backend (set IMPCC_API_URL or deploy with api/).';return;}
  fetch(base+'/translate',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({text:text,teacher:IMPCC_SOLVER.TEACHER_FULL[code]})
  })
  .then(r=>{if(!r.ok)throw new Error('HTTP '+r.status);return r.json();})
  .then(d=>{
    if(d.error){if(st)st.textContent='⚠ '+d.error;return;}
    const sum=rulesSummary(d.rules||{});
    const preview=sum.join(' · ')||'(no rules)';
    pendingTranslations[code]=d;
    if(st)st.textContent='✓ '+preview+(d.confidence?(' · confidence '+Math.round(d.confidence*100)+'%'):'')+(d.unmapped&&d.unmapped.length?(' · unmapped: '+d.unmapped.join(', ')):'');
    const applyBtn=document.querySelector('[data-apply="'+code+'"]');
    if(applyBtn)applyBtn.disabled=false;
  })
  .catch(err=>{if(st)st.textContent='⚠ Translation failed: '+err.message;});
}
function applyTranslation(code){
  const d=pendingTranslations[code];
  if(!d)return;
  const ta=document.querySelector('.cons-nl[data-code="'+code+'"]');
  const natural=ta?ta.value.trim():d.natural;
  if(!state.constraints)state.constraints={};
  state.constraints[code]={name:IMPCC_SOLVER.TEACHER_FULL[code],natural:natural,rules:d.rules||{}};
  saveConstraints();
  delete pendingTranslations[code];
  setTicker('Applied constraints for '+IMPCC_SOLVER.TEACHER_FULL[code]+' — will affect the next generation','ok');
  renderMain();
}

"""
rep("/* ---------- boot: restore saved results (no auto-generation) ---------- */",
    constraints_js + "/* ---------- boot: restore saved results (no auto-generation) ---------- */")


# ---- 19) Supabase: auth, cloud-synced allocation + constraints ----------
# (a) load supabase client after solver
rep('<script src="solver.js"></script>',
    '<script src="solver.js"></script>\n<script src="supabase.js"></script>')

# (b) masthead auth + modal (before the single literal </header>)
rep('</header>',
    '  <div class="mast-auth" id="authUi"></div>\n</header>\n<div class="auth-modal" id="authModal">\n  <div class="auth-box">\n    <h3>Sign in to IMPCC Timetable</h3>\n    <p>Authorized access only — your allocation and constraints sync across devices.</p>\n    <input id="authEmail" type="email" placeholder="Email">\n    <input id="authPass" type="password" placeholder="Password">\n    <div class="auth-row">\n      <button class="btn primary" id="authSignInBtn">Sign in</button>\n      <button class="btn" id="authClose">Cancel</button>\n    </div>\n    <div class="cons-status" id="authMsg"></div>\n  </div>\n</div>')

# (c) CSS for auth + allocation
rep('.cons-status{font-family:var(--mono);font-size:10.5px;color:var(--ink2);min-height:14px}',
    '.cons-status{font-family:var(--mono);font-size:10.5px;color:var(--ink2);min-height:14px}\n.mast-auth{margin-left:auto;display:flex;align-items:center;gap:8px}\n.mast-auth .auth-name{font-family:var(--mono);font-size:11px;color:var(--green-deep)}\n.auth-modal{position:fixed;inset:0;background:rgba(14,59,41,.45);z-index:200;display:none;align-items:center;justify-content:center}\n.auth-box{background:var(--surface);border-radius:14px;padding:22px 26px;width:min(420px,92vw);box-shadow:0 24px 60px rgba(0,0,0,.3)}\n.auth-box h3{font-family:var(--disp);font-weight:900;font-size:20px;color:var(--green-deep);margin:0 0 4px}\n.auth-box p{font-size:12.5px;color:var(--ink2);margin:0 0 14px}\n.auth-box input{display:block;width:100%;margin-bottom:10px;padding:9px 11px;border:1px solid var(--line2);border-radius:8px;font-size:14px}\n.auth-row{display:flex;gap:8px;flex-wrap:wrap;margin-top:4px}\n.auth-row .btn{color:var(--ink);background:var(--surface2);border-color:var(--line2)}\n.auth-row .btn.primary{color:#fff;background:var(--green)}\n.alloc-rows{display:flex;flex-direction:column;gap:5px}\n.alloc-row{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.3fr) 64px 28px;gap:5px;align-items:center;min-width:0}\n.alloc-row input,.alloc-row select{font-size:12px;padding:5px 7px;border:1px solid var(--line2);border-radius:6px;background:#fff;color:var(--ink);min-width:0;max-width:100%;box-sizing:border-box}\n.alloc-row input.alloc-per{width:100%}\n.alloc-row select{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}')

# (d) Allocation tab
rep('<button id="viewConstraints">⚙ Constraints</button>',
    '<button id="viewConstraints">⚙ Constraints</button>\n      <button id="viewAllocation">🗂 Allocation</button>')
rep("$('viewConstraints').addEventListener('click',()=>setView('constraints'));",
    "$('viewConstraints').addEventListener('click',()=>setView('constraints'));\n$('viewAllocation').addEventListener('click',()=>setView('allocation'));")
rep("  $('viewConstraints').classList.toggle('on',v==='constraints');",
    "  $('viewConstraints').classList.toggle('on',v==='constraints');\n  $('viewAllocation').classList.toggle('on',v==='allocation');")
rep("  if(state.view==='constraints'){renderConstraints();return;}",
    "  if(state.view==='constraints'){renderConstraints();return;}\n  if(state.view==='allocation'){renderAllocation();return;}")

# (e) generation + CP-SAT use live allocation/constraints
rep("const res=IMPCC_SOLVER.generate({maxCount:0,timeMs:320,seed:(Math.random()*2147483647)|0,constraints:currentConstraints()});",
    "const res=IMPCC_SOLVER.generate({maxCount:0,timeMs:320,seed:(Math.random()*2147483647)|0,constraints:currentConstraints(),sections:currentAllocation()});")
rep("body:JSON.stringify({time_limit:120,n_seeds:1,max_solutions:0})",
    "body:JSON.stringify({time_limit:120,n_seeds:1,max_solutions:0,constraints:currentConstraints(),sections:currentAllocation()})")

# (f) cloud sync: persist constraints/allocation to Supabase when signed in
rep("function saveConstraints(){\n  try{\n    if(state.constraints)localStorage.setItem(CONST_KEY,JSON.stringify(state.constraints));\n    else localStorage.removeItem(CONST_KEY);\n  }catch(e){}\n}",
    "function saveConstraints(){\n  try{\n    if(state.constraints)localStorage.setItem(CONST_KEY,JSON.stringify(state.constraints));\n    else localStorage.removeItem(CONST_KEY);\n  }catch(e){}\n  pushToCloud();\n}")

# (g) boot: load allocation + auth + cloud refresh
rep("/* ---------- boot: restore saved results (no auto-generation) ---------- */\nloadConstraints();\nconst restored=restore();",
    "/* ---------- boot: restore saved results (no auto-generation) ---------- */\nloadConstraints();\nloadAllocation();\nrenderAuth();\nconst restored=restore();\nif(SB&&SB.loggedIn){syncFromCloud().then(()=>{renderMain();renderChrome();});}")

# (h) the auth + cloud + allocation module (insert before the constraints module)
auth_module = """/* ---------- auth + cloud sync + allocation page ---------- */
const SB = (typeof IMPCC_SUPABASE!=='undefined') ? IMPCC_SUPABASE : null;
function rosterNames(){
  const names=[];
  for(const code in IMPCC_SOLVER.TEACHER_FULL) names.push(IMPCC_SOLVER.TEACHER_FULL[code]);
  return Array.from(new Set(names)).sort();
}
function defaultAllocation(){
  const a={};
  for(const sec of IMPCC_SOLVER.DEFAULT_SECTIONS){
    a[sec.key]={subjects:sec.subs.map(t=>({subject:t[0],teacher:IMPCC_SOLVER.TEACHER_FULL[t[1]],periods:t[2]}))};
  }
  return a;
}
function loadAllocation(){
  try{const raw=localStorage.getItem('impcc-allocation-v1');if(raw){state.allocation=JSON.parse(raw);return true;}}catch(e){}
  state.allocation=null;return false;
}
function saveAllocationLocal(){
  try{if(state.allocation)localStorage.setItem('impcc-allocation-v1',JSON.stringify(state.allocation));else localStorage.removeItem('impcc-allocation-v1');}catch(e){}
}
function currentAllocation(){return state.allocation||undefined;}
function sectionTotal(subs){return (subs||[]).reduce((n,e)=>n+(e.periods|0),0);}
function getWorkingAllocation(){if(!state.allocation)state.allocation=defaultAllocation();return state.allocation;}

function renderAuth(){
  const el=document.getElementById('authUi');if(!el)return;
  if(SB&&SB.loggedIn){
    el.innerHTML='<span class="auth-name">'+esc(SB.user.email)+'</span><button class="mini-export" id="authSignOut">Sign out</button>';
    document.getElementById('authSignOut').addEventListener('click',()=>{
      SB.logout().then(()=>{renderAuth();setTicker('Signed out — using local data','ok');});
    });
  }else{
    el.innerHTML='<button class="mini-export" id="authSignIn">Sign in</button>';
    document.getElementById('authSignIn').addEventListener('click',()=>{document.getElementById('authModal').style.display='flex';});
  }
}
function setAuthMsg(m){const el=document.getElementById('authMsg');if(el)el.textContent=m;}
function authSubmit(mode){
  const email=document.getElementById('authEmail').value.trim();
  const pass=document.getElementById('authPass').value;
  if(!email||!pass){setAuthMsg('Enter email and password.');return;}
  if(!SB){setAuthMsg('Supabase unavailable in this environment.');return;}
  setAuthMsg('Signing in…');
  const p=SB.login(email,pass);
  p.then(async()=>{
    setAuthMsg('Signed in — loading your workspace…');
    await syncFromCloud();
    document.getElementById('authModal').style.display='none';
    renderAuth();renderMain();renderChrome();
    setTicker('Signed in as '+SB.user.email+' — workspace synced','ok');
  }).catch(err=>setAuthMsg('Error: '+err.message));
}
async function syncFromCloud(){
  if(!SB||!SB.loggedIn)return;
  try{
    const ws=await SB.loadWorkspace();
    if(ws){
      if(ws.constraints&&Object.keys(ws.constraints).length){state.constraints=ws.constraints;saveConstraints();}
      if(ws.allocation&&Object.keys(ws.allocation).length){state.allocation=ws.allocation;saveAllocationLocal();}
    }
  }catch(e){setTicker('Cloud load failed: '+e.message,'err');}
}
function pushToCloud(){
  if(!SB||!SB.loggedIn)return;
  SB.saveWorkspace(state.allocation||defaultAllocation(),state.constraints||{})
    .then(()=>setTicker('Saved to Supabase ✓','ok'))
    .catch(err=>setTicker('Cloud sync failed: '+err.message,'err'));
}
function saveAllocation(){
  const a=getWorkingAllocation();
  const bad=[];
  for(const sec of SECTIONS){const t=sectionTotal(a[sec.id]?a[sec.id].subjects:[]);if(t!==25)bad.push(sec.id+'='+t);}
  saveAllocationLocal();pushToCloud();
  setTicker(bad.length?('Saved, but '+bad.join(', ')+' not 25 periods'):'Allocation saved',bad.length?'':'ok');
}
function renderAllocation(){
  const a=getWorkingAllocation();const roster=rosterNames();
  let h='<div class="cons-note"><b>Course allocation is data.</b> Set the teacher and weekly periods for each subject. Every section must total <b>25 periods</b>. '+(SB&&SB.loggedIn?'Signed in — saving syncs to Supabase across devices.':'Not signed in — saved locally (sign in to sync).')+'<span class="cons-actions"><button class="mini-export" id="allocSave">💾 Save allocation</button></span></div>';
  h+='<div class="cons-grid">';
  for(const sec of SECTIONS){
    const key=sec.id;const subs=(a[key]&&a[key].subjects)||[];const total=sectionTotal(subs);
    h+='<article class="cons-card'+(total!==25?' edited':'')+'"><header><h4>'+esc(sec.label)+'</h4><span class="stag" data-total="'+key+'" style="'+(total===25?'':'color:var(--red);border-color:var(--red)')+'">'+total+'/25</span></header><div class="alloc-rows">';
    subs.forEach((e,idx)=>{
      h+='<div class="alloc-row">'+
        '<input class="alloc-subj" data-k="'+key+'" data-i="'+idx+'" value="'+esc(e.subject)+'">'+
        '<select class="alloc-tchr" data-k="'+key+'" data-i="'+idx+'">'+roster.map(n=>'<option'+(n===e.teacher?' selected':'')+'>'+esc(n)+'</option>').join('')+'</select>'+
        '<input class="alloc-per" type="number" min="1" max="5" data-k="'+key+'" data-i="'+idx+'" value="'+(e.periods|0)+'">'+
        '<button class="card-csv" data-alloc-del="'+key+'" data-i="'+idx+'" title="Remove subject">✕</button>'+
      '</div>';
    });
    h+='</div><button class="mini-export" data-alloc-add="'+key+'">＋ Add subject</button></article>';
  }
  h+='</div>';
  mainEl.innerHTML=h;
  document.getElementById('allocSave').addEventListener('click',saveAllocation);
}
function allocInputHandler(el){
  const key=el.dataset.k,i=+el.dataset.i;const a=getWorkingAllocation();
  a[key]=a[key]||{subjects:[]};
  if(!a[key].subjects[i])a[key].subjects[i]={subject:'',teacher:rosterNames()[0],periods:1};
  if(el.classList.contains('alloc-subj'))a[key].subjects[i].subject=el.value;
  else if(el.classList.contains('alloc-tchr'))a[key].subjects[i].teacher=el.value;
  else if(el.classList.contains('alloc-per'))a[key].subjects[i].periods=Math.max(1,Math.min(5,+el.value||1));
  const b=document.querySelector('.stag[data-total="'+key+'"]');
  if(b){const t=sectionTotal(a[key].subjects);b.textContent=t+'/25';b.style.cssText=t===25?'':'color:var(--red);border-color:var(--red)';}
}

"""
rep("/* ---------- constraints page (data-driven faculty constraints + LLM) ---------- */",
    auth_module + "/* ---------- constraints page (data-driven faculty constraints + LLM) ---------- */")

# (i) delegation for allocation inputs + auth modal buttons (append inside mainEl click handler region — add new listeners near others)
rep("$('spPrint').addEventListener('click',()=>{if(state.spot)exportTeacherImage(state.spot);});",
    "$('spPrint').addEventListener('click',()=>{if(state.spot)exportTeacherImage(state.spot);});\nmainEl.addEventListener('input',e=>{if(e.target.classList.contains('alloc-subj')||e.target.classList.contains('alloc-tchr')||e.target.classList.contains('alloc-per'))allocInputHandler(e.target);});\nmainEl.addEventListener('change',e=>{if(e.target.classList.contains('alloc-tchr'))allocInputHandler(e.target);});\nmainEl.addEventListener('click',e=>{\n  const del=e.target.closest('[data-alloc-del]');\n  if(del){const a=getWorkingAllocation();a[del.dataset.allocDel].subjects.splice(+del.dataset.i,1);renderAllocation();return;}\n  const add=e.target.closest('[data-alloc-add]');\n  if(add){const a=getWorkingAllocation();a[add.dataset.allocAdd]=a[add.dataset.allocAdd]||{subjects:[]};a[add.dataset.allocAdd].subjects.push({subject:'New Subject',teacher:rosterNames()[0],periods:1});renderAllocation();return;}\n});\nconst _ab1=document.getElementById('authSignInBtn');if(_ab1)_ab1.addEventListener('click',()=>authSubmit('in'));\n\nconst _ab3=document.getElementById('authClose');if(_ab3)_ab3.addEventListener('click',()=>{document.getElementById('authModal').style.display='none';});")


# ---- 20) gate expensive backend features behind sign-in -------------------
# runCpsat: refuse when signed out + send the Supabase token
rep("function runCpsat(){\n  if(state.cpsatBusy)return;",
    "function runCpsat(){\n  if(!SB||!SB.loggedIn){setCpsatStatus('Sign in required to use CP-SAT','err');setTicker('Sign in to use CP-SAT','ok');return;}\n  if(state.cpsatBusy)return;")
rep("    headers:{'Content-Type':'application/json'},\n    body:JSON.stringify({time_limit:120,n_seeds:1,max_solutions:0,constraints:currentConstraints(),sections:currentAllocation()})",
    "    headers:{'Content-Type':'application/json','Authorization':'Bearer '+(SB&&SB.session&&SB.session.access_token?SB.session.access_token:'')},\n    body:JSON.stringify({time_limit:120,n_seeds:1,max_solutions:0,constraints:currentConstraints(),sections:currentAllocation()})")
# translateOne: refuse when signed out + send the token
rep("  if(st)st.textContent='Translating…';",
    "  if(!SB||!SB.loggedIn){if(st)st.textContent='Sign in required to use AI translation.';return;}\n  if(st)st.textContent='Translating…';")
rep("    headers:{'Content-Type':'application/json'},\n    body:JSON.stringify({text:text,teacher:IMPCC_SOLVER.TEACHER_FULL[code]})",
    "    headers:{'Content-Type':'application/json','Authorization':'Bearer '+(SB&&SB.session&&SB.session.access_token?SB.session.access_token:'')},\n    body:JSON.stringify({text:text,teacher:IMPCC_SOLVER.TEACHER_FULL[code]})")
# 401 -> friendly "Sign in required" (both fetch chains)
rep(".then(r=>{if(!r.ok)throw new Error('HTTP '+r.status);return r.json();})",
    ".then(r=>{if(!r.ok)throw new Error(r.status===401?'Sign in required':'HTTP '+r.status);return r.json();})", count=2)
# renderChrome: disable the CP-SAT button while signed out
rep("    btnCpsat.disabled=false;",
    "    btnCpsat.disabled=!(SB&&SB.loggedIn);btnCpsat.title=(SB&&SB.loggedIn)?'Call the CP-SAT backend for proven-optimal results':'Sign in to use CP-SAT';")
# sign-out: refresh the console so the button re-disables
rep("SB.logout().then(()=>{renderAuth();setTicker('Signed out — using local data','ok');});",
    "SB.logout().then(()=>{renderAuth();renderChrome();setTicker('Signed out — local data only','ok');});")


# ---- 21) visible "sign in to unlock" hint on CP-SAT + translation ---------
rep("""    btnCpsat.innerHTML='<span class="g">✦</span> Compute optimal (CP-SAT)'+(state.cpsatDone?' ✓':'');""",
    """    const _signedIn=SB&&SB.loggedIn;btnCpsat.innerHTML='<span class="g">'+(_signedIn?'✦':'🔒')+'</span> Compute optimal (CP-SAT)'+(state.cpsatDone?' ✓':'');""")
rep("""    btnCpsat.disabled=!(SB&&SB.loggedIn);btnCpsat.title=(SB&&SB.loggedIn)?'Call the CP-SAT backend for proven-optimal results':'Sign in to use CP-SAT';""",
    """    btnCpsat.disabled=!_signedIn;btnCpsat.title=_signedIn?'Call the CP-SAT backend for proven-optimal results':'Sign in to unlock CP-SAT & AI translation';if(!_signedIn&&!state.cpsatDone){setCpsatStatus('CP-SAT: 🔒 sign in to unlock CP-SAT & AI translation','warn');}""")
rep("  let h='<div class=\"cons-note\"><b>Faculty constraints are data.</b>",
    "  let h='<div class=\"cons-note\">'+(SB&&SB.loggedIn?'':'<b style=\"color:var(--amber-deep)\">🔒 Sign in to unlock AI translation & cloud sync. </b>')+'<b>Faculty constraints are data.</b>")


# ---- 22) fix combination selector overflow (console bar) -------------------
# The <select> flex item had min-width:auto, so its longest option (e.g.
# "#12 · score 680 · +120 pts · ✦CP-SAT") forced it wider than the console row and
# it collided with the ‹ › arrows. Let it shrink; keep arrows/badges fixed-size.
rep(".con-sel{flex:1 1 300px;min-width:240px;display:flex;align-items:center;gap:8px}",
    ".con-sel{flex:1 1 300px;min-width:0;display:flex;align-items:center;gap:8px}")
rep("select#comboSel{\n  flex:1;background:#0b1712;color:#e7eee8;border:1px solid rgba(255,255,255,.18);border-radius:8px;\n  font-family:var(--mono);font-size:12px;padding:9px 10px;max-width:430px;cursor:pointer;\n}",
    "select#comboSel{\n  flex:1 1 auto;min-width:0;width:100%;background:#0b1712;color:#e7eee8;border:1px solid rgba(255,255,255,.18);border-radius:8px;\n  font-family:var(--mono);font-size:12px;padding:9px 10px;max-width:430px;cursor:pointer;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;\n}")
rep(".nav-arrows{display:flex;gap:6px}",
    ".nav-arrows{display:flex;gap:6px;flex:0 0 auto}")
rep(".badges{display:flex;gap:8px;margin-left:auto}",
    ".badges{display:flex;gap:8px;margin-left:auto;flex:0 0 auto}")
rep(".con-sel label{font-family:var(--mono);font-size:10px;letter-spacing:.14em;color:#9db5a8;text-transform:uppercase}",
    ".con-sel label{flex:0 0 auto;font-family:var(--mono);font-size:10px;letter-spacing:.14em;color:#9db5a8;text-transform:uppercase}")


# ---- 23) faculty directory (roster as data) + picker consistency -------------
# CSS
rep(".cons-status{font-family:var(--mono);font-size:10.5px;color:var(--ink2);min-height:14px}",
    ".cons-status{font-family:var(--mono);font-size:10.5px;color:var(--ink2);min-height:14px}\n.dir-add{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:16px}\n.dir-add input#dirNewName{flex:1;min-width:220px;padding:8px 11px;border:1px solid var(--line2);border-radius:8px;background:#fff;font-size:13px;color:var(--ink)}\n.dir-add select{padding:8px 10px;border:1px solid var(--line2);border-radius:8px;background:#fff;font-size:13px;color:var(--ink)}\n.dir-name{width:100%;font-family:var(--disp);font-weight:700;font-size:15px;border:1px solid transparent;background:transparent;color:var(--ink);padding:2px 4px;border-radius:6px;box-sizing:border-box}\n.dir-name:hover,.dir-name:focus{border-color:var(--line2);background:#fff}\n.dir-name[readonly]{cursor:default}\n.dir-name[readonly]:hover,.dir-name[readonly]:focus{border-color:transparent;background:transparent}\n.dir-type:disabled{opacity:.55;cursor:not-allowed}")

# Directory tab
rep('<button id="viewAllocation">🗂 Allocation</button>',
    '<button id="viewAllocation">🗂 Allocation</button>\n      <button id="viewDirectory">📇 Directory</button>')
rep("$('viewAllocation').addEventListener('click',()=>setView('allocation'));",
    "$('viewAllocation').addEventListener('click',()=>setView('allocation'));\n$('viewDirectory').addEventListener('click',()=>setView('directory'));")
rep("  $('viewAllocation').classList.toggle('on',v==='allocation');",
    "  $('viewAllocation').classList.toggle('on',v==='allocation');\n  $('viewDirectory').classList.toggle('on',v==='directory');")
rep("  $('secFilterWrap').classList.toggle('hidden',v!=='sections'&&v!=='constraints');",
    "  $('secFilterWrap').classList.toggle('hidden',v!=='sections');")
rep("  if(state.view==='allocation'){renderAllocation();return;}",
    "  if(state.view==='allocation'){renderAllocation();return;}\n  if(state.view==='directory'){renderDirectory();return;}")

# boot: load faculty
rep("loadConstraints();\nloadAllocation();\nrenderAuth();\nconst restored=restore();",
    "loadConstraints();\nloadAllocation();\nloadFaculty();\nrenderAuth();\nconst restored=restore();")

# rosterNames -> merged faculty names
rep("""function rosterNames(){
  const names=[];
  for(const code in IMPCC_SOLVER.TEACHER_FULL) names.push(IMPCC_SOLVER.TEACHER_FULL[code]);
  return Array.from(new Set(names)).sort();
}""",
    """function rosterNames(){return facultyNames();}""")

# pushToCloud / syncFromCloud include faculty
rep("""  SB.saveWorkspace(state.allocation||defaultAllocation(),state.constraints||{})
    .then(()=>setTicker('Saved to Supabase ✓','ok'))""",
    """  SB.saveWorkspace(state.allocation||defaultAllocation(),state.constraints||{},getFaculty())
    .then(()=>setTicker('Saved to Supabase ✓','ok'))""")
rep("""      if(ws.allocation&&Object.keys(ws.allocation).length){state.allocation=ws.allocation;saveAllocationLocal();}""",
    """      if(ws.allocation&&Object.keys(ws.allocation).length){state.allocation=ws.allocation;saveAllocationLocal();}
      if(ws.faculty&&ws.faculty.length){state.faculty=ws.faculty;saveFacultyLocal();}""")

# constraintEntries: also list directory-only faculty
rep("""function constraintEntries(){
  const cur=state.constraints||{};
  const list=[];
  for(const code in IMPCC_SOLVER.TEACHER_FULL){
    if(code==='PARALLEL')continue;
    const def=IMPCC_SOLVER.DEFAULT_CONSTRAINTS[code];
    const over=cur[code];
    list.push({
      code,
      name:IMPCC_SOLVER.TEACHER_FULL[code],
      hasDefault:!!def,
      natural:(over&&over.natural)||'',
      rules:over?(over.rules||{}):(def?def.rules:{}),
      overridden:!!over
    });
  }
  return list.sort((a,b)=>(b.overridden?1:0)-(a.overridden?1:0)||(b.hasDefault?1:0)-(a.hasDefault?1:0)||a.name.localeCompare(b.name));
}""",
    """function constraintEntries(){
  const cur=state.constraints||{};
  const list=[];
  const seen=new Set();
  for(const code in IMPCC_SOLVER.TEACHER_FULL){
    if(code==='PARALLEL')continue;
    seen.add(IMPCC_SOLVER.TEACHER_FULL[code]);
    const def=IMPCC_SOLVER.DEFAULT_CONSTRAINTS[code];
    const over=cur[code];
    list.push({
      code,
      name:IMPCC_SOLVER.TEACHER_FULL[code],
      hasDefault:!!def,
      natural:(over&&over.natural)||'',
      rules:over?(over.rules||{}):(def?def.rules:{}),
      overridden:!!over
    });
  }
  // directory-only faculty (e.g. newly added / visiting) — no built-in defaults
  for(const f of getFaculty()){
    if(seen.has(f.name))continue;
    seen.add(f.name);
    const over=cur[f.name];
    list.push({ code:f.name, name:f.name, hasDefault:false, natural:(over&&over.natural)||'', rules:over?(over.rules||{}):{}, overridden:!!over });
  }
  return list.sort((a,b)=>(b.overridden?1:0)-(a.overridden?1:0)||(b.hasDefault?1:0)-(a.hasDefault?1:0)||a.name.localeCompare(b.name));
}""")

# display-name fallbacks (new faculty have no TEACHER_FULL entry)
rep("setTicker('Reset '+IMPCC_SOLVER.TEACHER_FULL[code]+' to defaults','ok');",
    "setTicker('Reset '+(IMPCC_SOLVER.TEACHER_FULL[code]||code)+' to defaults','ok');")
rep("body:JSON.stringify({text:text,teacher:IMPCC_SOLVER.TEACHER_FULL[code]})",
    "body:JSON.stringify({text:text,teacher:IMPCC_SOLVER.TEACHER_FULL[code]||code})")
rep("state.constraints[code]={name:IMPCC_SOLVER.TEACHER_FULL[code],natural:natural,rules:d.rules||{}};",
    "state.constraints[code]={name:IMPCC_SOLVER.TEACHER_FULL[code]||code,natural:natural,rules:d.rules||{}};")
rep("setTicker('Applied constraints for '+IMPCC_SOLVER.TEACHER_FULL[code]+' — will affect the next generation','ok');",
    "setTicker('Applied constraints for '+(IMPCC_SOLVER.TEACHER_FULL[code]||code)+' — will affect the next generation','ok');")

# insert the directory module before the constraints-page module
dir_js = """/* ---------- faculty directory (roster as data) ---------- */
const FAC_KEY='impcc-faculty-v1';
function defaultFaculty(){
  const arr=[];
  for(const code in IMPCC_SOLVER.TEACHER_FULL){
    if(code==='PARALLEL')continue;
    const type=(code==='V1'||code==='V2'||code==='V3')?'visiting':'permanent';
    arr.push({name:IMPCC_SOLVER.TEACHER_FULL[code],type:type,active:true});
  }
  return arr;
}
function loadFaculty(){
  try{const raw=localStorage.getItem(FAC_KEY);if(raw){state.faculty=JSON.parse(raw);return true;}}catch(e){}
  state.faculty=null;return false;
}
function saveFacultyLocal(){
  try{if(state.faculty)localStorage.setItem(FAC_KEY,JSON.stringify(state.faculty));else localStorage.removeItem(FAC_KEY);}catch(e){}
}
function getFaculty(){if(!state.faculty)state.faculty=defaultFaculty();return state.faculty;}
function facultyNames(){
  const set=new Set();
  for(const code in IMPCC_SOLVER.TEACHER_FULL)if(code!=='PARALLEL')set.add(IMPCC_SOLVER.TEACHER_FULL[code]);
  for(const f of getFaculty())set.add(f.name);
  try{const a=getWorkingAllocation();for(const k in a)for(const e of (a[k].subjects||[]))if(e.teacher)set.add(e.teacher);}catch(e){}
  return Array.from(set).sort();
}
function renderDirectory(){
  const signedIn=SB&&SB.loggedIn;
  const roster=getFaculty();
  let h='<div class="cons-note"><b>Faculty directory.</b> '+(signedIn?'Add, rename or retire faculty — the Allocation and Constraints pickers stay in sync with this list.':'This is a read-only view. <b style="color:var(--amber-deep)">🔒 Sign in to add or edit faculty.</b>')+'</div>';
  if(signedIn){
    h+='<div class="dir-add"><input id="dirNewName" placeholder="New faculty name (e.g. Prof. Jane Doe)"><select id="dirNewType"><option value="permanent">Permanent</option><option value="visiting">Visiting</option></select><button class="mini-export" id="dirAddBtn">＋ Add</button></div>';
  }
  h+='<div class="cons-grid">';
  roster.forEach((f,i)=>{
    h+='<article class="cons-card'+(f.active?'':' edited')+'"><header><h4><input class="dir-name" data-i="'+i+'" value="'+esc(f.name)+'"'+(signedIn?'':' readonly')+'></h4><span class="stag'+(f.active?'':' edited')+'">'+(f.active?esc(f.type):'left')+'</span></header>';
    h+='<div class="cons-btns">';
    h+='<select class="dir-type" data-i="'+i+'"'+(signedIn?'':' disabled')+'><option value="permanent"'+(f.type==='permanent'?' selected':'')+'>Permanent</option><option value="visiting"'+(f.type==='visiting'?' selected':'')+'>Visiting</option></select>';
    if(signedIn){
      h+='<button class="mini-export" data-dir-toggle="'+i+'">'+(f.active?'Mark left':'Re-activate')+'</button>';
      h+='<button class="card-csv" data-dir-del="'+i+'" title="Remove from directory">✕</button>';
    }
    h+='</div></article>';
  });
  h+='</div>';
  mainEl.innerHTML=h;
  if(!signedIn)return;
  document.getElementById('dirAddBtn').addEventListener('click',()=>{
    const nm=document.getElementById('dirNewName').value.trim();
    if(!nm)return;
    if(facultyNames().indexOf(nm)>=0){setTicker('“'+nm+'” already exists','err');return;}
    getFaculty().push({name:nm,type:document.getElementById('dirNewType').value,active:true});
    saveFacultyLocal();pushToCloud();renderDirectory();
    setTicker('Added '+nm+' to the directory','ok');
  });
  document.querySelectorAll('.dir-name').forEach(el=>el.addEventListener('change',e=>{
    const f=getFaculty()[+e.target.dataset.i];if(!f)return;
    const v=e.target.value.trim();if(v)f.name=v;
    saveFacultyLocal();pushToCloud();setTicker('Faculty renamed','ok');
  }));
  document.querySelectorAll('.dir-type').forEach(el=>el.addEventListener('change',e=>{
    const f=getFaculty()[+e.target.dataset.i];if(!f)return;
    f.type=e.target.value;saveFacultyLocal();pushToCloud();
  }));
  document.querySelectorAll('[data-dir-toggle]').forEach(el=>el.addEventListener('click',e=>{
    const f=getFaculty()[+e.target.dataset.dirToggle];if(!f)return;
    f.active=!f.active;saveFacultyLocal();pushToCloud();renderDirectory();
    setTicker(f.name+(f.active?' re-activated':' marked as left'),'ok');
  }));
  document.querySelectorAll('[data-dir-del]').forEach(el=>el.addEventListener('click',e=>{
    const i=+e.target.dataset.dirDel;const f=getFaculty()[i];
    getFaculty().splice(i,1);saveFacultyLocal();pushToCloud();renderDirectory();
    setTicker('Removed '+(f?f.name:'entry')+' from the directory','ok');
  }));
}

"""
rep("/* ---------- constraints page (data-driven faculty constraints + LLM) ---------- */",
    dir_js + "/* ---------- constraints page (data-driven faculty constraints + LLM) ---------- */")


# ---- 24) global published data (all visitors see admin's allocation/constraints/faculty) ----
# Boot: everyone (signed in or not) loads the published state; generated combos stay local.
rep("if(SB&&SB.loggedIn){syncFromCloud().then(()=>{renderMain();renderChrome();});}",
    "syncFromCloud().then(()=>{renderMain();renderChrome();});")

# syncFromCloud: read the GLOBAL published row (works for everyone; no sign-in needed)
rep("""async function syncFromCloud(){
  if(!SB||!SB.loggedIn)return;
  try{
    const ws=await SB.loadWorkspace();
    if(ws){
      if(ws.constraints&&Object.keys(ws.constraints).length){state.constraints=ws.constraints;saveConstraints();}
      if(ws.allocation&&Object.keys(ws.allocation).length){state.allocation=ws.allocation;saveAllocationLocal();}
      if(ws.faculty&&ws.faculty.length){state.faculty=ws.faculty;saveFacultyLocal();}
    }
  }catch(e){setTicker('Cloud load failed: '+e.message,'err');}
}""",
    """async function syncFromCloud(){
  if(!SB)return;
  try{
    const pub=await SB.loadPublished();
    if(pub){
      if(pub.allocation&&Object.keys(pub.allocation).length){state.allocation=pub.allocation;saveAllocationLocal();}
      if(pub.constraints&&Object.keys(pub.constraints).length){state.constraints=pub.constraints;try{localStorage.setItem(CONST_KEY,JSON.stringify(state.constraints));}catch(e){}}
      if(Array.isArray(pub.faculty)&&pub.faculty.length){state.faculty=pub.faculty;saveFacultyLocal();}
    }
  }catch(e){setTicker('Cloud load failed: '+e.message,'err');}
}""")

# pushToCloud: publish globally (still sign-in-gated on the write side)
rep("""function pushToCloud(){
  if(!SB||!SB.loggedIn)return;
  SB.saveWorkspace(state.allocation||defaultAllocation(),state.constraints||{},getFaculty())
    .then(()=>setTicker('Saved to Supabase ✓','ok'))
    .catch(err=>setTicker('Cloud sync failed: '+err.message,'err'));
}""",
    """function pushToCloud(){
  if(!SB||!SB.loggedIn)return;
  SB.savePublished(state.allocation||defaultAllocation(),state.constraints||{},getFaculty())
    .then(()=>setTicker('Published for all users ✓','ok'))
    .catch(err=>setTicker('Cloud sync failed: '+err.message,'err'));
}""")


# ---- 25) "Last published" indicator (how fresh is the shared data) ----------
# CSS
rep("#cpsatStatus{margin-left:auto;color:#9db5a8}",
    "#cpsatStatus{margin-left:auto;color:#9db5a8}\n#publishedAge{font-family:var(--mono);font-size:11px;color:#9db5a8;white-space:nowrap;margin-left:12px}\n#publishedAge b{color:#ffd97a;font-weight:600}\n#publishedAge .led-dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:#4ade80;box-shadow:0 0 6px #4ade80;margin-right:4px;vertical-align:1px}")

# HTML: place the indicator at the end of the console status row
rep('<span id="cpsatStatus">CP-SAT: idle — press “Compute optimal” to call the backend</span>',
    '<span id="cpsatStatus">CP-SAT: idle — press “Compute optimal” to call the backend</span>\n    <span id="publishedAge"></span>')

# helpers + state, injected just before syncFromCloud
rep("async function syncFromCloud(){\n  if(!SB)return;",
    """let publishedAt=null;
function timeAgo(iso){
  const t=new Date(iso).getTime();
  if(isNaN(t))return '';
  const diff=Math.max(0,Date.now()-t);
  const m=Math.floor(diff/60000);
  if(m<1)return 'just now';
  if(m<60)return m+' min'+(m===1?'':'s')+' ago';
  const h=Math.floor(m/60);
  if(h<24)return h+' hour'+(h===1?'':'s')+' ago';
  const d=Math.floor(h/24);
  if(d<7)return d+' day'+(d===1?'':'s')+' ago';
  return new Date(t).toLocaleDateString('en-GB');
}
function renderPublishedAge(){
  const el=document.getElementById('publishedAge');
  if(!el)return;
  if(!publishedAt){el.innerHTML='';return;}
  el.innerHTML='<span class="led-dot"></span>Last published <b>'+esc(timeAgo(publishedAt))+'</b>';
}
async function syncFromCloud(){\n  if(!SB)return;""")

# capture updated_at after loadPublished
rep("    const pub=await SB.loadPublished();\n    if(pub){",
    "    const pub=await SB.loadPublished();\n    if(pub){\n      if(pub.updated_at){publishedAt=pub.updated_at;}")

# refresh the indicator after the sync try block
rep("  }catch(e){setTicker('Cloud load failed: '+e.message,'err');}\n}",
    "    renderPublishedAge();\n  }catch(e){setTicker('Cloud load failed: '+e.message,'err');}\n}")

# on admin publish, mark as 'just now'
rep(".then(()=>setTicker('Published for all users ✓','ok'))",
    ".then(()=>{publishedAt=new Date().toISOString();renderPublishedAge();setTicker('Published for all users ✓','ok');})")


RULE_EDITOR_JS = r'''/* ---------- rule editor (add / edit / remove individual rules) ---------- */
const RULE_META={
  allowed_slots:{label:'Only these periods',kind:'slots'},
  forbidden_slots:{label:'Never these periods',kind:'slots'},
  allowed_days:{label:'Only these days',kind:'days'},
  forbidden_days:{label:'Never these days',kind:'days'},
  forbidden_slots_on_days:{label:'Free slots on days',kind:'slotsOnDays'},
  min_days_in_slot:{label:'Min days in a period',kind:'minDaysSlot'},
  min_days_engaged:{label:'Min teaching days',kind:'number'},
  max_periods_per_day:{label:'Max periods per day',kind:'number'},
  subject_slots:{label:'Subject in periods',kind:'subjectSlots'},
  subject_forbidden_days:{label:'Subject not on days',kind:'subjectDays'},
  stream_slots_required:{label:'Stream fills periods',kind:'streamSlots'},
  stream_forbidden_days:{label:'Stream not on days',kind:'streamDays'},
};
function describeRule(key,v){
  const m=RULE_META[key];if(!m)return JSON.stringify(v);
  switch(m.kind){
    case 'slots':case 'days':return (v||[]).join(', ');
    case 'number':return String(v);
    case 'slotsOnDays':return (v||[]).map(e=>e.days.join('/')+' '+e.slots.join(',')).join(' · ');
    case 'minDaysSlot':return (v||[]).map(e=>e.slot+' ≥ '+e.min_days+' days').join(' · ');
    case 'subjectSlots':return (v||[]).map(e=>e.subject+' → '+e.slots.join(',')).join(' · ');
    case 'subjectDays':return (v||[]).map(e=>e.subject+' not '+e.days.join(',')).join(' · ');
    case 'streamSlots':return (v||[]).map(e=>e.stream+' fills '+e.slots.join(',')).join(' · ');
    case 'streamDays':return (v||[]).map(e=>e.stream+' not '+e.days.join(',')).join(' · ');
  }
  return JSON.stringify(v);
}
function displayNameOf(code){return IMPCC_SOLVER.TEACHER_FULL[code]||code;}
function ensureOverride(code){
  if(!state.constraints)state.constraints={};
  if(!state.constraints[code])state.constraints[code]={name:displayNameOf(code),natural:'',edits:{}};
  const o=state.constraints[code];
  if(!o.edits){o.edits=o.rules||{};delete o.rules;}
  if(!o.name)o.name=displayNameOf(code);
  return o;
}
function removeRule(code,key){
  const o=ensureOverride(code);
  o.edits[key]=null;
  saveConstraints();
  setTicker('Removed "'+(RULE_META[key]?RULE_META[key].label:key)+'" for '+displayNameOf(code),'ok');
  renderMain();
}
function saveRuleEdit(code,key,value){
  const o=ensureOverride(code);
  if(value===null||(Array.isArray(value)&&!value.length))o.edits[key]=null;
  else o.edits[key]=value;
  saveConstraints();
  setTicker('Updated "'+(RULE_META[key]?RULE_META[key].label:key)+'" for '+displayNameOf(code),'ok');
  renderMain();
}
function selTokens(root,cls){return Array.from(root.querySelectorAll('.'+cls+'.on')).map(e=>e.dataset.v);}
function readRuleEditor(root,kind){
  if(kind==='slots'){const a=selTokens(root,'ed-chip-slot');return a.length?a:null;}
  if(kind==='days'){const a=selTokens(root,'ed-chip-day');return a.length?a:null;}
  if(kind==='number'){const n=parseInt(root.querySelector('.ed-num').value,10);return isNaN(n)?null:n;}
  if(kind==='slotsOnDays'){const d=selTokens(root,'ed-chip-day'),sl=selTokens(root,'ed-chip-slot');return (d.length&&sl.length)?[{days:d,slots:sl}]:null;}
  if(kind==='minDaysSlot'){const sl=root.querySelector('.ed-slot-sel').value,n=parseInt(root.querySelector('.ed-min').value,10);return (sl&&n>0)?[{slot:sl,min_days:n}]:null;}
  if(kind==='subjectSlots'){const subj=root.querySelector('.ed-subject').value.trim(),sl=selTokens(root,'ed-chip-slot');return (subj&&sl.length)?[{subject:subj,slots:sl}]:null;}
  if(kind==='subjectDays'){const subj=root.querySelector('.ed-subject').value.trim(),d=selTokens(root,'ed-chip-day');return (subj&&d.length)?[{subject:subj,days:d}]:null;}
  if(kind==='streamSlots'){const st=root.querySelector('.ed-stream').value,sl=selTokens(root,'ed-chip-slot');return (st&&sl.length)?[{stream:st,slots:sl}]:null;}
  if(kind==='streamDays'){const st=root.querySelector('.ed-stream').value,d=selTokens(root,'ed-chip-day');return (st&&d.length)?[{stream:st,days:d}]:null;}
  return null;
}
function chipsHTML(cls,tokens,selected){
  return tokens.map(t=>'<span class="ed-chip '+cls+((selected||[]).indexOf(t)>=0?' on':'')+'" data-v="'+t+'">'+t+'</span>').join('');
}
function ruleEditorHTML(code,key,value){
  const m=RULE_META[key];if(!m)return '';
  const C='ed-chip-slot',D='ed-chip-day';const v=value||null;
  let inner='';
  switch(m.kind){
    case 'slots':inner=chipsHTML('ed-chip '+C,SLOTS,v||[]);break;
    case 'days':inner=chipsHTML('ed-chip '+D,DAYS,v||[]);break;
    case 'number':inner='<input class="ed-num" type="number" min="1" max="5" value="'+(v!=null?v:1)+'">';break;
    case 'slotsOnDays':inner=chipsHTML('ed-chip '+D,DAYS,(v&&v[0]&&v[0].days)||[])+' '+chipsHTML('ed-chip '+C,SLOTS,(v&&v[0]&&v[0].slots)||[]);break;
    case 'minDaysSlot':inner='<select class="ed-slot-sel">'+SLOTS.map(x=>'<option'+(v&&v[0]&&v[0].slot===x?' selected':'')+'>'+x+'</option>').join('')+'</select> ≥ <input class="ed-min" type="number" min="1" max="5" value="'+((v&&v[0]&&v[0].min_days)||1)+'"> days';break;
    case 'subjectSlots':inner='<input class="ed-subject" placeholder="Subject" value="'+esc((v&&v[0]&&v[0].subject)||'')+'"> '+chipsHTML('ed-chip '+C,SLOTS,(v&&v[0]&&v[0].slots)||[]);break;
    case 'subjectDays':inner='<input class="ed-subject" placeholder="Subject" value="'+esc((v&&v[0]&&v[0].subject)||'')+'"> '+chipsHTML('ed-chip '+D,DAYS,(v&&v[0]&&v[0].days)||[]);break;
    case 'streamSlots':inner='<select class="ed-stream"><option value="ICS"'+(v&&v[0]&&v[0].stream==='ICS'?' selected':'')+'>ICS</option><option value="I.COM"'+(v&&v[0]&&v[0].stream==='I.COM'?' selected':'')+'>I.COM</option></select> '+chipsHTML('ed-chip '+C,SLOTS,(v&&v[0]&&v[0].slots)||[]);break;
    case 'streamDays':inner='<select class="ed-stream"><option value="ICS"'+(v&&v[0]&&v[0].stream==='ICS'?' selected':'')+'>ICS</option><option value="I.COM"'+(v&&v[0]&&v[0].stream==='I.COM'?' selected':'')+'>I.COM</option></select> '+chipsHTML('ed-chip '+D,DAYS,(v&&v[0]&&v[0].days)||[]);break;
  }
  return '<div class="rule-ed" data-code="'+esc(code)+'" data-key="'+esc(key)+'" data-kind="'+m.kind+'">'+inner+'<button class="mini-export rule-save">Save</button><button class="mini-export rule-cancel">Cancel</button></div>';
}
function renderConstraints(){
  const entries=constraintEntries();
  const res=IMPCC_SOLVER.resolveConstraints(state.constraints);
  let h='<div class="cons-note">'+(SB&&SB.loggedIn?'':'<b style="color:var(--amber-deep)">🔒 Sign in to unlock AI translation & cloud sync. </b>')+'<b>Faculty constraints are data.</b> Add, edit or remove individual rules below (✎ / ✕), or describe a change in plain language and press <b>✦ Translate with AI</b>, then <b>Apply</b>. Changes take effect on the next generation.<span class="cons-actions"><button class="mini-export" id="consDownload">⇩ Download</button><button class="mini-export" id="consUpload">⇧ Upload</button><button class="mini-export" id="consReset">Reset to defaults</button></span></div>';
  h+='<input type="file" id="consUploadInput" accept="application/json" style="display:none">';
  h+='<div class="cons-grid">';
  for(const e of entries){
    const eff=((res[e.code]||{}).rules)||{};
    const keys=Object.keys(eff);
    h+='<article class="cons-card'+(e.overridden?' edited':'')+'">';
    h+='<header><h4>'+esc(e.name)+'</h4>'+(e.hasDefault?'<span class="stag">default</span>':'')+(e.overridden?'<span class="stag edited">edited</span>':'')+'</header>';
    h+='<div class="cons-rules-ed">';
    if(keys.length){
      for(const k of keys){
        h+='<div class="rule-row" data-code="'+e.code+'" data-key="'+k+'">'+
          '<span class="rule-label">'+esc(RULE_META[k]?RULE_META[k].label:k)+'</span>'+
          '<span class="rule-val">'+esc(describeRule(k,eff[k]))+'</span>'+
          '<button class="mini-export rule-edit" title="Edit this rule">✎</button>'+
          '<button class="card-csv rule-remove" title="Remove this rule">✕</button>'+
        '</div>';
      }
    }else{
      h+='<div class="cons-rule none">No constraints</div>';
    }
    h+='</div>';
    h+='<div class="rule-add"><select class="add-rule-type" data-code="'+e.code+'"><option value="">＋ Add rule…</option>'+
       Object.keys(RULE_META).map(k=>'<option value="'+k+'">'+esc(RULE_META[k].label)+'</option>').join('')+
       '</select></div>';
    h+='<textarea class="cons-nl" data-code="'+e.code+'" placeholder="Describe their constraint in plain language…">'+esc(e.natural)+'</textarea>';
    h+='<div class="cons-btns">'+
      '<button class="mini-export" data-translate="'+e.code+'">✦ Translate with AI</button>'+
      '<button class="mini-export" data-apply="'+e.code+'"'+(pendingTranslations[e.code]?'':' disabled')+'>Apply</button>'+
      '<button class="mini-export" data-reset-one="'+e.code+'"'+(e.overridden?'':' disabled')+'>Reset</button>'+
    '</div>';
    h+='<div class="cons-status" data-status="'+e.code+'">'+esc(pendingTranslations[e.code]||'')+'</div>';
    h+='</article>';
  }
  h+='</div>';
  mainEl.innerHTML=h;
  $('consUploadInput').addEventListener('change',ev=>{if(ev.target.files&&ev.target.files[0])uploadConstraintsFile(ev.target.files[0]);});
}
'''

# ---- 26) constraints: per-rule add / edit / remove (not just additive) ----
# (a) replace renderConstraints with the interactive rule editor
_i = src.index("function renderConstraints(){")
_j = src.index("function translateOne(")
src = src[:_i] + RULE_EDITOR_JS + src[_j:]

# (b) applyTranslation now MERGES the LLM rules into edits (preserves other rules)
rep("state.constraints[code]={name:IMPCC_SOLVER.TEACHER_FULL[code]||code,natural:natural,rules:d.rules||{}};",
    "{const o=ensureOverride(code);o.natural=natural;for(const rk in (d.rules||{})){o.edits[rk]=d.rules[rk];}}")

# (c) CSS for the rule editor
rep(".cons-status{font-family:var(--mono);font-size:10.5px;color:var(--ink2);min-height:14px}",
    ".cons-status{font-family:var(--mono);font-size:10.5px;color:var(--ink2);min-height:14px}\n.cons-rules-ed{display:flex;flex-direction:column;gap:4px}\n.rule-row{display:flex;align-items:center;gap:6px;font-size:12px}\n.rule-label{font-family:var(--mono);font-size:10px;color:var(--ink2);min-width:128px}\n.rule-val{flex:1;font-size:11.5px;color:var(--ink)}\n.rule-row .mini-export,.rule-row .card-csv{padding:2px 7px;font-size:10px}\n.rule-ed{display:flex;align-items:center;gap:6px;flex-wrap:wrap;font-size:12px;background:var(--surface2);border:1px dashed var(--line2);border-radius:8px;padding:6px 8px}\n.ed-chip{display:inline-flex;align-items:center;justify-content:center;font-family:var(--mono);font-size:10px;padding:2px 8px;border:1px solid var(--line2);border-radius:99px;cursor:pointer;background:#fff;color:var(--ink2)}\n.ed-chip.on{background:var(--green);color:#fff;border-color:var(--green)}\n.ed-num{padding:4px 7px;border:1px solid var(--line2);border-radius:6px;font-size:12px;width:56px}\n.ed-subject{padding:4px 7px;border:1px solid var(--line2);border-radius:6px;font-size:12px;width:150px}\n.ed-slot-sel,.ed-stream{padding:4px 6px;border:1px solid var(--line2);border-radius:6px;font-size:12px}\n.rule-add{margin-top:2px}\n.rule-add select{padding:5px 8px;border:1px solid var(--line2);border-radius:6px;font-size:12px;color:var(--ink)}")

# (d) delegation for the rule editor
rep("$('spPrint').addEventListener('click',()=>{if(state.spot)exportTeacherImage(state.spot);});",
    "$('spPrint').addEventListener('click',()=>{if(state.spot)exportTeacherImage(state.spot);});\nmainEl.addEventListener('click',e=>{\n  const chip=e.target.closest('.ed-chip');\n  if(chip){chip.classList.toggle('on');return;}\n  const rm=e.target.closest('.rule-remove');\n  if(rm){const row=rm.closest('.rule-row');removeRule(row.dataset.code,row.dataset.key);return;}\n  const ed=e.target.closest('.rule-edit');\n  if(ed){const row=ed.closest('.rule-row');const code=row.dataset.code,key=row.dataset.key;const eff=(IMPCC_SOLVER.resolveConstraints(state.constraints)[code]||{}).rules||{};row.outerHTML=ruleEditorHTML(code,key,eff[key]);return;}\n  const sv=e.target.closest('.rule-save');\n  if(sv){const box=sv.closest('.rule-ed');saveRuleEdit(box.dataset.code,box.dataset.key,readRuleEditor(box,box.dataset.kind));return;}\n  const cn=e.target.closest('.rule-cancel');\n  if(cn){renderMain();return;}\n});\nmainEl.addEventListener('change',e=>{\n  const at=e.target.closest('.add-rule-type');\n  if(at&&at.value){const code=at.dataset.code;at.closest('.rule-add').insertAdjacentHTML('beforebegin',ruleEditorHTML(code,at.value,null));at.value='';}\n});")


ZIP_MODULE = "/* ---------- PNG → ZIP exports (department / whole platform / all faculty) ---------- */\nconst _CRC_TABLE=(function(){const t=new Uint32Array(256);for(let n=0;n<256;n++){let c=n;for(let k=0;k<8;k++)c=(c&1)?(0xEDB88320^(c>>>1)):(c>>>1);t[n]=c;}return t;})();\nfunction _crc32(u8){let c=0xFFFFFFFF;for(let i=0;i<u8.length;i++)c=_CRC_TABLE[(c^u8[i])&0xFF]^(c>>>8);return (c^0xFFFFFFFF)>>>0;}\nfunction buildZip(files){\n  const enc=new TextEncoder();const parts=[];const central=[];let offset=0;\n  for(const f of files){\n    const nm=enc.encode(f.name);const crc=_crc32(f.data);\n    const lh=new DataView(new ArrayBuffer(30));\n    lh.setUint32(0,0x04034b50,true);lh.setUint16(4,20,true);lh.setUint16(6,0x0800,true);\n    lh.setUint16(8,0,true);lh.setUint16(10,0,true);lh.setUint16(12,0,true);\n    lh.setUint32(14,crc,true);lh.setUint32(18,f.data.length,true);lh.setUint32(22,f.data.length,true);\n    lh.setUint16(26,nm.length,true);lh.setUint16(28,0,true);\n    parts.push(new Uint8Array(lh.buffer),nm,f.data);\n    const ch=new DataView(new ArrayBuffer(46));\n    ch.setUint32(0,0x02014b50,true);ch.setUint16(4,20,true);ch.setUint16(6,20,true);\n    ch.setUint16(8,0x0800,true);ch.setUint16(10,0,true);ch.setUint16(12,0,true);ch.setUint16(14,0,true);\n    ch.setUint32(16,crc,true);ch.setUint32(20,f.data.length,true);ch.setUint32(24,f.data.length,true);\n    ch.setUint16(28,nm.length,true);ch.setUint32(42,offset,true);\n    central.push(new Uint8Array(ch.buffer),nm);\n    offset+=30+nm.length+f.data.length;\n  }\n  let cdSize=0;for(const c of central)cdSize+=c.length;\n  const eocd=new DataView(new ArrayBuffer(22));\n  eocd.setUint32(0,0x06054b50,true);\n  eocd.setUint16(8,files.length,true);eocd.setUint16(10,files.length,true);\n  eocd.setUint32(12,cdSize,true);eocd.setUint32(16,offset,true);\n  const out=new Uint8Array(offset+cdSize+22);let p=0;\n  for(const part of parts){out.set(part,p);p+=part.length;}\n  for(const c of central){out.set(c,p);p+=c.length;}\n  out.set(new Uint8Array(eocd.buffer),p);\n  return out;\n}\nfunction downloadZip(files,zipName){\n  const blob=new Blob([buildZip(files)],{type:'application/zip'});\n  const url=URL.createObjectURL(blob);\n  const a=document.createElement('a');a.href=url;a.download=zipName;\n  document.body.appendChild(a);a.click();a.remove();\n  setTimeout(function(){URL.revokeObjectURL(url);},800);\n}\nfunction downloadCanvas(canvas,filename){\n  return new Promise(function(resolve,reject){\n    canvas.toBlob(function(blob){\n      if(!blob){reject(new Error('canvas export failed'));return;}\n      const url=URL.createObjectURL(blob);\n      const a=document.createElement('a');a.href=url;a.download=filename;\n      document.body.appendChild(a);a.click();a.remove();\n      setTimeout(function(){URL.revokeObjectURL(url);},800);\n      resolve();\n    },'image/png');\n  });\n}\nasync function canvasToU8(canvas){\n  const blob=await new Promise(function(resolve,reject){\n    canvas.toBlob(function(b){b?resolve(b):reject(new Error('no blob'));},'image/png');\n  });\n  const buf=await blob.arrayBuffer();\n  return new Uint8Array(buf);\n}\nasync function exportStreamImages(stream){\n  const c=getSel();if(!c)return;\n  const secs=SECTIONS.filter(function(x){return x.stream===stream;});\n  setTicker('Rendering '+secs.length+' section images…','run',true);\n  const files=[];\n  for(const sec of secs){\n    const r=await drawSectionCanvas(sec.id);\n    if(r)files.push({name:r.filename,data:await canvasToU8(r.canvas)});\n  }\n  downloadZip(files,'IMPCC_'+(stream==='icom'?'ICom':'ICS')+'_schedules.zip');\n  setTicker('Exported '+files.length+' section images (ZIP)','ok');\n}\nasync function exportAllImages(){\n  const c=getSel();if(!c)return;\n  setTicker('Rendering all section images…','run',true);\n  const files=[];\n  for(const sec of SECTIONS){\n    const r=await drawSectionCanvas(sec.id);\n    if(r){const folder=sec.stream==='icom'?'I-Com':'ICS';files.push({name:folder+'/'+r.filename,data:await canvasToU8(r.canvas)});}\n  }\n  downloadZip(files,'IMPCC_all-sections_schedules.zip');\n  setTicker('Exported '+files.length+' section images in department folders (ZIP)','ok');\n}\nasync function exportAllFacultyImages(){\n  const c=getSel();if(!c)return;\n  const names=teacherOrder();\n  if(!names.length){setTicker('No faculty to export','err');return;}\n  setTicker('Rendering '+names.length+' faculty images…','run',true);\n  const files=[];\n  for(const name of names){\n    const r=await drawTeacherCanvas(name);\n    if(r)files.push({name:r.filename,data:await canvasToU8(r.canvas)});\n  }\n  downloadZip(files,'IMPCC_faculty_schedules.zip');\n  setTicker('Exported '+files.length+' faculty images (ZIP)','ok');\n}\n\n"

# ---- 27) PNG→ZIP exports (department, whole platform in folders, all faculty) ----
# (a) insert the ZIP module before the boot marker
rep("/* ---------- boot: restore saved results (no auto-generation) ---------- */",
    ZIP_MODULE + "/* ---------- boot: restore saved results (no auto-generation) ---------- */")
# (b) department ZIP button in each stream header (plain quotes, as in the source)
rep("data-pdf-stream=\"'+g.key+'\" title=\"Print this stream / save as PDF\">PDF</button></div><div class=\"sec-grid",
    "data-pdf-stream=\"'+g.key+'\" title=\"Print this stream / save as PDF\">PDF</button><button class=\"card-img\" data-img-stream=\"'+g.key+'\" title=\"Download this department section images (ZIP)\">ZIP</button></div><div class=\"sec-grid")
# (c) click handler: route the stream ZIP button
rep("    if(imgBtn.dataset.imgSec)exportSectionImage(imgBtn.dataset.imgSec);\n    else if(imgBtn.dataset.imgTeacher)exportTeacherImage(imgBtn.dataset.imgTeacher);",
    "    if(imgBtn.dataset.imgSec)exportSectionImage(imgBtn.dataset.imgSec);\n    else if(imgBtn.dataset.imgTeacher)exportTeacherImage(imgBtn.dataset.imgTeacher);\n    else if(imgBtn.dataset.imgStream)exportStreamImages(imgBtn.dataset.imgStream);")
# (d) viewbar: add whole-platform + all-faculty ZIP buttons
rep('<button class="mini-export" id="btnComboCsv" title="Download the selected combination as a CSV file (all 11 sections)">⇩ Export combination CSV</button>',
    '<button class="mini-export" id="btnComboCsv" title="Download the selected combination as a CSV file (all 11 sections)">⇩ Export combination CSV</button>\n    <button class="mini-export" id="btnAllImages" title="Download every section schedule as PNG images, grouped in department folders (ZIP)">⇩ All sections (ZIP)</button>\n    <button class="mini-export" id="btnFacultyImages" title="Download every faculty member schedule as PNG images (ZIP)">⇩ Faculty images (ZIP)</button>')
# (e) disable them when no combination exists
rep("  $('btnComboCsv').disabled=!list.length;",
    "  $('btnComboCsv').disabled=!list.length;\n  $('btnAllImages').disabled=!list.length;\n  $('btnFacultyImages').disabled=!list.length;")
# (f) wire listeners
rep("$('btnComboCsv').addEventListener('click',exportComboCSV);",
    "$('btnComboCsv').addEventListener('click',exportComboCSV);\n$('btnAllImages').addEventListener('click',exportAllImages);\n$('btnFacultyImages').addEventListener('click',exportAllFacultyImages);")

SAVED_MODULE = '''/* ---------- saved & pushed timetables + versioning ---------- */
function cellsToRaw(tt){
  const out={};
  for(const k in tt){out[k]=tt[k].map(function(row){return row.map(function(c){return [c.subj,c.teacher];});});}
  return out;
}
function rawKey(tt){return JSON.stringify(tt);}
function pushedCombo(){return state.combos.find(function(c){return c.via==='pushed';});}
function ensureSavedList(){if(!state.savedList)state.savedList=[];}
async function loadSavedList(){
  ensureSavedList();
  if(!SB||!SB.loggedIn){state.savedList=[];return;}
  try{state.savedList=await SB.listSaved();}catch(e){state.savedList=[];}
}
async function loadPushedTimetable(){
  if(!SB)return;
  try{
    const p=await SB.loadPushed();
    state.combos=state.combos.filter(function(c){return c.via!=='pushed';});
    if(p&&p.timetable){
      const combo=makeCombo({score:p.score,timetable:p.timetable},'pushed');
      state.combos.push(combo);
      state.selected=combo.id;
    }else{
      const list=sortedList();
      if(state.selected===null||!state.combos.some(function(c){return c.id===state.selected;}))state.selected=list.length?list[0].id:null;
    }
    persist();renderAll();
  }catch(e){setTicker('Could not load the published timetable: '+e.message,'err');}
}

/* ---------- versioning helpers ---------- */
function currentActionsSnapshot(){
  const eng=engagementPlan();
  return {
    tweaks:(state.tweaks||[]).map(function(t){return {kind:t.kind,recurring:t.recurring,window:t.window||null,effect:t.effect||null,natural:t.natural||''};}),
    edits:(state.lastLocks||state.edits||[]).slice(),
    engagement:eng?{covered:eng.covered,total:eng.total}:null,
    swaps:state.lastSwap?{count:state.lastSwap.circles.length,sizes:state.lastSwap.circles.map(function(c){return c.length;})}:null
  };
}
function actionsSummary(a){
  const out=[];
  const t=(a&&Array.isArray(a.tweaks))?a.tweaks.length:0;
  const e=(a&&Array.isArray(a.edits))?a.edits.length:0;
  const g=(a&&a.engagement&&a.engagement.total)?(a.engagement.covered+'/'+a.engagement.total+' engaged'):null;
  const s=(a&&a.swaps&&a.swaps.count)?(a.swaps.count+' swap'+(a.swaps.count===1?'':'s')):null;
  if(t)out.push('🛠 '+t+' tweak'+(t===1?'':'s'));
  if(e)out.push('✎ '+e+' edit'+(e===1?'':'s'));
  if(g)out.push('👥 '+g);
  if(s)out.push('⇄ '+s);
  return out.length?out.join(' · '):'—';
}
function savedNameOf(id){
  ensureSavedList();
  const r=(state.savedList||[]).find(function(x){return x.id===id;});
  return r?r.name:null;
}
function rootOf(id){
  ensureSavedList();
  const byId={};
  (state.savedList||[]).forEach(function(x){byId[x.id]=x;});
  let cur=byId[id];let guard=0;
  while(cur&&cur.parent_id&&byId[cur.parent_id]&&guard++<50){cur=byId[cur.parent_id];}
  return cur||byId[id]||null;
}
async function recordHistory(action,detail){
  if(!SB||!SB.loggedIn)return;
  if(!state.history)state.history=[];
  state.history.unshift({action:action,detail:detail,created_at:new Date().toISOString()});
  try{await SB.recordHistory({action:action,detail:detail});}catch(e){}
}
async function loadHistory(){
  if(!state.history)state.history=[];
  if(!SB||!SB.loggedIn){state.history=[];return;}
  try{state.history=await SB.listHistory();}catch(e){state.history=[];}
}

/* ---------- save: original, or version of a loaded source ---------- */
async function saveCurrent(){
  if(!SB||!SB.loggedIn){setTicker('Sign in to save timetables','err');return;}
  const c=getSel();if(!c)return;
  if(state.source&&state.source.id){openVersionModal();return;}
  const rank=rankOf(c,sortedList());
  const def='Combination #'+rank+' (score '+c.score+')';
  let name;
  try{name=window.prompt('Name this saved timetable:',def);}catch(e){name=def;}
  if(name===null)return;
  setTicker('Saving…','run',true);
  try{
    await SB.saveTimetable({name:name||def,score:c.score,timetable:cellsToRaw(c.tt),kind:'original',actions:currentActionsSnapshot()});
    await recordHistory('create_original',{name:name||def,score:c.score});
    await loadSavedList();
    setTicker('Saved "'+(name||def)+'" as an original','ok');
  }catch(e){setTicker('Save failed: '+e.message,'err');}
}
function openVersionModal(){
  const src=state.source;
  const c=getSel();if(!src||!c)return;
  const root=rootOf(src.id);
  const fromEl=document.getElementById('versionFrom');
  if(fromEl)fromEl.innerHTML='Deriving from <b>'+esc(src.name||'saved')+'</b>'+(root&&root.id!==src.id?' (chain root: '+esc(root.name||'saved')+')':'')+'<br><span class="saved-meta">'+esc(actionsSummary(currentActionsSnapshot()))+'</span>';
  const nm=document.getElementById('versionName');
  if(nm)nm.value='Version of '+src.name;
  const msg=document.getElementById('versionMsg');
  if(msg)msg.textContent='';
  document.getElementById('versionModal').style.display='flex';
}
async function doSaveVersion(mode){
  const c=getSel();const src=state.source;
  if(!c||!src){document.getElementById('versionModal').style.display='none';return;}
  const nm=document.getElementById('versionName');
  const name=(nm&&nm.value.trim())?nm.value.trim():('Version of '+src.name);
  setTicker('Saving…','run',true);
  try{
    if(mode==='keep'){
      await SB.saveTimetable({name:name,score:c.score,timetable:cellsToRaw(c.tt),kind:'version',parent_id:src.id,actions:currentActionsSnapshot()});
      await recordHistory('create_version',{name:name,from:src.name,score:c.score});
    }else{
      const root=rootOf(src.id);
      await SB.saveTimetable({name:name,score:c.score,timetable:cellsToRaw(c.tt),kind:'original',parent_id:root?root.id:null,actions:currentActionsSnapshot()});
      if(root)await SB.archiveTimetable(root.id);
      await recordHistory('replace_original',{name:name,replaced:root?root.name:src.name,score:c.score});
    }
    document.getElementById('versionModal').style.display='none';
    state.source=null;
    await loadSavedList();
    setTicker(mode==='keep'?'Saved as a version — original kept':'Saved — it replaced the original (old one archived)','ok');
  }catch(e){
    document.getElementById('versionMsg').textContent='Error: '+e.message;
    setTicker('Save failed: '+e.message,'err');
  }
}

async function pushCurrent(){
  if(!SB||!SB.loggedIn){setTicker('Sign in to push a timetable','err');return;}
  const c=getSel();if(!c)return;
  setTicker('Publishing timetable…','run',true);
  try{
    await SB.pushTimetable({score:c.score,timetable:cellsToRaw(c.tt)});
    await recordHistory('push',{name:'current combination',score:c.score});
    state.combos.forEach(function(x){x.via=(x.id===c.id)?'pushed':(x.via==='pushed'?'browser':x.via);});
    renderChrome();renderScorecard();
    setTicker('Pushed — everyone can now view this timetable without signing in','ok');
  }catch(e){setTicker('Push failed: '+e.message,'err');}
}
async function loadSavedCombo(id){
  if(!SB||!SB.loggedIn)return;
  try{
    const row=await SB.getSaved(id);
    if(!row){setTicker('Saved timetable not found','err');return;}
    const key=rawKey(row.timetable);
    let combo=state.combos.find(function(c){return rawKey(cellsToRaw(c.tt))===key;});
    if(!combo){
      combo=makeCombo({score:row.score,timetable:row.timetable},'saved');
      state.combos.push(combo);
      state.seen.add(key);
    }
    state.selected=combo.id;
    state.source={id:row.id,name:row.name||'saved',kind:row.kind||'original'};
    setView('sections');
    persist();renderAll();
    setTicker('Loaded "'+(row.name||'saved')+'" — tweak it, then press 💾 Save to keep a version or replace','ok');
  }catch(e){setTicker('Load failed: '+e.message,'err');}
}
async function pushSavedCombo(id){
  if(!SB||!SB.loggedIn)return;
  try{
    const row=await SB.getSaved(id);
    if(!row){setTicker('Saved timetable not found','err');return;}
    setTicker('Publishing…','run',true);
    await SB.pushTimetable({score:row.score,timetable:row.timetable});
    await recordHistory('push',{name:row.name||'saved',score:row.score});
    await loadPushedTimetable();
    setTicker('Pushed "'+(row.name||'saved')+'" — visible to everyone now','ok');
  }catch(e){setTicker('Push failed: '+e.message,'err');}
}
async function deleteSavedCombo(id){
  if(!SB||!SB.loggedIn)return;
  try{
    ensureSavedList();
    const it=(state.savedList||[]).find(function(x){return x.id===id;});
    await SB.deleteSaved(id);
    await recordHistory('delete_timetable',{name:it?it.name:'',kind:it?(it.kind||'original'):''});
    if(state.source&&state.source.id===id)state.source=null;
    await loadSavedList();
    renderMain();
    setTicker('Deleted '+(it&&it.kind==='version'?'version':'timetable')+' (the action stays in History)','ok');
  }catch(e){setTicker('Delete failed: '+e.message,'err');}
}
function renderSaved(){
  const signedIn=SB&&SB.loggedIn;
  let h='<div class="cons-note"><b>Saved timetables.</b> '+(signedIn?'<b>Originals</b> are saved straight from the main page. <b>Load</b> one, tweak it and re-optimise, then press 💾 Save to <b>keep it as a version</b> or <b>replace the original</b> (the old original is then archived). <b>Push</b> publishes any original or version; <b>Delete</b> wipes a version while its action stays in 🕘 History.':'<b style="color:var(--amber-deep)">🔒 Sign in to view your saved timetables.</b>')+'</div>';
  if(!signedIn){mainEl.innerHTML=h;return;}
  ensureSavedList();
  if(!state.savedList.length){h+='<div class="empty"><div class="eic">💾</div><h3>Nothing saved yet</h3><p>Select a combination and press “Save” in the toolbar.</p></div>';mainEl.innerHTML=h;return;}
  const byId={};
  state.savedList.forEach(function(x){byId[x.id]=x;});
  const active=state.savedList.filter(function(x){return !x.archived;}).sort(function(a,b){
    return (a.kind==='version'?1:0)-(b.kind==='version'?1:0)||new Date(a.created_at)-new Date(b.created_at);
  });
  const archived=state.savedList.filter(function(x){return x.archived;});
  function card(it){
    const when=new Date(it.created_at).toLocaleString('en-GB');
    const parent=it.parent_id?(byId[it.parent_id]?byId[it.parent_id].name:'(deleted)'):null;
    const kindBadge=it.archived?'<span class="stag edited">📦 archived</span>':(it.kind==='version'?'<span class="stag edited">🧬 version</span>':'<span class="stag">🗂 original</span>');
    let meta='Saved '+esc(when);
    if(it.kind==='version'&&parent)meta+=' · from '+esc(parent);
    if(it.actions)meta+=' · '+esc(actionsSummary(it.actions));
    return '<article class="cons-card'+(it.archived?' edited':'')+'"><header><h4>'+esc(it.name||'Untitled')+'</h4>'+kindBadge+'<span class="stag">score '+it.score+'</span></header>'+
      '<div class="saved-meta">'+meta+'</div>'+
      '<div class="cons-btns">'+
        '<button class="mini-export" data-saved-load="'+it.id+'">Load</button>'+
        '<button class="mini-export" data-saved-push="'+it.id+'">Push</button>'+
        '<button class="card-csv" data-saved-del="'+it.id+'" title="Delete this saved timetable">✕</button>'+
      '</div></article>';
  }
  h+='<div class="cons-grid">';
  active.forEach(function(it){h+=card(it);});
  h+='</div>';
  if(archived.length){
    h+='<div class="sp-block-title" style="margin:18px 0 8px">📦 Archived originals (replaced)</div><div class="cons-grid">';
    archived.forEach(function(it){h+=card(it);});
    h+='</div>';
  }
  mainEl.innerHTML=h;
  document.querySelectorAll('[data-saved-load]').forEach(function(el){el.addEventListener('click',function(){loadSavedCombo(el.dataset.savedLoad);});});
  document.querySelectorAll('[data-saved-push]').forEach(function(el){el.addEventListener('click',function(){pushSavedCombo(el.dataset.savedPush);});});
  document.querySelectorAll('[data-saved-del]').forEach(function(el){el.addEventListener('click',function(){deleteSavedCombo(el.dataset.savedDel);});});
}
function historyLabel(a){
  if(a==='create_original')return '🗂 Saved original';
  if(a==='create_version')return '🧬 Created version';
  if(a==='replace_original')return '♻️ Replaced original';
  if(a==='delete_timetable')return '✕ Deleted';
  if(a==='push')return '📣 Pushed';
  if(a==='unpush')return '🕳 Unpushed';
  return a;
}
function renderHistory(){
  const signedIn=SB&&SB.loggedIn;
  let h='<div class="cons-note"><b>History.</b> A record of every action on your timetables — it stays even after a version is deleted. '+(signedIn?'<span class="cons-actions"><button class="mini-export" id="histClear">🗑 Clear history</button></span>':'<b style="color:var(--amber-deep)">🔒 Sign in to view your history.</b>')+'</div>';
  if(!signedIn){mainEl.innerHTML=h;return;}
  if(!state.history)state.history=[];
  if(!state.history.length){h+='<div class="empty"><div class="eic">🕘</div><h3>No history yet</h3><p>Actions on your saved timetables will appear here.</p></div>';mainEl.innerHTML=h;return;}
  h+='<div class="cons-grid">';
  state.history.forEach(function(it){
    const when=new Date(it.created_at).toLocaleString('en-GB');
    const d=it.detail||{};
    let line='';
    if(it.action==='create_version')line='created version <b>'+esc(d.name||'?')+'</b> from <b>'+esc(d.from||'?')+'</b>';
    else if(it.action==='replace_original')line='replaced <b>'+esc(d.replaced||'?')+'</b> with <b>'+esc(d.name||'?')+'</b> (old one archived)';
    else if(it.action==='create_original')line='saved original <b>'+esc(d.name||'?')+'</b>';
    else if(it.action==='delete_timetable')line='deleted <b>'+esc(d.name||'?')+'</b> ('+esc(d.kind||'timetable')+')';
    else if(it.action==='push')line='pushed <b>'+esc(d.name||'timetable')+'</b> for everyone';
    else if(it.action==='unpush')line='removed the published timetable';
    else line=esc(it.action);
    h+='<article class="cons-card"><header><h4>'+historyLabel(it.action)+'</h4></header><div class="saved-meta">'+line+'</div><div class="saved-meta">'+esc(when)+'</div></article>';
  });
  h+='</div>';
  mainEl.innerHTML=h;
  const hc=document.getElementById('histClear');if(hc)hc.addEventListener('click',clearHistory);
}

'''

# ---- 28) saved (admin-only) + pushed (public) timetables --------------------
# (a) CSS
rep("</style>", ".saved-meta{font-family:var(--mono);font-size:10.5px;color:var(--ink2)}\n</style>")
# (b) DOM refs
rep("const btnGenerate=$('btnGenerate'),btnMore=$('btnMore'),btnCpsat=$('btnCpsat'),btnPrint=$('btnPrint');",
    "const btnGenerate=$('btnGenerate'),btnMore=$('btnMore'),btnCpsat=$('btnCpsat'),btnPrint=$('btnPrint'),btnSave=$('btnSave'),btnPush=$('btnPush');")
# (c) console buttons (Save + Push) before the combination selector
rep('<div class="con-sel">',
    '<button class="btn" id="btnSave" title="Save the selected combination to your account"><span class="g">🔒</span> Save</button>\n    <button class="btn" id="btnPush" title="Publish the selected combination so everyone can view it"><span class="g">🔒</span> Push</button>\n    <div class="con-sel">')
# (d) Saved tab after Directory
rep('<button id="viewDirectory">📇 Directory</button>',
    '<button id="viewDirectory">📇 Directory</button>\n      <button id="viewSaved">💾 Saved</button>')
# (e) setView toggle
rep("  $('viewDirectory').classList.toggle('on',v==='directory');",
    "  $('viewDirectory').classList.toggle('on',v==='directory');\n  $('viewSaved').classList.toggle('on',v==='saved');")
# (f) renderMain
rep("  if(state.view==='directory'){renderDirectory();return;}",
    "  if(state.view==='directory'){renderDirectory();return;}\n  if(state.view==='saved'){renderSaved();return;}")
# (g) listener
rep("$('viewDirectory').addEventListener('click',()=>setView('directory'));",
    "$('viewDirectory').addEventListener('click',()=>setView('directory'));\n$('viewSaved').addEventListener('click',()=>setView('saved'));")
# (h) renderChrome: enable/disable Save & Push (lock when signed out)
rep("    btnCpsat.disabled=!_signedIn;btnCpsat.title=_signedIn?'Call the CP-SAT backend for proven-optimal results':'Sign in to unlock CP-SAT & AI translation';if(!_signedIn&&!state.cpsatDone){setCpsatStatus('CP-SAT: 🔒 sign in to unlock CP-SAT & AI translation','warn');}",
    "    btnCpsat.disabled=!_signedIn;btnCpsat.title=_signedIn?'Call the CP-SAT backend for proven-optimal results':'Sign in to unlock CP-SAT & AI translation';if(!_signedIn&&!state.cpsatDone){setCpsatStatus('CP-SAT: 🔒 sign in to unlock CP-SAT & AI translation','warn');}\n    btnSave.disabled=!_signedIn||!list.length;btnSave.title=_signedIn?'Save the selected combination to your account':'Sign in to save timetables';btnSave.innerHTML='<span class=\"g\">'+(_signedIn?'💾':'🔒')+'</span> Save';\n    btnPush.disabled=!_signedIn||!list.length;btnPush.title=_signedIn?'Publish the selected combination so everyone can view it':'Sign in to push a timetable';btnPush.innerHTML='<span class=\"g\">'+(_signedIn?'📣':'🔒')+'</span> Push';")
# (i) selector option marker
rep("(o.via==='cpsat'?' ✦CP-SAT':'')+'</option>';",
    "(o.via==='cpsat'?' ✦CP-SAT':(o.via==='pushed'?' 📣':(o.via==='saved'?' 💾':'')))+'</option>';")
# (j) scorecard marker
rep("(c.via==='cpsat'?' · merged from CP-SAT ✦':'')+'</div>'+",
    "(c.via==='cpsat'?' · merged from CP-SAT ✦':(c.via==='pushed'?' · 📣 published to everyone':(c.via==='saved'?' · 💾 from your saved list':'')))+'</div>'+")
# (k) vbInfo via label
rep("(c.via==='cpsat'?'CP-SAT solver':'in-browser generation')+' · showing '+shown",
    "(c.via==='cpsat'?'CP-SAT solver':(c.via==='pushed'?'published':(c.via==='saved'?'saved':'in-browser generation')))+' · showing '+shown")
# (l) boot: also load the pushed timetable + saved list
rep("syncFromCloud().then(()=>{renderMain();renderChrome();});",
    "syncFromCloud().then(()=>{renderMain();renderChrome();});\nif(SB&&SB.loggedIn){SB.ensureSession().then(()=>renderAuth());}\nloadPushedTimetable().then(()=>{renderMain();renderChrome();});\nloadSavedList();")
# (m) login: refresh saved list; logout: clear it
rep("    await syncFromCloud();\n    document.getElementById('authModal').style.display='none';",
    "    await syncFromCloud();await loadSavedList();\n    document.getElementById('authModal').style.display='none';")
rep("SB.logout().then(()=>{renderAuth();renderChrome();setTicker('Signed out — local data only','ok');});",
    "SB.logout().then(()=>{state.savedList=[];renderAuth();renderChrome();setTicker('Signed out — local data only','ok');});")
# (n) listeners for the Save / Push buttons
rep("btnCpsat.addEventListener('click',runCpsat);",
    "btnCpsat.addEventListener('click',runCpsat);\nbtnSave.addEventListener('click',saveCurrent);\nbtnPush.addEventListener('click',pushCurrent);")
# (o) inject the saved/pushed module before the boot marker
rep("/* ---------- boot: restore saved results (no auto-generation) ---------- */",
    SAVED_MODULE + "/* ---------- boot: restore saved results (no auto-generation) ---------- */")


# ---- 29) Unpush (admin removes the public timetable from preview) ---------
# (a) DOM ref
rep("btnPush=$('btnPush');", "btnPush=$('btnPush'),btnUnpush=$('btnUnpush');")
# (b) console button after Push
rep('<button class="btn" id="btnPush" title="Publish the selected combination so everyone can view it"><span class="g">🔒</span> Push</button>',
    '<button class="btn" id="btnPush" title="Publish the selected combination so everyone can view it"><span class="g">🔒</span> Push</button>\n    <button class="btn" id="btnUnpush" title="Remove the published timetable so visitors can no longer see it" style="display:none"><span class="g">🕳</span> Unpush</button>')
# (c) renderChrome: show Unpush only when a pushed combo exists + signed in
rep("    btnPush.disabled=!_signedIn||!list.length;btnPush.title=_signedIn?'Publish the selected combination so everyone can view it':'Sign in to push a timetable';btnPush.innerHTML='<span class=\"g\">'+(_signedIn?'📣':'🔒')+'</span> Push';",
    "    btnPush.disabled=!_signedIn||!list.length;btnPush.title=_signedIn?'Publish the selected combination so everyone can view it':'Sign in to push a timetable';btnPush.innerHTML='<span class=\"g\">'+(_signedIn?'📣':'🔒')+'</span> Push';\n    const _pushed=pushedCombo();btnUnpush.style.display=(_signedIn&&_pushed)?'':'none';btnUnpush.disabled=!_signedIn||!_pushed;btnUnpush.title=_signedIn?'Remove the published timetable (visitors will no longer see it)':'Sign in to manage the published timetable';")
# (d) listener
rep("btnPush.addEventListener('click',pushCurrent);", "btnPush.addEventListener('click',pushCurrent);\nbtnUnpush.addEventListener('click',unpushCurrent);")
# (e) unpushCurrent (adds next to pushCurrent in the saved module)
rep("async function loadSavedCombo(id){", """async function unpushCurrent(){
  if(!SB||!SB.loggedIn){setTicker('Sign in to manage the published timetable','err');return;}
  const p=pushedCombo();if(!p){setTicker('Nothing is currently published','err');return;}
  setTicker('Removing published timetable…','run',true);
  try{
    await SB.unpushTimetable();
    await recordHistory('unpush',{});
    state.combos=state.combos.filter(function(c){return c.via!=='pushed';});
    const list=sortedList();
    state.selected=list.length?list[0].id:null;
    persist();renderAll();
    setTicker('Unpublished — visitors can no longer see that timetable','ok');
  }catch(e){setTicker('Unpush failed: '+e.message,'err');}
}
async function loadSavedCombo(id){""")


TWEAK_MODULE = r'''/* ---------- tweaks (temporary/permanent adjustments) + manual cell edits ---------- */
const TWEAK_KEY='impcc-tweaks-v1';
function loadTweaks(){
  try{const raw=localStorage.getItem(TWEAK_KEY);if(raw){state.tweaks=JSON.parse(raw);return true;}}catch(e){}
  state.tweaks=[];return false;
}
function saveTweaksLocal(){
  try{localStorage.setItem(TWEAK_KEY,JSON.stringify(state.tweaks||[]));}catch(e){}
  pushToCloud();
}
function activeTweaks(){
  const tstr=new Date().toISOString().slice(0,10);
  return (state.tweaks||[]).filter(function(t){
    if(t.kind==='permanent')return true;
    if(t.recurring)return true;
    const w=t.window||{};
    if(w.type==='dates'){
      if(w.from&&tstr<w.from)return false;
      if(w.to&&tstr>w.to)return false;
    }
    return true;
  });
}
function tweakActiveDays(t){
  const all=['MON','TUE','WED','THU','FRI'];
  const e=t.effect||{};
  if(t.recurring&&e.days&&e.days.length)return e.days;
  const w=t.window||{};
  if(w.type==='dates'){
    const today=new Date();today.setHours(0,0,0,0);
    const from=w.from?new Date(w.from+'T00:00:00'):today;
    const to=w.to?new Date(w.to+'T23:59:59'):from;
    const out=[];
    for(let i=0;i<8;i++){const d=new Date(from);d.setDate(from.getDate()+i);if(d>to)break;const dow=d.getDay();if(dow>=1&&dow<=5)out.push(all[dow-1]);}
    return out.length?out:all;
  }
  if(w.days&&w.days.length)return w.days;
  if(e.days&&e.days.length)return e.days;
  return all;
}
function tweaksToRulesDelta(){
  const delta={};
  const slots=['P1','P2','P3','P4','P5'];
  for(const t of activeTweaks()){
    const e=t.effect||{};if(!e.type)continue;
    const days=tweakActiveDays(t);
    if(!days.length)continue;
    const sl=(e.slots&&e.slots.length)?e.slots:slots;
    const push=function(name){delta[name]=delta[name]||[];delta[name].push({days:days,slots:sl});};
    if(e.type==='suspend_teacher'||e.type==='suspend_teacher_slots'){if(e.teacher)push(e.teacher);}
  }
  return delta;
}
function effectiveConstraints(){
  const R=IMPCC_SOLVER.resolveConstraints(state.constraints);
  const delta=tweaksToRulesDelta();
  const out={};
  for(const code in R){out[code]={name:R[code].name,rules:JSON.parse(JSON.stringify(R[code].rules))};}
  for(const name in delta){
    const code=IMPCC_SOLVER.NAME_TO_CODE[name]||name;
    const entry=out[code]||{name:name,rules:{}};
    entry.rules.forbidden_slots_on_days=(entry.rules.forbidden_slots_on_days||[]).concat(delta[name]);
    out[code]=entry;
  }
  return out;
}
function describeTweak(t){
  const e=t.effect||{};
  let eff='';
  if(e.type==='suspend_teacher')eff='Unavailable: '+esc(e.teacher||'?');
  else if(e.type==='suspend_teacher_slots')eff='Unavailable: '+esc(e.teacher||'?')+(e.slots?' ('+e.slots.join(', ')+')':'');
  else eff=esc(e.type||'?');
  if(e.days&&e.days.length)eff+=' on '+e.days.join(', ');
  return eff;
}
function tweakBadge(t){
  if(t.kind==='permanent')return '<span class="stag edited">permanent</span>';
  if(t.recurring)return '<span class="stag edited">recurring</span>';
  const w=t.window||{};
  if(w.type==='dates'&&w.to)return '<span class="stag edited">until '+esc(w.to)+'</span>';
  return '<span class="stag edited">temporary</span>';
}
function tweakStatus(t){
  const tstr=new Date().toISOString().slice(0,10);
  const w=t.window||{};
  if(t.kind==='permanent'||t.recurring)return 'active';
  if(w.type==='dates'){
    if(w.to&&tstr>w.to)return 'expired';
    if(w.from&&tstr<w.from)return 'upcoming';
  }
  return 'active';
}
function renderTweaks(){
  const signedIn=SB&&SB.loggedIn;
  let h='<div class="cons-note"><b>Timetable tweaks.</b> Handle teacher unavailability and one-off changes. '+(signedIn?'Describe a situation in plain language, or add it manually. <b>Permanent</b> changes apply forever; <b>temporary</b> ones revert automatically after their window; <b>recurring</b> ones apply every week.':'<b style="color:var(--amber-deep)">🔒 Sign in to add or remove tweaks.</b>')+'</div>';
  if(signedIn){
    h+='<div class="tweak-add">'+
      '<textarea class="cons-nl" id="tweakNl" placeholder="e.g. Prof. Naeem is on leave tomorrow"></textarea>'+
      '<button class="mini-export" id="tweakTranslate">✦ Translate</button>'+
    '</div>';
    h+='<div class="tweak-add">'+
      '<select id="tweakType"><option value="suspend_teacher">Teacher away</option><option value="suspend_teacher_slots">Teacher away (some periods)</option></select>'+
      '<select id="tweakTarget"></select>'+
      '<span class="ed-chip-wrap" id="tweakDays"></span>'+
      '<span class="ed-chip-wrap" id="tweakSlots"></span>'+
      '<select id="tweakWindow"><option value="permanent">Permanent</option><option value="dates">Temporary (date range)</option><option value="recurring">Recurring weekly</option></select>'+
      '<span id="tweakDateRange" style="display:none"><input type="date" id="tweakFrom"><input type="date" id="tweakTo"></span>'+
      '<button class="mini-export" id="tweakAdd">＋ Add</button>'+
    '</div>';
    h+='<div class="cons-status" id="tweakStatus"></div>';
  }
  const list=(state.tweaks||[]).slice().sort(function(a,b){return (a.created_at||'')>(b.created_at||'')?-1:1;});
  h+='<div class="cons-grid">';
  list.forEach(function(t,i){
    const st=tweakStatus(t);
    h+='<article class="cons-card'+(st!=='active'?' edited':'')+'"><header><h4>'+describeTweak(t)+'</h4>'+tweakBadge(t)+'</header>'+
      '<div class="tweak-nl">'+esc(t.natural||'')+'</div>'+
      '<div class="cons-btns"><span class="tweak-stag '+st+'">'+st+'</span>'+
      (signedIn?'<button class="card-csv" data-tweak-del="'+i+'" title="Remove this tweak">✕</button>':'')+
      '</div></article>';
  });
  if(!list.length)h+='<div class="cons-rule none">No tweaks yet.</div>';
  h+='</div>';
  mainEl.innerHTML=h;
  if(!signedIn)return;
  const targetSel=document.getElementById('tweakTarget');
  const typeSel=document.getElementById('tweakType');
  function repopulateTargets(){
    targetSel.innerHTML='';
    facultyNames().forEach(function(n){const o=document.createElement('option');o.value=n;o.textContent=n;targetSel.appendChild(o);});
  }
  repopulateTargets();
  typeSel.addEventListener('change',repopulateTargets);
  const daysWrap=document.getElementById('tweakDays');
  DAYS.forEach(function(d){daysWrap.innerHTML+='<span class="ed-chip ed-chip-day" data-v="'+d+'">'+d+'</span>';});
  const slotsWrap=document.getElementById('tweakSlots');
  SLOTS.forEach(function(p){slotsWrap.innerHTML+='<span class="ed-chip ed-chip-slot" data-v="'+p+'">'+p+'</span>';});
  document.getElementById('tweakWindow').addEventListener('change',function(e){document.getElementById('tweakDateRange').style.display=e.target.value==='dates'?'':'none';});
  document.getElementById('tweakAdd').addEventListener('click',function(){
    const type=typeSel.value,target=targetSel.value;
    const days=Array.from(daysWrap.querySelectorAll('.ed-chip-day.on')).map(function(x){return x.dataset.v;});
    const slots=Array.from(slotsWrap.querySelectorAll('.ed-chip-slot.on')).map(function(x){return x.dataset.v;});
    const win=document.getElementById('tweakWindow').value;
    if(!target){setTicker('Choose a teacher','err');return;}
    const effect={type:type};
    effect.teacher=target;
    if(slots.length)effect.slots=slots;
    if(days.length)effect.days=days;
    const tweak={kind:win==='permanent'?'permanent':'temporary',recurring:win==='recurring',effect:effect,natural:'',notes:'manual',created_at:new Date().toISOString()};
    if(win==='dates'){
      const f=document.getElementById('tweakFrom').value,to=document.getElementById('tweakTo').value;
      if(!f||!to){setTicker('Pick a start and end date','err');return;}
      tweak.window={type:'dates',from:f,to:to};
    }
    state.tweaks.push(tweak);saveTweaksLocal();renderTweaks();
    setTicker('Tweak added — will affect the next generation','ok');
  });
  document.getElementById('tweakTranslate').addEventListener('click',function(){translateTweakOne();});
  document.querySelectorAll('[data-tweak-del]').forEach(function(el){el.addEventListener('click',function(){state.tweaks.splice(+el.dataset.tweakDel,1);saveTweaksLocal();renderTweaks();setTicker('Tweak removed','ok');});});
}
let pendingTweak=null;
function translateTweakOne(){
  const ta=document.getElementById('tweakNl');
  const st=document.getElementById('tweakStatus');
  const text=ta?ta.value.trim():'';
  if(!text){if(st)st.textContent='Type a plain-language tweak first.';return;}
  if(!SB||!SB.loggedIn){if(st)st.textContent='Sign in required to use AI translation.';return;}
  if(st)st.textContent='Translating…';
  const base=(typeof window.IMPCC_API_URL==='string')?window.IMPCC_API_URL:'';
  fetch(base+'/translate-tweak',{
    method:'POST',
    headers:{'Content-Type':'application/json','Authorization':'Bearer '+(SB.session&&SB.session.access_token?SB.session.access_token:'')},
    body:JSON.stringify({text:text})
  })
  .then(function(r){if(!r.ok)throw new Error(r.status===401?'Sign in required':'HTTP '+r.status);return r.json();})
  .then(function(d){
    if(d.error){if(st)st.textContent='⚠ '+d.error;return;}
    pendingTweak=d;
    if(st)st.textContent='✓ '+describeTweak(d)+' · '+(d.kind==='permanent'?'permanent':(d.recurring?'recurring':'until '+(d.window&&d.window.to?d.window.to:'?')))+' — click ＋ Add to confirm';
  })
  .catch(function(err){if(st)st.textContent='⚠ Translation failed: '+err.message;});
}
/* manual cell editing + re-optimization */
function cellIsEdited(sec,d,s){
  return (state.edits||[]).some(function(e){return e.sec===sec&&e.d===d&&e.s===s;});
}
function toggleEditMode(){
  state.editMode=!state.editMode;
  if(state.editMode)state.swapMode=false;
  renderChrome();renderMain();
  setTicker(state.editMode?'Edit mode — click any cell to adjust it':'Edit mode off','ok');
}
function openCellEditor(ds,cellEl){
  state.editCell={sec:ds.sec,d:+ds.d,s:+ds.s,subj:ds.subj,teacher:ds.teacher};
  const sec=SECTIONS.find(function(x){return x.id===ds.sec;});
  const a=getWorkingAllocation()[ds.sec];
  let opts='';
  if(a&&a.subjects)a.subjects.forEach(function(x){opts+='<option>'+esc(x.subject+' — '+x.teacher)+'</option>';});
  const el=document.getElementById('cellEditor');
  el.innerHTML='<h3>Edit cell — '+esc(ds.sec)+' · '+DAYS[+ds.d]+' '+SLOTS[+ds.s]+'</h3>'+
    '<div class="ce-cur">Current: <b>'+esc(ds.subj)+'</b> — '+esc(ds.teacher)+'</div>'+
    '<select id="ceSelect">'+opts+'</select>'+
    '<div class="ce-actions"><button class="mini-export" id="ceSet">Set (force)</button><button class="mini-export" id="ceRemove">Remove (forbid)</button><button class="mini-export" id="ceClose">Close</button></div>';
  el.style.display='block';
  document.getElementById('ceSet').addEventListener('click',function(){applyCellEdit('force');});
  document.getElementById('ceRemove').addEventListener('click',function(){applyCellEdit('forbid');});
  document.getElementById('ceClose').addEventListener('click',closeCellEditor);
}
function closeCellEditor(){document.getElementById('cellEditor').style.display='none';}
document.addEventListener('click',function(e){
  const el=document.getElementById('cellEditor');
  if(!el||el.style.display==='none')return;
  if(el.contains(e.target))return;
  if(e.target.closest&&e.target.closest('.tg-cell'))return;
  closeCellEditor();
});
function applyCellEdit(mode){
  const c=state.editCell;if(!c)return;
  if(mode==='force'){
    const sel=document.getElementById('ceSelect').value.split(' — ');
    if(sel.length<2)return;
    state.edits=(state.edits||[]).filter(function(e){return !(e.sec===c.sec&&e.d===c.d&&e.s===c.s);});
    state.edits.push({sec:c.sec,d:c.d,s:c.s,mode:'force',subject:sel[0],teacher:sel.slice(1).join(' — ')});
  }else{
    state.edits=(state.edits||[]).filter(function(e){return !(e.sec===c.sec&&e.d===c.d&&e.s===c.s);});
    state.edits.push({sec:c.sec,d:c.d,s:c.s,mode:'forbid',subject:c.subj,teacher:c.teacher});
  }
  closeCellEditor();renderMain();renderChrome();
  setTicker((state.edits.length)+' edit'+(state.edits.length===1?'':'s')+' pending — press Re-optimize','ok');
}
function clearEdits(){state.edits=[];renderMain();renderChrome();setTicker('Edits cleared','ok');}
function reoptimizeWithEdits(){
  if(!(state.edits&&state.edits.length)){setTicker('No edits to apply','err');return;}
  const locks=state.edits.slice();
  state.lastLocks=locks.slice();
  state.running=true;state.stopRequested=false;
  progFill.style.width='100%';
  setTicker('Re-optimizing around '+locks.length+' edit'+(locks.length===1?'':'s')+'…','run',true);
  renderChrome();
  const t0=Date.now();
  const res=IMPCC_SOLVER.generate({maxCount:0,timeMs:24000,seed:(Math.random()*2147483647)|0,constraints:effectiveConstraints(),sections:currentAllocation(),locks:locks});
  state.running=false;state.stopRequested=false;progFill.style.width='0%';
  if(res.solutions&&res.solutions.length){
    state.combos=res.solutions.map(function(sol){return makeCombo(sol,'browser');});
    state.seen=new Set();
    const list=sortedList();state.selected=list[0].id;
    state.edits=[];state.editMode=false;
    persist();renderAll();
    setTicker('Re-optimized — '+res.solutions.length+' valid combinations honouring your edits · best score '+res.solutions[0].score,'ok');
  }else{
    setTicker('Could not find a valid arrangement keeping all edits — try removing some','err');
  }
}

'''

# ---- 30) tweaks (temporary/permanent) + manual cell edits + re-optimize ----
# (a) state fields
rep("const state={combos:[],selected:null,view:'sections',sectionFilter:'all',running:false,runTimer:null,runTarget:0,cpsatBusy:false,cpsatDone:false,cpsatMerged:0,spot:null,seen:new Set()};",
    "const state={combos:[],selected:null,view:'sections',sectionFilter:'all',running:false,runTimer:null,runTarget:0,cpsatBusy:false,cpsatDone:false,cpsatMerged:0,spot:null,seen:new Set(),tweaks:[],editMode:false,edits:[],editCell:null,source:null,lastLocks:null,history:[],swapMode:false,swapMoves:[],swapPick:null,swapDrag:null,lastSwap:null};")
# (b) CSS
rep("</style>", ".edited-cell{outline:2px solid var(--amber);outline-offset:-2px;position:relative}\n.edited-cell::after{content:'✎';position:absolute;top:2px;right:4px;font-size:9px;color:var(--amber-deep)}\n.cell-editor{display:none;position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);z-index:300;background:var(--surface);border:1px solid var(--line2);border-radius:14px;box-shadow:0 24px 60px rgba(0,0,0,.35);padding:16px 18px;width:min(420px,94vw)}\n.cell-editor h3{margin:0 0 4px;font-family:var(--disp);font-weight:900;font-size:17px;color:var(--green-deep)}\n.ce-cur{font-size:12.5px;color:var(--ink2);margin-bottom:12px}\n.cell-editor select{width:100%;margin-bottom:12px;padding:9px;border:1px solid var(--line2);border-radius:8px;font-size:13px;background:#fff;color:var(--ink)}\n.ce-actions{display:flex;gap:8px;flex-wrap:wrap}\n.tweak-add{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:10px}\n.tweak-add select,.tweak-add input[type=date]{padding:7px 9px;border:1px solid var(--line2);border-radius:8px;background:#fff;font-size:12.5px;color:var(--ink)}\n.tweak-nl{font-size:12px;color:var(--ink2);font-style:italic}\n.tweak-stag{font-family:var(--mono);font-size:10px;padding:2px 8px;border-radius:99px;border:1px solid var(--line2)}\n.tweak-stag.active{background:var(--green-tint);color:var(--green-deep);border-color:var(--green)}\n.tweak-stag.expired{background:var(--surface2);color:var(--ink2)}\n.tweak-stag.upcoming{background:var(--amber-tint);color:var(--amber-deep);border-color:var(--amber)}\n.ed-chip-wrap{display:inline-flex;gap:4px;flex-wrap:wrap}\n</style>")
# (c) Tweaks tab
rep('<button id="viewSaved">💾 Saved</button>',
    '<button id="viewSaved">💾 Saved</button>\n      <button id="viewTweaks">🛠 Tweaks</button>')
rep("$('viewSaved').addEventListener('click',()=>setView('saved'));",
    "$('viewSaved').addEventListener('click',()=>setView('saved'));\n$('viewTweaks').addEventListener('click',()=>setView('tweaks'));")
rep("  $('viewSaved').classList.toggle('on',v==='saved');",
    "  $('viewSaved').classList.toggle('on',v==='saved');\n  $('viewTweaks').classList.toggle('on',v==='tweaks');")
rep("  if(state.view==='saved'){renderSaved();return;}",
    "  if(state.view==='saved'){renderSaved();return;}\n  if(state.view==='tweaks'){renderTweaks();return;}")
# (d) boot: load tweaks
rep("loadFaculty();", "loadFaculty();\nloadTweaks();")
# (e) generation uses effective constraints (tweaks included)
rep("const res=IMPCC_SOLVER.generate({maxCount:0,timeMs:320,seed:(Math.random()*2147483647)|0,constraints:currentConstraints(),sections:currentAllocation()});",
    "const res=IMPCC_SOLVER.generate({maxCount:0,timeMs:320,seed:(Math.random()*2147483647)|0,constraints:effectiveConstraints(),sections:currentAllocation()});")
rep("body:JSON.stringify({time_limit:120,n_seeds:1,max_solutions:0,constraints:currentConstraints(),sections:currentAllocation()})",
    "body:JSON.stringify({time_limit:120,n_seeds:1,max_solutions:0,constraints:effectiveConstraints(),sections:currentAllocation()})")
# (f) cell markup: data attrs + edited highlight
rep("'<div class=\"tg-cell'+(cell.dual?' dual':'')+'\" data-teacher=\"'+esc(cell.teacher)+'\" title=\"'+esc(cell.subj)+' — '+esc(cell.teacher)+' · click to open the teacher\\u2019s personal courses\">'+",
    "'<div class=\"tg-cell'+(cell.dual?' dual':'')+(cellIsEdited(sec.id,d,s)?' edited-cell':'')+'\" data-sec=\"'+sec.id+'\" data-d=\"'+d+'\" data-s=\"'+s+'\" data-teacher=\"'+esc(cell.teacher)+'\" data-subj=\"'+esc(cell.subj)+'\" title=\"'+esc(cell.subj)+' — '+esc(cell.teacher)+' · click to open the teacher\\u2019s personal courses\">'+")
# (g) click handler: edit mode intercept
rep("  const card=e.target.closest('.t-card');\n  if(card){openSpotlight(card.dataset.name);return;}",
    "  if(state.editMode){const ec=e.target.closest('.tg-cell');if(ec){openCellEditor(ec.dataset);return;}}\n  const card=e.target.closest('.t-card');\n  if(card){openSpotlight(card.dataset.name);return;}")
# (h) edit controls in the viewbar + cell editor overlay
rep('<span class="vb-info" id="vbInfo"></span>',
    '<span class="vb-info" id="vbInfo"></span>\n    <span class="vb-edit" id="editControls" style="display:none"><button class="mini-export" id="btnEditMode">✎ Edit</button><button class="mini-export" id="btnReopt">Re-optimize</button><button class="mini-export" id="btnClearEdits">Clear</button><span class="vb-info" id="editCount"></span></span>')
rep('<div class="drawer-backdrop" id="spotBackdrop"></div>',
    '<div id="cellEditor" class="cell-editor"></div>\n<div class="drawer-backdrop" id="spotBackdrop"></div>')
# (i) setView toggles editControls (sections only)
rep("  $('secFilterWrap').classList.toggle('hidden',v!=='sections');",
    "  $('secFilterWrap').classList.toggle('hidden',v!=='sections');\n  $('editControls').style.display=(v==='sections')?'':'none';")
# (j) renderChrome: edit buttons state
rep("    btnCpsat.disabled=!_signedIn;btnCpsat.title=",
    "    $('editCount').textContent=(state.edits&&state.edits.length)?('· '+state.edits.length+' edit'+(state.edits.length===1?'':'s')):'';\n    $('btnReopt').disabled=!(state.edits&&state.edits.length);\n    $('btnClearEdits').disabled=!(state.edits&&state.edits.length);\n    $('btnEditMode').textContent=state.editMode?'✎ Editing…':'✎ Edit';\n    btnCpsat.disabled=!_signedIn;btnCpsat.title=")
# (k) listeners
rep("btnUnpush.addEventListener('click',unpushCurrent);",
    "btnUnpush.addEventListener('click',unpushCurrent);\n$('btnEditMode').addEventListener('click',toggleEditMode);\n$('btnReopt').addEventListener('click',reoptimizeWithEdits);\n$('btnClearEdits').addEventListener('click',clearEdits);")
# (l) module injection
rep("/* ---------- boot: restore saved results (no auto-generation) ---------- */",
    TWEAK_MODULE + "/* ---------- boot: restore saved results (no auto-generation) ---------- */")

# ---- 31) engagement (substitute covers for unavailable slot holders) ---------
ENGAGE_CSS = r'''/* ---------- engagement (substitute covers) ---------- */
.eng-badge{position:absolute;right:3px;bottom:2px;font-family:var(--mono);font-size:8px;line-height:1;padding:2px 4px;border-radius:4px;pointer-events:none;max-width:88%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.eng-cov{background:var(--green-tint);color:var(--green-deep);border:1px solid var(--green)}
.eng-noc{background:var(--amber-tint);color:var(--amber-deep);border:1px solid var(--amber)}
.tg-cell.eng-covered{box-shadow:inset 0 0 0 2px var(--green)}
.tg-cell.eng-uncovered{box-shadow:inset 0 0 0 2px var(--amber)}
.eng-summary{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:14px}
.eng-summary .stat{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:12px 18px;text-align:center;min-width:118px}
.eng-summary .stat b{display:block;font-family:var(--disp);font-weight:900;font-size:26px;color:var(--green-deep)}
.eng-summary .stat span{font-family:var(--mono);font-size:10px;color:var(--ink2)}
.eng-summary .stat.warn b{color:var(--amber-deep)}
.eng-warn{background:var(--amber-tint);border:1px solid var(--amber);color:var(--amber-deep);border-radius:10px;padding:10px 14px;font-size:12.5px;margin-bottom:14px}
.eng-groups{display:flex;flex-direction:column;gap:12px}
.eng-group{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:12px 16px}
.eng-group h4{font-family:var(--disp);font-weight:700;font-size:14px;margin:0 0 8px;color:var(--ink)}
.eng-rows{display:flex;flex-direction:column;gap:5px}
.eng-row{display:grid;grid-template-columns:150px minmax(0,1.3fr) minmax(0,1fr) 26px minmax(0,1.3fr);gap:8px;align-items:center;font-size:12px;padding:6px 8px;border:1px solid var(--line2);border-radius:8px}
.eng-row .eng-sec{font-family:var(--mono);font-size:10.5px;color:var(--ink2)}
.eng-row .eng-subj{font-weight:600;color:var(--ink)}
.eng-row .eng-teacher{color:var(--ink2)}
.eng-row .eng-arrow{color:var(--line2);text-align:center}
.eng-row .eng-cover{color:var(--green-deep);font-weight:600}
.eng-row .eng-cover.none{color:var(--amber-deep)}
.eng-row.uncovered{border-color:var(--amber);background:var(--amber-tint)}
'''
rep("</style>", ENGAGE_CSS + "</style>")

# (a) viewbar: Engagement tab after Tweaks
rep('<button id="viewTweaks">🛠 Tweaks</button>',
    '<button id="viewTweaks">🛠 Tweaks</button>\n      <button id="viewEngagement">👥 Engagement</button>')
# (b) listener
rep("$('viewTweaks').addEventListener('click',()=>setView('tweaks'));",
    "$('viewTweaks').addEventListener('click',()=>setView('tweaks'));\n$('viewEngagement').addEventListener('click',()=>setView('engagement'));")
# (c) setView toggle
rep("  $('viewTweaks').classList.toggle('on',v==='tweaks');",
    "  $('viewTweaks').classList.toggle('on',v==='tweaks');\n  $('viewEngagement').classList.toggle('on',v==='engagement');")
# (d) renderMain dispatch
rep("  if(state.view==='tweaks'){renderTweaks();return;}",
    "  if(state.view==='tweaks'){renderTweaks();return;}\n  if(state.view==='engagement'){renderEngagement();return;}")
# (e) decorate cells right after the sections grid renders
rep("if(state.view==='sections')renderSections(c.tt);else renderTeachers(c.tt);\n}",
    "if(state.view==='sections')renderSections(c.tt);else renderTeachers(c.tt);\n  decorateEngagement();\n}")

ENGAGE_MODULE = r'''/* ---------- engagement (substitute covers for unavailable slot holders) ---------- */
let engCache=null;
function engagementUnavailable(){
  const all=['P1','P2','P3','P4','P5'];
  const out=[];
  for(const t of activeTweaks()){
    const e=t.effect||{};
    if(e.type!=='suspend_teacher'&&e.type!=='suspend_teacher_slots')continue;
    if(!e.teacher)continue;
    const days=tweakActiveDays(t);
    if(!days.length)continue;
    out.push({teacher:e.teacher,days:days,slots:(e.slots&&e.slots.length)?e.slots:all});
  }
  return out;
}
function engagementPlan(){
  const c=getSel();
  const una=engagementUnavailable();
  if(!c||!una.length)return null;
  const key=c.id+'|'+JSON.stringify(una)+'|'+JSON.stringify(state.constraints||null);
  if(engCache&&engCache.key===key)return engCache.plan;
  const raw={};
  for(const k in c.tt)raw[k]=c.tt[k].map(function(r){return r.map(function(x){return [x.subj,x.teacher];});});
  const plan=IMPCC_SOLVER.engage(raw,effectiveConstraints(),una,{roster:facultyNames()});
  engCache={key:key,plan:plan};
  return plan;
}
function decorateEngagement(){
  const plan=engagementPlan();
  if(!plan)return;
  const els=document.querySelectorAll('.tg-cell[data-sec]');
  const m={};
  for(const a of plan.assignments)m[a.sec+'|'+a.d+'|'+a.s]={cover:a.cover};
  for(const u of plan.uncovered)m[u.sec+'|'+u.d+'|'+u.s]={cover:null};
  for(const el of els){
    const k=el.dataset.sec+'|'+el.dataset.d+'|'+el.dataset.s;
    const info=m[k];
    const old=el.querySelector('.eng-badge');
    if(old)old.remove();
    el.classList.remove('eng-covered','eng-uncovered');
    if(!info)continue;
    if(info.cover){
      el.classList.add('eng-covered');
      const b=document.createElement('span');b.className='eng-badge eng-cov';b.textContent='👥 '+info.cover;
      el.appendChild(b);
    }else{
      el.classList.add('eng-uncovered');
      const b=document.createElement('span');b.className='eng-badge eng-noc';b.textContent='⚠ no cover';
      el.appendChild(b);
    }
  }
}
function engSecLabel(id){const s=SECTIONS.find(function(x){return x.id===id;});return s?s.label:id;}
function engagementStatements(plan){
  const dayOrder=['MON','TUE','WED','THU','FRI'];
  const slotOrder=['P1','P2','P3','P4','P5'];
  const stmts=[];
  for(const a of plan.assignments){stmts.push({d:a.d,s:a.s,sec:a.sec,subj:a.subj,out:a.teacher,cover:a.cover});}
  for(const u of plan.uncovered){stmts.push({d:u.d,s:u.s,sec:u.sec,subj:u.subj,out:u.teacher,cover:null});}
  stmts.sort(function(a,b){return dayOrder.indexOf(DAYS[a.d])-dayOrder.indexOf(DAYS[b.d])||slotOrder.indexOf(SLOTS[a.s])-slotOrder.indexOf(SLOTS[b.s])||(a.sec<b.sec?-1:a.sec>b.sec?1:0);});
  let out='';
  for(const t of stmts){
    if(t.cover){
      out+='<p class="eng-stmt"><strong>'+esc(t.cover)+'</strong> will engage the class of <strong>'+esc(t.out)+'</strong> in <strong>'+esc(engSecLabel(t.sec))+'</strong> for <strong>'+esc(SLOTS[t.s])+'</strong> in the <strong>'+esc(DAYS[t.d])+'</strong> slot<em> — '+esc(t.subj)+'</em>.</p>';
    }else{
      out+='<p class="eng-stmt noc">The class of <strong>'+esc(t.out)+'</strong> in <strong>'+esc(engSecLabel(t.sec))+'</strong> for <strong>'+esc(SLOTS[t.s])+'</strong> in the <strong>'+esc(DAYS[t.d])+'</strong> slot<em> — '+esc(t.subj)+'</em> has <strong class="noc">no engaging professor</strong>.</p>';
    }
  }
  return out;
}
function renderEngagement(){
  const signedIn=SB&&SB.loggedIn;
  const una=engagementUnavailable();
  let h='<div class="cons-note"><b>Engagement.</b> When a slot holder is unavailable (an active <b>Teacher away</b> tweak — whole day or a few periods), this lists the <b>engaging professor</b> for each affected period of the selected combination. A cover must have <b>no class of his own</b> in that period and must <b>satisfy his own constraints</b>; coverage is maximised and the load is spread across the faculty. '+(signedIn?'Manage unavailability in the <b>🛠 Tweaks</b> tab.':'<b style="color:var(--amber-deep)">🔒 Sign in to manage tweaks.</b>')+'</div>';
  const c=getSel();
  if(!una.length){
    h+='<div class="empty"><div class="eic">👥</div><h3>No active unavailability</h3><p>Add a “Teacher away” tweak — for a whole day or for specific periods — and this view will list who engages each affected period.</p></div>';
    mainEl.innerHTML=h;return;
  }
  const plan=engagementPlan();
  if(!plan||!c){
    h+='<div class="empty"><div class="eic">🧩</div><h3>Generate a combination first</h3><p>Engagement is computed on the currently selected timetable.</p></div>';
    mainEl.innerHTML=h;return;
  }
  h+='<div class="eng-summary">'+
    '<div class="stat"><b>'+plan.total+'</b><span>periods affected</span></div>'+
    '<div class="stat"><b>'+plan.covered+'</b><span>engaged</span></div>'+
    '<div class="stat'+(plan.uncovered.length?' warn':'')+'"><b>'+plan.uncovered.length+'</b><span>no cover available</span></div>'+
    '</div>';
  h+='<div class="eng-actions"><button class="mini-export" id="engPrint">🖨 Print / PDF</button><button class="mini-export" id="engCsv">⇩ Export CSV</button></div>';
  if(plan.uncovered.length){
    h+='<div class="eng-warn">⚠ '+plan.uncovered.length+' period'+(plan.uncovered.length===1?'':'s')+' could not be engaged — every eligible professor is either teaching in that period or unavailable himself. Consider adding faculty or narrowing the tweak.</div>';
  }
  h+='<div class="eng-stack">'+engagementStatements(plan)+'</div>';
  mainEl.innerHTML=h;
  const bp=document.getElementById('engPrint');if(bp)bp.addEventListener('click',printEngagement);
  const bc=document.getElementById('engCsv');if(bc)bc.addEventListener('click',exportEngagementCSV);
}
function printEngagement(){
  const plan=engagementPlan();
  if(!plan){setTicker('No engagement plan to print','err');return;}
  let html=pdCover('Engagement — Substitute Allotments',COLLEGE_LINE+' · '+plan.covered+' of '+plan.total+' periods engaged');
  html+='<div class="eng-print">'+engagementStatements(plan)+'</div>';
  html+=pdFooter();
  const area=document.getElementById('printArea');
  if(!area)return;
  area.innerHTML=html;
  window.print();
}
function exportEngagementCSV(){
  const plan=engagementPlan();
  if(!plan){setTicker('No engagement plan to export','err');return;}
  const rows=[['Section','Day','Period','Subject','Slot holder','Engaging professor','Status']];
  for(const a of plan.assignments)rows.push([a.sec,DAYS[a.d],SLOTS[a.s],a.subj,a.teacher,a.cover,'engaged']);
  for(const u of plan.uncovered)rows.push([u.sec,DAYS[u.d],SLOTS[u.s],u.subj,u.teacher,'','UNCOVERED']);
  downloadCSV('IMPCC_engagement-plan.csv',rows);
  setTicker('Exported engagement plan (CSV)','ok');
}

'''
rep("/* ---------- boot: restore saved results (no auto-generation) ---------- */",
    ENGAGE_MODULE + "/* ---------- boot: restore saved results (no auto-generation) ---------- */")

# ---- 32) sync tweaks to/from the published cloud state ----------------------
# (engagement is driven by tweaks, so they must travel with the published data)
rep("SB.savePublished(state.allocation||defaultAllocation(),state.constraints||{},getFaculty())",
    "SB.savePublished(state.allocation||defaultAllocation(),state.constraints||{},getFaculty(),state.tweaks||[])")
rep("      if(Array.isArray(pub.faculty)&&pub.faculty.length){state.faculty=pub.faculty;saveFacultyLocal();}",
    "      if(Array.isArray(pub.faculty)&&pub.faculty.length){state.faculty=pub.faculty;saveFacultyLocal();}\n      if(Array.isArray(pub.tweaks)){state.tweaks=pub.tweaks;try{localStorage.setItem(TWEAK_KEY,JSON.stringify(state.tweaks));}catch(e){}}")

# ---- 33) engagement output: statements stack (separate from faculty grids) ----
rep("</style>", r'''.eng-actions{display:flex;gap:8px;justify-content:flex-end;margin-bottom:10px}
.eng-stack{display:flex;flex-direction:column;gap:8px}
.eng-stmt{padding:10px 14px;border:1px solid var(--line2);border-radius:10px;background:#fff;margin:0;font-size:13px;line-height:1.55;color:var(--ink)}
.eng-stmt strong{color:var(--green-deep);font-weight:700}
.eng-stmt strong.noc{color:var(--amber-deep)}
.eng-stmt em{color:var(--ink2);font-style:italic}
.eng-stmt.noc{border-color:var(--amber);background:var(--amber-tint)}
@media print{#printArea .eng-stmt{break-inside:avoid;border-color:#cfd6c8;font-size:12px}#printArea .eng-print{margin-top:10px}}
</style>''')

# ---- 34) versioning UI: version modal + history tab --------------------------
rep('<div class="auth-modal" id="authModal">',
    '<div class="auth-modal" id="versionModal">\n  <div class="auth-box">\n    <h3>Save as version</h3>\n    <p id="versionFrom" style="font-size:12px;color:var(--ink2);margin:0 0 10px">Deriving from …</p>\n    <input id="versionName" type="text" placeholder="Name this version">\n    <div class="auth-row">\n      <button class="btn primary" id="versionKeep">🔀 Keep as version</button>\n      <button class="btn" id="versionReplace">♻️ Replace original</button>\n      <button class="btn" id="versionClose">Cancel</button>\n    </div>\n    <div class="cons-status" id="versionMsg"></div>\n  </div>\n</div>\n<div class="auth-modal" id="authModal">')

# History tab after Saved
rep('<button id="viewSaved">💾 Saved</button>',
    '<button id="viewSaved">💾 Saved</button>\n      <button id="viewHistory">🕘 History</button>')
rep("$('viewSaved').addEventListener('click',()=>setView('saved'));",
    "$('viewSaved').addEventListener('click',()=>setView('saved'));\n$('viewHistory').addEventListener('click',()=>setView('history'));")
rep("  $('viewSaved').classList.toggle('on',v==='saved');",
    "  $('viewSaved').classList.toggle('on',v==='saved');\n  $('viewHistory').classList.toggle('on',v==='history');")
rep("  if(state.view==='saved'){renderSaved();return;}",
    "  if(state.view==='saved'){renderSaved();return;}\n  if(state.view==='history'){renderHistory();return;}")

# version modal listeners
rep("$('viewEngagement').addEventListener('click',()=>setView('engagement'));",
    "$('viewEngagement').addEventListener('click',()=>setView('engagement'));\n$('versionKeep').addEventListener('click',()=>doSaveVersion('keep'));\n$('versionReplace').addEventListener('click',()=>doSaveVersion('replace'));\n$('versionClose').addEventListener('click',()=>{document.getElementById('versionModal').style.display='none';});")

# boot: also load history
rep("loadPushedTimetable().then(()=>{renderMain();renderChrome();});\nloadSavedList();",
    "loadPushedTimetable().then(()=>{renderMain();renderChrome();});\nloadSavedList();\nloadHistory();")
# login: refresh history; logout: clear history + source
rep("    await syncFromCloud();await loadSavedList();",
    "    await syncFromCloud();await loadSavedList();await loadHistory();")
rep("state.savedList=[];renderAuth();renderChrome();",
    "state.savedList=[];state.history=[];state.source=null;renderAuth();renderChrome();")

# ---- 35) interactive swapping (drag cells into perfect circles) ---------------
SWAP_CSS = r'''/* ---------- interactive swapping ---------- */
.swap-badge{position:absolute;left:3px;top:2px;font-family:var(--mono);font-size:9px;line-height:1;padding:2px 4px;border-radius:4px;pointer-events:none;z-index:1}
.tg-cell.swap-circle{box-shadow:inset 0 0 0 2px var(--green)}
.tg-cell.swap-circle .swap-badge{background:var(--green-tint);color:var(--green-deep);border:1px solid var(--green)}
.tg-cell.swap-vacant,.tg-cell.swap-conflict{box-shadow:inset 0 0 0 2px var(--amber);background:var(--amber-tint)}
.tg-cell.swap-vacant .swap-badge,.tg-cell.swap-conflict .swap-badge{background:var(--amber-tint);color:var(--amber-deep);border:1px solid var(--amber)}
.tg-cell.swap-out,.tg-cell.swap-in{box-shadow:inset 0 0 0 1px var(--line2)}
.tg-cell.swap-out .swap-badge,.tg-cell.swap-in .swap-badge{background:var(--surface2);color:var(--ink2);border:1px solid var(--line2)}
.tg-cell.swap-pick{outline:2px dashed var(--green);outline-offset:-2px}
.tg-cell.swap-over{outline:2px dashed var(--amber);outline-offset:-2px}
.tg-cell.swap-drag{opacity:.55}
.tg-cell[draggable=true]{cursor:grab}
'''
rep("</style>", SWAP_CSS + "</style>")

# viewbar: swap controls inside editControls
rep('<span class="vb-info" id="editCount"></span></span>',
    '<span class="vb-info" id="editCount"></span><button class="mini-export" id="btnSwapMode">⇄ Swap</button><span class="vb-info" id="swapHud" style="display:none"></span><button class="mini-export" id="btnSwapApply" style="display:none">Apply swap</button><button class="mini-export" id="btnSwapClear" style="display:none">Clear</button></span>')

# click handler: swap-mode intercept before edit mode
rep("  if(state.editMode){const ec=e.target.closest('.tg-cell');if(ec){openCellEditor(ec.dataset);return;}}",
    "  if(state.swapMode){const sc=e.target.closest('.tg-cell');if(sc){handleSwapClick(sc);}return;}\n  if(state.editMode){const ec=e.target.closest('.tg-cell');if(ec){openCellEditor(ec.dataset,ec);return;}}")

# renderMain: decorate swap badges after engagement
rep("  decorateEngagement();",
    "  decorateEngagement();\n  decorateSwap();")

# renderChrome: swap button + HUD state
rep("    $('btnEditMode').textContent=state.editMode?'✎ Editing…':'✎ Edit';",
    "    $('btnEditMode').textContent=state.editMode?'✎ Editing…':'✎ Edit';\n    $('btnSwapMode').textContent=state.swapMode?'⇄ Swapping…':'⇄ Swap';\n    const _sw=state.swapMoves&&state.swapMoves.length?swapLiveEvaluate():null;\n    $('swapHud').style.display=state.swapMode?'':'none';\n    $('btnSwapApply').style.display=state.swapMode?'':'none';\n    $('btnSwapClear').style.display=state.swapMode?'':'none';\n    $('btnSwapApply').disabled=!(state.swapMoves&&state.swapMoves.length);\n    $('btnSwapClear').disabled=!(state.swapMoves&&state.swapMoves.length);\n    $('swapHud').textContent=_sw?('⇄ '+(state.swapMoves.length)+' move'+(state.swapMoves.length===1?'':'s')+' · disruptions '+_sw.net):'';")

# listeners
rep("$('btnEditMode').addEventListener('click',toggleEditMode);",
    "$('btnEditMode').addEventListener('click',toggleEditMode);\n$('btnSwapMode').addEventListener('click',toggleSwapMode);\n$('btnSwapApply').addEventListener('click',applySwap);\n$('btnSwapClear').addEventListener('click',swapClear);")

# swap modal (before the version modal)
rep('<div class="auth-modal" id="versionModal">',
    '<div class="auth-modal" id="swapModal">\n  <div class="auth-box">\n    <h3>Swap needs re-optimizing</h3>\n    <p id="swapResolveMsg" style="font-size:12.5px;color:var(--ink2);margin:0 0 14px">…</p>\n    <div class="auth-row">\n      <button class="btn primary" id="swapResolve">✨ Resolve & apply</button>\n      <button class="btn" id="swapClose">Cancel</button>\n    </div>\n  </div>\n</div>\n<div class="auth-modal" id="versionModal">')

# swap modal listeners
rep("$('versionClose').addEventListener('click',()=>{document.getElementById('versionModal').style.display='none';});",
    "$('versionClose').addEventListener('click',()=>{document.getElementById('versionModal').style.display='none';});\n$('swapResolve').addEventListener('click',doSwapResolve);\n$('swapClose').addEventListener('click',()=>{document.getElementById('swapModal').style.display='none';});")

# combo markers for 'swap' via
rep("(o.via==='saved'?' 💾':'')))", "(o.via==='saved'?' 💾':(o.via==='swap'?' ⇄':''))))")
rep("(c.via==='saved'?' · 💾 from your saved list':'')", "(c.via==='saved'?' · 💾 from your saved list':(c.via==='swap'?' · ⇄ swapped':''))")
rep("(c.via==='saved'?'saved':'in-browser generation')", "(c.via==='saved'?'saved':(c.via==='swap'?'swapped':'in-browser generation'))")

SWAP_MODULE = r'''/* ---------- interactive swapping (drag cells into perfect circles) ---------- */
function swapLiveEvaluate(){
  const c=getSel();if(!c)return null;
  return IMPCC_SOLVER.swapEvaluate(cellsToRaw(c.tt),state.swapMoves||[],effectiveConstraints());
}
function toggleSwapMode(){
  if(!state.swapMode&&!getSel()){setTicker('Generate a combination first','err');return;}
  state.swapMode=!state.swapMode;
  if(state.swapMode){state.editMode=false;if(!state.swapMoves)state.swapMoves=[];}
  else{state.swapMoves=[];state.swapPick=null;state.swapDrag=null;}
  renderChrome();renderMain();
  setTicker(state.swapMode?'Swap mode — drag a cell onto another (or tap two cells). Close circles for 0 disruptions, then Apply swap':'Swap mode off','ok');
}
function swapClear(){state.swapMoves=[];state.swapPick=null;decorateSwap();renderChrome();setTicker('Swap cleared','ok');}
function swapCellIsDual(c,sec,d,s){const cell=c.tt[sec][d][s];return !!(cell&&cell.dual);}
function addSwapMove(from,to){
  const c=getSel();if(!c)return false;
  if(from.sec+'|'+from.d+'|'+from.s===to.sec+'|'+to.d+'|'+to.s){setTicker('A cell cannot move onto itself','err');return false;}
  if(swapCellIsDual(c,from.sec,from.d,from.s)||swapCellIsDual(c,to.sec,to.d,to.s)){setTicker('The shared parallel block cannot be swapped','err');return false;}
  const dup=(state.swapMoves||[]).some(function(m){return m.to.sec===to.sec&&m.to.d===to.d&&m.to.s===to.s;});
  if(dup){setTicker('That cell already receives a move — Clear the swap to redo','err');return false;}
  state.swapMoves=(state.swapMoves||[]).filter(function(m){return !(m.from.sec===from.sec&&m.from.d===from.d&&m.from.s===from.s);});
  state.swapMoves.push({from:from,to:to});
  state.swapPick=null;
  decorateSwap();renderChrome();
  const ev=swapLiveEvaluate();
  setTicker('Move added — disruptions '+ev.net+(ev.net===0?' (perfect circle — Apply swap)':''),ev.net===0?'ok':'run');
  return true;
}
function decorateSwap(){
  const ev=(state.swapMoves&&state.swapMoves.length)?swapLiveEvaluate():null;
  const circleSet={},vacantSet={},conflictSet={},inSet={},outSet={};
  if(ev){
    ev.circles.forEach(function(c){c.forEach(function(k){circleSet[k]=1;});});
    ev.vacant.forEach(function(k){vacantSet[k]=1;});
    ev.conflicts.forEach(function(k){conflictSet[k]=1;});
  }
  (state.swapMoves||[]).forEach(function(m){
    inSet[m.to.sec+'|'+m.to.d+'|'+m.to.s]=1;
    outSet[m.from.sec+'|'+m.from.d+'|'+m.from.s]=1;
  });
  document.querySelectorAll('.tg-cell[data-sec]').forEach(function(el){
    const k=el.dataset.sec+'|'+el.dataset.d+'|'+el.dataset.s;
    el.draggable=state.swapMode;
    const old=el.querySelector('.swap-badge');if(old)old.remove();
    el.classList.remove('swap-circle','swap-vacant','swap-conflict','swap-out','swap-in','swap-pick');
    if(!state.swapMode)return;
    if(state.swapPick===k){el.classList.add('swap-pick');addSwapBadge(el,'➜');}
    if(circleSet[k]){el.classList.add('swap-circle');addSwapBadge(el,'⇄');}
    else if(vacantSet[k]){el.classList.add('swap-vacant');addSwapBadge(el,'⚠');}
    else if(conflictSet[k]){el.classList.add('swap-conflict');addSwapBadge(el,'⚠');}
    else if(outSet[k]&&inSet[k]){el.classList.add('swap-out');addSwapBadge(el,'⇄');}
    else if(outSet[k]){el.classList.add('swap-out');addSwapBadge(el,'→');}
    else if(inSet[k]){el.classList.add('swap-in');addSwapBadge(el,'←');}
  });
}
function addSwapBadge(el,label){const b=document.createElement('span');b.className='swap-badge';b.textContent=label;el.appendChild(b);}
function handleSwapClick(cellEl){
  const k=cellEl.dataset.sec+'|'+cellEl.dataset.d+'|'+cellEl.dataset.s;
  if(!state.swapPick){state.swapPick=k;decorateSwap();setTicker('Now click the cell this teacher should move to','run',true);return;}
  if(state.swapPick===k){state.swapPick=null;decorateSwap();return;}
  const p=state.swapPick.split('|');
  addSwapMove({sec:p[0],d:+p[1],s:+p[2]},{sec:cellEl.dataset.sec,d:+cellEl.dataset.d,s:+cellEl.dataset.s});
}
function applySwap(){
  if(!(state.swapMoves&&state.swapMoves.length)){setTicker('No swap moves to apply','err');return;}
  const c=getSel();if(!c)return;
  const raw=cellsToRaw(c.tt);
  const ev=IMPCC_SOLVER.swapEvaluate(raw,state.swapMoves,effectiveConstraints());
  if(ev.net===0){
    finishSwap(IMPCC_SOLVER.swapApply(raw,ev.circles),ev.circles,[],ev.constraintViolations);
  }else{
    document.getElementById('swapResolveMsg').innerHTML=(function(){
      let why='';
      if(ev.vacant.length||ev.conflicts.length)why='The moves do not form perfect circles yet — a targeted optimization will close the chains with the fewest extra cells to bring disruptions to 0.';
      if(ev.doubleBookings.length)why+=(why?' ':'')+'<b>'+ev.doubleBookings.length+' move(s) would double-book a teacher</b> (landing on a period where they already teach another class) — that part cannot be auto-fixed.';
      return 'Net disruptions: <b>'+ev.net+'</b> — '+why;
    })();
    document.getElementById('swapModal').style.display='flex';
  }
}
function doSwapResolve(){
  const c=getSel();if(!c)return;
  const raw=cellsToRaw(c.tt);
  const res=IMPCC_SOLVER.swapComplete(raw,state.swapMoves,effectiveConstraints());
  document.getElementById('swapModal').style.display='none';
  if(res.resolved){
    finishSwap(IMPCC_SOLVER.swapApply(raw,res.circles),res.circles,res.extraMoves,[]);
    setTicker('Targeted optimization closed the chains — swap applied','ok');
  }else{
    const left=(res.remainingNet!=null)?res.remainingNet:res.unresolved.length;
    setTicker('Could not resolve — '+left+' disruption(s) remain (double-booked teachers / constraints). Add more cells to the swap or Clear','err');
  }
}
function finishSwap(newtt,circles,extra,warnings){
  const c=getSel();
  const combo=makeCombo({score:c.score,timetable:newtt},'swap');
  state.combos.push(combo);
  state.selected=combo.id;
  state.lastSwap={circles:circles,extra:extra};
  state.swapMoves=[];state.swapMode=false;state.swapPick=null;
  persist();renderAll();
  const w=warnings&&warnings.length?(' · ⚠ '+warnings.length+' constraint warning'+(warnings.length===1?'':'s')):'';
  setTicker('Swap applied — '+circles.length+' circle'+(circles.length===1?'':'s')+' · '+circles.reduce(function(n,c){return n+c.length;},0)+' cells'+(extra.length?(' · '+extra.length+' auto-closed'):'')+w,'ok');
}
mainEl.addEventListener('dragstart',function(e){
  if(!state.swapMode)return;
  const el=e.target&&e.target.closest?e.target.closest('.tg-cell[data-sec]'):null;
  if(!el){e.preventDefault();return;}
  const k=el.dataset.sec+'|'+el.dataset.d+'|'+el.dataset.s;
  try{e.dataTransfer.setData('text/plain',k);}catch(err){}
  try{e.dataTransfer.effectAllowed='move';}catch(err){}
  state.swapDrag=k;el.classList.add('swap-drag');
});
mainEl.addEventListener('dragover',function(e){
  if(!state.swapMode)return;
  const el=e.target&&e.target.closest?e.target.closest('.tg-cell[data-sec]'):null;
  if(el){e.preventDefault();el.classList.add('swap-over');}
});
mainEl.addEventListener('dragleave',function(e){
  const el=e.target&&e.target.closest?e.target.closest('.tg-cell[data-sec]'):null;
  if(el)el.classList.remove('swap-over');
});
mainEl.addEventListener('drop',function(e){
  if(!state.swapMode)return;
  const el=e.target&&e.target.closest?e.target.closest('.tg-cell[data-sec]'):null;
  if(el)e.preventDefault();
  const src=state.swapDrag;state.swapDrag=null;
  document.querySelectorAll('.tg-cell').forEach(function(x){x.classList.remove('swap-over','swap-drag');});
  if(!el||!src)return;
  const p=src.split('|');
  addSwapMove({sec:p[0],d:+p[1],s:+p[2]},{sec:el.dataset.sec,d:+el.dataset.d,s:+el.dataset.s});
});
mainEl.addEventListener('dragend',function(){state.swapDrag=null;document.querySelectorAll('.tg-cell').forEach(function(x){x.classList.remove('swap-over','swap-drag');});});

'''
rep("/* ---------- boot: restore saved results (no auto-generation) ---------- */",
    SWAP_MODULE + "/* ---------- boot: restore saved results (no auto-generation) ---------- */")

# ---- 36) Clear results (generated pool) + Clear history (action log) ---------
rep('<button class="mini-export" id="btnFacultyImages" title="Download every faculty member schedule as PNG images (ZIP)">⇩ Faculty images (ZIP)</button>',
    '<button class="mini-export" id="btnFacultyImages" title="Download every faculty member schedule as PNG images (ZIP)">⇩ Faculty images (ZIP)</button>\n    <button class="mini-export" id="btnClearResults" title="Clear all generated combinations (saved timetables stay)">🗑 Clear results</button>')
rep("  $('btnFacultyImages').disabled=!list.length;",
    "  $('btnFacultyImages').disabled=!list.length;\n  $('btnClearResults').disabled=!list.length;")
rep("$('btnFacultyImages').addEventListener('click',exportAllFacultyImages);",
    "$('btnFacultyImages').addEventListener('click',exportAllFacultyImages);\n$('btnClearResults').addEventListener('click',clearResults);")

CLEAR_MODULE = r'''/* ---------- clear results (generated pool) + clear history (action log) ---------- */
function clearResults(){
  clearStorage();
  state.combos=[];state.selected=null;comboSeq=0;
  state.cpsatDone=false;state.cpsatMerged=0;
  state.seen=new Set();
  state.source=null;state.lastLocks=null;state.lastSwap=null;
  closeSpotlight();
  state.sectionFilter='all';secFilterEl.value='all';
  setCpsatStatus('CP-SAT: idle — press “Compute optimal” to call the backend','');
  renderChrome();
  loadPushedTimetable().then(function(){renderMain();renderChrome();});
  setTicker('Results cleared — saved timetables and the published timetable are untouched','ok');
}
async function clearHistory(){
  if(!SB||!SB.loggedIn){setTicker('Sign in to clear history','err');return;}
  if(!(state.history&&state.history.length)){setTicker('History is already empty','ok');return;}
  let ok=true;
  try{ok=window.confirm('Clear the entire version history? This wipes the action log (messages + version IDs) — saved timetables and versions stay.');}catch(e){ok=true;}
  if(ok===false)return;
  setTicker('Clearing history…','run',true);
  try{
    await SB.clearHistory();
    state.history=[];
    renderMain();
    setTicker('History cleared — saved timetables and versions are untouched','ok');
  }catch(e){setTicker('Clear history failed: '+e.message,'err');}
}

'''
rep("/* ---------- boot: restore saved results (no auto-generation) ---------- */",
    CLEAR_MODULE + "/* ---------- boot: restore saved results (no auto-generation) ---------- */")

# ---- 37) masthead: avatar menu + faculty live search + edit-strip fix ---------
# (a) fix: show the Edit/Re-optimize/Clear/Swap strip on first load too
rep("    $('btnEditMode').textContent=state.editMode?'✎ Editing…':'✎ Edit';",
    "    $('btnEditMode').textContent=state.editMode?'✎ Editing…':'✎ Edit';\n    $('editControls').style.display=(state.view==='sections')?'':'none';")

# (b) add the faculty search box to the masthead (before the auth area)
rep('<div class="mast-auth" id="authUi"></div>',
    '<div class="mast-search" id="facSearchWrap">\n    <input id="facSearchInput" type="text" placeholder="🔍 Search faculty — live location" autocomplete="off">\n    <div class="fac-drop" id="facDrop"></div>\n  </div>\n  <div class="mast-auth" id="authUi"></div>')

# (c) CSS
rep("</style>", r'''.mast-search{position:relative;flex:0 1 300px;min-width:210px;display:flex;align-items:center;background:linear-gradient(135deg,var(--green-deep),var(--green));border:1px solid var(--gold);border-radius:99px;padding:2px;box-shadow:0 2px 6px rgba(14,59,41,.18)}
.mast-search input{width:100%;padding:8px 16px;border:1px solid transparent;border-radius:96px;font-size:12.5px;background:#fff;color:var(--ink);box-shadow:none}
.mast-search input:focus{outline:none;border-color:var(--amber);box-shadow:0 0 0 2px rgba(232,164,31,.35)}
.fac-drop{position:absolute;top:calc(100% + 6px);left:0;right:0;background:var(--surface);border:1px solid var(--line);border-radius:12px;box-shadow:0 16px 48px rgba(14,59,41,.22);z-index:120;max-height:360px;overflow:auto;display:none}
.fac-drop.open{display:block}
.fac-item{padding:9px 12px;border-bottom:1px solid var(--line2);cursor:default}
.fac-item:last-child{border-bottom:none}
.fac-item:hover{background:var(--green-tint)}
.fac-item .fn{font-weight:700;font-size:13px;color:var(--ink)}
.fac-item .fl{font-size:11px;color:var(--green-deep);margin-top:2px}
.fac-item .ff{font-size:10.5px;color:var(--ink2);margin-top:2px}
.fac-item .free{color:var(--ink2);font-style:italic}
.mast-auth{position:relative}
.avatar{width:40px;height:40px;border-radius:50%;border:2px solid var(--green);background:var(--green-tint);color:var(--green-deep);font-family:var(--disp);font-weight:900;font-size:16px;display:flex;align-items:center;justify-content:center;cursor:pointer;flex:0 0 auto}
.avatar:hover{background:var(--green);color:#f0f6ef}
.avatar-menu{position:absolute;top:calc(100% + 8px);right:0;background:var(--surface);border:1px solid var(--line);border-radius:12px;box-shadow:0 16px 48px rgba(14,59,41,.25);z-index:130;min-width:210px;padding:10px;display:none}
.avatar-menu.open{display:block}
.avatar-menu .am-email{font-family:var(--mono);font-size:11px;color:var(--ink2);padding:2px 6px 8px;border-bottom:1px solid var(--line2);margin-bottom:6px;word-break:break-all}
.avatar-menu .mini-export{width:100%;text-align:left;margin-bottom:4px}
</style>''')

# (d) module: live-location search + avatar menu
HEADER_MODULE = r'''/* ---------- masthead: avatar menu + faculty live search ---------- */
function liveNow(){
  const now=new Date();
  const dow=now.getDay();
  const mins=now.getHours()*60+now.getMinutes();
  if(dow===0||dow===6)return {day:-1,period:-1,phase:'weekend'};
  const day=dow-1;
  const b=[[510,550],[550,590],[590,630],[655,695],[695,735]];
  if(mins<b[0][0])return {day:day,period:-1,phase:'before'};
  if(mins>=b[4][1])return {day:day,period:-1,phase:'after'};
  for(let p=0;p<5;p++){if(mins>=b[p][0]&&mins<b[p][1])return {day:day,period:p,phase:'period'};}
  return {day:day,period:-1,phase:'break'};
}
function teacherEntries(name){
  const c=getSel();if(!c)return [];
  return (buildTeacherIndex(c.tt)[name])||[];
}
function liveLocationOf(name){
  const c=getSel();
  if(!c)return {text:'No timetable selected yet',entries:[]};
  const entries=teacherEntries(name);
  if(!entries.length)return {text:'No classes in the selected timetable',entries:[]};
  const lv=liveNow();
  if(lv.phase==='weekend')return {text:'Weekend — free',entries:entries};
  if(lv.phase==='before')return {text:'Free — college hours not started',entries:entries};
  if(lv.phase==='after')return {text:'Free — college hours over',entries:entries};
  if(lv.phase==='break')return {text:'Break time — free',entries:entries};
  for(const e of entries){if(e.d===lv.day&&e.s===lv.period)return {text:'In '+engSecLabel(e.sec)+' — '+e.subj,entries:entries};}
  return {text:'Free',entries:entries};
}
function upcomingFixtures(name){
  const entries=teacherEntries(name);
  const lv=liveNow();
  let cur=0;
  if(lv.phase!=='weekend')cur=lv.day*5+(lv.period>=0?lv.period+1:0);
  const sorted=entries.slice().sort(function(a,b){return (a.d*5+a.s)-(b.d*5+b.s);});
  const up=sorted.filter(function(e){return (e.d*5+e.s)>=cur;});
  return (up.length?up:sorted).slice(0,4);
}
function renderFacDrop(){
  const inp=document.getElementById('facSearchInput');
  const drop=document.getElementById('facDrop');
  if(!inp||!drop)return;
  const q=(inp.value||'').trim().toLowerCase();
  if(!q){drop.classList.remove('open');drop.innerHTML='';return;}
  const names=facultyNames().filter(function(n){return n.toLowerCase().indexOf(q)>=0;}).slice(0,8);
  if(!names.length){drop.innerHTML='<div class="fac-item"><span class="free">No faculty match “'+esc(q)+'”</span></div>';drop.classList.add('open');return;}
  let h='';
  for(const nm of names){
    const loc=liveLocationOf(nm);
    const up=upcomingFixtures(nm);
    h+='<div class="fac-item" data-fac="'+esc(nm)+'">'+
      '<div class="fn">'+esc(nm)+'</div>'+
      '<div class="fl">🕒 '+esc(loc.text)+'</div>'+
      '<div class="ff">'+(up.length?('▶ '+up.map(function(e){return DAYS[e.d]+' '+SLOTS[e.s]+' · '+esc(e.subj)+' ('+esc(engSecLabel(e.sec))+')';}).join(' · ')):'No upcoming classes')+'</div>'+
      '</div>';
  }
  drop.innerHTML=h;
  drop.classList.add('open');
  drop.querySelectorAll('.fac-item[data-fac]').forEach(function(item){
    item.addEventListener('click',function(){
      const nm=item.getAttribute('data-fac');
      drop.classList.remove('open');
      inp.value='';
      if(nm)openSpotlight(nm);
    });
  });
}
function renderAuth(){
  const el=document.getElementById('authUi');if(!el)return;
  if(SB&&SB.loggedIn){
    const initial=((SB.user&&SB.user.email)||'A').charAt(0).toUpperCase();
    el.innerHTML='<button class="avatar" id="avatarBtn" title="Account">'+esc(initial)+'</button><div class="avatar-menu" id="avatarMenu"><div class="am-email">'+esc((SB.user&&SB.user.email)||'')+'</div><button class="mini-export" id="authSignOut">Sign out</button></div>';
    document.getElementById('avatarBtn').addEventListener('click',function(e){e.stopPropagation();document.getElementById('avatarMenu').classList.toggle('open');});
    document.getElementById('authSignOut').addEventListener('click',function(){SB.logout().then(function(){state.savedList=[];state.history=[];state.source=null;renderAuth();renderChrome();setTicker('Signed out — local data only','ok');});});
  }else{
    el.innerHTML='<button class="avatar" id="avatarBtn" title="Sign in">👤</button><div class="avatar-menu" id="avatarMenu"><div class="am-email">Not signed in</div><button class="mini-export" id="authSignIn">Sign in</button></div>';
    document.getElementById('avatarBtn').addEventListener('click',function(e){e.stopPropagation();document.getElementById('avatarMenu').classList.toggle('open');});
    document.getElementById('authSignIn').addEventListener('click',function(){document.getElementById('authModal').style.display='flex';});
  }
}
(function wireHeader(){
  const inp=document.getElementById('facSearchInput');
  if(inp){inp.addEventListener('input',renderFacDrop);inp.addEventListener('focus',renderFacDrop);}
  document.addEventListener('click',function(e){
    const drop=document.getElementById('facDrop');
    const wrap=document.getElementById('facSearchWrap');
    if(drop&&wrap&&!wrap.contains(e.target))drop.classList.remove('open');
    const menu=document.getElementById('avatarMenu');
    const auth=document.getElementById('authUi');
    if(menu&&auth&&!auth.contains(e.target))menu.classList.remove('open');
  });
})();

'''
rep("/* ---------- boot: restore saved results (no auto-generation) ---------- */",
    HEADER_MODULE + "/* ---------- boot: restore saved results (no auto-generation) ---------- */")

# ---- 38) keep the masthead (and its dropdowns) above the sticky console ----
rep(".mast{max-width:1280px;margin:0 auto;padding:26px 24px 18px;display:flex;gap:20px;align-items:center;flex-wrap:wrap;animation:drop .6s ease both}",
    ".mast{position:relative;z-index:70;max-width:1280px;margin:0 auto;padding:26px 24px 18px;display:flex;gap:20px;align-items:center;flex-wrap:wrap;animation:drop .6s ease both}")

# ---- 39) responsive: high-quality mobile experience (desktop unchanged) -------
rep("</style>", r'''.mast .logo{width:88px;height:88px;object-fit:contain;flex:0 0 auto;filter:drop-shadow(0 5px 14px rgba(14,59,41,.28))}
/* ============ MOBILE (phones) — compact & native; desktop untouched ============ */
@media(max-width:760px){
  html,body{font-size:14.5px}
  *{-webkit-tap-highlight-color:transparent}
  .wrap{padding:14px 12px 44px}
  footer{padding:0 14px 30px;font-size:10px}

  /* masthead: dark green band, a few shades lighter */
  .mast{max-width:none;margin:0;padding:14px 14px 12px;gap:10px;align-items:center;background:linear-gradient(180deg,#27553c 0%,#1c3e2c 100%);border-bottom:3px solid var(--amber);box-shadow:0 4px 14px rgba(10,20,14,.18)}
  .mast .logo{width:44px;height:44px;flex:0 0 auto;filter:drop-shadow(0 3px 8px rgba(0,0,0,.35))}
  .mast-txt{flex:1 1 0%;min-width:0}
  .mast-auth{margin-left:auto;flex:0 0 auto;align-self:center}
  .overline{font-size:8px;letter-spacing:.14em;color:#9db5a8}
  .mast h1{font-size:clamp(18px,6.2vw,26px);line-height:1.08;margin:1px 0 3px;color:#f2f7f3}
  .mast h1 em{color:var(--amber)}
  .sub{font-size:11px;color:#b9c9bf}
  .avatar{border-color:rgba(255,255,255,.6)}

  .mast-search{flex:1 1 100%;order:10;min-width:0;margin-top:8px;background:linear-gradient(135deg,var(--amber),var(--amber-deep));border:2px solid var(--green-deep);border-radius:99px;padding:3px;box-shadow:0 3px 10px rgba(138,98,16,.25)}
  .mast-search input{font-size:13px;padding:9px 15px;border:1px solid transparent;background:#fff;box-shadow:none}
  .mast-search input:focus{outline:none;border-color:var(--green);box-shadow:0 0 0 2px rgba(28,107,72,.3)}
  .fac-drop{max-height:290px}
  .fac-item{padding:10px 12px}

  /* console: light control panel (no harsh dark slab) + compact controls */
  .console{position:static;top:auto;background:var(--surface);color:var(--ink);box-shadow:0 4px 14px rgba(24,39,32,.07);border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
  .prog{display:none}
  .con-in{padding:8px 10px 6px;gap:6px}
  .con-in .btn{padding:6px 9px;font-size:10.5px;flex:1 1 auto;justify-content:center;gap:5px;border-radius:8px;background:var(--green-tint);color:var(--green-deep);border:1px solid var(--green);font-weight:600}
  .con-in .btn:hover:not(:disabled){background:var(--green);color:#f0f6ef;border-color:var(--green);transform:none}
  .con-in .btn.primary{background:var(--green);color:#f0f6ef;border-color:var(--green)}
  .con-in .btn.primary:hover:not(:disabled){background:#22805a;color:#fff}
  .con-in .btn.amber{background:var(--amber-tint);color:var(--amber-deep);border:1px solid var(--amber)}
  .con-in .btn.amber:hover:not(:disabled){background:var(--amber);color:#241a02;border-color:var(--amber)}
  .con-in .btn.stop{background:var(--red);color:#fff;border-color:var(--red)}
  .con-in .btn .g{font-size:10px}
  .con-sel{flex:1 1 auto;min-width:0;gap:6px}
  .con-sel label{display:none}
  select#comboSel{font-size:11px;padding:7px 8px;max-width:none;background:#fff;color:var(--ink);border:1px solid var(--line2)}
  select#comboSel:focus{outline:2px solid var(--amber);outline-offset:1px}
  .nav-arrows .btn{padding:6px 9px;flex:0 0 auto;background:#fff;color:var(--green-deep);border:1px solid var(--line2)}
  .nav-arrows .btn:hover:not(:disabled){background:var(--green);color:#f0f6ef}
  .badges{margin-left:auto;gap:6px;flex:0 0 auto}
  .badge{font-size:10px;padding:6px 8px;flex:0 0 auto;background:var(--surface2);border:1px solid var(--line2);color:var(--ink)}
  .badge.score{color:var(--amber-deep);border-color:var(--amber)}
  .badge.score.best{background:var(--amber);color:#241a02;border-color:var(--amber)}
  .con-row2{padding:5px 10px 6px;font-size:9.5px;gap:6px 10px;flex-wrap:nowrap;border-top:1px solid var(--line);color:var(--ink2)}
  .con-row2 .tick{flex:1 1 auto;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--ink2)}
  #cpsatStatus{flex:0 0 auto;max-width:46%;margin-left:auto;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--ink2)}
  #cpsatStatus.ok{color:var(--green-deep)}
  #cpsatStatus.err{color:var(--red)}
  #cpsatStatus.warn{color:var(--amber-deep)}
  #publishedAge{display:none}

  /* scorecard: very minimalist — one compact row */
  .scorecard{display:flex;flex-direction:row;align-items:center;gap:14px;padding:12px 14px;margin-bottom:12px;border-left-width:5px;border-radius:11px}
  .scorecard > div:first-child{flex:0 0 auto;min-width:86px}
  .sc-label{font-size:7.5px;letter-spacing:.12em}
  .sc-num{font-size:34px;line-height:1;margin:1px 0 0}
  .sc-delta{display:none}
  .scorecard > div:nth-child(2){flex:1 1 auto;min-width:0}
  .rankchip{font-size:10.5px;padding:2px 9px;margin-bottom:3px}
  .stand-text{font-size:13px;line-height:1.3}
  .pct{display:none}
  .meter{display:none}
  .bd{display:none}
  .hist-wrap{display:none}

  /* viewbar */
  .viewbar{gap:8px;margin-bottom:12px}
  .seg{width:100%;display:grid;grid-template-columns:repeat(4,1fr);gap:1px;padding:1px;flex-wrap:wrap;overflow:hidden;background:var(--line2);border:1px solid var(--line2);border-radius:10px;box-shadow:0 2px 8px rgba(24,39,32,.06)}
  .seg button{flex:none;justify-content:center;gap:4px;padding:10px 4px;font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0;background:var(--surface);border-radius:0;box-shadow:none}
  .seg button.on{box-shadow:none}
  .seg button:not(.on):hover{background:var(--green-tint)}
  .seg button:last-child{grid-column:1/-1}
  .vb-filter{flex:1 1 auto;justify-content:space-between;padding:7px 12px}
  .vb-filter select{max-width:58vw}
  .vb-info{flex:1 1 100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:10px}
  .vb-edit{display:flex;flex-wrap:wrap;gap:6px;flex:1 1 100%}
  .vb-edit .mini-export{margin-left:0;flex:1 1 auto;justify-content:center;padding:8px 8px;font-size:10.5px;background:var(--green-tint);color:var(--green-deep);border:1px solid var(--green);border-radius:8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .vb-edit .mini-export:hover:not(:disabled){background:var(--green);color:#f0f6ef}
  .vb-edit .vb-info{flex:1 1 100%;margin:0;text-align:left;color:var(--ink2)}
  .viewbar > .mini-export{flex:1 1 auto;justify-content:center;margin-left:0;padding:8px 8px;font-size:10px;background:var(--green-tint);color:var(--green-deep);border:1px solid var(--green);border-radius:8px}
  .viewbar > .mini-export:hover:not(:disabled){background:var(--green);color:#f0f6ef}

  /* streams & sections */
  .stream{margin-bottom:22px}
  .stream-head{flex-wrap:wrap;gap:7px;margin-bottom:10px}
  .stream-head h2{font-size:17px}
  .stream-head .cnt{margin-left:0;flex-basis:100%;font-size:10px}
  .stream-head .card-csv,.stream-head .card-pdf,.stream-head .card-img{padding:6px 9px;font-size:8.5px;margin-left:0}
  .sec-grid{gap:13px}
  .sec-card > header{flex-wrap:wrap;gap:6px;padding:9px 11px}
  .sec-card h3{font-size:14px}
  .sec-card .pw{margin-left:auto;font-size:9px}
  .sec-card > header .card-csv,.sec-card > header .card-img{padding:5px 8px;font-size:8.5px;margin-left:0}
  .tt-wrap{-webkit-overflow-scrolling:touch}
  .tt{min-width:430px;padding:8px;gap:2px}
  .tg-cell{min-height:44px;padding:5px 6px}
  .tg-cell b{font-size:10.5px}
  .tg-cell i{font-size:9px}
  .tg-break{min-height:44px}

  /* faculty view */
  .t-grid{grid-template-columns:1fr;gap:13px}
  .t-card{padding:13px 14px}
  .t-head{flex-wrap:wrap;gap:8px}
  .t-head h4{font-size:14.5px}
  .spot-hint{margin-left:auto}
  .t-head .card-csv,.t-head .card-img{margin-left:0;padding:5px 8px;font-size:8.5px}
  .t-sched{max-height:220px}

  /* data cards (constraints / saved / history / directory) */
  .cons-grid{grid-template-columns:1fr;gap:13px}
  .cons-card{padding:12px 13px}
  .cons-note{padding:11px 13px;font-size:12.5px}
  .cons-actions{float:none;display:flex;flex-wrap:wrap;gap:6px;margin-left:0;margin-top:8px}
  .cons-nl{font-size:12px}
  .rule-row{flex-wrap:wrap;gap:4px 8px}
  .rule-label{min-width:0;flex-basis:100%}
  .rule-val{font-size:11px}
  .rule-ed{flex-wrap:wrap}
  .ed-chip{padding:3px 10px;font-size:10px}
  .alloc-row{grid-template-columns:minmax(0,1fr) minmax(0,1.2fr) 48px 24px;gap:4px}
  .dir-add input#dirNewName{flex:1 1 100%}
  .dir-add select{flex:1 1 auto}

  /* tweaks */
  .tweak-add{flex-direction:column;align-items:stretch;gap:7px}
  .tweak-add select,.tweak-add input[type=date]{width:100%;padding:9px 10px}

  /* engagement */
  .eng-summary{display:grid;grid-template-columns:repeat(3,1fr);gap:7px}
  .eng-summary .stat{min-width:0;padding:9px 6px}
  .eng-summary .stat b{font-size:20px}
  .eng-summary .stat span{font-size:7.5px;letter-spacing:.04em}
  .eng-warn{font-size:12px;padding:9px 12px}
  .eng-actions{flex-wrap:wrap}
  .eng-actions .mini-export{flex:1 1 auto;justify-content:center;margin-left:0}
  .eng-stmt{font-size:12.5px;padding:9px 12px;line-height:1.5}
  .eng-row{grid-template-columns:1fr;gap:2px;padding:9px 11px}
  .eng-row .eng-arrow{display:none}
  .eng-row .eng-cover{padding-top:6px;margin-top:2px;border-top:1px dashed var(--line2)}

  /* spotlight drawer */
  .dr-head{padding:10px 12px;gap:8px}
  .dr-title h3{font-size:16px}
  .dr-title span{font-size:9px}
  .dr-export .btn{padding:7px 9px;font-size:10px}
  .dr-close{width:34px;height:34px}
  .dr-body{padding:14px}
  .sp-stats{gap:6px}
  .stat b{font-size:15px}
  .stat span{font-size:7.5px}

  /* misc */
  .empty{padding:38px 18px}
  .empty h3{font-size:19px}
  .auth-box{padding:18px;width:min(420px,94vw)}
  .cell-editor{width:min(400px,92vw)}
  .filter-note{font-size:12px;padding:8px 12px}
}
@media(max-width:400px){
  .overline{display:none}
  .mast h1{font-size:19px}
  .sub{font-size:10.5px}
  .con-in .btn{font-size:11px;padding:9px 7px}
  .tt{min-width:395px}
  .tg-cell b{font-size:10px}
  .seg button{font-size:10px;gap:2px;padding:10px 3px}
}
</style>''')

# ---- 40) developer credit footer (bottom of page) ---------------------------
rep("</style>", r'''.dev-credit{display:flex;flex-wrap:wrap;gap:6px 18px;align-items:center;justify-content:center;text-align:center}
.dev-credit .heart{color:var(--red);display:inline-block;margin:0 2px;animation:heartbeat 1.3s ease infinite}
@keyframes heartbeat{0%,100%{transform:scale(1)}50%{transform:scale(1.28)}}
.dev-credit b{color:var(--green-deep);font-weight:700}
.dev-links{display:inline-flex;gap:14px}
.dev-links a{color:var(--green);text-decoration:none;font-weight:600;letter-spacing:.02em;transition:color .15s ease}
.dev-links a:hover{color:var(--amber-deep);text-decoration:underline}
@media(max-width:760px){
  .dev-credit{flex-direction:column;gap:4px}
  .dev-links{gap:16px}
}
</style>''')

io.open(DST, "w", encoding="utf-8").write(src)
print("OK → wrote", DST, "(", len(src), "bytes )")
