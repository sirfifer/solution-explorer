#!/usr/bin/env python3
"""What one run costs, measured in the thing that is actually scarce.

The dollar figures the `claude` CLI reports are API-EQUIVALENT prices for work
that was metered against a Claude Max subscription. No card is charged. That
makes them useful for comparing one run against another and useless for the
question that actually governs the week:

    if I regenerate VS Code and Kubernetes four times, have I spent Tuesday or
    have I spent the whole week?

A Max subscription is not a dollar balance, it is an allowance that refills
weekly. So this tool converts a run's measured token usage into a share of that
allowance, and reports the answer as a percentage of the week and as a number of
runs that fit inside it.

WHAT IS MEASURED AND WHAT IS ASSUMED
------------------------------------
Measured, per run, from the enrichment report: tokens by model, split into fresh
input, output, cache reads and cache writes, plus the call count. Those come from
the CLI's own usage envelope and are facts.

Assumed, exactly once, in WEEKLY_ALLOWANCE: how much a week of the subscription
is worth in the same API-equivalent units. This is the only guess in the file and
it is isolated on purpose, because it is the number that must be calibrated
against observation rather than reasoned about. `--calibrate` sets it from a real
measurement, and until it has been calibrated every report says so out loud.

Weighting between models is NOT a guess. Anthropic publishes per-model token
prices and they differ by an order of magnitude across the ladder's rungs, so an
hour of Fable and an hour of Haiku are not remotely the same amount of allowance.
Those rates are in MODEL_RATES and the arithmetic from tokens to
API-equivalent dollars is exact.

WHY NOT "HOURS"
---------------
Hours are the unit people think in, and they are the wrong unit to store, because
an hour of a cheap model and an hour of an expensive one differ by 10x. This
reports hours as a DERIVED convenience, from a measured tokens-per-hour rate, and
keeps tokens as the number of record. When the two disagree, believe the tokens.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "demos" / "usage-calibration.json"

# Published per-million-token rates, 2026-06. Input and output differ by 5x on
# every model, so a run that reads a lot and writes a little is nothing like one
# that does the reverse, and a single blended rate would hide that.
#
# Cache reads are ~0.1x input and cache writes ~1.25x input. Those two multipliers
# matter more here than anywhere else: the enrichment ladder sends a large stable
# prefix to every partition, so a well-cached run and a badly-cached one can
# differ several-fold on identical work.
MODEL_RATES = {
    # key           input $/1M   output $/1M
    "fable":        (10.00,      50.00),
    "opus":         (5.00,       25.00),
    "sonnet":       (3.00,       15.00),
    "haiku":        (1.00,       5.00),
}
CACHE_READ_MULTIPLIER = 0.10
CACHE_WRITE_MULTIPLIER = 1.25

# The one assumption. Until `--calibrate` has run against a real observation this
# is a placeholder, and every report built on it is labelled UNCALIBRATED.
#
# Seeded from the only anchor available without guessing at Anthropic's internal
# limits: a Max 20x subscription is $200/month, and subscription plans are worth
# materially more in API-equivalent terms than their sticker price or nobody
# would buy them. 10x is a deliberately round, deliberately unverified stand-in.
# Do not reason from it. Replace it with a measurement.
DEFAULT_WEEKLY_ALLOWANCE_USD = 460.0
DEFAULT_CALIBRATED = False

# For the derived "hours" figure only. Measured from this project's own runs: a
# sustained enrichment partition moves roughly this many tokens per wall hour per
# worker. Wrong by a factor of two is fine here, because hours are the sanity
# check and tokens are the answer.
TOKENS_PER_HOUR_SUSTAINED = 2_000_000


# Claude View, the local usage service the ecosystem project runs on this
# machine. It indexes the session transcripts under ~/.claude/projects and
# reports what the account has actually consumed, which is the one thing this
# tool cannot derive from a run's own report.
#
# It matters because headless `claude -p` invocations, which is how the
# enrichment ladder calls models, write session transcripts exactly like
# interactive ones. So the ladder's own consumption lands here automatically and
# the weekly denominator needs no one to remember to read a number off a screen.
CLAUDE_VIEW_URL = "http://127.0.0.1:47892"
ECOSYSTEM_OPS_URL = "http://127.0.0.1:8787"


def account_week(timeout: float = 8.0) -> Optional[dict]:
    """What the account has spent this week, or None if the service is not up.

    Never fatal. A missing usage service costs this tool its denominator, not
    its numbers: the per-model account of a run is measured from the run itself
    and stands on its own.
    """
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(
            f"{ECOSYSTEM_OPS_URL}/api/claudeview", timeout=timeout
        ) as resp:
            doc = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError):
        return None
    summary = ((doc.get("service") or {}).get("summary")) or {}
    week = summary.get("week") or {}
    if not week:
        return None
    return {
        "sessions": week.get("sessions"),
        "cost_usd": week.get("cost"),
        "cost_basis": summary.get("cost_basis"),
        "collected_at": (doc.get("service") or {}).get("collected_at"),
    }


def _load_config() -> dict:
    if CONFIG_PATH.is_file():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {
        "weekly_allowance_api_equivalent_usd": DEFAULT_WEEKLY_ALLOWANCE_USD,
        "calibrated": DEFAULT_CALIBRATED,
        "basis": "placeholder; run --calibrate against a real observation",
    }


def _save_config(doc: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def rate_for(model: str) -> Optional[tuple]:
    """Match a binding like 'anthropic-claude-cli:sonnet' to published rates.

    Matched by substring rather than exact name because the binding string, the
    CLI's reported model id and the marketing name are three different things
    that all mean the same rung.
    """
    lowered = (model or "").lower()
    for key, rates in MODEL_RATES.items():
        if key in lowered:
            return rates
    return None


def api_equivalent_usd(usage_by_model: dict) -> tuple[float, list[dict], list[str]]:
    """Price a run's tokens at published rates. Returns (total, rows, unknowns)."""
    rows: list[dict] = []
    unknown: list[str] = []
    total = 0.0
    for model, bucket in sorted((usage_by_model or {}).items()):
        rates = rate_for(model)
        fresh_in = bucket.get("input_tokens", 0)
        out = bucket.get("output_tokens", 0)
        cache_read = bucket.get("cache_read_input_tokens", 0)
        cache_write = bucket.get("cache_creation_input_tokens", 0)
        if rates is None:
            unknown.append(model)
            # Fall back to what the CLI itself reported for this model, so an
            # unrecognised binding still contributes its cost instead of silently
            # counting as free.
            priced = float(bucket.get("cost_usd", 0.0) or 0.0)
        else:
            in_rate, out_rate = rates
            priced = (
                fresh_in / 1e6 * in_rate
                + cache_read / 1e6 * in_rate * CACHE_READ_MULTIPLIER
                + cache_write / 1e6 * in_rate * CACHE_WRITE_MULTIPLIER
                + out / 1e6 * out_rate
            )
        total += priced
        rows.append({
            "model": model,
            "calls": bucket.get("calls", 0),
            "input_tokens": fresh_in,
            "output_tokens": out,
            "cache_read_input_tokens": cache_read,
            "cache_creation_input_tokens": cache_write,
            "api_equivalent_usd": round(priced, 4),
            "priced_from": "published rates" if rates else "CLI-reported cost (unrecognised model)",
        })
    return total, rows, unknown


