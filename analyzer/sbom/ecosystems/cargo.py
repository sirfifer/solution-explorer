"""Rust / Cargo ecosystem: Cargo.toml plus Cargo.lock.

Direct dependencies come from Cargo.toml's dependency tables (a bare ``"1.2.3"``
is a caret range in Cargo, so pin classification uses the cargo rules). Cargo.lock
lists every resolved package including the transitive closure. ``rust-version``
from ``[package]`` surfaces as a target.
"""

from __future__ import annotations

from pathlib import Path

from ..models import (
    PIN_EXACT,
    SCOPE_DIRECT,
    SCOPE_TRANSITIVE,
    Dependency,
    EcosystemResult,
    ParseWarning,
    Target,
)
from ..purl import build_purl, classify_pin
from . import _toml
from ._common import find_line, join_rel, read_text

ECOSYSTEM = "cargo"

_DEP_TABLES = ("dependencies", "dev-dependencies", "build-dependencies")


def is_anchored(filenames: set[str]) -> bool:
    return "Cargo.toml" in filenames


def collect(root: Path, dirpath: str, filenames: set[str]) -> EcosystemResult:
    result = EcosystemResult(ecosystem=ECOSYSTEM)
    base = root / dirpath if dirpath else root
    rel = join_rel(dirpath, "Cargo.toml")
    result.manifests.append(rel)
    try:
        text = read_text(base / "Cargo.toml")
    except OSError as exc:
        result.warnings.append(ParseWarning(ECOSYSTEM, rel, f"unreadable: {exc}"))
        return result
    try:
        data = _toml.load(text)
    except _toml.TomlUnavailable as exc:
        result.warnings.append(ParseWarning(ECOSYSTEM, rel, str(exc)))
        return result
    except _toml.TomlError as exc:
        result.warnings.append(ParseWarning(ECOSYSTEM, rel, f"invalid TOML: {exc}"))
        return result

    lines = text.splitlines()
    package = data.get("package") if isinstance(data.get("package"), dict) else {}
    rust_version = package.get("rust-version")
    if isinstance(rust_version, str) and rust_version.strip():
        result.targets.append(Target(
            ecosystem=ECOSYSTEM, kind="rust", label="Rust toolchain",
            constraint=rust_version.strip(), evidence_file=rel,
            evidence_line=find_line(lines, "rust-version"),
        ))

    direct: dict[str, str | None] = {}
    for table in _DEP_TABLES:
        block = data.get(table)
        if not isinstance(block, dict):
            continue
        for name, value in block.items():
            if name in direct:
                continue
            direct[name] = _constraint_of(value)

    lock_rel, resolved = _read_lock(base, dirpath, filenames, result)

    for name in sorted(direct):
        constraint = direct[name]
        version = resolved.get(name)
        result.dependencies.append(Dependency(
            ecosystem=ECOSYSTEM, name=name, declared=constraint, version=version,
            pin_status=classify_pin(ECOSYSTEM, constraint), scope=SCOPE_DIRECT,
            purl=build_purl(ECOSYSTEM, name, version), evidence_file=rel,
            evidence_line=find_line(lines, name),
        ))

    if lock_rel is not None:
        for name in sorted(resolved):
            if name in direct:
                continue
            version = resolved[name]
            result.dependencies.append(Dependency(
                ecosystem=ECOSYSTEM, name=name, declared=None, version=version,
                pin_status=PIN_EXACT if version else classify_pin(ECOSYSTEM, None),
                scope=SCOPE_TRANSITIVE,
                purl=build_purl(ECOSYSTEM, name, version), evidence_file=lock_rel,
            ))

    return result


def _constraint_of(value) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        version = value.get("version")
        if isinstance(version, str):
            return version
        # A git/path dependency has no version range.
        return value.get("git") or value.get("path") or None
    return None


def _read_lock(base: Path, dirpath: str, filenames: set[str], result: EcosystemResult):
    if "Cargo.lock" not in filenames:
        return None, {}
    rel = join_rel(dirpath, "Cargo.lock")
    result.manifests.append(rel)
    try:
        text = read_text(base / "Cargo.lock")
    except OSError as exc:
        result.warnings.append(ParseWarning(ECOSYSTEM, rel, f"unreadable: {exc}"))
        return rel, {}
    try:
        data = _toml.load(text)
    except _toml.TomlUnavailable as exc:
        result.warnings.append(ParseWarning(ECOSYSTEM, rel, str(exc)))
        return rel, {}
    except _toml.TomlError as exc:
        result.warnings.append(ParseWarning(ECOSYSTEM, rel, f"invalid TOML: {exc}"))
        return rel, {}
    resolved: dict[str, str] = {}
    for pkg in data.get("package", []) or []:
        if not isinstance(pkg, dict):
            continue
        name = pkg.get("name")
        version = pkg.get("version")
        if isinstance(name, str) and isinstance(version, str) and name not in resolved:
            resolved[name] = version
    return rel, resolved
