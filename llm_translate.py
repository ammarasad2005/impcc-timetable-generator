"""Natural-language → constraint-schema translation via an OpenAI-compatible LLM.

The LLM key lives server-side (env vars), never in the browser:
  LLM_API_KEY   (required)  — e.g. an OpenAI/Groq/OpenRouter key
  LLM_BASE_URL  (optional)  — default https://openrouter.ai/api/v1
  LLM_MODEL     (optional)  — default google/gemma-4-26b-a4b-it:free

See constraints_schema.md for the schema this translates into.
"""
import json
import os
import re
from urllib import request as urlreq
from urllib.error import HTTPError, URLError

SLOTS = ["P1", "P2", "P3", "P4", "P5"]
DAYS = ["MON", "TUE", "WED", "THU", "FRI"]
STREAMS = ["I.COM", "ICS"]

# rule keys we accept (and their expected value shape) — used for validation
# rule keys we accept (and their expected value shape) — DRIVEN BY
# personal_constraints_model.md (taxonomy v2). Keep 1:1 with the spec's
# "kind" column; anything else is dropped with a warning so the LLM cannot
# smuggle ambiguous keys into the engine.
RULE_SPEC = {
    # ---- legacy + v2 hard masks
    "allowed_slots": list,             # ["P1","P2"]
    "forbidden_slots": list,           # ["P5"]
    "allowed_days": list,              # ["THU","FRI"]
    "forbidden_days": list,            # ["FRI"]
    "allowed_slots_days": list,        # [{days?, slots}] ONLY-IN window (union across entries)
    "allowed_slots_in_sections": list, # [{sections:[...], slots:[...], days?}]
    "allowed_days_in_sections": list,  # [{sections:[...], days:[...]}]
    "allowed_sections": list,          # [section keys] — teach ONLY these
    "forbidden_sections": list,        # [section keys] — never these
    "forbidden_slots_on_days": list,   # [{days:[...], slots:[...]}]
    "allowed_slots_in_stream": list,   # [{stream, slots, days?}]
    "allowed_days_in_stream": list,    # [{stream, days}]
    "stream_forbidden_days": list,     # [{stream, days}]
    # ---- subject pins
    "subject_slots": list,             # [{subject, slots, days?}]
    "subject_forbidden_days": list,    # [{subject, days}]
    "subject_days_allowed": list,      # [{subject, days}] — ONLY these days
    "subject_slot_days": list,         # [{subject, slot, days}] (legacy singular)
    "subject_slots_days": list,        # [{subject, slots, days}] (plural window)
    # ---- engagement counts
    "min_days_in_slot": list,          # [{slot, min_days, days?, scope?}]
    "max_days_in_slot": list,          # [{slot, max_days, days?, scope?}]
    "min_days_engaged": int,
    "max_periods_per_day": "int_or_list",  # int OR [{max, days?, stream?, sections?, scope?}]
    "min_periods_per_day": "int_or_list",  # int OR [{min, ...}] (only on engaged days)
    "stream_slots_required": list,     # [{stream, slots, min_days?, days?}]
    # ---- distribution quotas
    "max_pieces_match": list,          # [{max, subject?, subjects?, stream?, sections?, slot?, days?, scope?}]
    "min_pieces_match": list,          # [{min, ...}]
    # ---- structure
    "no_daily_gaps": bool,             # no free holes inside a teaching day
    # ---- soft preferences
    "soft_prefer_free_slots": list,        # ["P3"]
    "soft_prefer_free_slots_days": list,   # [{days, slots}]
    "soft_even_distribution": bool,
    "soft_compact_days": bool,
    # ---- personal exception
    "allow_same_subject_same_day": bool,
}
# per-entry scope object (may sit on ANY list-entry; absent = applies everywhere)
SCOPE_KEYS = ("populations", "streams", "sections", "days")

