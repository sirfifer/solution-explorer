# Valuation snapshot: Solution Explorer / SysCorpus

Snapshot date: **2026-08-19**. Product state: `main` at `273a9c9`, demo program at
phase N2 (pre-flight), no public launch, no revenue, 1 GitHub star. This is the
recurring valuation artifact that DEMO-PROGRAM.md section 10 proposed. It names
the value drivers, the evidence for each, the comparables, and honest ranges
with their assumptions. Method: a six-track market research pass (deal comps,
competitive landscape, licensing price points, solo-founder outcomes, buyer
scan, launch reality), all claims web-verified 2026-08-19. Dollar ranges in
section 4 are calibrated estimates built from the comps in section 3; they are
labeled as estimates because that is what they are.

Owner's stated goals (2026-08-18/19): floor around a few hundred thousand on a
sale; preference for revenue early (thousands to tens of thousands, ideally
recurring) while maturing toward something bigger; interest in what an offer
would look like 2-6 months out versus 12-24 months out.

---

## 1. The asset, as a buyer's first ten minutes would find it

What exists and is verifiable:

| Driver | Evidence |
|---|---|
| Working product at real scale | VS Code measured: 15,256 files, 4,936,720 lines, 136.5s cold / 95.5s warm, complete coverage ledger |
| Verifiable-accuracy thesis | Coverage ledger (every file accounted for), publish gate, preview gate, provenance stamping, "no theater" rule enforced by instrument |
| Comprehension instrument with scores | Three-persona study (B+), N1 calibration run: P1 11 to 17/24, P3 6 to 16/24, trust incidents 17 to 8 |
| Language breadth | 9 full-parse groups (Swift, Python, Rust, TS/JS, Go, Ruby, Java, C#, C/C++), detect+metrics for the rest |
| Multi-repo composition | M1 shipped (composition without cross-repo edges); M2-M4 designed, not built |
| Engineering hygiene | 1,642 passing tests, golden corpora with parity guards, CI green, SBOM, CRA readiness artifact |
| AI-era angles | Machine front door (`ai.json`, `llms.txt`): agents consume the enumeration at a fraction of raw-repo token cost |
| Clean IP | One human contributor plus dependabot; solo copyright; PolyForm Noncommercial 1.0.0 with all commercial rights reserved; license review, grant policy, and consent policy already built |
| Operational maturity path | Weekly refresh harness designed (gates, provenance, findings loop); demos as living infrastructure, not screenshots |

What does not exist, and a buyer will notice in the same ten minutes:

- Zero distribution: 1 star, 0 forks, no users, no traffic, no waitlist.
- Zero revenue, zero logos, zero testimonials.
- Solo bus factor: one person holds all context.
- P2, the non-coding executive persona, moved only +1 in N1. The product
  currently proves itself to engineers; executive-legible value lags.
- Demos: two UnaMentis sites live; the three flagship demos are not built yet.

## 2. Market context, August 2026

**Tailwinds (all sourced, section 13):**

- "Comprehension debt" became a named industry problem in late 2025-2026
  (Addy Osmani et al.). Surveyed developers report 11.4 hrs/week reviewing AI
  code versus 9.8 writing; 55% concerned about codebase comprehension; Sonar
  found 96% do not fully trust AI-generated code.
- Capital is flowing to exactly this problem: Cognition raised $1B+ at $26B
  (May 2026, owns DeepWiki); Mintlify $45M at $500M (Apr 2026) on the explicit
  thesis of "knowledge infrastructure for AI" with nearly half of docs traffic
  now from agents; Greptile $25M (Sept 2025); Unblocked $20M (May 2025);
  Entelligence $5M (Jan 2026); Port $100M at $800M (Dec 2025); Atlassian paid
  ~$1B for DX (Nov 2025).
- Nobody ships the full combination Solution Explorer targets: automatically
  generated + interactive and drillable + verified accuracy + multi-repo.
  Closest are Google Code Wiki (free, public repos, no accuracy claims),
  Driver AI (enterprise black box), CodeBoarding (early OSS).
- The accuracy gap is documented, not hypothetical: DeepWiki backlash includes
  fabricated build systems (LibreOffice/Buck) and omitted core components
  (LLVM/TableGen). Trust is the open flank, and trust is this product's thesis.

**Headwinds (equally sourced):**

- Two free giants set the price of public-repo maps at zero: DeepWiki (50k+
  repos indexed, free, a Devin funnel) and Google Code Wiki (public preview,
  Nov 2025). The demos can prove capability; they cannot be the product.
- The category graveyard is real: CodeSee (shut down Feb 2024, assets to
  GitKraken, product sunset), Sourcetrail (archived), Adrenaline (dead), bloop
  (pivoted to COBOL), Swimm (pivoted to mainframe). Standalone code
  visualization has repeatedly failed as a business, including with VC money.
- In the last 24 months, every free visualization comparable made $0 in
  revenue (GitDiagram ~16k stars, no revenue; DeepWiki free; OpenClaw 386k
  stars, converted to a job, not a sale).
- Acquirers in 2025-2026 paid for distribution and traction, not code: uv had
  126M monthly downloads (Astral to OpenAI), Better Auth 4.7M weekly (to
  Vercel), Promptfoo 25% of Fortune 500 (to OpenAI), Base44 250k users and
  monthly profit (to Wix).
- The "we could rebuild this with AI" dismissal is now standard diligence
  posture (a Show HN literally titled "I Rebuilt DeepWiki for $300K less").
  The hard 20% (accuracy, edge cases, gates) is invisible until a buyer tries.

## 3. How value actually transferred, 2024-2026

The comp set, condensed. Confidence labels: [C] confirmed by primary or
top-tier outlets, [R] reported estimate, [U] undisclosed.

| Deal | Date | Shape | Price | What was paid for |
|---|---|---|---|---|
| Google / Windsurf | Jul 2025 | Non-exclusive license + ~40 hires, no equity | $2.4B [C] (~half to investors, ~half comp) | Talent + tech license |
| Cognition / Windsurf remainder | Jul 2025 | Acquisition | ~$250M [R] | $82M ARR, 350+ enterprise customers |
| Wix / Base44 | Jun 2025 | Acquisition, founder joined | $80M cash + $25M retention + $90M earnout [C] | 250k users, ~$1M ARR, profitable, solo-owned |
| Atlassian / DX | Sep 2025 | Acquisition | ~$1B [C] | 350+ enterprise customers on <$5M raised |
| OpenAI / Statsig | Sep 2025 | Acquisition (stock) | $1.1B [C] | Product + CEO became CTO Applications |
| OpenAI / Astral (uv, Ruff) | Mar 2026 | Acquisition, tools stay OSS | [U], nine figures [R] | 126M downloads/month + elite team |
| OpenAI / Promptfoo | Mar 2026 | Acquisition | [U] (was $86M post [C]) | 25% F500 penetration, 11 people |
| Anthropic / Bun | Dec 2025 | Acquisition, stays MIT | [U] | Runtime under Claude Code + Jarred Sumner |
| Anthropic / Stainless | May 2026 | Acquisition | >$300M [R] | SDK infra used by OpenAI/Google/Cloudflare |
| Vercel / Better Auth | Jul 2026 | Acquisition, stays MIT | [U] | 4.7M weekly downloads, solo founder joined |
| GitKraken / CodeSee | May 2024 | Distress asset tuck-in, product sunset | [U] | The closest product analog; cautionary |
| OpenAI hire / OpenClaw | Feb 2026 | Job + IP to foundation | no asset payment [C] | The most viral solo tool of the era |
| Acquire.com market | 2025 | Marketplace asset sales | median 3.9x annual profit [C] | Profit; unprofitable listings languish |

Three patterns carry every dollar in that table:

1. **Real revenue** (Base44, DX, Windsurf-to-Cognition): priced on proof.
2. **Massive adoption as talent-plus-stewardship signal** (Astral, Bun, Better
   Auth): undisclosed, structured around the people joining.
3. **A person's demonstrated capability** (OpenClaw, Humanloop, Alex, Koala):
   a hire, with the product often sunset or donated.

The research found **no 2025-2026 example of a meaningful-price dev-tool sale
where the builder walked away entirely.** Buyers expect 6-12 months of
transition (consulting agreement) at minimum; the acqui-hire premium exists
only if the person comes with the deal. Bootstrapped solo ownership does mean
every dollar of consideration is the owner's (Base44 demonstrated the clean
version of this). EU residence blocked none of the observed deals.

