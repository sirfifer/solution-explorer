# Showcase Disclosure Policy

Status: adopted 2026-07-21 (owner-directed). Applies to every public demo we
publish of a codebase we do not own or maintain.

## Principles

1. **Respect first.** Every project in the showcase is one we respect and chose on
   purpose. The showcase exists to demonstrate our tool, never to embarrass anyone.
2. **Consent before amplification.** Reading public source is everyone's right, and
   our license review confirms our right to publish structural analysis. But
   aggregating and spotlighting a project's weak points is amplification, and for
   that we ask first.
3. **No deadlines, no pressure.** We are not doing security research and we do not
   run disclosure clocks. When we contact maintainers we wait, and the message says
   so plainly.
4. **Default to no.** If maintainers ask us not to publish, the default outcome is
   that we do not publish. Overriding that default requires an explicit owner
   decision and a genuinely good reason, which we do not currently expect to ever
   have.
5. **Honesty gates still apply to us.** Our no-theater rules govern claims about
   our own accuracy and coverage. If a demo is scoped down at a maintainer's
   request, the demo must not imply completeness it no longer has: the gap is
   declared, tactfully and without attribution of blame.

## Process, per demo

1. **Build and validate.** The demo passes all validation gates first (coverage,
   sampled accuracy audit, GUI walk). We never preview something we are not
   confident in: a preview full of our own errors wastes the one first impression
   we get with a maintainer.
2. **Sensitivity triage.** Reviewer question: could a reasonable maintainer be
   unhappy to see this aggregated and amplified? Signals that flip a demo to the
   private path: security-relevant surfaces or findings, conspicuous structural
   problems, large declared gaps, anything our lenses frame negatively. When in
   doubt, take the private path. A clean triage goes straight to step 6.
3. **Private preview.** Deploy gated, never public. Acceptable gates: Cloudflare
   Access (email allowlist or one-time PIN) or a shared passcode enforced
   server-side (Pages Function middleware). Client-side-only gating is theater and
   is not acceptable. `publication.json` carries
   `access.visibility: "private-preview"`.
4. **Maintainer outreach.** Send the canned email
   (`maintainer-outreach-email.md`), personalized in the marked places, to the
   project's preferred contact (SECURITY.md contact for security-adjacent
   findings, otherwise the maintainer email or discussion channel the project
   advertises). Include the preview link and passcode.
5. **Wait states.** Whatever they choose, we honor:
   - **Fix first:** they want time to address findings. We wait as long as they
     ask, then re-run the analysis on fresh source and show them the new result.
   - **Approve:** we publish, with the showcase boilerplate.
   - **Decline:** we do not publish. We thank them and keep the demo private or
     delete it, their preference.
   - **No response:** one gentle follow-up after about three weeks. After that,
     owner decision, with the conservative default being to stay unpublished.
6. **Publish.** Public deploys always carry the showcase boilerplate
   (`templates/publication.showcase.json`): unofficial framing, pinned commit,
   upstream license, maintainer contact line, validation disclaimer.
7. **Record.** Every demo gets a row in `DEPLOYMENTS.md`: subject, commit, status
   (`private-preview`, `cleared`, `published`, `declined`, `withdrawn`), date, and
   the outreach state. No demo ships unrecorded.

## What this policy is not

It is not a legal shield (the license review in the showcase program does that
work), not a security disclosure program (we do not hunt vulnerabilities), and not
an approval process for demos of our own projects, which need only the default
boilerplate and our normal gates.