SYSTEM_PROMPT = """You translate a faculty member's natural-language timetable constraints into strict JSON.

VOCABULARY
- Period slots (use EXACTLY these tokens): P1 P2 P3 P4 P5  (P1 = first period, P5 = last period).
- Days (use EXACTLY these tokens): MON TUE WED THU FRI.
- Streams (use EXACTLY these tokens): "I.COM" or "ICS".

OUTPUT — return ONLY a JSON object, no markdown fences, with exactly this shape:
{
  "teacher": "<name, or null if not identifiable>",
  "natural": "<the original statement, verbatim>",
  "rules": { ... },
  "confidence": 0.0,
  "unmapped": ["<anything you could not express>"],
  "notes": "<one short sentence explaining your interpretation>"
}

RULES — deterministic kind table (personal_constraints_model.md v2). Use ONLY these keys; anything that does not map mechanically to a row goes into "unmapped" — NEVER invent keys.

HARD availability masks:
- "allowed_slots": ["P1","P2"]            → ONLY these periods, week-wide.
- "forbidden_slots": ["P5"]               → never these periods ("never the last period").
- "allowed_days": ["THU","FRI"]           → ONLY these days.
- "forbidden_days": ["FRI"]               → never these days.
- "forbidden_slots_on_days": [{"days":["MON"],"slots":["P1","P2"]}] → never these day×period windows.
- "allowed_slots_days": [{"days":["FRI"],"slots":["P3","P4","P5"]}] → ONLY these day×period windows (union across entries; combos not listed are off-limits). "Use only 3rd–5th periods on Fridays" / "arrange his 3,4,5 periods on Fri".
- "allowed_slots_in_stream": [{"stream":"I.COM","slots":["P1","P2","P3"],"days":optional}] → within that stream ONLY these periods (whole week unless "days" given).
- "allowed_days_in_stream": [{"stream":"I.COM","days":["THU","FRI"]}] → within that stream ONLY these days.
- "stream_forbidden_days": [{"stream":"I.COM","days":["FRI"]}] → never these days within that stream.
- "allowed_slots_in_sections": [{"sections":["ICS-II-A"],"slots":["P3","P4","P5"],"days":optional}] → in these sections ONLY these periods.
- "allowed_days_in_sections": [{"sections":["BSAF-SEM-I"],"days":["MON","TUE"]}] → in these sections ONLY these days.
- "allowed_sections": ["ICS-II-A","ICS-II-B"] → may teach ONLY these sections.
- "forbidden_sections": ["I.COM-I-A"] → may never teach these sections.
- "subject_slots": [{"subject":"Business Mathematics","slots":["P3"],"days":optional}] → that subject in these periods only (week-wide unless days given).
- "subject_forbidden_days": [{"subject":"Principles of Economics","days":["FRI"]}] → subject never on those days.
- "subject_days_allowed": [{"subject":"Principles of Economics","days":["MON","TUE","WED"]}] → subject ONLY those days.
- "subject_slot_days": [{"subject":"...","slot":"P3","days":["MON","TUE"]}] → subject pinned to one period on days (legacy form, still accepted).
- "subject_slots_days": [{"subject":"...","slots":["P3","P4"],"days":["MON","TUE"]}] → subject ONLY these day×period windows.

Counts:
- "min_days_engaged": 5 → teach on at least N distinct days ("no day completely off" → 5).
- "min_days_in_slot": [{"slot":"P1","min_days":4}] → occupy the period ≥N distinct days.
- "max_days_in_slot": [{"slot":"P5","max_days":2}] → occupy the period ≤N distinct days ("last period at most 2 days a week").
- "max_periods_per_day": 3 — OR scoped entries [{"max":2,"days":["FRI"],"stream":"ICS","sections":optional}] → ≤N scoped periods in one day.
- "min_periods_per_day": 2 — OR [{"min":2,...}] → ≥N scoped periods on any day he actually teaches (never forces an empty day).
- "stream_slots_required": [{"stream":"ICS","slots":["P1","P2"],"min_days":optional}] → each listed period occupied in that stream (default ≥4 days).
- "max_pieces_match": [{"max":2,"subject":"Principles of Economics","stream":"I.COM"}] → QUOTA: ≤N matching pieces per week; matchers any of subject/subjects/stream/sections/slot/days.
- "min_pieces_match": [{"min":3,"stream":"ICS"}] → QUOTA: ≥N matching pieces per week.

Structure:
- "no_daily_gaps": true → per teaching day, occupied periods form one contiguous run.
- "allow_same_subject_same_day": true → personal exception: his same-subject classes MAY double on one day (overrides the inter no-double rule for his units only).

SOFT preferences (penalized, never forbidden — only when the statement says prefer / as-much-as-possible / when possible):
- "soft_prefer_free_slots": ["P3"] → prefer these periods free.
- "soft_prefer_free_slots_days": [{"days":["FRI"],"slots":["P5"]}] → windowed prefer-free.
- "soft_even_distribution": true → spread his load evenly across the week.
- "soft_compact_days": true → prefer no gaps inside a teaching day.

SCOPE — every LIST entry may carry "scope": {"populations":["inter-1"],"streams":["ICS"],"sections":["ICS-II-A"],"days":["MON"]} when the statement restricts WHERE the rule applies ("…but only for his BS sections", "…only on Fridays"). Omit scope when it applies everywhere.

MAPPING RULES (synonyms → canonical keys)
- "free", "off", "should not / must not / cannot take" → forbidden family.
- "only", "can only", "available only" → allowed family (slots / days / day×period windows — pick the row matching what is restricted).
- "no day off", "every day" → min_days_engaged.
- "engaged / must take / at least N days" + period → min_days_in_slot; "at most N days" + period → max_days_in_slot.
- "never more than N periods <where> in a day" → max_periods_per_day (scoped entry when restricted to a stream/section/days).
- "at least N <where> periods on any teaching day" → min_periods_per_day.
- "at most / at least N of his <subject/stream/sections> classes" → max_pieces_match / min_pieces_match quotas.
- "arrange periods P.. only in <streams/sections>" (optionally with days) → allowed_slots_in_stream / allowed_slots_in_sections; day×period combos week-wide or day-listed → allowed_slots_days.
- "<subject> on P<n> on <days>" → subject_slots_days (plural) or subject_slot_days (single period).
- stream words + "must engage/fill" → stream_slots_required; "only these periods" → allowed_slots_in_stream.
- "as much as possible", "preferably", "if possible" → the soft_* twin (soft_prefer_free_slots(_days), soft_compact_days, soft_even_distribution) — NEVER the hard forbiddens.
- "no gaps between my periods within a day" → no_daily_gaps; "…as much as possible" → soft_compact_days.
- "first period" = P1, "last period" = P5. "after break" = P4 or P5 (pick the more specific reading).
- A subject name MUST be kept verbatim from the catalog (e.g. "Business Mathematics", "Principles of Accounting").


MAPPING RULES (synonyms → canonical keys)
- "free", "off", "should not teach", "must not teach", "cannot take" → forbidden.
- "only", "can only come", "available only" → allowed_*.
- "no day off", "every day", "daily" → min_days_engaged 5.
- "engaged", "must take", "should take" + a period number + a day count → min_days_in_slot.
- stream words ("in I.Com", "in ICS", "for ICS") + period list → stream_slots_required when "must engage/fill", else allowed_slots_in_stream.
- stream words + day list ("on Thursday and Friday") → allowed_days_in_stream.
- "as much as possible", "preferably", "if possible" + period list → soft_prefer_free_slots (SOFT — never forbidden_slots).
- "evenly distribute", "spread over the week" → soft_even_distribution (SOFT).
- "two consecutive classes for the same subject can be set on the same day", "doubles allowed" (about one teacher) → allow_same_subject_same_day.
- "<subject> on P<n> on <days>" / "engage P<n> in <subject> on <days>" → subject_slot_days.
- "first period" = P1, "last period" = P5.
- "after break" = P4 or P5; ask yourself which fits, prefer the more specific reading.
- A subject name should be kept verbatim (e.g. "Business Mathematics", "Principles of Accounting").

RULES OF CONDUCT
1. If a statement conflicts with itself, choose the more restrictive reading and note it.
2. If something is un-expressible (e.g. "wants a window seat"), put it in "unmapped", not in rules.
3. confidence reflects how sure you are (0.9+ for clear mechanical rules, lower for guesses).
4. Return valid JSON only. Do not invent rule keys.

EXAMPLES

Input: "He can only come on Thursday and Friday, in the first three periods."
Output: {"teacher":null,"natural":"He can only come on Thursday and Friday, in the first three periods.","rules":{"allowed_days":["THU","FRI"],"allowed_slots":["P1","P2","P3"]},"confidence":0.97,"unmapped":[],"notes":"Interpreted 'first three periods' as P1-P3."}

Input: "1st period must be engaged 4 days a week, last period must be free, no day must be completely off."
Output: {"teacher":null,"natural":"1st period must be engaged 4 days a week, last period must be free, no day must be completely off.","rules":{"min_days_in_slot":[{"slot":"P1","min_days":4}],"forbidden_slots":["P5"],"min_days_engaged":5},"confidence":0.95,"unmapped":[],"notes":"'No day completely off' mapped to min_days_engaged 5."}

Input: "Monday first two periods free, and I prefer not to teach on Friday."
Output: {"teacher":null,"natural":"Monday first two periods free, and I prefer not to teach on Friday.","rules":{"forbidden_slots_on_days":[{"days":["MON"],"slots":["P1","P2"]}],"forbidden_days":["FRI"]},"confidence":0.9,"unmapped":[],"notes":"'Prefer' treated as a hard constraint."}
"""


