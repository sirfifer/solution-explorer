"""Contracts for the identity derive pass (UG-1).

Every case runs the real pipeline over a temporary repository: extract into a
FactStore, derive, and read ``arch["identity"]``. Nothing here inspects the
detector functions in isolation, because the claim under test is what a reader
would be shown about a real checkout, and the component types the earlier passes
assign are half of that claim.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from analyzer.derive import derive_all
from analyzer.derive import identity as identity_pass
from analyzer.extract import extract_repo
from analyzer.project import project_monolith, project_split
from analyzer.store import FactStore

FIXTURES = Path(__file__).parent / "fixtures" / "identity"


# ---------------------------------------------------------------------------
# fixture repositories
# ---------------------------------------------------------------------------

VSCODE_SHAPED = {
    "package.json": json.dumps({
        "name": "code-oss-dev",
        "version": "1.0.0",
        # The same word appears in scripts 8 lines earlier, which is why the
        # evidence line has to be resolved inside devDependencies.
        "scripts": {"electron": "node build/lib/electron.ts"},
        "dependencies": {"jschardet": "3.1.4"},
        "devDependencies": {"electron": "42.8.1", "typescript": "5.9.2"},
    }, indent=2),
    "product.json": json.dumps({
        "nameShort": "Code - OSS",
        "win32x64AppId": "{{D77B7E06}}",
        "win32arm64AppId": "{{D1ACE434}}",
        "darwinBundleIdentifier": "com.visualstudio.code.oss",
        "linuxIconName": "code-oss",
    }, indent=2),
    "extensions/alpha/package.json": json.dumps({"name": "alpha", "contributes": {"commands": []}}),
    "extensions/alpha/src/main.ts": "export const alpha = 1;\n",
    "extensions/beta/package.json": json.dumps({"name": "beta", "contributes": {"menus": {}}}),
    "extensions/beta/src/main.ts": "export const beta = 2;\n",
    "extensions/gamma/package.json": json.dumps({"name": "gamma", "engines": {"vscode": "^1.0.0"}}),
    "extensions/gamma/src/main.ts": "export const gamma = 3;\n",
    "cli/Cargo.toml": (
        '[package]\nname = "code-cli"\nversion = "0.1.0"\n\n'
        '[[bin]]\nname = "code"\npath = "src/main.rs"\n'
    ),
    "cli/src/main.rs": 'fn main() { println!("code"); }\n',
    "src/vs/workbench/package.json": json.dumps({
        "name": "workbench", "dependencies": {"react": "18.0.0"},
    }),
    "src/vs/workbench/browser/part.ts": "export class Part {}\n",
    "src/vs/code/browser/workbench/workbench.html": "<!DOCTYPE html><html><body></body></html>\n",
    "src/vs/code/browser/workbench/workbench-dev.html": "<!DOCTYPE html><html></html>\n",
}

IOS_SHAPED = {
    "README.md": (
        "# UnaMentis\n\n"
        "UnaMentis is a study companion for iPhone and Apple Watch that keeps "
        "every session on the device.\n"
    ),
    "UnaMentis/Info.plist": '<?xml version="1.0"?>\n<plist><dict></dict></plist>\n',
    "UnaMentis/App.swift": (
        "import SwiftUI\n\n@main\nstruct UnaMentisApp: App {\n"
        "  var body: some Scene { WindowGroup { ContentView() } }\n}\n"
    ),
    "UnaMentis/ContentView.swift": (
        "import SwiftUI\n\nstruct ContentView: View {\n"
        '  var body: some View { Text("hello") }\n}\n'
    ),
    "watch-app/Info.plist": '<?xml version="1.0"?>\n<plist><dict></dict></plist>\n',
    "watch-app/WatchApp.swift": (
        "import SwiftUI\n\n@main\nstruct WatchApp: App {\n"
        '  var body: some Scene { WindowGroup { Text("w") } }\n}\n'
    ),
}

GO_SHAPED = {
    "go.mod": "module example.com/cluster\n\ngo 1.22\n",
    "cmd/apiserver/main.go": "package main\n\nfunc main() {}\n",
    "cmd/kubelet/main.go": "package main\n\nfunc main() {}\n",
    "deploy/deployment.yaml": "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: apiserver\n",
    "pkg/util/util.go": "package util\n\nfunc Helper() {}\n",
}

LIBRARY_SHAPED = {
    "pyproject.toml": '[project]\nname = "tinylib"\nversion = "0.1.0"\n',
    "tinylib/__init__.py": 'VERSION = "0.1.0"\n',
    "tinylib/core.py": "def add(a, b):\n    return a + b\n",
}

SOURCE_ONLY = {
    "src/one.py": "def one():\n    return 1\n",
    "src/two.py": "def two():\n    return 2\n",
}


def _write_repo(root: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    return root


def _derive(root: Path, name: str):
    store = FactStore(":memory:")
    extract_repo(str(root), store)
    return derive_all(store, name)


def _identity(tmp_path: Path, files: dict[str, str], name: str, slug: str) -> dict:
    root = _write_repo(tmp_path / slug, files)
    _, arch = _derive(root, name)
    assert arch.get("identity") is not None, "the identity pass produced nothing"
    return arch["identity"]


def _kinds(identity: dict) -> list[str]:
    return [row["kind"] for row in identity["form_factors"]]


# ---------------------------------------------------------------------------
# every record points at a file that exists
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("slug", "files", "name"),
    [
        ("vscode", VSCODE_SHAPED, "Visual Studio Code"),
        ("ios", IOS_SHAPED, "UnaMentis"),
        ("go", GO_SHAPED, "cluster"),
        ("library", LIBRARY_SHAPED, "tinylib"),
        ("source-only", SOURCE_ONLY, "bare"),
    ],
)
def test_every_form_factor_names_a_file_that_exists(tmp_path, slug, files, name):
    root = _write_repo(tmp_path / slug, files)
    _, arch = _derive(root, name)
    identity = arch["identity"]
    for row in identity["form_factors"]:
        assert row["evidence"], f"{row['kind']} was recorded with no evidence"
        for item in row["evidence"]:
            assert (root / item["file"]).exists(), (
                f"{row['kind']} cites {item['file']}, which is not in the repository"
            )
            assert item.get("marker"), f"{row['kind']} cites {item['file']} with no marker"
        assert row["statement_kind"] == "observed_source_reference"
        assert row["how_met"]
        assert isinstance(row["weight"], int)


# ---------------------------------------------------------------------------
# the four fixture shapes
# ---------------------------------------------------------------------------

def test_a_vscode_shaped_repository_reads_as_desktop_web_cli_and_plugin_host(tmp_path):
    identity = _identity(tmp_path, VSCODE_SHAPED, "Visual Studio Code", "vscode")
    assert sorted(_kinds(identity)) == ["cli", "desktop-app", "plugin-host", "web-app"]
    assert identity["primary"] == "desktop-app"

    desktop = next(row for row in identity["form_factors"] if row["kind"] == "desktop-app")
    assert desktop["platforms"] == ["macos", "windows", "linux"]
    assert desktop["platforms_assumed"] is False
    markers = {(item["file"], item["marker"]) for item in desktop["evidence"]}
    assert ("product.json", "darwinBundleIdentifier") in markers
    assert ("package.json", "devDependencies.electron") in markers

    # The word "electron" also appears in scripts; the cited line must be the
    # one inside devDependencies, or the evidence sends the reader to the wrong
    # place.
    electron = next(
        item for item in desktop["evidence"] if item["marker"] == "devDependencies.electron"
    )
    manifest_lines = VSCODE_SHAPED["package.json"].split("\n")
    assert '"electron"' in manifest_lines[electron["line"] - 1]
    assert "devDependencies" in "\n".join(manifest_lines[:electron["line"]])

    web = next(row for row in identity["form_factors"] if row["kind"] == "web-app")
    assert web["component_id"] == "src/vs/workbench"
    assert web["evidence"][0]["file"] == "src/vs/code/browser/workbench/workbench.html"
    assert web["platforms"] == ["browser"]

    cli = next(row for row in identity["form_factors"] if row["kind"] == "cli")
    assert ("cli/Cargo.toml", "[[bin]]") in {
        (item["file"], item["marker"]) for item in cli["evidence"]
    }

    plugin = next(row for row in identity["form_factors"] if row["kind"] == "plugin-host")
    assert len(plugin["evidence"]) == 3
    assert all(item["file"].startswith("extensions/") for item in plugin["evidence"])


def test_form_factors_are_ordered_by_weight_then_detector_order(tmp_path):
    identity = _identity(tmp_path, VSCODE_SHAPED, "Visual Studio Code", "vscode")
    keys = [
        (-row["weight"], identity_pass.KIND_ORDER.index(row["kind"]))
        for row in identity["form_factors"]
    ]
    assert keys == sorted(keys)


def test_an_ios_shaped_repository_reads_as_an_ios_app_with_a_watch_app(tmp_path):
    identity = _identity(tmp_path, IOS_SHAPED, "UnaMentis", "ios")
    assert _kinds(identity) == ["ios-app", "watch-app"]
    assert identity["primary"] == "ios-app"
    ios = identity["form_factors"][0]
    watch = identity["form_factors"][1]
    assert ios["platforms"] == ["ios"]
    assert watch["platforms"] == ["watchos"]
    # The watch target is built with SwiftUI too. It must not also be claimed
    # as an iPhone app.
    assert watch["component_id"] not in {ios["component_id"]}
    assert identity["languages"] == [{"language": "swift", "share": 1.0}]


def test_a_go_repository_names_each_command_and_its_deployment(tmp_path):
    identity = _identity(tmp_path, GO_SHAPED, "cluster", "go")
    clis = [row for row in identity["form_factors"] if row["kind"] == "cli"]
    assert [row["name"] for row in clis] == ["apiserver", "kubelet"]
    assert [row["evidence"][0]["file"] for row in clis] == [
        "cmd/apiserver/main.go", "cmd/kubelet/main.go",
    ]
    server = next(row for row in identity["form_factors"] if row["kind"] == "server")
    assert server["evidence"][0]["file"] == "deploy/deployment.yaml"
    assert server["evidence"][0]["marker"] == "kind: Deployment"


def test_a_library_repository_reads_as_a_library_and_nothing_else(tmp_path):
    identity = _identity(tmp_path, LIBRARY_SHAPED, "tinylib", "library")
    assert _kinds(identity) == ["library"]
    assert identity["form_factors"][0]["evidence"][0]["file"] == "pyproject.toml"


def test_a_repository_with_no_manifests_claims_nothing(tmp_path):
    identity = _identity(tmp_path, SOURCE_ONLY, "bare", "source-only")
    assert identity["form_factors"] == []
    assert identity["primary"] is None
    assert identity["authors_claim"] is None
    assert identity["truncated"] is False


# ---------------------------------------------------------------------------
# the maintainers' claim
# ---------------------------------------------------------------------------

def test_the_authors_claim_is_the_first_prose_paragraph_of_the_readme(tmp_path):
    files = dict(VSCODE_SHAPED)
    files["README.md"] = (FIXTURES / "vscode-README-head.md").read_text()
    identity = _identity(tmp_path, files, "Visual Studio Code", "readme")
    claim = identity["authors_claim"]
    assert claim is not None
    assert claim["text"].startswith(
        'This repository ("Code - OSS") is where we (Microsoft) develop'
    )
    # Headings, badge rows and the HTML block below are all skipped, and the
    # cited line is where the paragraph starts.
    assert claim["source"] == "README.md"
    assert claim["line"] == 8
    assert claim["statement_kind"] == "repository_claim"
    # Link markup is stripped to its text and inline code loses its backticks,
    # because the reader is shown a sentence, not Markdown.
    assert "](" not in claim["text"]
    assert "`" not in claim["text"]
    assert "shields.io" not in claim["text"]
    assert len(claim["text"]) <= 400


def test_a_long_readme_paragraph_is_capped_on_a_sentence_boundary(tmp_path):
    sentence = "This library moves bytes from one place to another with care. "
    files = dict(LIBRARY_SHAPED)
    files["README.md"] = f"# tinylib\n\n{sentence * 12}\n"
    identity = _identity(tmp_path, files, "tinylib", "long-readme")
    text = identity["authors_claim"]["text"]
    assert len(text) <= 400
    assert text.endswith("care.")


def test_a_repository_with_no_readme_has_no_authors_claim(tmp_path):
    identity = _identity(tmp_path, GO_SHAPED, "cluster", "no-readme")
    assert identity["authors_claim"] is None


# ---------------------------------------------------------------------------
# the projection carries it
# ---------------------------------------------------------------------------

def test_identity_reaches_the_split_manifest_and_the_monolith(tmp_path):
    root = _write_repo(tmp_path / "vscode", VSCODE_SHAPED)
    _, arch = _derive(root, "Visual Studio Code")

    split_dir = tmp_path / "split"
    result = project_split(arch, split_dir)
    manifest = json.loads(Path(result.manifest_path).read_text())
    assert "identity" in manifest
    assert manifest["identity"]["primary"] == "desktop-app"
    assert [row["kind"] for row in manifest["identity"]["form_factors"]] == \
        [row["kind"] for row in arch["identity"]["form_factors"]]

    monolith_path = tmp_path / "architecture.json"
    project_monolith(arch, monolith_path)
    document = json.loads(monolith_path.read_text())
    assert document["identity"]["primary"] == "desktop-app"


# ---------------------------------------------------------------------------
# isolation and determinism
# ---------------------------------------------------------------------------

def test_a_raising_detector_becomes_a_gap_and_the_run_continues(tmp_path, monkeypatch):
    def explode(_facts):
        raise RuntimeError("marker reader tripped")

    patched = tuple(
        (kind, explode if kind == "web-app" else detector)
        for kind, detector in identity_pass._DETECTORS
    )
    monkeypatch.setattr(identity_pass, "_DETECTORS", patched)

    root = _write_repo(tmp_path / "vscode", VSCODE_SHAPED)
    _, arch = _derive(root, "Visual Studio Code")

    gaps = arch.get("gaps") or []
    assert any(gap["producer"] == "derive.identity.web-app" for gap in gaps), gaps
    # The other detectors still reached the reader, and the run assembled.
    assert "web-app" not in _kinds(arch["identity"])
    assert "desktop-app" in _kinds(arch["identity"])
    assert arch["stats"]["total_components"] > 0


def test_identity_is_byte_identical_across_runs(tmp_path):
    root = _write_repo(tmp_path / "vscode", VSCODE_SHAPED)
    first = _derive(root, "Visual Studio Code")[1]["identity"]
    second = _derive(root, "Visual Studio Code")[1]["identity"]
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_identity_reads_no_source_files(tmp_path):
    from analyzer.derive import source_read_audit

    root = _write_repo(tmp_path / "vscode", VSCODE_SHAPED)
    store = FactStore(":memory:")
    extract_repo(str(root), store)
    with source_read_audit() as audit:
        derive_all(store, "Visual Studio Code")
    assert audit.count == 0, f"the derivation read source files: {audit.paths[:10]}"


def test_language_shares_ignore_data_and_documentation(tmp_path):
    files = dict(VSCODE_SHAPED)
    files["fixtures/big.json"] = json.dumps({"rows": [{"n": i} for i in range(4000)]}, indent=1)
    identity = _identity(tmp_path, files, "Visual Studio Code", "languages")
    languages = [row["language"] for row in identity["languages"]]
    assert "json" not in languages
    assert languages[0] == "typescript"
    assert all(0.0 <= row["share"] <= 1.0 for row in identity["languages"])


def test_the_pass_is_registered_between_docs_and_capabilities():
    source = (Path(__file__).parent.parent / "analyzer" / "derive" / "pipeline.py").read_text()
    docs_at = source.index('"derive.docs"')
    identity_at = source.index('"derive.identity"')
    capabilities_at = source.index('"derive.capabilities"')
    assert docs_at < identity_at < capabilities_at


def test_no_dash_characters_leak_into_reader_facing_strings():
    # House rule: no em dashes or en dashes anywhere, including the labels and
    # the how-met phrases the viewer prints verbatim.
    text = os.linesep.join(
        list(identity_pass._LABELS.values()) + list(identity_pass._HOW_MET.values())
    )
    assert "—" not in text
    assert "–" not in text


# ---------------------------------------------------------------------------
# a corrected component type must not leave a stale claim on the front door
# ---------------------------------------------------------------------------

def test_a_corrected_component_type_removes_the_claim_it_supported():
    from analyzer.project.pipeline import prune_identity_against_corrections

    prepared = {
        "components": [{
            "id": "root", "type": "package", "children": [
                # The enrichment's identity verdict corrected this from
                # api-server to module after derive.identity had read it.
                {"id": "completions", "type": "module", "children": []},
                {"id": "api", "type": "api-server", "children": []},
            ],
        }],
        "identity": {
            "primary": "server",
            "form_factors": [
                {"kind": "server", "component_id": "completions", "evidence": [
                    {"file": "completions/azd.ts",
                     "marker": "component typed api-server on port 2377"},
                ]},
                {"kind": "server", "component_id": "api", "evidence": [
                    {"file": "api/package.json",
                     "marker": "component typed api-server on port 8080"},
                ]},
                {"kind": "cli", "component_id": "root", "evidence": [
                    {"file": "package.json", "marker": "bin"},
                ]},
            ],
        },
    }
    prune_identity_against_corrections(prepared)
    records = prepared["identity"]["form_factors"]
    assert [(row["kind"], row["component_id"]) for row in records] == [
        ("server", "api"), ("cli", "root"),
    ]
    assert prepared["identity"]["primary"] == "server"


def test_pruning_is_a_no_op_when_no_type_was_corrected():
    from analyzer.project.pipeline import prune_identity_against_corrections

    prepared = {
        "components": [{"id": "root", "type": "ios-client", "children": []}],
        "identity": {
            "primary": "ios-app",
            "form_factors": [{
                "kind": "ios-app", "component_id": "root",
                "evidence": [{"file": "Info.plist", "marker": "component typed ios-client"}],
            }],
        },
    }
    before = json.dumps(prepared["identity"], sort_keys=True)
    prune_identity_against_corrections(prepared)
    assert json.dumps(prepared["identity"], sort_keys=True) == before


def test_pruning_tolerates_a_projection_with_no_identity():
    from analyzer.project.pipeline import prune_identity_against_corrections

    for identity in (None, {}, {"form_factors": []}):
        prepared = {"components": [], "identity": identity}
        prune_identity_against_corrections(prepared)
