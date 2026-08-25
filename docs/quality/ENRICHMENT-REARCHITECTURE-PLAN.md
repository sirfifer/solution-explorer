# Enrichment Rearchitecture Plan: Multi-Tier Agent Orchestration

**Status**: Blueprint for two-expert personas to solve the $1,000→$90 efficiency gap  
**Date**: 2026-08-25  
**Scope**: Design the entire enhancement pipeline as an orchestrated multi-tier system

---

## Executive Summary

The killed 2026-08-25 run revealed not isolated bugs but systemic inefficiency: **$1,000+ to enhance 173 VS Code architecture components**, with Opus handling 47% of the work on validation failures caused by a bug, not difficulty. Analysis shows the path to **~$90 total cost** requires rethinking how work flows between rungs:

- **Rung 2a** currently runs at maximum reasoning effort ($xhigh), failing grounding checks due to validator bug, escalating work unnecessarily
- **Rung 2b/2c** receive escalated work without the prior rung's findings, forcing re-work  
- **Prompts are static**, asking every rung for the same contract shape, wasting tokens on audit scaffolding
- **Context isn't amortized**, re-prompted on each turn, billed at 2x cache-creation rate
- **Evidence is transcribed, not derived**, 31.3% of output re-spelling the prompt's own facts

The fix requires **expert orchestration design** — how to partition work, design dynamic prompts, use caching, escalate efficiently — not piecemeal field trimming.

---

## Current State (Baseline)

**Full-run cost as configured: $1,000+**

| rung | cost | model | targets/call | escalation rate | quality issue |
|---|---|---|---|---|---|
| 2a | $326 | Sonnet (xhigh effort) | 43.1 (avg) | — | 67.8% of output is reasoning, not JSON |
| 2b | ~$670 | Opus | 5 per call | **47%** (relationships) | validator bug rejects 93% of symbol citations; bug, not hard work |
| 2c | unmeasured | Opus | — | ~21% (escalated items) | — |
| **total** | **$1,000+** | — | — | — | **113 of 173 partitions project over output ceiling** |

**Why it's broken:**
1. Rung 2a asks "produce a complete, grounded contract" with maximum reasoning effort
2. Validator bug (`evidence.py:236`) rejects 93% of valid symbol citations  
3. Escalation to 2b is massive, losing the context of what actually failed
4. Each rung re-prompts, re-ingesting prior output as cache-creation input (2x billing)
5. No dynamic prompting — same schema for all three rungs

---

## Target State (Post-Rearchitecture)

**Full-run cost target: ~$90**

| rung | cost | model | work | prompt | context |
|---|---|---|---|---|---|
| 2a | ~$33 | Sonnet (low effort) | Bulk pass: grounding checklist | "Is this grounded? Yes/Escalate" | Facts + deterministic output |
| 2b | ~$45 | Opus | Medium: ground escalated + borderline | "Ground this item. Why?" | Prior findings + deeper facts |
| 2c | ~$12 | Opus | High: finalize hard cases | "Finalize this. Be certain." | Full context, final decision |
| **total** | **~$90** | — | — | — | **0 partitions over ceiling; 9x cost reduction** |

**How it works:**
1. Rung 2a is a **high-volume bulk pass** asking one question: "grounded, yes or escalate?"
2. Work that escalates carries **exactly what failed** as input to rung 2b
3. Each rung's prompt is **dynamically generated** based on prior rung's findings
4. Context is **cached once and reused** across rungs
5. **No re-prompting** — each rung hands off structured findings, not raw output

---

## The Two Expert Personas

### Persona 1: Agent Orchestration Architect

**Seed Source**: Lilian Weng (OpenAI researcher, "Agents" series on LLM agent workflows), Karpathy's compound AI systems framework, routing literature

**Background & Expertise:**
- 10+ years designing multi-tier AI systems with cost constraints
- Deep knowledge of: agent routing, capability-based delegation, context propagation, cost-benefit analysis of escalation
- Published work on efficient handoff protocols between model tiers
- Understands trade-offs: latency vs. cost vs. quality, when to escalate, how to design work for each tier

**How They Think:**
- Starts with the rung hierarchy: what should each tier be *asked* to do, not what can it do
- Designs from the output backward: what must 2c produce? What does 2b need to achieve that? What minimal work can 2a do?
- Obsessed with context: every token matters, cache efficiency is as important as model choice
- Escalation is a **cost**, not a feature — minimize it by asking each rung the right question

**Key Questions They'll Answer:**
- What is the *minimal* question each rung should answer to make escalation decisions?
- How should failed items be represented so the next rung doesn't re-discover the same facts?
- What context should be cached and reused across rungs?
- What is the optimal batch size and routing logic for each rung?

