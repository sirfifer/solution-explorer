"""P5-1 capability extraction: per-framework endpoints, CLI, events, jobs.

Two layers:
  1. Direct unit tests over analyzer/extract/frameworks (the per-framework
     endpoint matrix and the header-name false-positive regression).
  2. End-to-end tests that build a temp repo, run the real extract + derive
     tiers, and assert capabilities land in the store and the arch dict with
     evidence, confidence, owning component, and a defining-symbol link.

The false-positive regression (test_header_names_never_become_routes and its
end-to-end sibling) is the audit's counterexample class: header names captured
as routes. It fails on the pre-fix code (delegation to the legacy parser); the
fail-before proof is recorded in the P5-1 card Evidence.
"""

from __future__ import annotations

import json

import pytest

from analyzer.derive import derive_all
from analyzer.extract.frameworks import (
    extract_cli,
    extract_endpoints,
    extract_jobs,
    is_route_path,
)
from analyzer.extract.runner import extract_repo
from analyzer.store import FactStore

# ---------------------------------------------------------------------------
# 1. Per-framework endpoint matrix (a test per framework, card scope)
# ---------------------------------------------------------------------------

_FLASK = (
    "from flask import Flask\n"
    "app = Flask(__name__)\n"
    "@app.route('/users', methods=['GET', 'POST'])\n"
    "def users():\n"
    "    return []\n"
)
_FASTAPI = (
    "from fastapi import FastAPI\n"
    "app = FastAPI()\n"
    "@app.get('/users/{user_id}')\n"
    "def read_user(user_id: int):\n"
    "    return {}\n"
)
_AIOHTTP = (
    "from aiohttp import web\n"
    "app = web.Application()\n"
    "app.router.add_get('/health', handle)\n"
    "app.router.add_post('/submit', handle)\n"
)
_EXPRESS = (
    "const express = require('express');\n"
    "const app = express();\n"
    "app.get('/api/users', (req, res) => res.json([]));\n"
    "app.post('/api/users', (req, res) => res.sendStatus(201));\n"
)
_NEXT = (
    "export async function GET(request) { return Response.json([]); }\n"
    "export async function POST(request) { return new Response(null); }\n"
)
_GIN = (
    "package main\n"
    "import \"github.com/gin-gonic/gin\"\n"
    "func main() {\n"
    "    r := gin.Default()\n"
    "    r.GET(\"/ping\", pong)\n"
    "    r.POST(\"/users\", create)\n"
    "}\n"
)
_RAILS = (
    "Rails.application.routes.draw do\n"
    "  get '/health', to: 'health#show'\n"
    "  resources :articles\n"
    "end\n"
)
_ACTIX = (
    "use actix_web::{get, web, App};\n"
    "#[get(\"/hello\")]\n"
    "async fn hello() -> impl Responder { \"\" }\n"
)
_AXUM = (
    "use axum::{routing::get, Router};\n"
    "let app = Router::new().route(\"/users\", get(list_users));\n"
)
_VAPOR = (
    "import Vapor\n"
    "func routes(_ app: Application) throws {\n"
    "    app.get(\"todos\") { req in return [] }\n"
    "    app.post(\"login\") { req in return \"\" }\n"
    "}\n"
)

_MATRIX = [
    ("flask", _FLASK, "python", {("GET", "/users"), ("POST", "/users")}, "flask"),
    ("fastapi", _FASTAPI, "python", {("GET", "/users/{user_id}")}, "fastapi"),
    ("aiohttp", _AIOHTTP, "python", {("GET", "/health"), ("POST", "/submit")}, "aiohttp"),
    ("express", _EXPRESS, "javascript", {("GET", "/api/users"), ("POST", "/api/users")}, "express"),
    ("nextjs", _NEXT, "typescript", {("GET", "(file-based)"), ("POST", "(file-based)")}, "nextjs"),
    ("gin", _GIN, "go", {("GET", "/ping"), ("POST", "/users")}, "gin"),
    ("rails", _RAILS, "ruby", {("GET", "/health"), ("RESOURCE", "/articles")}, "rails"),
    ("actix", _ACTIX, "rust", {("GET", "/hello")}, "actix"),
    ("axum", _AXUM, "rust", {("GET", "/users")}, "axum"),
    ("vapor", _VAPOR, "swift", {("GET", "/todos"), ("POST", "/login")}, "vapor"),
]


