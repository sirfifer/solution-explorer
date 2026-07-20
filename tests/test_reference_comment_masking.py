"""C-family comment-content reference fabrication (integration-phase-a review).

The C-family reference extractors (csharp, java, cpp in
analyzer/extract/references.py) scan a file for type-like names. Before this fix
:func:`analyzer.extract.frameworks.compute_string_spans` masked string literals
and, for hash-comment languages, ``#`` line comments, but it did NOT mask ``//``
line comments or ``/* */`` block comments. So a type named only in comment prose
(the reviewer's case: a Java file importing ``PaymentGateway`` but naming it only
in ``// The PaymentGateway handles ...``) fabricated a real ``uses`` edge. The
Java bare-declaration rule is the worst, since "Capitalized lowercase" is
ordinary English.

The fix scopes C-style comment masking to the three NEW languages
(:data:`~analyzer.extract.frameworks.SLASH_COMMENT_LANGUAGES`). These tests lock
that in: for java, csharp, and cpp a name that appears ONLY in a ``//`` comment
or ONLY in a ``/* */`` block comment produces no reference signal, while the same
name in real code still does; an end-to-end two-module fixture whose only mention
of an imported type is a comment draws NO ``uses`` edge; and swift/typescript
reference behavior is unchanged (their comments are deliberately not masked), so
the scoping is real and not an accident of the whole scanner changing.
"""

from __future__ import annotations

from pathlib import Path

from analyzer.derive import derive_all
from analyzer.extract import extract_repo
from analyzer.extract.frameworks import StringMask
from analyzer.extract.references import extract_reference_signals
from analyzer.store import FactStore


def _names(src: str, language: str) -> set[str]:
    mask = StringMask(src, language)
    return {s.value["name"] for s in extract_reference_signals(src, language, mask)}


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _derive(root: Path):
    store = FactStore(":memory:")
    extract_repo(str(root), store)
    return derive_all(store, root.name, root_path=str(root))


def _uses(arch, src_id: str, tgt_id: str):
    return [
        r for r in arch["relationships"]
        if r["type"] == "uses" and r["source"] == src_id and r["target"] == tgt_id
    ]


# ---------------------------------------------------------------------------
# Per-language: a name only in a comment is not a reference; in real code it is.
# The comment bodies contain code-shaped text so masking is genuinely exercised.
# ---------------------------------------------------------------------------

def test_java_line_comment_name_is_not_a_reference():
    commented = (
        "package a;\n"
        "public class Service {\n"
        "    // PaymentGateway gateway = new PaymentGateway();\n"
        "    void run() { return; }\n"
        "}\n"
    )
    assert "PaymentGateway" not in _names(commented, "java")

    real = (
        "package a;\n"
        "public class Service {\n"
        "    void run() { PaymentGateway gateway = null; }\n"
        "}\n"
    )
    assert "PaymentGateway" in _names(real, "java")


def test_java_block_comment_name_is_not_a_reference():
    commented = (
        "package a;\n"
        "public class Service {\n"
        "    /* new PaymentGateway(); PaymentGateway gateway; */\n"
        "    void run() { return; }\n"
        "}\n"
    )
    assert "PaymentGateway" not in _names(commented, "java")

    real = (
        "package a;\n"
        "public class Service {\n"
        "    void run() { var g = new PaymentGateway(); }\n"
        "}\n"
    )
    assert "PaymentGateway" in _names(real, "java")


def test_csharp_line_comment_name_is_not_a_reference():
    commented = (
        "namespace A;\n"
        "public class Service {\n"
        "    // var g = new PaymentGateway();\n"
        "    void Run() { }\n"
        "}\n"
    )
    assert "PaymentGateway" not in _names(commented, "csharp")

    real = (
        "namespace A;\n"
        "public class Service {\n"
        "    void Run() { var g = new PaymentGateway(); }\n"
        "}\n"
    )
    assert "PaymentGateway" in _names(real, "csharp")


