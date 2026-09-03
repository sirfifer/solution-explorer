"""Identity facts: what the repository is to a person (Tier 3).

The overview used to open on a sentence about the snapshot. A first-time reader
needs to know whether the subject is a desktop program, a phone app, a web site
or a server before any count means anything, and the repository already says so
in its own markers: an Electron dependency, a product.json carrying platform
identifiers, an Xcode project, a Cargo binary table, a directory of extension
manifests. This pass reads those markers through the store and records the
form-factor facts, the maintainers' own first paragraph, the language shares and
the external services. The projection tier composes them into one plain sentence
(analyzer/project/human_views.py), so the viewer's fallback can never disagree
with the sidecar.

Nothing is asserted without a file to point at. A detector that finds no marker
yields no record, and a subject with no records leaves the viewer on its old
headline. That is the whole honesty contract of the front door.
"""

from __future__ import annotations

import json
import os
import re
from typing import Optional

from ..constants import CODE_LANGUAGES
from .context import Deriver

__all__ = ["derive_identity"]

# Detector order. It is the tie-break for equal weights and, more importantly,
# the order the composed sentence reads its secondary clauses in, so that a
# subject that is a desktop app, a web app, a CLI and a plug-in host always
# describes itself in that order however the file counts fall.
KIND_ORDER = (
    "desktop-app",
    "ios-app",
    "watch-app",
    "android-app",
    "web-app",
    "cli",
    "server",
    "plugin-host",
    "infrastructure",
    "library",
)

_LABELS = {
    "desktop-app": "Desktop application",
    "ios-app": "iOS app",
    "watch-app": "Watch app",
    "android-app": "Android app",
    "web-app": "Web application",
    "cli": "Command-line tool",
    "server": "Server",
    "plugin-host": "Extensible by plug-ins",
    "infrastructure": "Infrastructure",
    "library": "Library",
}

_HOW_MET = {
    "desktop-app": "installed and opened on a computer",
    "ios-app": "installed from the App Store on a phone or tablet",
    "watch-app": "installed on a watch",
    "android-app": "installed on a phone or tablet",
    "web-app": "opened in a web browser",
    "cli": "run from a terminal",
    "server": "deployed and reached over the network",
    "plugin-host": "extended by plug-ins",
    "infrastructure": "deployed as infrastructure",
    "library": "used by other programs",
}

_MAX_RECORDS = 8
_MAX_EVIDENCE = 6
_MAX_GO_BINARIES = 12
_CLAIM_LIMIT = 400

_DESKTOP_DEPS = ("electron", "tauri", "@tauri-apps/api")
_WEB_FRAMEWORK_DEPS = ("next", "nuxt", "@sveltejs/kit", "vite", "react-scripts")
_PRODUCT_PLATFORM_KEYS = (
    ("darwinBundleIdentifier", "macos"),
    ("win32x64AppId", "windows"),
    ("win32arm64AppId", "windows"),
    ("linuxIconName", "linux"),
)
_PLATFORM_ORDER = ("macos", "windows", "linux", "ios", "watchos", "android", "browser")
_APPLE_UI_FRAMEWORKS = {"swiftui", "uikit"}
_SERVER_ROOT_FILES = ("Dockerfile", "Procfile")
_KUBERNETES_KIND = re.compile(r"^kind:\s*(?:Deployment|Service|StatefulSet|DaemonSet)\s*$", re.M)
_CLOUDFORMATION = re.compile(r"AWSTemplateFormatVersion")
_YAML_SUFFIXES = (".yaml", ".yml")
_SKIP_PATH_PARTS = ("/node_modules/", "/.git/")


# ---------------------------------------------------------------------------
# small readers over the store
# ---------------------------------------------------------------------------

def _skipped(path: str) -> bool:
    padded = f"/{path}"
    return any(part in padded for part in _SKIP_PATH_PARTS)


