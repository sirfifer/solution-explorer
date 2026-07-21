"""Unit tests for analyzer/contracts.py (card R1 backbone).

Covers the three pieces of the honest-gap backbone in isolation: the
deterministic ProducerGap record and its exception constructor, the require /
PostconditionError shape-and-completeness helper, and the Isolator driver
bulkhead (healthy pass-through, exception capture, and the BaseException
boundary). The real-pass integration proof lives in test_derive_isolation.py.
"""

from __future__ import annotations

import pytest

from analyzer import contracts


def test_producer_gap_fields_and_serialization():
    gap = contracts.ProducerGap(producer="derive.x", stage="derive", reason="boom")
    d = contracts.gap_to_dict(gap)
    assert d == {
        "producer": "derive.x",
        "stage": "derive",
        "status": "failed",  # default disposition mirrors the coverage ledger
        "reason": "boom",
    }


def test_gap_from_exception_is_deterministic_and_traceback_free():
    exc = ValueError("something specific broke")
    g1 = contracts.gap_from_exception("derive.rel", "derive", exc)
    g2 = contracts.gap_from_exception("derive.rel", "derive", exc)
    assert contracts.gap_to_dict(g1) == contracts.gap_to_dict(g2)  # deterministic
    assert g1.reason == "ValueError: something specific broke"
    # No traceback, no file paths, no line numbers in the reason.
    assert "line" not in g1.reason.lower()
    assert "/" not in g1.reason


def test_gap_reason_is_single_line_and_capped():
    exc = RuntimeError("first\nsecond\nthird")
    g = contracts.gap_from_exception("p", "s", exc)
    assert "\n" not in g.reason  # collapsed to one line
    long = RuntimeError("x" * 2000)
    gl = contracts.gap_from_exception("p", "s", long)
    assert len(gl.reason) < 600
    assert "truncated" in gl.reason  # announced, never a silent cut


def test_gap_reason_scrubs_memory_addresses_for_determinism():
    # A default object repr embeds a heap address that varies run to run. The
    # reason must collapse it so two distinct instances yield the SAME gap, or a
    # degraded run would drift under the golden gate.
    import re

    class Widget:
        pass

    r1 = contracts.gap_from_exception("p", "s", RuntimeError(f"bad {Widget()!r}")).reason
    r2 = contracts.gap_from_exception("p", "s", RuntimeError(f"bad {Widget()!r}")).reason
    assert "0x..." in r1
    assert r1 == r2  # deterministic across distinct heap addresses
    assert not re.search(r"0x[0-9a-fA-F]{4,}", r1)  # no raw address survives


def test_require_passes_and_raises():
    contracts.require(True, "must not raise")
    with pytest.raises(contracts.PostconditionError, match="missing thing"):
        contracts.require(False, "missing thing")


def test_isolator_healthy_passthrough_records_no_gap():
    gaps: list = []
    iso = contracts.Isolator("derive", gaps)
    result = iso.run("derive.ok", lambda x: x * 2, 21)
    assert result == 42
    assert gaps == []


def test_isolator_captures_exception_and_returns_default():
    gaps: list = []
    iso = contracts.Isolator("derive", gaps)

    def boom():
        raise RuntimeError("pass exploded")

    result = iso.run("derive.boom", boom, default="fallback")
    assert result == "fallback"
    assert len(gaps) == 1
    d = contracts.gap_to_dict(gaps[0])
    assert d["producer"] == "derive.boom"
    assert d["stage"] == "derive"
    assert d["status"] == "failed"
    assert d["reason"] == "RuntimeError: pass exploded"


def test_isolator_captures_postcondition_failure_as_gap():
    gaps: list = []
    iso = contracts.Isolator("derive", gaps)

    def bad_output():
        contracts.require(False, "output missing a required section")

    iso.run("derive.contract", bad_output)
    assert len(gaps) == 1
    assert "output missing a required section" in contracts.gap_to_dict(gaps[0])["reason"]


def test_isolator_default_factory_is_lazy_and_used_only_on_failure():
    gaps: list = []
    iso = contracts.Isolator("derive", gaps)
    calls: list = []

    def factory():
        calls.append(1)
        return "skeleton"

    # Success: the factory is never built (a healthy run pays nothing).
    assert iso.run("ok", lambda: "real", default_factory=factory) == "real"
    assert calls == []
    # Failure: the factory value is returned and a gap is recorded.
    assert iso.run("bad", lambda: (_ for _ in ()).throw(ValueError("x")),
                   default_factory=factory) == "skeleton"
    assert calls == [1]
    assert len(gaps) == 1


def test_isolator_does_not_swallow_base_exceptions():
    gaps: list = []
    iso = contracts.Isolator("derive", gaps)

    def interrupted():
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        iso.run("derive.interrupt", interrupted)
    assert gaps == []  # a user abort is never turned into an honest gap


def test_isolator_direct_gap():
    gaps: list = []
    iso = contracts.Isolator("emit", gaps)
    iso.gap("emit.sbom", "no manifest resolver available")
    assert contracts.gap_to_dict(gaps[0]) == {
        "producer": "emit.sbom",
        "stage": "emit",
        "status": "failed",
        "reason": "no manifest resolver available",
    }


def test_finalize_gaps_is_sorted_and_serialized():
    gaps = [
        contracts.ProducerGap(producer="derive.z", stage="derive", reason="z"),
        contracts.ProducerGap(producer="derive.a", stage="derive", reason="a"),
    ]
    out = contracts.finalize_gaps(gaps)
    assert [g["producer"] for g in out] == ["derive.a", "derive.z"]  # sorted
    assert all(isinstance(g, dict) for g in out)


def test_finalize_gaps_sort_key_includes_stage():
    # Same producer, different stage: stage breaks the tie so the order is total
    # and independent of insertion order (matters once multi-stage gaps are
    # finalized together in later R1 waves).
    gaps = [
        contracts.ProducerGap(producer="p", stage="emit", reason="r"),
        contracts.ProducerGap(producer="p", stage="derive", reason="r"),
    ]
    out = contracts.finalize_gaps(gaps)
    assert [g["stage"] for g in out] == ["derive", "emit"]


def test_unresolved_reference_count():
    assert contracts.unresolved_reference_count({"a", "b"}, ["a", "b", "c", "c"]) == 2
    assert contracts.unresolved_reference_count({"a", "b"}, ["a", "b"]) == 0
