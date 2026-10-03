# model_result/

Up to 50 **fresh** model-mode ("Use model") conversion results, regenerated
against live code, each with an honest strict-similarity score (no inflated
100s — the QA authority is `qa/similarity_audit.py`).


## 2026-10-03 new engines (measured, visual-check-driven)
- pixel-art engine (<=64px inputs): alpha-exact RLE crisp rect rows -
  downscale32 rows 1-17% -> 99.9-100% (24 rows now mean 99.7); kills the
  32px raster floor honestly (rect runs are the true grid)
- hairline skeleton engine (Zhang-Suen + centerline polylines, ink color
  sampled along chain, stroke-width 1.5 tuned): thin opaque strokes
  63.9% contour-fill -> 75.9% (1px lines no longer inflated to ~3px);
  route gate = opaque flat + ink share <12% + erodes away within 2 rounds
- sweep after both: 174 PASS / 142 WEAK / 84 FAIL (FAIL 103 -> 84 over
  400 rows; engines in the sweep: halo 77, pixel-art 25, binary 30,
  hairline 2, cutout-family 266)

## 2026-10-02 routing + detail upgrades (measured)
- mono-alpha route gate: strong-pixel share <= 0.17 -> alpha-halo-stack
  (calibrated 41-image sweep: halo wins 21/21 in that regime by +8.5 avg);
  dense fills stay binary (-12..-54 otherwise). Teal now converts at 87.9 /
  86.6 vs-reference through model mode
- detail retry: flat cutout with <= 6 paths retraces in detail mode
  (beak/eye micro-cutouts): bird 50.6 -> 57.7; 26-image corpus: worst -2.1
- sweep after upgrades: 154 PASS / 143 WEAK / 103 FAIL (FAIL 147 -> 103)
- collages/ one side-by-side input|output PNG per row, verdict stamped
- blur-family wall measured (2026-10-03): blur2-6 variants mean 31-50 vs
  57+ for all other degradations - heavily blurred COLOR art defies
  flat-tone vectorization; color-tone-stack engine added as opt-in
  (engine:"color-tone-stack", 7 tones): +55 on blur6 rows where cutout
  collapses to 7.4, but catastrophic misses on 4/8 probe rows -> NOT
  auto-routed (calibration discipline), kept for the candidate space;
  blur recovery is assigned to the training loop (its own scoring uses
  restoration truth, not input fidelity)
- mono routing v2 (2026-10-03, 72-image calibration): radial 3-zone gate.
  ultra-sparse share<=0.02 -> binary (text/lines: was misrouted to halo,
  text rows 63.9 -> 80.9 mean, 0 FAIL in draw); ring-halo mean_d>=0.68 or
  compact <=0.56 with share in (0.02,0.17] -> halo; rest binary.
  13.6-FAIL text row -> 71.6 WEAK, 49.1 -> 86.4 PASS
- watches: 32px downscale inputs cap ~1-17% every engine (raster floor,
  no route gate applies); thin strokes sharpened 47.6 -> 63.9 but stroke
  weight still +2px (hairline-width emitting planned)

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

- 399 outputs + reference. Honest split: **143 PASS / 137 WEAK / 120 FAIL** (400 rows incl.
  reference; test-assets 75/66/61 + fresh trainer corpus 67/71/59)
- Teal-orbit logo: 87.0% vs input, **86.0% vs reference** (binary-alpha-mono
  route). The remaining gap to the 97% reference is engine capability
  (multi-tone halo reproduction), which the visual-training loop is targeting.
- Blue-bird logo remains the known open FAIL case (50.6%; deepened inks raise
  it only to 58.9% — palette-merge policy redesign is the planned fix).