## 4. Value states and honest ranges

All numbers here are **estimates** synthesized from section 3. The single
biggest price lever at every state is competitive tension: one interested
party anchors low, two changes everything (the entire Windsurf saga is this).

**S0. Today, pre-launch.** No external signal exists; value is replacement
cost minus rebuild-confidence discount.
- Open-market asset sale: **$15k-$75k**. Marketplaces price on profit; there is none.
- A motivated strategic who somehow found it: **$50k-$250k**, but no one is looking.
- Not a state to sell in, and nobody is proposing to.

**S1. Wave 1 demos live + closed preview + visible attention** (target state,
2-5 months out). Three flagship demos public, instrument scores published,
hundreds-to-thousands of stars, badge adoption starting, inbound trickle.
- Asset-only sale (clean walk-away): **$75k-$400k**.
- Sale with 6-12 month consulting/transition attach: **$250k-$900k** with one
  motivated strategic buyer.
- With two credible bidders: **$500k-$1.5M**.
- Probability at least one credible offer of $300k+ materializes within ~6
  months of demos landing well: **~10-20%** (est.). It requires the demos to
  visibly land AND a roadmap-hole buyer to notice or be shown.

**S2. Revenue proof** (9-18 months out): 3-10 paying organizations, $5k-$20k
MRR equivalent from pilots/service/licenses, 1-2 case studies.
- Strategic tuck-in: **$750k-$3M**. At this scale revenue is not priced on
  multiples; its job is to de-risk the asset and prove enterprise pull (the DX
  logic at micro scale: capital efficiency plus enterprise proof).