def _load_json(text: Optional[str]) -> Optional[dict]:
    """Parse cached JSON, tolerating whatever a repository actually ships."""
    if not text:
        return None
    try:
        value = json.loads(text)
    except (ValueError, RecursionError):
        return None
    return value if isinstance(value, dict) else None


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _object_span(text: str, key: str) -> Optional[tuple[int, int]]:
    """Character span of the object value for ``key``, by brace matching.

    Line numbers are evidence, so they must point at the key inside the section
    that actually proves the claim. VS Code names ``electron`` in ``scripts``
    130 lines before it names it in ``devDependencies``; a plain text search
    would cite the wrong one.
    """
    needle = f'"{key}"'
    start = text.find(needle)
    while start != -1:
        colon = text.find(":", start + len(needle))
        brace = text.find("{", start + len(needle))
        if colon != -1 and brace != -1 and colon < brace and not text[colon + 1:brace].strip():
            depth = 0
            in_string = False
            escaped = False
            index = brace
            while index < len(text):
                char = text[index]
                if in_string:
                    if escaped:
                        escaped = False
                    elif char == "\\":
                        escaped = True
                    elif char == '"':
                        in_string = False
                elif char == '"':
                    in_string = True
                elif char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        return (brace, index)
                index += 1
        start = text.find(needle, start + 1)
    return None


def _key_line(text: str, key: str, span: Optional[tuple[int, int]] = None) -> Optional[int]:
    low, high = span if span else (0, len(text))
    index = text.find(f'"{key}"', low, high)
    return _line_of(text, index) if index != -1 else None


def _pattern_line(text: str, pattern: str) -> Optional[int]:
    match = re.search(pattern, text, re.M)
    return _line_of(text, match.start()) if match else None


# ---------------------------------------------------------------------------
# the working context: components, weights and cached manifests
# ---------------------------------------------------------------------------

class _Facts:
    """Everything the detectors read, resolved once per run."""

    def __init__(self, d: Deriver) -> None:
        self.d = d
        self.paths = list(d.view.all_paths)
        self.path_set = set(self.paths)
        self.total_mapped_files = len(d._all_files)
        # Component paths sorted longest first, so a file resolves to its
        # nearest owning component rather than the repository root.
        self.component_paths = sorted(d._component_map, key=lambda p: (-len(p), p))
        self.weights = self._weights()

    def _weights(self) -> dict[str, int]:
        """Mapped files under each component, including its nested components.

        A form factor's weight ranks it against the others, so it must count the
        subtree a marker speaks for: the root's markers speak for the whole
        repository, and ``src/vs/workbench`` speaks for the workbench tree.
        """
        weights: dict[str, int] = {}
        for path, component in self.d._component_map.items():
            prefix = f"{path}/" if path else ""
            total = 0
            for other_path, other in self.d._component_map.items():
                if other_path == path or (prefix and other_path.startswith(prefix)) or not prefix:
                    total += len(other.files)
            weights[component.id] = total
        return weights

    # -- lookups ---------------------------------------------------------

    def component(self, path: str):
        return self.d._component_map.get(path)

    def component_id(self, path: str) -> str:
        component = self.component(path)
        return component.id if component else "root"

    def owning_component_id(self, file_path: str) -> str:
        """The id of the nearest component that contains ``file_path``."""
        directory = os.path.dirname(file_path)
        while True:
            if directory in self.d._component_map:
                return self.d._component_map[directory].id
            if not directory:
                break
            directory = os.path.dirname(directory)
        return self.component_id("")

    def weight(self, component_id: str) -> int:
        return self.weights.get(component_id, self.total_mapped_files)

    def evidence_weight(self, component_id: str, evidence: list[dict]) -> int:
        """What this record speaks for, in mapped files.

        Normally the component the marker belongs to. A marker that lives in a
        subtree the repository never made a component of (a bare ``extensions/``
        directory, say) falls back to the root component, and weighing it as the
        whole repository would rank a side feature above the product itself. In
        that case count only the components the evidence actually sits in.
        """
        if component_id != self.component_id("") or not evidence:
            return self.weight(component_id)
        if any("/" not in item.get("file", "") for item in evidence):
            return self.weight(component_id)
        owners = {self.owning_component_id(item["file"]) for item in evidence}
        owner_paths = sorted(
            path for path, component in self.d._component_map.items()
            if component.id in owners
        )
        outermost = [
            path for path in owner_paths
            if not any(path.startswith(f"{other}/") for other in owner_paths if other != path)
        ]
        total = sum(self.weight(self.component_id(path)) for path in outermost)
        return total or self.weight(component_id)

    def content(self, path: str) -> Optional[str]:
        return self.d.view.content(path)

    def exists(self, path: str) -> bool:
        return path in self.path_set

    def components_typed(self, *types: str) -> list[tuple[str, object]]:
        wanted = {t.lower() for t in types}
        return [
            (path, component)
            for path, component in sorted(self.d._component_map.items())
            if str(getattr(component, "type", "") or "").lower() in wanted
        ]

    def manifest_paths(self, filename: str) -> list[str]:
        """Every ``filename`` that sits at a component root, root first."""
        out = []
        for path in sorted(self.d._component_map):
            candidate = f"{path}/{filename}" if path else filename
            if self.content(candidate) is not None:
                out.append(candidate)
        return out

    def files_named(self, filename: str, limit: int = 400) -> list[str]:
        base = filename.lower()
        out = []
        for path in self.paths:
            if _skipped(path):
                continue
            if os.path.basename(path).lower() == base:
                out.append(path)
                if len(out) >= limit:
                    break
        return out

    def files_with_suffix(self, suffix: str, limit: int = 400) -> list[str]:
        out = []
        for path in self.paths:
            if _skipped(path):
                continue
            if path.lower().endswith(suffix):
                out.append(path)
                if len(out) >= limit:
                    break
        return out


