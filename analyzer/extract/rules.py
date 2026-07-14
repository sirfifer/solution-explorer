"""Per-file rule-bearing-code detection (Tier 1 support for P5-5, Rules lens L6).

A rule is a discrete unit of decision or constraint logic, operationally kinded
into four types (LENS-DESIGN.md section 4, L6):

  - ``validation``: guard-clause clusters and declared validators (pydantic
    validators, Django ``clean_*``, Rails ``validates``, zod/joi chains).
  - ``calculation``: an assignment or return computing a value from domain
    operands, anchored by a domain-named target or operand (fee/rate/total/...).
  - ``policy``: permission/authorization gates and decision-table-shaped
    branching (``match``/``switch`` over a domain value, ``if/elif`` chains).
  - ``io``: declarative field bounds and format constraints on model/schema
    fields (``max_length``, ``NOT NULL``, ``CHECK``, regex validators).

Detection is DETERMINISTIC and CONSERVATIVE: precision over recall. Ordinary
control flow (loop guards, internal null checks, bare error-handling re-raises,
index/counter math, single if/else) must NOT become a rule (see the noise test
in tests/test_rules.py). Each detector returns ``(value_dict, match_start)``
tuples in file-position order; signals.py turns ``match_start`` into a 1-based
line number and wraps each value in a :class:`SignalRecord`.

The ``summary`` on each value is a MECHANICAL rendering of the code (the
condition text and the outcome), never a natural-language explanation of intent:
plain-language statements are Phase 7 enrichment work, never extraction
(invariant I1). Owner, enclosing symbol, trigger capability, and entity links
are resolved later, in the Tier 3 derivation pass (analyzer/derive/rules.py).
"""

from __future__ import annotations

import re
from typing import Optional

# ---------------------------------------------------------------------------
# Shared vocabularies and thresholds (recorded in the P5-5 card).
# ---------------------------------------------------------------------------

# Exception/error types whose raise/throw marks a guard clause as *validation*
# rather than internal error handling. A bare re-raise, or a raise of a
# non-validation error, is not a rule.
_PY_VALIDATION_EXC = {
    "ValueError", "ValidationError", "TypeError", "AssertionError",
    "HTTPException", "HTTPError", "BadRequest", "BadRequestError",
    "InvalidArgument", "InvalidArgumentError", "ArgumentError",
    "Invalid", "ValidationException",
}
_JS_VALIDATION_ERR = {
    "ValidationError", "TypeError", "RangeError", "ValidationException",
    "BadRequestError", "BadRequestException", "InvalidArgumentError",
}
_RB_VALIDATION_EXC = {
    "ArgumentError", "TypeError", "RangeError", "ValidationError",
    "ActiveRecord::RecordInvalid",
}

# A domain vocabulary that anchors a calculation. A formula whose target and
# operands are all non-domain tokens (index/counter math) is rejected.
_DOMAIN_TERMS = {
    "fee", "fees", "rate", "rates", "tax", "taxes", "total", "totals",
    "subtotal", "price", "prices", "amount", "amounts", "discount",
    "discounts", "cost", "costs", "threshold", "limit", "limits", "interest",
    "balance", "salary", "wage", "wages", "score", "scores", "commission",
    "penalty", "penalties", "charge", "charges", "vat", "margin", "bonus",
    "quantity", "qty", "duration", "surcharge", "shipping", "gross", "net",
    "premium", "deductible", "payment", "payout", "revenue", "profit",
}

# A condition is "validation-shaped" when it contains a comparison, negation,
# membership, emptiness/presence, length, or regex check. Combined with a
# validation-allowlisted raise/throw, this keeps precision high.
_VALIDATION_SHAPE = re.compile(
    r"==|!=|<=|>=|<|>|\bnot\b|!|\bin\b|\bis\s+None\b|\bis\s+not\s+None\b|"
    r"\bNone\b|\bnull\b|\bnil\b|\.nil\?|\.empty\?|\.blank\?|\.present\?|"
    r"len\s*\(|\.length\b|\.match\b|=~|\.include\?|\.test\s*\("
)

_ARITH = re.compile(r"[+\-*/%]")
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")

