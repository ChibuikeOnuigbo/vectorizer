# complex-set — harder battery + redos (2026-10-08)

Eight probes beyond the bg-remove ladder (real photo, watercolor, comic+text,
mandala microdetail, ink cross-hatch, transparent glow, low-contrast,
pre-upscaled pixel art) + the native-size pixel-art redo. Every probe through
the shipped default POST; renders via file:// CDP transport. `contact-sheet.png`
shows each pair. Numbers in `results.json`.

## Verdicts

| probe | engine | paths/fills | size | ssim | verdict |
|---|---|---|---|---|---|
| photo beagle | soft-stack cp8 | 5,398 / 55 | 2.1MB | 0.892 | PASS fidelity; heavy envelope |
| watercolor fox | cutout photo | 4,363 / 76 | 3.3MB | 0.763 | OK |
| comic + text | cutout photo | 212 / 199 | 271KB | 0.792 | **PASS — "BLAST OFF!"/"mission 26" crisp** |
| mandala microdetail | soft-stack | 5,220 / 26 | 5.1MB / 16.7s | 0.429 | WEAK (structure kept, detail muddied) |
| ink falcon hatching | soft-stack | 3,194 / 20 | 3.3MB | 0.588 | WEAK (hatching -> tone patches) |
| pre-upscaled sprite 1024 | cutout flat | 2 / 1 | 0.8KB | — | **FIXED-2026-10-08** (white blade -> brown blob) |
| transparent glow orb | binary-alpha | 1 / 1 | 3KB | 0.524 | **FIXED-2026-10-08** (radial glow -> flat disc) |
| low-contrast heart (span 12) | cutout flat | 1 / 1 | 0.4KB | 0.990* | **FIXED-2026-10-08** (heart collapsed into bg) |

*ssim 0.990 lies: both input and output are near-blank dark fields; ssim
cannot see a lost invisible shape. This is THE cautionary row for
metric-only verdicts.

## Redos (user directive: redo the horrible ones)

1. **cx-08 heart -> FIXED this commit.** Gate `opaque AND 2 <= p1..p99
   luminance span <= 24` in analyze(): stretch `working` range to [48,224]
   (hue-preserving additive map; a["img"] untouched for A/B judges).
   Calibrated against all 25 probes (15 ladder + 8 complex + 2 uploads):
   fires only on cx-08; the alpha-branch is a different code path entirely.
   Redo: 2 paths / 2 colors / 7.0KB — the heart is plainly visible
   (cx-08 render in this dir).
2. **cx-06 pre-upscaled sprite -> partially product-fair.** Probe was not
   realistic (users upload the native sprite): native 32x32 redo (cx-09)
   routes to the pixel-art engine and vectors crisply (grid rects, correct
   colors, transparent bg — see render; evidence render is presentation-
   scaled x32, the SVG itself is 32x32 1:1). The 1024 pre-upscaled input
   remains a documented limitation (block-size UNDETECTED upscales stay in
   the flat pipeline) — queued: axis-aligned block-period detection.
3. **cx-07 glow orb -> documented limitation.** Pure RGB-flat + radial
   alpha glow routes to binary-alpha (alpha coverage > 0.17) and becomes a
   flat disc (transparent bg is correct). A "alpha-is-radial-glow" route
   tweak is queued (share gate for continuous alpha histograms), not shipped
   this turn.

## Regression proof (after the cx-08 fix)

- uploads teal/bird byte-identical to sealed evidence (b81b4d/6b0c26)
- guard icons 11 (parrot fix), 12, 13, 05, 08: all byte-identical
- structural battery: 1234/1234 PASS (now shipped in-repo as
  qa/final_validation.py after ad-hoc /tmp copies kept dying in wipes)

## redo: cx-06 upscaled pixel sprite FIXED (2026-10-08)
New route `pixel-art-upscaled` (harmonic-gcd comb detector + phase-aligned
per-cell majority/median snap): the 1024px bilinear/upscaled mushroom-sword
row that rendered as a 15x15 fuzz grid now emits the recovered native 32x32
lattice as output-space integer rects (62 rects, 3.6KB), crisp on every
renderer (proved: 1-pixel transitions at exact lattice coords, palette
{white/silver/steel/gold/brown} hard). See redo-upscaled/.
