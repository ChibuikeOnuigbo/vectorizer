# bg-remove ladder — part 1 (2026-10-07)

User's test: generate icons with AI across a difficulty ladder and see whether
the shipped model **understands the subject, removes the background color,
and creates a clean SVG**. This is part 1: tiers T1—T4 (10 icons); tier T5
(~200-color maximalist, icons 11–15) is queued for the next turn (generator
rate limit 10/turn). All conversions through the shipped endpoint, default
POST, no fields — the same bytes the UI sends.

## Contact sheet

`contact-sheet.png` — per icon: INPUT | SVG OUTPUT render | key numbers.

## Measured wall-map (numbers in verification-part1.json)

| tier | icons | bg removed? | fidelity (ssim/edge) | SVG sanity | verdict |
|---|---|---|---|---|---|
| T1 flat bg | 01 rocket | **yes** — but 402 fragment paths | 0.366 / 0.005 | 104KB | strip works, subject edges shredded |
| T1 flat bg | 02 leaf | **no** (navy plate kept) | 0.695 / 0.232 | 21KB, 6 paths | clean SVG, bg not stripped |
| T1 flat bg | 03 anchor | **no** (mint plate kept) | 0.527 / 0.170 | 35KB, 7 paths | clean SVG, bg not stripped, and corners of plate clipped |
| T2 gradient | 04–06 | **half** (bg collapsed to a patch behind the subject) | 0.092–0.165 / ≤0.05 | 402–594KB, 800–1652 paths | FAIL |
| T3 textured | 07–09 | **no** (texture traced as content) | 0.004–0.135 | **14,187–16,272 paths, 4.5–7.7 MB, 9–15 s** | catastrophic — unusable output |
| T4 multi-color 15+ | 10 | no (lime plate kept) | 0.906 / 0.719 | 153KB, 159 paths | PASS |

## Findings (honest, all reproducible)

1. **BG removal is inconsistent within the same tier.** Icon 01's yellow bg
   was stripped to transparency while icons 02/03/10 kept a full-canvas
   background plate. Routing (soft-stack vs cutout A/B), not user intent,
   decides whether "the bg is removed".
2. **Stripping on imperfect-flat backgrounds shreds the subject.** The AI's
   "flat" yellow carried generator mottle; the strip + trace path turned it
   into 402 fragments and lumpy subject edges (edge_f1 0.005).
3. **Gradient backgrounds leave a half-stripped patch** behind the subject
   and cost 0.8–1.7k paths while still missing fidelity badly (mae 90–111).
4. **Textured backgrounds explode**: 14k–16k speckle paths in 9–15s for a
   1024px image — file sizes (4.5–7.7MB) no icon user can consume, and the
   halftone case additionally lost its subject almost entirely (ssim 0.004).
5. **Strength reconfirmed**: clean multi-color flat art (even 150+ colors)
   vectorizes beautifully (icon-10 PASS at 0.906).
6. **Measurement artifact disclosed**: first T3 renders were blank because
   the audit's CDP renderer hits a >2MB data-URL transport cap; fidelity was
   recomputed on true renders (file:// transport) before any verdict — the
   catastrophes are in the SVGs, not the renderer.

## Answers to "can it remove the bg and create svg?"

- On its **home turf** (icon art on clean flat/alpha bg, like your uploaded
  teal/bird): yes, calibrated-pass.
- **Removing** the bg: only sometimes, and un-requested; when it fires on
  imperfect-flat art it fragments the subject.
- **Textured or gradient bg**: currently outside the model's safe zone —
  half-strips or speckle-traces. Noted as ladder wall T2/T3 for the next
  improvement cycle (alongside the remaining FAIL rows of sweep v7).

Next turn (generator budget reset): T5 — three ~200-color maximalist pieces
(skull graffiti, kaleidoscope owl, mosaic phoenix).