# Policy branching thresholds (recorded): a decision-table needs >= 2 elif/case
# arms (a 3+-way branch), so a plain if/else is never a policy rule.
_MIN_ELIF_ARMS = 2
_MIN_CASE_LABELS = 2

_KEYWORD_IDENTS = {
    "if", "elif", "else", "for", "while", "return", "and", "or", "not", "in",
    "is", "None", "True", "False", "self", "let", "const", "var", "new",
    "true", "false", "null", "nil", "def", "function", "int", "float", "str",
}


def _domain_tokens(name: str) -> set[str]:
    """Split an identifier into lowercased word tokens (snake + camel)."""
    parts: set[str] = set()
    for chunk in name.replace(".", "_").split("_"):
        for piece in _CAMEL_BOUNDARY.split(chunk):
            if piece:
                parts.add(piece.lower())
    return parts


def _has_domain_anchor(*names: str) -> bool:
    for n in names:
        if _domain_tokens(n) & _DOMAIN_TERMS:
            return True
    return False


def _idents(expr: str) -> list[str]:
    """Identifiers in an expression, minus keywords and pure numbers."""
    out: list[str] = []
    seen: set[str] = set()
    for m in _IDENT.finditer(expr):
        tok = m.group(0)
        if tok in _KEYWORD_IDENTS or tok in seen:
            continue
        seen.add(tok)
        out.append(tok)
    return out


def _lines_with_offsets(content: str) -> list[tuple[str, int, int]]:
    """Return (text, char_offset, indent) per line, newline stripped."""
    out: list[tuple[str, int, int]] = []
    off = 0
    for raw in content.splitlines(keepends=True):
        text = raw.rstrip("\n").rstrip("\r")
        indent = len(text) - len(text.lstrip())
        out.append((text, off, indent))
        off += len(raw)
    return out


def _value(kind, summary, *, inputs=None, outputs=None, anchor=None,
           framework=None, confidence="inferred", field=None) -> dict:
    v: dict = {"kind": kind, "summary": summary[:300], "confidence": confidence}
    if inputs:
        v["inputs"] = sorted(dict.fromkeys(inputs))
    if outputs:
        v["outputs"] = sorted(dict.fromkeys(outputs))
    if anchor:
        v["anchor"] = anchor
    if framework:
        v["framework"] = framework
    if field:
        v["field"] = field
    return v


# ===========================================================================
# VALIDATION
# ===========================================================================

_PY_VALIDATOR_DEC = re.compile(
    r"@(?:\w+\.)?(field_validator|validator|root_validator|model_validator)\b"
    r"(?:\s*\(([^)]*)\))?"
)
_PY_CLEAN = re.compile(r"^\s*def\s+(clean(?:_\w+)?)\s*\(\s*self\b")
_QUOTED = re.compile(r"""['"]([\w.]+)['"]""")

_RB_VALIDATES = re.compile(r"^\s*(validates?)\s+(.+?)\s*$")
_RB_SYM = re.compile(r":(\w+)")

_ZOD_FIELD = re.compile(
    r"(\w+)\s*:\s*z\.[A-Za-z]+\(\s*\)((?:\s*\.[A-Za-z]+\([^)]*\))+)"
)
_JOI_FIELD = re.compile(
    r"(\w+)\s*:\s*Joi\.[A-Za-z]+\(\s*\)((?:\s*\.[A-Za-z]+\([^)]*\))*)"
)
_ZOD_CONSTRAINT = re.compile(
    r"\.(min|max|length|email|url|uuid|regex|positive|nonnegative|int|gt|lt|"
    r"gte|lte|startsWith|endsWith|nonempty|required|pattern|valid)\b"
)
_CHAIN_METHOD = re.compile(r"\.([A-Za-z]+)\(")


