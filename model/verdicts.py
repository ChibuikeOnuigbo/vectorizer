"""Human-verdict feedback for the forever trainer (user acceptance criterion:
proof-page Good/Rubbish verdicts -> persisted verdicts.jsonl -> fed BACK into
training; this module is the consumption side).

  from model.verdicts import load_verdict_feedback
  weights = load_verdict_feedback(record_names)   # np float32 array, mean=1

Mapping: verdicts are keyed by report-row index `i` + method; the row's
`name` (asset filename) maps onto dataset records by exact filename match.
A "bad" verdict on the MODEL output up-weights that record (x2 sampling),
a "good" verdict down-weights it to 0.7 (never 0 - still keep coverage).
The verdicts aggregate over ALL rows for the method; the input asset only
appears once per record.

Reading is best-effort: empty/missing/unparseable encounters return weights
of 1.0 so training is never blocked by feedback plumbing.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERDICTS = ROOT / "model_data_snapshot/verdicts.jsonl"
REPORT = ROOT / "app/static/testreport/report.json"

BAD_W = 2.0
GOOD_W = 0.7


def load_verdict_feedback(record_names: list[str], method: str = "model"):
    """Return (weights np.array aligned with record_names, stats dict)."""
    import numpy as np

    stats = {"verdict_records": 0, "matched": 0, "bad_up": 0, "good_down": 0,
             "method": method, "verdicts_file": str(VERDICTS.relative_to(ROOT))}
    n = len(record_names)
    w = np.ones(n, dtype=np.float32)
    if n == 0 or not VERDICTS.exists():
        return w, stats
    try:
        ver = [json.loads(x) for x in VERDICTS.read_text().strip().splitlines() if x.strip()]
    except Exception:
        return w, stats
    ver = [v for v in ver if v.get("method") == method and v.get("verdict") in ("good", "bad")
           and v.get("i") is not None]
    stats["verdict_records"] = len(ver)
    if not ver:
        return w, stats
    rows: dict[int, str] = {}
    if REPORT.exists():
        try:
            rows = {int(r["i"]): str(r.get("name", "")) for r in json.loads(REPORT.read_text()).get("rows", [])
                    if r.get("i") is not None}
        except Exception:
            rows = {}
    pos = {nm: k for k, nm in enumerate(record_names)}
    for v in ver:
        nm = rows.get(int(v["i"]))
        if not nm or nm not in pos:
            continue
        stats["matched"] += 1
        if v["verdict"] == "bad":
            w[pos[nm]] = BAD_W
            stats["bad_up"] += 1
        else:
            w[pos[nm]] = GOOD_W
            stats["good_down"] += 1
    return w, stats
