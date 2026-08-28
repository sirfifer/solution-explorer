"""Salvaging a response that the transport damaged or the ceiling cut short.

Every case here is drawn from the 2026-08-25 VS Code run, where 10 of 31
completed rung-2a partitions were paid for and then discarded because the
parser gave up on text that was mostly intact. The corpus lives at
``demos/runs/vscode/2026-08-25/enrichment/failures/``.

The suite asserts both directions. Salvage has to recover what the model
actually wrote, and it has to REFUSE anything that would let a partition be
recorded as answered while storing nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

from analyzer.enrich.engine import _parse_json_object, _repair_truncated, _strip_fences

# The top-level keys a contract partition response must carry. Passed as the
# shape guard everywhere the ladder parses one.
PARTITION_KEYS = ("components", "relationships")

FAILURES = (
    Path(__file__).resolve().parents[1]
    / "demos/runs/vscode/2026-08-25/enrichment/failures"
)


def _payload(components: int = 8, relationships: int = 6) -> dict:
    """A response shaped like a real rung-2a answer."""
    return {
        "components": {
            f"comp-{i}": {
                "help_text": "A component that does a thing. " * 4,
                "description": f"does thing {i}",
                "criticality": "important",
                "contract": {
                    "answers": [
                        {
                            "claim": "what it is",
                            "status": "answered",
                            "evidence": [{"kind": "file", "path": f"src/a{i}.ts"}],
                        }
                    ],
                    "self_state": "grounded",
                },
            }
            for i in range(components)
        },
        "relationships": {
            f"rel-{i}": {"claim": "uses", "status": "answered"}
            for i in range(relationships)
        },
    }


# --- what salvage must recover ------------------------------------------------


def test_a_clean_response_still_parses():
    text = json.dumps(_payload(), indent=2)
    obj = _parse_json_object(text, expect_keys=PARTITION_KEYS)
    assert obj is not None
    assert len(obj["components"]) == 8


def test_a_fenced_response_parses():
    text = "```json\n" + json.dumps(_payload(), indent=2) + "\n```"
    obj = _parse_json_object(text, expect_keys=PARTITION_KEYS)
    assert obj is not None
    assert len(obj["components"]) == 8


def test_complete_response_with_trailing_commas_parses_without_losing_content():
    text = """{
      "verdict": "not-done",
      "criteria": [
        {"criterion_id": "s1", "verdict": "met"},
      ],
      "run_analysis": {"watch_next_run": ["grounding, not prose",],},
    }"""
    obj = _parse_json_object(text, expect_keys=("verdict", "criteria"))
    assert obj == {
        "verdict": "not-done",
        "criteria": [{"criterion_id": "s1", "verdict": "met"}],
        "run_analysis": {"watch_next_run": ["grounding, not prose"]},
    }


def test_trailing_comma_repair_never_changes_commas_inside_strings():
    obj = _parse_json_object(
        '{"reasoning":"keep comma, } and comma, ]",}',
        expect_keys=("reasoning",),
    )
    assert obj == {"reasoning": "keep comma, } and comma, ]"}


def test_a_fence_reopened_mid_object_parses():
    """The continuation defect seen in four sessions of the killed run.

    When a response overflows the ceiling the transport continues it, and the
    continuation often reopens a ```json fence partway through the object it
    was already writing. The fence and its newline both have to go: leaving the
    newline behind is the difference between recovering 10 partitions and 7.
    """
    text = json.dumps(_payload(), indent=2)
    seam = text.index("\n", len(text) // 2)
    damaged = text[:seam] + "\n```json\n" + text[seam:]
    obj = _parse_json_object(damaged, expect_keys=PARTITION_KEYS)
    assert obj is not None, "a mid-object fence must not cost the whole response"
    assert len(obj["components"]) == 8


