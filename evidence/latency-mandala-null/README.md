# mandala latency — measured nulls (2026-10-11)

Task: attack the documented cx-04 mandala latency (16.7s record; 4.9-6.5s
re-measured on today's sandbox; profile: 4.67s of 6.25s inside ONE native
vtracer call at the 640px working cap, ~0.7s Python re/parsing).

Profile (cProfile, shipped route, cx-04):
- vtracer native call 4.67s / 6.25s total (75%) — the C-bound floor
- re/lambda + findall + listcomp ~0.67s (11%) — documented, not touched
  (byte-identical-output refactor possible, est. saves ~half; parked)

## Null 1: max_iterations sweep (knob is dead)
mi ∈ {8,16,24,30,48} × 5 soft-stack rows: output byte-IDENTICAL at every mi
(paths/kb unchanged), ms within ±5% noise. vtracer saturates its iteration
budget early on this class. No latency lever here. Removing the knob sweep
from consideration permanently.

## Null 2: trace-cap 640→512 (pre-registered rule: adopt iff Δsim ≥ −1.0 on
every soft-stack fleet row; fleet = rows the soft-stack engine owns)
Time at 512: −60% cx-04, −43% cx-05, −23% x2-04, −30% x2-05, −35% x2-06.
But strict sim (fixed-ssim audit, composite incl. midfreq_rec50):

| row | 640 | 512 | Δ | 448 |
|---|---|---|---|---|
| cx-04 mandala | 49.2 (FAIL) | 41.7 | −7.5 ❌ | 38.0 (−11.2) |
| cx-05 falcon | 71.9 | 68.7 | −3.2 ❌ | 66.4 |
| x2-04 mug | 75.8 | 74.3 | −1.5 ❌ | 73.9 |
| x2-05 pin | 75.2 | 69.7 | −5.5 ❌ | 67.9 |
| x2-06 castle | 86.7 | 86.3 | −0.4 ✓ | 83.6 (−3.1) |

VETO: 4/5 rows exceed −1.0 binding channel = ssim12 (the class's fidelity
lives exactly at the sub-640px structure the cap preserves). 640 stays.

## Kept byproducts
- `_softcap` QA knob in `_trace_color_soft_stack` (default 640 = byte-
  identical to shipped, verified in-row; the hardlock strip drops it from
  client params — production routing untouched).
- Strict-sim baseline for the soft-stack fleet under the fixed-ssim judge
  (mandala 49.2 FAIL-class honestly recorded; castle 86.7 PASS).
- Baseline sha12 of shipped svgs per row available in turn log if a future
  engine change needs drift guards on this fleet (not sealed: non-evidence
  outputs regenerate per-run).

Conclusion: mandala-class latency is backend-bound (single visioncortex
pass at 640²). The honest remaining levers are (a) a faster native tracer
backend (dependency-level work, blocked endpoints today) or (b) the
corpus-retrain route cycle to move the class off soft-stack. Both are
infra-scale; documented here as the terminus of cheap levers.

## Adjunct shipped same turn (byte-identical perf): bg-pop scan reorder
The soft-stack bg-mass pop reordered to scan coordinates only for near-white
candidates (sentinel drop uses rgb alone; the -6-figure float scan hit all
5,220 paths for ~1 candidate). cx-04 -13% (4.90->4.27s), castle -11%, pin
-13%, others within noise; svg byte-identical on the whole 5-row fleet
(sha12 pinned in turn log). `_round_path_data` kept as-is: measured
301,923 substitutions on cx-04 change ZERO tokens (pp=10 output is already
%g-clean); memoization measured slower (0.396 vs 0.305s on 178k uniques) —
documented, not shipped.
