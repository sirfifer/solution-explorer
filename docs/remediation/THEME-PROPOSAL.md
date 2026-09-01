# Viewer themes: the launch wardrobe and the expansion rack

Status: LAUNCH WARDROBE SHIPPED, 2026-08-31. The token seam exists and all
four themes are live in the viewer, switchable from the header: Signal,
Ledger, Atlas and Fold. Lumen moves to the front of the backlog. The expansion rack (Relay, Brassworks, Grimoire)
is designed and specimen-proven, kept as built options that may surface on
non-flagship demos such as our own project. Originally written as a proposal
2026-08-22. The full visual
treatment, with screenshots of the current design, palette and type specimens,
and a live reskinnable specimen, is in the "SysCorpus Theme Studio" artifact
delivered with this proposal. This file records the durable substance so the
decision and its reasoning survive in the repo.

## The ask

Before SysCorpus goes public, the viewer should offer more than its single
current aesthetic. Owner direction (clarified 2026-08-22): a theme that is
functional, attractive, and comfortable in a business or boardroom context; a
whimsical one; and, required, a genuinely striking one whose jump from the
others is two to three times the size of the others' differences, while
staying broad in appeal. Sci-fi, steampunk, and fantasy mark the right level
of imagination but the wrong audience radius, so the striking theme must reach
that imaginative distance through near-universal material. Theming must be
pure CSS in the CSS Zen Garden sense: no involvement of data generation,
enrichment, or layout logic, and no loss of interaction. This flexibility is
itself a product feature: a customer should be able to dress their own map in
their own brand with a stylesheet. Light and dark mode remain an orthogonal
axis; each theme carries both variants.

## The three themes

**Signal (current, named so we can discuss it).** Near-black zinc, dot grid,
device frames glowing in their type color, animated neon edges. Strengths:
instantly recognizable, color is informational, native for developers and
demos. Costs: reads "gamer" to part of a boardroom audience, projects poorly
on weak conference screens, and its light mode is an inversion rather than a
design.

**Ledger (proposed, boardroom).** Named for the coverage ledger. Warm paper,
graph-paper hairlines, white cards with ink borders and a colored top rule per
component type, drafted solid edges with arrowheads, tabular numerals,
small-caps tags, solid-ink method chips. Palette: paper #FBFAF6, ink #101826,
teal #0F766E, blueprint #1D4ED8, critical #B91C1C. Type: Libre Franklin plus
IBM Plex Mono. Dark variant: slate ink. The register is engineering drawing
meets annual report.

**Atlas (proposed, whimsical).** The product says "living maps"; Atlas takes
it literally. Parchment with faint contour lines, components as etched
landmark cards with double-ruled borders, edges as expedition routes, jewel
inks: lapis #2B5B8C, viridian #3D7A5D, madder #A64D42, ochre #C8912E on
parchment #F3EBD9 with sepia ink #3E3120. Type: Fraunces display, Alegreya
captions. Dark variant: night navigation (deep indigo chart). Chosen because
an antique atlas is whimsical yet reads as beautiful to nearly everyone,
carries no gender or subculture coding, and explains the product rather than
distracting from it.

**Lumen (candidate A for the striking slot, bioluminescent deep water).** The
map as a living reef at depth: organic capsule cards with slow drift, light as
the information carrier, nothing rectangular. Abyss #041521, biolume #4FE3C1,
ray #7FD8FF, medusa #B78BFF, foam #E9FCF8. Type: Quicksand. Nature rather
than genre, so the wonder is near-universal. Light variant: sunlit shallows.
The one theme with a real rendering budget (glows), so it gets a performance
pass if chosen.

**Fold (candidate B for the striking slot, cut-paper craft).** The map as a
hand-built paper diorama: stacked cut-paper cards with physical shadow depth,
washi tape, stitched-thread edges, layered paper landscape, sticky-note stat
tiles. Cream #F6EFDF, charcoal #4A4238, coral #E76F51, teal #2A9D8F, mustard
#E9C46A, sky paper #CFE0EA. Type: Baloo 2 plus typewriter mono. Craft is
warm, unisex, ageless, and the furthest material from "software dashboard,"
which makes a working map in it feel like a magic trick. No animation needed,
so it is the cheapest theme to render. Dark variant: lamplit workshop.

