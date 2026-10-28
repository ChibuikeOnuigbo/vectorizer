# fix ladder — dims stamp + palette collapse (2026-10-08)

Two shipped fixes driven by the bg-remove ladder, each with a calibrated
acceptance rule. `results.json` = fresh end-to-end rerun of all 15 ladder
icons through the FIXED pipeline (renders via file:// CDP transport).

## Fix 1 — soft-stack SVG dims stamp (correctness)

`color-soft-stack` traced on a ≤640px working frame and stamped the OUTPUT
SVG `width/height/viewBox` as the 640 frame: a 1024px upload silently
shipped a 640px SVG while `meta.width/height` said 1024. UI previews and
Figma imports land at the wrong size.

Fix: keep the working-frame viewBox (SVG scales losslessly) and stamp the
input dims. Geometry untouched. After fix: **all 15 ladder icons stamp
1024×1024** (`results.json` tag_w/tag_h), 1234-check structural battery
still passes.

### Honest artifact disclosure (own measurement)

The part-1 ladder report marked T2/T3 fidelity as catastrophic-fail
(ssim 0.03–0.17). That was substantially MY measurement artifact: the CDP
render harness laid the 640-wide SVG into a 1024px frame (white padding on
2 sides), so renders of soft-stack icons were geometrically wrong. With the
dims fix, renders match inputs and the honest fidelity map is:

| icon | part-1 ssim (artifact) | real ssim (fixed) |
|---|---|---|
| 01 rocket | 0.366 | **0.936** |
| 04 fox grad | 0.165 | **0.871** |
| 05 moon grad | 0.092 | **0.883** |
| 06 camera grad | 0.133 | **0.803** |
| 07 knight paper | 0.135 | **0.632** |
| 08 star denim | 0.025 | **0.609** |
| 09 apple halftone | 0.005 | **0.881** |

The REAL remaining T2/T3 defect is the envelope, not fidelity: icon-07/08
still carry **14k–16k speckle paths / 7.0–7.7MB** (pathology regime,
unchanged by these fixes — queued: tiny-region merge).

## Fix 2 — palette collapse (T5 envelope, evidence-driven)

T5 maximalist inputs produced 6–8k paths with 6–8k DISTINCT FILLS
(palette collapse ≈ zero). Post-trace, `_collapse_palette` greedily clusters
fill colors (frequency-ordered, per-channel tol=14) when output exceeds 512
distinct fills. tol calibrated against collapsed-vs-uncollapsed renders with
a pre-registered ssim floor of 0.995:

- tol=9: min-ssim 0.9982 (1.0–1.5k fills)
- **tol=14: min-ssim 0.9953 (414–636 fills) — shipped**
- tol=20: min-ssim 0.9900 (179–292 fills) — REJECTED (below floor)

Post-fix ladder: icon-13 7908→636 fills, icon-14 6190→550, icon-15 8285→414,
soft-stack icons 17–36 fills. Fidelity intact (results.json vs inputs:
0.88 skull / 0.76 owl / 0.66 phoenix — at or above pre-fix values).

## Not fixed this round (explicitly)

- T3 speckle path explosion (14–16k paths / multi-MB) — needs tiny-region
  merging, measured next.
- icon-11 parrot hue-mapping (44-color flats get wrong hues via cutout).
- T5 latency 13–32s (dominated by vtracer trace at 1024px, not post-pass:
  collapse adds <0.1s).

Regression proof: `/tmp` structural battery 1234/1234 PASS post-fix;
uploads teal/bird byte-deterministic, engines unchanged (alpha-halo /
soft-stack), meta intact.
