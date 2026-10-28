# fallback-gate-extension — corpus-scale exposure + falcon un-parked (2026-10-12)

Two measured follow-ups to the mandala-tone-route gate from its first
corpus exposure test.

## Corpus exposure scan (2,757 model_result/inputs, per-row analyze stats)
- Fallback-reach cohort (flat, no-alpha, unclaimed by any family gate): 54
  rows; melt max **0.0326**. A melt>=0.14 gate placed in the plain-fallback
  block CANNOT fire on any corpus row → the fronting concern for the parked
  falcon reroute ("hijacking unmeasured v6-wall rows") is measured empty.
- Shipped color-soft reroute exposure: exactly **1** corpus row,
  `gen-07jpeg.jpg.png` (melt 0.1117).

## Threshold correction 0.08 -> 0.14 (the jpeg row bit back)
gen-07jpeg strict sims: soft-stack **95.4 PASS** > tone-stack 91.2 PASS >
cutout 89.1. The 0.08 gate handed it to the weaker engine (-4.2).
Measured 2,757-row exposure gap now used for the center: excluded side
{bird 0.055 → soft 97.2 PASS; jpeg 0.112 → soft 95.4 PASS} both better on
soft-stack; included side {pin 0.169 → +8.1 tone-stack; mandala 0.532 →
+18.9} both better on tone-stack. Threshold 0.14 centers the gap; 0.08 was
the first-calibration value, corrected by measurement.
(composite: `gen-07jpeg.jpg_similarity.png`.)

## Falcon un-parked
Same class evidence as the color-soft reroute (visual falcon composite
lives in the x2-era audit history), measured fallback-cohort emptiness
above, and the shade of the retuned threshold: fallback sibling gate
`is_flat ∧ no-alpha ∧ melt>=0.14 → color-tone-stack` placed BEFORE the
plain-fallback A/B (which the blind 128px judge always decides blob-side).
Shipped result: cx-05 falcon soft-stack 71.9 WEAK → tone-stack **81.4 WEAK
(+9.5)** through the DEFAULT route.

## Ship-time verification (default route, strict sim)
| row | engine now | sim | delta vs 2026-10-11 ship |
|---|---|---|---|
| cx-05 falcon | color-tone-stack | 81.4 WEAK | +9.5 (un-parked) |
| cx-04 mandala | color-tone-stack | 68.1 FAIL | held |
| x2-05 pin | color-tone-stack | 83.3 WEAK | held |
| download.png bird | color-soft-stack | 97.2 PASS | protected |
| gen-07jpeg | color-soft-stack | 95.4 PASS | restored (+4.2) |

Still parked: x2-04 mug (+12.4 measured) — melt-route arbitration chain is
blur4-6-calibrated; reroute there needs the same cohort-empty proof for the
melt branch, not yet measured.
Files: this README, gen-07 composite, `cohort.jsonl` summary card (full
scan retained in session log; per-row stats are recomputable with
scripts/midfreq-era analyze helpers).

## Battery catch + seal refresh (the battery earning its keep)
Battery drift guard caught the fallback sibling gate moving TWO bg-remove
evidence rows (the earlier fleet drift table did not cover bg-remove —
registered oversight, note added to the drift-check practice: always run
battery, not just the changed-class fleet):
- icon-08-star-texturebg (SEALED row, color-soft branch: melt 0.5156, aa
  0.408): sealed soft-stack **47.9 FAIL** -> tone-stack **73.0 WEAK (+25.1)**;
  visual composite `icon-08-star-texturebg_similarity.png` (denim weave
  preserved vs chunky block melt). Seal REFRESHED in evidence/fix-t3-speckle
  with refresh note (svg 5.7MB -> 14.3MB, visibility cost recorded).
- icon-12-prism-stripes (unsealed): cutout-era 72.9 WEAK -> tone-stack
  **86.8 PASS (+13.9)**; composite shows the inset white ring re-traced and
  stripes de-wobbled.
Both visual-verified as gains before the seal write (zero-trust rule).
The other five sealed rows byte-match after battery re-run.

## mug un-parked (same turn): melt-branch sibling gate at >=0.10
Cohort scan in the melt branch: blur4-6 calibrated winners max melt
0.0883; no-alpha melt_cand exposure >=0.10 is exactly one row (gen-07jpeg
0.1117) and it routes via COLOR-SOFT (protected there by the 0.14 gate) —
the in-branch corridor is empty. Shipped: color_soft=False ∧ no-alpha ∧
melt>=0.10 → tone-stack before the melt arbitration. Result: x2-04 mug
soft-stack 75.8 WEAK → tone-stack **88.2 PASS (+12.4)** through the default
route; composite `x2-04-doodle-crosshatch-mug_similarity.png` (hatching
legible vs muddied). Fragility disclosed in code comment: blur-max 0.0883
to gate 0.10 is a thin corridor.

## knight + fox corridors (2026-10-12, second half)

Fleet audit (evidence/fleet-audit) surfaced two more default-route FAILs
of the same blind-arbitration family; both un-parked on measured rows
with corpus exposure proof, same protocol as mug/falcon:

- icon-07 knight (melt 0.070 — INSIDE the blur-winner band, unreachable
  by the 0.10 melt gate): corridor = _texture_bg_regime(working) OR-ed
  into the no-alpha melt branch. Fires on denim/paper full-bleed texture
  backgrounds: knight soft-stack 48.8 FAIL -> tone-stack 76.5 WEAK
  (+27.7; composites: icon-07-knight-texturebg_similarity.*). Exposure:
  0 of the 20 no-alpha melt_cand corpus rows fires the texture regime.
  icon-08 side effect discovered at battery: reflowed sealed bytes under
  the post-wipe pinned stack (numpy k-means epsilon, not a route change —
  same +25.1 measured class; resealed, fix-t3-speckle/RESEAL-NOTE.md).
- cx-02 watercolor fox (not flat, no alpha, aa 0.232): corridor =
  0.20 <= aa < 0.55 in the fallback block. Cutout 66.5 FAIL ->
  tone-stack 76.5 WEAK (+10.0; composites: cx-02-watercolor-fox_*).
  Exposure: 0 rows in the 2,757-row corpus. The < 0.55 cap keeps
  castle-style dioramas OUT (x2-06 aa 0.709 stays soft-stack 86.7 PASS,
  vs 81.0 if annexed) and leaves mosaic-class parked (phoenix aa 0.736;
  no engine passes, no gate reaches it). Dog guard: flat=True melt 0.068
  aa 0.164 — outside both corridors, stays soft-stack 91.9.

Post-ship default route verified: knight 76.5, fox 76.5, castle 86.7,
phoenix 59.6 (parked), mandala 68.2 (parked), mug 88.6, dog 91.9,
bird 97.2. Battery 3171/3171 after seal refresh.