## The expansion rack (built in the studio, backlog for the product)

Genre skins carry the right level of imagination but the wrong audience
radius for the launch wardrobe, so they live on the rack rather than in it.
Per owner direction they were built properly rather than left theoretical,
under one design rule: no props, no costume iconography, nothing on screen
names the genre; material, light, and typography quietly scream it while
every utility element stays where every other theme puts it.

**Relay (starship systems console).** Chamfered dark panels, scanlines,
phosphor amber #FFB454 against ice cyan #9BE8FF on void #05070C, uppercase
tracked Rajdhani. The genre arrives through instrument-panel discipline.

**Brassworks (Victorian machine room).** Enamel plates #F2E9D8 with brass
bezels #C9A227 and dotted rivet rules on dark mahogany #291A10, copper pipe
edges #B87352, Playfair Display with engraved highlights, enamel gauge stat
tiles. Not a single gear anywhere. The busiest of the eight by design.

**Grimoire (illuminated manuscript at night).** Dark vellum cards with
gilded double borders and corner fleurons on night ink #171126, gold leaf
#D4AF37 first letters on every component name, wax-seal badges, gemstone
indicators, gold ley-line and silver moonlit-path edges, faint arcane rings.
Cormorant Garamond.

## The engineering truth, and how the seam was actually built

The original estimate assumed the seam meant extracting semantic tokens by
hand across roughly 2,900 utility call sites, days of wide-but-shallow
mechanical edits with a screenshot diff to prove zero drift.

That work turned out to be unnecessary. The viewer is on Tailwind v4, which
compiles every utility to a CSS custom property reference: `bg-zinc-900`
becomes `background-color: var(--color-zinc-900)`. The seam was already there,
unused. Redefining those variables under a `[data-theme]` selector on the root
element re-dresses every component without editing one, which is the Zen-garden
property this document asks for, reached without touching the components at all.

The implementation is two files:

- `viewer/src/themes.generated.css`, the palette, produced by
  `viewer/scripts/generate-themes.mjs`. Each theme declares a small set of
  inks and assigns the eighteen Tailwind color families the viewer uses onto
  them, which is what collapses a generic palette into a deliberate one. The
  generator reads Tailwind's own oklch ladder and reuses its lightness value
  for every stop unchanged, moving only hue and chroma. That rule is what
  preserves every contrast relationship the viewer already relies on, and it
  replaces the screenshot diff as the guarantee against drift.
- `viewer/src/themes.css`, the character: type, radii, shadows, canvas
  ground, and the semantic `--se-*` tokens for the few values React Flow
  takes as props rather than from CSS.

A palette alone was not enough, and shipping it as though it were was the
first mistake. A dress is a material, not a hue: Ledger's cards are white
stock with an ink hairline, a type-coloured rule along the top and an offset
ink shadow, and its tags are squared outlined stamps; Atlas's are engraved
plates whose double rule is drawn as two rings, a band of the card's own
parchment and then a tan hairline, with italic pill captions. None of that is
reachable by redefining colours. It needs somewhere to attach, and the viewer
had no semantic classes at all, so a small set of `data-se` hooks was added to
the card roots, the type badge, the component name, the side panel, the
summary banner, and the panel's stat tiles, endpoint rows and method chips.
Those hooks are the whole of the component-side change; every rule that uses
them lives in the stylesheet.

Two things a stylesheet cannot decide travel with the theme instead:

- **The variant it was drawn in.** Light and dark stay orthogonal and every
  theme carries both, but they are not equally the point. Signal is a control
  room and is conceived dark; Ledger and Atlas are paper and parchment and are
  conceived light. Choosing a dress moves to its own variant. Without this a
  paper theme picked from Signal renders as night navigation and reads as a
  recolour, which is exactly how it was first reported.
- **Whether the hero glow belongs.** It is drawn as an inline box-shadow, out
  of CSS's reach. Paper does not glow.

