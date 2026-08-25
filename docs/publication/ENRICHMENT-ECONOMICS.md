# Enrichment economics: spend less without spending quality

The standing order, in the owner's words: make this as cheap as possible **without
ever compromising quality, utility, or comprehensibility by humans and AI**, and
not even coming close to compromising them. Effort spent raising the success rate
at each rung is not a cost-cutting exercise, it makes everything faster and
better at once.

Three rules follow from that, in priority order.

---

## 1. Deterministic first, always

**Every question a parser can settle should be settled by a parser.**

There is no downside as long as the deterministic answer is not worse and not
riskier. If it works it works; if it does not, it falls through to the model tier
exactly as before, and nothing is lost. The asymmetry is total: a fact computed
deterministically costs nothing, cannot hallucinate, is identical on every run,
and is available to every later stage.

The compounding argument is the important one. Deterministic work does not merely
replace a model call. It **improves the input to enrichment**, so the model tier
spends its budget on the questions that genuinely need judgement instead of
rediscovering facts. Better data in, better data out. Moving work down is how the
enrichment gets *more* capable, not less.

This is why the Run Report's "Questions the parser should have answered" table is
the first thing in its improvement section. Those entries are declared by the
model tier itself (`parser_first`), so they are not guesses about what could be
automated: they are the tier saying it was asked something it should not have
had to reason about.

**The 2026-08-24 parser incident is the cautionary half of this rule.** Moving
work deterministic-side only pays if the deterministic side is trustworthy. A
regex parser silently standing in for tree-sitter produced 355,617 symbols where
there should have been 153,231 and 55 methods where there should have been
28,501, while reporting 100% coverage. Determinism is worth nothing without
verification; see `census.parser_degraded` in `scripts/lint-projection.py`.

---

## 2. Every escalation is a question about the rung below

An escalation tree is not a mechanism for eventually reaching a model that can
answer. Its value is that the **cheapest rung is handed context good enough to
succeed**, and every climb is evidence that some specific context was missing.

So the question after every escalation is not "was Opus right" but:

> What would Sonnet have needed to get this right?

Not answered mid-run, which would cost more than the escalation did. Recorded, in
the Run Report's `escalation_economics` section, so it can be answered
deliberately afterwards. Each trigger carries a suspect:

| Trigger | Meaning | Suspect |
|---|---|---|
| E1 | no answer to a required question | reasoning, usually genuine |
| E2 | answer given, evidence not citable | **context** |
| E3 | evidence contradicts a known fact | **context** |
| E4 | answer would fit a sibling equally well | **context** |
| E5 | tier declares it cannot reconcile the code | reasoning |

Three of the five triggers are context failures before they are capability
failures. A tier that had the facts and could not ground them was probably not
given them well.

**Why an avoided escalation is worth more than its price.** On a Max plan, Sonnet
and Opus draw from *separate* weekly buckets. Work moved down the ladder does not
just cost fewer dollars, it stops consuming the scarcer allowance. An Opus-heavy
run can exhaust its own bucket while the all-models bar still looks comfortable,
so the split matters more than the total.

---

## 3. Tools at a lower rung: a live hypothesis, not a decision

The proposition is that **Sonnet with tools may beat Opus reasoning unaided**, at
lower cost. It is plausible and it is not yet established. Both halves matter.

**Evidence for.** On GAIA, 4B models *with* tools outperformed 32B models
*without* them (18.18% vs 12.73%), which says tool access changes the capability
calculus rather than merely padding it. Targeted agentic training has closed most
of the gap between small and large models on specific domains.

**Evidence against, and it is the specific risk here.** Lower-capability models
consume **more tokens inside the agent loop**, which can more than offset a lower
per-token price. The honest unit is cost per completed task, not price per token.
A cheaper model that loops four times is not cheaper.

**And our own architecture currently argues the other way.** The ladder pins
*pure inference*: one turn per call. `analyzer/enrich/pipeline.py` raises a loud
note when a rung call reports more than one turn, because an agentic loop
"multiplies tokens and replaces the JSON answer with tool narration". That
decision protects two things at once, the token budget and the machine-readable
answer format. Introducing tools at a rung is therefore a deliberate reversal of
a reasoned choice, not a free improvement.

**How this gets settled: measurement, not argument.** The instrument already
exists. Run a real partition set both ways and compare cost per *grounded item*,
not cost per call:

- control: current pure-inference Sonnet rung, escalating as it does today
- variant: Sonnet with a bounded tool surface and a turn cap, same partitions

Then compare, from the Run Report and `scripts/usage-budget.py`:

1. items reaching `grounded` without escalation (quality, the gate)
2. total tokens **including** loop turns (the caveat above)
3. Opus-bucket consumption avoided (the bucket that is actually scarce)
4. whether any answer arrived as narration instead of JSON (the format risk)

The variant wins only if (1) holds or improves. Cheaper at the cost of grounding
is not cheaper; it is the one trade this project does not make.

---

## Sources

- [Small Language Models for Efficient Agentic Tool Calling](https://arxiv.org/pdf/2512.15943)
- [AgenticQwen: Training Small Agentic Language Models](https://arxiv.org/pdf/2604.21590)
- [Agentic Performance at the Edge: Insights from Benchmarking](https://arxiv.org/html/2605.10384)
- [Claude's Weekly Limit: All-Models vs Sonnet vs Opus](https://tokn.watch/blog/claude-weekly-limit/)