def _read_usage(report_path: Path) -> tuple[dict, float]:
    """Pull the per-model account out of an enrichment report."""
    doc = json.loads(report_path.read_text(encoding="utf-8"))

    # The Run Report's accounting section is the canonical account: one row per
    # model, measured from the ledger rather than estimated.
    acct = doc.get("accounting") or {}
    if acct.get("by_model"):
        usage = {}
        for bucket in acct["by_model"]:
            usage[bucket["model"]] = {
                "calls": bucket.get("invocations", 0),
                "input_tokens": bucket.get("tokens_in", 0),
                "output_tokens": bucket.get("tokens_out", 0),
                "cache_read_input_tokens": bucket.get("tokens_cached", 0),
                "cache_creation_input_tokens": 0,
                "cost_usd": bucket.get("cost_usd", 0.0),
            }
        return usage, float((acct.get("totals") or {}).get("cost_usd", 0.0) or 0.0)

    usage = doc.get("usage_by_model")
    if isinstance(usage, dict) and usage:
        return usage, float(doc.get("total_cost_usd", 0.0) or 0.0)
    # Older reports predate per-model accounting and carry only the ledger.
    usage = {}
    for entry in doc.get("ledger") or []:
        model = entry.get("model") or "unknown"
        bucket = usage.setdefault(model, {"calls": 0, "cost_usd": 0.0})
        bucket["calls"] += 1
        bucket["cost_usd"] += float(entry.get("cost_usd", 0.0) or 0.0)
    return usage, float(doc.get("total_cost_usd", 0.0) or 0.0)