@pytest.mark.parametrize("fw,code,lang,expected,framework", _MATRIX, ids=[m[0] for m in _MATRIX])
def test_endpoint_extraction_per_framework(fw, code, lang, expected, framework):
    found = {(v["method"], v["path"]) for v, _ in extract_endpoints(code, lang)}
    assert found == expected, f"{fw}: got {found}"
    frameworks = {v["framework"] for v, _ in extract_endpoints(code, lang)}
    assert framework in frameworks, f"{fw}: framework label {frameworks}"


# ---------------------------------------------------------------------------
# 2. The header-name false-positive regression (the audit counterexamples)
# ---------------------------------------------------------------------------

_WORKER_TS = (
    "async function handleWebhook(request) {\n"
    "  const sig = request.headers.get('X-Hub-Signature-256');\n"
    "  const auth = request.headers.get('Authorization');\n"
    "  const ct = request.headers.get('Content-Type');\n"
    "  const resp = await fetch('https://api.example.com/v1/data');\n"
    "  const remote = await axios.get('https://api.example.com/users');\n"
    "  return new Response('ok');\n"
    "}\n"
)
_CLIENT_PY = (
    "import requests\n"
    "def fetch():\n"
    "    r = requests.get('https://api.example.com/users')\n"
    "    token = headers.get('Authorization')\n"
    "    sig = headers.get('X-Hub-Signature-256')\n"
    "    return r.json()\n"
)


def test_header_names_never_become_routes():
    assert extract_endpoints(_WORKER_TS, "typescript") == []
    assert extract_endpoints(_CLIENT_PY, "python") == []


def test_route_shape_guard_rejects_headers_and_urls():
    for header in ("Authorization", "X-Hub-Signature-256", "Content-Type", "Accept"):
        assert not is_route_path(header)
        assert not is_route_path(header, allow_bare=True)
    assert not is_route_path("https://api.example.com/users")
    assert not is_route_path("http://x/y", allow_bare=True)
    assert is_route_path("/users")
    assert is_route_path("users", allow_bare=True)  # bare route component (Vapor/Rails)
    assert not is_route_path("users")               # bare rejected for slash frameworks


def test_no_api_capability_from_header_code_end_to_end(tmp_path):
    (tmp_path / "worker.ts").write_text(_WORKER_TS)
    (tmp_path / "client.py").write_text(_CLIENT_PY)
    store = FactStore(":memory:")
    extract_repo(str(tmp_path), store)
    _, arch = derive_all(store, "svc")
    endpoint_signals = [s for s in store.signals() if s["kind"] == "endpoint"]
    assert endpoint_signals == [], f"header code produced endpoint signals: {endpoint_signals}"
    api_caps = [c for c in store.capabilities() if c["kind"] == "api"]
    assert api_caps == [], f"header code produced api capabilities: {api_caps}"


# ---------------------------------------------------------------------------
# 3. CLI command + flag extraction (click, typer, clap, commander)
# ---------------------------------------------------------------------------

def test_cli_click_commands_and_flags():
    code = (
        "import click\n"
        "@click.command('deploy')\n"
        "@click.option('--force')\n"
        "@click.option('--env')\n"
        "def deploy():\n    pass\n"
    )
    commands, options = extract_cli(code, "python")
    assert ("deploy", "click") in {(c["name"], c["framework"]) for c, _ in commands}
    flags = {o["flag"] for o, _ in options}
    assert {"--force", "--env"} <= flags


def test_cli_typer_command_and_option():
    code = (
        "import typer\n"
        "app = typer.Typer()\n"
        "@app.command()\n"
        "def build(name: str = typer.Option('--name')):\n    pass\n"
    )
    commands, options = extract_cli(code, "python")
    assert any(c["framework"] == "typer" for c, _ in commands)
    assert any(o["flag"] == "--name" for o, _ in options)


def test_cli_clap_commands_and_flags():
    code = (
        'let m = Command::new("mytool")\n'
        '    .subcommand(Command::new("run")\n'
        '        .arg(Arg::new("v").long("verbose")));\n'
    )
    commands, options = extract_cli(code, "rust")
    names = {c["name"] for c, _ in commands}
    assert {"mytool", "run"} <= names
    assert any(o["flag"] == "verbose" for o, _ in options)


def test_cli_commander_commands_and_flags():
    code = (
        "program\n"
        "  .command('serve <port>')\n"
        "  .option('-p, --port <n>')\n"
        "  .requiredOption('--host <h>')\n"
    )
    commands, options = extract_cli(code, "javascript")
    assert any(c["framework"] == "commander" for c, _ in commands)
    flags = {o["flag"] for o, _ in options}
    assert {"--port", "--host"} <= flags


