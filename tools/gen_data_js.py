#!/usr/bin/env python3
"""Regenerate data.js (the browser-loadable canonical dataset) from
data/canonical.json. Run from the repo root after editing canonical.json:

    python3 tools/gen_data_js.py
"""
import json
import os
import io

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "canonical.json")
DST = os.path.join(ROOT, "data.js")

data = json.load(io.open(SRC, encoding="utf-8"))
payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))

out = """/*
 * data.js — the canonical IMPCC dataset (generated; DO NOT EDIT BY HAND).
 *
 * Generated from data/canonical.json by tools/gen_data_js.py. The canonical
 * model is documented in canonical_model.md: faculty directory (with aliases),
 * subjects registry, per-population allocations (courses -> faculty),
 * parallel groups, combined classes, faculty constraints and structured
 * general instructions.
 *
 * Consumed by canonical.js (IMPCC_CANONICAL). Also require()-able in Node.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.IMPCC_DATA = factory();
})(typeof self !== "undefined" ? self : this, function () {
  return %s;
});
""" % payload

io.open(DST, "w", encoding="utf-8").write(out)
print("wrote", DST, "(%.1f KB)" % (os.path.getsize(DST) / 1024))
