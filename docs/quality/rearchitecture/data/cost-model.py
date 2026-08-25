#!/usr/bin/env python3
"""Per-rung cost model for the rearchitected enrichment ladder. Revision 2.

Companion to ../ORCHESTRATION-SPEC.md (post-adjudication revision). Every
constant is labeled with its source. Run it to reproduce every dollar figure
in the spec's cost tables:

    python3 docs/quality/rearchitecture/data/cost-model.py

Sources:
- "ADJ"    docs/quality/rearchitecture/data/qa-adjudication.json (binding)
- "PE"     PROMPT-SPEC.md and its data/ artifacts (QA-confirmed measurements)
- "ledger" demos/runs/vscode/2026-08-25/enrichment/ledger.jsonl
- "store"  re-derivations against /Volumes/Studio/dev/.demo-corpus/_out/vscode/index.db
- "PM"     the two 2026-08-25 postmortems
- "FLAGGED" an assumption with its resolving measurement named

Revision 2 replaces: chars/token 1.71 (falsified, ADJ dispute 1), the output
fit 1,100/320/4,400 (falsified on the held-out point, ADJ dispute 2), and the
$15/$75 Opus/Fable prices (Fable falsified by its own ledger row, ADJ
dispute 3). Opus is dual-priced; the first pilot Opus ledger row arbitrates.
"""
import math

# ---- adjudicated calibration (ADJ) ----
CT = 2.886          # marginal chars per billed token (fit slope over 35 first
                    # turns; spot check c95c2999 = 2.72). Applied ONLY where a
                    # chars-measured quantity has no direct token measurement.
CLI_OVERHEAD = 12_546   # fixed prompt-side tokens per call (fit intercept);
                        # created once per rung warm call, cache-read after.

# Prices per token, API-equivalent. Sonnet and Fable are ledger-verified
# (ADJ dispute 3: row 2 to 1.6%, p1 row to 1.8%). Unique per-call input bills
# as 1h cache creation at 2x base (observed CLI behavior, every first turn).
S_W, S_R, S_OUT = 6e-6, 0.3e-6, 15e-6          # sonnet $3/$15
F_W, F_R, F_OUT = 20e-6, 1.0e-6, 50e-6         # fable $10/$50 (ledger-fit)
# Opus: DUAL-PRICED, the open variable. No Opus row exists in any ledger.
OPUS = {
    "5/25":  (10e-6, 0.5e-6, 25e-6),           # current-sheet claim (PE)
    "15/75": (30e-6, 1.5e-6, 75e-6),           # legacy-sheet alternative
}

# ---- output model at --effort low, tier B (current schema) (ADJ) ----
CB_OUT, RB_OUT, FIX_OUT = 1050, 382, 1369      # lsq over all 4 replay probes,
FIX_BOUNDS = (500, 2800)                       # max err 5.7%; fixed-term
                                               # bounds carried per ADJ.
# Tier C schema (PE measured transform, central): comp 880+20 entry,
# rel 124+20 entry; per-call fixed kept at the adjudicated 1,369.
CC_OUT, RC_OUT = 900, 144                      # PE, resolved by M-P1/M-4

# ---- structure (store; QA-verified exact) ----
N_COMP, N_REL, N_GROUPS = 569, 5453, 55
COMP_CALLS = 61     # cap 21 per G2 dispersion rule: 6 groups (5x30, 1x24)
                    # split in two (store re-derivation, matches PE)
REL_CALLS = 100     # batch 80, per-group chunking (store)

# ---- input volumes, scaled tokens (PE direct measurements, QA-confirmed) ----
COMP_FACTS = 373_182    # all 569 fact blocks, byte-capped 20k/component (PE D7)
EDGE_MENUS = 51_900     # new edges menus, all 569 (PE 2.2)
REL_FACT = 235          # per relationship fact block (PE D5, n=400)
REL_CTX_CALL = 4_700    # component one-liners per 2a-R call: 3,703 measured
                        # with parser-era descriptions + ~1k fresh-run (PE D6
                        # + its stated caveat; FLAGGED, M-5/M-P1)
PREFIX = {"2aC": 4364, "2aR": 2808, "2b": 3072, "2c": 2745}   # PE re-measure
# after the l/need prompt additions (QA final verdict E-2)

# ---- escalation (PM recompute; QA final verdict E-1) ----
P2B_COMP, P2B_REL = 285, 654                   # 939 total, the postmortem
# baseline (285 restored per E-1; the 284 was an int-floor artifact). M-P5's
# harness recompute supersedes both counts when it runs.
COMP_ITEM_IN = 1727 + 750   # escalated-set facts mean (PE D8 planning figure;
                            # population FLAGGED, M-2) + handoff (FLAGGED, M-2)
REL_ITEM_IN = 235 + 400
D_COMP_OUT, D_REL_OUT = 480, 145               # delta-only repairs (FLAGGED,
                                               # M-2; failed-question
                                               # distribution runs on the V-5
                                               # harness at $0 first)
# 2c items carry two attempts (protocol); out is gap-or-repair per item.
C2_COMP_IN, C2_REL_IN = 2477, 635              # PE D11 + second attempt
C2_COMP_OUT, C2_REL_OUT = 300, 120             # FLAGGED, M-2/M-P3
P2C_FRACS = (0.10, 0.20, 0.30)                 # entry fraction (FLAGGED, M-2)