def _record(
    kind: str,
    component_id: str,
    evidence: list[dict],
    *,
    platforms: Optional[list[str]] = None,
    platforms_assumed: bool = False,
    name: Optional[str] = None,
) -> dict:
    row = {
        "kind": kind,
        "label": _LABELS[kind],
        "platforms": list(platforms or []),
        "platforms_assumed": bool(platforms_assumed),
        "how_met": _HOW_MET[kind],
        "component_id": component_id,
        "evidence": evidence,
        "statement_kind": "observed_source_reference",
    }
    if name:
        row["name"] = name
    return row


def _evidence(file: str, marker: str, line: Optional[int] = None) -> dict:
    row = {"file": file, "marker": marker}
    if line is not None:
        row["line"] = line
    return row


def _marker_file_for(
    facts: _Facts,
    path: str,
    component,
    preferred: tuple[str, ...],
    *,
    require_marker: bool = False,
) -> Optional[str]:
    """A real file under ``component`` that stands for its declared type.

    A component-type detector still owes the reader a file. Prefer a manifest
    the type was read from, then the component's own config files, then its
    first mapped file.

    ``require_marker`` refuses that last fallback. "This is a server, and here is
    a shell-completion source file to prove it" is not evidence, it is a file
    picked because one was needed, and the run that found VS Code's
    terminal-suggest completions typed api-server on a port scraped out of a
    string is exactly the case it produced. A claim about how software is run
    has to point at something that declares how it is run.
    """
    prefix = f"{path}/" if path else ""
    for name in preferred:
        candidate = f"{prefix}{name}"
        if facts.exists(candidate):
            return candidate
    for config in getattr(component, "config_files", None) or []:
        config_path = config.get("path") if isinstance(config, dict) else None
        if config_path and facts.exists(config_path):
            return config_path
    if require_marker:
        return None
    files = sorted(getattr(component, "files", None) or [])
    return files[0] if files else None


# ---------------------------------------------------------------------------
# detectors, one per form factor
# ---------------------------------------------------------------------------

def _detect_desktop_app(facts: _Facts) -> list[dict]:
    records: list[dict] = []

    product = facts.content("product.json")
    if product is not None and _load_json(product) is not None:
        data = _load_json(product) or {}
        platforms: list[str] = []
        evidence: list[dict] = []
        for key, platform in _PRODUCT_PLATFORM_KEYS:
            if key in data:
                if platform not in platforms:
                    platforms.append(platform)
                evidence.append(_evidence("product.json", key, _key_line(product, key)))
        if platforms:
            records.append(_record(
                "desktop-app", facts.component_id(""), evidence,
                platforms=[p for p in _PLATFORM_ORDER if p in platforms],
            ))

    for manifest_path in facts.manifest_paths("package.json"):
        text = facts.content(manifest_path) or ""
        data = _load_json(text)
        if data is None:
            continue
        for section in ("dependencies", "devDependencies"):
            block = data.get(section)
            if not isinstance(block, dict):
                continue
            span = _object_span(text, section)
            for dependency in _DESKTOP_DEPS:
                if dependency not in block:
                    continue
                directory = os.path.dirname(manifest_path)
                records.append(_record(
                    "desktop-app", facts.component_id(directory),
                    [_evidence(manifest_path, f"{section}.{dependency}",
                               _key_line(text, dependency, span))],
                    platforms=["macos", "windows", "linux"], platforms_assumed=True,
                ))

    for path, component in facts.components_typed("desktop-app"):
        marker = _marker_file_for(facts, path, component, ("package.json", "tauri.conf.json"))
        if marker:
            records.append(_record(
                "desktop-app", component.id,
                [_evidence(marker, "component typed desktop-app")],
                platforms=["macos", "windows", "linux"], platforms_assumed=True,
            ))
    return records


