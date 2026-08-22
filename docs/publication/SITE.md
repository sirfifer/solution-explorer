# The SysCorpus commercial site

Operating notes for `site/`, the root site for `syscorpus.com`. This file
lives in `docs/publication/`, not in `site/`, on purpose: everything in
`site/` is uploaded verbatim by the deploy, so `site/` may contain only
publishable files (`index.html` and image assets). Do not put notes, drafts,
or READMEs there.

The apex domain stays
free for the commercial site per `DEMO-PROGRAM.md` section 4.4. Demo hosting
has since moved one level deeper than 4.4 describes: demos live under
`*.demo.syscorpus.com` (see `demos/registry/` and
`.github/workflows/demo-domain.yml`, which exists because the free Universal
SSL wildcard does not reach that depth).

## What it is

A single self-contained `index.html`. No build step, no JavaScript, no
analytics, no external assets except Google Fonts. Everything else is inline,
so the page can be deployed as-is to any static host and audited at a glance.

## Content rules (owner direction, 2026-08-22)

- Bold about the vision and the principles; humble and specific about the
  actual state. No claims of results we have not published.
- No hints about which projects the initial demos cover. "Multiple well-known
  open-source projects, starting soon" is as specific as it gets until they
  are live.
- No screenshots yet. Screenshot hints come later, per the screenshot story in
  `docs/publication/SCREENSHOT-STORY.md`.
- The hero carries a live "dress demo": one block of specimen HTML restyled
  between Atlas (default), Ledger, and Signal. The switch is radio inputs plus
  CSS, deliberately zero JavaScript, so anyone inspecting can verify the
  markup never changes. Keep it that way; it is a claim, not a decoration.
- Nothing on the page may state or allude to decisions not yet taken, in
  particular anything about the repository, source availability, licensing,
  or pricing. "We prove in public" refers to demos and feedback, nothing else.
- Writing style follows `.claude/rules/writing-style.md`. In particular, no em
  or en dashes as sentence interrupters.

## Before first deploy

1. Create the Cloudflare Pages project (suggested name: `syscorpus-www`) and
   attach `syscorpus.com` and `www.syscorpus.com`.
2. Set up Cloudflare Email Routing so `hello@syscorpus.com` forwards somewhere
   real, or change the footer address before publishing.
3. Owner review of the copy.

## Deploy

```bash
wrangler pages deploy site/ --project-name syscorpus-www
```

The page is static, so a redeploy is the whole release process.
