# F-9 cache probe: the appended system prefix does join the cached entry, with one flag

**Question answered**: ARCHITECT-ON-PROMPT-SPEC F-9 flagged as load-bearing and
unverified whether content passed via `--append-system-prompt-file` joins the
CLI's cached system block, so that later calls read it at 0.1x instead of
re-writing it at 2x. PROMPT-SPEC section 10 priced its entire caching design on
this. Nobody had run the probe.

**Answer**: yes, but only together with `--exclude-dynamic-system-prompt-sections`.
Without that flag the appended prefix re-bills at the 2x 1h-write rate on every
call and is never read.

**Probe cost**: 11 calls, $0.42 for the original F-9 series below. With the
three addenda (session resume, 3 calls $0.09; P-A opus and fable, 10 calls
$0.66; J-series schema interaction, 4 calls $0.31) the document's full
program is **28 calls, $1.48**. Run 2026-08-26 on CLI 2.1.220, effort `low`,
from /Volumes/Studio/dev/solution-explorer.

## Protocol

Every call mirrors the engine's exact argv (engine.py:209-215) plus the flags
under test, prompt on stdin:

    claude -p --output-format json --tools "" --setting-sources user \
      --effort low --model sonnet \
      [--exclude-dynamic-system-prompt-sections] \
      [--append-system-prompt-file f9-prefix.txt]

The prefix file is 18,579 chars (measured 6,388-6,401 tokens by write deltas) of
deterministic rule text, no timestamps. Calls ran seconds apart, well inside
both TTL windows. Usage fields are read from the CLI JSON envelope.

## Results

| call | flags | user message | cache_write (1h) | cache_read | cost |
|---|---|---|---|---|---|
| A1 | append only | "Reply with exactly: ok" | 12,248 | 3,298 | $0.0751 |
| A2 | append only | same | 12,243 | 3,298 | $0.0751 |
| B1 | neither | same | 5,860 | 3,289 | $0.0368 |
| B2 | neither | same | 5,859 | 3,289 | $0.0368 |
| C1 | exclude + append | same | 15,323 | 0 | $0.0926 |
| C2 | exclude + append | same | 762 | 14,560 | $0.0096 |
| C3 | exclude + append | same | 761 | 14,560 | $0.0096 |
| D1 | exclude only | same | 8,922 | 0 | $0.0542 |
| D2 | exclude only | same | 762 | 8,162 | $0.0077 |
| E1 | exclude + append | "State rule 057 verbatim, then stop." | 767 | 14,560 | $0.0104 |
| E2 | exclude + append | "How many rules mention evidence kind k3? Reply with a number only." | 778 | 14,560 | $0.0115 |

## Findings

1. **Naive append fails.** A2 re-wrote 12,243 tokens instead of reading A1's
   entry. Even two byte-identical plain calls share nothing beyond a 3,289-token
   base block (B1 vs B2): roughly 5,860 tokens of the default system prompt are
   per-call dynamic (cwd, git status, environment), so the prefix diverges
   before any appended content and no cross-call read is possible. This is the
   exact failure mode F-9 predicted, and it is the reality the killed runs were
   billing under.
2. **With `--exclude-dynamic-system-prompt-sections` the mechanism works.** The
   dynamic sections move into the first user message, the remaining system block
   (CLI base plus appended prefix) is byte-stable, and every later call reads it
   at 0.1x: C2 read 14,560 and wrote 762, cutting the identical call's cost from
   $0.0926 to $0.0096, a 90% reduction.
3. **The read attributes to the appended file.** Read with append (14,560) minus
   read without (8,162) is 6,398 tokens, matching the prefix file's measured
   size from the round-1 write deltas (12,248 minus 5,860 is 6,388).
4. **Varying the user tail keeps the hit.** E1 and E2 sent different prompts and
   still read the full 14,560. E1 recited rule 057 from the cached prefix, so
   the appended content is genuinely in the model's context, not just in the
   billing.
5. **The steady-state per-call overhead is about 762-778 tokens of 1h write**:
   the relocated dynamic sections plus the user message envelope. This is the
   floor the ledger predicate should pin for non-warm calls, in place of the
   old expectation that every prompt token is a 2x write.
6. **Writes are 1h TTL** (`ephemeral_1h`, zero in `ephemeral_5m` on every call),
   so all calls of a phase, and in practice an entire run at current wall times,
   sit inside one window. Caches are model-scoped: each tier warms its own.

## Addendum: session resume, the second verified mechanism

Three further calls probed headless continuation (`claude -p --resume
<session_id>`, same engine argv otherwise, no exclude flag needed):

| call | user message | cache_write (1h) | cache_read | cost |
|---|---|---|---|---|
| R1 seed | 18,579-char rule text + "Acknowledge with exactly: ok" | 12,255 | 3,289 | $0.0799 |
| R2 resume | "State rule 019 verbatim, then stop." | 21 | 15,544 | $0.0056 |
| R3 resume | "How many rules mention evidence kind k5? Number only." | 74 | 15,565 | $0.0059 |

