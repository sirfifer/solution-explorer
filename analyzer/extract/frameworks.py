"""Per-framework capability-signal extraction (Tier 1 support for P5-1).

The v2 endpoint, CLI, and job signals come from precise, framework-anchored
rules defined here, not from the legacy ``analyzer/parsers/*.detect_api_endpoints``
methods (which stay as the reference implementation and keep their own tests) nor
from scanner.py's regexes. Elevating the rules here is what lets P5-1 eliminate
the audited header-name false-positive class: the old endpoint regexes matched
``request.headers.get("X-Hub-Signature-256")`` and captured the header name as a
route. Every route candidate here passes through :func:`is_route_path`, which
rejects anything that is not shaped like a route, so header names and outbound
client URLs never become capabilities (TARGET-ARCHITECTURE.md section 5).

Each extractor returns a list of ``(value_dict, match_start)`` tuples; the
caller (signals.py) turns ``match_start`` into a 1-based line number and wraps
each value in a :class:`SignalRecord`. Results are position-ordered and deduped
so extraction is deterministic across processes (invariant I4).
"""

from __future__ import annotations

import re
from bisect import bisect_left
from typing import Optional

# ---------------------------------------------------------------------------
# Route-shape guard: the single choke point that kills the header false-positive
# class. A route candidate is accepted only when it looks like a route.
# ---------------------------------------------------------------------------

# HTTP header-ish token: Title-Case, optionally hyphenated (Authorization,
# Content-Type, X-Hub-Signature-256). Bare-path frameworks (Vapor, Rails) reject
# these; slash frameworks reject them implicitly (a header never starts with /).
_HEADERISH = re.compile(r"^[A-Z][A-Za-z0-9]*(-[A-Za-z0-9]+)*$")


def is_route_path(path: Optional[str], *, allow_bare: bool = False) -> bool:
    """True when ``path`` is shaped like an HTTP route, not a header or URL.

    Slash frameworks (Flask, FastAPI, aiohttp, Express, gin/echo/fiber,
    actix/axum) require a leading ``/``. Bare-path frameworks (Vapor, Rails,
    which write ``app.get("users")`` / ``get "users"``) set ``allow_bare`` and
    are guarded instead by their framework anchor plus a header-shape rejection.
    An outbound client URL (contains ``://``) is never a route.
    """
    if not path or path.isspace():
        return False
    if "://" in path:
        return False
    if path.startswith("/"):
        return True
    if allow_bare:
        # A bare route component ("users", "v1", ":id"). Reject header-shaped
        # tokens (Authorization, X-Hub-Signature-256) and whitespace.
        if _HEADERISH.match(path):
            return False
        return " " not in path
    return False


# Languages whose line comments start with an unquoted '#'. ONLY these get the
# comment handling in compute_string_spans: applying '#' comment rules to a
# language where '#' is code (Swift `#available` / raw strings `#"..."#`, TS/JS
# private fields `#count`) would un-mask real strings relative to the pre-guard
# scanner (PR #55 review finding 3).
HASH_COMMENT_LANGUAGES = frozenset({"python", "ruby", "shell", "bash", "yaml"})