def test_a_bare_fence_reopened_mid_object_parses():
    text = json.dumps(_payload(), indent=2)
    seam = text.index("\n", len(text) // 2)
    damaged = text[:seam] + "\n```\n" + text[seam:]
    obj = _parse_json_object(damaged, expect_keys=PARTITION_KEYS)
    assert obj is not None
    assert len(obj["components"]) == 8


def test_truncation_keeps_the_blocks_that_finished():
    """A response cut off at the ceiling is a valid object plus a partial one.

    Recovering the finished blocks is the difference between paying for a call
    and getting nothing, which happened ten times in one run.
    """
    text = json.dumps(_payload(), indent=2)
    obj = _parse_json_object(text[: int(len(text) * 0.62)], expect_keys=PARTITION_KEYS)
    assert obj is not None
    recovered = obj.get("components") or {}
    assert 0 < len(recovered) < 8, "expected a partial recovery, not all or nothing"
    # Everything recovered must be exactly what the model wrote, not a stub.
    for block in recovered.values():
        assert block["description"]
        assert block["contract"]["self_state"] == "grounded"


def test_leading_and_trailing_chatter_is_ignored():
    text = "Here is the object you asked for:\n" + json.dumps(_payload()) + "\nDone!"
    obj = _parse_json_object(text, expect_keys=PARTITION_KEYS)
    assert obj is not None
    assert len(obj["components"]) == 8


# --- what salvage must refuse -------------------------------------------------


def test_an_inner_fragment_is_not_a_response():
    """The failure mode that makes unguarded salvage worse than no salvage.

    Text that begins mid-object has its first ``{`` deep inside some nested
    value. Repairing from there produces a valid object that happens to be one
    evidence item. Absorbing it would mark the partition answered and store
    nothing, turning a loud failure into a silent one.
    """
    for fragment in (
        '{"kind": "file", "path": "src/a.ts"}',
        '{"claim": "x", "status": "answered", "evidence": []}',
        '{"parser_first": [], "answers": [], "self_state": "grounded"}',
    ):
        assert _parse_json_object(fragment, expect_keys=PARTITION_KEYS) is None


def test_the_real_discarded_tails_are_refused_not_faked():
    """The ten real discarded responses, asserted honestly.

    `--output-format json` returns only the FINAL turn, so each of these files
    begins mid-string and the earlier turn, where the components were actually
    written, is not in the file at all. No runtime salvage can recover them:
    the information is not present. They are here to prove salvage refuses
    them rather than inventing a hollow success, and the real defence against
    this class is upstream (pinned effort, the ceiling tripwire, and the retry).
    """
    if not FAILURES.is_dir():
        return
    tails = sorted(FAILURES.glob("*.txt"))
    assert tails, "the discarded-response corpus should be committed"
    for path in tails:
        obj = _parse_json_object(path.read_text(), expect_keys=PARTITION_KEYS)
        assert obj is None, f"{path.name} is a mid-object tail and must not 'recover'"


def test_prose_is_not_an_object():
    assert _parse_json_object("I could not do that.", expect_keys=PARTITION_KEYS) is None
    assert _parse_json_object("", expect_keys=PARTITION_KEYS) is None


def test_repair_never_invents_a_value():
    """Salvage only ever CLOSES structures; it never supplies missing content."""
    text = '{"components": {"a": {"description": "half a sen'
    obj = _repair_truncated(text)
    if obj is not None:
        assert "a" not in (obj.get("components") or {}) or obj["components"]["a"] == {}


def test_strip_fences_takes_the_newline_with_the_fence():
    assert _strip_fences("```json\n{}") == "{}"
    assert _strip_fences("```\n{}") == "{}"
    assert _strip_fences('{"a": 1}\n```\n') == '{"a": 1}\n'


# --- literal control characters inside prose ----------------------------------


def test_a_real_newline_inside_a_string_does_not_cost_the_response():
    """Found on the 2026-08-26 full build, at the cost of a whole partition.

    A model writing multi-line prose emits an actual newline inside a
    ``help_text`` rather than the \\n escape. Strict JSON rejects the entire
    document over that one character, so a structurally perfect 114KB response
    carrying 22 components and 40 relationships was discarded, retried, and
    discarded again.

    Structure is still parsed strictly. Only the character class permitted
    inside string VALUES is relaxed, which is the difference between tolerating
    how models write prose and tolerating malformed JSON.
    """
    payload = _payload(components=3, relationships=2)
    text = json.dumps(payload, indent=2)
    # Put a real newline inside a string value, the way a model does.
    damaged = text.replace("A component that does a thing. ", "A component.\nIt does a thing. ", 1)
    obj = _parse_json_object(damaged, expect_keys=PARTITION_KEYS)
    assert obj is not None, "one raw newline must not cost the whole response"
    assert len(obj["components"]) == 3
    assert "\n" in obj["components"]["comp-0"]["help_text"]


def test_a_tab_inside_a_string_is_also_tolerated():
    payload = _payload(components=2, relationships=1)
    text = json.dumps(payload, indent=2)
    damaged = text.replace("does thing 0", "does\tthing 0", 1)
    obj = _parse_json_object(damaged, expect_keys=PARTITION_KEYS)
    assert obj is not None
    assert len(obj["components"]) == 2


def test_relaxing_control_characters_does_not_relax_structure():
    """The tolerance must not extend to genuinely broken JSON."""
    for broken in (
        '{"components": {"a": {,}}, "relationships": {}}',
        '{"components": [1,2,, "relationships": {}}',
        '{"components": {"a": undefined}, "relationships": {}}',
    ):
        assert _parse_json_object(broken, expect_keys=PARTITION_KEYS) is None