def _valid_scope(scope):
    """scope object: populations/streams/sections/days lists (days checked
    against the vocabulary). Empty/absent keys are ignored."""
    if not isinstance(scope, dict):
        return False
    for k, v in scope.items():
        if k not in SCOPE_KEYS or not isinstance(v, list):
            return False
        if k == "days" and any(d not in DAYS and d != "SAT" for d in v):
            return False
    return True


def _entries(val):
    return val if isinstance(val, list) else []


def _entry_ok(e, need=(), opt=()):
    if not isinstance(e, dict):
        return False
    for f in need:
        if f not in e:
            return False
    if "scope" in e and not _valid_scope(e["scope"]):
        return False
    if "days" in e and any(d not in DAYS and d != "SAT" for d in _entries(e["days"])):
        return False
    return True


def _slots_of(e, field="slots"):
    return all(s in SLOTS for s in _entries(e.get(field)))


def _validate_rules(rules):
    """Normalize + validate against RULE_SPEC (personal_constraints_model.md
    taxonomy v2); returns (clean_rules, errors, warnings). Unknown keys are
    dropped with a warning (never silently accepted); malformed entries are
    dropped with an error."""
    clean, errors, warnings = {}, [], []
    if not isinstance(rules, dict):
        return {}, ["rules must be an object"], []
    for key, val in rules.items():
        if key not in RULE_SPEC:
            warnings.append(f"ignored unknown key '{key}'")
            continue
        ok = True
        if key in ("allowed_slots", "forbidden_slots", "soft_prefer_free_slots"):
            ok = isinstance(val, list) and all(s in SLOTS for s in val)
        elif key in ("allowed_days", "forbidden_days"):
            ok = isinstance(val, list) and all(d in DAYS for d in val)
        elif key in ("allowed_sections", "forbidden_sections"):
            ok = isinstance(val, list) and all(isinstance(x, str) for x in val)
        elif key == "forbidden_slots_on_days":
            ok = all(_entry_ok(e, ("days", "slots")) and _slots_of(e) for e in _entries(val)) and isinstance(val, list)
        elif key == "allowed_slots_days":
            ok = isinstance(val, list) and all(_entry_ok(e, ("slots",)) and _slots_of(e) for e in val)
        elif key == "soft_prefer_free_slots_days":
            ok = isinstance(val, list) and all(_entry_ok(e, ("days", "slots")) and _slots_of(e) for e in val)
        elif key == "allowed_slots_in_sections":
            ok = isinstance(val, list) and all(_entry_ok(e, ("sections", "slots")) and _slots_of(e) for e in val)
        elif key == "allowed_days_in_sections":
            ok = isinstance(val, list) and all(_entry_ok(e, ("sections", "days")) for e in val)
        elif key == "allowed_slots_in_stream":
            ok = isinstance(val, list) and all(_entry_ok(e, ("stream", "slots"))
                                               and e.get("stream") in STREAMS and _slots_of(e) for e in val)
        elif key == "allowed_days_in_stream":
            ok = isinstance(val, list) and all(_entry_ok(e, ("stream", "days"))
                                               and e.get("stream") in STREAMS for e in val)
        elif key == "stream_forbidden_days":
            ok = isinstance(val, list) and all(_entry_ok(e, ("stream", "days"))
                                               and e.get("stream") in STREAMS for e in val)
        elif key == "stream_slots_required":
            ok = isinstance(val, list) and all(_entry_ok(e, ("stream", "slots"))
                                               and e.get("stream") in STREAMS and _slots_of(e) for e in val)
        elif key == "subject_slots":
            ok = isinstance(val, list) and all(_entry_ok(e, ("subject", "slots")) and _slots_of(e) for e in val)
        elif key == "subject_forbidden_days":
            ok = isinstance(val, list) and all(_entry_ok(e, ("subject", "days")) for e in val)
        elif key == "subject_days_allowed":
            ok = isinstance(val, list) and all(_entry_ok(e, ("subject", "days")) for e in val)
        elif key == "subject_slot_days":
            ok = isinstance(val, list) and all(_entry_ok(e, ("subject", "slot", "days"))
                                               and e.get("slot") in SLOTS for e in val)
        elif key == "subject_slots_days":
            ok = isinstance(val, list) and all(_entry_ok(e, ("subject", "slots", "days")) and _slots_of(e) for e in val)
        elif key == "min_days_in_slot":
            ok = isinstance(val, list) and all(_entry_ok(e, ("slot",))
                                               and e.get("slot") in SLOTS
                                               and isinstance(e.get("min_days"), (int, float)) for e in val)
        elif key == "max_days_in_slot":
            ok = isinstance(val, list) and all(_entry_ok(e, ("slot",))
                                               and e.get("slot") in SLOTS
                                               and isinstance(e.get("max_days"), (int, float)) for e in val)
        elif key == "min_days_engaged":
            ok = isinstance(val, int) and 1 <= val <= 6
        elif key in ("max_periods_per_day", "min_periods_per_day"):
            field = "max" if key.startswith("max") else "min"
            if isinstance(val, int):
                ok = 1 <= val <= 8
            else:
                ok = isinstance(val, list) and all(
                    _entry_ok(e) and isinstance(e.get(field), int) and 1 <= e[field] <= 8 for e in val)
        elif key in ("max_pieces_match", "min_pieces_match"):
            field = "max" if key.startswith("max") else "min"
            ok = isinstance(val, list) and all(
                _entry_ok(e) and isinstance(e.get(field), int)
                and (not e.get("slot") or e["slot"] in SLOTS)
                and (not e.get("stream") or e["stream"] in STREAMS)
                for e in val)
        elif key in ("no_daily_gaps", "soft_even_distribution", "soft_compact_days",
                     "allow_same_subject_same_day"):
            ok = isinstance(val, bool)
        if not ok:
            errors.append(f"bad shape for '{key}': {val!r}")
            continue
        clean[key] = val
    return clean, errors, warnings