def _validation_python(content: str, lines) -> list[tuple[dict, int]]:
    out: list[tuple[dict, int]] = []
    # Declared: pydantic validators.
    for m in _PY_VALIDATOR_DEC.finditer(content):
        fields = [q.group(1) for q in _QUOTED.finditer(m.group(2) or "")]
        name = m.group(1)
        summary = f"@{name}({', '.join(fields)})" if fields else f"@{name}"
        out.append((_value(
            "validation", summary, inputs=fields, anchor="pydantic_validator",
            framework="pydantic", confidence="certain",
        ), m.start()))
    # Declared: Django clean_* methods.
    for text, off, _ in lines:
        cm = _PY_CLEAN.match(text)
        if cm:
            fname = cm.group(1)
            field = fname[len("clean_"):] if fname.startswith("clean_") else None
            out.append((_value(
                "validation", f"def {fname}(self)",
                inputs=[field] if field else None, anchor="django_clean",
                framework="django", confidence="certain", field=field,
            ), off + cm.start(1) - len("def ")))
    # Guard clauses.
    out.extend(_guard_clauses(lines, language="python"))
    return out


def _validation_ruby(content: str, lines) -> list[tuple[dict, int]]:
    out: list[tuple[dict, int]] = []
    for text, off, _ in lines:
        vm = _RB_VALIDATES.match(text)
        if vm:
            args = vm.group(2)
            syms = [s.group(1) for s in _RB_SYM.finditer(args)]
            if not syms:
                continue
            summary = f"{vm.group(1)} {', '.join(':' + s for s in syms)}"
            out.append((_value(
                "validation", summary, inputs=syms, anchor="rails_validates",
                framework="rails", confidence="certain",
            ), off + vm.start(1)))
    out.extend(_guard_clauses(lines, language="ruby"))
    return out


def _validation_js(content: str, lines) -> list[tuple[dict, int]]:
    out: list[tuple[dict, int]] = []
    for m in _ZOD_FIELD.finditer(content):
        chain = m.group(2)
        if not _ZOD_CONSTRAINT.search(chain):
            continue
        methods = [c.group(1) for c in _CHAIN_METHOD.finditer(chain)]
        name = m.group(1)
        out.append((_value(
            "validation", f"{name}: z chain [{', '.join(methods)}]",
            inputs=[name], outputs=methods, anchor="zod", framework="zod",
            confidence="certain", field=name,
        ), m.start()))
    for m in _JOI_FIELD.finditer(content):
        chain = m.group(2) or ""
        methods = [c.group(1) for c in _CHAIN_METHOD.finditer(chain)]
        if not any(x in methods for x in (
                "required", "min", "max", "email", "regex", "pattern",
                "length", "valid")):
            continue
        name = m.group(1)
        out.append((_value(
            "validation", f"{name}: Joi chain [{', '.join(methods)}]",
            inputs=[name], outputs=methods, anchor="joi", framework="joi",
            confidence="certain", field=name,
        ), m.start()))
    out.extend(_guard_clauses(lines, language="js"))
    return out


_PY_IF_ONELINE = re.compile(r"^(\s*)if\s+(.+?):\s*raise\s+([A-Za-z_][\w.]*)")
_PY_IF_HEADER = re.compile(r"^(\s*)if\s+(.+?):\s*$")
_PY_RAISE = re.compile(r"^\s*raise\s+([A-Za-z_][\w.]*)")
_JS_IF_THROW = re.compile(
    r"if\s*\((.+?)\)\s*(?:\{)?\s*(?:return\s+)?throw\s+new\s+(\w+)"
)
_JS_IF_HEADER = re.compile(r"^(\s*)if\s*\((.+?)\)\s*\{?\s*$")
_JS_THROW = re.compile(r"^\s*throw\s+new\s+(\w+)")
_RB_RAISE_MOD = re.compile(
    r"^\s*raise\s+([A-Za-z_][\w:]*)[^\n]*?\s+(if|unless)\s+(.+?)\s*$"
)


def _exc_ok(exc: str, allow: set[str]) -> bool:
    short = exc.rsplit(".", 1)[-1]
    if short in allow or exc in allow:
        return True
    return (short.endswith("ValidationError")
            or short.endswith("ValidationException")
            or "Invalid" in short)