def cmd_report(args: argparse.Namespace) -> int:
    cfg = _load_config()
    allowance = float(cfg["weekly_allowance_api_equivalent_usd"])
    calibrated = bool(cfg.get("calibrated"))

    path = Path(args.report).expanduser().resolve()
    if not path.is_file():
        print(f"error: no such report: {path}", file=sys.stderr)
        return 2
    usage, reported_cost = _read_usage(path)
    if not usage:
        print("This report carries no usage account. Either it is a dry run, or it")
        print("predates per-model token accounting (analyzer/enrich/engine.py).")
        return 1

    total, rows, unknown = api_equivalent_usd(usage)
    share = total / allowance if allowance else 0.0
    tokens = sum(
        r["input_tokens"] + r["output_tokens"]
        + r["cache_read_input_tokens"] + r["cache_creation_input_tokens"]
        for r in rows
    )

    print(f"Run: {path}")
    print()
    print(f"{'model':<34}{'calls':>7}{'in':>12}{'out':>10}{'cached':>12}{'api-equiv':>12}")
    for r in rows:
        print(
            f"{r['model'][:33]:<34}{r['calls']:>7}{r['input_tokens']:>12,}"
            f"{r['output_tokens']:>10,}"
            f"{r['cache_read_input_tokens'] + r['cache_creation_input_tokens']:>12,}"
            f"{'$' + format(r['api_equivalent_usd'], '.2f'):>12}"
        )
    print(f"{'':<34}{'':>7}{'':>12}{'':>10}{'total':>12}{'$' + format(total, '.2f'):>12}")
    print()
    print(f"tokens moved         {tokens:,}")
    print(f"api-equivalent       ${total:.2f}"
          + (f"   (CLI reported ${reported_cost:.2f})" if reported_cost else ""))

    # Two independent numbers for the same run: one modelled from the published
    # rate table, one reported by the CLI that actually did the metering. They
    # should agree. When they stop agreeing, the rate table has gone stale, and
    # that is worth saying out loud rather than discovering months later through
    # a forecast that was quietly wrong the whole time. Pricing changes; a tool
    # that assumes it does not is a tool that lies with increasing confidence.
    if reported_cost > 0 and total > 0:
        drift = abs(total - reported_cost) / reported_cost
        if drift > 0.20:
            higher = "above" if total > reported_cost else "below"
            print()
            print(f"  ! modelled price is {drift:.0%} {higher} what the CLI reported.")
            print("    MODEL_RATES in this file may be out of date, or this run used a")
            print("    rung whose binding does not match its rate key. Trust the CLI")
            print("    figure and reconcile the table.")
    print(f"sustained-hours      {tokens / TOKENS_PER_HOUR_SUSTAINED:.1f}h  (derived, see module docstring)")
    print()
    print(f"share of one week    {share * 100:.1f}%")
    if share > 0:
        print(f"runs per week        {1 / share:.1f}")
    print(f"weekly allowance     ${allowance:.2f} api-equivalent"
          f"  [{'calibrated' if calibrated else 'UNCALIBRATED PLACEHOLDER'}]")

    observed = account_week()
    if observed and observed.get("cost_usd") is not None:
        spent = float(observed["cost_usd"])
        print()
        print(f"account this week    ${spent:.2f} across "
              f"{observed.get('sessions', '?')} session(s)"
              f"   [{observed.get('cost_basis', 'unknown basis')}]")
        if allowance:
            print(f"                     {spent / allowance * 100:.0f}% of the "
                  f"allowance above, everything included")
        # Free calibration, and the honest kind. If the account has already spent
        # more than the assumed allowance and is still working, the assumption is
        # provably too low: an allowance is at minimum whatever has been spent
        # against it without exhausting it. This raises a floor from observation
        # every time the tool runs, so the placeholder converges toward the truth
        # without anyone remembering to do anything.
        if not calibrated and spent > allowance:
            cfg["weekly_allowance_api_equivalent_usd"] = round(spent, 2)
            cfg["basis"] = (
                f"floor observed {observed.get('collected_at') or 'recently'}: "
                f"${spent:.2f} was spent this week without exhausting the "
                f"allowance, so the allowance is at least that. Still a floor, "
                f"not a measurement."
            )
            _save_config(cfg)
            print()
            print(f"  ^ raised the working figure to ${spent:.2f}. That much has been")
            print("    spent this week WITHOUT hitting a limit, so the allowance is at")
            print("    least that. It is still a floor: the real ceiling is higher by")
            print("    an unknown amount until a run measures it.")
        if total > 0:
            print(f"this run would be    {total / max(spent, 1e-9) * 100:.1f}% "
                  f"of what the account has already spent this week")
    else:
        print()
        print("account this week    Claude View not reachable; the per-run numbers")
        print("                     above stand on their own, only the denominator is missing")
    if not calibrated:
        print()
        print("The percentage above is arithmetic on an assumption, not a measurement.")
        print("Calibrate it the next time you hit a weekly limit:")
        print("    python3 scripts/usage-budget.py calibrate --spent-usd <api-equiv spent that week>")
    if unknown:
        print()
        print(f"note: no published rate matched {', '.join(unknown)}; "
              f"priced from the CLI's own figure instead")
    return 0


