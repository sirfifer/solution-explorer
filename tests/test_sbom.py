"""SBOM and supply chain (P10-1).

These tests drive the real collector and CycloneDX builder against committed
manifest+lockfile fixtures (small but real shapes, no mocks), plus the full
projection pipeline against the polyglot fixture and the self repository. They
encode the card's accept criteria:

  - per-ecosystem parsing (npm, PyPI incl. poetry, Swift, Go, Ruby, Cargo,
    CocoaPods, NuGet) with correct name, declared constraint, resolved version,
    pin status, and direct-vs-transitive scope;
  - pin-status classification is ecosystem-aware (a bare 1.2.3 is exact in npm
    but a range in Cargo);
  - a manifest that fails to parse is a loud warning plus a record, never silent;
  - determinism: two runs are byte-identical;
  - CycloneDX 1.5 structural validity and lowercase-normalized purls;
  - the projection emits sbom.json and the supply_chain section in both split and
    monolith modes, with the sbom.json endpoint present in ai.json;
  - the self repo's real dependencies appear with the correct pin flags.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from analyzer.derive import derive_all
from analyzer.extract import extract_repo
from analyzer.project.pipeline import project_monolith, project_split
from analyzer.project.sbom_emit import emit_sbom
from analyzer.sbom import build_cyclonedx, collect_supply_chain
from analyzer.sbom.models import PIN_EXACT, PIN_RANGE, PIN_UNPINNED
from analyzer.sbom.purl import build_purl, classify_pin, normalize_name
from analyzer.store import FactStore

FIXTURES = Path(__file__).parent / "fixtures"
SBOM = FIXTURES / "sbom"
POLYGLOT = FIXTURES / "polyglot"
REPO_ROOT = Path(__file__).resolve().parent.parent

FIXED_TS = "2020-01-01T00:00:00Z"


def _deps_by_name(sc, ecosystem=None):
    out = {}
    for d in sc.dependencies:
        if ecosystem is None or d.ecosystem == ecosystem:
            out[d.name] = d
    return out


# ---------------------------------------------------------------------------
# Per-ecosystem parsing
# ---------------------------------------------------------------------------

def test_npm_direct_transitive_pins_and_engine_target():
    sc = collect_supply_chain(SBOM / "npm")
    assert sc.ecosystems() == ["npm"]
    deps = _deps_by_name(sc)

    # Direct deps carry their declared constraint and the lockfile-resolved version.
    assert deps["left-pad"].scope == "direct"
    assert deps["left-pad"].version == "1.3.0"
    assert deps["left-pad"].pin_status == PIN_EXACT  # bare 1.3.0 is exact in npm
    assert deps["lodash"].pin_status == PIN_RANGE     # ^4.17.21
    assert deps["typescript"].pin_status == PIN_RANGE  # ~5.4.0
    assert deps["typescript"].version == "5.4.5"

    # A package only in the lockfile is transitive and exact-pinned.
    assert deps["undici"].scope == "transitive"
    assert deps["undici"].version == "5.28.4"
    assert deps["undici"].pin_status == PIN_EXACT

    # The node engine surfaces as a target, not a dependency.
    assert ("node", ">=18") in [(t.kind, t.constraint) for t in sc.targets]
    assert "node" not in deps

    # Evidence points at the manifest and, for a direct dep, the declaring line.
    assert deps["lodash"].evidence_file == "package.json"
    assert deps["lodash"].evidence_line is not None


def test_pypi_pep621_and_requirements():
    sc = collect_supply_chain(SBOM / "pypi")
    deps = _deps_by_name(sc)
    assert deps["click"].pin_status == PIN_EXACT       # ==8.1.7
    assert deps["requests"].pin_status == PIN_RANGE    # >=2.28
    assert deps["PyYAML"].pin_status == PIN_UNPINNED   # no specifier
    assert deps["pytest"].pin_status == PIN_RANGE      # optional-dependency >=7.0
    assert deps["flask"].pin_status == PIN_EXACT       # requirements.txt ==2.3.0
    assert deps["gunicorn"].pin_status == PIN_UNPINNED
    # requires-python is a target, surfaced separately.
    assert ("python", ">=3.9") in [(t.kind, t.constraint) for t in sc.targets]
    # requirements.txt evidence carries the real line number.
    assert deps["flask"].evidence_file == "requirements.txt"
    assert deps["flask"].evidence_line == 2


def test_pypi_poetry_lock_resolves_and_finds_transitive():
    sc = collect_supply_chain(SBOM / "pypi_poetry")
    deps = _deps_by_name(sc)
    assert deps["httpx"].version == "0.27.2"
    assert deps["httpx"].scope == "direct"
    # certifi is only in poetry.lock: transitive, exact-pinned.
    assert deps["certifi"].scope == "transitive"
    assert deps["certifi"].pin_status == PIN_EXACT
    assert ("python", "^3.10") in [(t.kind, t.constraint) for t in sc.targets]


def test_swift_package_and_resolved():
    sc = collect_supply_chain(SBOM / "swift")
    deps = _deps_by_name(sc)
    assert deps["swift-log"].pin_status == PIN_EXACT    # exact: "1.5.3"
    assert deps["swift-nio"].pin_status == PIN_RANGE     # from: "2.0.0"
    assert deps["swift-nio"].version == "2.65.0"
    assert deps["swift-collections"].scope == "transitive"
    assert ("swift-tools", "5.9") in [(t.kind, t.constraint) for t in sc.targets]
    # Swift purl carries the repository path.
    assert deps["swift-nio"].purl == "pkg:swift/github.com/apple/swift-nio@2.65.0"


def test_go_mod_direct_indirect_and_go_directive():
    sc = collect_supply_chain(SBOM / "go")
    deps = _deps_by_name(sc)
    assert deps["github.com/gorilla/mux"].scope == "direct"
    assert deps["github.com/gorilla/mux"].version == "v1.8.1"
    # // indirect marks a transitive requirement, in both block and single form.
    assert deps["github.com/stretchr/testify"].scope == "transitive"
    assert deps["golang.org/x/sys"].scope == "transitive"
    # Every go.mod requirement is exact-pinned by construction.
    assert all(d.pin_status == PIN_EXACT for d in sc.dependencies)
    assert ("go", "1.21") in [(t.kind, t.constraint) for t in sc.targets]


def test_gem_gemfile_and_lock():
    sc = collect_supply_chain(SBOM / "gem")
    deps = _deps_by_name(sc)
    assert deps["rails"].pin_status == PIN_RANGE       # ~> 7.1
    assert deps["rails"].version == "7.1.3"
    assert deps["puma"].pin_status == PIN_UNPINNED
    assert deps["pg"].pin_status == PIN_RANGE          # >= 1.1
    # rack and railties come only from the lock: transitive.
    assert deps["rack"].scope == "transitive"
    assert deps["railties"].scope == "transitive"
    assert ("ruby", "3.2.2") in [(t.kind, t.constraint) for t in sc.targets]


def test_cargo_bare_is_range_but_equals_is_exact():
    sc = collect_supply_chain(SBOM / "cargo")
    deps = _deps_by_name(sc)
    # A bare "1.0" in Cargo is a caret range, unlike npm.
    assert deps["serde"].pin_status == PIN_RANGE
    assert deps["rand"].pin_status == PIN_RANGE        # table {version = "0.8.5"}
    assert deps["anyhow"].pin_status == PIN_EXACT      # "=1.0.80"
    assert deps["serde"].version == "1.0.197"
    assert deps["libc"].scope == "transitive"
    assert ("rust", "1.74") in [(t.kind, t.constraint) for t in sc.targets]


def test_cocoapods_podfile_and_lock():
    sc = collect_supply_chain(SBOM / "cocoapods")
    deps = _deps_by_name(sc)
    assert deps["Alamofire"].pin_status == PIN_RANGE   # ~> 5.8
    assert deps["Alamofire"].version == "5.8.1"
    assert deps["SnapKit"].pin_status == PIN_UNPINNED
    assert deps["Kingfisher"].scope == "transitive"


def test_nuget_csproj_and_lock_direct_transitive():
    sc = collect_supply_chain(SBOM / "nuget")
    deps = _deps_by_name(sc)
    assert deps["Newtonsoft.Json"].scope == "direct"
    assert deps["Newtonsoft.Json"].version == "13.0.3"
    assert deps["Newtonsoft.Json"].pin_status == PIN_EXACT
    # The lock's Transitive type drives the scope.
    assert deps["Serilog.Sinks.Console"].scope == "transitive"
    assert ("dotnet", "net8.0") in [(t.kind, t.constraint) for t in sc.targets]
    # nuget purl is lowercased.
    assert deps["Newtonsoft.Json"].purl == "pkg:nuget/newtonsoft.json@13.0.3"


# ---------------------------------------------------------------------------
# Pin classification and purl normalization (unit)
# ---------------------------------------------------------------------------

def test_classify_pin_is_ecosystem_aware():
    assert classify_pin("npm", "1.2.3") == PIN_EXACT
    assert classify_pin("cargo", "1.2.3") == PIN_RANGE  # caret by default
    assert classify_pin("npm", "^1.2.3") == PIN_RANGE
    assert classify_pin("pypi", "==1.2.3") == PIN_EXACT
    assert classify_pin("pypi", ">=1.0") == PIN_RANGE
    assert classify_pin("npm", "*") == PIN_UNPINNED
    assert classify_pin("npm", None) == PIN_UNPINNED
    assert classify_pin("npm", "git+https://example.com/x.git") == PIN_UNPINNED
    assert classify_pin("nuget", "[1.0,2.0)") == PIN_RANGE
    assert classify_pin("nuget", "1.2.3") == PIN_EXACT


def test_purl_normalization():
    # npm and pypi lowercase; pypi collapses separators (PEP 503).
    assert build_purl("npm", "Left-Pad", "1.0.0") == "pkg:npm/left-pad@1.0.0"
    assert build_purl("pypi", "PyYAML", None) == "pkg:pypi/pyyaml"
    assert normalize_name("pypi", "typing_extensions") == "typing-extensions"
    # A scoped npm name percent-encodes the namespace @.
    assert build_purl("npm", "@babel/core", "7.0.0") == "pkg:npm/%40babel/core@7.0.0"
    # go module paths keep their slashes and case.
    assert build_purl("golang", "github.com/Gorilla/Mux", "v1.0.0") == (
        "pkg:golang/github.com/Gorilla/Mux@v1.0.0"
    )


# ---------------------------------------------------------------------------
# Parse-error loudness
# ---------------------------------------------------------------------------

def test_parse_error_is_loud_not_silent():
    sc = collect_supply_chain(SBOM / "broken")
    # The broken manifest yields no dependencies but a visible warning naming it.
    assert sc is not None
    assert sc.dependencies == []
    assert len(sc.warnings) == 1
    warning = sc.warnings[0]
    assert warning.file == "package.json"
    assert "invalid JSON" in warning.error
    # The warning rides in the section so the viewer can show it.
    section = sc.to_section()
    assert section["counts"]["warnings"] == 1
    assert section["warnings"][0]["file"] == "package.json"


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_collect_and_cyclonedx_are_deterministic():
    sc1 = collect_supply_chain(SBOM / "npm")
    sc2 = collect_supply_chain(SBOM / "npm")
    a = build_cyclonedx(sc1, component_name="x", generated_at=FIXED_TS)
    b = build_cyclonedx(sc2, component_name="x", generated_at=FIXED_TS)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    # Same inputs, same content-derived serial number.
    assert a["serialNumber"] == b["serialNumber"]


def test_dependencies_ranked_direct_before_transitive():
    sc = collect_supply_chain(SBOM / "npm")
    scopes = [d.scope for d in sc.dependencies]
    # Within an ecosystem, every direct dep precedes every transitive one.
    first_transitive = scopes.index("transitive")
    assert all(s == "direct" for s in scopes[:first_transitive])
    assert all(s == "transitive" for s in scopes[first_transitive:])


# ---------------------------------------------------------------------------
# CycloneDX 1.5 structural validity
# ---------------------------------------------------------------------------

def test_cyclonedx_structural_validity():
    sc = collect_supply_chain(SBOM / "npm")
    doc = build_cyclonedx(sc, component_name="npm-fixture", generated_at=FIXED_TS)
    assert doc["bomFormat"] == "CycloneDX"
    assert doc["specVersion"] == "1.5"
    assert isinstance(doc["version"], int)
    assert re.match(
        r"^urn:uuid:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        doc["serialNumber"],
    )
    meta = doc["metadata"]["component"]
    assert meta["type"] == "application"
    assert meta["name"] == "npm-fixture"
    assert doc["metadata"]["timestamp"] == FIXED_TS
    # Every component is a well-formed library with type and name; purls, where
    # present, are pkg: URLs.
    assert doc["components"], "expected components"
    for comp in doc["components"]:
        assert comp["type"] == "library"
        assert comp["name"]
        if "purl" in comp:
            assert comp["purl"].startswith("pkg:")


def test_cyclonedx_metadata_carries_targets_as_properties():
    sc = collect_supply_chain(SBOM / "npm")
    doc = build_cyclonedx(sc, component_name="npm-fixture", generated_at=FIXED_TS)
    props = doc["metadata"]["component"].get("properties", [])
    names = {p["name"]: p["value"] for p in props}
    assert names.get("solution_explorer:target:npm:node") == ">=18"


# ---------------------------------------------------------------------------
# Vendored seam (from the coverage inventory)
# ---------------------------------------------------------------------------

def test_vendored_directories_from_coverage_inventory():
    coverage = {
        "inventory": {
            "groups": [
                {
                    "id": "vendored",
                    "top_directories": [{"dir": "node_modules", "count": 1200}],
                }
            ]
        }
    }
    sc = collect_supply_chain(SBOM / "npm", coverage=coverage)
    assert sc.vendored == [
        {"path": "node_modules", "file_count": 1200, "evidence": {"file": "node_modules"}}
    ]
    section = sc.to_section()
    assert section["vendored"][0]["path"] == "node_modules"
    assert section["counts"]["vendored"] == 1
    # Vendored dirs also appear as CycloneDX library components.
    doc = build_cyclonedx(sc, component_name="x", generated_at=FIXED_TS)
    vendored = [c for c in doc["components"] if c["name"] == "node_modules"]
    assert len(vendored) == 1
    assert vendored[0]["type"] == "library"


# ---------------------------------------------------------------------------
# Section shape and no-theater scope note
# ---------------------------------------------------------------------------

def test_section_shape_and_scope_note():
    sc = collect_supply_chain(SBOM / "npm")
    section = sc.to_section()
    assert section["version"] == 1
    assert section["sbom_endpoint"] == "sbom.json"
    assert section["sbom_format"] == "CycloneDX 1.5"
    # The no-theater scope note states plainly this is not a vulnerability scan.
    assert "not a vulnerability scan" in section["scope_note"].lower()
    eco = section["ecosystems"][0]
    assert eco["id"] == "npm"
    assert eco["direct_count"] == 3
    assert eco["transitive_count"] == 1
    assert eco["pin_counts"].get("exact-pinned") == 2  # left-pad + undici


# ---------------------------------------------------------------------------
# Empty / no-manifest repositories
# ---------------------------------------------------------------------------

def test_no_manifests_returns_none(tmp_path):
    (tmp_path / "readme.md").write_text("# nothing here", encoding="utf-8")
    assert collect_supply_chain(tmp_path) is None


def test_none_root_returns_none():
    assert collect_supply_chain(None) is None


# ---------------------------------------------------------------------------
# Projection emission (split and monolith) against a real store
# ---------------------------------------------------------------------------

def _project(root, tmp_path, split):
    store = FactStore(":memory:")
    extract_repo(root, store)
    _, arch = derive_all(store, root.name, root_path=str(root))
    if split:
        out = tmp_path / "arch"
        result = project_split(
            arch, out, store=store, root=root,
            generated_at=FIXED_TS, analyzer_version="test",
        )
        store.close()
        return out, result
    out = tmp_path / "architecture.json"
    result = project_monolith(
        arch, out, store=store, root=root,
        generated_at=FIXED_TS, analyzer_version="test",
    )
    store.close()
    return out, result


def test_projection_split_emits_sbom_and_section(tmp_path):
    out, result = _project(POLYGLOT, tmp_path, split=True)
    sbom_path = out / "sbom.json"
    assert sbom_path.is_file()
    assert result.sbom_path == sbom_path

    manifest = json.loads((out / "manifest.json").read_text())
    assert "supply_chain" in manifest
    assert manifest["supply_chain"]["counts"]["dependencies"] > 0

    sbom = json.loads(sbom_path.read_text())
    assert sbom["specVersion"] == "1.5"

    ai = json.loads((out / "ai.json").read_text())
    sbom_endpoints = [e for e in ai["endpoints"] if e["path"] == "sbom.json"]
    assert len(sbom_endpoints) == 1
    questions = [w["question"] for w in ai["walk_orders"]]
    assert "what does this depend on" in questions
    # llms.txt links the SBOM.
    assert "sbom.json" in (out / "llms.txt").read_text()


def test_projection_monolith_emits_sbom_and_section(tmp_path):
    out, result = _project(POLYGLOT, tmp_path, split=False)
    sbom_path = out.parent / "sbom.json"
    assert sbom_path.is_file()
    assert result.sbom_path == sbom_path

    mono = json.loads(out.read_text())
    assert "supply_chain" in mono

    ai = json.loads((out.parent / "ai.json").read_text())
    assert any(e["path"] == "sbom.json" for e in ai["endpoints"])


def test_projection_sbom_is_byte_stable(tmp_path):
    out1, _ = _project(POLYGLOT, tmp_path / "a", split=True)
    out2, _ = _project(POLYGLOT, tmp_path / "b", split=True)
    assert (out1 / "sbom.json").read_bytes() == (out2 / "sbom.json").read_bytes()


def test_emit_sbom_is_none_without_root(tmp_path):
    # No scan root: no SBOM (a multi-repo top-level projection).
    assert emit_sbom({"name": "x"}, tmp_path, root=None) is None


# ---------------------------------------------------------------------------
# Self repository, end to end
# ---------------------------------------------------------------------------

def test_self_repo_real_dependencies_appear_with_pins():
    sc = collect_supply_chain(REPO_ROOT)
    assert sc is not None
    # The self repo carries npm (viewer) and PyPI (pyproject) manifests.
    ecosystems = set(sc.ecosystems())
    assert "npm" in ecosystems
    assert "pypi" in ecosystems

    npm = _deps_by_name(sc, "npm")
    # The viewer's real, caret-ranged direct dependencies.
    assert "react" in npm
    assert npm["react"].pin_status == PIN_RANGE
    assert "zustand" in npm
    assert npm["zustand"].scope == "direct"

    pypi = _deps_by_name(sc, "pypi")
    # pyproject optional-dependencies declare pydantic with a >= range.
    assert "pydantic" in pypi
    assert pypi["pydantic"].pin_status == PIN_RANGE

    # requires-python surfaces as a target, not a dependency.
    kinds = {(t.kind, t.ecosystem) for t in sc.targets}
    assert ("python", "pypi") in kinds
