"""The Comprehension Review scoring tool (docs/quality/COMPREHENSION-REVIEW.md).

The review used to produce a letter grade, which is not comparable and cannot
distinguish the product improving from the subject being easier. These tests
pin the rules that make the numbers mean something rather than the arithmetic,
which is trivial.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "comprehension-score.py"


def _load():
    spec = importlib.util.spec_from_file_location("comprehension_score", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cs = _load()


def card(persona="P1", score=3, subject="unamentis", version="comprehension-review/v1",
         trust=0, blocked=0, verdicts=None):
    verdicts = verdicts or ["correct"] * 5
    return {
        "charter_version": version,
        "subject": subject,
        "run_date": "2026-08-18",
        "persona": persona,
        "dimensions": {
            d: {"score": score, "evidence": "12-detail-panel.png"}
            for d in cs.DIMENSIONS
        },
        "battery": [
            {"question": i + 1, "verdict": v, "confidence": "high", "source": "Docs tab"}
            for i, v in enumerate(verdicts)
        ],
        "trust_incidents": [
            {"what": f"claimed thing {i}", "severity": "high" if i == 0 else "low"}
            for i in range(trust)
        ],
        "blocked_paths": [{"feature": f"gesture {i}"} for i in range(blocked)],
    }


def write_run(tmp_path, cards, profile=True):
    run = tmp_path
    run.mkdir(parents=True, exist_ok=True)
    for c in cards:
        (run / f"{c['persona']}.json").write_text(json.dumps(c), encoding="utf-8")
    if profile:
        (run / "PROFILE.json").write_text(json.dumps({"files": 100, "lines": 1000}), encoding="utf-8")
    return run


# ---------------------------------------------------------------------------
# What a score is, and is not
# ---------------------------------------------------------------------------

def test_a_run_is_the_set_of_persona_scores_never_an_average(tmp_path, capsys):
    run = write_run(tmp_path / "r", [card("P1", 4), card("P2", 1), card("P3", 3)])
    assert cs.main(["score", str(run)]) == 0
    out = capsys.readouterr().out
    assert "24/24" in out and "6/24" in out and "18/24" in out
    # The mean would be 16/24 and would hide P2 entirely.
    assert "16/24" not in out
    assert "average" in out.lower(), "the report must say why it is not averaged"


def test_a_score_without_evidence_is_refused(tmp_path):
    bad = card()
    bad["dimensions"]["trust"]["evidence"] = "   "
    run = write_run(tmp_path / "r", [bad])
    assert cs.main(["score", str(run)]) == 2, "a score with no evidence is an opinion"


def test_an_incomplete_run_is_reported_and_fails(tmp_path, capsys):
    run = write_run(tmp_path / "r", [card("P1"), card("P2")])
    assert cs.main(["score", str(run)]) == 1
    out = capsys.readouterr().out
    assert "INCOMPLETE RUN" in out and "P3" in out


def test_a_run_without_a_difficulty_profile_says_it_cannot_be_compared(tmp_path, capsys):
    run = write_run(tmp_path / "r", [card("P1"), card("P2"), card("P3")], profile=False)
    cs.main(["score", str(run)])
    assert "NO PROFILE.json" in capsys.readouterr().out


def test_trust_incidents_are_counted_not_scored_away(tmp_path, capsys):
    # A run can score perfectly and still have shipped a lie; the report has to
    # show that rather than let the score absorb it.
    run = write_run(tmp_path / "r", [card("P1", 4, trust=3), card("P2", 4), card("P3", 4)])
    cs.main(["score", str(run)])
    out = capsys.readouterr().out
    assert "24/24" in out
    assert "3 (1 high)" in out


# ---------------------------------------------------------------------------
# The comparability rules
# ---------------------------------------------------------------------------

def test_comparing_across_charter_versions_is_refused(tmp_path, capsys):
    old = write_run(tmp_path / "old", [card("P1", 3, version="comprehension-review/v1")])
    new = write_run(tmp_path / "new", [card("P1", 3, version="comprehension-review/v2")])
    assert cs.main(["compare", str(new), str(old)]) == 1
    out = capsys.readouterr().out
    assert "REFUSED" in out and "offset" in out


def test_comparing_different_subjects_is_allowed_but_flagged(tmp_path, capsys):
    a = write_run(tmp_path / "a", [card("P1", 3, subject="unamentis")])
    b = write_run(tmp_path / "b", [card("P1", 2, subject="large-repository-validation")])
    assert cs.main(["compare", str(b), str(a)]) == 1
    out = capsys.readouterr().out
    assert "DIFFERENT SUBJECTS" in out
    assert "harder" in out


def test_a_same_subject_comparison_names_the_regressed_dimensions(tmp_path, capsys):
    before = card("P1", 4)
    after = card("P1", 4)
    after["dimensions"]["trust"]["score"] = 1
    a = write_run(tmp_path / "a", [before])
    b = write_run(tmp_path / "b", [after])
    assert cs.main(["compare", str(b), str(a)]) == 0
    out = capsys.readouterr().out
    assert "REGRESSED: trust" in out
    assert "24/24 -> 21/24" in out and "(-3)" in out


def test_an_improvement_reads_as_an_improvement(tmp_path, capsys):
    a = write_run(tmp_path / "a", [card("P1", 2)])
    b = write_run(tmp_path / "b", [card("P1", 3)])
    assert cs.main(["compare", str(b), str(a)]) == 0
    out = capsys.readouterr().out
    assert "12/24 -> 18/24" in out and "(+6)" in out
    assert "REGRESSED" not in out


# ---------------------------------------------------------------------------
# Structural guards
# ---------------------------------------------------------------------------

def test_a_run_may_not_mix_charter_versions_or_subjects(tmp_path):
    run = write_run(tmp_path / "r", [
        card("P1", version="comprehension-review/v1"),
        card("P2", version="comprehension-review/v2"),
    ])
    assert cs.main(["score", str(run)]) == 2
    run2 = write_run(tmp_path / "r2", [card("P1", subject="a"), card("P2", subject="b")])
    assert cs.main(["score", str(run2)]) == 2


@pytest.mark.parametrize("dim", cs.DIMENSIONS)
def test_every_rubric_dimension_is_required(tmp_path, dim):
    bad = card()
    del bad["dimensions"][dim]
    run = write_run(tmp_path / f"r-{dim}", [bad])
    assert cs.main(["score", str(run)]) == 2


def test_the_battery_is_five_questions(tmp_path):
    bad = card(verdicts=["correct"] * 4)
    run = write_run(tmp_path / "r", [bad])
    assert cs.main(["score", str(run)]) == 2


def test_the_rubric_matches_the_charter_and_the_schema():
    """The dimensions live in three places: the charter table, the schema, and
    the tool. This is the guard against them drifting apart."""
    schema = json.loads((REPO_ROOT / "docs" / "quality" / "scorecard.schema.json").read_text())
    required = schema["properties"]["dimensions"]["required"]
    assert sorted(required) == sorted(cs.DIMENSIONS)
    charter = (REPO_ROOT / "docs" / "quality" / "COMPREHENSION-REVIEW.md").read_text()
    for dim in cs.DIMENSIONS:
        pretty = dim.replace("_", " ")
        assert pretty in charter.lower(), f"{dim} is scored but not documented in the charter"
    assert f"out of {cs.MAX_TOTAL}" in charter or f"/{cs.MAX_TOTAL}" in charter


# ---------------------------------------------------------------------------
# Retrospective cards: legitimate for a pre-rubric sitting, never a measurement
# ---------------------------------------------------------------------------

def test_a_null_score_needs_the_retrospective_flag(tmp_path):
    bad = card()
    bad["dimensions"]["orientation"]["score"] = None
    run = write_run(tmp_path / "r", [bad])
    assert cs.main(["score", str(run)]) == 2, "inventing a number would be worse, but so is hiding the gap"


def test_a_retrospective_card_may_leave_a_dimension_unscored_and_says_so(tmp_path, capsys):
    c = card("P1", 3)
    c["retrospective"] = True
    c["dimensions"]["orientation"]["score"] = None
    c["dimensions"]["orientation"]["evidence"] = "journal records no timings"
    run = write_run(tmp_path / "r", [c])
    cs.main(["score", str(run)])
    out = capsys.readouterr().out
    assert "unscoreable" in out and "FLOOR" in out
    assert "RETROSPECTIVE" in out


def test_a_retrospective_run_cannot_be_the_later_side_of_a_comparison(tmp_path, capsys):
    before = card("P1", 3)
    after = card("P1", 4)
    after["retrospective"] = True
    a = write_run(tmp_path / "a", [before])
    b = write_run(tmp_path / "b", [after])
    assert cs.main(["compare", str(b), str(a)]) == 1
    assert "never the thing being measured" in capsys.readouterr().out
