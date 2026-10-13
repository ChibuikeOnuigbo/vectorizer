# fleet audit 2026-10-12 — first all-fleet default-route leaderboard

All 42 evidence rows (bg-remove-set, complex-set, icon-x2-set,
curve-cv-set) driven through the SHIPPED default route (+ strict
similarity audit, edge_f1 tol 1, calibrated verdicts). Purpose: the
fallback/melt corridors were previously drift-checked per-family only;
this table makes reroute exposure measurable fleet-wide in one place.

Headline (engine = default-route stamp; sim = strict visual_similarity_pct):
- FAIL: icon-07 knight 48.8 (soft-stack), icon-15 phoenix 59.6 (cutout),
  cx-02 watercolor-fox 66.5 (cutout), cx-04 mandala 68.2 (tone-stack)
- WEAK: skull 71.2, star 73.0, owl 74.6, falcon 81.6, voxel-heart 81.6,
  pin 83.3, camera 83.5
- PASS: remaining 31 rows, >= 85.8

Actions taken from this table (same day):
- knight: texture corridor in melt branch (fallback-gate-extension
  addendum): 48.8 -> 76.5 under color-tone-stack (+27.7).
- fox: aa-band corridor in fallback block: 66.5 -> 76.5 (+10.0).
- mandala: parked — paper-wash flattening is band-count-independent
  (tone_bands 7..10 sweep in tone-stack-cost/bands_sweep.jsonl; keep 7).
- phoenix: parked — no engine passes (cutout 59.6 / soft 65.8 / tone
  64.3); engine-quality ceiling, needs vtracer-core classwork. Gates
  deliberately do NOT reach for it (aa 0.736 excluded from fox corridor).

Row data: fleet_audit.jsonl (name, fleet, engine, sim, verdict, paths, kb).

## owl corridor (2026-10-12, post-leaderboard action)

WEAK-band probe of the 200-color mosaic family: icon-14 owl (aa 0.643,
not flat, no alpha) scores cutout 74.6 / soft 81.8 / tone-stack 90.9.
Corridor = extend the fox aa-band cap from 0.55 to 0.70 in the fallback
block (fallback-gate-extension comment carries the rationale). Exposure
proof: 0/2,757 corpus rows in [0.55, 0.70); evidence collateral: only
skull (aa 0.636, comes along neutral +0.3: 71.2 -> 71.5). castle
(aa 0.709) stays OUT on soft-stack 86.7 PASS; phoenix (aa 0.736) stays
parked untouched on cutout FAIL. Visual proof:
icon-14-owl-200colors_similarity.* (stained-glass mosaic preserved vs
cutout palette fragmentation). Shipped: owl 74.6 WEAK -> 90.9 PASS
(+16.3). Remaining WEAK-band ceilings measured this round: skull 71.5
(soft-stack 76.5 max — no no-regression corridor exists to it), star
73.0 (bands-independent).