def compute_string_spans(content: str, language: str | None = None) -> list[tuple[int, int]]:
    """Ordered, non-overlapping ``[start, end)`` masked spans (D3).

    A pattern/detector tool defines its own detection patterns as string
    constants (for example a job rule written as a compiled regex over the token
    a celery task decorator uses), so scanning such a repo makes the detectors
    fire on their own definitions: the token appears inside the pattern string
    and is reported as real usage. It also appears inside module docstrings that
    document those patterns. A code anchor (a decorator, a method call, an
    import) never lives inside a string literal in real usage, so a match whose
    START is inside a quoted string is a definition or a documentation example,
    not real usage, and is suppressed.

    A SINGLE left-to-right scan builds the span list, so callers with many match
    positions on one file binary-search the spans (:func:`pos_in_spans`) instead
    of rescanning from offset 0 per match (the PR #53 quadratic-rescan nit). The
    scan understands triple-quoted strings (Python docstrings, multi-line),
    single- and double-quoted strings (terminated by their quote or the line
    end), and backtick template literals (multi-line), all with backslash-escape
    awareness. Route paths and URLs, whose *value* lives in a string but whose
    match *anchor* is real code before the quote, are unaffected because the
    anchor offset is not inside a string.

    Language boundary (PR #55 review findings 2 and 3): when ``language`` is one
    of :data:`HASH_COMMENT_LANGUAGES`, an unquoted ``#`` opens a line comment
    that runs to the end of its line and the WHOLE comment is recorded as a
    masked span, so (a) a triple-quote opener inside a comment does not open a
    phantom, never-closed string that would swallow the rest of the file, and
    (b) commented-out code (``# x = Config()``) is masked and never read as real
    usage. For every other language (and ``language=None``) ``#`` is an ordinary
    character, byte-identical to the pre-guard scanner, so Swift ``#available``
    / raw strings and TS/JS ``#field`` syntax stay code. ``//`` line comments
    are deliberately NOT modeled: the guard fails toward "not in a string" (a
    match is treated as real usage), which is the safe direction. See the
    recorded rows in TASKS.md.
    """
    hash_comments = language in HASH_COMMENT_LANGUAGES
    spans: list[tuple[int, int]] = []
    length = len(content)
    i = 0
    while i < length:
        ch = content[i]
        # An unquoted '#' opens a line comment in hash-comment languages; the
        # whole comment is masked so neither a '"""' inside it opens a string
        # nor commented-out code reads as usage (findings 2 and 3).
        if ch == "#" and hash_comments:
            nl = content.find("\n", i)
            end = length if nl == -1 else nl
            spans.append((i, end))
            i = end + 1
            continue
        # Triple-quoted strings first: they can span many lines (docstrings).
        if content.startswith('"""', i) or content.startswith("'''", i):
            q = content[i:i + 3]
            end = content.find(q, i + 3)
            if end == -1:
                spans.append((i, length))  # unterminated triple quote
                break
            close = end + 3
            spans.append((i, close))
            i = close
            continue
        if ch in "\"'`":
            j = i + 1
            while j < length:
                c = content[j]
                if c == "\\":
                    j += 2
                    continue
                if c == ch:
                    j += 1
                    break
                if c == "\n" and ch != "`":
                    break  # an unterminated single-line string ends at the line
                j += 1
            spans.append((i, j))
            i = j
            continue
        i += 1
    return spans


class StringMask:
    """Precomputed masked-span index for one file's content (PR #53 nit b).

    Build once per file (with the file's ``language`` so hash-comment handling
    is applied only where ``#`` really is a comment), then query many match
    positions in O(log n) each via binary search, instead of the old O(n)
    rescan-from-zero per position that made whole-file signal extraction
    quadratic on match-heavy files. Masked spans are string literals plus, for
    :data:`HASH_COMMENT_LANGUAGES`, ``#`` line comments.
    """

    __slots__ = ("_starts", "_ends")

    def __init__(self, content: str, language: str | None = None):
        spans = compute_string_spans(content, language)
        self._starts = [s for s, _ in spans]
        self._ends = [e for _, e in spans]

    def in_string(self, pos: int) -> bool:
        """True when ``pos`` falls strictly inside a masked span (``start < pos < end``).

        The opening-quote offset itself is not "inside", matching the historical
        :func:`in_string_literal` semantics so extraction stays byte-stable.
        """
        if pos <= 0 or not self._starts:
            return False
        idx = bisect_left(self._starts, pos) - 1
        return idx >= 0 and pos < self._ends[idx]


def pos_in_spans(spans: list[tuple[int, int]], pos: int) -> bool:
    """Binary-search helper: is ``pos`` strictly inside one of ``spans``?

    ``spans`` must be the sorted, non-overlapping output of
    :func:`compute_string_spans`.
    """
    if pos <= 0 or not spans:
        return False
    starts = [s for s, _ in spans]
    idx = bisect_left(starts, pos) - 1
    return idx >= 0 and pos < spans[idx][1]