def _detect_ios_app(facts: _Facts) -> list[dict]:
    records: list[dict] = []
    for path, component in facts.components_typed("ios-client", "mobile-client"):
        marker = _marker_file_for(facts, path, component, ("Info.plist", "Package.swift"))
        if marker is None:
            prefix = f"{path}/" if path else ""
            plists = [p for p in facts.files_named("Info.plist") if p.startswith(prefix)]
            marker = plists[0] if plists else None
        if marker:
            records.append(_record(
                "ios-app", component.id,
                [_evidence(marker, f"component typed {component.type}")],
                platforms=["ios"],
            ))

    for plist in facts.files_named("Info.plist", limit=40):
        owner = facts.owning_component_id(plist)
        component = next(
            (c for c in facts.d._component_map.values() if c.id == owner), None
        )
        framework = str(getattr(component, "framework", "") or "").lower()
        # A watch or Mac target is built with the same frameworks, and its own
        # detector states the sharper truth. Claiming it is also an iPhone app
        # would put two chips on the page for one binary.
        already_placed = str(getattr(component, "type", "") or "").lower() in {
            "watch-app", "desktop-app", "android-client",
        }
        if framework in _APPLE_UI_FRAMEWORKS and not already_placed:
            records.append(_record(
                "ios-app", owner,
                [_evidence(plist, f"Info.plist under a {component.framework} component")],
                platforms=["ios"],
            ))
    return records


def _detect_watch_app(facts: _Facts) -> list[dict]:
    records: list[dict] = []
    for path, component in facts.components_typed("watch-app"):
        marker = _marker_file_for(facts, path, component, ("Info.plist",))
        if marker:
            records.append(_record(
                "watch-app", component.id,
                [_evidence(marker, "component typed watch-app")],
                platforms=["watchos"],
            ))
    return records


def _detect_android_app(facts: _Facts) -> list[dict]:
    records: list[dict] = []
    for path, component in facts.components_typed("android-client"):
        marker = _marker_file_for(facts, path, component, ("AndroidManifest.xml", "build.gradle"))
        if marker:
            records.append(_record(
                "android-app", component.id,
                [_evidence(marker, "component typed android-client")],
                platforms=["android"],
            ))
    for manifest in facts.files_named("AndroidManifest.xml", limit=20):
        records.append(_record(
            "android-app", facts.owning_component_id(manifest),
            [_evidence(manifest, "AndroidManifest.xml")],
            platforms=["android"],
        ))
    return records


def _html_entry_rank(path: str) -> tuple:
    """Rank HTML candidates so the browser entry document wins, not a fixture.

    Two conventions decide it, in this order. An entry document is named
    ``index.html`` or after the directory it opens (``workbench/workbench.html``),
    and it sits nearer the top of the tree than the shims and fixtures beneath
    it. On VS Code that picks ``src/vs/code/browser/workbench/workbench.html``
    over a webview's ``pre/index.html`` two directories deeper.
    """
    directory = os.path.dirname(path)
    stem = os.path.splitext(os.path.basename(path))[0].lower()
    is_test = 1 if re.search(r"(?:^|/)(?:tests?|fixtures?)(?:/|$)", directory) else 0
    entry_convention = 0 if stem in ("index", os.path.basename(directory).lower()) else 1
    return (is_test, entry_convention, path.count("/"), path)


