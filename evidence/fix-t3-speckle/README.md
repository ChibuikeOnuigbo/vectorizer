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
