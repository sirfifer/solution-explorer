"""Tests for the S2 identity-verification gate (verify_identity pass).

Owner ruling 2026-08-17: a published identity is resolved or flagged, never a
guess. Confirmations stamp a verdict row; corrections apply at projection with
an ``identity_corrections`` provenance marker; uncertains become honest-gap
entries. The Claude invocation is mocked so these tests are hermetic.
"""

from __future__ import annotations

import json
import re

from analyzer.derive import derive_all
from analyzer.enrich import apply_verdict_overlay
from analyzer.enrich.engine import InvokeResult
from analyzer.enrich.passes import VerifyConfig, verify_identity
from analyzer.extract import extract_repo
from analyzer.store import FactStore

FIXED_CLOCK = lambda: "2026-08-17T00:00:00+00:00"  # noqa: E731

_AIOHTTP = (
    "from aiohttp import web\n"
    "app = web.Application()\n"
    "async def health(request):\n"
    "    return web.json_response({})\n"
    "app.router.add_get('/api/health', health)\n"
    "web.run_app(app, port=8766)\n"
)


def _repo(tmp_path):
    repo = tmp_path / "repo"
    server = repo / "server"
    server.mkdir(parents=True)
    (server / "pyproject.toml").write_text('[project]\nname = "server"\n')
    (server / "app.py").write_text(_AIOHTTP)
    return repo


def _build(tmp_path):
    repo = _repo(tmp_path)
    db = tmp_path / "facts.db"
    store = FactStore(str(db))
    extract_repo(repo, store)
    derive_all(store, "repo", root_path=str(repo))
    store.commit()
    store.close()
    return repo, db


def _fields(**overrides):
    fields = {f: {"status": "confirmed"} for f in ("name", "type", "framework", "port")}
    fields.update(overrides)
    return fields


def _ids_in(prompt):
    """The component ids a batched identity prompt is asking about."""
    return re.findall(r'"id":\s*"([^"]+)"', prompt)


def _batch(prompt, answer):
    """Give every component in the batch the same answer."""
    return json.dumps({"components": {cid: answer for cid in _ids_in(prompt)}})


def _mock(fields, prose_issues=None):
    """A model that answers every component in the batch it was handed.

    Identity verification is batched: one call carries several components and
    returns a verdict per id. Per-component calls cost $8.54 across 111 calls
    on one real run for answers averaging 292 tokens.
    """
    def invoker(prompt):
        return InvokeResult(
            ok=True,
            text=_batch(prompt, {"fields": fields, "prose_issues": prose_issues or []}),
            cost_usd=0.01,
        )
    return invoker


def _overlaid_arch(repo, db):
    store = FactStore(str(db))
    _, arch = derive_all(store, "repo", root_path=str(repo))
    apply_verdict_overlay(arch, store)
    store.close()
    return arch


def _find(arch, comp_id):
    def walk(cs):
        for c in cs:
            yield c
            yield from walk(c.get("children", []))
    return next(c for c in walk(arch["components"]) if c["id"] == comp_id)


def test_confirmed_identity_stamps_a_row_and_changes_nothing(tmp_path):
    repo, db = _build(tmp_path)
    cfg = VerifyConfig(store_path=db, root=repo)
    report = verify_identity(cfg, invoker=_mock(_fields()), clock=FIXED_CLOCK)
    assert report.ok and report.done >= 1
    assert all(o.verdict == "confirmed" for o in report.outcomes)

    store = FactStore(str(db))
    rows = [r for r in store.enrichment() if r["target_kind"] == "identity-verdict"]
    assert rows and rows[0]["derived_from_hash"] is not None
    store.close()

    arch = _overlaid_arch(repo, db)
    server = _find(arch, "server")
    assert server["type"] == "api-server"
    assert "identity_corrections" not in server
    assert not arch.get("gaps")


def test_correction_applies_at_projection_with_provenance(tmp_path):
    repo, db = _build(tmp_path)
    cfg = VerifyConfig(store_path=db, root=repo)
    corrected = _fields(type={
        "status": "corrected", "value": "module",
        "reason": "The routes are demo scaffolding, not a served API.",
        "evidence": {"file": "server/app.py", "line": 5},
    })
    report = verify_identity(cfg, invoker=_mock(corrected), clock=FIXED_CLOCK)
    assert report.ok
    assert any(o.verdict == "corrected" for o in report.outcomes)

    arch = _overlaid_arch(repo, db)
    server = _find(arch, "server")
    assert server["type"] == "module"
    marker = server["identity_corrections"]["type"]
    assert marker["from"] == "api-server" and marker["to"] == "module"
    assert marker["evidence"]["file"] == "server/app.py"


def test_optional_identity_field_can_be_corrected_to_explicit_null(tmp_path):
    """A verifier can remove a false framework label without inventing one."""
    repo, db = _build(tmp_path)
    cfg = VerifyConfig(store_path=db, root=repo)
    corrected = _fields(framework={
        "status": "corrected", "value": None,
        "reason": "The manifest contains no application framework.",
        "evidence": {"file": "server/pyproject.toml", "line": 1},
    })

    report = verify_identity(cfg, invoker=_mock(corrected), clock=FIXED_CLOCK)

    assert report.ok
    arch = _overlaid_arch(repo, db)
    server = _find(arch, "server")
    assert server["framework"] is None
    marker = server["identity_corrections"]["framework"]
    assert marker["to"] is None


