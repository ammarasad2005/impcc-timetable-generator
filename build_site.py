"""Build self-contained index.html: inline solver.js + app.js into the page shell."""
import io

HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>IMPCC — Inter (1st Shift) Timetable Generator</title>
<style>
  :root{
    --ink:#1a2233; --muted:#6b7280; --line:#e5e7eb;
    --com:#2f5597; --ics:#0e7a5f; --paper:#ffffff; --bg:#f4f6fa;
    --accent:#1d4ed8; --accent-soft:#e8efff;
  }
  *{box-sizing:border-box}
  body{margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
       background:var(--bg);color:var(--ink);line-height:1.45}
  header{background:linear-gradient(120deg,#1d3557,#2f5597);color:#fff;padding:26px 22px 22px}
  header h1{margin:0 0 6px;font-size:1.45rem}
  header p{margin:0;opacity:.9;font-size:.92rem;max-width:980px}
  .wrap{max-width:1320px;margin:0 auto;padding:18px}
  .bar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;position:sticky;top:0;
       background:var(--bg);padding:12px 0;z-index:5}
  .bar .lbl{font-weight:600;font-size:.9rem}
  select{font-size:.95rem;padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:#fff}
  .pill{font-weight:700;padding:6px 12px;border-radius:999px;font-size:.8rem}
  .rank-badge{background:var(--accent-soft);color:var(--accent)}
  .score-badge{background:#eef2ff;color:#4338ca}
  .meta{font-size:.8rem;color:var(--muted)}
  .viewtoggle{display:inline-flex;border:1px solid var(--line);border-radius:8px;overflow:hidden;background:#fff}
  .viewtoggle button{border:none;background:#fff;padding:8px 14px;font-size:.9rem;cursor:pointer}
  .viewtoggle button.on{background:var(--accent);color:#fff}
  button#genbtn{background:#1d4ed8;color:#fff;border:none;border-radius:8px;padding:8px 16px;font-size:.9rem;cursor:pointer;font-weight:600}
  button#genbtn.stop{background:#c2410c}
  button#optbtn{background:#7c3aed;color:#fff;border:none;border-radius:8px;padding:8px 16px;font-size:.9rem;cursor:pointer;font-weight:600}
  button#optbtn:disabled{opacity:.6;cursor:default}
  button#genbtn:disabled{opacity:.6;cursor:default}
  .nav{display:inline-flex;gap:4px}
  .nav button{background:#fff;border:1px solid var(--line);border-radius:8px;padding:6px 10px;cursor:pointer;font-size:.95rem}
  .nav button:disabled{opacity:.4;cursor:default}
  button#printbtn{background:#0e7a5f;color:#fff;border:none;border-radius:8px;padding:8px 14px;font-size:.9rem;cursor:pointer}
  #semantic{background:#fff;border:1px solid var(--line);border-radius:12px;padding:12px 16px;margin-top:12px;font-size:.86rem;color:#334155;max-width:900px}
  #semantic b{color:var(--ink)}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:16px;margin-top:6px}
  .card{background:var(--paper);border:1px solid var(--line);border-radius:12px;overflow:hidden;
        box-shadow:0 1px 3px rgba(16,24,40,.08)}
  .card h2{margin:0;padding:10px 14px;font-size:1rem;color:#fff;font-weight:600}
  .card.com h2{background:var(--com)} .card.ics h2{background:var(--ics)}
  table{width:100%;border-collapse:collapse;font-size:.82rem}
  th,td{border:1px solid var(--line);padding:6px 4px;text-align:center;vertical-align:top}
  thead th{background:#f0f4fb;font-size:.72rem;color:#334155;text-transform:uppercase;letter-spacing:.3px}
  td.day{font-weight:700;background:#fafbfd;color:#334155;white-space:nowrap}
  td.break-cell{background:#fff5f0;color:#c2410c;font-size:.68rem;vertical-align:middle}
  .subj{font-weight:600;font-size:.8rem}
  .tchr{display:block;font-weight:400;font-size:.7rem;color:var(--muted);margin-top:1px}
  td.par .subj{color:#0e7a5f}
  .tgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px;margin-top:6px}
  .tcard{background:#fff;border:1px solid var(--line);border-radius:12px;padding:12px 14px}
  .tcard .tname{font-weight:700;font-size:.92rem}
  .tcard .tload{font-size:.75rem;color:var(--muted);margin-left:6px;display:inline}
  .tcard .trule{font-size:.74rem;color:#0e7a5f;font-style:italic;margin:2px 0 8px}
  .tcard ul{margin:0;padding-left:0;list-style:none;font-size:.8rem}
  .tcard li{padding:2px 0;border-top:1px dashed var(--line)}
  .tcard li span.dp{display:inline-block;min-width:66px;font-weight:600;color:#334155}
  .note{background:#fff;border:1px dashed var(--line);border-radius:12px;padding:14px 18px;margin-top:18px;font-size:.85rem;color:#374151}
  .note details{margin-top:8px}
  .note summary{cursor:pointer;font-weight:600;color:var(--accent)}
  footer{color:var(--muted);font-size:.78rem;padding:10px 22px 30px;max-width:1320px;margin:0 auto}
  @media print{ .bar{display:none} .card{break-inside:avoid} header{background:#fff;color:#000} }
</style>
</head>
<body>
<header>
  <h1>IMPCC — Inter (1st Shift) Timetable Generator</h1>
  <p>Islamabad Model Postgraduate College of Commerce (H-8). ICS &amp; I.Com · Mon–Fri · 5 periods/day (40 min) · break after 3rd period.
     <b>Everything is generated live in your browser</b> by a constraint solver (a JavaScript port of the same model used offline).
     <b>No cutoff:</b> every distinct valid combination that is found is kept, shown in the chooser, and ranked by score — hit <b>&ldquo;Generate more&rdquo;</b> to keep growing the set.</p>
</header>
<div class="wrap">
  <div class="bar">
    <button id="genbtn">Generating…</button>
    <button id="optbtn">Compute optimal (CP-SAT)</button>
    <span class="lbl">Combination</span>
    <span class="nav">
      <button id="prevbtn" disabled>◀</button>
      <button id="nextbtn" disabled>▶</button>
    </span>
    <select id="combo"></select>
    <span id="rank" class="pill rank-badge">—</span>
    <span id="score" class="pill score-badge">—</span>
    <span class="meta" id="progress">starting…</span>
    <div class="viewtoggle">
      <button id="btnSec" class="on">Sections</button>
      <button id="btnTch">Teachers</button>
    </div>
    <button id="printbtn">Print / PDF</button>
  </div>
  <div id="semantic"></div>
  <div id="optbadge" class="meta" style="padding:0 2px;"></div>
  <div id="grid" class="grid"></div>
  <div class="note">
    <b>How to read the score.</b> Every combination already satisfies <b>all</b> hard rules (faculty constraints,
    no subject twice a day, no teacher double-booked, Accounting-vs-Economics non-overriding, the parallel
    Economics/Statistics block, …). The score only ranks the <b>soft "don't shuffle" preference</b>: for each subject we
    count how many different period-slots it uses across the week minus one, and multiply by its weekly weight
    (5/wk → 100,000 · 4/wk → 10,000 · 3/wk → 100 · 2/wk → 10). Lower = closer to "every subject stays in one slot".
    The proven minimum is <b>560</b>; this live solver typically lands at 570–580.
    <details><summary>More notes</summary>
      Break sits between Period-3 and Period-4 (10:30–10:55). In <b>ICS-II (Section-B)</b>, "Economics / Statistics" is an
      either/or option block — students take one of the two, taught in parallel rooms by Prof. Naeem Asghar (Economics) and
      Prof. Ishfaq Ahmed (Statistics) at the same time. Visiting-1/2/3 are placeholder labels for visiting faculty, exactly
      as in the allocation sheet. Use the <b>Teachers</b> view to check any faculty member's weekly schedule against their
      personal constraints. The <b>combination chooser</b> lists every generated solution with its rank, score, and a plain-language
      description of where it stands (near-optimal, good, …); the panel above the grids repeats this with a percentile.
      If a CP-SAT backend is configured (<code>API_URL</code>), the <b>“Compute optimal (CP-SAT)”</b> button fetches the
      provably-optimal set (score 560) from Cloud Run and merges it into the ranking.
    </details>
  </div>
</div>
<footer>Runs entirely in your browser · 11 sections · 25 periods/week per section · generated live by the solver in <code>solver.js</code>.</footer>
<script>
__SOLVER__
</script>
<script>
__APP__
</script>
</body>
</html>
"""

def main():
    solver = io.open("solver.js", encoding="utf-8").read()
    app = io.open("app.js", encoding="utf-8").read()
    html = HEAD.replace("__SOLVER__", solver).replace("__APP__", app)
    io.open("index.html", "w", encoding="utf-8").write(html)
    print("wrote index.html (", len(html), "bytes )")

if __name__ == "__main__":
    main()