def _detect_web_app(facts: _Facts) -> list[dict]:
    records: list[dict] = []

    web_components = facts.components_typed("web-client")
    if web_components:
        path, component = max(
            web_components, key=lambda row: (facts.weight(row[1].id), row[0])
        )
        prefix = f"{path}/" if path else ""
        candidates = [
            html for html in facts.files_with_suffix(".html")
            if "/browser/" in f"/{html}" or html == f"{prefix}index.html"
        ]
        if candidates:
            best = min(candidates, key=_html_entry_rank)
            records.append(_record(
                "web-app", component.id,
                [_evidence(best, "html entry")],
                platforms=["browser"],
            ))

    root_manifest = "package.json"
    text = facts.content(root_manifest)
    data = _load_json(text)
    if data:
        for section in ("dependencies", "devDependencies"):
            block = data.get(section)
            if not isinstance(block, dict):
                continue
            span = _object_span(text or "", section)
            for framework in _WEB_FRAMEWORK_DEPS:
                if framework in block:
                    records.append(_record(
                        "web-app", facts.component_id(""),
                        [_evidence(root_manifest, f"{section}.{framework}",
                                   _key_line(text or "", framework, span))],
                        platforms=["browser"],
                    ))
    return records


def _detect_cli(facts: _Facts) -> list[dict]:
    records: list[dict] = []

    for path, component in facts.components_typed("cli-tool"):
        marker = _marker_file_for(
            facts, path, component, ("Cargo.toml", "package.json", "pyproject.toml", "setup.py"),
            require_marker=True,
        )
        if marker:
            records.append(_record(
                "cli", component.id, [_evidence(marker, "component typed cli-tool")],
            ))

    for manifest_path in facts.manifest_paths("package.json"):
        text = facts.content(manifest_path) or ""
        data = _load_json(text)
        if data and data.get("bin"):
            records.append(_record(
                "cli", facts.component_id(os.path.dirname(manifest_path)),
                [_evidence(manifest_path, "bin", _key_line(text, "bin"))],
            ))

    for manifest_path in facts.manifest_paths("Cargo.toml"):
        text = facts.content(manifest_path) or ""
        directory = os.path.dirname(manifest_path)
        main_rs = f"{directory}/src/main.rs" if directory else "src/main.rs"
        if "[[bin]]" in text:
            records.append(_record(
                "cli", facts.component_id(directory),
                [_evidence(manifest_path, "[[bin]]", _pattern_line(text, r"^\[\[bin\]\]"))],
            ))
        elif facts.exists(main_rs):
            records.append(_record(
                "cli", facts.component_id(directory), [_evidence(main_rs, "src/main.rs")],
            ))

    for manifest_path in facts.manifest_paths("pyproject.toml"):
        text = facts.content(manifest_path) or ""
        if "[project.scripts]" in text:
            records.append(_record(
                "cli", facts.component_id(os.path.dirname(manifest_path)),
                [_evidence(manifest_path, "[project.scripts]",
                           _pattern_line(text, r"^\[project\.scripts\]"))],
            ))

    for manifest_path in facts.manifest_paths("setup.py"):
        text = facts.content(manifest_path) or ""
        if "console_scripts" in text:
            records.append(_record(
                "cli", facts.component_id(os.path.dirname(manifest_path)),
                [_evidence(manifest_path, "console_scripts",
                           _pattern_line(text, r"console_scripts"))],
            ))

    if facts.exists("go.mod"):
        binaries = sorted(
            path for path in facts.paths
            if path.startswith("cmd/") and path.endswith("/main.go")
            and path.count("/") == 2 and not _skipped(path)
        )
        truncated = binaries[_MAX_GO_BINARIES:]
        for main_go in binaries[:_MAX_GO_BINARIES]:
            binary = main_go.split("/")[1]
            records.append(_record(
                "cli", facts.owning_component_id(main_go),
                [_evidence(main_go, f"cmd/{binary}/main.go")], name=binary,
            ))
        if truncated:
            records[-1]["truncated"] = True
    return records


