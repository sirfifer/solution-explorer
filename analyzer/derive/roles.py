"""Type promotion, architectural role classification, ports, and names (Tier 3).

Re-expresses ``ArchitectureScanner._promote_component_types``,
``_classify_architectural_role``, ``_is_content_only``,
``_improve_component_names`` and ``_assign_server_ports`` over the store. Config
dependency lists come from the StoreFS shim (cached marker content); framework
markers and ports come from extracted signals already carried on components or
read here. No disk access.
"""

from __future__ import annotations

import os
import re
from typing import Optional

from ..config_parsers import (
    parse_cargo_toml,
    parse_gemfile,
    parse_package_json,
    parse_pyproject_toml,
)
from ..constants import (
    CODE_LANGUAGES,
    CONTENT_DIR_NAMES,
    CONTENT_EXTENSIONS,
    LANGUAGE_MAP,
)
from ..models import Component
from ..utils import _name_from_server_script
from .context import Deriver

# Content-exclusion inversion (P5-2; TARGET-ARCHITECTURE.md section 5). The Data
# lens is sourced from models/migrations/schemas directories, so on the v2 path
# they participate fully in derivation and are NOT classified content-only. v1
# (scanner.py) still reads the shared CONTENT_DIR_NAMES unchanged, so its output
# is byte-stable (parity snapshots green); the inversion lives only here.
_DATA_LENS_DIRS = {"models", "migrations", "schemas"}
_V2_CONTENT_DIR_NAMES = CONTENT_DIR_NAMES - _DATA_LENS_DIRS

# Identity-scoping guards (comprehension-study S2). A component's published
# identity must come from what it IS, not from what its examples and fixtures
# import: a pytest suite importing aiohttp is not an API server, a docs tree
# with an example plugin is not a service, and a scripts directory containing
# one server script is not that server. These sets gate hero-type promotion
# and, for test suites, endpoint/env-var aggregation (derive/docs.py).
TEST_DIR_NAMES = frozenset({
    "tests", "test", "spec", "specs", "__tests__",
    "testing", "test_suite", "e2e", "integration",
})
_TEST_FILE_RE = re.compile(
    r"(?:^|/)(?:test_[^/]+|[^/]+_test\.[^/.]+|[^/]+\.(?:test|spec)\.[^/.]+"
    r"|[^/]+Tests?\.(?:swift|java|kt|cs|m))$"
)
# Documentation trees never promote, including their subdirectories: example
# code inside docs is illustration, not identity.
_DOCS_PATH_SEGMENTS = frozenset({"docs", "doc", "documentation"})
# Example/sample/fixture DIRECTORIES never promote themselves; their children
# may (an example app genuinely is an app, and showing it as one is truthful).
_EXAMPLE_DIR_NAMES = frozenset({
    "examples", "example", "samples", "sample", "fixtures",
})
_UTILITY_DIR_NAMES = frozenset({
    "scripts", "bin", "tools", "utils", "ci", "build", "devops", "deploy",
})


def is_test_suite_component(comp: Component, rel_path: str) -> bool:
    """Whether a component is a test suite by directory name or file share."""
    if os.path.basename(rel_path).lower() in TEST_DIR_NAMES:
        return True
    if not comp.files:
        return False
    matches = sum(1 for f in comp.files if _TEST_FILE_RE.search(f))
    return matches / len(comp.files) > 0.6


def _safe_iterdir(fs_dir) -> list:
    try:
        return list(fs_dir.iterdir())
    except OSError:
        return []