def _warm_reads(calls, prefix, w, r):
    """Warm call creates CLI overhead + prefix at 2x; later calls read at 0.1x."""
    warm = (CLI_OVERHEAD + prefix) * w
    reads = (calls - 1) * (CLI_OVERHEAD + prefix) * r
    return warm + reads


def rung2a(schema):
    cb, rb = (CB_OUT, RB_OUT) if schema == "B" else (CC_OUT, RC_OUT)
    out_c = N_COMP * cb + COMP_CALLS * FIX_OUT
    in_c = COMP_FACTS + EDGE_MENUS
    cost_c = out_c * S_OUT + in_c * S_W + _warm_reads(COMP_CALLS, PREFIX["2aC"], S_W, S_R)
    out_r = N_REL * rb + REL_CALLS * FIX_OUT
    in_r = N_REL * REL_FACT + REL_CALLS * REL_CTX_CALL
    cost_r = out_r * S_OUT + in_r * S_W + _warm_reads(REL_CALLS, PREFIX["2aR"], S_W, S_R)
    return cost_c, cost_r, out_c, out_r


def rung2b(batch, price_key, fix=FIX_OUT):
    w, r, o = OPUS[price_key]
    calls = math.ceil(P2B_COMP / batch) + math.ceil(P2B_REL / batch)
    out = P2B_COMP * D_COMP_OUT + P2B_REL * D_REL_OUT + calls * fix
    inn = P2B_COMP * COMP_ITEM_IN + P2B_REL * REL_ITEM_IN
    return calls, out * o + inn * w + _warm_reads(calls, PREFIX["2b"], w, r)


def rung2c(frac, batch=5):
    nc, nr = round(P2B_COMP * frac), round(P2B_REL * frac)
    calls = math.ceil(nc / batch) + math.ceil(nr / batch)
    out = nc * C2_COMP_OUT + nr * C2_REL_OUT + calls * FIX_OUT
    inn = nc * C2_COMP_IN + nr * C2_REL_IN
    return nc + nr, calls, out * F_OUT + inn * F_W + _warm_reads(calls, PREFIX["2c"], F_W, F_R)


def g2_worst(cap, block, fix=FIX_OUT, dispersion=1.90, ceiling=64_000):
    """G2 rule: worst-call mean x dispersion at or under 0.85 x ceiling."""
    mean = cap * block + fix
    return mean, mean * dispersion, mean * dispersion / ceiling


if __name__ == "__main__":
    for schema in ("B", "C"):
        c, r, oc, orr = rung2a(schema)
        print(f"2a tier {schema}: comp ${c:.1f} + rel ${r:.1f} = ${c + r:.1f} "
              f"(out: comp {oc:,}, rel {orr:,})")
    for pk in OPUS:
        for b in (5, 15):
            calls, cost = rung2b(b, pk)
            print(f"2b opus {pk} batch {b}: {calls} calls ${cost:.1f}")
    for f in P2C_FRACS:
        n, calls, cost = rung2c(f)
        print(f"2c entry {f:.0%}: {n} items, {calls} calls, ${cost:.1f}")
    n, calls, cost = rung2c(1.0)
    print(f"2c worst case (all {n} items): {calls} calls, ${cost:.1f}")

    print("\nG2 dispersion check (rule: mean x 1.90 <= 0.85 x 64,000 = 54,400):")
    for cap, blk, label in ((21, 1283, "2a-C cap 21, conservative block 1,263+20"),
                            (24, 1283, "2a-C cap 24 (rejected)"),
                            (80, 173, "2a-R batch 80, conservative 153+20")):
        m, disp, share = g2_worst(cap, blk)
        print(f"  {label}: mean {m:,.0f}, x1.90 = {disp:,.0f} ({share:.1%} of ceiling)"
              f" -> {'PASS' if disp <= 54_400 else 'FAIL'}")

    print("\nLadder bands (2c central 20%):")
    for pk in OPUS:
        for b, blabel in ((5, "batch 5 (default)"), (15, "batch 15 (M-2 gated)")):
            lo = sum(rung2a("C")[:2]) + rung2b(b, pk)[1] + rung2c(0.10)[2]
            mid = sum(rung2a("C")[:2]) + rung2b(b, pk)[1] + rung2c(0.20)[2]
            hi = sum(rung2a("B")[:2]) + rung2b(b, pk)[1] + rung2c(0.30)[2]
            print(f"  opus {pk}, {blabel}: lo ${lo:.0f} mid ${mid:.0f} hi ${hi:.0f}")
    # sensitivity: adjudicated fixed-out bounds
    base = sum(rung2a("C")[:2]) + rung2b(5, "5/25")[1] + rung2c(0.20)[2]
    for fb in FIX_BOUNDS:
        delta = (fb - 1369) * (COMP_CALLS + REL_CALLS) * S_OUT \
              + (fb - 1369) * rung2b(5, "5/25")[0] * OPUS["5/25"][2] \
              + (fb - 1369) * rung2c(0.20)[1] * F_OUT
        print(f"  mid sensitivity, fixed-out {fb}: ${base + delta:.0f}")
