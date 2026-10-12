# tone-stack-cost — k-means subsampling speedup + cap veto (2026-10-12)

Follow-up to the micro-detail wash reroute: the rerouted fleet's cost was
high (mandala 13.5s / 14.5MB etc.) because `_trace_color_tone_stack` did
k-means over EVERY pixel at full input resolution.

## Sweep (rerouted fleet, tone-stack engine; full table: tone_cost.jsonl)

| row | default ms | tsample=0.08 ms | Δsim@tsample | cap768+ts08 sim | cap640+ts08 sim |
|---|---|---|---|---|---|
| cx-04 mandala | 13,516 | 4,456 (−67%) | 68.1→68.2 | 17.3 ❌ | 17.2 ❌ |
| x2-04 mug | 12,239 | 2,897 (−76%) | 88.2→88.6 | 29.8 ❌ | 12.4 ❌ |
| cx-05 falcon | 10,632 | 2,329 (−78%) | 81.4→81.6 | 43.5 ❌ | 33.2 ❌ |
| x2-05 pin | 10,743 | 2,201 (−80%) | 83.3→83.3 | 23.6 ❌ | 12.7 ❌ |
| icon-08 star | 11,407 | 4,077 (−64%) | 73.0→73.0 | 5.8 ❌ | 6.5 ❌ |

## Verdicts
- **Working-cap veto (measured)**: resolution IS the fidelity on
  micro-detail wash (each mandala line ≈0.8px at 1024; crush to 640 and
  the trace can't see the lines; ssim collapses to 5.8–43.5). Same physics
  as the soft-stack cap veto in evidence/latency-mandala-null, sharper.
  `_tonecap` kept as a QA-only knob for future sweeps (no-op default).
- **Subsampling shipped**: k-means centers fit on 8% of pixels (floor 20k;
  converged Lloyd iterations are insensitive beyond ~80k samples for 7
  centers — paths/kb move ~1%, strict sim inside ±0.4 on every row),
  full-res label assignment kept, so micro detail is preserved. Latency
  −64..−80% on every rerouted row. Adopted as the engine default.
- Default-route re-verification after ship: mandala 68.2 (4.6s), mug 88.6
  PASS (3.1s), falcon 81.6 (2.3s), pin 83.3 (2.3s), star 73.0 (4.3s),
  prism 87.0 PASS (1.9s), bird 97.2 PASS (soft-stack, untouched).
- Battery 3170/3170: no seal drift (icon-08's converged 7-cluster solution
  is provably stable for this image — identical bytes pre/post; mandala
  class shows its byte-level k-means path DOES vary with sampling, which
  is expected and covered by sim-stability, not seals).

QA knobs: `_tsample` (override the 0.08 default), `_tonecap` (px cap —
vetoed for this engine at 640/768 above; no-op default).
