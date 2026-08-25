"""PROMPT-SPEC section 9 cost model, revision 2 (Phase 2 step 2).

Reproduces data/prompt-aligned-cost-model.json. Constants revised per the QA
adjudication (data/qa-adjudication.json) and the Architect's review findings
F-1 to F-9:

- Per-call fixed prompt-side overhead: 12,546 tokens (adjudicated char-side
  fit intercept; band 10,000 to 12,500; mostly cache read after warm).
- Per-call fixed OUTPUT at low effort: 1,369 tokens central, bounds 500 to
  2,800 (adjudicated; subsumes thinking and JSON envelope, resolving F-3).
- Marginal input tokens: measured o200k x 1.5829 totals from
  prompt-measure-projection.py (QA P-1 confirmed the method; the char-side
  equivalent is chars / 2.886).
- Opus is DUAL-PRICED at $5/$25 and $15/$75 per F-1; no artifact carries an
  Opus cost and the first pilot Opus ledger row arbitrates. Sonnet $3/$15 and
  Fable $10/$50 are ledger-fit (1.6% and 1.8% residuals).
- 2a-C capped at 21 components per call (61 calls) so the worst call passes
  the binding dispersion rule: predicted mean x 1.90 <= 0.85 x 64,000.
- 2b booked at BATCH 5, the agreed default pending M-2 parity (QA final
  verdict E-3); batch 15 is the labeled contingency.
- The conservative column varies all four rungs (F-7), not only 2a.
- The prefix cache-read pricing is CONTINGENT on the M-P1 append-file gate
  (F-9 / E-4); the exposure block prices the fallback (prefix at the 2x
  write rate every call) per scenario.
- 2a-C input reflects the R-10 fact byte budget (20k scaled per component);
  2a-R input adds ~1k/call for fresh 2a-C descriptions (estimate, M-5).

Token unit throughout: billed-equivalent scaled tokens (o200k x 1.5829).
"""
import json
import math
from pathlib import Path

S_OVERHEAD = 12546            # per-call prompt-side fixed overhead (adjudicated)
P2AC, P2AR, P2B, P2C = 4364, 2808, 3072, 2745   # measured prefix sizes w/ brief

# prices per token: (input 1x, 1h cache write 2x, cache read 0.1x, output)
SONNET = (3e-6, 6e-6, 0.3e-6, 15e-6)            # ledger-fit, 1.6%
OPUS_LO = (5e-6, 10e-6, 0.5e-6, 25e-6)          # current sheet; NO artifact
OPUS_HI = (15e-6, 30e-6, 1.5e-6, 75e-6)         # legacy sheet; NO artifact
FABLE = (10e-6, 20e-6, 1.0e-6, 50e-6)           # ledger-fit, 1.8%

N_COMP, N_REL = 569, 5453
FIX_OUT = {"central": 1369, "conservative": 2800}
ENTRY = 20                    # array "i"/"k" per-entry overhead (estimate)

# per-block delivered output, new schema (measured; see PROMPT-SPEC section 9)
BLOCK = {"central": (880, 124), "conservative": (1263, 153)}

# 2a inputs (measured totals, scaled)
IN_2AC = 430_000              # 574,437 uncapped - 196,579 byte budget + 51,852 edges
IN_2AR = {"central": 1_752_000, "conservative": 1_852_000}  # 1,652k measured + fresh descriptions estimate (+/-)

CALLS_2AC, CALLS_2AR = 61, 100          # cap 21 (dispersion rule), batch 80

# 2b population (efficiency postmortem recompute): 285 comp + 654 rel = 939
NB_C, NB_R = 285, 654
BATCH_2B = 5                             # the agreed default (E-3); 15 is the M-2 contingency
# per-item input: facts + established/attempt + failed(with citations_tried) + overhead
ITEM_2B = {"central": (2250, 530), "conservative": (3550, 830)}
# per-item repair output (repairs x failed-per-item + wrapper)
OUT_2B = {"central": (105, 75), "conservative": (180, 140)}

# 2c entry fraction: 20% central, 30% conservative; batch 5; carries two attempts
FRAC_2C = {"central": 0.20, "conservative": 0.30}
ITEM_2C = {"central": (3000, 620), "conservative": (4300, 950)}
OUT_2C = {"central": (130, 95), "conservative": (220, 160)}


def rung(calls, creation, out, prefix, rates):
    inr, wr, rr, outr = rates
    read = calls * (S_OVERHEAD + prefix)
    return {
        "calls": calls,
        "creation": round(creation),
        "read": round(read),
        "output": round(out),
        "usd": round(creation * wr + out * outr + read * rr, 2),
    }