def _guard_clauses(lines, language: str) -> list[tuple[dict, int]]:
    out: list[tuple[dict, int]] = []
    n = len(lines)
    if language in ("python", "ruby"):
        allow = _PY_VALIDATION_EXC if language == "python" else _RB_VALIDATION_EXC
        for i, (text, off, indent) in enumerate(lines):
            # one-line python: if cond: raise Exc
            m1 = _PY_IF_ONELINE.match(text)
            if language == "python" and m1:
                cond, exc = m1.group(2), m1.group(3)
                if _exc_ok(exc, allow) and _VALIDATION_SHAPE.search(cond):
                    out.append((_value(
                        "validation", f"raise {exc.rsplit('.', 1)[-1]} when {cond.strip()}",
                        inputs=_idents(cond), outputs=[exc.rsplit(".", 1)[-1]],
                        anchor="guard_clause",
                    ), off + m1.start(2) - len(m1.group(1)) - len("if ")))
                continue
            # two-line python: if cond:\n  raise Exc
            if language == "python":
                mh = _PY_IF_HEADER.match(text)
                if mh and i + 1 < n:
                    nxt, noff, nindent = lines[i + 1]
                    rm = _PY_RAISE.match(nxt)
                    if rm and nindent > indent:
                        cond, exc = mh.group(2), rm.group(1)
                        if _exc_ok(exc, allow) and _VALIDATION_SHAPE.search(cond):
                            out.append((_value(
                                "validation",
                                f"raise {exc.rsplit('.', 1)[-1]} when {cond.strip()}",
                                inputs=_idents(cond),
                                outputs=[exc.rsplit(".", 1)[-1]],
                                anchor="guard_clause",
                            ), off + mh.start(2)))
                continue
            # ruby modifier: raise Exc, "msg" unless cond   /   ... if cond
            if language == "ruby":
                rm = _RB_RAISE_MOD.match(text)
                if rm:
                    exc, kw, cond = rm.group(1), rm.group(2), rm.group(3)
                    if _exc_ok(exc, allow) and _VALIDATION_SHAPE.search(cond):
                        out.append((_value(
                            "validation",
                            f"raise {exc.rsplit('::', 1)[-1]} {kw} {cond.strip()}",
                            inputs=_idents(cond), outputs=[exc.rsplit("::", 1)[-1]],
                            anchor="guard_clause",
                        ), off + rm.start(1) - len("raise ")))
    else:  # js / ts
        allow = _JS_VALIDATION_ERR
        for i, (text, off, _indent) in enumerate(lines):
            m = _JS_IF_THROW.search(text)
            if m:
                cond, err = m.group(1), m.group(2)
                if err in allow and _VALIDATION_SHAPE.search(cond):
                    out.append((_value(
                        "validation", f"throw {err} when {cond.strip()}",
                        inputs=_idents(cond), outputs=[err], anchor="guard_clause",
                    ), off + m.start()))
                continue
            mh = _JS_IF_HEADER.match(text)
            if mh and i + 1 < n:
                nxt, noff, _ = lines[i + 1]
                tm = _JS_THROW.match(nxt)
                if tm:
                    cond, err = mh.group(2), tm.group(1)
                    if err in allow and _VALIDATION_SHAPE.search(cond):
                        out.append((_value(
                            "validation", f"throw {err} when {cond.strip()}",
                            inputs=_idents(cond), outputs=[err],
                            anchor="guard_clause",
                        ), off + mh.start(2)))
    return out


# ===========================================================================
# CALCULATION
# ===========================================================================

_ASSIGN = re.compile(
    r"^\s*(?:let|const|var|final|val)?\s*"
    r"([A-Za-z_][\w.\[\]]*)\s*(?:\+|-|\*|/|%)?(?::)?=\s*(.+?);?\s*$"
)
_RETURN = re.compile(r"^\s*return\s+(.+?);?\s*$")
_COMPARISON = re.compile(r"[=!<>]=|<|>")


def _calc_from_expr(target: Optional[str], rhs: str) -> Optional[dict]:
    # Must contain an arithmetic op and at least one named operand.
    if not _ARITH.search(rhs):
        return None
    # Strip string literals so "a" + "b" concat is not read as arithmetic math.
    stripped = re.sub(r"""(['"`]).*?\1""", "", rhs)
    if not _ARITH.search(stripped):
        return None
    operands = _idents(stripped)
    if not operands:
        return None
    anchor_names = list(operands)
    if target:
        anchor_names.append(target)
    if not _has_domain_anchor(*anchor_names):
        return None
    outputs = [target] if target else ["return"]
    summary = (f"{target} = {rhs.strip()}" if target else f"return {rhs.strip()}")
    return _value("calculation", summary, inputs=operands, outputs=outputs,
                  anchor="formula")


