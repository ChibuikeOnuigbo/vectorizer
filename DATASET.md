# Dataset documentation

All counts come from `test-assets/manifest.json` (regenerate with
`python3 scripts/dataset/build_manifest.py`), computed from files that
actually exist. No fabricated entries.

## Layout

```
test-assets/images/user-provided/   USER_PROVIDED images (attachments; user check-ins)
test-assets/images/generated/       GENERATED corpus (200 files) + generated_index.json
test-assets/manifest.json           full machine-readable manifest (2,354 entries)
dataset/icons/fontawesome/          OPEN_LICENSE_SOURCE ground-truth SVG pairs
  solid|regular|brands/<slug>/source.svg        original licensed SVG (951 distinct)
  solid|regular|brands/<slug>/input-w64.png     64px raster input (white bg)
  solid|regular|brands/<slug>/input-w128.png    128px raster input (white bg)
  solid|regular|brands/<slug>/input-w256.png    256px raster input (white bg)
  solid|regular|brands/<slug>/input-d128.png    128px on dark (#0b1220) bg
  solid|regular|brands/<slug>/input-blur128.png gaussian blr condition
  solid|regular|brands/<slug>/input-jpeg128.png jpeg q30 condition
  licenses/FONT_AWESOME_FREE.txt    license text
  index.json                        extracted asset index + md5
  renders.json                      per-render records
qa/results/                         per-execution JSON (2,064) + _summary.json
qa/artifacts/                       committed SVG outputs incl. user-image proofs
```

## Sources & licenses

| Family | Provenance | Source | License | Records |
|---|---|---|---|---|
| User attachments | USER_PROVIDED | chat uploads 2026-09-25 | user-supplied | 3 (1 exact duplicate kept as evidence) |
| Generated corpus | GENERATED | `model/make_logos.py`, `model/gen_text_no_bg.py` + deterministic PIL conditions | generated in-repo | 200 base/condition assets |
| Font Awesome Free 5.15.4 | OPEN_LICENSE_SOURCE | `fontawesome-free` pip package (svg files) | CC BY 4.0 icons / MIT code | 951 SVG + 1,800 raster renders |

Acquisition method: package-installed files copied locally
(`scripts/dataset/extract_pairs.py`) — no site scraping, no robots
circumvention, no paywall/auth bypass.

## Generated corpus categories (§3)

24 procedural logo bases × 7 deterministic conditions (blur r2.2, uniform
noise 12.5%px, JPEG q22 round-trip, 32×32 downscale, dark-bg composite,
grayscale, −11° rotation) + edge cases: 1×1, single-color, fully
transparent canvas, 16:1 extreme aspect, 1px thin-stroke rules, 1024×1024
upscale, text image, plus `gauntlet-x1024.png` — the section-5 difficult
composite mixing gradients, nested rings, thin+thick strokes, translucent
overlaps, hex cutouts, text, and scatter at 1024px.

## Rendering method (§7/§35)

Headless Chromium over CDP renders inline SVG grids (10 per row,
deviceScaleFactor 1), PIL slices cells — deterministic per renderer build.
Worker: `scripts/dataset/render_pairs.py` (bounded at 300 pairs this pass;
parametrize limit).

## Augmentation / conditions (§8)

Sizes 64/128/256, backgrounds white/dark, gaussian blur, JPEG q30; the
generated corpus separately covers noise, rotation, grayscale, downscales.
Every derived file has `transformation_applied` + `variant_of` in the
manifest; original reference SVGs are never mutated.

## Duplicate handling (§11)

md5 exact-hash on every record (`unique_md5`: 2,353 of 2,354); same-source
derivatives tracked via `variant_of`, not counted as independent assets.
The two byte-identical user attachments are recorded as
`EXACT_DUPLICATE_KEPT_AS_EVIDENCE`.

## QA/status fields (§32)

Each manifest entry carries provenance, asset_kind
(ORIGINAL_ASSET / DERIVED_TEST_VARIANT), md5, dimensions where applicable,
reference SVG link, expected characteristics, and test_status referencing
the execution family in `qa/results/`.

## Train/test separation (§34)

QA/test seeds live at 100_000+ ranges and never overlap model training
seeds (forever trainer consumes its own generated corpus); holdout report
page `/static/test-report.html` renders a fixed 100-image test set from
seed base 10,000 (never trained on). User attachments are QA-only and
stored separately from any training snapshot under `model_data_snapshot/`
(manual verdicts excluded from automated dataset builds).

## Known limitations

- Font Awesome 5.15.4 is one icon family (single-color glyph style) — other
  open sets (Tabler/Lucide/Heroicons) require network access this sandbox
  lacks; pipeline+licenses scaffolding is in place to extend.
- Rasterized icons at very small sizes lose detail by nature; counted as
  conditions, not defects.
- This sandbox blocks package-registry-external downloads; when network is
  available, `extract_pairs.py` can be extended with additional licensed
  sources to grow Stage B/C corpora.
