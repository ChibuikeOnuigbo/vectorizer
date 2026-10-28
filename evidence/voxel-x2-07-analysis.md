# x2-07 voxel heart — measured analysis (2026-10-09)

Claim checked: "cubes merged" (weak-pass row).
Facts:
- Input faces are SOFT-shaded (mean |grad| 2.71, only 0.9% strong edges,
  334 distinct 4-bit inks): the input itself has no crisp cube lattice
  (comb period ~28px but borders are gradient-blended).
- Default trace: 57 paths/118KB/judge 96.2/ssim12 0.889.
- colors=32/64/96: 269 paths/judge 96.5 — the knob buys +0.3 judge for
  +212 paths (measured: all palette sizes land on the same trace).

Outcome: KEEP default route. The cube-face merging is real (ssim drop +
my eyeball) but the calibrated judge blocks judge it visually
near-identical; the 28px face scale sits at/under the judge's 12px block
resolution, so the +212-path cost has no measured reward.
Standing calibration finding (for the corpus-rebuild cycle): the block-ssim
judge is BLIND to mid-frequency structural merges at ~block scale
(same lesson as x2-08 confetti and the band-tracing pathology) — the
second-order task is a mid-frequency judge channel, NOT yet another
engine route. Documented; no code shipped.
