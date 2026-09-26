# model_result/

Up to 50 **fresh** model-mode ("Use model") conversion results, regenerated
against live code, each with an honest strict-similarity score (no inflated
100s — the QA authority is `qa/similarity_audit.py`).

## View it

Open in your browser (app preview host):
**`/model_result/index.html`** — side-by-side input vs model SVG with verdict
badges for all 50 rows (regenerate with `scripts/model_result_gallery.py`).

## Files

- `absolute_test_svg.svg` — the reference SVG the user approved as "85% almost
  like the uploaded" teal-orbit logo. Measured by the strict audit it is
  actually **97.0%** (mae 0.66, ssim12 0.986, silhouette IoU 0.970). This file
  is the visual target the model trains toward.
- `mr-001 … mr-049` — freshly converted SVGs (model mode), one per test image
  (user-provided uploads first, then generated assets).
- `index.json` — table of every output: engine route, strict similarity,
  verdict (PASS ≥85 / WEAK 70–85 / FAIL <70), per-channel metrics, and for the
  teal logo also `similarity_to_reference_pct` (closeness to
  `absolute_test_svg.svg`).

## Refresh

```bash
curl -s 127.0.0.1:8000/healthz        # app must be up
curl -s 127.0.0.1:9222/json/version   # CDP renderer must be up
PYTHONPATH=vendor:app/deps:. python3 scripts/model_result_build.py --n 50
```

Re-run after every engine or model-weights change to see the current truth.

## Current state (2026-09-26)

- 49 outputs + reference. Honest split: **24 PASS / 9 WEAK / 16 FAIL**.
- Teal-orbit logo: 87.0% vs input, **86.0% vs reference** (binary-alpha-mono
  route). The remaining gap to the 97% reference is engine capability
  (multi-tone halo reproduction), which the visual-training loop is targeting.
- Blue-bird logo remains the known open FAIL case (50.6%; deepened inks raise
  it only to 58.9% — palette-merge policy redesign is the planned fix).