def promote_component_types(d: Deriver) -> None:
    for rel_path, comp in d._component_map.items():
        if rel_path:
            if _is_content_only(d, comp, rel_path):
                comp.type = "content"
                continue
        promoted = _classify_architectural_role(d, comp, rel_path)
        if promoted:
            comp.type = promoted

    hero_types = {
        "ios-client", "android-client", "mobile-client", "web-client",
        "api-server", "watch-app", "desktop-app", "cli-tool", "service",
    }
    subordinate_dirs = {
        "tests", "test", "spec", "specs", "__tests__",
        "static", "public", "dist", "build", "assets",
    }
    for rel_path, comp in d._component_map.items():
        if comp.type not in hero_types:
            continue
        direct_child_hero_types: set[str] = set()
        descendant_hero_types: set[str] = set()
        prefix = (rel_path + os.sep) if rel_path else ""
        for child_path, child_comp in d._component_map.items():
            if not child_path or child_path == rel_path:
                continue
            if prefix and not child_path.startswith(prefix):
                continue
            if os.path.basename(child_path).lower() in subordinate_dirs:
                continue
            if not prefix:
                is_direct = os.sep not in child_path
            else:
                is_direct = child_path[len(prefix):].count(os.sep) == 0
            if child_comp.type in hero_types:
                descendant_hero_types.add(child_comp.type)
                if is_direct:
                    direct_child_hero_types.add(child_comp.type)
        other_direct = direct_child_hero_types - {comp.type}
        other_all = descendant_hero_types - {comp.type}
        if len(other_direct) >= 2:
            comp.type = "package"
        elif len(other_all) >= 3 and len(comp.files) <= 25:
            comp.type = "package"


def _is_content_only(d: Deriver, comp: Component, rel_path: str) -> bool:
    dir_name = os.path.basename(rel_path).lower()
    if dir_name in _V2_CONTENT_DIR_NAMES:
        code_exts = set(LANGUAGE_MAP.keys()) - CONTENT_EXTENSIONS
        code_files = [f for f in comp.files if os.path.splitext(f)[1].lower() in code_exts]
        total = len(comp.files)
        if total == 0 or len(code_files) / max(total, 1) < 0.2:
            return True
    if comp.files:
        content_count = sum(
            1 for f in comp.files
            if os.path.splitext(f)[1].lower() in CONTENT_EXTENSIONS
        )
        if content_count / len(comp.files) > 0.8:
            return True
    return False


