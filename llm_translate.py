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
- "stream_forbidden_days": [{"stream":"I.COM","days":["FRI"]}]  → no classes of a stream on days.

MAPPING RULES (synonyms → canonical keys)
- "free", "off", "should not teach", "must not teach", "cannot take" → forbidden.
- "only", "can only come", "available only" → allowed_*.
- "no day off", "every day", "daily" → min_days_engaged 5.
- "engaged", "must take", "should take" + a period number + a day count → min_days_in_slot.
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
        if not ok:
            errors.append(f"bad shape for '{key}': {val!r}")
            continue
        clean[key] = val
    return clean, errors, warnings


def translate_constraints(text, teacher=None):
    """Call the LLM and return a normalized result dict (never raises)."""
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
