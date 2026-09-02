# Graph engine evaluation

Status: implementation decision, reviewed 2026-09-01

## Decision

Keep React Flow and ELK for the production front door's primary 2D workbench.
The overlap in the reported UnaMentis view was an integration defect, not an
engine ceiling: nodes and edges were sent to ELK, but relationship labels were
not; ELK's routed bend points were then discarded and React Flow independently
placed labels at visual midpoints. The layout engine could not avoid objects it
had never been told existed.

The corrected implementation produced zero node/node, label/node, and
label/label intersections in the rendered audit matrix covering Overview,
root and nested selections, Flow, and Support at wide desktop, tall desktop,
and phone dimensions. This is enough evidence to continue with the present
stack, not a claim that every future graph is solved.

Treat 3D as an optional projection of the same semantic scene, not a replacement
for the readable 2D answer surface.

## What the current stack can do

The installed viewer uses `@xyflow/react` 12.10.0 and `elkjs` 0.9.3.
[React Flow](https://reactflow.dev/learn/layouting/layouting) supplies the
interactive canvas, selection, controls, custom nodes and custom edges.
[ELK Layered](https://eclipse.dev/elk/reference/algorithms/org-eclipse-elk-layered.html)
supplies node coordinates, orthogonal edge routes, bend points, ports, label
positions, spacing, compaction, disconnected-component packing, and
aspect-ratio-aware layout.

Upstream [`elkjs`](https://github.com/kieler/elkjs) is now 0.11.1. Because the
package is below 1.0, the existing `^0.9.3` range does not adopt 0.10 or 0.11
automatically. Upgrade it as a separate compatibility change with the full
screenshot matrix, rather than mixing it into this geometry correction.

## Integration changes now in place

1. Measure each relationship label and include its bounding box in the ELK graph.
2. Render the path and label coordinates ELK solved, instead of generating a
   second midpoint route in React Flow.
3. Feed React Flow's measured DOM node dimensions back into ELK. This matters
   for tall phone frames and other nonstandard cards.
4. Reserve explicit edge-to-node, label-to-edge, and label-to-label spacing.
5. Select layout direction and component packing from the usable canvas aspect
   ratio after rails and sheets are removed.
6. Pin a URL-, search-, or route-selected component into the visible node budget;
   ranking may choose its context but may not aggregate away the named answer.
7. Hide labels that fall outside the visible canvas rather than showing clipped
   fragments.
8. Below 0.55 zoom, treat relationship labels as ambient and hide them. At that
   scale a 13 px label is under 7 effective pixels; it becomes readable again as
   the user approaches Read scale.
9. On phones, reserve space for the detail or lens sheet and keep it above the
   persistent navigation.

## Real limits of the present approach

- React Flow renders DOM nodes. It is appropriate for the current bounded,
  semantic views, but not for placing thousands of active cards on one canvas.
- A fresh full layout can move unrelated nodes. Guided focus should preserve
  positions when a bounded answer already fits and locally re-layout only when
  it does not.
- Dragging a node invalidates a precomputed ELK route until routing runs again.
  Before expanding freeform editing, reroute on drag end and spike
  [ELK Libavoid](https://eclipse.dev/elk/reference/algorithms/org-eclipse-elk-alg-libavoid.html)
  for interactive orthogonal obstacle avoidance.
- Neither React Flow nor ELK is a native 3D renderer. A 3D mode requires a
  companion renderer that consumes the same scene contract.

None of these limits blocks the current workbench. They define the next tests.

## Alternatives and their proper role

### yFiles for HTML

The strongest commercial fallback for 2D.
[yFiles](https://docs.yworks.com/yfiles-html/dguide/label_placement/) integrates
sophisticated graph layout, orthogonal routing, label placement, folding, and
large-graph features.
Evaluate it if collision-free labels, constrained incremental layout, or
interactive routing remain unreliable after the ELK integration and upgrade.
Its licensing and migration cost make it an escalation, not the starting point.

### react-force-graph

The best initial spatial-mode experiment because
[react-force-graph](https://github.com/vasturiano/react-force-graph) exposes
closely matched 2D, 3D, VR, and AR renderers. It could render the same selected
subgraph as the 2D workbench and preserve identity/filter state across a toggle.
Force-directed 3D does not inherently improve comprehension, label placement,
keyboard access, or precise flow reading, so it must stay optional.

### Cytoscape.js

A mature [graph-analysis and visualization option](https://js.cytoscape.org/)
with many layouts and a canvas renderer. It is valuable for analytical graph
operations, but moving to it would not by itself solve the 3D requirement or
guarantee label-aware semantic cards. It is not a clearer fit than the repaired
current stack.

### Ogma

A commercial [WebGL option](https://doc.linkurious.com/ogma/latest/) worth
evaluating if very large interactive graphs become a committed requirement.
Its strengths are scale and graph interaction; the reviewed product material
does not establish the seamless, matched 2D/3D toggle as a reason to migrate
today.

## Shared 2D/3D scene contract

A spatial spike must consume the same generated view model as 2D:

- stable component and relationship IDs;
- active lens, drill level, filters, node budget, and bounded answer set;
- selected identity, inspector state, and guided-route step;
- node role, status, theme tokens, evidence state, and accessible name;
- edge direction, relationship kind, protocol, and evidence as facts rather
  than inferred spatial properties;
- camera target and a reversible mapping between the 2D viewport and 3D camera;
- a list/detail representation containing the same facts.

The toggle should feel like the current scene gains depth: selection and filters
remain, the camera rotates around the selected answer, and returning restores
the prior 2D viewport. The Z axis may encode a documented projection such as
layer, time, confidence, or runtime activity; it must never invent analyzer
truth, and depth or motion must never be the sole carrier of meaning.

## Reconsider the engine when

Run a replacement spike only if one or more of these becomes true:

- label or route collisions persist in bounded views after the ELK upgrade and
  route-on-drag work;
- a two-to-five-object focused answer cannot meet the Read size floor while
  occupying at most 85% of the usable canvas;
- routine use requires hundreds or thousands of simultaneously active nodes;
- continuous obstacle-aware rerouting during freeform editing is a core task;
- 3D becomes a committed product surface rather than an exploratory lens.

Until then, invest in the shared scene contract, focus collection, regression
matrix, and analyzer-derived lenses. Those improvements survive any eventual
renderer change.
