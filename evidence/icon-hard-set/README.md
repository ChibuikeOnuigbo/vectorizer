# icon-hard-set — complex but ACTUAL icons (2026-10-08)

User direction: complex probes must be real icon types, not photos/water-
colors. 8 hard icon classes through the shipped default POST; renders via
file:// CDP transport; `contact-sheet.png`; numbers in `results.json`.

| probe | class | engine | paths/fills | kb | ssim | verdict |
|---|---|---|---|---|---|---|
| hx-01 ELITE badge | text badge + stars | cutout | 194/91 | 282 | 0.606 | **PASS** (text + stars crisp) |
| hx-02 iso chest | isometric game icon | cutout | 90/58 | 157 | 0.492 | WEAK-PASS (shading simplified) |
| hx-03 glass sun | glassmorphism | soft-stack | 1,577/56 | 874 | 0.904 | PASS-WEAK (frost flat but reads) |
| hx-04 hummingbird | monoline origami | cutout | 15/11 | 52 | 0.695 | **PASS** (single-line intact) |
| hx-05 fox swirl | negative space | cutout | 4/3 | 18 | 0.702 | WEAK (inner wisps merged into one) |
| hx-06 coffee | duotone | cutout | 25/17 | 35 | 0.728 | **PASS** |
| hx-07 rocket pin | in-icon halftone | soft-stack | 3,399/87 | 1,443 | 0.806 | **PASS** (dots survived) |
| hx-08 lion emoji | dense emoji detail | soft-stack | 3,777/96 | 1,543 | 0.883 | **PASS** (mane/eyes/cheeks crisp) |

**No HORRIBLE row (no redo needed).** Negative-space inner-wisp merging
(hx-05) is the softest row: 4 paths reduced two white tail wisps into one
question-mark shape — logged as negative-space simplification, not a crash.
Halftone-shadow inside an icon (hx-07) survived at 3.4k paths; dense emoji
detail (hx-08) at 3.8k — both visually faithful.

Proof: uploads byte-identical to sealed evidence (b81b4d / 6b0c26);
structural battery 1234/1234; code unchanged from 91bbee86e.