def _classify_architectural_role(d: Deriver, comp: Component, rel_path: str) -> Optional[str]:
    framework = (comp.framework or "").lower()
    comp_dir = (d.root / rel_path) if rel_path else d.root
    dir_name = os.path.basename(rel_path).lower()

    # Identity-scoping guards (S2): test suites, documentation trees, and
    # example/fixture directories keep their neutral type no matter what
    # frameworks their contents import. Wrong-but-confident classification is
    # the failure mode this prevents (owner ruling 2026-08-17: resolve or stay
    # neutral, never publish a guess).
    if is_test_suite_component(comp, rel_path):
        return None
    path_segments = {seg.lower() for seg in rel_path.split(os.sep) if seg}
    if path_segments & _DOCS_PATH_SEGMENTS:
        return None
    if dir_name in _EXAMPLE_DIR_NAMES:
        return None

    has_info_plist = (comp_dir / "Info.plist").exists()
    has_xcodeproj = any(
        p.suffix == ".xcodeproj" for p in _safe_iterdir(comp_dir) if p.is_dir()
    ) if comp_dir.is_dir() else False
    has_package_swift = (comp_dir / "Package.swift").exists()
    if not has_xcodeproj and comp.language == "swift" and not has_package_swift:
        parent_dir = comp_dir.parent
        if parent_dir.is_dir() and str(parent_dir) != "":
            has_xcodeproj = any(
                p.suffix == ".xcodeproj" for p in _safe_iterdir(parent_dir) if p.is_dir()
            )
    has_android_manifest = (
        (comp_dir / "AndroidManifest.xml").exists()
        or (comp_dir / "src" / "main" / "AndroidManifest.xml").exists()
    )
    has_build_gradle = (
        (comp_dir / "build.gradle").exists() or (comp_dir / "build.gradle.kts").exists()
    )
    has_package_json = (comp_dir / "package.json").exists()
    has_cargo_toml = (comp_dir / "Cargo.toml").exists()
    has_pubspec = (comp_dir / "pubspec.yaml").exists()

    pkg_deps: set[str] = set()
    if has_package_json:
        pkg_deps = set(parse_package_json(comp_dir / "package.json").get("dependencies", []))
    cargo_deps: set[str] = set()
    if has_cargo_toml:
        cargo_deps = set(parse_cargo_toml(comp_dir / "Cargo.toml").get("dependencies", []))

    if "watch" in dir_name and (comp.language == "swift" or framework in ("swiftui", "watchkit")):
        return "watch-app"

    if framework == "appkit":
        return "desktop-app"
    if framework == "swiftui":
        macos_indicators = {"MenuBarExtra", "NSApplication", "NSWindow",
                            "NSStatusBar", ".menuBarExtraStyle"}
        for fpath in comp.files:
            if not fpath.endswith(".swift"):
                continue
            fc = d.view.content(fpath)
            if fc and any(ind in fc for ind in macos_indicators):
                return "desktop-app"

    if framework in ("swiftui", "uikit"):
        if has_info_plist or has_xcodeproj or comp.type == "application":
            return "ios-client"

    if has_android_manifest:
        return "android-client"
    if has_build_gradle and comp.language in ("java", "kotlin"):
        if has_android_manifest or "android" in dir_name:
            return "android-client"

    if "react-native" in pkg_deps:
        return "mobile-client"

    if has_pubspec:
        content = d.view.content(str(comp_dir / "pubspec.yaml").lstrip("/"))
        if content and "flutter:" in content:
            return "mobile-client"

    if framework == "electron" or "electron" in pkg_deps:
        return "desktop-app"

    server_frameworks = {
        "axum", "actix", "rocket", "warp", "vapor",
        "express", "fastify", "hono", "koa", "nestjs",
        "flask", "django", "fastapi", "starlette", "aiohttp",
        "tornado", "gin", "echo", "fiber", "chi", "gorilla", "beego",
        "rails", "sinatra", "grape", "hanami",
    }
    if framework in server_frameworks:
        return "api-server"

    pure_server_deps = {"express", "fastify", "hono", "koa", "@nestjs/core"}
    client_deps = {"react", "vue", "svelte", "@angular/core"}
    if pkg_deps & pure_server_deps and not (pkg_deps & client_deps):
        return "api-server"

    rust_server_deps = {"axum", "actix-web", "rocket", "warp"}
    if cargo_deps & rust_server_deps:
        return "api-server"

    has_gemfile = (comp_dir / "Gemfile").exists()
    if has_gemfile:
        ruby_deps = set(parse_gemfile(comp_dir / "Gemfile").get("dependencies", []))
        if ruby_deps & {"rails", "sinatra", "grape", "hanami", "roda"}:
            return "api-server"

    # A utility directory (scripts/, tools/, ...) containing one server script
    # must not take that server's name, type, and port as the identity of the
    # whole directory (S2: unamentis/scripts became "Remote Log Server").
    python_files = [f for f in comp.files if f.endswith(".py")]
    if python_files and dir_name not in _UTILITY_DIR_NAMES:
        server_file_patterns = re.compile(
            r'(?:^|/)(?:.*server.*|.*gateway.*|.*daemon.*)\.py$', re.I)
        server_imports = {
            "http.server", "aiohttp", "flask", "fastapi", "tornado",
            "uvicorn", "gunicorn", "starlette", "socketserver",
        }
        for fpath in python_files:
            if server_file_patterns.search(fpath):
                content = d.view.content(fpath)
                if content is None:
                    continue
                for srv_import in server_imports:
                    if f"import {srv_import}" in content or f"from {srv_import}" in content:
                        if not comp.port:
                            port_match = re.search(
                                r'(?:default|port)["\']?\s*[:=]\s*(\d{4,5})', content, re.I)
                            if port_match:
                                comp.port = int(port_match.group(1))
                        if comp.name == dir_name:
                            comp.name = _name_from_server_script(fpath, content)
                        return "service"

    server_languages = {"python", "rust", "go", "ruby", "typescript", "javascript"}
    if (comp.port and comp.language in server_languages
            and not (pkg_deps & client_deps) and dir_name not in _UTILITY_DIR_NAMES):
        return "api-server"

    logging_dir_patterns = {"log", "logger", "logging", "logs", "metrics",
                            "monitor", "telemetry", "observability"}
    if dir_name in logging_dir_patterns and (comp.port or comp.language in server_languages):
        return "service"

    logging_deps = {
        "winston", "pino", "bunyan", "log4js",
        "loguru", "structlog", "python-json-logger",
        "slog", "zap", "logrus", "tracing", "log4rs",
        "sentry-sdk", "@sentry/node", "datadog", "ddtrace",
        "prometheus-client", "prom-client", "opentelemetry",
    }
    if pkg_deps & logging_deps and comp.port:
        return "service"

    web_client_frameworks = {
        "react", "next.js", "vue", "nuxt", "svelte", "sveltekit", "angular",
    }
    if framework in web_client_frameworks:
        return "web-client"
    web_client_deps = {"react", "vue", "svelte", "@angular/core",
                       "next", "nuxt", "@sveltejs/kit"}
    if pkg_deps & web_client_deps:
        return "web-client"

    admin_dir_patterns = {"admin", "dashboard", "console", "portal", "ui",
                          "frontend", "web-client", "webclient"}
    if dir_name in admin_dir_patterns:
        if framework in web_client_frameworks or (pkg_deps & web_client_deps):
            return "web-client"
        if any(f.endswith((".html", ".jsx", ".tsx", ".vue", ".svelte")) for f in comp.files):
            return "web-client"

    if comp.language == "python" and framework in ("click", "typer"):
        return "cli-tool"
    if cargo_deps & {"clap"} and not (cargo_deps & rust_server_deps):
        return "cli-tool"

    return None


