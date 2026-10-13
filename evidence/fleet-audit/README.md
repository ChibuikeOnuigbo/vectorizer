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

## camera + voxel bands (2026-10-13): two more WEAK rows un-parked

WEAK-band engine probes (cutout/soft/tone forced per row) surfaced two
flat+no-alpha photo-content rows mis-owned by their current family, with
the discriminator being distinct-color count (128px unique RGB):

- camera band (in color-soft gate; flat, melt 0.05..0.10, aa >= 0.25,
  colors128 >= 3000): icon-06 camera — shipped soft-stack 83.5 WEAK ->
  tone-stack 92.9 PASS (+9.4). Exposure 0/2,757 corpus rows. Bird has
  IDENTICAL aa (0.302) but colors128 721 -> glow regime protected (soft
  97.2 vs tone 63.5 measured); dog excluded by aa floor (0.164; soft
  owns 91.9 vs 89.5 if annexed, -2.4). Composites: icon-06-camera-*
  (speckled bg -> smooth gradient bands).
- voxel band (in fallback corridor; flat, melt 0.05..0.10, aa < 0.12,
  colors128 >= 3000): x2-07 voxel-heart — shipped cutout 81.6 WEAK ->
  92.0 PASS (+10.4). Post-ship mechanism: clause fires as melt-route
  recursion base; judge picks soft-stack (engine-forced tone was 95.4).
  Corpus exposure 1/2,757: gen-17jpeg measured 89.3 -> 95.9 PASS (+6.6,
  no regression). Dog excluded by aa cap; bird/glow by color floor.
  Composites: x2-07-voxel-heart_* (voxel face shading restored).

Remaining measured ceilings, all parked (no collateral-free corridor or
engine ceiling): skull 71.5 (soft 76.5 max measured), star 73.0
(bands-independent), falcon 81.6 / pin 83.3 (already best engine),
mandala 68.2 (paper-wash flattening), phoenix 59.6 (no engine passes —
vtracer-core classwork). Battery 3172/3172 with server-restart-before-
battery protocol (the 654d9e8da battery silently passed on a stale pre-
owl server; skull migrated legitimately, seal refreshed 892d44b51).