def in_string_literal(content: str, pos: int, language: str | None = None) -> bool:
    """True when offset ``pos`` falls inside a masked span (D3).

    Backward-compatible single-shot wrapper over :class:`StringMask`. With the
    default ``language=None`` this is byte-identical to the original pre-mask
    byte scan (no ``#`` comment handling). Callers that test many positions on
    the same content should build one :class:`StringMask` and reuse it (this
    wrapper rescans per call).
    """
    return StringMask(content, language).in_string(pos)


def _hint(content: str, *markers: str) -> bool:
    return any(m in content for m in markers)


def _line_key(value: dict, start: int) -> tuple:
    return (value.get("method"), value.get("path"))


def _dedupe(items: list[tuple[dict, int]]) -> list[tuple[dict, int]]:
    """Keep the first (most specific) match per (method, path), position-ordered."""
    seen: set = set()
    out: list[tuple[dict, int]] = []
    for value, start in sorted(items, key=lambda t: t[1]):
        key = _line_key(value, start)
        if key in seen:
            continue
        seen.add(key)
        out.append((value, start))
    return out


# ---------------------------------------------------------------------------
# Endpoints, per framework.
# ---------------------------------------------------------------------------

_PY_VERB = r"(get|post|put|delete|patch|head|options|websocket)"

_PY_DECORATOR_VERB = re.compile(
    rf"@\s*[\w.]+\.{_PY_VERB}\s*\(\s*['\"](/[^'\"]*)['\"]"
)
_PY_FLASK_ROUTE = re.compile(
    r"@\s*[\w.]+\.route\s*\(\s*['\"](/[^'\"]*)['\"]([^)]*)", re.DOTALL
)
_PY_AIOHTTP_ADD = re.compile(
    rf"[\w.]+\.add_{_PY_VERB}\s*\(\s*['\"](/[^'\"]*)['\"]"
)
_PY_AIOHTTP_WEB = re.compile(
    rf"\bweb\.{_PY_VERB}\s*\(\s*['\"](/[^'\"]*)['\"]"
)
_PY_AIOHTTP_ROUTES = re.compile(
    rf"@\s*\w*[Rr]outes?\.{_PY_VERB}\s*\(\s*['\"](/[^'\"]*)['\"]"
)
_FLASK_METHODS = re.compile(r"methods\s*=\s*\[([^\]]*)\]")


def _python_endpoints(content: str) -> list[tuple[dict, int]]:
    is_flask = _hint(content, "from flask", "import flask", "Flask(")
    is_fastapi = _hint(content, "from fastapi", "import fastapi", "FastAPI(", "APIRouter(")
    is_aiohttp = _hint(content, "aiohttp", "RouteTableDef", ".add_get", "web.get")
    out: list[tuple[dict, int]] = []

    # Flask route decorator (explicit methods= list, else GET).
    for m in _PY_FLASK_ROUTE.finditer(content):
        path = m.group(1)
        if not is_route_path(path):
            continue
        mm = _FLASK_METHODS.search(m.group(2) or "")
        if mm:
            methods = [x.strip().strip("'\"").upper() for x in mm.group(1).split(",") if x.strip()]
        else:
            methods = ["GET"]
        for method in methods:
            out.append(({"method": method, "path": path, "framework": "flask"}, m.start()))

    # aiohttp routers.
    for rx in (_PY_AIOHTTP_ADD, _PY_AIOHTTP_WEB, _PY_AIOHTTP_ROUTES):
        for m in rx.finditer(content):
            path = m.group(2)
            if not is_route_path(path):
                continue
            out.append((
                {"method": m.group(1).upper(), "path": path, "framework": "aiohttp"},
                m.start(),
            ))

    # FastAPI / Flask verb decorators (an @app verb call). Framework by hint.
    consumed = {(v["method"], v["path"]) for v, _ in out}
    for m in _PY_DECORATOR_VERB.finditer(content):
        path = m.group(2)
        if not is_route_path(path):
            continue
        method = m.group(1).upper()
        if (method, path) in consumed:
            continue
        framework = "fastapi" if is_fastapi or not is_flask else "flask"
        if is_aiohttp and not is_fastapi and not is_flask:
            framework = "aiohttp"
        out.append(({"method": method, "path": path, "framework": framework}, m.start()))
    return _dedupe(out)


