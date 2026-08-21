# Enrichment calibration: what ran, what it cost, what it means

Written 2026-08-20 (N3), replacing the cost projection in `DECISIONS-N3.md`,
which was wrong. Read this instead.

---

## 0. Correction first

`DECISIONS-N3.md` projects a full VS Code enrichment run at **$37.56**. **That
number is wrong and should not be used.** It was a token-weighted extrapolation
that assumed cost scales with prompt tokens. The per-partition data disproves
that assumption, and I did not check it before publishing the figure.

The honest projection is **somewhere between roughly $38 and $79**, and the
spread is not noise. Section 4 explains what drives it and why it cannot be
narrowed without more data.

This is the same failure shape this project keeps recording: a plausible number,
a partial check, a confident conclusion. The extrapolation looked more rigorous
than the naive one it replaced, which is exactly what made it convincing.

---

## 1. Was the cost measured or estimated?

Both, and they are different things that are easy to conflate.

| Figure | Kind | Source |
|---|---|---|
| **1,446,236 prompt tokens** | **Estimate** | `enhance --dry-run`. Input side only. Models no output tokens and no cost |
| **$9.1920 for this run** | **Measured** | Reported by the `claude` CLI itself, `total_cost_usd` in its JSON envelope, summed across the six calls |

**No dollars were charged.** Enrichment runs on the Claude Code subscription, so
the CLI's dollar figure is the API-equivalent price of the work. Treat it as a
proxy for how much subscription usage the run consumed, and as the number that
*would* apply if this ever moved to a billed API key. It is measured, not
guessed, but it is a usage proxy, not an invoice.

---

## 2. What actually ran

**One model. Sonnet. Nothing else.** No tiering exists in the code, so:

| Tier | What it did in this run |
|---|---|
| **Sonnet** | All 5 partitions and the architecture narrative. Every field of every payload |
| **Opus** | **Nothing.** No ladder exists |
| **Fable** | **Nothing.** No ladder exists |

The command:

```
analyze.py enhance <root> --store <db> --max-partitions 5 --model sonnet --report <json>
```

### The pipeline as it exists today

```
  fact store (570 components, 5,469 relationships)
        |
        v
  deterministic partitioner            <- no AI, byte-stable
        |
        +--> 55 partitions + 1 narrative pass
        |
        v
  FOR EACH partition:  ONE `claude -p` call
        |              input:  component metadata, file lists, relationships
        |              output: ALL fields for EVERY component in that partition
        v
  completeness scorer  <- the gate. Checks form, never truth
```

**The granularity is: one call per partition, one model, all fields at once.**
That single call does the mechanical work (restate the language, count the
files) and the hard work (what is this thing *for*, is this classification
right) in the same breath, at the same price, with no seam between them.

That seam is the whole opportunity, and it is what section 5 is about.

### What one call produced

Partition 0 covered 7 components. For `cli/src/tunnels` Sonnet returned:

| Field | Value (truncated) |
|---|---|
| `description` | "Remote tunneling, dev-tunnel, and code-server hosting engine." |
| `architectural_role` | `proxy` |
| `criticality` | `critical` |
| `tech_context` | "Rust with Tokio; tunneling, the control server, and code-server hosting are all concurrent network services..." |
| `complexity_assessment` | "At 13,860 lines across 30 files, this is by far the largest module in the CLI..." |
| `data_handled` | "Dev Tunnels session tokens and port mappings, code-server HTTP/WebSocket connections, systemd/journalctl service logs..." |
| `testing_assessment` | "No unit, integration, or e2e tests are recorded for this module despite CI running against it..." |
| `testing_maturity` | `untested` |
| `help_text` | "This is the largest module in the CLI, at 13,860 lines across 30 files, implementing Dev Tunnels session negotiation..." |

This is good output. Specific line counts, real technology (Tokio, systemd,
journalctl), and an honest testing verdict rather than a flattering one. Any
judgement about "can Sonnet do this work" has to start from the fact that this
is what it produced.

---

## 3. The measured breakdown

| Partition | Components | Relationships | Prompt tokens (est.) | Cost (measured) | $ / 1k input tok | Mean completeness |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 7 | 10 | 156,212 | $1.9016 | 0.0122 | 90.4 |
| 1 | 30 | 0 | 9,126 | $0.9438 | **0.1034** | 85.7 |
| 2 | 30 | 2 | 8,155 | $0.7001 | 0.0858 | 85.5 |
| 3 | 2 | 56 | 11,356 | $0.6563 | 0.0578 | 92.1 |
| 4 | 30 | 1 | 7,671 | $0.8379 | **0.1092** | 85.3 |
| narrative | - | - | 169,886 | $4.1522 | 0.0244 | - |
| **total** | **99** | **69** | **362,406** | **$9.1920** | | **86.0** |

