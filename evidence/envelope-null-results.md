# envelope optimization — measured null results (2026-10-08)

Two T5-envelope/latency ideas were pre-registered, measured, and REJECTED
with numbers; code untouched (convert.py byte-identical to 5f4b25347).

## Serial latency baseline (honest, no pool contention)
icon-13 10.3s / icon-14 9.2s / icon-15 10.9s (the 13-32s earlier numbers
were 3-worker pool + trainer contention). Soft-stack heavy icons ~1s.

## Profile of the 11.6s on icon-13 (cProfile)
- vtracer native C calls: 8.76s (75%) — cutout 6.3s + soft-stack A/B 2.4s
- regex post-passes (_tidy/_round_path_data/... on 4.6MB strings): ~1.5s
- the rest: A/B judge renders, analysis.

## REJECTED idea 1: skip the soft-stack A/B half for the T5 regime
Measured judge margins (sv > base rule needs +5):
  icon-13: soft-stack 81.4 vs cutout 78.8 (ss wins +2.6)
  icon-14: ss 72.9 vs 68.8 (+4.1)   icon-15: ss 87.0 vs 83.1 (+3.9)
Soft-stack is the objectively better candidate on T5 and falls just short of
the +5 fallback. Pre-deciding would change outputs honestly indistinguishable
from a judge flip — NOT shippable without a judge recalibration.

## REJECTED idea 2: DOM merge of same-fill sibling paths (cutout only)
Fold potential: 7,939 -> 7,908 elements (0.4%) because near-every path
carries a unique style key; bytes GREW (translate absorbed into coords);
and renders were NOT pixel-exact (mae 0.07-0.21, max 200): vtracer cutout
tiles are not perfectly disjoint — same-fill repaint order shifts AA seams.
Killed. Function removed; vectorize() untouched.

## What stands (already shipped)
palette collapse (fills 8k->414-636), T3 speckle gate (16k->4.7k paths),
dims stamp, adaptive inks. Latency beyond this needs a downscale-trace +
upscale-judge strategy measureable on the full sweep corpus — queued behind
corpus rebuild (trainer regenerating; 399-row sweep is the respecting
acceptance surface for that change).
