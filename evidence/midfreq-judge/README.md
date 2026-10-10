# midfreq-judge — mid-frequency judge channel (2026-10-10)

Task: close the measured 12-64px judge blind spot documented twice this
week (x2-07 voxel: 28px cube-face merges scored judge-96.2 while visually
merged; x2-08 confetti collapse blind at block scale; cv-01 shading
interiors dropped at ssim .967). Result: **shipped**, as
`midfreq_rec50` in `qa/similarity_audit.py`, wired into the strict
composite `similarity = min(f_mae, ssim12, silhouette_iou, midfreq_rec50)`
and into `qa/runner.py` strict_channels.

## Channel spec (elected, only positive-margin variant of its family)
128px LANCZOS grid → per-channel |grad|, max over RGB (melt-share guard:
hue-swap edges share luminance) → input ridge mask at 0.5*mean amplitude →
**amplitude-weighted (p=1) recall** of input ridges in the output, 1-cell
dilation tolerance. Weighting p=1 is the measured physics: p=2 collapses
(weak_max 0.995 — merged rows keep their dominant outer outline; the lost
structure lives at mid amplitude).

Separation on the 20-row pre-registered corpus: blind-weak 0.816..0.953 |
clean 0.961..1.000 | gray 0.985..1.000 → margin **+0.008**. The margin is
thin by design honesty: the channel is a mild tug inside min() (~1-3 pts
on flagged rows), never a verdict hammer. Corpus: 4 blind-weak / 13 clean /
3 gray rows pinned by the visual READMEs of curve-cv-set, icon-x2-set,
bg-remove-set (manifested in this dir).

## Measured outcome (final composite, audit() shipped path)

| row | cluster | sim before | sim after | verdict shift |
|---|---|---|---|---|
| x2-07 voxel (faces merged) | blind-weak | 87.2 | **81.6** | PASS→WEAK ✓ (the point) |
| cv-01 ribbon (shading dropped) | blind-weak | 96.7 | 94.3 | none (honest tug −2.4) |
| cv-09 ribbon (banding) | blind-weak | 94.9 | 94.9 | none (min already mae-bound) |
| x2-08 holo (confetti) | gray* | 85.8 | 85.8 | none (out of band by design) |
| 13 clean rows | clean | — | **all unchanged** | zero false flags |
| x2-04/x2-05/x2-02 | gray | 75.8/../95.5 | 75.2 WEAK / 95.5 | none from mfr (mfr 0.985-0.996) |

\* x2-08's loss lives below the documented band (<12px sub-band texture +
banding taste); honest channels must not be tuned to it — documented scope.

## Rejected candidates (same corpus, margins)
unweighted recall/F1 @t30: −0.433 (bg-mottle confound: AI-input background
grain ridges never reappear in clean vector output → icon-02-leaf clean
0.433, the key finding of this calibration) · NCC of gradient-energy fields
−0.101 · NCC of local-std maps −0.061 · energy ratio −0.543 · edgeF1@t50
−0.059. Full per-row sweep in `calib.json` (script `scripts/midfreq_calib.py`,
cache /tmp/mfcache is harness-volatile).

## Incidental harness/scoring fixes this work exposed
1. **ssim12 normalization bug (pre-existing)**: callers pass 0..255 luma but
   constants were [0,1]-space → contrast/structure terms collapsed to ~1e-3
   on any real-variance icon (cv-02 measured 0.022 vs true 0.912). All
   strict audits/runner rows historically consumed this; direction was
   over-strict (conservative). Fixed at entry of `ssim_block` (normalize to
   [0,1]). "OLD sim" column above = ssim-fixed, pre-mfr composite.
2. **CDP render flakiness on multi-MB SVGs**: data-URL navigation silently
   dies (castle 4.8MB html, pin 2.4MB → blank canvas, iou 0/mae 100-185,
   sieved as 0.0 rows in the first calib run). Fixed: >1.5MB payloads go via
   `Page.setDocumentContent` (CDP message, ws max 64MB) + parse budget
   scales with size + blank-canvas retry for path-heavy svgs.
3. Provenance note: x2 README "ssim" column (castle 1.000, pin 0.902) came
   from an earlier bespoke battery script with different windowing; the
   strict audit ssim12 is now the single calibrated definition (castle
   86.7, pin 75.2 under it — verdicts unchanged: castle PASS, pin WEAK as
   the visual review already held).

Files: `calib.json` (candidate sweep), `final-audit.json` (shipped
composite, 20 rows), this README. No engine code touched; no ship-route
threshold changed; the shipped `_ab_svg_score` A/B arbitration judge is
out of scope here (its blind spot is a separate measured finding).