Signal needs no palette block at all: it is Tailwind's own palette, so it is
the default every other theme overrides. Its former hardcoded values were
moved onto the seam and verified against what they replaced. The page ground,
canvas grid, and edge-label surfaces resolve to the identical bytes. The edge
and minimap accent colors moved by at most 31/255 on one channel, because the
literals were Tailwind v3 hex while the variables carry v4's oklch values, the
same ones the nodes at either end of those edges were already using. The
change makes an edge agree with the components it connects.

Adding a theme is now a block in each of those two files and an entry in
`viewer/src/utils/themes.ts`. No component changes.

## The decision and the plan

Owner decision, 2026-08-22: build the seam, ship four themes at launch:
Signal (kept, still the developer default), Ledger (proposed default when a
demo is entered from the commercial site), Atlas (the whimsical middle step),
and Fold as the striking showpiece. Fold doubles as the seam's stress test:
if the seam cannot carry that jump, it is too shallow and gets fixed before
demos go public. Add a theme picker in the header. A theme switch on a live
map of a famous codebase is honest theater, since nothing changes but the
dress, and that separation is the product's own argument made visible.

The commercial site's hero now carries a public miniature of this claim: one
specimen block restyled between Atlas, Ledger, and Signal with radio inputs
and pure CSS, zero JavaScript, so the claim is inspectable by anyone.

Shipped 2026-08-31: the seam, plus Ledger and Atlas, the two dresses the site
hero demonstrates. The header picker replaces the old dark-mode button rather
than sitting beside it, because theme and appearance are one question asked
twice; each theme carries both a light and a dark variant, so the two stay
orthogonal axes and the switcher carries both. It is reachable on every
viewport, where the dark-mode toggle used to be buried in the phone overflow
menu.

Fold, the striking slot, is built, and it answers the question this document
poses about whether the seam can carry that size of jump. It can. Fold changes
stock, ink, type, corner, shadow language, edge treatment and the shape of
every tile: cards are sheets lying on a bench with three stacked shadows
rather than one, a contact shadow, a lift, and a lit cut along the top edge,
because a single blurred shadow reads as elevation while three read as a
physical object. There is washi tape across each card corner, drawn on the
card with a gradient rather than added to the markup, since a theme may change
only how the page looks and never what is on it. Edges are stitched thread and
stat tiles are sticky notes, each sitting half a degree off square.

It was added with one generated palette block, one stylesheet section, and one
registry entry. No component was touched. That is the seam working as
intended, and it is the strongest evidence in this document that a customer
could dress their own map in their own brand with a stylesheet.

One rule about the canvas ground earned itself the hard way. It must be drawn
once, by React Flow's own Background component, and never also in CSS. Two
grids at different pitches never resolve into one surface, and the
interference is what makes a ground assertive rather than quiet; worse, only
the React Flow layer pans, so a CSS grid sits still while the map moves under
it and slides off whatever it was meant to help you line up against. A canvas
gets one grid, at a fine pitch, in a tone a few steps off the page, and it
belongs to the layer that pans.

Geometry matters as much as weight. A ruled grid was tried on Atlas and had to
come out: straight rules and the theme's contour arcs are different geometries
at about the same weight, so they compete instead of layering. Discrete marks
do not have that problem, which is why Atlas rules its ground with crosses and
Ledger, which has no arcs, rules it with lines. Weight is `lineWidth`, not
`size`; for a cross, `size` is the length of the arms, and a mark can be drawn
larger and still read as quiet if it is struck thinly.

The same area produced the one genuine defect of this work. Anything that
resolves a theme variable by reading computed style off the root, which the
canvas must do because React Flow takes its colours as props, runs its effect
before App's: child effects commit before parent effects. A theme applied in
App's effect therefore lands after the canvas has already read the outgoing
one, so the ground rendered a theme behind and kept the previous dress's grid
colour. It is invisible on a page load, where the pre-paint script has already
set the attribute, and shows only on a live switch, which is the demo action.
The document attribute is now written synchronously from the store action,
ahead of every reader.

Still open: Fold, the default-theme-per-entry-point idea, and whether the
theme faces should be self-hosted rather than fetched from Google Fonts, which
matters for a viewer shipped to run offline.
