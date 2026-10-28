# icon-x2-set — second wave of hard icon classes (2026-10-09)

8 newly-generated REAL icon classes through the shipped default POST,
3.164-gate state. renders use file:// CDP (transparent page -> white bands
are the 1408x768 aspect letterbox of the QA render div, NOT product output).

| probe | class | engine | paths/fills | kb | ssim | verdict |
|---|---|---|---|---|---|---|
| x2-01 star | neubrutalist | cutout | 114/54 | 154 | 0.998 | WEAK-PASS (shadow rougher+doubled) |
| x2-02 bee | sticker cutout | cutout | 18/9 | 37 | 0.916 | WEAK-PASS (wing fills washed) |
| x2-03 anchor | lineal-color | cutout | 5/4 | 35 | 0.966 | **PASS** |
| x2-04 mug | doodle+crosshatch | soft-stack | 1494/417 | 1336 | 0.971 | PASS-WEAK (paper texture mush) |
| x2-05 pin | metallic enamel | soft-stack | 2321/52 | 1872 | 0.902 | WEAK-PASS (pin OK, stone bg mottled) |
| x2-06 castle | diorama game icon | soft-stack | 7755/407 | 3637 | 1.000 | **PASS** |
| x2-07 heart | voxel iso | cutout | 57/42 | 119 | 0.889 | WEAK-PASS (cubes merged) |
| x2-08 badge | holo iridescent | cutout | 1645/411 | 1067 | 0.973 | WEAK-PASS (bands+confetti dots) |

No HORRIBLE. Recurring honest weakness family: NOT-subject but
TEXTURE-in-bg artifacts (stone/paper mottle class, hx-07-same-family) and
iridescent/holo ramp banding. Subject structure always survives.
