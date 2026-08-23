#!/usr/bin/env python3
"""Apply a Supabase migration file to the project database via the
management API. Statements run one by one; every statement is expected to be
idempotent (see the .sql files in supabase/migrations/).

Usage:
    python3 tools/migrate_supabase.py supabase/migrations/002_populations.sql

Requires the SUPABASE_ACCESS_TOKEN (management API personal access token,
sbp_...) and SUPABASE_PROJECT_REF environment variables.
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error

API = "https://api.supabase.com/v1/projects/{ref}/database/query"


def run_statement(ref, token, sql):
    req = urllib.request.Request(
        API.format(ref=ref), method="POST",
        headers={"Authorization": "Bearer " + token,
                 "Content-Type": "application/json",
                 "User-Agent": "impcc-migration/1.0"},
        data=json.dumps({"query": sql}).encode())
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read().decode()
        try:
            return json.loads(body) if body else None
        except ValueError:
            return body


def split_statements(sql_text):
    """Split on ';' at line ends, respecting -- comments. Every migration
    statement here is single-line-safe (no semicolons inside strings)."""
    out = []
    for raw in sql_text.split("\n"):
        stripped = raw.strip()
        if not stripped or stripped.startswith("--"):
            continue
        if not stripped.endswith(";"):
            continue
        out.append(stripped)
    return out


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    path = sys.argv[1]
    token = os.environ.get("SUPABASE_ACCESS_TOKEN")
    ref = os.environ.get("SUPABASE_PROJECT_REF", "xdckubhqhglmorwmxtfs")
    if not token:
        print("SUPABASE_ACCESS_TOKEN not set")
        sys.exit(2)

    sql_text = open(path).read()
    statements = split_statements(sql_text)
    print(f"applying {path}: {len(statements)} statements to project {ref}")
    ok = 0
    for i, stmt in enumerate(statements):
        label = stmt if len(stmt) <= 90 else stmt[:87] + "..."
        try:
            res = run_statement(ref, token, stmt)
            ok += 1
            detail = ""
            if isinstance(res, list) and res:
                detail = " -> " + json.dumps(res)[:120]
            print(f"  [{i + 1}/{len(statements)}] OK {label}{detail}")
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:300]
            print(f"  [{i + 1}/{len(statements)}] FAIL {label}")
            print(f"      HTTP {e.code}: {body}")
            print("      (statements are idempotent — fix the issue and re-run)")
            sys.exit(1)
        time.sleep(0.15)
    print(f"done: {ok}/{len(statements)} statements applied")


if __name__ == "__main__":
    main()