def _detect_server(facts: _Facts) -> list[dict]:
    records: list[dict] = []

    for path, component in facts.components_typed("api-server", "service", "server"):
        if not getattr(component, "port", None):
            continue
        marker = _marker_file_for(
            facts, path, component,
            ("Dockerfile", "docker-compose.yml", "docker-compose.yaml", "Procfile",
             "package.json", "pyproject.toml", "go.mod", "Cargo.toml"),
            require_marker=True,
        )
        if marker:
            records.append(_record(
                "server", component.id,
                [_evidence(marker, f"component typed {component.type} on port {component.port}")],
            ))

    for name in _SERVER_ROOT_FILES:
        if facts.exists(name):
            records.append(_record(
                "server", facts.component_id(""), [_evidence(name, name)],
            ))
    for path in facts.paths:
        base = os.path.basename(path)
        if path == base and base.startswith("docker-compose") and base.endswith(_YAML_SUFFIXES):
            records.append(_record(
                "server", facts.component_id(""), [_evidence(path, "docker-compose")],
            ))

    for path in facts.files_with_suffix(".yaml") + facts.files_with_suffix(".yml"):
        if facts.d._is_under_vendored(path):
            continue
        text = facts.content(path)
        if not text:
            continue
        match = _KUBERNETES_KIND.search(text)
        if match:
            records.append(_record(
                "server", facts.owning_component_id(path),
                [_evidence(path, match.group(0).strip(), _line_of(text, match.start()))],
            ))
            break
    return records


def _detect_plugin_host(facts: _Facts) -> list[dict]:
    records: list[dict] = []

    for root in ("extensions", "plugins"):
        manifests = [
            path for path in facts.paths
            if path.startswith(f"{root}/") and os.path.basename(path) == "package.json"
            and not _skipped(path)
        ]
        contributing = []
        for path in sorted(manifests):
            data = _load_json(facts.content(path))
            if data and ("contributes" in data or "vscode" in (data.get("engines") or {})):
                contributing.append(path)
        if len(contributing) >= 3:
            text_evidence = []
            for path in contributing[:3]:
                text = facts.content(path) or ""
                marker = "contributes" if '"contributes"' in text else "engines.vscode"
                text_evidence.append(_evidence(path, marker, _key_line(text, marker.split(".")[-1])))
            records.append(_record(
                "plugin-host", facts.component_id(root), text_evidence,
            ))

    for path, component in facts.components_typed("vscode-extension"):
        marker = _marker_file_for(facts, path, component, ("package.json",))
        if marker:
            records.append(_record(
                "plugin-host", component.id,
                [_evidence(marker, "component typed vscode-extension")],
            ))
    return records


def _detect_infrastructure(facts: _Facts) -> list[dict]:
    records: list[dict] = []
    for chart in facts.files_named("Chart.yaml", limit=20):
        records.append(_record(
            "infrastructure", facts.owning_component_id(chart),
            [_evidence(chart, "Helm Chart.yaml")],
        ))
        break
    terraform = facts.files_with_suffix(".tf", limit=20)
    if terraform:
        records.append(_record(
            "infrastructure", facts.owning_component_id(terraform[0]),
            [_evidence(terraform[0], "terraform")],
        ))
    for path in facts.files_with_suffix(".yaml", limit=200) + facts.files_with_suffix(".json", limit=200):
        text = facts.content(path)
        if text and _CLOUDFORMATION.search(text):
            records.append(_record(
                "infrastructure", facts.owning_component_id(path),
                [_evidence(path, "AWSTemplateFormatVersion",
                           _pattern_line(text, "AWSTemplateFormatVersion"))],
            ))
            break
    return records


def _detect_library(facts: _Facts) -> list[dict]:
    """The fallback, and only when nothing a person opens or runs was found."""
    root_id = facts.component_id("")
    package = _load_json(facts.content("package.json"))
    if package and (package.get("main") or package.get("exports")):
        text = facts.content("package.json") or ""
        key = "main" if package.get("main") else "exports"
        return [_record("library", root_id, [_evidence("package.json", key, _key_line(text, key))])]
    for name in ("pyproject.toml", "setup.py"):
        if facts.exists(name):
            return [_record("library", root_id, [_evidence(name, name)])]
    cargo = facts.content("Cargo.toml")
    if cargo is not None and "[lib]" in cargo:
        return [_record("library", root_id,
                        [_evidence("Cargo.toml", "[lib]", _pattern_line(cargo, r"^\[lib\]"))])]
    if facts.exists("go.mod"):
        return [_record("library", root_id, [_evidence("go.mod", "go.mod")])]
    return []