_JS_VERB = r"(get|post|put|delete|patch|all|options|head)"
_JS_EXPRESS = re.compile(
    rf"\b[\w.]+\.{_JS_VERB}\s*\(\s*['\"`](/[^'\"`]*)['\"`]"
)
_JS_NEXT = re.compile(
    r"export\s+(?:async\s+)?function\s+(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\b"
)


def _js_endpoints(content: str) -> list[tuple[dict, int]]:
    out: list[tuple[dict, int]] = []
    for m in _JS_EXPRESS.finditer(content):
        path = m.group(2)
        if not is_route_path(path):
            continue
        out.append((
            {"method": m.group(1).upper(), "path": path, "framework": "express"},
            m.start(),
        ))
    for m in _JS_NEXT.finditer(content):
        out.append((
            {"method": m.group(1).upper(), "path": "(file-based)", "framework": "nextjs"},
            m.start(),
        ))
    return _dedupe(out)


_GO_VERB = (
    r"(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS|Any|All"
    r"|Get|Post|Put|Delete|Patch|Head|Options)"
)
_GO_ROUTE = re.compile(rf"\b[\w.]+\.{_GO_VERB}\s*\(\s*\"(/[^\"]*)\"")


def _go_endpoints(content: str) -> list[tuple[dict, int]]:
    if _hint(content, "gin.Default", "gin.New", "*gin."):
        framework = "gin"
    elif _hint(content, "echo.New", "labstack/echo"):
        framework = "echo"
    elif _hint(content, "fiber.New", "gofiber/fiber"):
        framework = "fiber"
    else:
        framework = "go-http"
    out: list[tuple[dict, int]] = []
    for m in _GO_ROUTE.finditer(content):
        path = m.group(2)
        if not is_route_path(path):
            continue
        out.append((
            {"method": m.group(1).upper(), "path": path, "framework": framework},
            m.start(),
        ))
    return _dedupe(out)


_RB_VERB = re.compile(
    r"(?m)^\s*(get|post|put|patch|delete|head|options)\s+['\"]([^'\"]+)['\"]"
)
_RB_RESOURCES = re.compile(r"(?m)^\s*(resources|resource)\s+:(\w+)")


def _ruby_endpoints(content: str) -> list[tuple[dict, int]]:
    framework = "sinatra" if _hint(content, "sinatra", "Sinatra") else "rails"
    out: list[tuple[dict, int]] = []
    for m in _RB_VERB.finditer(content):
        path = m.group(2)
        if not is_route_path(path, allow_bare=True):
            continue
        norm = path if path.startswith("/") else "/" + path
        out.append((
            {"method": m.group(1).upper(), "path": norm, "framework": framework},
            m.start(),
        ))
    for m in _RB_RESOURCES.finditer(content):
        out.append((
            {"method": "RESOURCE", "path": "/" + m.group(2), "framework": "rails"},
            m.start(),
        ))
    return _dedupe(out)


_RS_ACTIX_MACRO = re.compile(
    r"#\[\s*(get|post|put|delete|patch|head|options)\s*\(\s*\"(/[^\"]*)\""
)
_RS_ACTIX_ROUTE = re.compile(
    r"\.route\s*\(\s*\"(/[^\"]*)\"\s*,\s*web::(get|post|put|delete|patch)"
)
_RS_AXUM_ROUTE = re.compile(
    r"\.route\s*\(\s*\"(/[^\"]*)\"\s*,\s*(get|post|put|delete|patch)\s*\("
)


def _rust_endpoints(content: str) -> list[tuple[dict, int]]:
    out: list[tuple[dict, int]] = []
    for m in _RS_ACTIX_MACRO.finditer(content):
        path = m.group(2)
        if not is_route_path(path):
            continue
        out.append((
            {"method": m.group(1).upper(), "path": path, "framework": "actix"},
            m.start(),
        ))
    for m in _RS_ACTIX_ROUTE.finditer(content):
        path = m.group(1)
        if not is_route_path(path):
            continue
        out.append((
            {"method": m.group(2).upper(), "path": path, "framework": "actix"},
            m.start(),
        ))
    for m in _RS_AXUM_ROUTE.finditer(content):
        path = m.group(1)
        if not is_route_path(path):
            continue
        out.append((
            {"method": m.group(2).upper(), "path": path, "framework": "axum"},
            m.start(),
        ))
    return _dedupe(out)