def try_direct_expression(text, teacher=None):
    """Direct-expression route: an admin may paste the structured JSON itself
    instead of natural language. If the input parses as a rules payload it is
    validated locally and returned with confidence 1.0 — no LLM call at all.
    Returns None when the text is not a JSON payload (normal NL flow).
    Accepted shapes: {"rules": {...}} or a bare rules object
    ({"forbidden_slots": ["P5"], ...})."""
    t = (text or "").strip()
    if not (t.startswith("{") and t.endswith("}")):
        return None
    try:
        payload = json.loads(t)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    raw_rules = payload.get("rules") if isinstance(payload.get("rules"), dict) else (
        payload if any(k in RULE_SPEC for k in payload.keys()) else None)
    if raw_rules is None:
        return None
    clean, errs, warns = _validate_rules(raw_rules)
    note = "direct expression (validated locally, no LLM call)"
    if errs:
        return {"error": "invalid direct expression", "errors": errs, "warnings": warns,
                "rules": clean, "natural": payload.get("natural") or t,
                "teacher": teacher or payload.get("teacher") or None,
                "notes": note, "unmapped": errs}
    return {
        "teacher": teacher or payload.get("teacher") or None,
        "natural": payload.get("natural") or t,
        "rules": clean,
        "confidence": 1.0,
        "unmapped": payload.get("unmapped") or [],
        "notes": ("; ".join(warns) + " — " if warns else "") + note,
        "errors": [],
        "warnings": warns,
    }


def try_direct_gi_expression(text):
    """Direct-expression route for general instructions: {"type": ..., "params": {...}}.
    Validated locally, no LLM call. Returns None for non-JSON input."""
    t = (text or "").strip()
    if not (t.startswith("{") and t.endswith("}")):
        return None
    try:
        payload = json.loads(t)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or "type" not in payload:
        return None
    rtype = payload.get("type")
    if rtype not in GI_RULE_TYPES:
        return {"error": f"unknown rule type '{rtype}' in direct expression"}
    params = payload.get("params")
    if params is not None and not isinstance(params, dict):
        return {"error": "'params' must be an object in direct expression"}
    return {
        "type": rtype,
        "params": params or {},
        "natural": payload.get("natural") or t,
        "notes": "direct expression (validated locally, no LLM call)",
        "confidence": 1.0,
        "unmapped": [],
    }


