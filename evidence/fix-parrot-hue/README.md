# fix-parrot-hue — adaptive ink budget for multi-hue flat art (2026-10-08)

## The bug
icon-11 (44-hue flat parrot) routed `color-cutout` flat with the calibrated
`max_inks=3`; `_flatten_colors` merged every >3rd hue into its nearest
survivor: the black beak vanished into dark blue, the white face patch and
black linework became red/green. Structure traced perfectly — hues wrong
(ssim 0.381, T4-extended wall from the ladder).

## The fix (convert.py `_significant_inks` + adapt in `_trace_cutout`)
Count the flattener's own significant hue buckets (FASTOCTREE-12, ≥2%
coverage, bg excluded) and raise the ink budget to it (cap 12), flat
profile only. Explicit user palette knob (`_palette`) overrides the adapt.
- inks=5 measured vs inks=3 baseline: ssim 0.381 -> 0.7131; beak, white
  face, black linework all return; residual: tiny gold accent joins chest.
- Guard rows (leaf/anchor/stripes; buckets <= 3): adapt is a no-op.

## Live proof through shipped default POST
- parrot: 76 paths / 65 colors / 88.6KB / 0.89s; ssim 0.3813 -> **0.7131**
- byte-identical guards: icon-02/03/12 (flat trio), icon-13 skull (photo),
  icon-05 moon (soft-stack), icon-08 star (T3-gated)
- uploads teal/bird: byte-identical to sealed evidence (b81b4d/6b0c26)
- structural battery: 1234/1234 PASS

Files: parrot-fixed.svg, parrot-fixed-render.png (live output).
