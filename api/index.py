"""Vercel serverless entry point for the IMPCC CP-SAT backend + frontend host.

Serves:
  GET  /            → the frontend (index.html)
  GET  /solver.js   → the in-browser solver script
  GET  /health      → liveness
  POST /generate    → CP-SAT solve (ranked, valid timetables)
  GET  /docs        → Swagger UI

The solver modules (cp_solver.py, solver.py) and the static assets (index.html,
solver.js) live at the repo root and are bundled into this function via
`includeFiles` in vercel.json.
"""
import os
import sys
import time
import pathlib

# Make the repo root importable (parent of api/) so cp_solver / solver resolve.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Header, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

import cp_solver as CS
import llm_translate
import auth_check
import solver as _solver_mod
from solver import UNITS, SECTIONS, TEACHER_FULL, DEFAULT_CONSTRAINTS

app = FastAPI(
    title="IMPCC Timetable Generator API",
    description="CP-SAT solver for IMPCC (H-8/4) Inter 1st-shift timetables (ICS & I.Com).",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _find_root() -> pathlib.Path:
    """Locate the directory holding index.html / solver.js (robust to bundling)."""
    here = pathlib.Path(__file__).resolve()
    candidates = [
        here.parent.parent,   # api/.. = project root
        here.parent,          # api/ (if assets were copied alongside)
        pathlib.Path.cwd(),
    ]
    for c in candidates:
        if (c / "index.html").exists() or (c / "solver.js").exists():
            return c
    return here.parent.parent


@app.get("/", include_in_schema=False)
def home():
    root = _find_root()
    index = root / "index.html"
    if index.exists():
        return FileResponse(index, media_type="text/html")
    return JSONResponse({"ok": True, "service": "impcc-timetable-generator",
                         "hint": "frontend assets not bundled"}, status_code=404)


@app.get("/solver.js", include_in_schema=False)
def solver_js():
    root = _find_root()
    f = root / "solver.js"
    if f.exists():
        return FileResponse(f, media_type="application/javascript")
    return JSONResponse({"detail": "solver.js not found"}, status_code=404)


@app.get("/data.js", include_in_schema=False)
def data_js():
    """The canonical dataset (browser-loadable form of data/canonical.json)."""
    root = _find_root()
    f = root / "data.js"
    if f.exists():
        return FileResponse(f, media_type="application/javascript")
    return JSONResponse({"detail": "data.js not found"}, status_code=404)


@app.get("/canonical.js", include_in_schema=False)
def canonical_js():
    """The canonical model adapter (IMPCC_CANONICAL)."""
    root = _find_root()
    f = root / "canonical.js"
    if f.exists():
        return FileResponse(f, media_type="application/javascript")
    return JSONResponse({"detail": "canonical.js not found"}, status_code=404)


@app.get("/context_solver.js", include_in_schema=False)
def context_solver_js():
    """The in-browser context solver (IMPCC_CONTEXT_SOLVER)."""
    root = _find_root()
    f = root / "context_solver.js"
    if f.exists():
        return FileResponse(f, media_type="application/javascript")
    return JSONResponse({"detail": "context_solver.js not found"}, status_code=404)


@app.get("/supabase.js", include_in_schema=False)
def supabase_js():
    root = _find_root()
    f = root / "supabase.js"
    if f.exists():
        return FileResponse(f, media_type="application/javascript")
    return JSONResponse({"detail": "supabase.js not found"}, status_code=404)


@app.get("/populations.js", include_in_schema=False)
def populations_js():
    """The population/schedule domain model (IMPCC_POPULATIONS)."""
    root = _find_root()
    f = root / "populations.js"
    if f.exists():
        return FileResponse(f, media_type="application/javascript")
    return JSONResponse({"detail": "populations.js not found"}, status_code=404)




def require_user(authorization: str = Header(default="")):
    """Reject the request unless it carries a valid Supabase session token."""
    token = ""
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    user = auth_check.verify_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    return user

class GenerateRequest(BaseModel):
    # Vercel Hobby gives 1 vCPU + a 300s cap, so defaults are tuned for that:
    # 20s reliably returns the best-known 560 without needing a 45s prove-optimal run.
    time_limit: int = Field(default=45, ge=1, le=300,
                            description="seconds per CP-SAT seed (45s returns best 560; ~120s proves optimality)")
    n_seeds: int = Field(default=1, ge=1, le=4,
                         description="number of randomized optimization seeds")
    max_solutions: int = Field(default=0, ge=0,
                               description="cap on returned solutions (0 = no cap)")
    days: int = Field(default=5, ge=1, le=6,
                      description="ACTIVE day count (capacity 6 = Mon-Sat; default Mon-Fri)")
    periods: int = Field(default=5, ge=1, le=8,
                         description="ACTIVE periods per day (capacity 8; default 5)")
    constraints: dict = Field(default=None,
                              description="optional faculty-constraint overrides (see constraints_schema.md)")
    sections: dict = Field(default=None,
                           description="optional course-allocation overrides (section -> subjects)")


class TranslateRequest(BaseModel):
    text: str = Field(..., description="the natural-language constraint statement")
    teacher: str = Field(default=None, description="optional faculty member name")


def grids_to_dict(grids):
    out = {}
    for sec in SECTIONS:
        g = grids[sec["key"]]
        rows = []
        for d in range(5):
            row = []
            for s in range(5):
                u = UNITS[g[d][s]]
                row.append([u["subject"], TEACHER_FULL.get(u["teacher"], u["teacher"])])
            rows.append(row)
        out[sec["key"]] = rows
    return out


@app.get("/health")
def health():
    return {"ok": True, "service": "impcc-timetable-generator", "solver": "cp-sat"}


@app.get("/constraints")
def constraints():
    """Return the default faculty constraints (the 'system language' data)."""
    return {"defaults": DEFAULT_CONSTRAINTS, "schema_url": "/constraints"}


@app.post("/translate")
def translate(req: TranslateRequest, user: dict = Depends(require_user)):
    """Translate a natural-language constraint into the system schema via the LLM."""
    if not (req.text or "").strip():
        return {"error": "text is required"}
    result = llm_translate.translate_constraints(req.text.strip(), req.teacher)
    return result


class GITranslateRequest(BaseModel):
    text: str = Field(..., description="the plain-language general instruction")
    population: str = Field(default=None, description="optional population context (inter-1/bs-1/inter-2)")


@app.post("/translate-gi")
def translate_gi(req: GITranslateRequest, user: dict = Depends(require_user)):
    """Translate a plain-language GENERAL instruction into the structured GI schema."""
    if not (req.text or "").strip():
        return {"error": "text is required"}
    return llm_translate.translate_general_instruction(req.text.strip())


class TweakTranslateRequest(BaseModel):
    text: str = Field(..., description="the plain-language tweak statement")


@app.post("/translate-tweak")
def translate_tweak(req: TweakTranslateRequest, user: dict = Depends(require_user)):
    """Translate a plain-language tweak (leave, lab closed, …) into the tweak schema."""
    if not (req.text or "").strip():
        return {"error": "text is required"}
    return llm_translate.translate_tweak(req.text.strip())


@app.post("/generate")
def generate(req: GenerateRequest, user: dict = Depends(require_user)):
    t0 = time.time()
    ranked, any_optimal = CS.generate_ranked(
        n_seeds=req.n_seeds,
        time_per_seed=req.time_limit,
        max_solutions=req.max_solutions,
        constraints=req.constraints,
        sections=req.sections,
        days=req.days,
        periods=req.periods,
    )
    solutions = []
    for sc, g in ranked:
        solutions.append({"score": sc, "timetable": grids_to_dict(g)})

    return {
        "solver": "cp-sat",
        "solutions": solutions,
        "total_found": len(ranked),
        "optimal": any_optimal,
        "best_score": ranked[0][0] if ranked else None,
        "worst_score": ranked[-1][0] if ranked else None,
        "elapsed_seconds": round(time.time() - t0, 2),
        "meta": {
            "days": _solver_mod.DAYS,
            "slots": _solver_mod.SLOTS,
            "section_order": [s["key"] for s in SECTIONS],
        },
    }


_SCORE_REF_CACHE = {}


def _canon_fingerprint():
    """Fingerprint of the shipped canonical dataset (score references are
    derived from it — the fingerprint guards stale baked/cache entries)."""
    import hashlib
    import canonical as _canon
    try:
        with open(_canon._DEFAULT_PATH, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:16]
    except Exception:
        return "unknown"


@app.get("/score-references")
def score_references():
    """Per-population STANDALONE best-known figures for the fairness
    scorecard: each population solved ALONE by CP-SAT (no cross-population
    coupling), so combinations can show "95% of Inter's standalone best"
    per side. Public read; results fingerprinted to the canonical dataset,
    preferring the file baked at deploy time over live compute."""
    import json as _j
    import time as _time
    import timetable_config as TC

    fp = _canon_fingerprint()
    if _SCORE_REF_CACHE.get("fingerprint") == fp:
        return _SCORE_REF_CACHE["payload"]
    baked = _find_root() / "data" / "score_references.json"
    if baked.exists():
        try:
            doc = _j.loads(baked.read_text(encoding="utf-8"))
            if doc.get("fingerprint") == fp:
                doc["source"] = "baked"
                _SCORE_REF_CACHE["fingerprint"] = fp
                _SCORE_REF_CACHE["payload"] = doc
                return doc
        except Exception:
            pass
    t0 = _time.time()
    refs = {}
    for pid in TC.POPULATIONS.keys():
        try:
            r = CS.standalone_reference(pid, time_per_seed=25, n_seeds=1)
        except Exception:
            r = None
        if r:
            refs[pid] = r
    doc = {"fingerprint": fp, "computedAt": _time.strftime("%Y-%m-%d %H:%M UTC", _time.gmtime()),
           "references": refs, "elapsedSeconds": round(_time.time() - t0, 2), "source": "live"}
    _SCORE_REF_CACHE["fingerprint"] = fp
    _SCORE_REF_CACHE["payload"] = doc
    return doc


@app.get("/populations")
def populations():
    """The timetable population registry + schedule configurations (domain model)."""
    import timetable_config as TC
    return {
        "capacity": TC.CAPACITY,
        "populations": {
            pid: {"label": p["label"], "short": p["short"], "shift": p["shift"],
                  "level": p["level"], "config": p["config"]}
            for pid, p in TC.POPULATIONS.items()
        },
    }


class GenerateContextRequest(BaseModel):
    """Solve a full shift context (multi-population) from the canonical dataset."""
    populations: list = Field(default=["inter-1", "bs-1"],
                              description="populations to solve jointly — shift 1: ['inter-1','bs-1']; shift 2: ['inter-2']")
    time_limit: int = Field(default=45, ge=1, le=300, description="seconds per CP-SAT seed")
    n_seeds: int = Field(default=1, ge=1, le=4, description="randomized seeds")
    max_solutions: int = Field(default=0, ge=0, description="cap on returned solutions (0 = no cap)")


def _grids_to_dict_ctx(grids, model):
    """Context grids -> per-section [subject, teacher] cells (course names per
    section; parallel groups render 'A / B')."""
    import canonical as _canon
    units = {u["id"]: u for u in model["units"]}
    out = {}
    for section in model["sections"]:
        key = section["key"]
        g = grids.get(key)
        rows = []
        for d in range(len(g)):
            row = []
            for s in range(len(g[d])):
                uid = g[d][s]
                if uid is None:
                    row.append(["Library Work", ""])
                    continue
                u = units[uid]
                cname = u["courseBySec"].get(key) or list(u["courseBySec"].values())[0]
                if u["group"]:
                    tnames = " / ".join(_canon.display_name(t) for t in u["members"])
                else:
                    tnames = _canon.display_name(u["teacher"])
                row.append([cname, tnames])
            rows.append(row)
        out[key] = rows
    return out


@app.post("/generate-context")
def generate_context(req: GenerateContextRequest, user: dict = Depends(require_user)):
    """Solve a shift context (Inter-1st + BS jointly, or Inter-2nd) from the
    canonical dataset. Solutions carry documented soft-constraint violations."""
    import time as _time
    import canonical as _canon
    import cp_solver as _cs
    import context_model as _cm
    t0 = _time.time()
    try:
        ctx = _canon.solver_context(req.populations)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    ranked, any_optimal = _cs.generate_context(
        ctx, n_seeds=req.n_seeds, time_per_seed=req.time_limit,
        max_solutions=req.max_solutions)
    model = _cm.context_to_model(ctx)
    solutions = [{
        "score": r["score"], "penalty": r["penalty"], "total": r["total"],
        "violations": r["violations"],
        "timetable": _grids_to_dict_ctx(r["grids"], model),
    } for r in ranked]
    return {
        "solver": "cp-sat-context",
        "populations": req.populations,
        "solutions": solutions,
        "total_found": len(solutions),
        "optimal": any_optimal,
        "best_score": solutions[0]["score"] if solutions else None,
        "best_total": solutions[0]["total"] if solutions else None,
        "elapsed_seconds": round(_time.time() - t0, 2),
        "meta": {
            "days": _solver_mod.DAYS, "slots": _solver_mod.SLOTS,
            "section_order": [s["key"] for s in model["sections"]],
        },
    }


# ------------------------------------------------------------------ manual build
class ManualAnalyzeRequest(BaseModel):
    """A manually-entered shift timetable to check ('insights from timetable')."""
    populations: list = Field(default=["inter-1", "bs-1"],
                              description="shift context — shift 1: ['inter-1','bs-1']; shift 2: ['inter-2']")
    timetable: dict = Field(default=None,
                            description="{section: dayRows[[subject, teacher]]} display cells")


class ManualRepairRequest(BaseModel):
    """Targeted repair request for one insight card (or all like it)."""
    populations: list = Field(default=["inter-1", "bs-1"])
    timetable: dict = Field(default=None)
    focus: dict = Field(default=None,
                        description='{"kind":"hard"|"soft","index":int} — the insight card; null repairs all')
    mode: str = Field(default="instance", description="instance = this card only; type = all cards of its kind")
    time_per_tier: int = Field(default=12, ge=1, le=60,
                               description="CP-SAT seconds per repair tier (strict → local → open)")


def _manual_ctx(populations):
    import canonical as _canon
    try:
        return _canon.solver_context(populations)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _check_manual_body(tt):
    if not isinstance(tt, dict):
        raise HTTPException(status_code=400, detail="timetable must be an object {section: dayRows}")
    import json as _j
    try:
        size = len(_j.dumps(tt))
    except Exception:
        raise HTTPException(status_code=400, detail="timetable payload is not JSON-serializable")
    if size > 256 * 1024:
        raise HTTPException(status_code=413, detail="timetable payload too large")


@app.get("/manual-template")
def manual_template(populations: str = "inter-1,bs-1", user: dict = Depends(require_user)):
    """The Manual Build vocabulary: per-section entry options (subjects + their
    teachers, weekly period counts), schedule config and off-days — everything
    the in-browser picker grid needs, straight from the canonical dataset."""
    import context_model as _cm
    pops = [p.strip() for p in populations.split(",") if p.strip()]
    ctx = _manual_ctx(pops)
    vocab = _cm.manual_vocabulary(ctx)
    return {
        "populations": pops,
        "sections": {k: {"level": v["level"], "offDays": v["offDays"],
                         "firstLast": v["firstLast"], "options": v["options"]}
                     for k, v in vocab.items()},
    }


@app.post("/manual-analyze")
def manual_analyze(req: ManualAnalyzeRequest, user: dict = Depends(require_user)):
    """Check a manually-entered shift timetable and return structured insights
    (hard issues + soft violations) with focus metadata for targeted repair."""
    import time as _time
    import context_model as _cm
    t0 = _time.time()
    ctx = _manual_ctx(req.populations)
    _check_manual_body(req.timetable)
    model = _cm.context_to_model(ctx)
    grids, unmatched = _cm.placements_from_display(req.timetable or {}, model)
    ev = _cm.analyze_structured(grids, model)
    return {
        "issues": ev["issues"],
        "issues_detail": ev["issues_detail"],
        "violations": ev["violations"],
        "penalty": ev["penalty"],
        "score": _cm.shuffle_score(grids, model),
        "total": _cm.shuffle_score(grids, model) + ev["penalty"],
        "unmatched": unmatched,
        "elapsed_seconds": round(_time.time() - t0, 2),
    }


@app.post("/manual-repair")
def manual_repair(req: ManualRepairRequest, user: dict = Depends(require_user)):
    """Fix one insight (or all of its kind) with a minimal-diff CP-SAT repair:
    every uninvolved cell stays where the admin put it; only the implicated
    units (and, escalating through tiers, their neighbourhood) may move."""
    import cp_solver as _cs
    ctx = _manual_ctx(req.populations)
    _check_manual_body(req.timetable)
    mode = (req.mode or "instance").lower()
    if mode not in ("instance", "type"):
        raise HTTPException(status_code=400, detail="mode must be 'instance' or 'type'")
    result = _cs.repair_context(
        ctx, req.timetable or {}, focus=req.focus, mode=mode,
        time_per_tier=req.time_per_tier)
    if not result.get("ok"):
        raise HTTPException(status_code=422, detail={
            "reason": result.get("reason"),
            "issues_before": result.get("issues_before"),
            "penalty_before": result.get("penalty_before"),
            "violations_before": result.get("violations_before"),
        })
    return result