Zero failed partitions, zero retries, 69 of 69 relationships valid, no
validation errors.

---

## 4. The finding that matters most: input is cheap, output is expensive

Look at the `$ / 1k input tok` column.

- **Partition 0** took **156,212** input tokens and cost **$1.90**.
- **Partition 1** took **9,126** input tokens, **17x less**, and cost **$0.94**,
  only half as much. Per input token it was **8.5x more expensive**.

The difference is what each was asked to *write*. Partition 0 covered 7
components; partition 1 covered 30. **Cost tracks the volume of output, not the
volume of context.**

Fitting `cost = a x input + b x components + c x relationships` over the five
partitions gives roughly `$10.54 per 1M input tokens + $0.024 per component +
$0.009 per relationship`, and attributes the measured $5.04 of partition cost
as: **$2.03 input, $2.41 components, $0.60 relationships.** Input is the
*smallest* of the three.

### Why the projection stays wide

That fit extrapolated to the full run gives **$78.69**. Treat it as a ceiling,
not an answer, for one specific reason: the full run has **5,469 relationships**
and this sample saw **69 of them, 1.3%**. The relationship coefficient carries
$47 of the projected $74.54 while resting on the thinnest evidence in the
dataset. The earlier input-weighted method gives $38. The truth is bracketed by
those two and cannot be narrowed without a sample that actually contains
relationships.

**Practical consequence:** if the full run matters, the next calibration should
deliberately select relationship-dense partitions (37, 41, 47, 49, 50, 51) rather
than taking the first five.

### Why this validates the re-framing

If cost were driven by context, the efficiency play would be to feed cheaper
models less. It is not. **The efficiency play is to stop expensive models from
re-writing what a cheaper model already wrote.** A higher tier that reads a
compact digest of Sonnet's output and emits only a verdict or a correction pays
the input rate, roughly $10 per million tokens, and almost nothing for output.
A higher tier that redoes the pass pays the output rate on every field.

That is the difference between an escalation ladder that is nearly free and one
that costs more than running Opus over everything from the start.

---

## 5. Evaluation of the Sonnet baseline

**Where it did well.** Specific, non-generic, honest. It reported `untested` for
a critical module rather than flattering it, and it grounded claims in real
counts. Zero failures, zero retries, zero validation errors.

**What we cannot say from this run.** Whether any of it is *true*. The gate that
passed it is a completeness metric (50% required fields non-empty, 10%
help_text sentence count, 30% optional fields populated, 10% valid enum). It
never checks correctness, which is why 83 of 99 components scored *exactly*
85.0, differing only in `optional_populated: 2/4`. The correctness instrument,
`analyze.py verify` with its confirmed/refuted/uncertain verdicts, exists and
**was not run and is not in the graduation gate.**

**So the honest verdict on "can we get away with the lower model" is: not yet
answerable.** The output reads well and one spot-check held up. Nothing has
tested whether the classifications are right, and misclassification (S2) was the
single worst trust defect the comprehension study found.

---

## 6. The re-framing, and why it is the better design

The original framing was: run all 55 partitions on Sonnet, pick ~15 for Opus,
pick ~5 of those for Fable. **Partition-shaped escalation.**

The better framing, from the owner 2026-08-20: it is less about *which items* a
higher model re-reviews and more about *what nature of work* each tier does, so
**a higher tier never redoes the grunt work.**

Section 4's cost data says this is not merely tidier, it is the difference
between a ladder that is nearly free and one that costs more than just running
Opus over everything. Partition-shaped escalation makes the expensive model
*re-write* every field for the partitions it touches, and writing is what costs.
Nature-shaped delegation makes it *read* a digest and emit a verdict.

### The four natures of work inside one enrichment call today

One call currently produces all of these at one price with no seam:

| # | Nature | Fields | Really needs |
|---|---|---|---|
| 1 | **Restatement** of facts the analyzer already holds | `tech_context`, `complexity_assessment` | **The parser.** "Rust with Tokio", "13,860 lines across 30 files" are not AI work |
| 2 | **Labelling** into constrained vocabularies | `description`, `architectural_role`, `criticality`, `testing_maturity` | Cheap to emit, expensive to get wrong. The S2 surface |
| 3 | **Assessment** from evidence | `testing_assessment`, `data_handled` | Real reading. Sonnet did this well |
| 4 | **Explanation** for a human navigating the map | `help_text` | The utility priority. The hardest and most valuable |

