"""Server-side auth gate: verify a Supabase session token before expensive actions.

CP-SAT generation and LLM translation are only allowed for signed-in users.
The incoming JWT is validated live against Supabase Auth (no secret needed here —
the access token itself is the proof). Pure stdlib.
"""
import json
import os
from urllib import request as urlreq
from urllib.error import HTTPError, URLError

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://xdckubhqhglmorwmxtfs.supabase.co")
SUPABASE_ANON_KEY = os.environ.get(
    "SUPABASE_ANON_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhkY2t1YmhxaGdsbW9yd214dGZzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY2NDY5NTksImV4cCI6MjEwMjIyMjk1OX0.a8Apb7KaEumAxDEb0ojgGDjizGaVseK6O28DsSWRpys",
)


def verify_token(token):
    """Return the Supabase user dict if the token is valid, else None."""
    if not token:
        return None
    req = urlreq.Request(
        SUPABASE_URL + "/auth/v1/user",
        headers={"Authorization": "Bearer " + token, "apikey": SUPABASE_ANON_KEY},
    )
    try:
        with urlreq.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except (HTTPError, URLError, ValueError):
        return None