def ladder(variant, opus, batch_2b=BATCH_2B):
    fx = FIX_OUT[variant]
    cb, rb = BLOCK[variant]
    out_2ac = N_COMP * (cb + ENTRY) + CALLS_2AC * fx
    out_2ar = N_REL * (rb + ENTRY) + CALLS_2AR * fx
    r_2ac = rung(CALLS_2AC, IN_2AC, out_2ac, P2AC, SONNET)
    r_2ar = rung(CALLS_2AR, IN_2AR[variant], out_2ar, P2AR, SONNET)

    calls_2b = math.ceil(NB_C / batch_2b) + math.ceil(NB_R / batch_2b)
    ic, ir = ITEM_2B[variant]
    oc, orr = OUT_2B[variant]
    in_2b = NB_C * ic + NB_R * ir
    out_2b = NB_C * oc + NB_R * orr + calls_2b * fx
    r_2b = rung(calls_2b, in_2b, out_2b, P2B, opus)

    nc, nr = round(NB_C * FRAC_2C[variant]), round(NB_R * FRAC_2C[variant])
    calls_2c = math.ceil(nc / 5) + math.ceil(nr / 5)
    ic, ir = ITEM_2C[variant]
    oc, orr = OUT_2C[variant]
    in_2c = nc * ic + nr * ir
    out_2c = nc * oc + nr * orr + calls_2c * fx
    r_2c = rung(calls_2c, in_2c, out_2c, P2C, FABLE)

    total = round(r_2ac["usd"] + r_2ar["usd"] + r_2b["usd"] + r_2c["usd"], 2)
    return {"2a_c": r_2ac, "2a_r": r_2ar, "2b": r_2b, "2c": r_2c, "ladder_usd": total}


CEILING, DISP, BOUND = 64000, 1.90, 0.85
worst_2ac_mean = 21 * (BLOCK["conservative"][0] + ENTRY) + FIX_OUT["central"]
worst_2ar_mean = 80 * (BLOCK["conservative"][1] + ENTRY) + FIX_OUT["central"]

def prefix_exposure(batch_2b, opus):
    """E-4 fallback: the appended prefix bills at 2x per call instead of 0.1x."""
    calls_2b = math.ceil(NB_C / batch_2b) + math.ceil(NB_R / batch_2b)
    parts = [
        CALLS_2AC * P2AC * 1.9 * SONNET[0],
        CALLS_2AR * P2AR * 1.9 * SONNET[0],
        calls_2b * P2B * 1.9 * opus[0],
        39 * P2C * 1.9 * FABLE[0],
    ]
    return round(sum(parts), 2)


result = {
    "basis": "2b at batch 5 (agreed default, E-3); batch 15 below as contingency",
    "central_opus_5_25": ladder("central", OPUS_LO),
    "central_opus_15_75": ladder("central", OPUS_HI),
    "conservative_opus_5_25": ladder("conservative", OPUS_LO),
    "conservative_opus_15_75": ladder("conservative", OPUS_HI),
    "contingency_batch15_ladder_usd": {
        "central_opus_5_25": ladder("central", OPUS_LO, 15)["ladder_usd"],
        "central_opus_15_75": ladder("central", OPUS_HI, 15)["ladder_usd"],
        "conservative_opus_5_25": ladder("conservative", OPUS_LO, 15)["ladder_usd"],
        "conservative_opus_15_75": ladder("conservative", OPUS_HI, 15)["ladder_usd"],
    },
    "prefix_exposure_if_MP1_gate_fails_usd": {
        "batch5_opus_5_25": prefix_exposure(5, OPUS_LO),
        "batch5_opus_15_75": prefix_exposure(5, OPUS_HI),
        "batch15_opus_5_25": prefix_exposure(15, OPUS_LO),
        "batch15_opus_15_75": prefix_exposure(15, OPUS_HI),
    },
    "dispersion_rule": {
        "rule": "worst-call predicted mean x 1.90 <= 0.85 x 64,000 (binding until Level 1 recalibrates dispersion_max(low))",
        "2a_c_cap": 21,
        "2a_c_worst_mean": worst_2ac_mean,
        "2a_c_worst_dispersed": round(worst_2ac_mean * DISP),
        "2a_c_share_of_ceiling": round(worst_2ac_mean * DISP / CEILING, 4),
        "2a_c_fixed_limit_for_cap21": int(CEILING * BOUND / DISP - 21 * (BLOCK["conservative"][0] + ENTRY)),
        "2a_c_cap_if_fixed_at_2800": 20,
        "2a_r_worst_mean": worst_2ar_mean,
        "2a_r_share_of_ceiling": round(worst_2ar_mean * DISP / CEILING, 4),
    },
    "batch5_vs_15_delta_usd_at_5_25": round(
        ladder("central", OPUS_LO, 5)["ladder_usd"]
        - ladder("central", OPUS_LO, 15)["ladder_usd"], 2),
}
json.dump(result, open(Path(__file__).parent / "prompt-aligned-cost-model.json", "w"), indent=1)
print(json.dumps(result, indent=1))