The resumed call reads the entire prior context (system prompt plus all prior
turns, 15,544 = R1's 12,255 write plus its 3,289 read) at 0.1x and writes only
its own new message. The session_id is stable across resumes. This is exactly
the interactive-session economics the effort postmortem measured (393M reads at
0.1x over 95 hours), available headlessly. It is serial within a session and
each resume is still a single -p one-shot turn, so the agentic-drift exposure
of a long-lived interactive loop does not apply per call. Candidate fit: the
phases that iterate over one shared corpus (verification, determination
follow-ups), where fresh-call prefix caching would re-write the per-call tail
and re-read the prefix anyway, and where parallelism is already limited.

## Addendum 2: probe P-A, the same mechanism on opus and fable

Ten further calls (IMPLEMENTATION-DELTA-ORCH.md section 1.6), $0.66, same
protocol, engine argv, prompt "Reply with exactly: ok":

| call | write (1h) | read | cost |
|---|---|---|---|
| opus plain 1 / 2 | 3,778 / 3,782 | 0 / 0 | $0.0385 each |
| opus excl+append 1 | 9,934 | 0 | $0.1000 |
| opus excl+append 2 / 3 | 1,396 / 1,400 | 8,532 / 8,532 | $0.0189 each |
| fable plain 1 / 2 | 4,093 / 4,089 | 0 / 0 | $0.0827 each |
| fable excl+append 1 | 10,243 | 0 | $0.2057 |
| fable excl+append 2 / 3 | 1,400 / 1,396 | 8,843 / 8,843 | $0.0376 each |

Findings:

1. **The opus and fable default system prompts never cache at all.** Two
   byte-identical plain calls read zero both times, on both models. This is
   the mechanism behind the v2 ledger's 123 zero-read opus and fable calls:
   every one rewrote its full system prompt at the 2x rate.
2. **With the two flags both models behave exactly like sonnet**: the second
   call reads the stable block at 0.1x and writes only the relocated tail.
   Cost per repeat call falls 81% on opus and 82% on fable.
3. **Predicate constants per model** (V-P4 to V-P6): steady-state non-warm
   write floor about 1,400 tokens (against sonnet's 762 to 778); non-warm
   read floor 8,532 on opus and 8,843 on fable for this 6.4k-token prefix,
   scaling with prefix size.

## Addendum 3: probe J, the --json-schema interaction

The prompt spec left one cache interaction unmeasured: whether passing
`--json-schema` disturbs the cached entry (section 2.5 of the Prompt
implementation delta; flagged again by the cross-session review). Four calls,
$0.31, sonnet, engine argv plus `--max-turns 1`, same prefix file throughout:

| call | flags | cache_write (1h) | cache_read | cost |
|---|---|---|---|---|
| J1 | schema A, cold | 15,806 | 0 | $0.1014 |
| J2 | schema A again | 833 | 14,974 | $0.0146 |
| J3 | schema B (one field added) | 15,825 | 0 | $0.0966 |
| J4 | no schema | 15,326 | 0 | $0.0960 |

Findings:

1. **The schema participates in the cached entry.** An identical schema
   preserves the full 0.1x prefix read (J2). A schema that differs by one
   byte, or the schema's removal, forces the entire stable block back to the
   2x cold-write rate (J3, J4 read zero).
2. **Per-call schemas would therefore have silently destroyed the caching
   win.** The compact schema originally pinned minItems and maxItems to each
   call's exact target count, so no two calls of a rung shared a cacheable
   request. The fix is a byte-constant schema per rung: array bounds sit at
   the rung caps (components 21, relationships 80, escalation 40) and exact
   per-call counts remain with `coverage_issues`, which was always the
   deterministic authority. J2 is the direct proof that the fixed design
   caches.
3. The steady-state tail with schema and `--max-turns 1` is 833 tokens,
   slightly above the flag-free 762 to 778 floor; the audit's non-warm write
   ceiling keeps its margin.

## What this changes

- PROMPT-SPEC section 10's contingency booking
  (`prefix_exposure_if_MP1_gate_fails_usd`) is closed on the favorable side:
  price prefixes at cache-read rates.
- The engine invoker gains two flags and prefix-file plumbing; `warm_first`
  becomes meaningful (first call writes the prefix, the rest read it).
- The ledger predicate for a healthy non-warm call: `cache_read >=` base block
  plus rung prefix, `cache_write <=` relocated-dynamic floor plus that call's
  own user message. A later call whose read falls below the prefix size is a
  cache miss and a defect.
- The dynamic sections now arrive inside the first user message. The probe shows
  behavior is unaffected for single-turn schema calls, but prompt-shape tests
  should pin that the model's answer format survives this relocation on the
  real rung prompts.