_DETECTORS = (
    ("desktop-app", _detect_desktop_app),
    ("ios-app", _detect_ios_app),
    ("watch-app", _detect_watch_app),
    ("android-app", _detect_android_app),
    ("web-app", _detect_web_app),
    ("cli", _detect_cli),
    ("server", _detect_server),
    ("plugin-host", _detect_plugin_host),
    ("infrastructure", _detect_infrastructure),
)


# ---------------------------------------------------------------------------
# merging
# ---------------------------------------------------------------------------

def _merge(facts: _Facts, records: list[dict]) -> tuple[list[dict], bool]:
    """One record per kind per component, then collapse nested restatements.

    Two components can prove the same thing about the same subtree: VS Code
    types both ``extensions`` and ``extensions/copilot``, and UnaMentis types
    both the repository root and ``UnaMentis`` as an iOS client. Showing the
    reader two identical chips is the count-noise defect this front door exists
    to remove, so a record whose component sits inside another record's
    component of the same kind folds into it and hands over its evidence.
    """
    merged: dict[tuple, dict] = {}
    for row in records:
        key = (row["kind"], row["component_id"], row.get("name"))
        existing = merged.get(key)
        if existing is None:
            merged[key] = dict(row)
            continue
        for item in row["evidence"]:
            if item not in existing["evidence"]:
                existing["evidence"].append(item)
        if row["platforms"] and not row["platforms_assumed"]:
            existing["platforms"] = row["platforms"]
            existing["platforms_assumed"] = False
        elif not existing["platforms"]:
            existing["platforms"] = row["platforms"]

    id_to_path = {c.id: path for path, c in facts.d._component_map.items()}
    rows = list(merged.values())
    absorbed: set[int] = set()
    for index, row in enumerate(rows):
        for other_index, other in enumerate(rows):
            if index == other_index or other_index in absorbed or index in absorbed:
                continue
            if row["kind"] != other["kind"] or row.get("name") != other.get("name"):
                continue
            row_path = id_to_path.get(row["component_id"])
            other_path = id_to_path.get(other["component_id"])
            if row_path is None or other_path is None:
                continue
            inside = other_path == "" or (row_path or "").startswith(f"{other_path}/")
            if inside and row_path != other_path:
                for item in row["evidence"]:
                    if item not in other["evidence"]:
                        other["evidence"].append(item)
                absorbed.add(index)
    rows = [row for index, row in enumerate(rows) if index not in absorbed]

    for row in rows:
        # Shallowest file first. A merged record can hold a root manifest and a
        # marker from a nested component, and the cap must not spend itself on
        # the nested ones before it reaches product.json.
        row["evidence"] = sorted(
            row["evidence"],
            key=lambda item: (item["file"].count("/"), item["file"], item.get("line") or 0),
        )[:_MAX_EVIDENCE]
        row["weight"] = facts.evidence_weight(row["component_id"], row["evidence"])

    rows.sort(key=lambda row: (-row["weight"], KIND_ORDER.index(row["kind"]),
                               row["component_id"], row.get("name") or ""))
    truncated = any(row.pop("truncated", False) for row in rows) or len(rows) > _MAX_RECORDS
    return rows[:_MAX_RECORDS], truncated


# ---------------------------------------------------------------------------
# the maintainers' own words
# ---------------------------------------------------------------------------

_README_NAMES = ("README.md", "README.rst", "README.txt", "README")
_BADGE_LINE = re.compile(r"^\s*(?:\[!\[|!\[|<img|<a\b|<p\b|<div\b|<br)", re.I)
_LIST_LINE = re.compile(r"^\s*(?:[-*+]\s|\d+[.)]\s|\|)")
_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _clean_prose(text: str) -> str:
    text = _MD_IMAGE.sub("", text)
    text = _MD_LINK.sub(r"\1", text)
    text = text.replace("`", "")
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _cap_on_sentence(text: str, limit: int = _CLAIM_LIMIT) -> str:
    if len(text) <= limit:
        return text
    kept = ""
    for sentence in _SENTENCE_END.split(text):
        candidate = f"{kept} {sentence}".strip() if kept else sentence
        if len(candidate) > limit:
            break
        kept = candidate
    if kept:
        return kept
    bounded = text[:limit]
    space = bounded.rfind(" ")
    return bounded[:space] if space > 0 else bounded


