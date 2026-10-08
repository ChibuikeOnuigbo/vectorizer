# reseal note (2026-10-08): icon-11-parrot-multicolor

Wipe #17 wiped vendor/, and pip reinstalled at unknowable pre-wipe
versions. Current stack (pinned in requirements-qapin.txt) reproduces
05/08/13 seals byte-identically but reflows parrot (paths 73->76, fills
44->65, render mae 8.27 / 7.5% pixels shifted): vtracer quantize internals
are version-dependent for 200-color inputs. convert.py proven untouched on
the parrot path (git diff 91bbee86e shows only the upscaled-pixel-code
addition; the probe returns None for parrot -> stamped color-cutout).
RESEALED under vtracer==0.6.15; future byte-drift after vendor reinstalls
should be judged against the pinned stack first.