def _calculation(content: str, lines) -> list[tuple[dict, int]]:
    out: list[tuple[dict, int]] = []
    for text, off, _ in lines:
        rm = _RETURN.match(text)
        if rm:
            v = _calc_from_expr(None, rm.group(1))
            if v:
                out.append((v, off + rm.start(1)))
            continue
        am = _ASSIGN.match(text)
        if am:
            # Reject comparisons: the regex already excludes '==' via the RHS,
            # but guard against '<=' style false splits by requiring no bare
            # comparison operator at the split point.
            target, rhs = am.group(1), am.group(2)
            if _COMPARISON.match(rhs) or rhs.startswith("="):
                continue
            v = _calc_from_expr(target, rhs)
            if v:
                out.append((v, off + am.start(1)))
    return out


# ===========================================================================
# POLICY
# ===========================================================================

_PERM_DEF = re.compile(
    r"^\s*(?:def|func|function|fun)\s+"
    r"(can_\w+|is_allowed\w*|has_permission\w*|authorize\w*|check_\w*permission\w*"
    r"|can[A-Z]\w*|isAllowed\w*|hasPermission\w*)\b"
)
_PERM_DEC = re.compile(
    r"@(permission_required|login_required|requires_permission|requires_role|"
    r"requires_auth|authenticated|authorize)\b"
)
_RB_BEFORE = re.compile(
    r"^\s*before_action\s+:(authorize\w*|authenticate\w*|require_\w+)\b"
)
_PERM_CALL = re.compile(
    r"\b(authorize!?|can\?|cannot\?|has_permission|is_allowed|"
    r"ensure_permission|check_permission)\s*[(!]"
)

_PY_MATCH = re.compile(r"^(\s*)match\s+(.+?):\s*$")
_PY_CASE = re.compile(r"^(\s*)case\s+(.+?):\s*$")
_SWITCH = re.compile(r"switch\s*\(?\s*(.+?)\s*\)?\s*\{")
_CASE_LABEL = re.compile(r"\bcase\s+([^:\n]+):")
_PY_ELIF = re.compile(r"^(\s*)elif\b")
_RB_ELSIF = re.compile(r"^(\s*)elsif\b")
_PY_IF = re.compile(r"^(\s*)if\s+(.+?):\s*$")
_RB_IF = re.compile(r"^(\s*)if\s+(.+?)\s*$")


def _policy(content: str, lines, language: str) -> list[tuple[dict, int]]:
    out: list[tuple[dict, int]] = []

    # Permission gates (declared: certain; calls: inferred).
    for text, off, _ in lines:
        dm = _PERM_DEF.match(text)
        if dm:
            out.append((_value(
                "policy", f"permission gate: {dm.group(1)}", outputs=[dm.group(1)],
                anchor="permission_check", confidence="certain",
            ), off + dm.start(1)))
        pm = _PERM_DEC.search(text)
        if pm:
            out.append((_value(
                "policy", f"@{pm.group(1)}", anchor="permission_decorator",
                confidence="certain",
            ), off + pm.start()))
        if language == "ruby":
            bm = _RB_BEFORE.match(text)
            if bm:
                out.append((_value(
                    "policy", f"before_action :{bm.group(1)}", outputs=[bm.group(1)],
                    anchor="permission_check", confidence="certain",
                ), off + bm.start(1)))
        cm = _PERM_CALL.search(text)
        if cm and not _PERM_DEF.match(text):
            out.append((_value(
                "policy", f"permission check: {cm.group(1)}",
                anchor="permission_call", confidence="inferred",
            ), off + cm.start(1)))

    # Decision-table branching.
    out.extend(_decision_tables(lines, language))
    return out