def translate_constraints(text, teacher=None):
    """Call the LLM and return a normalized result dict (never raises)."""
    direct = try_direct_expression(text, teacher)
    if direct is not None:
        return direct
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        return {"error": "LLM not configured — set LLM_API_KEY on the backend"}

    base_url = os.environ.get("LLM_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    model = os.environ.get("LLM_MODEL", "google/gemma-4-26b-a4b-it:free")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": (f"Teacher name: {teacher}\n" if teacher else "")
                                    + f"Constraint statement: {text}"},
    ]
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": 0,
    }).encode()

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": os.environ.get("LLM_HTTP_REFERER", "https://impcc-timetable-generator.vercel.app"),
        "X-Title": os.environ.get("LLM_X_TITLE", "IMPCC Timetable Generator"),
    }
    req = urlreq.Request(
        f"{base_url}/chat/completions",
        data=payload,
        headers=headers,
    )
    try:
        with urlreq.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
    except HTTPError as e:
        return {"error": f"LLM HTTP {e.code}: {e.read().decode()[:300]}"}
    except URLError as e:
        return {"error": f"LLM unreachable: {e.reason}"}

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        return {"error": "LLM returned an unexpected shape"}

    # strip markdown fences if present
    content = re.sub(r"^```(json)?\s*|\s*```$", "", content.strip(), flags=re.MULTILINE).strip()
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return {"error": "LLM did not return valid JSON", "raw": content}

    if not isinstance(parsed, dict):
        return {"error": "LLM output was not an object", "raw": content}

    rules, errs, warns = _validate_rules(parsed.get("rules") or {})
    return {
        "teacher": parsed.get("teacher") or teacher or None,
        "natural": parsed.get("natural") or text,
        "rules": rules,
        "confidence": float(parsed.get("confidence") or 0),
        "unmapped": parsed.get("unmapped") or [],
        "notes": parsed.get("notes") or "",
        "errors": errs,
        "warnings": warns,
    }


TWEAK_SYSTEM_PROMPT = """You translate a college timetable adjustment (a "tweak") from plain language into strict JSON.

CONTEXT: Mon-Fri teaching, 5 periods a day (P1..P5). Tweaks are either temporary (a window) or permanent.

OUTPUT — return ONLY a JSON object, no markdown fences:
{
  "kind": "temporary" | "permanent",
  "window": { "type": "dates", "from": "YYYY-MM-DD", "to": "YYYY-MM-DD" },   // temporary only
  "recurring": false,                                   // true if it repeats EVERY week
  "effect": {
    "type": "suspend_teacher" | "suspend_teacher_slots" | "block_section_slots",
    "teacher": "Prof. …",        // for suspend_teacher / suspend_teacher_slots
    "section": "ICS-I-A",        // for block_section_slots (use section keys like I.COM-I-A, ICS-II-B)
    "slots": ["P1","P2"],        // optional; defaults to all P1-P5
    "days": ["MON","TUE"]        // optional; defaults to all Mon-Fri
  },
  "natural": "<verbatim statement>",
  "notes": "<one short interpretation note>",
  "confidence": 0.0,
  "unmapped": []
}

MAPPING RULES
- "X is on leave / absent / won't come / not available today" → kind temporary, effect.suspend_teacher, teacher=X, window today→today.
- "…tomorrow" → today+1 → today+1. "…this week" → this Monday → this Friday. "…on Thursday" → days:["THU"].
- "…only the first two periods on Friday" → suspend_teacher_slots, days:["FRI"], slots:["P1","P2"].
- "…every Wednesday P4" → recurring:true, suspend_teacher_slots, days:["WED"], slots:["P4"].
- "X has left / resigned / retired" → kind permanent, suspend_teacher.
- "lab / exam / no classes for section S" → block_section_slots with the section key.
- Resolve relative dates using the CURRENT DATE given below. Dates must be YYYY-MM-DD.
- If the statement isn't a schedule tweak, return empty effect and put it in unmapped.

CURRENT DATE: {today}

EXAMPLES
Input: "Prof. Naeem is on leave tomorrow"
Output: {"kind":"temporary","window":{"type":"dates","from":"{tomorrow}","to":"{tomorrow}"},"recurring":false,"effect":{"type":"suspend_teacher","teacher":"Prof. Muhammad Naeem"},"natural":"Prof. Naeem is on leave tomorrow","notes":"One-day absence.","confidence":0.95,"unmapped":[]}

Input: "Computer lab is closed this week"
Output: {"kind":"temporary","window":{"type":"dates","from":"{monday}","to":"{friday}"},"recurring":false,"effect":{"type":"block_section_slots","slots":["P1","P2","P3","P4","P5"]},"natural":"Computer lab is closed this week","notes":"Treated as blocking lab-based sections for the week (refine the section in review).","confidence":0.7,"unmapped":["exact sections using the lab"]}
"""