**Resources They'll Consult:**
- Multi-agent orchestration literature (Anthropic, OpenAI, DeepMind papers)
- LLM routing systems (Claude's own routing, Mixtral patterns)
- Cost-aware AI system design
- Prior art on capability-based delegation

---

### Persona 2: Prompt Efficiency Specialist

**Seed Source**: Brex LLM prompt engineering practices, OPRO (optimization by prompting) literature, prompt compression research, Linus Ekenstam (PromptEngineering)

**Background & Expertise:**
- 8+ years optimizing prompts for scale and cost
- Deep knowledge of: semantic compression, token efficiency, dynamic prompting, in-context learning, information-theoretic minimum context
- Has shipped systems where prompt engineering cuts inference cost by 60%+
- Understands: what information is *necessary* vs. nice-to-have, how to make prompts self-describing, how to encode decisions in structure

**How They Think:**
- Every token is a choice — why is it there, what does it earn?
- Prompts should be generated, not templated — different work gets different prompts
- Redundancy is the enemy: if information is in the input, don't ask the model to re-emit it
- Structure encodes decisions: the schema shape itself can make answers cheaper

**Key Questions They'll Answer:**
- What is the *minimum* prompt needed for rung 2a to make a grounding decision?
- How should prior-rung findings be encoded to make 2b's work cheaper?
- What structure (schema) makes answers cheaper to produce?
- Where is evidence coming from the prompt itself (wasteful) vs. from the model's analysis (valuable)?

**Resources They'll Consult:**
- Prompt optimization papers (prompt compression, in-context learning efficiency)
- Token economics literature
- Real systems that achieved 60%+ cost reductions through prompting
- Semantic compression and information theory

---

## The Central Question for Both Personas

**"Design an enrichment pipeline where:**
- **Rung 2a** is a cheap ($33/run), high-volume bulk pass that makes grounding decisions
- **Rung 2b** gets escalated work + the prior rung's findings, costs ~$45/run total
- **Rung 2c** finalizes hard cases, costs ~$12/run
- **Total cost** is ~$90 (9x reduction from $1,000+)
- **Quality** does not degrade — coverage and accuracy stay the same or improve
- **Zero partitions** project over the output ceiling

**Constraints:**
- Must work with Sonnet (2a) and Opus (2b/2c)
- Must handle 173 components, 5,453 relationships
- Must be deterministic and testable
- Must use the deterministic parser output as a foundation

**Deliverable:**
A detailed architecture document specifying:
1. The exact question each rung asks and why
2. The prompt structure for each rung (schema, instructions, examples)
3. How work is escalated (what information is passed, how it's structured)
4. Context strategy (what is cached, what is reused, what is fresh)
5. Cost projection by rung with token breakdown
6. How to test it works before a full run
**"

---

## Research & Analysis Phase (What the Experts Will Do)

### Orchestration Architect Will:
1. **Analyze the current ladder logic** (`analyzer/enrich/ladder.py`) to understand the current handoff protocol
2. **Map the escalation triggers** (what makes an item escalate from 2a to 2b?)
3. **Design the minimal handoff format** (what must 2b receive to not re-do work?)
4. **Specify routing logic** (should 2b/2c route to different batches? different models?)
5. **Model the cost by rung** using measured per-call costs and escalation rates
6. **Propose the checkpoint strategy** (where does absorption happen? When is work banked?)

### Prompt Efficiency Specialist Will:
1. **Audit the current prompts** (`analyzer/enrich/prompts.py`, `_CONTRACT_SCHEMA`, etc.) for redundancy
2. **Measure information overlap** (what % of evidence is already in the input facts?)
3. **Design the rung-specific prompts**:
   - **Rung 2a prompt**: "For each component/relationship, is the contract grounded? Answer PASS/ESCALATE with one-line reasoning"
   - **Rung 2b prompt**: "Ground these escalated items. [Prior findings]. Complete the contract."
   - **Rung 2c prompt**: "Finalize these items. Make certain. [Full context]."
4. **Encode findings as structure** (how should 2a's ESCALATE decisions be machine-readable for 2b?)
5. **Compute token savings** by eliminating redundant fields and re-prompting

### Both Will:
- **Consult real orchestration systems** (papers, code, design docs) to validate patterns
- **Test on a small sample** (5-10 partitions) to verify cost projections
- **Identify new risks** not visible in the current failure analysis
- **Recommend which fixes to do first** (validator bug, effort pin, then rearchitecture)

---

## Timeline for Next Session

1. **Persona definition** (this document) — use the seeds, build the detailed personas
2. **Research & analysis** (Orchestration + Prompt agents, parallel) — 2-3 hours
3. **Architecture draft** — detailed spec from both experts
4. **Cost model validation** — sample run on 5 partitions at proposed design
5. **Implementation plan** — what code changes, in what order, with checkpoints

---

## Key Documents & Resources

- **Overflow postmortem**: `docs/quality/postmortem/2026-08-25-enrichment-overflow.md` — root cause analysis
- **Efficiency postmortem**: `docs/quality/postmortem/2026-08-25-efficiency.md` — detailed cost breakdown by field
- **Memory**: `~/.claude/projects/-Volumes-Studio-dev-solution-explorer/memory/` — cached findings on effort, validator bug, component duplication
- **Current ladder code**: `analyzer/enrich/ladder.py:320-620` — the orchestration to redesign
- **Current prompts**: `analyzer/enrich/prompts.py:827-882` — contract partition prompt (the 2a ask)
- **Live transcripts**: 37 subprocess sessions in `~/.claude/projects/-Volumes-Studio-dev-solution-explorer/` — real data on token breakdown by rung

---

## Success Criteria

✅ **Architecture spec** that specifies the question each rung asks, the prompt shape, and the handoff protocol  
✅ **Cost projection** of ~$90 total with token breakdown per rung  
✅ **Sample validation** on 5 partitions showing the projection holds  
✅ **Implementation roadmap** specifying code changes in dependency order  
✅ **Risk assessment** identifying new failure modes introduced by the redesign  

**NOT a success if:**
- Projection remains theoretical without sample validation
- Quality degrades in the sample test
- Handoff protocol is vague or unmeasurable
- Implementation plan has unknown dependencies

---

## Next Steps

1. **Read this document** in a fresh session
2. **Use it to spawn the two personas** (detailed instructions in the prompt template below)
3. **Run the Orchestration Architect** to design the rung hierarchy and handoff protocol
4. **Run the Prompt Efficiency Specialist** to design the dynamic prompts and encode findings
5. **Synthesize** their findings into the architecture spec and sample test plan

---

## Initial Prompt Template for New Session

When you open a fresh session, use this to spawn the two agents:

```
You have two specialized agents to engage:

## Agent 1: Agent Orchestration Architect
Seed from: Lilian Weng (OpenAI agent research), Karpathy (compound AI systems)
Expertise: Multi-tier AI system design, capability-based routing, context efficiency
Task: Design the rung hierarchy and escalation protocol for the enhancement pipeline

Your prompt: "You are an expert in multi-tier AI system orchestration with 10+ years 
designing cost-efficient agent hierarchies. Your job is to redesign how the enrichment 
enhancement rungs (2a, 2b, 2c) work together to reduce cost from $1,000+ to ~$90 while 
maintaining quality.

Read: docs/quality/postmortem/2026-08-25-overflow.md, 2026-08-25-efficiency.md

Design:
1. What is the minimal question each rung should answer?
2. How should failed items be represented for the next rung (what context is passed)?
3. What context should be cached and reused across rungs?
4. What is the routing logic and escalation threshold for each rung?

Deliverable: Rung hierarchy specification with cost projection per rung and total.

## Agent 2: Prompt Efficiency Specialist
Seed from: Brex LLM prompt engineering, OPRO literature, prompt compression research
Expertise: Token-efficient prompting, semantic compression, dynamic prompt design
Task: Design the prompt structure for each rung to be dynamically generated and cost-minimal

Your prompt: "You are an expert in prompt optimization who has cut inference costs by 60%+ 
through prompting alone. Your job is to design the three rung prompts (2a, 2b, 2c) to be:
- Dynamically generated based on prior-rung findings
- Minimal in tokens (no redundancy with input facts)
- Structured so decisions are encoded, not re-computed

Read: analyzer/enrich/prompts.py (current prompts), docs/quality/postmortem/2026-08-25-efficiency.md

Design:
1. What is the minimal prompt for rung 2a to make a grounding decision?
2. How should findings from 2a be encoded for 2b?
3. What schema shape makes answers cheaper to produce?
4. Where is evidence wasted (re-emitted from the prompt)?

Deliverable: Rung-specific prompts with token projection and savings vs. current design.
```

---

## Why This Approach

This plan avoids:
- ❌ Trying to redesign a complex system in one head (mine)
- ❌ Losing nuance by staying in the weeds of field-level trims
- ❌ Reinventing orchestration patterns that have real precedent

It ensures:
- ✅ Two independent expert perspectives challenge each other
- ✅ Prompts are grounded in real prior art, not speculation
- ✅ The redesign is validated on a sample before the full run
- ✅ Cost projections have confidence because they're from measured data

---

