# hatching/sketch routing — measured null (2026-10-09)

Class: mono-ink sketches w/ crosshatch shading + filled body regions
(cx-05 ink falcon, x2-04 doodle mug). Current route: color-soft-stack.
Hypothesis: reroute to the hairline engine (wireframes).

Measured (calibrated A/B judge, same-render protocol):
  cx-05: soft-stack 91.0 / 3194p / 3250KB  vs  hairline 40.3 / 3093p / 584KB
  x2-04: soft-stack 93.2 / 1494p / 1335KB  vs  hairline 47.8 / 830p / 160KB

Hairline collapses the filled regions (sketches are NOT pure wireframe);
~50-point judge melt -> ship nothing. _hairline_candidate correctly
returns False for both inputs (route protection intact — battery engines
unchanged). The sketch class stays documented PASS-WEAK: hatch fidelity
is accepted by the soft-stack route; a true hatching class would need a
stroke MAP engine (path->centerline+width fields), which has no SVG-native
primitive and is queued below the mid-frequency judge channel.

Standing: 3 of the last 4 class-probes ended as measured nulls kept by
pre-registered rules (stone/paper bgm, iridescent despeckle, voxel
auto-palette... and now sketch->hairline). One shipped: soft-stack-bgm.