def translate_tweak(text):
    """Natural-language tweak -> structured tweak JSON via the LLM."""
    import datetime
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        return {"error": "LLM not configured — set LLM_API_KEY on the backend"}

    base_url = os.environ.get("LLM_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    model = os.environ.get("LLM_MODEL", "google/gemma-4-26b-a4b-it:free")

    today = datetime.date.today()
    def iso(d): return d.isoformat()
    tomorrow = today + datetime.timedelta(days=1)
    monday = today - datetime.timedelta(days=today.weekday())
    friday = monday + datetime.timedelta(days=4)

    prompt = TWEAK_SYSTEM_PROMPT.replace("{today}", iso(today)).replace("{tomorrow}", iso(tomorrow)) \
        .replace("{monday}", iso(monday)).replace("{friday}", iso(friday))

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": text.strip()},
    ]
    payload = json.dumps({"model": model, "messages": messages, "temperature": 0}).encode()
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + api_key,
        "HTTP-Referer": os.environ.get("LLM_HTTP_REFERER", "https://impcc-timetable-generator.vercel.app"),
        "X-Title": os.environ.get("LLM_X_TITLE", "IMPCC Timetable Generator"),
    }
    req = urlreq.Request(f"{base_url}/chat/completions", data=payload, headers=headers)
    try:
        with urlreq.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
    except HTTPError as e:
        return {"error": f"LLM HTTP {e.code}: {e.read().decode()[:300]}"}
    except URLError as e:
        return {"error": f"LLM unreachable: {e.reason}"}

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        return {"error": "LLM returned an unexpected shape"}

    content = re.sub(r"^```(json)?\s*|\s*```$", "", content.strip(), flags=re.MULTILINE).strip()
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return {"error": "LLM did not return valid JSON", "raw": content}

    if not isinstance(parsed, dict):
        return {"error": "LLM output was not an object", "raw": content}

    effect = parsed.get("effect") or {}
    eff_type = effect.get("type")
    if eff_type not in ("suspend_teacher", "suspend_teacher_slots", "block_section_slots"):
        eff_type = None
    def cln(x, pool): return [v for v in (x or []) if v in pool]
    slots = cln(effect.get("slots"), SLOTS)
    days = cln(effect.get("days"), DAYS)

    window = parsed.get("window") or {}
    kind = parsed.get("kind")
    if kind not in ("temporary", "permanent"):
        kind = "temporary"

    return {
        "kind": kind,
        "window": window if kind == "temporary" else None,
        "recurring": bool(parsed.get("recurring")),
        "effect": {
            "type": eff_type,
            "teacher": effect.get("teacher") or None,
            "section": effect.get("section") or None,
            "slots": slots or None,
            "days": days or None,
        },
        "natural": parsed.get("natural") or text.strip(),
        "notes": parsed.get("notes") or "",
        "confidence": float(parsed.get("confidence") or 0),
        "unmapped": parsed.get("unmapped") or [],
    }


# =====================================================================
# GENERAL-INSTRUCTION translation (NL -> structured GI rule)
# =====================================================================
GI_SYSTEM_PROMPT = """You translate a college's timetable GENERAL INSTRUCTION (institution-level rule) into strict JSON.

CONTEXT: 6-day capacity (MON-SAT), up to 8 periods/day (P1..P8). Populations: "inter-1" (Intermediate 1st shift), "bs-1" (BS departments 1st shift), "inter-2" (Intermediate 2nd shift). Sections look like "I.COM-I-A", "ICS-II-B", "BSAF-SEM-VII".

OUTPUT — return ONLY a JSON object, no markdown fences:
{
  "type": "<one of the rule types below>",
  "params": { ... },
  "natural": "<the original statement, verbatim>",
  "confidence": 0.0,
  "notes": "<one short interpretation note>",
  "unmapped": ["<anything you could not express>"]
}

RULE TYPES (use EXACTLY these):
- "no_same_subject_same_day" params {} — a subject may not appear twice in one day
- "same_subject_same_day_allowed" params {} — doubles ARE allowed (e.g. BS level)
- "avoid_shuffling" params {} — keep each subject in the same period slot across the week (soft)
- "non_overriding" params {"sections": ["I.COM-I-A",...], "subjects": ["Subject A", "Subject B"]} — each listed section must have a period of subject A where the OTHER sections do NOT have subject B
- "consecutive_days_for_2pw" params {} — subjects with 2 classes/week sit on consecutive days
- "subject_forbidden_days" params {"subject": "<name>", "days": ["FRI"], "scope": "I.COM"|"ICS"|null} — a subject must not be scheduled on those days (scope optional)
- "subject_forbidden_slots_on_days" params {"subject": "<name>", "days": ["FRI"], "slots": ["P4","P5"], "scope": "I.COM"|"ICS"|null} — a subject must not be scheduled in those SPECIFIC periods on those days (scope optional). Prefer this over a full-day ban whenever the statement mentions specific periods ("last two periods", "P1", "first period").
- "section_off_days" params {"sections": ["BSAF-SEM-VII",...], "days": ["FRI"]} — whole sections have no classes those days
- "first_last_period_occupied" params {"libraryWorkLabel": "Library Work"} — free boundary periods not allowed; free middle periods become library work
- "combined_classes" params {"groups": ["<id>"]} — co-taught section pairs at identical slots (admin links groups in the data)
- "soft_individual_spread" params {} — a teacher engaged in P1 should preferably be free in the last period (soft)

RULES OF CONDUCT
1. Institution-level only. If the statement is about ONE teacher's personal availability, refuse: {"error":"personal constraint — use the faculty constraints page"}.
2. Keep subject names VERBATIM from the statement.
3. Days tokens: MON TUE WED THU FRI SAT. Period tokens: P1..P8.
4. If a rule cannot be expressed, put it in "unmapped" and pick the closest type.
5. confidence 0.9+ for mechanical rules; lower for interpretation.

EXAMPLES
Input: "Friday must be free for 7th semesters of BS"
Output: {"type":"section_off_days","params":{"sections":["BSAF-SEM-VII","BSCM-SEM-VII","BBA-SEM-VII"],"days":["FRI"]},"natural":"Friday must be free for 7th semesters of BS","confidence":0.95,"notes":"All BS 7th-semester sections.","unmapped":[]}

Input: "Business Mathematics in I.Com must not be set on Friday"
Output: {"type":"subject_forbidden_days","params":{"subject":"Business Mathematics","days":["FRI"],"scope":"I.COM"},"natural":"Business Mathematics in I.Com must not be set on Friday","confidence":0.95,"notes":"Scoped to I.Com sections.","unmapped":[]}

Input: "Physics must not be scheduled in the last two periods on Friday"
Output: {"type":"subject_forbidden_slots_on_days","params":{"subject":"Physics","days":["FRI"],"slots":["P4","P5"],"scope":null},"natural":"Physics must not be scheduled in the last two periods on Friday","confidence":0.95,"notes":"Last two periods of a 5-period day are P4 and P5.","unmapped":[]}
"""

