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
RULE_SPEC = {
    "allowed_slots": list,
    "forbidden_slots": list,
    "allowed_days": list,
    "forbidden_days": list,
    "forbidden_slots_on_days": list,   # [{"days":[...], "slots":[...]}]
    "min_days_in_slot": list,          # [{"slot": "P1", "min_days": 4}]
    "min_days_engaged": int,
    "max_periods_per_day": int,
    "subject_slots": list,             # [{"subject": "...", "slots":[...]}]
    "subject_forbidden_days": list,    # [{"subject": "...", "days":[...]}]
    "stream_slots_required": list,     # [{"stream": "ICS", "slots":[...]}]
    "stream_forbidden_days": list,     # [{"stream": "I.COM", "days":[...]}]
    "allowed_slots_in_stream": list,   # [{"stream": "I.COM", "slots": ["P1","P2","P3"]}]
    "allowed_days_in_stream": list,    # [{"stream": "I.COM", "days": ["THU","FRI"]}]
    "subject_slot_days": list,         # [{"subject": "...", "slot": "P3", "days": ["MON","TUE"]}]
    "soft_prefer_free_slots": list,    # ["P3"] — SOFT: penalized, not forbidden
    "soft_even_distribution": bool,    # SOFT: spread the weekly load evenly
    "allow_same_subject_same_day": bool,  # personal exception: same-subject doubles allowed
}

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

RULES — use ONLY these keys:
- "allowed_slots": ["P1","P2","P4"]              → the ONLY periods they may teach.
- "forbidden_slots": ["P5"]                      → periods they must never teach ("never the last period", "no 5th period").
- "allowed_days": ["THU","FRI"]                  → the ONLY days they may teach ("only Thursday and Friday").
- "forbidden_days": ["FRI"]                      → days they must never teach ("never on Friday").
- "forbidden_slots_on_days": [{"days":["MON"],"slots":["P1","P2"]}]  → combined ban ("Monday first two periods free").
- "min_days_in_slot": [{"slot":"P1","min_days":4}]  → must teach in that period on at least N distinct days ("1st period engaged 4 days a week").
- "min_days_engaged": 5                          → must teach on at least N distinct days ("no completely free day" → 5).
- "max_periods_per_day": 3                       → never more than N periods in one day.
- "subject_slots": [{"subject":"Business Mathematics","slots":["P3"]}]  → pin a subject into specific periods.
- "subject_forbidden_days": [{"subject":"Principles of Commerce","days":["MON"]}] → forbid a subject on days.
- "stream_slots_required": [{"stream":"ICS","slots":["P1","P2"]}]  → must occupy periods in a stream ("ICS fills P1 & P2").
- "allowed_slots_in_stream": [{"stream":"I.COM","slots":["P1","P2","P3"]}] → in that stream ONLY these periods may be used ("engage 1st-3rd periods in I.Com").
- "allowed_days_in_stream": [{"stream":"I.COM","days":["THU","FRI"]}] → in that stream ONLY these days may be used ("I.Com classes on Thursday and Friday").
- "subject_slot_days": [{"subject":"Business Mathematics","slot":"P3","days":["MON","TUE"]}] → pin a subject's period onto specific days ("3rd period in I.Com on Monday and Tuesday" where their I.Com subject is BM).
- "soft_prefer_free_slots": ["P3"] → SOFT preference: keep these periods free "as much as possible"; violations are penalized, never forbidden.
- "soft_even_distribution": true → SOFT: spread this teacher's periods evenly over the week.
- "allow_same_subject_same_day": true → personal exception: this teacher's same-subject classes MAY double on one day (overrides the inter-level no-double rule for their units).
- "stream_forbidden_days": [{"stream":"I.COM","days":["FRI"]}]  → no classes of a stream on days.

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


def _validate_rules(rules):
    """Normalize + validate; returns (clean_rules, errors, warnings)."""
    clean, errors, warnings = {}, [], []
    if not isinstance(rules, dict):
        return {}, ["rules must be an object"], []
    for key, val in rules.items():
        if key not in RULE_SPEC:
            warnings.append(f"ignored unknown key '{key}'")
            continue
        # basic shape checks
        ok = True
        if key in ("allowed_slots", "forbidden_slots"):
            ok = isinstance(val, list) and all(s in SLOTS for s in val)
        elif key in ("allowed_days", "forbidden_days"):
            ok = isinstance(val, list) and all(d in DAYS for d in val)
        elif key == "forbidden_slots_on_days":
            ok = isinstance(val, list) and all(
                isinstance(e, dict) and all(d in DAYS for d in e.get("days", []))
                and all(s in SLOTS for s in e.get("slots", [])) for e in val)
        elif key == "min_days_in_slot":
            ok = isinstance(val, list) and all(
                isinstance(e, dict) and e.get("slot") in SLOTS
                and isinstance(e.get("min_days"), (int, float)) for e in val)
        elif key == "min_days_engaged":
            ok = isinstance(val, int) and 1 <= val <= 5
        elif key == "max_periods_per_day":
            ok = isinstance(val, int) and 1 <= val <= 5
        elif key in ("subject_slots", "subject_forbidden_days"):
            ok = isinstance(val, list)
        elif key in ("stream_slots_required", "stream_forbidden_days"):
            ok = isinstance(val, list) and all(
                isinstance(e, dict) and e.get("stream") in STREAMS for e in val)
        elif key == "allowed_slots_in_stream":
            ok = isinstance(val, list) and all(
                isinstance(e, dict) and e.get("stream") in STREAMS
                and all(s in SLOTS for s in e.get("slots", [])) for e in val)
        elif key == "allowed_days_in_stream":
            ok = isinstance(val, list) and all(
                isinstance(e, dict) and e.get("stream") in STREAMS
                and all(d in DAYS for d in e.get("days", [])) for e in val)
        elif key == "subject_slot_days":
            ok = isinstance(val, list) and all(
                isinstance(e, dict) and isinstance(e.get("subject"), str)
                and e.get("slot") in SLOTS
                and all(d in DAYS for d in e.get("days", [])) for e in val)
        elif key == "soft_prefer_free_slots":
            ok = isinstance(val, list) and all(s in SLOTS for s in val)
        elif key in ("soft_even_distribution", "allow_same_subject_same_day"):
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