def improve_component_names(d: Deriver) -> None:
    for rel_path, comp in d._component_map.items():
        if not rel_path:
            continue
        folder_name = os.path.basename(rel_path)
        if comp.name != folder_name:
            continue
        comp_dir = d.root / rel_path
        if comp.language == "ruby" or (comp.framework and comp.framework.lower() in ("rails", "sinatra", "grape")):
            from ..config_parsers import _extract_ruby_app_name
            name = _extract_ruby_app_name(comp_dir)
            if name:
                comp.name = name
                continue
        if comp.language == "python":
            for cfg_name in ("pyproject.toml", "setup.cfg", "setup.py"):
                cfg_path = comp_dir / cfg_name
                if cfg_path.exists():
                    if cfg_name == "pyproject.toml":
                        info = parse_pyproject_toml(cfg_path)
                    else:
                        continue
                    if info.get("name"):
                        comp.name = info["name"]
                        break


def assign_server_ports(d: Deriver) -> None:
    server_types = {"api-server", "service", "infrastructure"}

    def _first_port_for_component(comp_id: str) -> Optional[int]:
        for fi in d._all_files:
            if fi.language not in CODE_LANGUAGES:
                continue
            fc = d._find_component_for_file(fi.path)
            if fc and fc.id == comp_id:
                for s in d.view.signals(fi.path):
                    if s["kind"] == "port":
                        return (s["value"] or {}).get("port")
        return None

    for comp in d._component_map.values():
        if comp.port or comp.type not in server_types:
            continue
        port = _first_port_for_component(comp.id)
        if port:
            comp.port = port

    for comp in d._component_map.values():
        if comp.port or comp.type not in server_types:
            continue
        for rel_path, child in d._component_map.items():
            if not rel_path:
                continue
            if d._find_parent_component(rel_path) == comp.id:
                port = _first_port_for_component(child.id)
                if port:
                    comp.port = port
                    break
        if comp.port:
            continue