GI_RULE_TYPES = {
    "no_same_subject_same_day", "same_subject_same_day_allowed", "avoid_shuffling",
    "non_overriding", "consecutive_days_for_2pw", "subject_forbidden_days",
    "section_off_days", "first_last_period_occupied", "combined_classes",
    "soft_individual_spread", "subject_forbidden_slots_on_days",
}


def translate_general_instruction(text):
    """Natural-language general instruction -> structured GI rule via the LLM."""
    direct = try_direct_gi_expression(text)
    if direct is not None:
        return direct
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        return {"error": "LLM not configured — set LLM_API_KEY on the backend"}
    base_url = os.environ.get("LLM_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    model = os.environ.get("LLM_MODEL", "google/gemma-4-26b-a4b-it:free")
    messages = [
        {"role": "system", "content": GI_SYSTEM_PROMPT},
        {"role": "user", "content": text.strip()},
    ]
    payload = json.dumps({"model": model, "messages": messages, "temperature": 0}).encode()
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + api_key,
        "HTTP-Referer": os.environ.get("LLM_HTTP_REFERER", "https://impcc-timetable-generator.vercel.app"),
        "X-Title": os.environ.get("LLM_X_TITLE", "IMPCC Timetable Generator"),
    }
    req = urlreq.Request(f"{base_url}/chat/completions", data=payload, headers=headers)
    try:
        with urlreq.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
    except HTTPError as e:
        return {"error": f"LLM HTTP {e.code}: {e.read().decode()[:300]}"}
    except URLError as e:
        return {"error": f"LLM unreachable: {e.reason}"}
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        return {"error": "LLM returned an unexpected shape"}
    content = re.sub(r"^```(json)?\s*|\s*```$", "", content.strip(), flags=re.MULTILINE).strip()
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return {"error": "LLM did not return valid JSON", "raw": content}
    if not isinstance(parsed, dict):
        return {"error": "LLM output was not an object", "raw": content}
    if parsed.get("error"):
        return parsed
    rtype = parsed.get("type")
    if rtype not in GI_RULE_TYPES:
        return {"error": f"unknown rule type '{rtype}'", "raw": content}
    return {
        "type": rtype,
        "params": parsed.get("params") or {},
        "natural": parsed.get("natural") or text.strip(),
        "notes": parsed.get("notes") or "",
        "confidence": float(parsed.get("confidence") or 0),
        "unmapped": parsed.get("unmapped") or [],
    }

# =====================================================================
# DYNAMIC RULES — the self-extending ruleset
#
# Fixed kernel v1: forbid_cells — a HARD ban of matched unit pieces from
# (day x slot) cell windows, matched by subject / subjects / sections /
# teachers / stream scope. A dynamic rule DEFINITION is data only (never
# generated code); the authoring call proposes one, we validate it hard,
# and it enters the registry that ships on the publish channel.

DYN_KERNEL_KINDS = {"forbid_cells"}
_DYN_SLUG = re.compile(r"^[a-z][a-z0-9_]{2,39}$")
_DYN_LIST_LIMIT = 12
_DYN_PARAM_KEYS = {"subject", "subjects", "sections", "teachers", "stream",
                   "days", "slots", "libraryWorkLabel"}


def ruleset_context_md(registry):
    """The living ruleset document the authoring call reasons over: the
    kernel vocabulary + every dynamic rule currently registered."""
    lines = [
        "# IMPCC dynamic ruleset (kernel v1: forbid_cells)",
        "",
        "Enforcement kernel: forbid_cells — permanently BAN matched teaching units",
        "from every (day, slot) cell selected by the matchers. Matchers (all optional):",
        "subject | subjects[] | sections[] | teachers[] | stream (I.COM/ICS/BBA) |",
        "days[] (MON..SAT) | slots[] (P1..P8). Empty days/slots list means 'all'.",
        "Matchers combine with AND. A rule can only forbid cells, never schedule.",
        "",
        "Currently registered dynamic rules:",
    ]
    if not registry:
        lines.append("  (none yet)")
    for slug, d in sorted((registry or {}).items()):
        en = d.get("enforcement") or {}
        lst = sorted((en.get("matchers") or {}).keys())
        lines.append("- `%s` — %s%s" % (slug, d.get("label", slug),
                                        (" [matchers: " + ", ".join(lst) + "]") if lst else ""))
        if d.get("summary"):
            lines.append("    " + str(d["summary"]))
    return "\n".join(lines)


def validate_dyn_rule(defn, existing_ids=None):
    """Hard validation of an authored rule definition; returns a cleaned copy
    or None (caller rejects / falls back). Kernel kinds only, no code."""
    if not isinstance(defn, dict):
        return None
    rid = str(defn.get("id") or "").strip().lower()
    if not _DYN_SLUG.match(rid):
        return None
    if existing_ids and rid in set(existing_ids):
        return None
    if rid in GI_RULE_TYPES:
        return None
    label = str(defn.get("label") or "").strip()[:120]
    if not label:
        return None
    summary = str(defn.get("summary") or "").strip()[:400]
    params = defn.get("params_schema") or {}
    if not isinstance(params, dict) or len(params) > 6:
        return None
    for k in params:
        if str(k) not in _DYN_PARAM_KEYS:
            return None
    en = defn.get("enforcement") or {}
    if en.get("kind") not in DYN_KERNEL_KINDS:
        return None
    matchers = en.get("matchers") or {}
    if not isinstance(matchers, dict) or not matchers:
        return None
    clean_matchers = {}
    for k, v in matchers.items():
        if k not in ("subject", "subjects", "sections", "teachers", "stream", "days", "slots"):
            return None
        if k in ("subject", "stream"):
            if not isinstance(v, str) or not (0 < len(v) <= 48):
                return None
            clean_matchers[k] = v.upper() if k == "stream" else v
        else:
            if not isinstance(v, list) or not v or len(v) > _DYN_LIST_LIMIT:
                return None
            if not all(isinstance(x, str) and 0 < len(x) <= 48 for x in v):
                return None
            clean_matchers[k] = [x.upper() for x in v] if k in ("days", "slots") else list(v)
    return {"id": rid, "label": label, "summary": summary,
            "params_schema": {str(k): str(v)[:80] for k, v in params.items()},
            "enforcement": {"kind": en["kind"], "matchers": clean_matchers},
            "enabled": True, "authored": True}

