#!/usr/bin/env python3
"""Materialize GUI regression datasets and assemble static serve roots.

Design authority: docs/testing/GUI-REGRESSION-STRATEGY.md. The dataset registry
is viewer/tests/gui/datasets.yaml; this tool executes it. Nothing here touches
the analyzer engine: it runs the same commands a person would (analyze.py, the
AI-enhancement merge) and applies the two documented degradation transforms.

Subcommands:
  list                  Print dataset keys and descriptions.
  generate <key>        Run the dataset's generate commands from the repo root
                        into viewer/tests/gui/.datasets/<key>/ (the staging
                        payload, laid out exactly as it overlays a serve root).
  strip-ai <file>       Transform: remove every ai_enhance key (architecture,
                        component, relationship level) from a monolith
                        projection, in place.
  inject-gaps <file>    Transform: add a deterministic, honestly-labeled
                        producer-gap record (R1 `gaps` key) to a monolith
                        projection, in place.
  write-malformed <file>  Write a deterministic syntactically-invalid
                        architecture.json (V12: the viewer must degrade to a
                        legible message, never a blank page).
  assemble <key>        Copy viewer/dist to viewer/tests/gui/.serve/<key>/,
                        remove the architecture data baked in from
                        viewer/public, and overlay the staged payload. Prints
                        the serve command.

The serve command for an assembled root:
  python3 -m http.server <port> --directory viewer/tests/gui/.serve/<key>
"""

from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GUI_DIR = REPO_ROOT / "viewer" / "tests" / "gui"
DATASETS_YAML = GUI_DIR / "datasets.yaml"
STAGING_ROOT = GUI_DIR / ".datasets"
SERVE_ROOT = GUI_DIR / ".serve"
DIST_DIR = REPO_ROOT / "viewer" / "dist"

# Data files vite bakes into dist from viewer/public that belong to a
# projection, not to the app. Removed from every assembled serve root so the
# dataset payload fully controls what the app loads (including which probes
# 404, which the datasets.yaml allowlists depend on).
BAKED_DATA = ["architecture.json", "architecture", "ai.json", "llms.txt"]

# The injected honest-gap record for the `gaps` dataset. Deterministic and
# self-describing: the reason text says it is a fixture transform, because the
# no-theater rule applies to test data too. Shape matches analyzer/contracts.py
# ProducerGap and is kept in the sort order sort_gaps would emit
# (producer, status, reason).
INJECTED_GAPS = [
    {
        "producer": "derive.capabilities",
        "stage": "derive",
        "status": "failed",
        "reason": "GUI-fixture: representative gap injected by scripts/gui-datasets.py inject-gaps, not a real analyzer failure",
    },
    {
        "producer": "project.emitters.activity",
        "stage": "project",
        "status": "failed",
        "reason": "GUI-fixture: representative gap injected by scripts/gui-datasets.py inject-gaps, not a real analyzer failure",
    },
]


def _load_yaml(path: Path) -> dict:
    try:
        import yaml
    except ImportError:
        sys.exit(
            "PyYAML is required to read datasets.yaml. Install it with "
            "`pip install pyyaml` (it is part of the repo's [dev] extras)."
        )
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except yaml.YAMLError as exc:
        sys.exit(f"Unreadable YAML in {path}: {exc}")


