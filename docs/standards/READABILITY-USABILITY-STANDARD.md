# Readability and usability standard

Status: product standard, adopted 2026-09-01

This is the permanent visual-usability contract for the web viewer and native
clients. It treats formal accessibility as a minimum and ordinary, sustained
readability as the product requirement. A person using the product in normal
conditions should not need to squint, hunt for a relationship, or infer which
tiny object a guided view intended them to inspect.

## Authorities and interpretation

The baseline is:

- [WCAG 2.2](https://www.w3.org/TR/WCAG22/) at Level AA for web content,
  including contrast, resize, reflow, text spacing, focus visibility, and
  target size.
- [Apple Human Interface Guidelines: Accessibility](https://developer.apple.com/design/human-interface-guidelines/accessibility)
  and [Typography](https://developer.apple.com/design/human-interface-guidelines/typography)
  for iOS and iPadOS. Apple identifies 17 pt as the normal default, 11 pt as
  the recommended minimum for custom text, 44 x 44 pt as the default control
  size, and Dynamic Type as the normal enlargement mechanism.
- [Android accessibility guidance](https://developer.android.com/guide/topics/ui/accessibility/views/apps-views)
  when behavior is shared with Android or web touch interfaces; it recommends
  at least a 48 x 48 dp focusable touch area.
- [ISO 9241-110 interaction principles](https://www.iso.org/obp/ui/#iso:std:iso:9241:-110:ed-2:v1:en)
  for suitability to task, self-descriptiveness, conformity with expectations,
  learnability, controllability, error robustness, and engagement.

WCAG intentionally does not prescribe a universal minimum body font size. It
requires outcomes such as 200% text resize without loss, reflow at an equivalent
320 CSS px width, and minimum contrast. Therefore the concrete sizes below are
our product defaults, not claims that WCAG itself requires those exact sizes.

## Content roles

Every visible element belongs to one of three roles. Role is determined by the
current task and focus state, not by component type.

### Primary

The information a surface is asking the user to read or act on now: page and
panel titles, body copy, selected object identity, focused node content,
relationship labels in a focused graph, question choices, evidence, warnings,
and navigation controls.

Primary content must meet every default-size, contrast, layout, and focus rule.
It may not become illegible merely because it is drawn inside a graph.

### Secondary

Useful supporting facts: metrics, reason labels, confidence, source type,
counts, timestamps, and compact metadata. Secondary content may be smaller but
must remain comfortably readable when its object is selected or its panel is
open.

### Ambient

Context that is not intended to be read in the current state: dimmed background
nodes, overview thumbnails, grid decoration, abbreviated topology in a minimap,
or peripheral labels while a focused collection is in relief.

Ambient content may be small or low emphasis only when the same facts have a
clear readable route through selection, list, detail, or focus. It must not look
interactive if it cannot be operated reliably at that scale.

## Typography

### Web defaults

| Role | Default | Absolute floor | Notes |
|---|---:|---:|---|
| Reading/body copy | 16 px | 14 px | 1.5-1.75 line height; prefer 45-75 characters per line |
| Navigation and controls | 14 px | 12 px | Full words over unexplained initials |
| Panel and list item title | 14-16 px | 14 px | Selected identity is never metadata |
| Secondary facts | 12-14 px | 12 px | Increase contrast before adding weight |
| Dense code or tabular metadata | 11-12 px | 11 px | Monospace needs extra width and contrast |
| Ambient labels | context-dependent | none | Must become at least secondary size on focus |

Text below 11 px is decoration, never the sole carrier of meaning. A 9 or 10 px
eyebrow can establish hierarchy only when the adjacent heading carries the same
context. A 9 or 10 px navigation label, warning, reason, relationship, evidence
state, or selected-object fact is a defect.

### Native defaults

Use Dynamic Type styles. Body starts at 17 pt. Secondary text should normally be
13-15 pt. The 11 pt Apple minimum is reserved for genuinely secondary metadata,
not body copy, controls, relationship labels, or selected-object content. The
layout must survive at least the accessibility sizes selected for the product's
test matrix; truncation requires a discoverable full-text state.

### Blocks and spacing

- Body line height: at least 1.5 times the font size.
- Compact labels may use 1.25-1.4 only when they do not wrap.
- Do not justify prose.
- Keep normal prose at 80 characters or fewer; 45-75 is the preferred range.
- The interface must tolerate the WCAG text-spacing override: 1.5 line height,
  2 times font size after paragraphs, 0.12 em letter spacing, and 0.16 em word
  spacing without content or control loss.
- Browser text zoom to 200% must not clip, hide, or make a control unavailable.

## Information structure

Hover-triggered reading surfaces must remain open while the pointer moves from
the trigger into the surface, including across the visual gap, and while the
reader scrolls or uses links within it. Scrolling a popup must not scroll or
zoom the underlying canvas. Dismiss only after leaving both trigger and popup,
or through an explicit dismissal such as Escape. Clicking a persistent help
panel replaces the transient preview; the two may not overlap. Every reading
surface stays inside its available boundary at supported window sizes.

Use the installed viewer/library primitives first. Graph-attached reading
surfaces retain React Flow's `NodeToolbar` anchoring, `position`, `offset`, and
`align`; scrolling and dragging use its `nowheel` and `nopan` controls plus
native CSS overflow and overscroll containment. Do not replace those mechanisms
with custom canvas transforms or wheel interception. The installed NodeToolbar
does not implement boundary collision handling or trigger-to-popup dismissal;
shared application code supplies only those missing responsibilities.

The routine graph crawl exercises pointer transfer, scrolling, return to the
trigger, departure, containment, and help-panel keyboard dismissal at both
1440 × 1000 and 1024 × 768. Shared-tooltip lifecycle checks run in the normal
viewer unit suite. New popup implementations must reuse these behaviors or
demonstrate the same regression coverage.

The data contract preserves semantic structure all the way to the reader. A
list does not become comma-separated prose, a set of named claims does not
become one paragraph, and a fact already carried by a typed field is not
repeated as an opaque AI sentence. Flattened text may be emitted as a secondary
compatibility or search representation, but it is never preferred over the
structured source.

- Lead with identity and a concise summary, then reveal labeled sections,
  lists, facts, evidence, and narrative in that order when they exist.
- Use headings for distinct claims such as purpose, mechanism, place in the
  system, why it matters, and where to go next.
- Render typed arrays as lists, chips, tables, or other appropriate collections;
  never join them into prose merely to simplify a component API.
- Reserve uninterrupted prose for genuine narrative. Narrative still uses
  paragraphs and headings wherever its meaning permits.
- Never truncate explanatory prose at an arbitrary character boundary. Author
  a concise field or use progressive disclosure while preserving a route to the
  complete text.
- Preserve uncertainty, provenance, and honest gaps as structured, visible
  information. They are part of the answer, not implementation metadata.

The executable counterparts to this rule are the typed projection contract,
the shared structured-information components, and the semantic `--se-*` visual
tokens in the viewer stylesheet. Theme styles may dress those roles but may not
weaken their size, contrast, hierarchy, or interaction guarantees.

## Contrast and emphasis

- Normal text: at least 4.5:1 against its actual background.
- Large text: at least 3:1 only at WCAG's large-text threshold.
- Meaningful component boundaries, focus indicators, relationship lines,
  arrowheads, and other non-text graphics: at least 3:1 against adjacent color.
- Focus indicators should be at least a 2 CSS px perimeter-equivalent and 3:1
  different from the unfocused state.
- Color never carries relationship type, status, direction, or selection alone;
  use labels, arrows, dash patterns, shapes, or icons as a second channel.
- Low contrast is allowed for ambient context, but selected and connected
  elements must return to the primary/secondary contrast thresholds.

Every shipped theme is tested separately in light and dark appearance. Passing
in one theme does not waive another theme.

## Controls and navigation

- Product touch target: 44 x 44 CSS px on web touch surfaces and 44 x 44 pt on
  iOS. Prefer 48 x 48 where density permits. This deliberately exceeds WCAG
  2.2 AA's 24 x 24 CSS px minimum.
- Desktop pointer controls may render more compactly but must meet WCAG target
  size/spacing and have a visible keyboard focus state.
- Persistent high-level navigation uses words. Initials are acceptable only
  after the word is already established and an accessible name is present.
- A focused control may not be hidden behind sticky headers, sheets, toasts, or
  bottom navigation.
- Primary actions remain reachable at 320 CSS px reflow and 200% text zoom.

## Graph and diagram contract

### Two honest states

`Fit` and `Read` are different promises.

- **Fit** proves scope and relative geometry. Labels may become ambient. Fit
  must never be the only path to any object.
- **Read** presents the selected object or bounded collection as an answer. All
  primary and secondary rules apply at the final rendered scale.

The interface must visibly distinguish these states through behavior and, where
needed, a small state label. “Everything is on screen” is not a readability
success criterion.

### Effective rendered size

Graph type is measured after zoom:

```text
effective size = authored CSS size x graph zoom
```

In Read/focus state:

- selected node title: at least 14 effective CSS px;
- selected node facts: at least 12 effective CSS px;
- relationship label: at least 12 effective CSS px;
- important edge: at least 2 effective CSS px, normally 2.5-3 px when selected;
- arrowheads and endpoints remain clearly visible and direction is not encoded
  by motion alone;
- the selected node itself supplies a touch/click target of at least 44 px in
  each dimension; small ports use a larger invisible hit area.

### Focus collection

A guided route selects a bounded answer set: the target plus the relationships
and neighbors needed to answer the route, normally no more than five objects.
The full graph may remain in place at 8-20% opacity to preserve mental context.

1. Remove the space occupied by open rails, inspectors, sheets, banners, safe
   areas, and persistent navigation from the usable focus rectangle.
2. Choose layout direction and disconnected-component packing from that
   rectangle's aspect ratio.
3. Attempt to preserve the existing positions and frame the focus bounds at
   Read scale.
4. If all focused objects and labels fit within 85% of both usable dimensions,
   animate to that viewport without changing layout.
5. If they do not fit, compact or locally re-layout the focused collection for
   the usable aspect ratio. Animate the transition and keep background context
   dimmed so the user's mental map is not discarded without explanation.
6. Never zoom below the effective type and edge floors just to keep a widely
   spread collection in frame. A compact focus layout is preferable to an
   unreadable faithful layout.

For a single object, center it in the usable rectangle at 1x or greater. For a
collection, prefer a portrait stack in tall regions, a left-to-right sequence
for true flows in wide regions, and a compact grid for weakly connected or
disconnected objects. Semantic flow can override aspect ratio only when the
result still meets the Read floors.

### Relationships

- Edge labels describe the actual observed relationship; do not rely on color.
- Labels sit on an opaque or sufficiently contrasting backing when they cross
  a busy canvas.
- Label collision is a layout failure, not a reason to reduce type below the
  floor.
- Connected edges return to full opacity and thicken on focus. Unrelated edges
  may dim, but the selected path must remain traceable end to end.
- A list or inspector must provide the same relationship facts as the diagram,
  especially on phones.

## Responsive geometry

- Layout reads the current usable canvas after panels and sheets, not the
  browser's outer viewport and not a generic device category.
- Disconnected components must be packed toward the canvas aspect ratio instead
  of placed in a single row.
- Resize, panel opening, device rotation, and split view trigger a bounded
  re-evaluation of layout and focus.
- Portrait regions favor vertical rank progression or compact grids. Landscape
  regions may favor horizontal flow. Empty space is acceptable around a readable
  answer; empty space caused by a mismatched layout while the answer is tiny is
  a failure.
- Mobile Workbench uses ranked list/tree plus detail as its primary model. Graph
  remains an optional context/read surface, never the only navigator.

## Motion

- Focus and layout transitions should normally complete in 200-400 ms: enough
  to preserve object continuity without delaying work.
- Respect `prefers-reduced-motion` and iOS Reduce Motion. Replace travel with a
  short crossfade or immediate state while preserving the final focus frame.
- Auto-focus must not fight a user's active pan, pinch, drag, or direct
  double-click. Guided/list/search selection may snap; direct manipulation
  remains under user control.

## Verification matrix

Every release candidate is checked at:

- 360 x 740, 393 x 852, and 430 x 932 portrait;
- phone landscape at approximately 844 x 390;
- tablet portrait and landscape;
- 1280 x 720 laptop and a tall desktop window;
- 200% browser text zoom and 320 CSS px reflow;
- all themes in light and dark appearance;
- normal motion and reduced motion;
- mouse, keyboard, and touch paths.

Automated checks record:

- clipped controls, unintended horizontal overflow, and obscured focus;
- effective focused-node and edge-label size after graph zoom;
- selected edge stroke width and contrast;
- focus bounds versus the usable canvas and canvas aspect ratio;
- touch target size;
- text and non-text contrast for every theme;
- console, page, and request errors.

Rendered review remains mandatory. A numeric pass cannot decide whether a
diagram's geometry communicates the intended answer.

## Current front-door review

Reviewed against the live UnaMentis projection on 2026-09-01.

### Meets or substantially meets the standard

- Portrait, Questions, and Atlas reflow cleanly at tested phone sizes.
- Primary Overview prose is 14-36 px with bounded line length and clear
  hierarchy.
- Mobile high-level navigation now uses full labels and 44 px targets.
- Theme, Search, preferences, tree, Support, Security, and detail sheets remain
  reachable without horizontal document overflow.
- Support/Security caveats, ranked rows, unknowns, and row metadata now use the
  selected-panel readability floor instead of 10 px low-contrast copy.
- A portrait-area handoff resets a stale specialist lens before selecting its
  stable target.
- Guided selection now lands at 1x, where the selected node title renders at
  14 px and relationship labels at 13-14 px; connected edges render at 2.5 px.
- ELK receives the usable canvas aspect ratio and compacts disconnected
  components. In the reproduced tall-window case, the canvas aspect was 0.89,
  the rendered graph bounds were 0.74, and the selected Database node landed at
  1x with no horizontal page overflow.
- Relationship labels and their backing boxes now participate in ELK layout;
  React Flow renders ELK's solved orthogonal routes and label coordinates.
  Across the wide, tall, and phone matrix for Overview, root and nested
  selection, Flow, and Support, the rendered audit found no node/node,
  label/node, or label/label intersections.
- The selected component is pinned into the visible node budget, so a deep link
  cannot silently aggregate away its named answer. Actual rendered node sizes
  are fed back into layout, including tall mobile-device cards.
- In Fit state, relationship labels become ambient and hide below 0.55 zoom;
  detail and guided Read states reveal them at readable effective size.
- Mobile graph space now excludes the open detail/lens sheet and persistent
  navigation; sheets no longer cover the bottom navigation.

### Open remediation

1. DetailPanel, TreeNavigator, selection sets, tours, coverage, and several
   legacy dense panels still contain meaningful 9-11 px labels. Classify each
   as primary, secondary, or ambient and migrate the first two to tokens rather
   than performing a blind global enlargement.
2. Theme contrast needs an automated all-theme/light-dark matrix. Several
   legacy `zinc-500` and `zinc-600` text choices are intentionally subdued but
   are not acceptable when the text becomes primary on selection.
3. Guided focus currently guarantees the selected object, collision-aware
   relationship labels, and aspect-aware full layout. The bounded
   focus-collection algorithm must still be implemented for routes whose answer
   requires two to five widely separated objects.
4. Full 200% text resize, WCAG text-spacing override, 320 px reflow, keyboard
   focus-not-obscured, and reduced-motion runs must become release gates.
5. Fit state needs a clearer visible distinction from Read state and an
   explicit, one-action “focus selection” affordance in addition to the existing
   double-tap gesture.

No open item permits a guided or selected answer to remain microscopic. Until
the focus-collection work lands, routes that cannot meet the Read floors must
prefer their ranked list or detail representation over a whole-graph fit.
