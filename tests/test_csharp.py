"""C# parser coverage: parity snapshot (tree-sitter tier) plus tier-agnostic checks.

The parity snapshot freezes the engine's C# output on tests/fixtures/csharp the
same way test_engine_parity.py freezes the polyglot and multi fixtures. It is
pinned to the C# tree-sitter tier (the regex fallback legitimately emits fewer
members and different visibility), so it skips loudly in the regex-only CI lane.

The functional tests below run on BOTH tiers: they exercise symbol, import,
framework, endpoint, and symbol-reference extraction through the public APIs, so
the regex lane still verifies C# end to end.
"""

import copy
import json
import os
from pathlib import Path

import pytest

from analyzer.extract.frameworks import StringMask, extract_endpoints
from analyzer.extract.references import REFERENCE_LANGUAGES, extract_reference_signals
from analyzer.models import to_dict
from analyzer.parsers import PARSERS
from analyzer.scanner import ArchitectureScanner

FIXTURES = Path(__file__).parent / "fixtures"
SNAPSHOTS = FIXTURES / "parity"
CSHARP_FIXTURE = FIXTURES / "csharp"

# Pin the snapshot to the tree-sitter tier, matching test_engine_parity.py: the
# regex fallback emits different symbols, so a tree-sitter baseline is only
# meaningful when C# resolved to tree-sitter. `_ts_available` is the runtime
# truth; the regex baseline parser lacks the attribute, so getattr defaults False.
_TREE_SITTER_ACTIVE = getattr(PARSERS["csharp"], "_ts_available", False)
requires_tree_sitter_tier = pytest.mark.skipif(
    not _TREE_SITTER_ACTIVE,
    reason="C# parity snapshot is pinned to the tree-sitter tier; this "
    "environment resolved C# to the regex fallback",
)

_VOLATILE_KEYS = (
    "generated_at",
    "root_path",
    "analyzer_version",
    "changelog",
    "changelog_serial",
)


def _deep_sort(obj):
    if isinstance(obj, dict):
        return {k: _deep_sort(v) for k, v in obj.items()}
    if isinstance(obj, list):
        items = [_deep_sort(x) for x in obj]
        items.sort(key=lambda x: json.dumps(x, sort_keys=True, default=str))
        return items
    return obj


def _normalize(arch_dict: dict) -> dict:
    d = copy.deepcopy(arch_dict)
    for key in _VOLATILE_KEYS:
        d.pop(key, None)
    return _deep_sort(d)


def _canonical(d: dict) -> str:
    return json.dumps(d, sort_keys=True, indent=2, default=str) + "\n"


def _run_csharp() -> dict:
    return _normalize(to_dict(ArchitectureScanner(CSHARP_FIXTURE).scan()))


def _snapshot_path() -> Path:
    return SNAPSHOTS / "csharp.snapshot.json"


def _regen_requested() -> bool:
    return os.environ.get("SE_REGEN_PARITY") == "1"


@requires_tree_sitter_tier
def test_csharp_engine_matches_snapshot():
    produced = _canonical(_run_csharp())
    path = _snapshot_path()

    if _regen_requested():
        SNAPSHOTS.mkdir(parents=True, exist_ok=True)
        path.write_text(produced, encoding="utf-8")
        pytest.skip(f"regenerated parity snapshot {path.name}")

    assert path.exists(), (
        f"missing parity snapshot {path}; regenerate with "
        f"SE_REGEN_PARITY=1 python -m pytest {__file__}"
    )
    expected = path.read_text(encoding="utf-8")
    assert produced == expected, (
        "C# engine output drifted from the committed parity snapshot. If this "
        "change is intended, regenerate with SE_REGEN_PARITY=1 and review the diff."
    )


@requires_tree_sitter_tier
def test_csharp_engine_output_is_deterministic():
    assert _canonical(_run_csharp()) == _canonical(_run_csharp())


@requires_tree_sitter_tier
def test_csharp_guard_detects_a_perturbed_snapshot():
    committed = _snapshot_path().read_text(encoding="utf-8")
    assert _canonical(_run_csharp()) == committed
    perturbed = _run_csharp()
    assert perturbed["symbols"], "fixture must have symbols to perturb"
    perturbed["symbols"][0]["name"] = perturbed["symbols"][0]["name"] + "_PERTURBED"
    assert _canonical(perturbed) != committed


def test_csharp_snapshot_is_committed_and_nonempty():
    path = _snapshot_path()
    assert path.exists(), f"C# parity snapshot {path} is not committed"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["components"], "C# snapshot has no components"
    assert data["files"], "C# snapshot has no files"
    assert data["symbols"], "C# snapshot has no symbols"


# --- Tier-agnostic functional tests (run on both CI lanes) ------------------

_SAMPLE = '''using System;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace Demo.Api;

/// <summary>User service.</summary>
public interface IUserService
{
    User Find(int id);
}

public class UserService : IUserService
{
    private readonly AppDbContext _db;

    public UserService(AppDbContext db)
    {
        _db = db;
    }

    public User Find(int id)
    {
        return new User();
    }

    public string Name { get; set; }
}

public record User(int Id, string Name);

public enum Role
{
    Admin,
    Guest
}

public struct Point
{
    public int X;
    public int Y;
}
'''


def _kinds(symbols):
    return {(s.name, s.kind) for s in symbols}


def test_csharp_extracts_types_and_members():
    syms = PARSERS["csharp"].extract_symbols(_SAMPLE, "Svc.cs")
    kinds = _kinds(syms)
    assert ("IUserService", "interface") in kinds
    assert ("UserService", "class") in kinds
    assert ("User", "record") in kinds
    assert ("Role", "enum") in kinds
    assert ("Point", "struct") in kinds


def test_csharp_extracts_using_imports():
    imports = PARSERS["csharp"].extract_imports(_SAMPLE)
    assert "System" in imports
    assert "Microsoft.AspNetCore.Mvc" in imports
    assert "Microsoft.EntityFrameworkCore" in imports


def test_csharp_detects_frameworks():
    parser = PARSERS["csharp"]
    assert parser.detect_framework("using Microsoft.AspNetCore.Mvc;") == "ASP.NET Core"
    assert parser.detect_framework("using Microsoft.EntityFrameworkCore;") == "EF Core"
    assert parser.detect_framework("using System;\nnamespace A;") == ".NET"
    assert parser.detect_framework("int x = 1;") is None


def test_csharp_endpoint_signals():
    src = (
        "using Microsoft.AspNetCore.Builder;\n"
        "var app = WebApplication.CreateBuilder().Build();\n"
        'app.MapGet("/health", () => "ok");\n'
        'app.MapPost("/users", () => {});\n'
    )
    endpoints = extract_endpoints(src, "csharp")
    got = {(v["method"], v["path"]) for v, _ in endpoints}
    assert ("GET", "/health") in got
    assert ("POST", "/users") in got
    assert all(v["framework"] == "aspnetcore" for v, _ in endpoints)


def test_csharp_is_a_reference_language():
    assert "csharp" in REFERENCE_LANGUAGES
    src = (
        "namespace A;\n"
        "public class Widget : BaseWidget\n"
        "{\n"
        "    public void Build() { var w = new Gadget(); }\n"
        "}\n"
    )
    mask = StringMask(src, "csharp")
    names = {r.value["name"] for r in extract_reference_signals(src, "csharp", mask)}
    assert "BaseWidget" in names   # base type
    assert "Gadget" in names       # constructor call