def test_csharp_block_comment_name_is_not_a_reference():
    commented = (
        "namespace A;\n"
        "public class Service {\n"
        "    /* new PaymentGateway(); Config.Value; */\n"
        "    void Run() { }\n"
        "}\n"
    )
    names = _names(commented, "csharp")
    assert "PaymentGateway" not in names
    assert "Config" not in names

    real = (
        "namespace A;\n"
        "public class Service {\n"
        "    void Run() { var g = new PaymentGateway(); }\n"
        "}\n"
    )
    assert "PaymentGateway" in _names(real, "csharp")


def test_cpp_line_comment_name_is_not_a_reference():
    commented = (
        "void run() {\n"
        "    // new PaymentGateway(); Logger::instance();\n"
        "    return;\n"
        "}\n"
    )
    names = _names(commented, "cpp")
    assert "PaymentGateway" not in names
    assert "Logger" not in names

    real = "void run() {\n    auto* g = new PaymentGateway();\n}\n"
    assert "PaymentGateway" in _names(real, "cpp")


def test_cpp_block_comment_name_is_not_a_reference():
    commented = (
        "void run() {\n"
        "    /* Logger::instance(); new PaymentGateway(); */\n"
        "    return;\n"
        "}\n"
    )
    names = _names(commented, "cpp")
    assert "PaymentGateway" not in names
    assert "Logger" not in names

    real = "void run() {\n    Logger::instance();\n}\n"
    assert "Logger" in _names(real, "cpp")


# ---------------------------------------------------------------------------
# Scoping guard: swift and typescript comments are NOT masked (frozen baselines),
# so a name in a `//` comment still produces a signal there. This proves the fix
# is scoped to the three new languages, not a blanket scanner change.
# ---------------------------------------------------------------------------

def test_swift_comment_reference_behavior_is_unchanged():
    src = (
        "struct View1 {\n"
        "    func body() {\n"
        "        // let e = AudioEngine()\n"
        "        return\n"
        "    }\n"
        "}\n"
    )
    assert "AudioEngine" in _names(src, "swift"), (
        "swift comments are deliberately not masked; behavior must be unchanged"
    )


def test_typescript_comment_reference_behavior_is_unchanged():
    src = "function f() {\n    // const g = new PaymentGateway();\n    return 1;\n}\n"
    assert "PaymentGateway" in _names(src, "typescript"), (
        "typescript comments are deliberately not masked; behavior must be unchanged"
    )


# ---------------------------------------------------------------------------
# End-to-end (the reviewer's case): a two-module tree whose ONLY mention of an
# imported type is a comment draws NO uses edge; the same mention as real code
# does. C# is used because it is not a per-name-import language, so a single
# definer resolves without import evidence, keeping the positive case honest.
# ---------------------------------------------------------------------------

def _gateway_tree(root: Path) -> None:
    _write(root, "gateway/PaymentGateway.cs",
           "namespace Billing;\npublic class PaymentGateway { public void Charge() { } }\n")
    _write(root, "gateway/Ledger.cs",
           "namespace Billing;\npublic class Ledger { public int Total; }\n")


def test_e2e_comment_only_mention_draws_no_uses_edge(tmp_path):
    _gateway_tree(tmp_path)
    _write(tmp_path, "web/Handler.cs",
           "namespace Web;\npublic class Handler {\n"
           "    // new PaymentGateway().Charge() runs on checkout.\n"
           "    public void Run() { }\n}\n")
    _write(tmp_path, "web/Other.cs",
           "namespace Web;\npublic class Other { public int X; }\n")

    _, arch = _derive(tmp_path)
    assert _uses(arch, "web", "gateway") == [], (
        "a comment-only mention must not fabricate a uses edge"
    )


def test_e2e_real_code_mention_draws_a_uses_edge(tmp_path):
    _gateway_tree(tmp_path)
    _write(tmp_path, "web/Handler.cs",
           "namespace Web;\npublic class Handler {\n"
           "    public void Run() { var g = new PaymentGateway(); }\n}\n")
    _write(tmp_path, "web/Other.cs",
           "namespace Web;\npublic class Other { public int X; }\n")

    _, arch = _derive(tmp_path)
    assert len(_uses(arch, "web", "gateway")) == 1, (
        "a real-code reference to the imported type must draw the uses edge "
        "(guards against the negative test being vacuous)"
    )