def _load_projection(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        sys.exit(f"Cannot read {path} as JSON: {exc}")


def _dataset(key: str) -> dict:
    registry = _load_yaml(DATASETS_YAML)
    datasets = registry.get("datasets") or {}
    if key not in datasets:
        sys.exit(
            f"Unknown dataset '{key}'. Known keys: {', '.join(sorted(datasets))}"
        )
    return datasets[key]


def cmd_list() -> int:
    registry = _load_yaml(DATASETS_YAML)
    for key, spec in (registry.get("datasets") or {}).items():
        desc = " ".join((spec.get("description") or "").split())
        print(f"{key}: {desc}")
    return 0


def cmd_generate(key: str) -> int:
    spec = _dataset(key)
    staging = STAGING_ROOT / key
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    for template in spec.get("generate") or []:
        command = template.replace("{staging}", shlex.quote(str(staging)))
        print(f"[gui-datasets] {command}")
        result = subprocess.run(command, shell=True, cwd=REPO_ROOT)
        if result.returncode != 0:
            sys.exit(
                f"Generate step failed (exit {result.returncode}) for dataset "
                f"'{key}': {command}"
            )
    print(f"[gui-datasets] staged: {staging}")
    return 0


def _strip_ai(node: object) -> int:
    """Recursively remove ai_enhance keys; returns the number removed."""
    removed = 0
    if isinstance(node, dict):
        if "ai_enhance" in node:
            del node["ai_enhance"]
            removed += 1
        for value in node.values():
            removed += _strip_ai(value)
    elif isinstance(node, list):
        for item in node:
            removed += _strip_ai(item)
    return removed


def cmd_strip_ai(path: Path) -> int:
    data = _load_projection(path)
    removed = _strip_ai(data)
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    if removed == 0:
        # A no-op strip means the input was never enriched; the "unenriched"
        # dataset would silently equal dogfood-without-merge. Loud, not fatal.
        print(
            "[gui-datasets] WARNING: strip-ai removed nothing; input carried "
            "no ai_enhance keys"
        )
    else:
        print(f"[gui-datasets] strip-ai removed {removed} ai_enhance keys from {path}")
    return 0


def cmd_inject_gaps(path: Path) -> int:
    data = _load_projection(path)
    if not isinstance(data, dict) or "components" not in data:
        sys.exit(f"{path} does not look like a monolith projection")
    data["gaps"] = INJECTED_GAPS
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    print(f"[gui-datasets] injected {len(INJECTED_GAPS)} gap records into {path}")
    return 0


# Deterministic invalid JSON for the malformed dataset (V12). Truncated mid
# object so JSON.parse fails with a stable message shape.
MALFORMED_PAYLOAD = '{"name": "malformed-fixture", "components": [ {"id": "x", '


def cmd_write_malformed(path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(MALFORMED_PAYLOAD, encoding="utf-8")
    print(f"[gui-datasets] wrote deterministic malformed JSON to {path}")
    return 0


def cmd_assemble(key: str, dist: Path) -> int:
    _dataset(key)  # validates the key
    staging = STAGING_ROOT / key
    if not staging.is_dir() or not any(staging.iterdir()):
        sys.exit(
            f"No staged payload for '{key}'. Run: python3 scripts/gui-datasets.py generate {key}"
        )
    if not (dist / "index.html").is_file():
        sys.exit(
            f"No built viewer at {dist}. Run: cd viewer && npm ci && npm run build"
        )
    serve = SERVE_ROOT / key
    if serve.exists():
        shutil.rmtree(serve)
    shutil.copytree(dist, serve)
    for name in BAKED_DATA:
        target = serve / name
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
    shutil.copytree(staging, serve, dirs_exist_ok=True)
    print(f"[gui-datasets] assembled: {serve}")
    print(
        "[gui-datasets] serve with: "
        f"python3 -m http.server <port> --directory {serve.relative_to(REPO_ROOT)}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    p_gen = sub.add_parser("generate")
    p_gen.add_argument("key")
    p_strip = sub.add_parser("strip-ai")
    p_strip.add_argument("file", type=Path)
    p_gaps = sub.add_parser("inject-gaps")
    p_gaps.add_argument("file", type=Path)
    p_mal = sub.add_parser("write-malformed")
    p_mal.add_argument("file", type=Path)
    p_asm = sub.add_parser("assemble")
    p_asm.add_argument("key")
    p_asm.add_argument("--dist", type=Path, default=DIST_DIR)
    args = parser.parse_args(argv)

    if args.command == "list":
        return cmd_list()
    if args.command == "generate":
        return cmd_generate(args.key)
    if args.command == "strip-ai":
        return cmd_strip_ai(args.file)
    if args.command == "inject-gaps":
        return cmd_inject_gaps(args.file)
    if args.command == "write-malformed":
        return cmd_write_malformed(args.file)
    if args.command == "assemble":
        return cmd_assemble(args.key, args.dist)
    return 2


if __name__ == "__main__":
    sys.exit(main())