def cmd_calibrate(args: argparse.Namespace) -> int:
    """Replace the assumption with an observation.

    The honest calibration is the moment a weekly limit is actually reached: at
    that instant the API-equivalent total spent since the reset IS the week's
    allowance, in exactly the units everything else here is measured in.
    """
    cfg = _load_config()
    cfg["weekly_allowance_api_equivalent_usd"] = float(args.spent_usd)
    cfg["calibrated"] = True
    cfg["basis"] = args.basis or (
        "observed: this much api-equivalent usage exhausted one weekly allowance"
    )
    if args.plan:
        cfg["plan"] = args.plan
    _save_config(cfg)
    print(f"weekly allowance set to ${float(args.spent_usd):.2f} api-equivalent")
    print(f"written to {CONFIG_PATH}")
    return 0


def cmd_measure(args: argparse.Namespace) -> int:
    """Calibrate from an isolated run: two /usage readings and the run between them.

    This is the only hard measurement available. Claude Code exposes subscription
    usage through /usage and /status in a live session and nowhere else: there is
    no CLI subcommand and no endpoint for it, and the open feature requests for
    one are still open. So the allowance cannot be looked up, only observed.

    The observation is only valid if the account was idle apart from the run.
    Anything else running in parallel lands in the same bucket and inflates the
    delta, which would make every later forecast quietly optimistic.

    On Max plans Sonnet and Opus draw from separate weekly buckets, so both are
    calibrated separately when the Opus readings are supplied. A single blended
    number would be wrong in the direction that matters: an Opus-heavy run can
    exhaust its own bucket while the all-models bar still looks comfortable.
    """
    path = Path(args.report).expanduser().resolve()
    if not path.is_file():
        print(f"error: no such report: {path}", file=sys.stderr)
        return 2
    usage, _ = _read_usage(path)
    if not usage:
        print("error: that report carries no usage account", file=sys.stderr)
        return 2

    total, rows, _ = api_equivalent_usd(usage)
    delta_all = args.after_all - args.before_all
    if delta_all <= 0:
        print("error: the all-models reading did not increase; either the run was "
              "too small to register or the readings are the wrong way round",
              file=sys.stderr)
        return 2

    cfg = _load_config()
    weekly_all = total / (delta_all / 100.0)
    cfg["weekly_allowance_api_equivalent_usd"] = round(weekly_all, 2)
    cfg["calibrated"] = True
    cfg["basis"] = (
        f"measured on an isolated run: {total:.2f} api-equivalent moved the "
        f"all-models weekly bar {args.before_all:.1f}% -> {args.after_all:.1f}% "
        f"({delta_all:.1f}% of the week)"
    )
    if args.plan:
        cfg["plan"] = args.plan

    print(f"run consumed          ${total:.2f} api-equivalent")
    print(f"all-models bar        {args.before_all:.1f}% -> {args.after_all:.1f}%  "
          f"(+{delta_all:.1f}% of the week)")
    print(f"=> weekly allowance   ${weekly_all:.2f} api-equivalent")
    print(f"=> runs per week      {100.0 / delta_all:.1f}")

    if args.before_opus is not None and args.after_opus is not None:
        delta_opus = args.after_opus - args.before_opus
        opus_cost = sum(
            r["api_equivalent_usd"] for r in rows if "opus" in r["model"].lower()
        )
        print()
        if delta_opus > 0 and opus_cost > 0:
            weekly_opus = opus_cost / (delta_opus / 100.0)
            cfg["weekly_opus_allowance_api_equivalent_usd"] = round(weekly_opus, 2)
            print(f"opus work in this run ${opus_cost:.2f} api-equivalent")
            print(f"opus bar              {args.before_opus:.1f}% -> {args.after_opus:.1f}%  "
                  f"(+{delta_opus:.1f}% of the opus week)")
            print(f"=> opus allowance     ${weekly_opus:.2f} api-equivalent")
            print(f"=> opus-bound runs    {100.0 / delta_opus:.1f} per week")
            binding = "opus" if delta_opus > delta_all else "all-models"
            print()
            print(f"The {binding} bucket is what limits this run's cadence.")
        else:
            print("opus bucket: no measurable movement, so nothing calibrated for it")

    _save_config(cfg)
    print()
    print(f"written to {CONFIG_PATH}")
    return 0


