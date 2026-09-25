# QA Report — Vectorizer (master directive pass 1)

Generated 2026-09-25 (pass 2, Stage B) from artifacts on disk. Every number below is traceable
to `qa/results/`, `qa/screenshots/`, `test-assets/manifest.json`, or
`automation/TASK_STATE.json`. Nothing is estimated.

## Totals (§43)

| Metric | Value | Evidence |
|---|---|---|
| Total QA executions | **4,628** | `qa/results/_summary.json` |
| PASS | **4,615** | same |
| FAIL | **0** | same |
| ERROR | 0 | same |
| TIMEOUT | 0 | same |
| UNSUPPORTED_WITH_REASON | **13** (11-provider validation matrix + 2 AI probes; no user key in sandbox, server rejects gracefully HTTP 400) | `aimode-*.json`, `provider-*.json` |
| Determinism pairs | 150 run, **150 identical** (exact same input+params ⇒ byte-identical SVG) | `_summary.json` |
| Latency | avg 198.7 ms, p95 347 ms, max 3.19 s | same |
| Icon pairs compared to reference SVG | **3,133/3,133 PASS**; generated avg 4.7 paths vs authored 1.0 (path ratio 4.66 — expected for raster→vector tracing incl. AA regions) | `qa/results/_icon_compare.json` |
| Visible repository test images | **203** (3 user + 200 generated) | `test-assets/manifest.json` |
| Test-asset manifest entries | **5,909** (5,908 unique md5; Stage B target 5,000 pairs/references EXCEEDED) | same |
| Open-license SVG ground truth | **951 distinct SVGs** (Font Awesome Free 5.15.4: solid 400 / brands 395 / regular 156 after md5 dedup of 2) | `dataset/icons/fontawesome/index.json` |
| Raster pair renders | **4,755** inputs (951 icons × w64/w128/w256/w512/d128) + 600 blur/jpeg variants | `dataset/icons/fontawesome/renders.json` |

## Execution matrix (§13/§22)

Per-image conversion through the REAL live server (`POST /api/convert`):

- 200 generated assets × {model, classic, preset:logo} = 600
- Stage B: every icon 200..950 at w256 classic+model (1,502) + w512 classic (751) = 2,253
- pixel-score compare: 300 icon cases (model.svg_geom silhouette/edge scorer) avg 96.5, p05 94.1, min 70.7
- provider validation matrix: all 11 AI providers = 11
- 120 icon renders × 2 sizes × {classic, model, preset:icon} = 720 (+160 more icons × 2 modes)
- 2 user images × 5 modes = 10
- slider sweep colors∈{2,4,8,16,32} × detail∈{25,75} on 10 assets = 100
- preset sweep {illustration,lqip,artistic,custom} on 40 assets = 160
- determinism: 150 assets run twice = 300
- malformed inputs (empty file, truncated PNG/JPEG/GIF, exe-as-image, 1×1, 2×2000, fully transparent) = 12 — all rejected gracefully or handled without crashing the worker
- AI mode probes = 2 (no key configured in this sandbox → UNSUPPORTED_WITH_REASON, not faked as tested)

By mode (`by_mode` in `_summary.json`): model 1,273 PASS, classic 2,736,
preset:logo 202, preset:icon 242, preset:illustration 42, preset:lqip 40,
preset:artistic 40, preset:custom 40, ai 2 UNSUPPORTED.

## Real bugs found and FIXED this pass

1. **Crash on extreme aspect-ratio opaque images** — `analyze()` built its
   boolean content mask with numpy shape `(small_w, small_h)` (width-first)
   while the pixel array is `(small_h, small_w, 3)`; any opaque non-square
   image with a dim > 256 crashed with
   `IndexError: boolean index did not match indexed array along axis 0`
   (HTTP 422). Fix: `np.ones((small_h, small_w))` in `app/convert.py`.
   Found by `edge-aspect-wide.png` (1024×64): 5 executions.
