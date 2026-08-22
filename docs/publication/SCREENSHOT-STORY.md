# The screenshot story for syscorpus.com

Status: PROPOSAL, written 2026-08-22 for owner review. This is the plan for
the screenshots that will be added to the commercial site (`site/`) after
launch. The initial site carries no screenshots and no captures of the
product: its hero is a hand-built CSS miniature with illustrative numbers,
and it carries no hints about demo subjects. This document is the story the
real captures tell when they arrive.

## What the screenshots have to prove

The site's copy makes four claims: the map is complete, it is deep, it can be
interrogated in many ways, and it ends at the real code. Screenshots that
merely look attractive prove none of that. Every shot below is chosen to
demonstrate one specific claim, and together they should make a skeptical
engineer think "that is not a mockup, that is a working tool with opinions."

The diversity requirement is explicit: the set must show different lenses,
drill-down expansion, the depth of detail available, and that everything
bottoms out in real files (code, tests, help text, tooltips, documentation),
each linked back to the repository rather than trapped in the tool.

## The narrative arc

The gallery reads as one continuous descent, using the same subject and the
same component thread throughout, so a visitor experiences the story rather
than a pile of features: from the whole system, through one component, down to
a single symbol's code, then back out through the lenses that reframe the
whole, and finally the two loops (review back to AI, and the machine front
door) that make it more than a picture.

## The shot list

| # | Shot | What is on screen | The claim it proves |
|---|------|-------------------|---------------------|
| 1 | **The whole map** | Top level of a real system. Device frames legible (browser window, server rack, phone), colored animated communication edges, dashed structural edges, minimap | You recognize what the system is in seconds, without reading a line of code |
| 2 | **Drilling in** | Two levels down, breadcrumb trail visible (Home / App / Module), internal components rendered as their own graph | The map is hierarchical and every level is a real, navigable place |
| 3 | **Down to the code** | Detail panel, Symbols tab. A symbol expanded: kind icon, docstring, syntax-highlighted code preview, and the link out to the file in the repository | The bottom of the map is the actual code, in the actual repo |
| 4 | **The prose is on the map** | Detail panel, Docs tab, rendering the subject's own README or architecture notes | Documentation is indexed content, not a filename. The system's own words are part of the map |
| 5 | **One search, everything** | Cmd+K overlay with a query whose results mix a component, a file, a symbol, and a Markdown content match | Nothing is siloed. If it is in the system, search finds it |
| 6 | **A different question: Flow** | Flow lens docked beside the live graph, a user journey ranked in the panel | Lenses reframe the same map to answer a different question |
| 7 | **A different question: Design** | Design lens: plain-language findings with canonical-term chips, the abstractness against instability scatter with zones shaded | The tool has analytical opinions, stated in plain language, with the method named |
| 8 | **Blast radius** | Blast radius toggled on a heavily depended-on component: what breaks shaded one way, what it stands on another, the rest dimmed | The map is an instrument you operate, not an image you look at |
| 9 | **The honest gap** | Coverage badge open, ledger visible: every file parsed, skipped for a stated reason, or pruned. If the subject has a declared gap, show it | Completeness is verifiable, and the tool admits what it cannot see |
| 10 | **The loop back to AI** | Review mode: an annotation on a component, and beside or below it, the exported structured prompt | Exploration turns into feedback an AI can act on. The loop closes |
| 11 | **The other front door** | `ai.json` or an MCP tool call and its structured response, styled as a terminal or code block | AI agents are first-class readers of the same map |
| 12 | **In your hand** | Phone-sized viewport: the map with a lens as a bottom sheet | The map works in a hallway, not only at a desk |

Shots 1, 3, and 8 are the highest-value trio if only three are used: whole,
depth, and interactivity. Shot 9 is the one no competitor would lead with,
which is exactly why we should.

## Rollout sequence

1. **Hint wave** (site update before demos launch): shots 1, 3, and one lens
   shot, presented as cropped glimpses rather than full-bleed captures.
   Subjects must not be identifiable if the shot could reveal an unannounced
   demo subject.
2. **Launch wave** (first demo public): the full descent, shots 1 through 9,
   captured from the live demo so every screenshot corresponds to something a
   visitor can click into.
3. **Full gallery** (multiple demos live): add shots 10 through 12 and pair
   each screenshot with a deep link into the live map at that exact state.

## Capture standards

- Take shots from a **deployed, public map**, so the screenshot is a claim a
  visitor can verify by clicking. Until a SysCorpus demo is public, the
  already-public UnaMentis maps are acceptable interim subjects, to be
  replaced at the launch wave.
- Same subject and, where possible, the same component thread across the
  whole set, so the gallery reads as one descent.
- Real data only. No staged or edited content, ever. This is a trust product.
- 2x resolution, consistent viewport (1600x1000 for desktop shots, 390x844
  for the mobile shot), dark mode for visual consistency with the site.
- Crop browser chrome. The product is the interface, not the browser.
- File naming: `shot-NN-slug@2x.png` under `site/assets/`.
- Re-capture, do not reuse, after any significant viewer redesign, and
  re-verify each caption's claim against the current product at that time.