def test_optional_absence_prose_sentinel_is_canonicalized_to_null(tmp_path):
    repo, db = _build(tmp_path)
    cfg = VerifyConfig(store_path=db, root=repo)
    corrected = _fields(framework={
        "status": "corrected", "value": "none detected",
        "reason": "The manifest contains no application framework.",
        "evidence": {"file": "server/pyproject.toml", "line": 1},
    })

    report = verify_identity(cfg, invoker=_mock(corrected), clock=FIXED_CLOCK)

    assert report.ok
    server = _find(_overlaid_arch(repo, db), "server")
    assert server["framework"] is None
    assert server["identity_corrections"]["framework"]["to"] is None


def test_required_identity_field_cannot_be_corrected_to_null(tmp_path):
    repo, db = _build(tmp_path)
    cfg = VerifyConfig(store_path=db, root=repo)
    corrected = _fields(type={
        "status": "corrected", "value": None,
        "reason": "The classification is wrong.",
        "evidence": {"file": "server/pyproject.toml", "line": 1},
    })

    report = verify_identity(cfg, invoker=_mock(corrected), clock=FIXED_CLOCK)

    assert not report.ok


def test_uncertain_identity_lands_in_the_honest_gaps_record(tmp_path):
    repo, db = _build(tmp_path)
    cfg = VerifyConfig(store_path=db, root=repo)
    uncertain = _fields(port={
        "status": "uncertain",
        "reason": "The port literal appears only in a sample invocation.",
    })
    verify_identity(cfg, invoker=_mock(uncertain), clock=FIXED_CLOCK)

    arch = _overlaid_arch(repo, db)
    gaps = arch.get("gaps") or []
    gap = next(g for g in gaps if g["producer"] == "enrich.verify-identity")
    assert gap["stage"] == "server:port"
    assert gap["status"] == "unresolved"
    assert "sample invocation" in gap["reason"]


def test_invalid_payload_writes_no_row(tmp_path):
    repo, db = _build(tmp_path)
    cfg = VerifyConfig(store_path=db, root=repo)

    def bad_invoker(prompt):
        # corrected without value/evidence: must fail validation (both tries).
        return InvokeResult(
            ok=True,
            text=_batch(prompt, {"fields": _fields(type={"status": "corrected"})}),
            cost_usd=0.01,
        )

    report = verify_identity(cfg, invoker=bad_invoker, clock=FIXED_CLOCK)
    assert not report.ok
    store = FactStore(str(db))
    rows = [r for r in store.enrichment() if r["target_kind"] == "identity-verdict"]
    assert rows == []
    store.close()


def test_stale_correction_is_not_applied(tmp_path):
    repo, db = _build(tmp_path)
    cfg = VerifyConfig(store_path=db, root=repo)
    corrected = _fields(type={
        "status": "corrected", "value": "module",
        "reason": "Demo scaffolding.",
        "evidence": {"file": "server/app.py"},
    })
    verify_identity(cfg, invoker=_mock(corrected), clock=FIXED_CLOCK)

    # The component's content changes after the verdict: the verdict is stale
    # and the deterministic value must stand until the next verification run.
    (repo / "server" / "app.py").write_text(_AIOHTTP + "\n# changed\n")
    store = FactStore(str(db))
    extract_repo(repo, store)
    derive_all(store, "repo", root_path=str(repo))
    store.commit()
    store.close()

    arch = _overlaid_arch(repo, db)
    server = _find(arch, "server")
    assert server["type"] == "api-server"
    assert "identity_corrections" not in server


def test_prose_issues_ride_the_verdict_row(tmp_path):
    repo, db = _build(tmp_path)
    cfg = VerifyConfig(store_path=db, root=repo)
    verify_identity(
        cfg,
        invoker=_mock(_fields(), prose_issues=[
            {"claim": "69+ HTTP endpoints", "fact": "265 endpoints detected"},
        ]),
        clock=FIXED_CLOCK,
    )
    store = FactStore(str(db))
    row = next(r for r in store.enrichment() if r["target_kind"] == "identity-verdict")
    assert row["payload"]["prose_issues"][0]["claim"] == "69+ HTTP endpoints"
    store.close()


def test_update_mode_skips_fresh_verdicts(tmp_path):
    repo, db = _build(tmp_path)
    cfg = VerifyConfig(store_path=db, root=repo)
    first = verify_identity(cfg, invoker=_mock(_fields()), clock=FIXED_CLOCK)
    assert first.done >= 1

    calls = {"n": 0}

    def counting(prompt):
        calls["n"] += 1
        return InvokeResult(ok=True, text=_batch(prompt, {"fields": _fields()}), cost_usd=0.01)

    again = verify_identity(
        VerifyConfig(store_path=db, root=repo, update=True),
        invoker=counting, clock=FIXED_CLOCK,
    )
    assert again.target_count == 0 and calls["n"] == 0
