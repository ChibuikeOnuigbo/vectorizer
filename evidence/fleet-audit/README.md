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
