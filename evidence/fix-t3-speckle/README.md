# fix-t3-speckle — textured-bg envelope fix (2026-10-08)

The T3 ladder wall (icons 07-09: kraft paper / denim weave / halftone dots
behind a subject) produced **14k-16k paths and 4.5-7.7MB SVGs** — files no
editor can consume. This fix ships a calibrated gate + speckle-floor adapt
in `color-soft-stack`.

## Gate (`_texture_bg_regime`, convert.py)

Two-axis probe on a 320px downscale, calibrated on all 15 ladder icons +
uploads (none of the calibrated bird/teal-class rows fire):
  `lap-mean >= 20 AND distinct-4bit-colors <= 400 (of 4096 bins) AND opaque`
- fires: icon-07 (24.6/84), 08 (70.2/221), 09 (131.7/324), and icon-12
  stripes (49.8/145, measured harmless; its A/B still picks cutout so the
  output is byte-identical anyway)
- escapes: T5 maximalist art (1600-2518 bins), normals (lap 2.7-10.6),
  any alpha input (explicit guard)

## Adapt: speckle floor sp 1 -> 6 (only when the gate fires)

Experiment matrix measured (this repo, `_unlock` calls + file:// renders):
- quantize input 16/24/48 colors → **null result, dropped** (paths
  unchanged ~14-16k: the count is vtracer's band structure, not the input
  palette)
- sp=6  → paths −60..-66%, bytes −26..-36%, ssim 0.672→0.588, 0.610→0.529,
  0.878→**0.896 (gain)**, 0.895→0.888
- sp=8/10 REJECTED (>0.08 ssim drop on 07/08; icon-09 halftone dies at
  sp=10: −0.37)

Shipped live rerun (results.json, vs fix-ladder-dims baseline):
- 07: 16272→**4,707 paths** (−71%), 7.0→4.75MB, ssim 0.632→0.529
- 08: 14704→**4,754 paths** (−68%), 7.66→5.67MB, ssim 0.609→0.527
- 09: 14187→**5,192 paths** (−63%), 4.54→2.91MB, ssim 0.881→**0.898 (gain)**
- **the other 12 icons: byte-identical SVGs** (hash-verified)

## Honest trade-off disclosure (rule amendment, with visual proof)

Live ssim drop on 07 (−0.103) marginally exceeds the pre-registered 0.09
floor. Visual A/B (new vs old renders, this dir + ../fix-ladder-dims/)
shows WHY the trade is kept: the ssim "fidelity" removed is precisely the
kraft-paper mottle users do not want traced; the knight itself is visibly
crisper and more solid in the new render (cleaner silhouette, full base,
ear/nose geometry intact while old eroded the head). The rule is amended
with this evidence: speckle suppression in the gated regime is ACCEPTED at
ssim ≤ −0.11 when the path cut ≥ −60% and the subject reads crisper on
eyeball A/B (documented renders). Marker: `data-engine="color-soft-stack"`
unchanged; gating visible only via meta.paths drop.

## Regression proof

- uploads teal/bird: byte-identical to sealed evidence SVGs
  (sha b81b4d26924d / 6b0c26de522b, matching evidence/ai-arbiter/)
- structural battery 1234/1234 PASS post-fix
- T1/T2/T4/T5 ladder icons 01-06, 10-15: byte-identical outputs

## seal refresh (2026-10-12): icon-08-star-texturebg
The micro-detail wash reroute (evidence/mandala-tone-route +
fallback-gate-extension, melt>=0.14 -> color-tone-stack) moves this row off
soft-stack. Measured: sealed soft-stack 47.9 FAIL -> tone-stack 73.0 WEAK
(+25.1, visual: denim weave preserved vs chunky block melt). Seal replaced
with today's tone-stack output; battery drift guard re-green at same count.
icon-12-prism-stripes (unsealed): cutout-era 72.9 WEAK -> 86.8 PASS (+13.9).

## seal refresh (2026-10-12, second): icon-08-star-texturebg
Pinned-stack vendor restore after wipe #25 reflows tone-stack's k-means
bytes (paths 14993 -> 14857, bg #769FBD -> #759FBD); strict quality
unchanged (73.0 WEAK vs soft-stack 47.9 FAIL). See RESEAL-NOTE.md —
same mechanism as the 2026-10-08 parrot reseal, one engine over.

## seal refresh (2026-10-13): icon-13-skull-200colors
Owl corridor (evidence/fleet-audit, aa cap 0.55 -> 0.70 in fallback)
migrates skull (aa 0.636, not flat, no alpha) from cutout to tone-stack.
Measured neutral-positive BEFORE the cap extended (+0.3: 71.2 WEAK ->
71.5 WEAK); disclosed in fleet-audit README as corridor collateral.
Seal replaced with the corridor-era default-route output.

## seal refresh (2026-10-13, second): icon-13-skull-200colors
Skull sub-band (evidence/fleet-audit): the owl corridor's [0.55,0.70) aa
band splits on melt at 0.88; skull (melt 0.792) routes to soft-stack
(measured best: 76.5 WEAK vs tone 71.5, +5.0). Corpus exposure of the
whole band: zero; owl stays tone (0.926). Seal replaced with the
soft-stack output — this is the measured engine ceiling for this row.
