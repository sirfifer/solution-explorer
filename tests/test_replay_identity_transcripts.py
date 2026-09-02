from __future__ import annotations

import json

import pytest


def _module():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts" / "replay-identity-transcripts.py"
    spec = importlib.util.spec_from_file_location("replay_identity_transcripts", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _event(components: dict) -> str:
    return json.dumps({
        "type": "assistant",
        "message": {"content": [{
            "type": "text", "text": json.dumps({"components": components}),
        }]},
    })


def test_loader_uses_the_last_complete_envelope_and_merges_transcripts(tmp_path):
    module = _module()
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    first.write_text(_event({"a": {"fields": {}}}) + "\n")
    second.write_text(_event({"b": {"fields": {}}}) + "\n")

    assert set(module._load_components([first, second])) == {"a", "b"}


def test_loader_rejects_conflicting_paid_answers(tmp_path):
    module = _module()
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    first.write_text(_event({"a": {"fields": {"name": 1}}}) + "\n")
    second.write_text(_event({"a": {"fields": {"name": 2}}}) + "\n")

    with pytest.raises(ValueError, match="conflicting paid answers"):
        module._load_components([first, second])