2. **Empty-SVG shells at slider colors=2** — `sliders_to_params` maps
   “2 colors” to vtracer `color_precision=1` bit, collapsing flat-ink
   buckets into the background bucket; the single remaining path was then
   stripped as background → 134-byte `<svg/>` shell on 13 executions
   (8 sweep + 5 degraded variants were the signal after mask fix).
   Fix: floor `color_precision` at 2 (palette size is still governed by
   `_flatten_colors` ink cap).
3. **Persistence clobbered by init code (R2 regression)** — `bindRange()`
   runs its `update()` — which calls `saveProject()` — at boot, before
   `loadProject()`; with an empty `state.svgText` this **overwrote the
   stored project with an empty record on every page load**, making reload
   persistence permanently fail. Fix: `saveProject()` now refuses to
   replace a stored vector project with an empty one (view name still
   persists). Verified: after reload the app restores source image + SVG,
   view=result, **zero** re-conversion requests.

## Browser/UI regressions (§18/§19/§39) — all PASS

`qa/qa_regressions.mjs` (real Chromium/Playwright), evidence in
`qa/screenshots/regressions/` + `regressions.json`:

- **R1 upload-bug**: after conversion, clicking on/around the vector result
  never reopens the upload UI and never triggers the file picker
  (`fileInput.click()` spy count 0). Clicking the SVG box opens the
  fullscreen viewer (intended). PASS.
- **R2 persistence**: upload→convert→reload restores source+SVG, no
  re-conversion. PASS after fix #3.
- **R3 interactions**: zoom 100→125, reset→100, compare overlay opens,
  background toggle. PASS.
- **R4 explicit new-image** returns to upload view. PASS.
- Workspace-choice modal (Simple/Advanced) appears after convert — intended
  (§38), scripted accordingly.

Screenshots: `01-after-upload`, `02a-workspace-choice`, `02-result`,
`03-zoom-compare` (incl. dotted divider), `04-after-reload`.

## User-provided images (§4)

The three attachments live in `test-assets/images/user-provided/`
(`blue-bird-appicon.png`, `teal-orbit-logo.png`, plus the byte-identical
duplicate kept as dedup evidence). All processed through model/classic/
preset-logo/preset-icon/preset-illustration — 10/10 PASS. Their SVG outputs
from both pipelines are committed at `qa/artifacts/*-{classic,model}.svg`
with a rendered side-by-side proof at `qa/artifacts/user-proofs-grid.png`.

## Known limitations / open items

- **AI modes**: only 2 probes executed; both correctly UNSUPPORTED in this
  sandbox (network egress to providers is blocked and no user key is set).
  Full AI-mode comparison requires a keyed run.
- **Cloudinary workflow comparison (§20)**: reference workflow documentation
  exists in research notes from earlier turns; network-blocked sandbox
  prevents a live re-verification this pass → not claimed as tested.
- **Histogram vs authored icons**: vectorizer output has ~3.9× path count of
  hand-authored reference SVGs (region-splitting + anti-aliasing); structural
  comparison only, pixel-metrics reuse the trainer scorer on training data.
- **Training in progress**: forever trainer at 2,772-record dataset window,
  scoring 0.60 s/img, best=97.9 avg20=96.2 toward 70K images / 2M steps.
- Lucide bundle is minified only (no per-icon SVGs) → Font Awesome used as
  the open-license icon corpus; Lucide extraction deferred (not needed).

## §20 reference workflow (mock) + AI analysis scaffold

- Local reference mock (:8100) exercised via browser; comparison at
  `qa/cloudinary_reference.md` + `qa/screenshots/reference/` (app 1,687 ms,
  mock 2,682 ms incl. artificial 2.5 s sleep, 0 console errors). Real
  Cloudinary service unreachable from sandbox - documented as blocker, not
  claimed as tested.
- `qa/ai_svg_analysis.py` produces `svg_analysis_<name>.json` with
  observed_from_svg (deterministic, verified) strictly separated from
  model_interpretation/model_recommendation (UNSUPPORTED without a key;
  4 committed samples under `qa/artifacts/`).

## Restart / continue

`automation/timer.py` restarts server/trainer/runner as needed and echoes
the continuation line; checkpoints in `automation/TASK_STATE.json`.