Plus, across components: **synthesis** (the architecture narrative) and
**verification** (the `verify` verdicts, which nothing currently runs).

### Proposed phase-decomposed pipeline

```
  PHASE 0   PARSER, no AI
            everything deterministically derivable.
            Fed by the parser-first rule below.
                |
                v
  PHASE 1   SONNET, all 570 components
            natures 2 and 3: labels, descriptions, assessments.
            High output volume on the cheap tier. The grunt work.
                |
                +--> compact digest: label + evidence pointer per component
                |    (NOT the full prose)
                v
  PHASE 2   OPUS, reads the digest, writes almost nothing
            adjudicates natures 2 only: is this label supported by this
            evidence?  emits agree | correct | uncertain(+reason).
            NEVER re-emits a description. Pays input rate (~$10/1M),
            near-zero output.
                |
                +--> the uncertain set + the navigation-critical set
                v
  PHASE 3   FABLE, few components
            nature 4 and synthesis: help_text for the components that
            carry navigation, the architecture narrative, and whatever
            Phase 2 could not settle.
```

**The invariant that makes it cheap: no phase rewrites a previous phase's
output.** Phase 2 reads and judges. Phase 3 writes only where writing is worth
the top tier.

**It also degrades cleanly to the owner's fallback.** If Phase 1 quality turns
out to be poor, Phase 1's model becomes Opus and Phase 2 collapses into it. The
phases are the design; the model per phase is configuration.

### What "success" has to mean here

Priority order, owner, 2026-08-20:

1. **Quality, richness, accuracy, and above all utility** — can a person, or an
   agent, genuinely understand and navigate the model.
2. **Token efficiency** — a high priority, but strictly secondary to 1.

Note that **no current instrument measures 1.** The completeness scorer measures
form. The `verify` passes would measure accuracy. Utility is measured only by
the comprehension review, which is per-subject and expensive. Any claim that a
tiering change "worked" needs to say which of these it moved.

---

## 7. Standing rules recorded 2026-08-20

### 7.1 The parser-first question, no exceptions

**Every enrichment review, every pass, asks this first, before anything else:**

> This fact appears missing, wrong, or thin. **How could the parsing and
> deterministic processing have gotten this right, and how do we improve it so
> next time it does?**

Not an optional observation category. The **first** question, every time. The
reasoning: deterministic extraction is free, reproducible, and improves for
every future subject, while an AI-written fix is paid for once per refresh
forever. `tech_context` saying "Rust with Tokio" is the clearest example: the
analyzer already knows the language and the dependency manifest already names
Tokio.

Mechanically this becomes a required output field carrying a proposed parser
improvement, which feeds the findings loop (`DEMO-PROGRAM.md` 5.2) as a
`capability:` card rather than being lost in prose.

### 7.2 Lessons travel home

The product is licensed, not open source, and not intended for others to run
themselves. Licensing therefore includes a phone-home for lessons learned,
scrubbed for privacy, IP and security per contract. Many of the most valuable
lessons are abstract enough to survive heavy scrubbing: "a Rust component whose
manifest names Tokio should not need AI to say so" carries no customer content
at all. This is what makes 7.1 compound across every deployment rather than only
improving the subject in front of us.

### 7.3 No regression, and how to get there without timidity

**No regression is one of the hardest and most important rules in this process.**
It does **not** mean "this might break something, so do not touch it." Refusing
to take a risk is its own failure.

The protocol:

1. Take the risk **in isolation**: a worktree, a branch, a transaction, a
   sandboxed run. The mechanism does not matter; the isolation does.
2. **Validate on real work**, not on a toy. Measure whether the change actually
   improved usefulness, validity or results.
3. If it does not clear the line, **roll back**. That is a successful
   experiment, not a failure.
4. Before anything merges, vet it against **both**:
   - the code that motivated the change and showed the defect, **and**
   - **multiple randomly chosen other parts of a codebase**, to confirm nothing
     else regressed.

Step 4's second half is the one that gets skipped, and it is the one that caught
the FastAPI incident: fixing a classification removed an accidental exclusion
elsewhere and produced 68 bogus findings. The golden corpora exist for exactly
this and must be run on both, every time.
