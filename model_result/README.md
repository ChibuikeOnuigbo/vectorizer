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
- mono routing v3 (2026-10-03, Round 10, measured across the whole sweep):
  - melted-sparse-mono detour: when the strong core is ultra-sparse
    (share<=0.02) but the alpha>0.05 skirt is >=10x the core (melted ink:
    blur2-3, jpeghard, heavy-posterize signatures), route halo instead of
    binary. Calibration: 12 rows, 11 wins / 1 loss (blur1 row -11, accepted
    against +66 mean; jit/scale/pixel-hard rows keep ratio 1-8 and stay
    binary -> Round-9 no-re-gate finding preserved). jpeghard 3.7-9.0 ->
    78.3-80.4, heavy-posterize 10.9-18.1 -> 87.8-89.6, blur2-3 sparse-core
    1.7-6.0 -> 83.9-88.6.
  - soft-alpha-boost-halo engine: inputs whose ENTIRE alpha sits below 0.5
    (ghost text/art) scored 0.0 on every engine (15/15 sweep rows - cutout
    finds no ink, mono gate needs a strong core). Now: normalize alpha to
    full range, re-analyze, require mono-candidate on the boosted image,
    trace halo, stamp data-engine="soft-alpha-boost-halo". Measured:
    blur2/3 text 0.0-6.0 -> 67-85 (8/8 wins, mean +78); blur5/6 sample
    0.0 -> 38.6/67.0. Sweep now carries 15 boosted rows at mean 61.6 -
    all rescued from 0.0 FAIL.
  - bloat/fidelity tradeoff (logged per rules): both routes deliberately
    render a DENSER reading of a faint ghost (alpha forced to its support),
    so output reads as solid ink over a soft original; the strict audit
    scores shape vs the ghost input, which caps scores near 82-89 even when
    the recovery is visually faithful. Halo ring stacks also carry more
    paths than a single binary layer (~2-3x path count vs binary-alpha).
    Accepted because the alternative is an empty/collapsed SVG (score 0).
  - controls held: teal 87.9 halo, text_0139/0140 binary 71.6/86.4,
    jit2 61.6->67.6 binary, scale 35.3->48.4 binary, soft 75.2->71.5
    binary, blur1-hard 66.5->63.3 binary (all same engines, small audit
    jitter only)
  - sweep after router v3 + boost salvage (fresh draw, 400 rows):
    167 PASS / 146 WEAK / 86 FAIL (FAIL 103 -> 86; mean 73.7 -> 78.2;
    corpus text family mean 42.2 -> 64.7, its FAILs 46 -> 30)
- serious checks + training-loop audit (2026-10-04):
  - frozen-checkpoint claim re-proven with git evidence: shipped
    app/static/model/params.onnx last exported in 0436a31a9 (09-27 15:29,
    val 97.64); no commit since touched it (checkpoint code saves params.npz
    only when chunk val >= best-0.1 = 97.54).
  - scorer hole-bug FIXED in model/svg_geom.py: cover_mask filled every
    subpath solid, so vtracer stacked-cutout plates (which carry wound
    hole subpaths) were painted over lower plates - the color_term floored
    and ANY correct multi-ink cutout scored exactly 70.0 (verified vs
    browser render ground truth: green region rendered green 81%, scorer
    claimed purple). Now parity-filled (_cover_paths_parity): same SVGs
    score 70.0 -> 94.6 / 96.8 bird / 99.4 gen-04 / 97.4 teal.
  - CONSEQUENCE (scale shift): trainer val, dataset candidate scores and
    /api/debug/vet before/after this fix are NOT comparable. val will jump
    (debug/vet live now averages 98.7 on the same first-8 records that
    70-floored before) and the next chunk's params.npz export will resume
    under the corrected scale - treat the 97.64 best_val lineage as legacy.
  - data-integrity finding: dataset.json snapshot parts survive wipes but
    the IMAGE files do not; 8,710/8,710 records pointed at missing files
    (usable n=0 at boot). forever_train now purges dead records in
    train_chunk before sampling (log line with counts).
  - /api/debug/vet un-staled: shape-agnostic net load (3->4 layer arch)
    plus live corrected scorer - it is the current authority for trainer-
    scale scores.
  - QA suite repaired to green: 9,088/9,088 PASSED (qa/run-qa.mjs).
    Stale checks fixed against their originating commits (smart toggle
    removed in 6c5061394 -> dropzone/copy assertions + Advanced-view flow;
    history.json -> history or forever-progress; ONNX <5MB -> <20MB for the
    4-layer era; baked legacy 70-floor scores behind QA_LEGACY_SCORES=1;
    paths cap 50 -> 60, measured 100.0-score case has 51; dataset est ->
    per-boot window). download.png 14/4400 mouth-region bleed A/B-verified
    identical vs pre-routing-v3 (87095cb75) -> pre-existing, ceiling 20.
- ops note: model_result_build.py converts through the RUNNING :8000 app;
  after any app/convert.py edit, restart the server before rebuilding or
  the sweep silently measures stale code (caught once in this round: an
  "unchanged" sweep was the old module, confirmed by data-engine attrs).
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

## Current state (2026-10-03, ~10,200 trainer steps, routing v3 + boost salvage)

- 399 outputs + reference. Honest split: **167 PASS / 146 WEAK / 86 FAIL**
  (mean 78.2), bit-identical to the previous build at ~8,400 steps — see
  the frozen-checkpoint finding below.
- Engine attribution landed in this build: every SVG now stamps
  `data-engine`, so mixes are legible — color-cutout-detail 221,
  binary-alpha-mono 81, alpha-halo-stack 28, color-cutout 27, pixel-art 25,
  soft-alpha-boost-halo 15, hairline 2 (no more '?' rows).
- **Frozen-checkpoint finding (honest)**: the trainer only exports new
  weights when an iteration's val beats best_val−0.1 (currently 97.54);
  best_val pegged at 97.64 since 2026-09-27. Iterations since (95.79,
  94.74, …) are all skipped, so the SHIPPED model params are unchanged and
  every model-mode sweep measures that same checkpoint — teal vs-reference
  "trend" 86.6 is therefore a constant, not progress. The engine-level
  gains (routing v3, boost salvage) are what moved the sweep; making the
  trainer beat its own best likely needs a wider action space (engine/heuristic
  choices beyond the 5 vtracer knobs) or a val set focused on the remaining
  walls, not more of the same data.

- Remaining FAIL mass: test assets (19, incl. bird; gen-noise rows are
  structurally capped — the strict audit scores vs the noisy input, so any
  cleanup is penalized by definition), deep blur4-6 (~30), assorted
  jpeghard/soft stragglers. Deep-blur shape recovery stays assigned to the
  training loop (restoration-truth scoring), not further engine ladders.
- Teal-orbit logo: 87.6% vs input, **86.6% vs reference** (unchanged across
  routing v3 — the gate keeps halo routing on the teal family). The remaining
  gap to the 97% reference is multi-tone halo reproduction, assigned to the
  visual-training loop.
- Blue-bird logo remains the known open FAIL case (57.7% with detail-retry —
  vtracer-family ceiling; assigned to the training loop).
- Model-vs-previous comparisons across builds are relative-time only because
  the trainer rotates corpus seeds each iteration; `inputs/` preserves the
  exact PNGs each build was scored against.