def _decision_tables(lines, language: str) -> list[tuple[dict, int]]:
    out: list[tuple[dict, int]] = []
    n = len(lines)

    if language == "python":
        for i, (text, off, indent) in enumerate(lines):
            mm = _PY_MATCH.match(text)
            if mm:
                subj = mm.group(2)
                labels = []
                for j in range(i + 1, n):
                    t2, _, ind2 = lines[j]
                    if t2.strip() == "":
                        continue
                    if ind2 <= indent:
                        break
                    cm = _PY_CASE.match(t2)
                    if cm and ind2 > indent:
                        labels.append(cm.group(2).strip())
                if len(labels) >= _MIN_CASE_LABELS:
                    out.append((_value(
                        "policy", f"match {subj.strip()} -> [{', '.join(labels)}]",
                        inputs=_idents(subj), outputs=labels, anchor="match",
                        confidence="inferred",
                    ), off + mm.start(2)))
        out.extend(_elif_chains(lines, _PY_IF, _PY_ELIF))
    elif language == "ruby":
        out.extend(_elif_chains(lines, _RB_IF, _RB_ELSIF))
        out.extend(_case_when_ruby(lines))
    else:  # brace languages: js/ts/go/rust/swift/java/c/cpp/kotlin
        i = 0
        while i < n:
            text, off, _ = lines[i]
            sm = _SWITCH.search(text)
            if sm:
                subj = sm.group(1)
                labels = []
                for cl in _CASE_LABEL.finditer(text):
                    labels.append(cl.group(1).strip())
                brace = text.count("{") - text.count("}")
                j = i + 1
                while j < n and brace > 0:
                    t2, _, _ = lines[j]
                    for cl in _CASE_LABEL.finditer(t2):
                        labels.append(cl.group(1).strip())
                    brace += t2.count("{") - t2.count("}")
                    j += 1
                if len(labels) >= _MIN_CASE_LABELS:
                    out.append((_value(
                        "policy", f"switch {subj.strip()} -> [{', '.join(labels)}]",
                        inputs=_idents(subj), outputs=labels, anchor="switch",
                        confidence="inferred",
                    ), off + sm.start(1)))
                i = max(j, i + 1)
                continue
            i += 1
    return out


def _elif_chains(lines, if_re, elif_re) -> list[tuple[dict, int]]:
    out: list[tuple[dict, int]] = []
    n = len(lines)
    i = 0
    while i < n:
        text, off, indent = lines[i]
        im = if_re.match(text)
        if im:
            arms = 0
            j = i + 1
            while j < n:
                t2, _, ind2 = lines[j]
                if t2.strip() == "":
                    j += 1
                    continue
                if ind2 < indent:
                    break
                if ind2 == indent and elif_re.match(t2):
                    arms += 1
                    j += 1
                    continue
                if ind2 == indent and (t2.lstrip().startswith("else")):
                    j += 1
                    continue
                if ind2 <= indent:
                    break
                j += 1
            if arms >= _MIN_ELIF_ARMS:
                cond = im.group(2).strip()
                out.append((_value(
                    "policy", f"multi-branch: if {cond} (+{arms} branches)",
                    inputs=_idents(cond), anchor="if_elif_chain",
                    confidence="inferred",
                ), off + im.start(2)))
            i = j
            continue
        i += 1
    return out


_RB_CASE = re.compile(r"^(\s*)case\s+(.+?)\s*$")
_RB_WHEN = re.compile(r"^(\s*)when\s+(.+?)\s*$")


def _case_when_ruby(lines) -> list[tuple[dict, int]]:
    out: list[tuple[dict, int]] = []
    n = len(lines)
    for i, (text, off, indent) in enumerate(lines):
        cm = _RB_CASE.match(text)
        if cm:
            subj = cm.group(2)
            labels = []
            for j in range(i + 1, n):
                t2, _, ind2 = lines[j]
                if t2.strip() == "":
                    continue
                if ind2 < indent or (t2.strip() == "end" and ind2 <= indent):
                    break
                wm = _RB_WHEN.match(t2)
                if wm and ind2 >= indent:
                    labels.append(wm.group(2).strip())
            if len(labels) >= _MIN_CASE_LABELS:
                out.append((_value(
                    "policy", f"case {subj.strip()} -> [{', '.join(labels)}]",
                    inputs=_idents(subj), outputs=labels, anchor="case_when",
                    confidence="inferred",
                ), off + cm.start(2)))
    return out


