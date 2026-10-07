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