def test_cli_flags_attach_to_nearest_command_end_to_end(tmp_path):
    (tmp_path / "cli.py").write_text(
        "import click\n"
        "@click.command('build')\n"
        "@click.option('--target')\n"
        "def build():\n    pass\n"
        "@click.command('deploy')\n"
        "@click.option('--force')\n"
        "@click.option('--env')\n"
        "def deploy():\n    pass\n"
    )
    store = FactStore(":memory:")
    extract_repo(str(tmp_path), store)
    _, arch = derive_all(store, "tool")
    caps = {c["name"]: c for c in store.capabilities() if c["kind"] == "cli"}
    assert caps["build"]["detail"]["flags"] == ["--target"]
    assert caps["deploy"]["detail"]["flags"] == ["--env", "--force"]


# ---------------------------------------------------------------------------
# 4. Events and jobs (inferred confidence)
# ---------------------------------------------------------------------------

def test_event_capability_from_queue_topic(tmp_path):
    (tmp_path / "pub.py").write_text(
        "def publish_order(bus):\n"
        "    bus.publish('orders.created', payload)\n"
        "    bus.subscribe('payments.settled', handler)\n"
    )
    store = FactStore(":memory:")
    extract_repo(str(tmp_path), store)
    derive_all(store, "svc")
    events = {c["name"]: c for c in store.capabilities() if c["kind"] == "event"}
    assert events, "no event capabilities extracted"
    for cap in events.values():
        assert cap["confidence"] == "inferred"
    produced = [c for c in events.values() if c["detail"].get("direction") == "produce"]
    consumed = [c for c in events.values() if c["detail"].get("direction") == "consume"]
    assert produced and consumed


def test_swift_argument_label_topic_is_not_an_event_capability(tmp_path):
    """A Swift ``topic:`` argument is not a queue declaration or operation."""
    (tmp_path / "Telemetry.swift").write_text(
        "func record() {\n"
        "    logger.log(topic: \"voice.latency\", value: 42)\n"
        "    monitor.measure(topic: \"session.health\")\n"
        "}\n"
    )
    store = FactStore(":memory:")
    extract_repo(str(tmp_path), store)
    derive_all(store, "app")
    assert [c for c in store.capabilities() if c["kind"] == "event"] == []


def test_queue_assignment_remains_event_evidence(tmp_path):
    (tmp_path / "events.py").write_text("import pika\ntopic = 'orders.created'\n")
    store = FactStore(":memory:")
    extract_repo(str(tmp_path), store)
    derive_all(store, "svc")
    events = [c for c in store.capabilities() if c["kind"] == "event"]
    assert [c["detail"]["topic"] for c in events] == ["orders.created"]


def test_plain_topic_assignment_without_queue_driver_is_not_event_evidence(tmp_path):
    (tmp_path / "model.py").write_text("topic = 'curriculum'\n")
    store = FactStore(":memory:")
    extract_repo(str(tmp_path), store)
    derive_all(store, "app")
    assert [c for c in store.capabilities() if c["kind"] == "event"] == []


def test_job_capability_from_scheduled_task(tmp_path):
    (tmp_path / "tasks.py").write_text(
        "from celery import shared_task\n"
        "@shared_task\n"
        "def send_email():\n    pass\n"
    )
    store = FactStore(":memory:")
    extract_repo(str(tmp_path), store)
    derive_all(store, "svc")
    jobs = [c for c in store.capabilities() if c["kind"] == "job"]
    assert jobs, "no job capabilities extracted"
    assert jobs[0]["confidence"] == "inferred"
    assert jobs[0]["detail"]["framework"] == "celery"
    # the defining symbol (the decorated function) is linked
    assert jobs[0]["name"] == "send_email"


def test_extract_jobs_direct():
    assert extract_jobs("@shared_task\ndef t(): pass", "python")
    assert extract_jobs("cron.schedule('*/5 * * * *', fn)", "javascript")


# ---------------------------------------------------------------------------
# 5. Store landing: evidence, confidence, owner, defining symbol
# ---------------------------------------------------------------------------

