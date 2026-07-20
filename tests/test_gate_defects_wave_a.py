"""P9-0 gate defects, wave A: honest stats, edges, self-detection, fixtures, activity.

Fail-before regression tests for the surgical analyzer defects D1, D2, D3, D6,
D9, and D11 filed in the P9-0 gate record (docs/remediation/TASKS.md). Each test
reproduces the real-world defect shape on a real fixture (a temp tree or a real
git repo driven through subprocess, no mocks) and asserts the fixed behavior.

  D1  generated projection output is not counted as source
  D2  an http edge is only drawn when the URL host resolves to the target
  D3  detectors do not fire on their own string-literal pattern definitions
  D6  capabilities and entities from test/fixture dirs are marked, not deleted
  D9  file-level churn ranking excludes non-source files
  D11 a warm store from a shallow clone reprocesses newly available history
"""

from __future__ import annotations

import json
import subprocess

from analyzer.derive import derive_all
from analyzer.extract.activity import extract_activity
from analyzer.extract.runner import extract_repo
from analyzer.extract.signals import extract_signals
from analyzer.parsers import PARSERS
from analyzer.project.activity import build_activity
from analyzer.store import FactStore

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

# A minimal but recognizable solution-explorer projection: the header carries
# the generator keys _is_generated_projection looks for.
_PROJECTION = json.dumps(
    {
        "name": "demo",
        "generated_at": "2026-07-19T00:00:00Z",
        "analyzer_version": "9.9.9",
        "components": [{"id": "root", "name": "demo"}],
        "relationships": [],
    }
)


def _coverage(store) -> dict[str, tuple[str, str | None]]:
    return {
        c["path"]: (c["disposition"], c["reason"]) for c in store.coverage()
    }


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True,
                   capture_output=True, text=True)


def _init_repo(root):
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init")
    _git(root, "config", "user.email", "t@t.com")
    _git(root, "config", "user.name", "T")


def _all_items(arch, key):
    # Capabilities and entities appear both as a top-level flat index and nested
    # on their owning components; dedupe by id so the count is honest.
    by_id: dict[str, dict] = {}

    def add(items):
        for it in items or []:
            by_id[it["id"]] = it

    def walk(cs):
        for c in cs:
            add(c.get(key, []))
            walk(c.get("children", []))

    add(arch.get(key, []))
    walk(arch["components"])
    return list(by_id.values())


# ---------------------------------------------------------------------------
# D1: generated projection output is accounted, never parsed as source
# ---------------------------------------------------------------------------

def test_d1_generated_projection_is_not_counted_as_source(tmp_path):
    # A real source file, a committed split dataset (manifest.json + data shard),
    # a committed monolith architecture.json, a real fixture, and a plain config.
    (tmp_path / "app.py").write_text("def run():\n    return 1\n")

    dataset = tmp_path / "viewer" / "public" / "architecture"
    (dataset / "data").mkdir(parents=True)
    (dataset / "manifest.json").write_text(_PROJECTION)
    (dataset / "data" / "detail-root.json").write_text(
        json.dumps({"id": "root", "symbols": []})
    )

    (tmp_path / "architecture.json").write_text(_PROJECTION)

    fixtures = tmp_path / "tests" / "fixtures"
    fixtures.mkdir(parents=True)
    (fixtures / "sample.py").write_text("SAMPLE = {'a': 1}\n")

    (tmp_path / "package.json").write_text(json.dumps({"name": "demo", "version": "1"}))

    store = FactStore(":memory:")
    extract_repo(str(tmp_path), store)
    cov = _coverage(store)

    # The real source, the fixture, and the plain config stay parsed.
    assert cov["app.py"][0] == "parsed"
    assert cov["tests/fixtures/sample.py"][0] == "parsed", "fixtures must stay parsed"
    assert cov["package.json"][0] == "parsed", "a plain config JSON is still source"

    # The monolith projection file is accounted as generated, never parsed.
    assert cov["architecture.json"][0] == "excluded:generated"

    # The split dataset directory is pruned to one build-output row and its
    # manifest/shards never enter the parsed set.
    assert cov["viewer/public/architecture"][0] == "excluded:skipped_directory"
    assert "generated" in (cov["viewer/public/architecture"][1] or "")
    assert "viewer/public/architecture/manifest.json" not in cov
    parsed = {p for p, (d, _) in cov.items() if d == "parsed"}
    assert not any(p.startswith("viewer/public/architecture/") for p in parsed)


def test_d1_generated_rows_classify_as_generated_inventory(tmp_path):
    from analyzer.project.inventory import classify_row

    assert classify_row("architecture.json", "excluded:generated", None) == "generated"
    assert (
        classify_row(
            "viewer/public/architecture",
            "excluded:skipped_directory",
            "generated: solution-explorer projection dataset",
        )
        == "generated"
    )


# ---------------------------------------------------------------------------
# D2: an http edge requires the URL host to resolve to the target component
# ---------------------------------------------------------------------------

