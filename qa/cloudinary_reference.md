# §20 Reference / Cloudinary workflow comparison (evidence-based)

## What actually exists

1. **USER PIPELINE** — this app (vtracer engine + trained param model), served
   at `:8000`.
2. **REFERENCE/MOCK PIPELINE** — `model/mock_site.py` at `:8100`, a local
   Cloudinary-style mock built earlier in the project to exercise the
   scraper loop. **Its "conversion" is static**: every upload returns the
   same 1-path blue-diamond SVG (`/result.svg`) after an artificial 2.5s
   sleep. It is a UX/workflow stand-in, NOT a real vectorizer, and it is
   labeled as such everywhere below.
3. **Cloudinary (the real product)** — earlier design research informed this
   app's slider labels (`colors/detail/smoothness`), preset naming, and
   best-tier picking (`app/convert.py` comments). A live Cloudinary
   side-by-side is **not claimed**: this sandbox blocks outbound HTTPS to
   that service, and no Cloudinary credentials exist here.

## Measured side-by-side (real browser, same input image)

Input: `test-assets/images/user-provided/teal-orbit-logo.png` (676×369 PNG,
transparent). Driver: `qa/qa_reference_workflow.mjs` (Chromium/Playwright);
artifacts `qa/screenshots/reference/` + `reference-comparison.json`.

| Aspect | USER PIPELINE (`:8000`) | REFERENCE/MOCK (`:8100`) |
|---|---|---|
| Upload UI | dropzone + picker, auto-convert on select | plain file input + Convert button |
| Conversion time | 1,687 ms (upload → result view) | 2,682 ms (includes the artificial 2.5 s sleep) |
| Result correctness | real vector trace of the input (5 paths, ~11.5 KB) | identical static diamond for **any** input (by mock design) |
| Output delivery | blob URL preview + `#downloadBtn` (generated SVG) | direct `/result.svg` download link |
| Workspace flow | Simple/Advanced choice modal after convert | none |
| Persistence | IndexedDB project + source blob (regression-tested) | none |
| Console errors | 0 | 0 |

## Interpretation (clearly labeled as interpretation)

- The mock is only useful for validating scraper-like flows and a
  Cloudinary-*inspired* interaction outline; it must never be cited as a
  quality reference. Quality references in this repo are the 951 open-license
  authored icon SVGs (`dataset/icons/fontawesome/`).
- The real Cloudinary service could not be reached from this environment —
  recorded as a blocker, not as a comparison result.