- Probability of reaching S2 given demos land and pilots are pursued
  seriously: **~35-55%** (est.).

**S3. Breakout** (18-30 months, requires luck): heavy adoption with real
usage, $50k+ MRR or marquee licensees, category-name status.
- **$3M-$15M+**, with Base44-shaped outliers above that requiring lightning
  plus revenue. Probability: **~5-10%** (est.).

**Talent overlay, available from S1 onward.** A senior-engineer-plus-IP deal
with a lab or platform (the dominant 2025-2026 shape): employment package
$500k-$1.2M/yr total comp (current AI-tooling bands: senior SWE $800k-$1.5M,
founding engineer $2M-$6M per advisory estimates) plus IP consideration
$100k-$500k. Two-year value **$1M-$3M**. Probability an offer of this shape
appears within 12 months if demos land and openness is signaled: **~25-40%**
(est.). It is the highest-probability route to $600k+, and it is a job, which
is a life decision and not just a price.

Timing multiplier: S1 to S2 raises the central sale range roughly 3-4x; S2 to
S3 another 3-5x. The owner's instinct of "2 to 10 or 20 times more by
waiting" matches the comp set, with the caveat that each wait also carries
fizzle risk and the fast-follow window (section 9).

## 5. Near-term revenue paths, with real price scaffolds

The revenue-early preference is not just income; per section 3 it is the only
reliable way to move from "interesting repo" to "priceable asset." Paths, in
recommended priority order:

**5a. Design-partner pilots ("map our estate")**: the strongest near-term path.
- Market norms: enterprise pilots run 10-30% of intended annual contract
  value; $25k-$50k for a 90-day pilot is a documented reference point
  (credited on conversion). Guidance for early startups: never free, at
  minimum 10%. Comparable consulting: code audits $8k-$25k (typical SaaS),
  $25k-$60k (multi-service enterprise).
- Realistic SysCorpus pricing at current maturity: **$10k-$30k per pilot**,
  which buys a mapped estate, N-weeks of refreshes, and a findings readout.