def test_d2_no_http_edge_from_name_inside_an_unrelated_url(tmp_path):
    # A frontend fetches a github.com URL that merely CONTAINS another component's
    # name as a path segment. Pre-fix this fabricated a "calls paymentservice"
    # http edge; post-fix the host is github.com, so no edge is drawn.
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "package.json").write_text(json.dumps({"name": "frontend"}))
    (tmp_path / "frontend" / "app.js").write_text(
        'export const load = () => fetch("https://github.com/acme/paymentservice/issues");\n'
    )
    (tmp_path / "paymentservice").mkdir()
    (tmp_path / "paymentservice" / "package.json").write_text(
        json.dumps({"name": "paymentservice"})
    )
    (tmp_path / "paymentservice" / "index.js").write_text("export const h = () => 'ok';\n")

    store = FactStore(":memory:")
    extract_repo(str(tmp_path), store)
    _, arch = derive_all(store, "proj")

    names = {}

    def walk(cs):
        for c in cs:
            names[c["id"]] = c["name"]
            walk(c.get("children", []))

    walk(arch["components"])
    http = [
        (names.get(r["source"]), names.get(r["target"]))
        for r in arch["relationships"]
        if r["type"] == "http"
    ]
    assert ("frontend", "paymentservice") not in http
    assert http == [], f"no http edge should be fabricated, got: {http}"
    # The url_reference is preserved as a per-component signal (not lost).
    assert any(s["kind"] == "url_reference" for s in store.signals())


def test_d2_http_edge_survives_when_host_resolves_to_a_server(tmp_path):
    # A web client references http://apibackend/... (no port) and apibackend is a
    # server that binds a port. The host resolves exactly to a component that
    # declares an endpoint, so the edge survives with real call-site evidence.
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "package.json").write_text(json.dumps({"name": "web"}))
    (tmp_path / "web" / "client.js").write_text(
        'const BASE = "http://apibackend/v1/users";\nexport const get = () => fetch(BASE);\n'
    )
    (tmp_path / "apibackend").mkdir()
    (tmp_path / "apibackend" / "package.json").write_text(json.dumps({"name": "apibackend"}))
    (tmp_path / "apibackend" / "server.js").write_text(
        'const express = require("express");\n'
        "const app = express();\n"
        'app.get("/v1/users", (req, res) => res.json([]));\n'
        "app.listen(8080);\n"
    )

    store = FactStore(":memory:")
    extract_repo(str(tmp_path), store)
    _, arch = derive_all(store, "proj")

    names = {}

    def walk(cs):
        for c in cs:
            names[c["id"]] = c["name"]
            walk(c.get("children", []))

    walk(arch["components"])
    http = [
        r
        for r in arch["relationships"]
        if r["type"] == "http"
        and names.get(r["source"]) == "web"
        and names.get(r["target"]) == "apibackend"
    ]
    assert len(http) == 1, f"host-resolved edge must survive, got: {http}"
    assert http[0]["evidence"], "the surviving edge must carry evidence"
    assert "apibackend" in http[0]["evidence"][0]["snippet"]


# ---------------------------------------------------------------------------
# D3: detectors do not fire on their own string-literal pattern definitions
# ---------------------------------------------------------------------------

_DETECTOR_SOURCE = (
    "import re\n"
    "# A pattern/detector tool defines detection rules as string constants.\n"
    "JOB_RULES = [\n"
    '    re.compile(r"@shared_task\\b"),\n'
    '    re.compile(r"@periodic_task\\b"),\n'
    "]\n"
    'QUEUE_RULE = re.compile(r"celery")\n'
    "def scan(text):\n"
    '    """Detect @shared_task and celery usage in text."""\n'
    "    return [r for r in JOB_RULES if r.search(text)]\n"
)

_REAL_CELERY = (
    "from celery import shared_task\n"
    "@shared_task\n"
    "def process_payment():\n"
    "    return True\n"
)


def test_d3_detector_definitions_produce_no_capability_signals():
    py = PARSERS.get("python")
    sigs = extract_signals(_DETECTOR_SOURCE, "python", py)
    firing = [s for s in sigs if s.kind in ("job", "queue_driver")]
    assert firing == [], f"detectors fired on their own pattern definitions: {firing}"


def test_d3_real_celery_usage_still_fires():
    py = PARSERS.get("python")
    sigs = extract_signals(_REAL_CELERY, "python", py)
    jobs = [s for s in sigs if s.kind == "job"]
    assert jobs, "a real @shared_task decorator must still be detected"
    assert jobs[0].value.get("framework") == "celery"


# ---------------------------------------------------------------------------
# D6: capabilities and entities from test/fixture dirs are marked, not deleted
# ---------------------------------------------------------------------------

