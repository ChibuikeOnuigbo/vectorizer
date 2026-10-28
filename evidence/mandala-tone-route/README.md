# mandala-tone-route — micro-detail wash reroute (2026-10-11)

Origin: cx-04 mandala is the worst-measured row in the strict fleet
(49.2 FAIL under the fixed-ssim calibrated judge; visual: soft-stack plates
blob the fine ink linework into gray mush — see
`cx-04-mandala-microdetail_similarity.png`, input / shipped / tone-stack).

## Engine sweep (strict sim, shipped judge = fixed ssim12 + midfreq_rec50)

| row | shipped (soft-stack) | tone-stack | cutout-photo | cutout-flat |
|---|---|---|---|---|
| cx-04 mandala | 49.2 FAIL | **68.1** (+18.9) | 50.0 | 30.8 |
| cx-05 falcon | 71.9 WEAK | **81.4** (+9.5) | — | — |
| x2-04 mug | 75.8 WEAK | **88.2** (+12.4) | — | — |
| x2-05 pin | 75.2 WEAK | **83.3** (+8.1) | — | — |
| x2-06 castle | 86.7 PASS | 81.0 (−5.7) | — | — |

Family mis-route confirmed on 4/5 weak rows; castle (the PASS row) loses.
Cost of tone-stack: ~2-3x paths/kb/ms (mandala 16.8k paths / 14.6MB /
13.5s — recorded visibility cost of the fidelity).

## Why not the shipped A/B judge
`_ab_svg_score` ranks the blobbier candidate higher on EVERY pair (ss 85.1
vs ts 67.2 on mandala — 18 pts wrong-side). Cause: 128px PIL polygon
rendering; micro-band structure collapses at ~0.24px polygons (the
convert.py note at the color-soft dispatch already documents a sibling of
this: "their A/B judge at 128px favors aliased cutouts"). No in-request
honest arbiter exists today (no Chromium in prod path) → input-side gate.

## Gate: color-soft family split by melt_share
Color-soft rows (`_color_soft_candidate`: is_flat + aa>=0.15) split:
- glow/AA art (bird `download.png`): soft-stack **97.2 PASS** vs tone-stack
  **63.5 FAIL** (−33.7 — the flagship veto; composite `download_similarity.png`)
- micro-detail wash (mandala/falcon/pin): tone-stack wins (+8.1..+18.9)

Discriminator: `_melt_share` (strong-gradient share). Measured values:
bird 0.055 | mug 0.105, pin 0.169, falcon 0.235, mandala 0.532. Threshold
0.08 sits in the nearest measured gap (0.055..0.105) per repo convention.
castle excluded: is_flat=False (it never reaches the color-soft dispatch).

Shipped: inside the auto-route's color-soft dispatch only —
`_melt_share(a) >= 0.08 → _trace_color_tone_stack` — engine-forced calls
stay literal; melt-route arbitration untouched (blur4-6 calibration);
plain-fallback A/B untouched.

## Parked
- cx-05 falcon (+9.5 would-be): reaches soft-stack via the plain-fallback
  A/B where the blind judge is the only arbiter — rerouting there without
  arbitration risks hijacking unmeasured v6-wall rows. Needs either an
  honest in-request judge or a strict-judge re-sweep of the fallback
  corpus (infra-scale). Parked with numbers (71.9 → 81.4 measured).
- x2-04 mug (+12.4): melt-route row (melt 0.1047<0.12); arbitration chain
  is blur4-6-calibrated; not touched. Parked.

## Regression gates (all green at ship)
- `final_validation.py` 3168/3168 (incl. 6 sealed byte-compares).
- Fleet engine-drift table (26 evidence inputs): only the 2 intended
  reroutes changed (mandala, pin); cx-06/07/08 deltas trace to the
  documented 2026-10-08 fixed routes (complex-set README), not this change.
Files: this README, the two composites, `gate-table.json` (engine sweep +
arbiter numbers).

## 2026-10-12 addendum: threshold correction 0.08 -> 0.14 + falcon extension
Corpus exposure (2,757 rows, evidence/fallback-gate-extension): the one
color_soft row hit by 0.08 (gen-07jpeg, melt 0.1117) scores better on
soft-stack (95.4 PASS vs 91.2 tone-stack) — gate retuned to 0.14, centered
in the measured exposure gap {excluded .055/.112 better-on-soft |
included .169/.532 better-on-tone}. Falcon extension shipped from the same
scan: fallback-reach cohort's max melt is 0.0326, so the sibling gate in the
plain-fallback block cannot fire on any corpus row; falcon un-parked
71.9 -> 81.4. All else unchanged.
