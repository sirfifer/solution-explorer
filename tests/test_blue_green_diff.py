"""Hermetic tests for the two-slot blue/green diff tool (card G3).

These drive the real ``scripts/blue-green-diff.py`` with local files and
``file://`` URLs only, never the live network or the live demo/dogfood site, so
they are deterministic and offline. Two behaviors are contract-critical and each
has a test that fails if a future change breaks it:

  1. The diff is a NON-BLOCKING health check: a missing blue (first build), an
     unreachable URL, a malformed projection, or a missing green each degrade to
     a loud honest note in the summary and a ZERO exit. The tool must never fail
     a deploy because the diff infrastructure failed.
  2. On a real diff it produces a correct human summary (with both identities)
     and a byte-deterministic JSON artifact equal to the G1 delta.

Fail-before framing: G3 adds a new capability (there is no prior code path to
regress), so these lock in the two contracts above. The degrade-exits-zero tests
are the regression guard: if the tool is ever changed to raise or exit non-zero
when it cannot fetch or read a projection, they fail.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "blue-green-diff.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("_blue_green_diff", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BGD = _load_module()


def _projection(name: str, component_ids: list[str], analyzer_version: str = "1.0.0") -> dict:
    return {
        "name": name,
        "analyzer_version": analyzer_version,
        "components": [
            {"id": cid, "type": "module", "name": cid.upper(), "children": []}
            for cid in component_ids
        ],
        "relationships": [],
    }


def _write_json(path: Path, obj: dict) -> Path:
    path.write_text(json.dumps(obj), encoding="utf-8")
    return path


# --- degrade-loudly, never break the deploy (contract 1) ---------------------


def test_missing_local_blue_degrades_loudly_and_exits_zero(tmp_path):
    green = _write_json(tmp_path / "green.json", _projection("demo", ["a"]))
    summary = tmp_path / "summary.md"
    rc = BGD.main([
        "--blue", str(tmp_path / "does-not-exist.json"),
        "--new", str(green),
        "--label", "dogfood",
        "--summary-out", str(summary),
        "--json-out", str(tmp_path / "diff.json"),
    ])
    assert rc == 0
    text = summary.read_text(encoding="utf-8")
    assert "BLUE/GREEN DIFF UNAVAILABLE" in text
    assert "non-blocking" in text
    # Green identity is still reported so the operator knows what was built.
    assert "demo (analyzer 1.0.0)" in text
    # No diff was possible, so no JSON artifact was written.
    assert not (tmp_path / "diff.json").exists()


def test_unreachable_url_blue_degrades_loudly(tmp_path):
    green = _write_json(tmp_path / "green.json", _projection("demo", ["a"]))
    summary = tmp_path / "summary.md"
    # A file:// URL to a nonexistent file exercises the URL branch and fails.
    bad_url = (tmp_path / "no-such-blue.json").as_uri()
    rc = BGD.main([
        "--blue", bad_url,
        "--new", str(green),
        "--summary-out", str(summary),
    ])
    assert rc == 0
    text = summary.read_text(encoding="utf-8")
    assert "BLUE/GREEN DIFF UNAVAILABLE" in text
    assert "could not fetch blue" in text


def test_malformed_blue_degrades_loudly(tmp_path):
    green = _write_json(tmp_path / "green.json", _projection("demo", ["a"]))
    blue = tmp_path / "blue.json"
    blue.write_text("{ this is not json", encoding="utf-8")
    summary = tmp_path / "summary.md"
    rc = BGD.main(["--blue", str(blue), "--new", str(green), "--summary-out", str(summary)])
    assert rc == 0
    text = summary.read_text(encoding="utf-8")
    assert "BLUE/GREEN DIFF UNAVAILABLE" in text
    assert "not valid JSON" in text


def test_blue_root_not_object_degrades_loudly(tmp_path):
    green = _write_json(tmp_path / "green.json", _projection("demo", ["a"]))
    blue = tmp_path / "blue.json"
    blue.write_text("[1, 2, 3]", encoding="utf-8")  # valid JSON, wrong shape
    summary = tmp_path / "summary.md"
    rc = BGD.main(["--blue", str(blue), "--new", str(green), "--summary-out", str(summary)])
    assert rc == 0
    assert "not a JSON object" in summary.read_text(encoding="utf-8")


def test_missing_green_degrades_loudly(tmp_path):
    blue = _write_json(tmp_path / "blue.json", _projection("demo", ["a"]))
    summary = tmp_path / "summary.md"
    rc = BGD.main([
        "--blue", str(blue),
        "--new", str(tmp_path / "no-green.json"),
        "--summary-out", str(summary),
    ])
    assert rc == 0
    text = summary.read_text(encoding="utf-8")
    assert "BLUE/GREEN DIFF UNAVAILABLE" in text
    assert "new (green) projection not found" in text


# --- correct summary and JSON on a real diff (contract 2) --------------------


def test_successful_diff_local_blue(tmp_path):
    blue = _write_json(tmp_path / "blue.json", _projection("demo", ["a"]))
    green = _write_json(tmp_path / "green.json", _projection("demo", ["a", "b"]))
    summary = tmp_path / "summary.md"
    json_out = tmp_path / "diff.json"
    rc = BGD.main([
        "--blue", str(blue),
        "--new", str(green),
        "--label", "dogfood",
        "--summary-out", str(summary),
        "--json-out", str(json_out),
    ])
    assert rc == 0
    text = summary.read_text(encoding="utf-8")
    assert "## Blue/green projection diff (dogfood)" in text
    assert "Blue (prior): demo (analyzer 1.0.0)" in text
    assert "Green (new): demo (analyzer 1.0.0)" in text
    # The added component shows up in the embedded G1 report.
    assert "Components: 1 -> 2 (+1)" in text
    assert "b" in text
    # The JSON artifact is the full G1 delta and marks the change.
    payload = json.loads(json_out.read_text(encoding="utf-8"))
    assert payload["schema"] == "solution-explorer/projection-diff/v1"
    assert payload["has_changes"] is True
    assert payload["changed_sections"]["components"] is True
    assert "b" in payload["sections"]["components"]["added"]


def test_successful_diff_via_file_url_blue(tmp_path):
    # Exercises the URL fetch branch (the demo path) with a file:// URL.
    blue = _write_json(tmp_path / "blue.json", _projection("demo", ["a"]))
    green = _write_json(tmp_path / "green.json", _projection("demo", ["a", "b"]))
    summary = tmp_path / "summary.md"
    rc = BGD.main([
        "--blue", blue.as_uri(),
        "--new", str(green),
        "--label", "demo",
        "--summary-out", str(summary),
    ])
    assert rc == 0
    text = summary.read_text(encoding="utf-8")
    assert "Components: 1 -> 2 (+1)" in text
    assert blue.as_uri() in text  # the blue source is recorded


def test_no_changes_summary(tmp_path):
    proj = _projection("demo", ["a", "b"])
    blue = _write_json(tmp_path / "blue.json", proj)
    green = _write_json(tmp_path / "green.json", proj)
    summary = tmp_path / "summary.md"
    rc = BGD.main(["--blue", str(blue), "--new", str(green), "--summary-out", str(summary)])
    assert rc == 0
    assert "No changes" in summary.read_text(encoding="utf-8")


def test_blue_context_recorded(tmp_path):
    blue = _write_json(tmp_path / "blue.json", _projection("demo", ["a"]))
    green = _write_json(tmp_path / "green.json", _projection("demo", ["a"]))
    summary = tmp_path / "summary.md"
    rc = BGD.main([
        "--blue", str(blue), "--new", str(green), "--summary-out", str(summary),
        "--blue-context", "prior-deployment abc123",
    ])
    assert rc == 0
    assert "prior-deployment abc123" in summary.read_text(encoding="utf-8")


# --- determinism and append behavior -----------------------------------------


def test_determinism_summary_and_json(tmp_path):
    blue = _write_json(tmp_path / "blue.json", _projection("demo", ["a", "c"]))
    green = _write_json(tmp_path / "green.json", _projection("demo", ["a", "b"]))
    outs = []
    for i in range(2):
        summary = tmp_path / f"summary{i}.md"
        json_out = tmp_path / f"diff{i}.json"
        BGD.main([
            "--blue", str(blue), "--new", str(green), "--label", "dogfood",
            "--summary-out", str(summary), "--json-out", str(json_out),
        ])
        outs.append((summary.read_bytes(), json_out.read_bytes()))
    assert outs[0][0] == outs[1][0], "summary is not byte-deterministic"
    assert outs[0][1] == outs[1][1], "JSON diff is not byte-deterministic"


def test_summary_is_appended_not_overwritten(tmp_path):
    blue = _write_json(tmp_path / "blue.json", _projection("demo", ["a"]))
    green = _write_json(tmp_path / "green.json", _projection("demo", ["a"]))
    summary = tmp_path / "summary.md"
    summary.write_text("PRIOR STEP OUTPUT\n", encoding="utf-8")
    BGD.main(["--blue", str(blue), "--new", str(green), "--summary-out", str(summary)])
    text = summary.read_text(encoding="utf-8")
    assert text.startswith("PRIOR STEP OUTPUT\n")
    assert "Blue/green projection diff" in text


# --- output-write failures must still exit 0 (adversarial review #78, MAJOR 1) -


def test_unwritable_summary_out_exits_zero(tmp_path, capsys):
    # A summary-out path whose parent directory does not exist must NOT crash:
    # the health check always exits 0. Fail-before: pre-fix this raised
    # FileNotFoundError and exited 1, which would fail the deploy job.
    blue = _write_json(tmp_path / "blue.json", _projection("demo", ["a"]))
    green = _write_json(tmp_path / "green.json", _projection("demo", ["a", "b"]))
    rc = BGD.main([
        "--blue", str(blue), "--new", str(green),
        "--summary-out", str(tmp_path / "no_such_dir" / "out.md"),
    ])
    assert rc == 0
    err = capsys.readouterr()
    # The report is not lost: a last-ditch stderr note plus the report echoed.
    assert "could not write summary" in err.err
    assert "Blue/green projection diff" in err.out


def test_summary_out_is_a_directory_exits_zero(tmp_path):
    blue = _write_json(tmp_path / "blue.json", _projection("demo", ["a"]))
    green = _write_json(tmp_path / "green.json", _projection("demo", ["a"]))
    a_dir = tmp_path / "adir"
    a_dir.mkdir()
    rc = BGD.main(["--blue", str(blue), "--new", str(green), "--summary-out", str(a_dir)])
    assert rc == 0


def test_unwritable_json_out_exits_zero(tmp_path):
    # A failed artifact write must not crash either; the summary is still written.
    blue = _write_json(tmp_path / "blue.json", _projection("demo", ["a"]))
    green = _write_json(tmp_path / "green.json", _projection("demo", ["a", "b"]))
    summary = tmp_path / "summary.md"
    rc = BGD.main([
        "--blue", str(blue), "--new", str(green),
        "--summary-out", str(summary),
        "--json-out", str(tmp_path / "no_such_dir" / "diff.json"),
    ])
    assert rc == 0
    assert "Components: 1 -> 2 (+1)" in summary.read_text(encoding="utf-8")
    assert not (tmp_path / "no_such_dir" / "diff.json").exists()


# --- fetch size cap must degrade loudly (adversarial review #78, MAJOR 2) ------


def test_oversized_blue_degrades_loudly(tmp_path, monkeypatch):
    # A blue larger than the size cap must degrade loudly rather than read
    # unbounded into memory. A file:// URL exercises the same capped-read path a
    # remote fetch uses.
    monkeypatch.setattr(BGD, "_MAX_BLUE_BYTES", 8)
    blue = _write_json(tmp_path / "blue.json", _projection("demo", ["a"]))  # > 8 bytes
    green = _write_json(tmp_path / "green.json", _projection("demo", ["a"]))
    summary = tmp_path / "summary.md"
    rc = BGD.main(["--blue", blue.as_uri(), "--new", str(green), "--summary-out", str(summary)])
    assert rc == 0
    text = summary.read_text(encoding="utf-8")
    assert "BLUE/GREEN DIFF UNAVAILABLE" in text
    assert "exceeds the 8-byte cap" in text


# --- URL classification unit --------------------------------------------------


def test_is_url_classification():
    assert BGD._is_url("http://example.com/a.json")
    assert BGD._is_url("https://example.pages.dev/architecture.json")
    assert BGD._is_url("file:///tmp/x.json")
    assert not BGD._is_url("architecture.json")
    assert not BGD._is_url("./viewer/public/architecture.json")
    assert not BGD._is_url("/abs/path/architecture.json")