_SW_VAPOR = re.compile(
    r"\b(app|routes|route|router|group|grouped|protected|builder|api)\b\??"
    r"\.(get|post|put|delete|patch)\s*\(\s*\"([^\"]*)\""
)


def _swift_endpoints(content: str) -> list[tuple[dict, int]]:
    # Gate on a Vapor marker so no unrelated Swift ``.get(`` matches.
    if not _hint(content, "import Vapor", "RoutesBuilder", "RouteCollection",
                 "func boot(routes", "app.grouped", "req.eventLoop"):
        return []
    out: list[tuple[dict, int]] = []
    for m in _SW_VAPOR.finditer(content):
        path = m.group(3)
        if not is_route_path(path, allow_bare=True):
            continue
        norm = path if path.startswith("/") else "/" + path
        out.append((
            {"method": m.group(2).upper(), "path": norm, "framework": "vapor"},
            m.start(),
        ))
    return _dedupe(out)


_CS_MINIMAL_API = re.compile(
    r"\.Map(Get|Post|Put|Delete|Patch)\s*\(\s*\"(/[^\"]*)\""
)
_CS_HTTP_ATTR = re.compile(
    r"\[\s*Http(Get|Post|Put|Delete|Patch)\s*\(\s*\"([^\"]*)\"\s*\)\s*\]"
)


def _csharp_endpoints(content: str) -> list[tuple[dict, int]]:
    # Gate on an ASP.NET Core marker so no unrelated `.MapGet(` matches.
    if not _hint(content, "Microsoft.AspNetCore", "ControllerBase",
                 "[ApiController]", "WebApplication.Create", "IEndpointRouteBuilder"):
        return []
    out: list[tuple[dict, int]] = []
    for m in _CS_MINIMAL_API.finditer(content):
        path = m.group(2)
        if not is_route_path(path):
            continue
        out.append((
            {"method": m.group(1).upper(), "path": path, "framework": "aspnetcore"},
            m.start(),
        ))
    for m in _CS_HTTP_ATTR.finditer(content):
        path = m.group(2)
        # Attribute routes are relative to the controller's [Route(...)]; keep
        # a leading slash so is_route_path accepts a bare template segment.
        norm = path if path.startswith("/") else "/" + path
        if not is_route_path(norm):
            continue
        out.append((
            {"method": m.group(1).upper(), "path": norm, "framework": "aspnetcore"},
            m.start(),
        ))
    return _dedupe(out)


_ENDPOINT_EXTRACTORS = {
    "csharp": _csharp_endpoints,
    "python": _python_endpoints,
    "javascript": _js_endpoints,
    "typescript": _js_endpoints,
    "go": _go_endpoints,
    "ruby": _ruby_endpoints,
    "rust": _rust_endpoints,
    "swift": _swift_endpoints,
}


def extract_endpoints(content: str, language: str) -> list[tuple[dict, int]]:
    """Return ``(value, match_start)`` endpoint tuples for ``content``."""
    fn = _ENDPOINT_EXTRACTORS.get(language)
    return fn(content) if fn else []


# ---------------------------------------------------------------------------
# CLI commands and flags, per framework.
# ---------------------------------------------------------------------------

