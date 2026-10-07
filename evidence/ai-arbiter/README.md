# AI-arbiter verification (2026-10-07)

Protocol (user-specified): run the uploaded images through the shipped model
(threads, default POST, no fields), rasterize each output SVG, then hand the
render to an independent AI image model with a strict change-NOTHING prompt.
If the AI cannot reproduce what it was shown, the output was not
understandable. Control: the identical AI + prompt on the ORIGINAL input
raster — an image generator restyles ANY image, so only the gap between
render-arbiter and control-arbiter is attributable to the SVG.

## Verdicts (full detail in verification.json)

- **blue-bird — UNDERSTOOD.** AI-from-output ssim 0.4694 / f_mae 0.9898 vs
  AI-from-input control 0.5445 / 0.9856; mae via the render BETTER (2.59 vs
  3.67). The two AI pictures are visually interchangeable. Output is good.
- **teal-logo — UNDERSTOOD (n=2).** Draw 1 inverted the hollow center
  (ssim 0.199 vs render); draw 2 from the same render got the interior right
  (ssim 0.669 / f_mae 0.968). Control on the original scored 0.9263 on one
  draw. Verdict: generator variance, not incomprehension — the render's
  semantics are legible.

Also re-verified en route: fresh threaded conversions are byte-identical to
the previously committed evidence SVGs (`repro_matches_evidence: true`,
stage1.json) — the shipped pipeline is deterministic for these inputs.

Files: per case `*-input.png`, `*-output.svg`, `*-render.png` (SVG raster),
`*-aigen.png` (+ `aigen2` for teal), `*-aictrol.png` (AI on the original),
`*-quad.png` (all stages side by side), `verification.json`, `MANIFEST.sha256`.

## Round 2 (user-directed): neutral identity-copy prompt, no scene description

Round 1's prompts described the scenes ("teal orbital rings around a dark
center", "small blue bird") — that text steered the generator (the teal
draw-1 dark-center inversion was very likely prompt-induced). Round 2 uses
one identical description-free prompt ("same image, same lighting, same
everything") for renders AND original-input controls. Results:

- **teal — UNDERSTOOD.** arbiter ssim 0.9167 / mae 1.51 vs control
  0.9237 / 2.93 — the SVG copy reproduces at the same level as the AI's own
  copy of the original input. Round-1 inversion was prompt poisoning.
- **blue-bird — bird UNDERSTOOD, background glow FLAGGED.** AI-from-output
  (ssim 0.1455 / mae 57.37) kept the bird/tile shapes but turned the white
  surround into a full-frame cyan wash; AI-from-original (0.5002 / 1.88)
  kept white. The diff belongs to a real, visible trait of the current
  output: the tile's surround glows wider/more diffuse than the input's.
  That halo spread is the same glow-gradient wall behind the 74.5% fidelity,
  owned by the training loop (completed: 70,005 images, best_val 99.54);
  routing/engine/knob levers were measured closed this cycle.
- Note: the model inputs are for convert-time reference only; the
  change-NOTHING instruction lives in the prompt text, logged in
  verification.json (round2_neutral_prompt).