def cmd_forecast(args: argparse.Namespace) -> int:
    """Answer the pacing question before spending anything.

    Takes a per-run cost and a plan, and says whether the plan fits in a week.
    """
    cfg = _load_config()
    allowance = float(cfg["weekly_allowance_api_equivalent_usd"])
    per_run = float(args.per_run_usd)
    runs = args.runs
    total = per_run * runs
    share = total / allowance if allowance else 0.0
    print(f"{runs} run(s) at ${per_run:.2f} api-equivalent = ${total:.2f}")
    print(f"share of one week    {share * 100:.1f}%"
          + ("   OVER BUDGET" if share > 1 else ""))
    print(f"weekly allowance     ${allowance:.2f}"
          f"  [{'calibrated' if cfg.get('calibrated') else 'UNCALIBRATED PLACEHOLDER'}]")
    if share > 0:
        print(f"headroom             {max(0.0, (1 - share)) * 100:.1f}% of the week left")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_report = sub.add_parser("report", help="what one finished run consumed")
    p_report.add_argument("report", help="path to an enrichment report.json")
    p_report.set_defaults(func=cmd_report)

    p_cal = sub.add_parser("calibrate", help="set the weekly allowance from an observation")
    p_cal.add_argument("--spent-usd", required=True, type=float,
                       help="api-equivalent usage that exhausted one week")
    p_cal.add_argument("--plan", default=None, help="e.g. 'Max 20x'")
    p_cal.add_argument("--basis", default=None, help="how this was observed")
    p_cal.set_defaults(func=cmd_calibrate)

    p_m = sub.add_parser(
        "measure",
        help="calibrate from an isolated run plus two /usage readings",
    )
    p_m.add_argument("--report", required=True, help="the run's report.json")
    p_m.add_argument("--before-all", required=True, type=float,
                     help="all-models weekly %% from /usage BEFORE the run")
    p_m.add_argument("--after-all", required=True, type=float,
                     help="all-models weekly %% from /usage AFTER the run")
    p_m.add_argument("--before-opus", type=float, default=None,
                     help="opus weekly %% before, if your plan shows one")
    p_m.add_argument("--after-opus", type=float, default=None)
    p_m.add_argument("--plan", default=None, help="e.g. 'Max 20x'")
    p_m.set_defaults(func=cmd_measure)

    p_fc = sub.add_parser("forecast", help="does this plan fit in a week")
    p_fc.add_argument("--per-run-usd", required=True, type=float)
    p_fc.add_argument("--runs", required=True, type=int)
    p_fc.set_defaults(func=cmd_forecast)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