_CLI_COMMAND_RULES: dict[str, list[tuple[re.Pattern, Optional[int], str]]] = {
    "python": [
        (re.compile(r"@(?:click|[\w.]+)\.command\s*\(\s*['\"]([\w:-]+)['\"]"), 1, "click"),
        (re.compile(r"@(?:click|[\w.]+)\.group\s*\(\s*['\"]([\w:-]+)['\"]"), 1, "click"),
        (re.compile(r"@(?:click)\.(?:command|group)\s*\(\s*\)"), None, "click"),
        (re.compile(r"@(?:app|cli|[\w.]+)\.command\s*\(\s*\)"), None, "typer"),
        (re.compile(r"@(?:app|cli|[\w.]+)\.command\s*\(\s*['\"]([\w:-]+)['\"]"), 1, "typer"),
        (re.compile(r"\.add_parser\s*\(\s*['\"]([\w:-]+)['\"]"), 1, "argparse"),
    ],
    "typescript": [
        (re.compile(r"\.command\s*\(\s*['\"]([\w:<> [\]-]+)['\"]"), 1, "commander"),
    ],
    "javascript": [
        (re.compile(r"\.command\s*\(\s*['\"]([\w:<> [\]-]+)['\"]"), 1, "commander"),
    ],
    "go": [
        (re.compile(r"cobra\.Command\s*\{[^}]*?Use\s*:\s*['\"]([\w:-]+)['\"]", re.DOTALL), 1, "cobra"),
    ],
    "rust": [
        (re.compile(r"(?:Command|App)::new\s*\(\s*['\"]([\w:-]+)['\"]"), 1, "clap"),
        (re.compile(r"\.subcommand\s*\(\s*(?:Command|App)::new\s*\(\s*['\"]([\w:-]+)['\"]"), 1, "clap"),
    ],
    "ruby": [
        (re.compile(r"(?m)^\s*desc\s+['\"]([\w:<> -]+)['\"]"), 1, "thor"),
    ],
}

_CLI_OPTION_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"@[\w.]+\.option\s*\(\s*['\"](--[\w-]+)['\"]"), "click"),
    (re.compile(r"@[\w.]+\.argument\s*\(\s*['\"]([\w-]+)['\"]"), "click"),
    (re.compile(r"typer\.Option\s*\([^)]*?['\"](--[\w-]+)['\"]"), "typer"),
    (re.compile(r"\.add_argument\s*\(\s*['\"](--[\w-]+)['\"]"), "argparse"),
    (re.compile(r"\.(?:option|requiredOption)\s*\(\s*['\"](?:-\w,\s*)?(--[\w-]+)"), "commander"),
    (re.compile(r"\.long\s*\(\s*['\"]([\w-]+)['\"]"), "clap"),
    (re.compile(r"#\[\s*arg\([^)]*?long\s*=\s*['\"]([\w-]+)['\"]"), "clap"),
]


def _suppress_overlaps(matches: list[tuple[dict, int, int]]) -> list[tuple[dict, int]]:
    """Drop matches whose span nests inside an accepted, more-specific match.

    Sorted by start, the outer/earlier match (for example ``@click.option(...)``
    or ``.subcommand(Command::new(...))``) is accepted and the inner one it
    contains (``.option(...)`` / ``Command::new(...)``) is dropped, so a single
    declaration does not yield two framework-tagged signals. Determinism holds:
    the input is position-ordered before suppression.
    """
    accepted: list[tuple[dict, int, int]] = []
    for value, start, end in sorted(matches, key=lambda t: (t[1], t[2])):
        if any(a_start <= start < a_end for _, a_start, a_end in accepted):
            continue
        accepted.append((value, start, end))
    return [(v, s) for v, s, _ in accepted]


def extract_cli(content: str, language: str) -> tuple[list[tuple[dict, int]], list[tuple[dict, int]]]:
    """Return (commands, options) as ``(value, match_start)`` tuples.

    A command value is ``{"name", "framework"}``; an option value is
    ``{"flag", "framework"}``. Flags are associated to commands later, in the
    capability derivation pass (nearest preceding command in the same file).
    Overlapping cross-rule matches (a click ``@x.option`` also matches the
    generic commander ``.option`` rule) are suppressed so one declaration yields
    one signal.
    """
    mask = StringMask(content, language)  # one scan; queried per match (PR #53 nit b)
    cmd_matches: list[tuple[dict, int, int]] = []
    for pat, name_group, framework in _CLI_COMMAND_RULES.get(language, []):
        for m in pat.finditer(content):
            if mask.in_string(m.start()):
                continue  # a pattern definition, not a real command anchor (D3)
            name = None
            if name_group is not None and m.lastindex and name_group <= m.lastindex:
                name = m.group(name_group)
            cmd_matches.append(({"name": name, "framework": framework}, m.start(), m.end()))
    commands = _suppress_overlaps(cmd_matches)

    opt_matches: list[tuple[dict, int, int]] = []
    for pat, framework in _CLI_OPTION_RULES:
        for m in pat.finditer(content):
            if mask.in_string(m.start()):
                continue  # a pattern definition, not a real option anchor (D3)
            opt_matches.append(
                ({"flag": m.group(1), "framework": framework}, m.start(), m.end())
            )
    options = _suppress_overlaps(opt_matches)
    return commands, options


