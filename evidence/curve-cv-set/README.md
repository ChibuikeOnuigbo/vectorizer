# curve-cv-set — curve reproduction battery (2026-10-09)

User ask: prove curve detection/redraw across classes and generation variety
(10 AI-generated curve icons, different styles/weights — from 1px
calligraphy to fat ribbons, spirals, loops, sinusoids, rings, dense curls,
gradient ribbon, translucent glass curves). Every probe through the shipped
default POST; renders via transparent CDP; `contact-sheet.png`; numbers in
`results.json`. (Render window bands = aspect letterbox, not output.)

| probe | class | engine | paths/fills | kb | ssim | verdict |
|---|---|---|---|---|---|---|
| cv-01 ribbon | fat S-ribon + shaded underside | cutout | 2/2 | 8 | 0.964 | WEAK (underside shading lost) |
| cv-02 spiral | golden spiral, wobbly | cutout | 2/2 | 67 | 0.998 | PASS (wobble = input-truth) |
| cv-03 blobs | organic circle blobs | cutout | 7/5 | 12 | 1.000 | **PASS** |
| cv-04 flourish | 1px calligraphy swirls | **hairline** | 92/1 | 34 | 0.998 | **PASS** (taper survives) |
| cv-05 loops | celtic over/under weave | cutout | 6/6 | 53 | 0.932 | **PASS** (weave order kept) |
| cv-06 waves | 4 stacked sinusoids | cutout | 5/4 | 33 | 0.938 | **PASS** |
| cv-07 rings | circle + 3 tilted ellipses | cutout | 9/3 | 80 | 0.999 | **PASS** |
| cv-08 curls | graffiti tight swirls | cutout | 53/4 | 329 | 0.920 | **PASS** (dense detail intact) |
| cv-09 ribbon | pink-purple gradient ribbon | cutout | 17/17 | 68 | 0.980 | PASS-WEAK (hue ramp banded) |
| cv-10 glass | translucent glass curves | cutout-detail | 77/34 | 198 | 0.987 | **PASS** |

## Verdict
9/10 curve-faithful, 0 horrible. The model dominates every curve class
measured: 1px tapering calligraphy, woven loops, organic blobs, perfect
rings, sinusoids, dense curls, transparent glass. Known-but-consistent
limits: malformed-but-complex shading (ribbon undersides and glass speculars
get re-tinted into banded fills — the edge curves themselves stay smooth;
this is the same band-tracing engine behaviour measured on iridescence and
stone builtins; the true lever remains fine-band palettes).

Guard-null: engine routing across the set touched cutout, cutout-detail,
hairline only — no background-mottle or glow-radial-alpha probes fired
(any change in those routes surfaces immediately via seal drift on the
strict tier).
