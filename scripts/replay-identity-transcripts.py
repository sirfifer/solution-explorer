#!/usr/bin/env python3
"""Replay paid identity-verification answers that failed local validation.

This is intentionally narrower than generic transcript recovery: it accepts
only complete ``{"components": ...}`` identity envelopes, then hands them back
through the production ``verify_identity`` validator and provenance stamper.
It never invokes a provider and never writes an answer that the current
identity contract rejects.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from analyzer.enrich.engine import InvokeResult, _parse_json_object
from analyzer.enrich.passes import VerifyConfig, verify_identity


def _load_components(paths: list[Path]) -> dict[str, dict]:
    merged: dict[str, dict] = {}
    for path in paths:
        envelopes: list[dict] = []
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSONL: {exc}") from exc
            if event.get("type") != "assistant":
                continue
            for block in (event.get("message") or {}).get("content") or []:
                if not isinstance(block, dict) or block.get("type") != "text":
                    continue
                obj = _parse_json_object(
                    str(block.get("text") or ""), expect_keys=("components",)
                )
                if isinstance(obj, dict) and isinstance(obj.get("components"), dict):
                    envelopes.append(obj)
        if not envelopes:
            raise ValueError(f"{path}: no identity components envelope found")
        components = envelopes[-1]["components"]
        for component_id, answer in components.items():
            component_id = str(component_id)
            if component_id in merged and merged[component_id] != answer:
                raise ValueError(
                    f"{path}: conflicting paid answers for component {component_id!r}"
                )
            merged[component_id] = answer
    return merged


class _TranscriptInvoker:
    def __init__(self, answers: dict[str, dict]) -> None:
        self.answers = answers
        self.requested: set[str] = set()

    def __call__(self, prompt: str) -> InvokeResult:
        component_ids = re.findall(r'"id":\s*"([^"]+)"', prompt)
        missing = [value for value in component_ids if value not in self.answers]
        if missing:
            return InvokeResult(
                ok=False,
                text="",
                error="paid transcript has no answer for: " + ", ".join(missing),
                cost_usd=0.0,
            )
        self.requested.update(component_ids)
        return InvokeResult(
            ok=True,
            text=json.dumps({
                "components": {
                    component_id: self.answers[component_id]
                    for component_id in component_ids
                }
            }),
            cost_usd=0.0,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("transcripts", nargs="+", type=Path)
    args = parser.parse_args()

    answers = _load_components(args.transcripts)
    invoker = _TranscriptInvoker(answers)
    report = verify_identity(
        VerifyConfig(store_path=args.store, root=args.root, update=True),
        invoker=invoker,
    )
    summary = {
        "provider_calls": 0,
        "transcripts": [str(path) for path in args.transcripts],
        "paid_answers_available": len(answers),
        "answers_replayed": len(invoker.requested),
        "rows_stamped": report.done,
        "failed": report.failed,
        "verdicts": report.tally(),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if report.ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