def _authors_claim(facts: _Facts) -> Optional[dict]:
    """The README's first prose paragraph, quoted as the authors' claim.

    The repository's own description is a claim to be checked, never the truth,
    so it is recorded with its file and line and labelled as such. Headings,
    badge rows, HTML blocks, block quotes and lists are skipped because none of
    them is the sentence a maintainer wrote to explain the project.
    """
    source = None
    content = None
    root = facts.component("")
    docs_readme = (getattr(root, "docs", None) or {}).get("readme") if root else None
    for name in _README_NAMES:
        text = facts.content(name)
        if text is not None:
            source, content = name, text
            break
    if content is None and docs_readme:
        source, content = "README.md", docs_readme
    if content is None:
        return None

    lines = content.split("\n")
    in_fence = False
    buffer: list[str] = []
    start_line = 0
    for index, raw in enumerate(lines, start=1):
        line = raw.strip()
        if line.startswith("```") or line.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        skip = (
            not line
            or line.startswith("#")
            or line.startswith(">")
            or line.startswith("=")
            or line.startswith("---")
            or bool(_BADGE_LINE.match(raw))
            or bool(_LIST_LINE.match(raw))
        )
        if skip:
            if buffer:
                break
            continue
        if not buffer:
            start_line = index
        buffer.append(line)

    paragraph = _clean_prose(" ".join(buffer))
    if len(paragraph) < 40 or "." not in paragraph:
        return None
    return {
        "text": _cap_on_sentence(paragraph),
        "source": source,
        "line": start_line,
        "statement_kind": "repository_claim",
    }


# ---------------------------------------------------------------------------
# languages and external services
# ---------------------------------------------------------------------------

def _languages(facts: _Facts) -> list[dict]:
    """The top three languages by mapped lines, code languages only.

    A reader asking what a system is written in does not mean its JSON payloads
    or its Markdown. The metrics pass already picks a component's dominant
    language among code languages for the same reason; this follows it, and
    falls back to every counted language when a repository has no code at all.
    """
    counts = dict(facts.d._language_counts)
    if not counts:
        for info in facts.d._all_files:
            counts[info.language or ""] = counts.get(info.language or "", 0) + (info.lines or 0)
    code = {name: lines for name, lines in counts.items() if name in CODE_LANGUAGES and lines}
    pick = code or {name: lines for name, lines in counts.items() if name and lines}
    total = sum(pick.values())
    if not total:
        return []
    ranked = sorted(pick.items(), key=lambda row: (-row[1], row[0]))[:3]
    return [{"language": name, "share": round(lines / total, 2)} for name, lines in ranked]


def _external_services(facts: _Facts) -> list[dict]:
    seen: dict[str, dict] = {}
    ordered = sorted(
        facts.d._component_map.values(),
        key=lambda component: (-facts.weight(component.id), component.id),
    )
    for component in ordered:
        for service in getattr(component, "external_services", None) or []:
            name = (service or {}).get("name") if isinstance(service, dict) else None
            if name and name not in seen:
                seen[name] = {"name": name, "component_id": component.id}
    return list(seen.values())[:8]


# ---------------------------------------------------------------------------
# the pass
# ---------------------------------------------------------------------------

def derive_identity(d: Deriver, *, iso=None) -> dict:
    """Record what the repository is to a person, from its own markers.

    ``iso`` is the driver's isolator. Each detector runs under it so a single
    marker reader that trips over an unexpected manifest records an honest gap
    and the other form factors still reach the reader; the driver isolates the
    pass as a whole on top of that.
    """
    facts = _Facts(d)

    collected: list[dict] = []
    for kind, detector in _DETECTORS:
        if iso is not None:
            collected.extend(iso.run(f"derive.identity.{kind}", detector, facts, default=[]) or [])
        else:
            collected.extend(detector(facts) or [])

    if not collected:
        collected.extend(_detect_library(facts))

    form_factors, truncated = _merge(facts, collected)
    return {
        "form_factors": form_factors,
        "primary": form_factors[0]["kind"] if form_factors else None,
        "authors_claim": _authors_claim(facts),
        "languages": _languages(facts),
        "external_services": _external_services(facts),
        "truncated": truncated,
    }