- Reality check: practitioner guidance is ~150-200 conversations to land 3-5
  deep design partners. 1-3 pilots in the first 6 months post-launch is the
  honest target. Revenue: **$15k-$75k cumulative** in the base case.
- Founding-partner pricing (per owner's sweeten-but-real intent, 2026-08-19):
  anchor the list price at **$15k-$25k**, offer the first one or two partners
  a named founding discount to **$7.5k-$15k**, and hold a floor around
  **$5k**. Market norms say never free and never below ~10% of intended
  contract value; below the floor the number stops being usable as revenue
  proof in a later diligence. Relationship freebies stay outside the pilot
  count entirely.

**5b. Managed refresh service (productized: the demo harness pointed at
private code)**: weekly refreshed, gated, provenance-stamped private map.
- Comp scaffold: IcePanel charges $40-$80/editor/month with unlimited free
  viewers; Sourcegraph enterprise floor ~$16k/yr; seats cluster $19-$48/user/mo.
- Realistic pricing: **$250-$1,000/month per estate** (viewers free, priced
  per repo-estate, not per seat, because the map's whole point is that
  everyone looks at it). 5-15 customers by month 9-12 in the good case:
  **$2k-$10k MRR**.

**5c. OEM / embed licensing to dev-tool companies.** PolyForm Noncommercial
makes this clean: no commercial use of any kind is granted, so embedding
Solution Explorer's capability in someone else's commercial product requires a
negotiated license, and so does that company merely trialling it. That forces
exactly the right companies to the table, earlier than FSL did.
- Comp scaffolds for small OEM: GoJS $3,995-$11,950 per team perpetual;
  JointJS+ $2,990/dev; tldraw SDK ~$6k/yr per team [R]; Zwibbler $5,999 flat;
  SQLite's public ladder $2k-$6k per component, support $8k-$85k/yr,
  consortium $150k/yr. Nobody press-releases five-figure OEM deals; they run
  on rate cards.
- Realistic: **$10k-$50k/yr per licensee** at current maturity; 0-2 deals in
  12 months; each one is disproportionate validation for a later sale.
- Natural licensee list: Mintlify, GitBook, Port, Cortex, GitKraken, IcePanel,
  Komodor (see section 6).

**5d. Self-serve team licenses** (Metafizzy/FullCalendar pattern): $99-$999/yr
support-and-updates licenses. Trickle revenue, low support cost. VS Code
Marketplace still cannot charge (license-key gating is the standard
workaround); GitHub Marketplace pays out 95%; JetBrains Marketplace 85% and
does support paid plugins.

**5e. Sponsorship**: negligible expected value (GitHub Sponsors median is
close to zero; $100M lifetime across 70k+ maintainers). Keep a sponsor
button; expect nothing.

**License mechanics worth writing down once** (relicensed from FSL-1.1-ALv2
to PolyForm Noncommercial 1.0.0 on 2026-08-27; see NOTICE for the full
history): dual licensing on top of a source-available license is standard
practice (PowerSync, Keygen; Sentry relicensed Codecov after acquiring it,
proving a single-owner source-available codebase transfers and relicenses
freely). Three consequences of the move off FSL:

- **The right to run the tool is now itself sellable.** Under FSL, internal
  corporate use was free and enterprise revenue had to sell operation,
  freshness, support, and gates. Under PolyForm Noncommercial it does not,
  which restores per-organization internal-use licensing (5b) as a primary
  line rather than a packaging exercise.
- **No conversion date.** FSL converted each release to Apache-2.0 after two
  years, which discounted older code in a sale and argued against a slow burn
  past ~24 months. PolyForm Noncommercial has no sunset, so age does not erode
  the asset and a longer build is not self-defeating.
- **Adoption is now top-down.** A developer can no longer legally trial it at
  work without a grant. Pipeline comes from inbound license requests, which
  enterprise SCA tooling reliably generates by flagging the license, plus
  direct sales. Bottom-up organic adoption inside companies is no longer a
  channel, and the demo showcase is a sales asset rather than a funnel.
  Grants are issued per docs/commercial/GRANT-POLICY.md, and every one is
  recorded in ADDITIONAL-PERMISSIONS.md, which doubles as evidence of
  consistent enforcement in diligence.

## 6. Buyer and licensee map, ranked

The instinctive list (Microsoft, Google, OpenAI, the labs, Cursor) is mostly
wrong for a direct sale, and the research says so concretely:

- **Microsoft/GitHub**: no small tool acquisition since 2019-2020 (Semmle,
  npm); builds internally (Spaces, Agent HQ, Copilot app); recent posture
  toward third parties around VS Code has been restriction (blocked its
  extensions on forks, Apr 2025). The VS Code demo will impress engineers;
  do not expect Microsoft amplification or a check.
- **Google**: ships Code Wiki free (Nov 2025); licenses at scale only for
  talent (Windsurf $2.4B, Contextual AI $80-90M, both with hires). The
  realistic Google outcome is fast-follow pressure or a job offer, not a
  purchase. On Kubernetes specifically: neither Google nor CNCF buys
  visualization tools; the ecosystem adopts donated projects (Dashboard
  archived Jan 2026 for lack of maintainers; Headlamp endorsed as successor
  Jun 2026 after being donated via Microsoft/Kinvolk). A K8s demo earns
  credibility with platform-engineering teams, not CNCF money.
- **OpenAI / Anthropic / Cursor**: OpenAI buys proven distribution (every
  2025-2026 buy had it); Anthropic makes rare infra/talent buys and points
  app-layer tools at its plugin/skills marketplace instead; Cursor is now a
  SpaceX unit (deal closed Aug 14, 2026 [C]) and is un-courtable near term.
  All three are talent-overlay candidates, not asset buyers.

The plausible list, ranked, with how each transacts:

1. **Atlassian.** Killed Compass (end-of-sale May 2026); publicly defined DX
   Fabric's first pillar as architectural context for AI-native development;
   serial acquirer from tuck-in to $1B (DX). Exactly the roadmap hole this
   fills. Shape: tuck-in acquisition or license into DX Fabric.
2. **Mintlify.** $45M raised Apr 2026 on "knowledge infrastructure for AI";
   half of docs traffic from agents; repo-to-architecture is a natural
   adjacency. Shape: OEM license first ($25k-$100k/yr), acquisition later.
3. **Port.** $100M fresh (Dec 2025, $800M valuation), agentic-platform
   ambition, catalog is YAML-declared today; code-derived maps would
   differentiate against Backstage and DX Fabric. Shape: license or tuck-in.
   (Cortex and OpsLevel are the same thesis, smaller checkbooks.)
4. **Datadog.** Most acquisitive in the scan (16 deals; Eppo ~$220M, Propolis,
   Metaplane; explored GitLab); expanding from runtime into the SDLC. Shape:
   acquisition with employment; they buy teams.
5. **GitKraken.** Bought CodeSee's assets once already; DevEx platform play.
   Shape: small asset tuck-in. This is the floor buyer, useful mostly as a
   BATNA, not a goal.

Wildcards: **Cognition** (DeepWiki's accuracy problem is this product's exact
strength; a deterministic-grounding license is conceivable; they build first
and buy distressed, so more plausibly a talent overlay), **Sourcegraph**
(deterministic ethos match, no map product, but post-Amp-split strategy is in
flux), **JetBrains** (never acquires; but the JetBrains Marketplace takes paid
plugins at 85% payout, making it a channel rather than a buyer), **IcePanel /
Structurizr** (adjacent smalls; partnership shapes, little cash),
**Komodor/Cast/Sysdig** (K8s demo audience; runtime-centric today), **Amp**
(new, unknown appetite).

Channel plays that pay regardless of buyer: a DeepWiki-style README badge
program (badge/embed adoption by repos is the one maintainer-amplification
mechanic with recent precedent: Google, Hugging Face, and Perplexity teams
added DeepWiki badges within two weeks of its launch); a GitHub Marketplace
app (95% payout); a JetBrains plugin (85%); an MCP server exposing the machine
front door (agent-facing discovery via MCP registries became real
infrastructure in 2026, and "hand your agent the verified map instead of the
raw repo" is a genuinely current wedge).

Home Assistant note: the Open Home Foundation absorbs and amplifies community
tools through official channels (Music Assistant precedent). Of the three
Wave 1 subjects, HA is the one where consent-first outreach could plausibly
yield official-channel amplification. Kubernetes naming is trademark-policed
("X for Kubernetes" is fine, "Kubernetes X" is not). And the curl "AI slop"
backlash means unsolicited AI-flavored analyses of major projects start from
suspicion: accuracy and the consent policy are the admission ticket, which is
an advantage here, not a cost.

## 7. The $600,000 question

Stated plainly:

- A **$600k lump sum within 2-6 months** requires an S1 strategic sale at the
  top of the one-bidder range or with competitive tension, on a timeline
  where the demos themselves take 1-3 months to land. Estimated probability:
  **~5-10%**. Possible, not a plan.
- The **highest-probability route to $600k+ within ~12 months** is the talent
  overlay (employment package plus IP consideration), at ~25-40% if courted.
  It conflicts with the self-employment preference and is a legitimate
  personal decision, not a default.
- The **highest-probability route to $600k+ as a sale** is S2 first: demos,
  then 3-10 paying organizations, then a deliberate process with the ranked
  buyer list in months 9-18. Unconditional probability of a $750k+ sale
  within 18 months: **~20-30%** (est.), roughly doubling conditional on S2
  being reached.
- Expected shape of any deal: cash at close plus a 6-12 month consulting
  attach (norms: most SaaS deals land there), possibly a small earnout. Take
  legal counsel the moment any conversation turns real; for sub-$1M deals a
  lawyer suffices, no banker needed. If relocation to Europe happens
  mid-process, deal structure and tax jurisdiction need professional planning
  early, not after a term sheet.

## 8. What most raises the number per month of work

In order of price-per-effort, given the comps:

1. **Paying logos.** Any revenue at all moves the asset across the
   "priceable" line (section 3). One $15k pilot is worth more to the sale
   price than a month of feature work.
2. **Visible demo adoption**: badges on other people's repos, traffic,
   citations. This is the distribution signal every 2025-2026 buyer paid for.
3. **The multi-repo differentiator made real** (M2 cross-repo edges): the one
   capability nobody else ships, and currently invisible (no TASKS.md cards).
4. **Executive-legible value** (the P2 gap): the personas who sign checks
   moved +1 point in N1. Stakeholder views that land with non-engineers
   compound every path, sale included.
5. **A second wave demo** proving generality (Deno / Supabase / Spring wall),
   already planned.

## 9. Risks that cap the number

- **Fast-follow window.** DeepWiki or Code Wiki adding deterministic
  verification, or an OSS clone reaching good-enough, compresses the
  differentiation. The window is realistically 12-24 months; the FSL two-year
  Apache conversion points the same direction. This argues for selling into
  S2, not holding for S3.
- **Launch fizzle.** Modal outcome for free visualization tools is silence.
  Mitigations: the closed preview, badge program, founder-led X/HN (every
  documented viral dev-tool case was founder-led, none contractor-led), and
  the fact that the demos are refreshed living sites rather than screenshots.
  Probability of no material revenue and no offers by month 12: **~30-45%**
  (est.). This is the scenario the revenue-first posture exists to shrink.
- **Solo bus factor and diligence discount**: partially mitigated by the
  unusually clean trail (tests, gates, provenance, license review); keep it
  that way, it is worth real money in the final 10%.
- **A weak public demo** lowers the number directly (DEMO-PROGRAM section 10
  already treats this as a hard gate; the market research confirms it).

## 10. Recommendation and sequencing

**Strategy: revenue-first, sale-ready.** Run both tracks with the demo program
as the shared engine; do not choose between licensing and sale now, because
the same three artifacts (demos, pilots, badges) raise the price of both.

1. **Execute the demo program unchanged** (N2 pre-flight, then VS Code demo).
   It is the value engine for every path in this document.
2. **Attach a thin commercial-capture layer from demo one**: a "map your own
   estate" call to action on the hub, a stated pilot offer at $15k-$25k, a
   contact path, and a README badge kit. Inbound with nowhere to land is the
   only unforced error available in month one. (Estimated effort: days.)
3. **Closed preview per the existing plan**, with the consent policy front
   and center; it is a differentiator against the DeepWiki-backlash backdrop.
4. **After Wave 1 is public: a deliberate 20-40 conversation pass** over the
   ranked list in section 6, framed as licensing/embedding partnership, never
   as "buy me". Acquisition interest, if it exists, surfaces as their
   counterproposal (GSAP-to-Webflow is the canonical arc: licensing business
   first, acquisition as its consequence).
5. **Refresh this snapshot at each trigger** (section 12) rather than
   re-arguing from scratch.

## 11. Decisions taken (owner, 2026-08-19)

D1. **Deal shape: consulting attach only.** Sale conversations assume a 6-12
   month transition/consulting agreement and independence afterward.
   Employment-shaped talent deals are not being courted. This sets which
   rows of section 4 are live: the S1/S2 sale ranges, not the talent overlay.

D2. **Sequencing refinement (owner).** Wave 1 is intended to complete fast,
   demo one followed quickly by the other two. The thin commercial-capture
   layer rides along during Wave 1. Caveat the owner set explicitly: if demo
   one triggers a serious findings cycle, that slows Wave 1 and is all the
   more reason to hold commercial pilots until the tool has earned
   confidence, then bring that confidence to the pilot.

   **Pilot planning is a two-path scenario build-out** (owner, 2026-08-19),
   to be worked up as Wave 1 nears completion:
   - Path A, ecosystem: someone the owner knows who is involved with or
     responsible for a codebase that would make a strong pilot, where he is
     a known quantity.
   - Path B, commercial: a strategically ideal pilot target, preferably one
     with some existing accessibility rather than a fully cold approach.
   Build both scenarios, pick one; running both is the exception, not the
   plan. A relationship freebie is allowed but is a side goodwill install,
   never counted as a commercial pilot, because pilots exist to demonstrate
   revenue.

D3. **Outreach posture: active.** After Wave 1 is public, run the deliberate
   20-40 conversation licensing/partnership pass over the section 6 list.

D4. **FSL posture: everything stays FSL for now.** Monetize operation,
   support, and OEM. Revisit an edition split only at first genuine
   enterprise pull. Owner framing recorded: whatever is the right path for
   the project and its goals; selling outright remains something he is very
   open to but does not need, and a growing revenue stream only advances
   every path, with no real downside if a sale never happens.

**Operating constraints recorded (owner, 2026-08-19):**

- The business runs on the owner plus spouse. **No hires planned.** Gaps are
  filled by contract work only (contract technical work with AI help,
  marketing, business services). Built in parallel with a full-time job, and
  that continues.
- Standing requirement before this counts as safely self-run: **a concrete,
  definitive plan for handling security issues and anything else that is
  effectively a liability** (vulnerability response, support commitments,
  incident handling). Existing inputs: SECURITY.md, docs/supply-chain-posture.md,
  the CRA evaluation, DISCLOSURE-POLICY.md. This plan is a flagged work item,
  not yet written.
- Pilot pricing intent: discount to make the yes easy, but keep it real
  money, because part of the pilot's job is demonstrating revenue. Include a
  clear statement of how the pilot is supported.

## 12. Refresh triggers

Update this snapshot when any of the following happens: a Wave 1 demo goes
public; the closed preview completes; first inbound commercial contact; first
paying pilot; any acquisition or licensing approach; a competitor ships
verified-accuracy maps; six months elapse with none of the above.

## 13. Source appendix (verified 2026-08-19)

Deals: Google/Windsurf license (techmeme.com/250711/p33; techcrunch.com
2025-08-01 payout split), Cognition/Windsurf (cognition.com/blog/windsurf),
Wix/Base44 (techcrunch.com 2025-06-18; calcalistech.com 2026-03-04 earnout),
Atlassian/DX (siliconangle.com 2025-09-18), OpenAI/Statsig (cnbc.com
2025-09-02), OpenAI/Astral (openai.com/index/openai-to-acquire-astral;
simonwillison.net 2026-03-19), OpenAI/Promptfoo (techcrunch.com 2026-03-09),
Anthropic/Bun (devclass.com 2025-12-03), Anthropic/Stainless (techcrunch.com
2026-05-18), Vercel/Better Auth (vercel.com/blog/vercel-acquires-better-auth),
GitKraken/CodeSee (gitkraken.com/blog, prnewswire.com 2024-05-14),
SpaceX/Cursor (forbes.com 2026-06-16; seekingalpha.com 2026-08-14),
OpenClaw/Steinberger (techcrunch.com 2026-02-15; openclaw.ai 2026-07-08),
Acquire.com multiples (blog.acquire.com Jan 2026 report).

Competitive: Cognition DeepWiki (cognition.com/blog/deepwiki; biggo.com
2025-08-27 accuracy concerns), Google Code Wiki (developers.googleblog.com
Nov 2025), Driver AI (driver.ai; tracxn May 2026), Mintlify Series B
(mintlify.com/blog/series-b), Port Series C (techcrunch.com 2025-12-11),
Atlassian Compass sunset (adaptavist.com 2026), CodeBoarding (github.com/
CodeBoarding), comprehension-debt data (addyosmani.com/blog/comprehension-debt;
digitalapplied.com 2026 survey aggregation; sonarsource.com State of Code).

Pricing: GoJS (nwoods.com/sales), JointJS+ (jointjs.com/pricing), tldraw
(tldraw.dev/pricing; biggo.com 2025-09-19), React Flow Pro (reactflow.dev/pro),
IcePanel (icepanel.io/pricing), Structurizr (docs.structurizr.com/server/
pricing), Sourcegraph (sourcegraph.com/pricing), SQLite ladder (sqlite.org/
prosupport.html), Zwibbler (zwibbler.com), pilot norms (getmonetizely.com;
dowhatmatter.com), audit consulting (variantsystems.io), GitHub Marketplace
95% (docs.github.com), JetBrains 85% (plugins.jetbrains.com/docs/marketplace),
VS Code no-paid-extensions (code.visualstudio.com/api; github.com/microsoft/
vscode/issues/111800), FSL (fsl.software; blog.sentry.io; powersync.com/legal/
fsl; keygen.sh/blog), GitHub Sponsors $100M (github.blog 2026-07-21).

GTM: HN reach (business.daily.dev; okara.ai 2026), DeepWiki badge adoption
(cognition.com/blog/deepwiki-mcp-server), OHF/Music Assistant amplification
(home-assistant.io/blog 2025-12-17; newsletter.openhomefoundation.org), K8s
trademark rules (linuxfoundation.org/legal/trademark-usage), Headlamp
endorsement (headlamp.dev/blog 2026-05-15), curl AI-slop backlash
(daniel.haxx.se 2025-07-14), cold email benchmarks (instantly.ai 2026),
DevRel contractor rates (marketerhire.com 2026-07-13), acqui-hire bands
(valueaddvc.com 2026-06-03), MCP registry (blog.modelcontextprotocol.io
2025-09-08; anthropic.com AAIF donation 2025-12-09).

## Changelog

- **2026-08-19 (b)**: Owner decisions recorded same day: consulting-attach
  deal posture, capture layer during a fast-tracked Wave 1 with the findings
  caveat, two-path pilot planning (ecosystem vs commercial), active outreach
  pass, FSL unchanged. Operating constraints added (owner plus spouse, no
  hires, contract-only help; security/liability response plan flagged as a
  required work item). Founding-partner pilot pricing guidance added to 5a.
- **2026-08-19**: Initial snapshot. State S0, pre-launch. Written from the
  six-track research pass; first recurring edition per DEMO-PROGRAM.md
  section 10.
