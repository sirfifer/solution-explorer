"""Contracts for scripts/reorient.py (UG-6).

The script exists so a portrait or identity change can be seen on the real VS
Code and UnaMentis bundles in seconds instead of minutes. Its whole value is
that it agrees, byte for byte, with what a full projection would have written,
so these tests compare it against ``build_orientation`` itself.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from analyzer.project.human_views import build_orientation

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "reorient.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("reorient", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reorient = _load_script()


def _manifest(*, with_identity: bool = True) -> dict:
    """The minimal shape build_orientation reads, in the test_human_views idiom."""
    manifest = {
        "name": "Transit Desk",
        "description": "Coordinates dispatch and rider status.",
        "components": [{
            "id": "web", "name": "Rider web", "type": "web-client", "path": "apps/web",
            "description": "The rider-facing web client.",
            "files": ["apps/web/main.ts"], "children": [],
        }, {
            "id": "api", "name": "Dispatch API", "type": "api-server", "path": "services/api",
            "description": "Dispatch and rider status endpoints.",
            "files": ["services/api/app.py"], "children": [],
        }],
        "relationships": [{"source": "web", "target": "api", "type": "http"}],
        "tours": [{"id": "rider", "steps": [{"evidence": {"file": "apps/web/main.ts"}}]}],
        "stats": {"total_components": 2, "total_relationships": 1},
    }
    if with_identity:
        manifest["identity"] = None
    return manifest


def _write_projection(root: Path, manifest: dict) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return root


def test_a_projection_carrying_identity_regenerates_cleanly(tmp_path):
    projection = _write_projection(tmp_path / "architecture", _manifest())
    assert reorient.reorient(projection) == reorient.EXIT_OK

    written = json.loads((projection / "orientation.json").read_text())
    assert written == build_orientation(_manifest())
    assert written["identity"] is None
    assert written["schema"] == "syscorpus.orientation/v1"


def test_a_projection_that_predates_the_identity_pass_is_refused(tmp_path, capsys):
    projection = _write_projection(
        tmp_path / "architecture", _manifest(with_identity=False),
    )
    assert reorient.reorient(projection) == reorient.EXIT_PREDATES_IDENTITY
    assert "predates the identity pass" in capsys.readouterr().err
    # Nothing is written: a sidecar claiming no form factors would be a lie the
    # reader could not tell from a subject that genuinely has none.
    assert not (projection / "orientation.json").exists()


def test_a_missing_manifest_is_refused(tmp_path, capsys):
    projection = tmp_path / "empty"
    projection.mkdir()
    assert reorient.reorient(projection) == reorient.EXIT_PREDATES_IDENTITY
    assert "no manifest.json" in capsys.readouterr().err


def test_check_reports_a_stale_sidecar_and_passes_once_regenerated(tmp_path, capsys):
    projection = _write_projection(tmp_path / "architecture", _manifest())
    (projection / "orientation.json").write_text('{"schema": "stale"}\n', encoding="utf-8")

    assert reorient.reorient(projection, check=True) == reorient.EXIT_DIFFERS
    diff = capsys.readouterr().out
    assert "(on disk)" in diff and "(rebuilt)" in diff

    assert reorient.reorient(projection) == reorient.EXIT_OK
    assert reorient.reorient(projection, check=True) == reorient.EXIT_OK
    assert "up to date" in capsys.readouterr().out


def test_check_never_writes(tmp_path):
    projection = _write_projection(tmp_path / "architecture", _manifest())
    reorient.reorient(projection, check=True)
    assert not (projection / "orientation.json").exists()


def test_optional_sidecars_are_read_when_present(tmp_path):
    manifest = _manifest()
    projection = _write_projection(tmp_path / "architecture", manifest)
    support = {"counts": {"configuration": 2}, "configuration": [], "external_dependencies": [],
               "entry_points": [], "attention": [], "method_caveat": "n/a"}
    (projection / "support.json").write_text(json.dumps(support), encoding="utf-8")

    assert reorient.reorient(projection) == reorient.EXIT_OK
    written = json.loads((projection / "orientation.json").read_text())
    route = next(row for row in written["question_routes"] if row["id"] == "support")
    assert route["available"] is True


def test_the_cli_entry_point_maps_arguments_to_the_same_result(tmp_path):
    projection = _write_projection(tmp_path / "architecture", _manifest())
    assert reorient.main([str(projection)]) == reorient.EXIT_OK
    assert reorient.main([str(projection), "--check"]) == reorient.EXIT_OK


def test_the_script_states_why_it_exists():
    doc = reorient.__doc__ or ""
    assert doc.strip()
    assert "—" not in doc and "–" not in doc


@pytest.mark.parametrize("flag", ["-h", "--help"])
def test_help_is_offered(flag, capsys):
    with pytest.raises(SystemExit) as exit_info:
        reorient.main([flag])
    assert exit_info.value.code == 0
    assert "projection directory" in capsys.readouterr().out
