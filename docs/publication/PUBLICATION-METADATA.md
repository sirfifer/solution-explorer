# Publication Metadata (publication.json)

Status: design approved by owner 2026-07-21, viewer wiring is a follow-up card.

## What this is

Every deployed viewer is a publication, and publishing carries obligations the
analyzer cannot know about: who is publishing, why, from what snapshot, with what
disclaimers, and under what access rules. That information lives in a sidecar file,
`publication.json`, that sits next to `architecture.json` in the deployed bundle.

It is publishing metadata, not analysis data. It never influences extraction,
enrichment, or scoring. It only feeds the presentation layer and the deploy tooling.

## Design rules

1. **The file is the artifact.** Any future editing UI is a convenience that reads
   and writes this file. Tooling and humans edit the same JSON.
2. **Always required at publish time.** The deploy paths (`action.yml`, the deploy
   and install skills) fail loudly when `publication.json` is missing or invalid,
   and the error names the boilerplate to copy. The viewer itself stays backward
   compatible: when the file is absent it renders exactly as today, so existing
   installs and local dev do not break. Enforcement lives at the publish gate,
   honesty lives in the render.
3. **Boilerplate ships in the repo.** Two canned variants live in
   `docs/publication/templates/`:
   - `publication.default.json`: sensible verbiage for an open source project or
     internal deployment publishing its own architecture.
   - `publication.showcase.json`: locked verbiage for our public demo program,
     including the unofficial-and-not-affiliated framing, snapshot provenance, and
     maintainer contact line. Edit per demo, keep the spirit.
4. **Placement is part of the contract.** Header content renders at the top of the
   page, footer content at the bottom. Both have an `always` region (every page and
   view) and a `front_page` region (landing view only). Attribution of the
   generating tool is footer boilerplate and is always present.
5. **No secrets.** The file describes access rules (for example that a deploy is a
   gated private preview). It never contains the passcode or any credential.

## Schema

Validated by `docs/publication/publication.schema.json` (JSON Schema draft-07).
Summary of the required shape:

| Key | Required | Meaning |
|---|---|---|
| `publication_version` | yes | Schema version, currently 1 |
| `publisher.name`, `publisher.contact` | yes | Who is publishing this deployment and how to reach them |
| `subject.name` | yes | The analyzed project |
| `subject.homepage_url` | no | Official public project website used for reader-facing links |
| `subject.repo_url`, `subject.license` | for external subjects | Upstream source and its license identifier |
| `subject.commit`, `subject.snapshot_date` | yes | Exact provenance of the snapshot (tooling may stamp these) |
| `subject.affiliation` | yes | `owner`, `maintainer`, `contributor`, or `none`. Anything other than `owner` or `maintainer` obligates unofficial framing |
| `purpose` | yes | `demo`, `documentation`, `internal`, `evaluation`, or `other` |
| `update_policy` | yes | `snapshot`, `periodic`, or `continuous` |
| `header.banner` | yes | One-line notice at the top of every page |
| `header.front_page` | no | Longer context blocks, landing view only |
| `footer.always` | yes, min 1 | Footer lines on every page, includes tool attribution |
| `footer.front_page` | no | Additional footer lines, landing view only |
| `context` | no | Narrative blocks: why this exists, what it is and is not |
| `disclaimers` | yes, may be empty | Explicit disclaimer lines |
| `access.visibility` | yes | `public`, `private-preview`, or `internal` |
| `access.gate` | no | Human description of the gate, never the secret |
| `generated_by` | yes | Tool name and version, stamped by tooling |

Text values support `{{path}}` substitution against the same file, for example
`"Architecture map of {{subject.name}} at {{subject.commit}}"`, so boilerplate
stays generic and facts live in one place.

## Follow-up card: viewer wiring

The viewer change (render header banner, front-page context, footer regions; loud
"unpublished preview" treatment when `access.visibility` is `private-preview`) is
a GUI change and ships with its GUI test plan delta per the project convention.
Requirements already known for that card:

- Fully functional at 390px width: banner wraps or collapses to a tap-to-expand
  notice, footer stacks, no horizontal scroll, no hover-only affordances.
- Rendering must be pure presentation: no layout shift of the graph canvas beyond
  reserving the banner and footer space.
- When `publication.json` is absent, render exactly as today.
- Substitution failures (a `{{path}}` that resolves to nothing) render loudly as
  `[missing: path]`, never silently as an empty string.

## Relationship to the showcase program

The showcase demo pipeline requires the showcase boilerplate plus a completed
sensitivity triage before any public deploy. That process is defined in
`DISCLOSURE-POLICY.md` in this directory.