_AUTHOR_PROMPT_LINES = [
    "You design ONE new scheduling rule for a school timetable solver.",
    "",
    "The constraint below does NOT match any existing rule type, so it needs a NEW",
    "rule definition that compiles onto the solver's fixed enforcement kernel.",
    "",
    "«ruleset»",
    "",
    "THE CONSTRAINT:",
    "«««detail»»»",
    "«context»",
    "",
    "Return ONLY a JSON object:",
    '  {"id": "<unique snake_case slug, 3-40 chars>",',
    '   "label": "<=12 words human label>",',
    '   "summary": "<what it enforces, <=60 words; quote the evidence>",',
    '   "params_schema": {"<matcher key>": "<short hint for admins>"},',
    '   "enforcement": {"kind": "forbid_cells",',
    '                    "matchers": { the fields the rule itself FIXES:',
    '                       subject/subjects/sections/teachers as written in the constraint;',
    '                       optionally stream, days[], slots[] when the constraint fixes them',
    '                    }',
    '   }',
    "  }",
    "",
    "Rules:",
    "- id must be a NEW unique slug (never reuse an existing id).",
    "- matchers may ONLY use: subject, subjects, sections, teachers, stream, days, slots.",
    "- days uses MON..SAT; slots uses P1..P8. Copy subject/section/teacher names verbatim.",
    "- Hard-code only what the constraint actually fixes; leave anything variable as a",
    "  parameter (params_schema) for admins to fill per use.",
    "- If the description is too vague to fix ANY matcher, return exactly:",
    '  {"unresolvable": true}',
]


def _openrouter_json(messages, max_tokens=3600):
    """One strict call; returns the parsed JSON object or a string error."""
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        return "LLM not configured — set LLM_API_KEY on the backend"
    base_url = os.environ.get("LLM_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    model = os.environ.get("LLM_MODEL", "google/gemma-4-26b-a4b-it:free")
    payload = json.dumps({"model": model, "messages": messages,
                          "temperature": 0, "max_tokens": max_tokens}).encode()
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + api_key,
        "HTTP-Referer": os.environ.get("LLM_HTTP_REFERER", "https://impcc-timetable-generator.vercel.app"),
        "X-Title": os.environ.get("LLM_X_TITLE", "IMPCC Timetable Generator"),
    }
    req = urlreq.Request(f"{base_url}/chat/completions", data=payload, headers=headers)
    try:
        with urlreq.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
    except HTTPError as e:
        return f"LLM HTTP {e.code}: {e.read().decode()[:300]}"
    except URLError as e:
        return f"LLM unreachable: {e.reason}"
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        return "LLM returned an unexpected shape"
    content = re.sub(r"^```(json)?\s*|\s*```$", "", content.strip(), flags=re.MULTILINE).strip()
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return "LLM did not return valid JSON"
    return parsed if isinstance(parsed, dict) else "LLM output was not an object"


def author_rule(detail, existing_registry=None, extras=None):
    """Author ONE new dynamic rule for a constraint that matched no fixed
    type. Returns {authored, rule:{...validated definition...}} or
    {"unresolvable": true} / {"error": ...} dicts (never raises)."""
    detail = (detail or "").strip()
    if len(detail) < 10:
        return {"error": "constraint description is too short"}
    registry = dict(existing_registry or {})
    context_lines = ""
    if extras:
        context_lines = "\nADMIN CONTEXT / NOTES:\n" + "\n".join(
            "- " + str(e)[:200] for e in extras[:8])
    prompt = "\n".join(_AUTHOR_PROMPT_LINES)
    prompt = prompt.replace("\u00abruleset\u00bb", ruleset_context_md(registry))
    prompt = prompt.replace("\u00ab\u00ab\u00abdetail\u00bb\u00bb\u00bb",
                            '###' + detail[:2000] + '###')
    prompt = prompt.replace("\u00abcontext\u00bb", context_lines)
    parsed = _openrouter_json(
        [{"role": "system", "content": "You are a rules author that ONLY returns strict JSON."},
         {"role": "user", "content": prompt}])
    if isinstance(parsed, str):
        return {"error": parsed}
    if parsed.get("unresolvable"):
        return {"unresolvable": True,
                "error": "the constraint is not expressible as a forbid-cells rule"}
    clean = validate_dyn_rule(parsed, existing_ids=set(registry) | GI_RULE_TYPES)
    if not clean:
        return {"error": "authored rule failed validation (bad slug/kind/matchers)",
                "raw": parsed}
    clean["natural"] = detail
    return {"authored": True,
            "rule": clean,
            "type": clean["id"],
            "params": dict(clean["enforcement"]["matchers"]),
            "natural": detail,
            "notes": "authored a NEW dynamic rule: " + clean["label"],
            "confidence": 0.8,
            "unmapped": []}