def test_api_capability_lands_in_store_with_full_record(tmp_path):
    pkg = tmp_path / "api"
    pkg.mkdir()
    (pkg / "server.py").write_text(_FASTAPI)
    store = FactStore(":memory:")
    extract_repo(str(tmp_path), store)
    _, arch = derive_all(store, "svc")

    caps = [c for c in store.capabilities() if c["kind"] == "api"]
    assert len(caps) == 1
    cap = caps[0]
    assert cap["name"] == "GET /users/{user_id}"
    assert cap["detail"]["method"] == "GET"
    assert cap["detail"]["path"] == "/users/{user_id}"
    assert cap["detail"]["framework"] == "fastapi"
    assert cap["confidence"] == "certain"
    assert cap["component_id"], "capability has no owning component"
    # evidence points at the decorator line with a snippet
    assert cap["evidence"] and cap["evidence"][0]["file"].endswith("server.py")
    assert cap["evidence"][0]["line"]
    # defining symbol resolved to the decorated function (rides in detail_json)
    assert cap["detail"]["symbol"].endswith("read_user")


def test_capabilities_index_and_component_key_in_arch(tmp_path):
    (tmp_path / "server.py").write_text(_FASTAPI)
    store = FactStore(":memory:")
    extract_repo(str(tmp_path), store)
    _, arch = derive_all(store, "svc")
    # flat top-level index present
    assert isinstance(arch["capabilities"], list) and arch["capabilities"]
    # the owning component carries the optional per-component key

    def find_caps(components):
        for c in components:
            if "capabilities" in c:
                return c["capabilities"]
            got = find_caps(c.get("children", []))
            if got:
                return got
        return None

    assert find_caps(arch["components"]), "no component carries a capabilities key"


# ---------------------------------------------------------------------------
# 6. Test linkage groundwork (LENS-DESIGN L2)
# ---------------------------------------------------------------------------

def test_test_linkage_records_route_reference(tmp_path):
    (tmp_path / "server.py").write_text(_FASTAPI)
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_users.py").write_text(
        "def test_read_user(client):\n"
        "    resp = client.get('/users/1')\n"
        "    assert resp.status_code == 200\n"
    )
    store = FactStore(":memory:")
    extract_repo(str(tmp_path), store)
    _, arch = derive_all(store, "svc")
    cap = next(c for c in store.capabilities() if c["kind"] == "api")
    links = cap["detail"].get("tests")
    assert links, "no test linkage recorded"
    assert links[0]["file"].endswith("test_users.py")
    assert links[0]["confidence"] == "inferred"


# ---------------------------------------------------------------------------
# 7. Backward compatibility: additive keys only, old datasets unaffected
# ---------------------------------------------------------------------------

def test_capabilities_are_additive_optional_keys(tmp_path):
    # A repo with no capability-bearing code emits no capabilities, and no
    # component carries the optional key: old datasets render unchanged.
    (tmp_path / "util.py").write_text("def add(a, b):\n    return a + b\n")
    store = FactStore(":memory:")
    extract_repo(str(tmp_path), store)
    _, arch = derive_all(store, "lib")
    assert arch["capabilities"] == []
    assert store.capabilities() == []

    def no_cap_key(components):
        for c in components:
            assert "capabilities" not in c, "empty component must not carry the key"
            no_cap_key(c.get("children", []))

    no_cap_key(arch["components"])


def test_projection_carries_capabilities_and_old_viewer_ignores(tmp_path):
    # The projected manifest/monolith carry capabilities as optional keys; a
    # consumer that does not know the key still reads every other field.
    from analyzer.project.pipeline import project_monolith

    (tmp_path / "server.py").write_text(_FASTAPI)
    store = FactStore(":memory:")
    extract_repo(str(tmp_path), store)
    _, arch = derive_all(store, "svc")
    out = tmp_path / "architecture.json"
    project_monolith(arch, out, store=store, generated_at="x", analyzer_version="v")
    doc = json.loads(out.read_text())
    assert "capabilities" in doc  # additive top-level key
    # every pre-existing key still present and readable
    for key in ("name", "components", "relationships", "stats", "files"):
        assert key in doc


# ---------------------------------------------------------------------------
# 8. Determinism (invariant I4)
# ---------------------------------------------------------------------------

def test_capability_emission_is_deterministic(tmp_path):
    (tmp_path / "server.py").write_text(_FASTAPI)
    (tmp_path / "cli.py").write_text(
        "import click\n@click.command('run')\n@click.option('--v')\ndef run():\n    pass\n"
    )
    (tmp_path / "tasks.py").write_text("@shared_task\ndef t(): pass\n")

    def caps_json():
        store = FactStore(":memory:")
        extract_repo(str(tmp_path), store)
        _, arch = derive_all(store, "svc")
        return json.dumps(arch["capabilities"], sort_keys=True, default=str)

    assert caps_json() == caps_json()
