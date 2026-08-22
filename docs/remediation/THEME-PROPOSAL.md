# Viewer themes: the launch wardrobe and the expansion rack

Status: DECIDED (launch set), 2026-08-22. **Fold takes the striking slot**
(owner decision). Launch wardrobe: Signal, Ledger, Atlas, Fold. Lumen moves
to the front of the backlog. The expansion rack (Relay, Brassworks, Grimoire)
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

## The engineering truth

The viewer today styles via Tailwind utility classes inline in components with
a `.light` override. There is no token seam, so no Zen-garden theme can be
dropped in yet. The one-time work is extracting semantic tokens (surface,
frame, glow, edge, badge, chip, and so on) keyed off a `data-theme` root
attribute, with Signal rebuilt as the reference theme and screenshot-diffed
against today to prove zero drift. After the seam, each theme is a stylesheet.
Estimate: days for the seam, a few days per theme. This is wide-but-shallow
mechanical work of exactly the kind the golden corpora and GUI plan check
exist to keep safe.

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

Still open: the default-theme-per-entry-point idea, and slotting the seam
work relative to demo one.
