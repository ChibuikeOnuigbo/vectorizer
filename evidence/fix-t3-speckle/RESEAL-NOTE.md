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

# reseal note (2026-10-12, second half): icon-08-star-texturebg

Same failure class as parrot, one engine-family over: tone-stack's numpy
float32 k-means (default 8% pixel subsample, seeded rng) returns 84k-sample
cluster means that epsilon-shift across vendor reinstalls — a one-ulp
distance flip relabels near-tie pixels and reflows byte output, even under
the pinned stack (numpy==2.4.6, pillow==12.3.0). Wipe #25 restored the
pinned wheels; icon-08 bytes reflowed from the 166de2acd seal (paths
14993 -> 14857, bg #769FBD -> #759FBD) while every other sealed engine
(soft-stack/cutout/pixel-art up/down scalers) still byte-matches — the
k-means accumulation is the only cross-version-sensitive op on these
paths. convert.py proven byte-neutral on this row: the 2026-10-12
knight/fox corridor edits short-circuit (melt 0.516) before any new
predicate runs, and every reachable gate calls _trace_color_tone_stack
with identical params. The pre-wipe-#25 stack that minted the
166de2acd seal is unknowable (vendor/ does not survive wipes, parrot-
note mechanism); the pinned stack is the arbiter. Quality unchanged by strict audit: soft-stack 47.9
FAIL vs tone-stack 73.0 WEAK (+25.1) on both stacks' bytes. RESEALED
under pip-installed requirements-qapin.txt; treat future sole-icon-08
(or any tone-stack) drift after reinstalls against this note first.
