# Product vision (canonical, owner-refined 2026-07-20)

This document is the running canonical statement of the product vision. Owner
restatements ENHANCE it; they do not replace it. When a restatement conflicts
with what is recorded, work STOPS and the conflict goes to the owner for a
call. The 2026-07-20 restatement was checked against everything below and
against TARGET-ARCHITECTURE.md and LENS-DESIGN.md: it is additive, no
conflicts found.

## The core

A graphical, easy-to-navigate website that is a full representation of a
codebase. At minimum a single repo; real solutions span repos (multi-repo is
designed in MULTI-REPO-DESIGN.md). It represents 100 percent of what is in
the repo: not just code, every artifact, accounted for through one means or
another, digested and understood from every reasonable angle. Views, stories,
and navigable pathways through the application from different perspectives:
user interface, user workflow, technology patterns, and angles not yet
thought of. Discovering new valuable angles is part of the work, and every
candidate angle gets hard value tests and pushback; nothing lands that
muddies the water. When an existing view seems weak, the default posture is
that the idea is sound and the implementation needs work: figure out what is
missing and build it out, never quietly drop it.

Humans first, uncompromisingly. A person in technology who does not know the
codebase or even the language must navigate efficiently, figure out how it
works, and start finding issues (duplicated libraries and worse) with no AI
required. AI is a first-class interface second in priority: an AI pointed at
a deployed site consumes the enumeration at a fraction of raw-repo token
cost and can guide the human to what matters.

## Stakeholder views (2026-07-20 enhancement)

Different stakeholders need different views, and some views hide most of the
technical surface:

- Technology outsiders to the codebase: the existing lens set, plus whatever
  the angle-discovery work adds.
- Support personnel: how the app behaves, where things are configured, what
  can go wrong where.
- Business and executive stakeholders: a view translated entirely into
  business rules and business logic, encompassing the system without
  technical language.
- SECURITY VIEW: focused on security in every shape: data, communications,
  authentication, secrets handling, everything about how security is dealt
  with.
- SUPPLY CHAIN VIEW: everything not written from scratch identified: every
  library, every dependency, with versions and pinning (per-language nuances
  like a pinned SDK version or a target/supported runtime version called out
  explicitly, not buried).

## SBOM (2026-07-20 enhancement, hard requirement)

A Software Bill of Materials, as accurate and complete as possible, built by
the tool and included in every SysCorpus site. All dependencies with
versions and pin status; language-specific target/SDK versioning surfaced
both inside the SBOM and separately in the supply chain view.

## Regulatory angle: EU Cyber Resilience Act (2026-07-20, to be evaluated)

The owner flagged the EU CRA (SBOM, reporting requirements, regulatory
obligations, penalties, phased implementation) as a candidate dedicated view
or dashboard, alongside its role as a findings source (for example, expected
repo artifacts like SECURITY.md present or missing). Explicit instruction:
think it through honestly. Is a dedicated CRA view real value, or is the
SBOM plus a compliance checklist most of the substance? The evaluation is a
design task with a recommendation, not an assumed build.

## No theater (owner, 2026-07-20)

The tool must never be fluff or a salesman's dream for marketing hype. Real
value and real capability only; any flash or show is purely earned by what it
actually is, not how it looks. This is why the CRA work is a truthful
checklist artifact and not a dashboard, and the test applies to every future
surface.

Dogfooding: the self-repo dogfood site stays local (no public deploy). The
public angle is covered by the demo sites; two different codebases are
analyzed for diversity, and the tool always dogfoods itself.

## Standing tests for anything new

Value first: an addition must let a named stakeholder do something they
could not do, or do it much faster. No noise, no complexity for its own
sake. Everything drillable to any line including tests. Deterministic
skeleton, AI as overlay. 100 percent accounting is the only mode.
