# bgm-redo — bg-mottle fix evidence (2026-10-09)

Route: `_bg_mottle_probe` (opaque, bg-frac>=0.4, sigma>=3.5, blur-residual
>=0.6, hf/block-spread>=0.4, within-bg->25dist <=0.30 rejector) then a
smooth local-mean-field retrace through the same soft-stack engine, gated
by the calibrated A/B judge AND a >=30% path cut (pre-registered).

Measured outcomes over the mottle family:
| probe | probes? | judge delta | paths | decision |
|---|---|---|---|---|
| hx-07 teal-noise | FIRE | -1.0 | 3399 -> 1655 (49%) | **bgm SHIPPED** (613KB, was 1443KB) |
| x2-05 stone | FIRE | -0.5 | 2321 -> 3773 (163%) | vetoed (path-cut fails) |
| x2-04 paper | FIRE | +1.9 | 1494 -> 1390 (93%) | vetoed (path-cut fails) |

Why the vetoes were kept: the stone/paper texture is medium-scale (islands
20-80px): no blur radius (13/24/36 measured) cuts soft-stack paths below
~88%; smoothing it out would erase intentional medium structure, not fine
noise -> fidel math can't call it an artifact, only a style preference.
The judge+path rule correctly protects them. Blur radius variants measured
null: r24/r36 change nothing beyond r13 on this engine.

Guard provenance: speckle icon-08 gate-excluded (midshare 0.434 > 0.30);
photo dog no-fire (resid 0.50 < 0.6); flat/gradient/holos no-fire. Battery
3165/3165 with engine allowlist updated (soft-stack-bgm).

Known cosmetic term: the smooth field ends at the strict bg-mask boundary,
so a ~30px darker-teal ring reads around the subject (bg-median mask
excludes near-subject pixels). It renders as a soft drop shadow; judged
harmless here (judge -1.0) but recorded for the next cycle. The checker-
board texture inside the rocket body (halftone dots) is INTACT; only the
background texture got smoothed.

## measured null: subject-side despeckle for iridescent/foil (x2-08)
Attempt (2026-10-09, probe-grid sibling of the bgm route): 5x5 median
despeckle blended 50% on the subject mask (dist>45 from bg median),
retraced through soft-stack, A/B + path-cut arbitration (same rule):
  x2-08 holo  : judge +2.0 but paths 1645 -> 3146..3188 (191-194%)  VETO
  x2-05 stone : judge  0.0 but paths 2321 -> 6172..6225 (266-268%)  VETO
Numbers identical across k=3/5/7: vtracer soft-stack traces BANDS, and
smooth band-transitions create MORE traceable edges, not fewer. Conclusion
(standing rule): smoothing a mid-frequency color field is never
envelope-positive under this engine. Iridescence/foil stays as traced
(WEAK-PASS); the true lever for this class is the colors-knob
(colors=8..16 coarsens palette bands measurably) — product-track item,
not a fidelity fix.