# ===========================================================================
# IO CONSTRAINT
# ===========================================================================

_DJANGO_FIELD = re.compile(
    r"^\s*(\w+)\s*=\s*(?:models\.)?\w*Field\s*\((.*)$"
)
_SA_COLUMN = re.compile(
    r"^\s*(\w+)\s*(?::[^=]+)?=\s*(?:Column|mapped_column)\s*\((.*)$"
)
_IO_TOKENS = re.compile(
    r"\b(max_length\s*=\s*\d+|min_length\s*=\s*\d+|max_value\s*=|min_value\s*="
    r"|MaxLengthValidator|MinLengthValidator|MaxValueValidator|MinValueValidator"
    r"|RegexValidator|validators\s*=|null\s*=\s*False|nullable\s*=\s*False"
    r"|unique\s*=\s*True|CheckConstraint)\b"
)

_SQL_COL = re.compile(
    r"^\s*[`\"]?(\w+)[`\"]?\s+[A-Za-z]+(?:\s*\(\s*\d+\s*\))?"
    r"(.*\b(?:NOT\s+NULL|CHECK|DEFAULT|UNIQUE)\b.*)$",
    re.IGNORECASE,
)
_SQL_VARCHAR = re.compile(r"VARCHAR\s*\(\s*(\d+)\s*\)", re.IGNORECASE)

_PRISMA_FIELD = re.compile(
    r"^\s*(\w+)\s+[\w\[\]?]+\s+.*@(db\.VarChar\(\d+\)|default\([^)]*\)|unique|id)\b"
)

_CLASS_VALIDATOR = re.compile(
    r"@(IsEmail|IsNotEmpty|MaxLength|MinLength|Min|Max|Length|Matches|IsInt"
    r"|IsPositive|IsUrl|IsUUID|IsEnum|IsDefined)\s*\(([^)]*)\)"
)
_TS_PROP = re.compile(r"^\s*(?:readonly\s+)?(\w+)\s*[!?:]")
_TS_PROP_INLINE = re.compile(r"(?:readonly\s+)?(\w+)\s*[!?:]")

_RB_SCHEMA_COL = re.compile(
    r"^\s*t\.\w+\s+[:'\"](\w+)['\"]?(.*\b(?:limit:|null:\s*false|default:)\b.*)$"
)


def _io_python(content: str, lines) -> list[tuple[dict, int]]:
    out: list[tuple[dict, int]] = []
    for text, off, _ in lines:
        for rx, framework, anchor in (
            (_DJANGO_FIELD, "django", "django_field"),
            (_SA_COLUMN, "sqlalchemy", "sqlalchemy_column"),
        ):
            fm = rx.match(text)
            if fm:
                field, rest = fm.group(1), fm.group(2)
                toks = [t.group(1) for t in _IO_TOKENS.finditer(rest)]
                if not toks:
                    continue
                out.append((_value(
                    "io", f"{field}: {', '.join(toks)}", field=field,
                    outputs=toks, anchor=anchor, framework=framework,
                    confidence="certain",
                ), off + fm.start(1)))
                break
    return out


def _io_sql(content: str, lines) -> list[tuple[dict, int]]:
    out: list[tuple[dict, int]] = []
    for text, off, _ in lines:
        sm = _SQL_COL.match(text)
        if sm:
            field = sm.group(1)
            if field.upper() in ("PRIMARY", "FOREIGN", "CONSTRAINT", "CHECK",
                                  "UNIQUE", "KEY", "INDEX"):
                continue
            toks = []
            for kw in ("NOT NULL", "CHECK", "DEFAULT", "UNIQUE"):
                if re.search(rf"\b{kw}\b", text, re.IGNORECASE):
                    toks.append(kw)
            vm = _SQL_VARCHAR.search(text)
            if vm:
                toks.append(f"VARCHAR({vm.group(1)})")
            if not toks:
                continue
            out.append((_value(
                "io", f"{field}: {', '.join(toks)}", field=field, outputs=toks,
                anchor="sql_column", framework="sql", confidence="certain",
            ), off + sm.start(1)))
    return out