def test_d6_fixture_capabilities_are_marked_and_product_ones_are_not(tmp_path):
    # A product endpoint under src/ and a fixture endpoint under tests/fixtures/.
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text(
        "from flask import Flask\n"
        "app = Flask(__name__)\n"
        "@app.route('/products')\n"
        "def products():\n    return []\n"
    )
    fx = tmp_path / "tests" / "fixtures" / "svc"
    fx.mkdir(parents=True)
    (fx / "server.py").write_text(
        "from flask import Flask\n"
        "app = Flask(__name__)\n"
        "@app.route('/scaffold')\n"
        "def scaffold():\n    return []\n"
    )

    store = FactStore(":memory:")
    extract_repo(str(tmp_path), store)
    _, arch = derive_all(store, "proj")
    caps = {c["name"]: c for c in _all_items(arch, "capabilities")}

    assert "GET /products" in caps and "GET /scaffold" in caps, caps.keys()
    assert not caps["GET /products"].get("fixture"), "product capability must not be marked"
    assert caps["GET /scaffold"].get("fixture") is True, "fixture capability must be marked"
    # Nothing is deleted: both are accounted.
    assert len([c for c in _all_items(arch, "capabilities") if c["kind"] == "api"]) == 2


def test_d6_fixture_entities_are_marked(tmp_path):
    fx = tmp_path / "tests" / "fixtures" / "models"
    fx.mkdir(parents=True)
    (fx / "models.py").write_text(
        "from django.db import models\n"
        "class Widget(models.Model):\n"
        "    name = models.CharField(max_length=10)\n"
    )
    src = tmp_path / "src"
    src.mkdir()
    (src / "models.py").write_text(
        "from django.db import models\n"
        "class Invoice(models.Model):\n"
        "    total = models.IntegerField()\n"
    )

    store = FactStore(":memory:")
    extract_repo(str(tmp_path), store)
    _, arch = derive_all(store, "proj")
    ents = {e["name"]: e for e in _all_items(arch, "data_entities")}

    assert "Widget" in ents and "Invoice" in ents, ents.keys()
    assert ents["Widget"].get("fixture") is True, "fixture entity must be marked"
    assert not ents["Invoice"].get("fixture"), "product entity must not be marked"


# ---------------------------------------------------------------------------
# D9: file-level churn ranking excludes non-source files
# ---------------------------------------------------------------------------

def test_d9_vendored_file_churn_does_not_rank(tmp_path):
    # A real git repo whose history touches a real source file AND the internals
    # of a vendored .xcframework (a pruned, non-source directory). The vendored
    # file must not appear in the file-level churn or coupling rankings, while
    # the source file must.
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "app.py").write_text("x = 1\n")
    fw = repo / "Vendor.xcframework"
    fw.mkdir()
    (fw / "binary.bin.txt").write_text("blob v1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "c1")
    # A second commit touching both, so they co-change.
    (repo / "app.py").write_text("x = 2\n")
    (fw / "binary.bin.txt").write_text("blob v2\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "c2")

    store = FactStore(":memory:")
    extract_repo(str(repo), store)
    extract_activity(repo, store)
    activity = build_activity(store)

    ranked = set(activity["files"])
    assert "app.py" in ranked, "source file must rank in churn"
    vendored = [p for p in ranked if "xcframework" in p]
    assert vendored == [], f"vendored files must not rank in churn: {vendored}"
    for pair in activity["file_coupling"]:
        assert "xcframework" not in pair["a"] and "xcframework" not in pair["b"], pair


# ---------------------------------------------------------------------------
# D11: a warm store from a shallow clone reprocesses newly available history
# ---------------------------------------------------------------------------

def test_d11_incremental_processes_a_new_commit_on_a_warm_store(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "f.txt").write_text("a\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "c1")

    store = FactStore(":memory:")
    first = extract_activity(repo, store)
    assert first.commits_processed == 1
    head1 = store.get_meta("activity_head")

    (repo / "f.txt").write_text("a\nb\n")
    _git(repo, "commit", "-am", "c2")

    second = extract_activity(repo, store)
    assert second.mode == "incremental"
    assert second.commits_processed == 1, "the new commit must be processed"
    assert store.get_meta("activity_head") != head1, "stored HEAD must advance"


def test_d11_warm_shallow_store_reprocesses_deepened_history(tmp_path):
    # A shallow clone builds a store with partial history; after the clone is
    # unshallowed the ancestor commits become available while HEAD is unchanged.
    # Pre-fix the warm store reported "unchanged, 0 commits" and stranded that
    # history; post-fix it reprocesses in full.
    src = tmp_path / "src"
    _init_repo(src)
    for i in range(1, 6):
        (src / "f.txt").write_text("\n".join(f"line{j}" for j in range(i)) + "\n")
        _git(src, "add", "-A")
        _git(src, "commit", "-m", f"c{i}")

    shallow = tmp_path / "shallow"
    subprocess.run(
        ["git", "clone", "--depth", "1", f"file://{src}", str(shallow)],
        check=True, capture_output=True, text=True,
    )

    store = FactStore(":memory:")
    r1 = extract_activity(shallow, store)
    assert r1.shallow is True
    assert r1.commits_processed == 1, "a depth-1 clone sees only the tip"

    _git(shallow, "fetch", "--unshallow")
    r2 = extract_activity(shallow, store)
    assert r2.commits_processed >= 4, (
        "newly available ancestor history must be reprocessed, not skipped as "
        f"unchanged (got mode={r2.mode}, commits={r2.commits_processed})"
    )