# ---------------------------------------------------------------------------
# Jobs: scheduled and background tasks (confidence 'inferred').
# ---------------------------------------------------------------------------

_JOB_RULES: dict[str, list[tuple[re.Pattern, Optional[int], str]]] = {
    "python": [
        (re.compile(r"@(?:app|celery|[\w.]+)\.task\b"), None, "celery"),
        (re.compile(r"@shared_task\b"), None, "celery"),
        (re.compile(r"@periodic_task\b"), None, "celery"),
        (re.compile(r"@(?:scheduler|sched|[\w.]+)\.scheduled_job\b"), None, "apscheduler"),
        (re.compile(r"@repeat_every\b"), None, "fastapi-utils"),
        (re.compile(r"schedule\.every\("), None, "schedule"),
    ],
    "javascript": [
        (re.compile(r"cron\.schedule\s*\(\s*['\"]([^'\"]+)['\"]"), 1, "node-cron"),
        (re.compile(r"new\s+CronJob\s*\(\s*['\"]([^'\"]+)['\"]"), 1, "cron"),
        (re.compile(r"\bagenda\.define\s*\(\s*['\"]([\w:-]+)['\"]"), 1, "agenda"),
        (re.compile(r"\.process\s*\(\s*['\"]([\w:-]+)['\"]"), 1, "bull"),
    ],
    "typescript": [
        (re.compile(r"cron\.schedule\s*\(\s*['\"]([^'\"]+)['\"]"), 1, "node-cron"),
        (re.compile(r"new\s+CronJob\s*\(\s*['\"]([^'\"]+)['\"]"), 1, "cron"),
        (re.compile(r"@Cron\s*\(\s*['\"]([^'\"]+)['\"]"), 1, "nestjs-schedule"),
        (re.compile(r"\bagenda\.define\s*\(\s*['\"]([\w:-]+)['\"]"), 1, "agenda"),
    ],
    "ruby": [
        (re.compile(r"include\s+Sidekiq::Worker\b"), None, "sidekiq"),
        (re.compile(r"(?m)^\s*class\s+\w+\s*<\s*ApplicationJob\b"), None, "activejob"),
    ],
    "go": [
        (re.compile(r"\.AddFunc\s*\(\s*\"([^\"]+)\""), 1, "robfig-cron"),
    ],
}


def extract_jobs(content: str, language: str) -> list[tuple[dict, int]]:
    """Return ``({"name"/"trigger", "framework"}, match_start)`` job tuples."""
    out: list[tuple[dict, int]] = []
    seen: set = set()
    mask = StringMask(content, language)  # one scan; queried per match (PR #53 nit b)
    for pat, group, framework in _JOB_RULES.get(language, []):
        for m in pat.finditer(content):
            if mask.in_string(m.start()):
                continue  # a pattern definition or docstring example, not usage (D3)
            value: dict = {"framework": framework}
            if group is not None and m.lastindex and group <= m.lastindex:
                token = m.group(group)
                # A cron expression (contains spaces / '*') is a trigger; a bare
                # identifier is a job name.
                if "*" in token or " " in token:
                    value["trigger"] = token
                else:
                    value["name"] = token
            key = (value.get("name"), value.get("trigger"), framework, m.start())
            if key in seen:
                continue
            seen.add(key)
            out.append((value, m.start()))
    return out