def _io_prisma(content: str, lines) -> list[tuple[dict, int]]:
    out: list[tuple[dict, int]] = []
    for text, off, _ in lines:
        pm = _PRISMA_FIELD.match(text)
        if pm:
            out.append((_value(
                "io", f"{pm.group(1)}: @{pm.group(2)}", field=pm.group(1),
                outputs=[pm.group(2)], anchor="prisma_field", framework="prisma",
                confidence="certain",
            ), off + pm.start(1)))
    return out


def _io_ts(content: str, lines) -> list[tuple[dict, int]]:
    out: list[tuple[dict, int]] = []
    n = len(lines)
    for i, (text, off, _) in enumerate(lines):
        cm = _CLASS_VALIDATOR.search(text)
        if cm:
            # the constrained property is after the decorator on this line, or
            # on the next line (decorator-on-its-own-line style).
            field = None
            tail = text[cm.end():]
            pm = _TS_PROP_INLINE.match(tail.lstrip())
            if pm:
                field = pm.group(1)
            elif i + 1 < n:
                pm2 = _TS_PROP.match(lines[i + 1][0])
                if pm2:
                    field = pm2.group(1)
            args = cm.group(2).strip()
            summary = f"@{cm.group(1)}({args})" if args else f"@{cm.group(1)}"
            if field:
                summary = f"{field}: {summary}"
            out.append((_value(
                "io", summary, field=field, outputs=[cm.group(1)],
                anchor="class_validator", framework="class-validator",
                confidence="certain",
            ), off + cm.start()))
    return out


def _io_ruby(content: str, lines) -> list[tuple[dict, int]]:
    out: list[tuple[dict, int]] = []
    for text, off, _ in lines:
        sm = _RB_SCHEMA_COL.match(text)
        if sm:
            field, rest = sm.group(1), sm.group(2)
            toks = []
            for kw, label in ((r"limit:", "limit"), (r"null:\s*false", "null:false"),
                              (r"default:", "default")):
                if re.search(kw, rest):
                    toks.append(label)
            out.append((_value(
                "io", f"{field}: {', '.join(toks)}", field=field, outputs=toks,
                anchor="rails_schema", framework="rails", confidence="certain",
            ), off + sm.start(1)))
    return out


# ===========================================================================
# Dispatch + dedup
# ===========================================================================

def _dedupe(items: list[tuple[dict, int]]) -> list[tuple[dict, int]]:
    """Position-order and drop duplicate (kind, summary, start) tuples."""
    seen: set = set()
    out: list[tuple[dict, int]] = []
    for value, start in sorted(items, key=lambda t: (t[1], t[0]["kind"], t[0]["summary"])):
        key = (value["kind"], value["summary"], start)
        if key in seen:
            continue
        seen.add(key)
        out.append((value, start))
    return out


def extract_rules(content: str, language: str, path: str) -> list[tuple[dict, int]]:
    """Detect rule-bearing code in one file. Returns ``(value, match_start)``."""
    lines = _lines_with_offsets(content)
    out: list[tuple[dict, int]] = []

    # -- validation --
    if language == "python":
        out.extend(_validation_python(content, lines))
    elif language == "ruby":
        out.extend(_validation_ruby(content, lines))
    elif language in ("javascript", "typescript"):
        out.extend(_validation_js(content, lines))
    else:
        out.extend(_guard_clauses(lines, language="js"
                                  if language in ("go", "rust", "swift", "java")
                                  else "python"))

    # -- calculation (language-agnostic) --
    out.extend(_calculation(content, lines))

    # -- policy --
    if language in ("javascript", "typescript", "go", "rust", "swift", "java",
                    "kotlin", "c", "cpp", "csharp"):
        out.extend(_policy(content, lines, language="js"))
    else:
        out.extend(_policy(content, lines, language=language))

    # -- io --
    if language == "python":
        out.extend(_io_python(content, lines))
    elif language == "sql":
        out.extend(_io_sql(content, lines))
    elif language == "prisma":
        out.extend(_io_prisma(content, lines))
    elif language in ("javascript", "typescript"):
        out.extend(_io_ts(content, lines))
    elif language == "ruby":
        out.extend(_io_ruby(content, lines))

    return _dedupe(out)
