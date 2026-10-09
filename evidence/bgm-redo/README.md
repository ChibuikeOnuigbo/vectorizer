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
