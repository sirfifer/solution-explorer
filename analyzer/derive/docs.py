"""Component documentation extraction (Tier 3).

Re-expresses ``ArchitectureScanner._extract_component_docs`` and
``_detect_patterns`` over the store: doc files (README, CLAUDE.md, changelog,
docs/) come from cached content; env vars and API endpoints come from the
extracted ``env_var`` and ``endpoint`` signals instead of a per-file reparse;
purpose comes from cached config content.
"""

from __future__ import annotations

import json
import os
import re

from ..constants import LANGUAGE_MAP
from ..models import ComponentDoc, to_dict
from .context import Deriver


def extract_component_docs(d: Deriver) -> None:
    for rel_path, comp in d._component_map.items():
        comp_dir = rel_path
        doc = ComponentDoc()

        doc_file_map = {
            "readme": ("README.md", "README.rst", "README.txt", "README"),
            "claude_md": ("CLAUDE.md",),
            "changelog": ("CHANGELOG.md", "CHANGES.md", "HISTORY.md"),
        }
        for field_name, candidates in doc_file_map.items():
            for fname in candidates:
                rel = f"{comp_dir}/{fname}" if comp_dir else fname
                content = d.view.content(rel)
                if content is not None:
                    if len(content) > 8000:
                        content = content[:8000] + "\n\n... (truncated)"
                    setattr(doc, field_name, content)
                    break

        _architecture_notes(d, doc, comp_dir)
        _purpose(d, doc, comp)
        _signals_docs(d, doc, comp)
        doc.patterns = detect_patterns(comp)
        doc.tech_stack = _tech_stack(d, comp)
        comp.docs = to_dict(doc)


def _architecture_notes(d: Deriver, doc: ComponentDoc, comp_dir: str) -> None:
    docs_dir = f"{comp_dir}/docs" if comp_dir else "docs"
    if docs_dir not in d.view.dir_paths:
        docs_dir = f"{comp_dir}/doc" if comp_dir else "doc"
    if docs_dir not in d.view.dir_paths:
        return
    arch_notes = []
    prefix = f"{docs_dir}/"
    names = sorted(p for p in d.view.all_paths
                   if p.startswith(prefix) and "/" not in p[len(prefix):])
    for rel in names:
        if not rel.endswith((".md", ".txt", ".rst")):
            continue
        content = d.view.content(rel)
        if content is None:
            continue
        heading = ""
        summary_lines = []
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("#") and not heading:
                heading = stripped.lstrip("#").strip()
            elif heading and stripped:
                summary_lines.append(stripped)
                if len(summary_lines) >= 3:
                    break
            elif heading and not stripped and summary_lines:
                break
        if heading:
            arch_notes.append(f"**{heading}** ({os.path.basename(rel)}): {' '.join(summary_lines)}")
    if arch_notes:
        doc.architecture_notes = "\n\n".join(arch_notes[:20])


def _purpose(d: Deriver, doc: ComponentDoc, comp) -> None:
    for cfg in comp.config_files:
        cfg_path = cfg.get("path", "") if isinstance(cfg, dict) else ""
        if not cfg_path:
            continue
        content = d.view.content(cfg_path)
        if content is None:
            continue
        basename = os.path.basename(cfg_path)
        if basename == "package.json":
            try:
                desc = json.loads(content).get("description", "")
                if desc:
                    doc.purpose = desc
            except json.JSONDecodeError:
                pass
        elif basename in ("Cargo.toml", "pyproject.toml", "setup.cfg"):
            m = re.search(r'description\s*=\s*"([^"]+)"', content)
            if m:
                doc.purpose = m.group(1)


def _signals_docs(d: Deriver, doc: ComponentDoc, comp) -> None:
    seen_ep = set()
    for file_path in comp.files[:100]:
        ext = os.path.splitext(file_path)[1].lower()
        if not LANGUAGE_MAP.get(ext):
            continue
        for s in d.view.signals(file_path):
            if s["kind"] == "env_var":
                name = (s["value"] or {}).get("name")
                if name and name not in doc.env_vars:
                    doc.env_vars.append(name)
            elif s["kind"] == "endpoint":
                ep = s["value"] or {}
                key = (ep.get("method"), ep.get("path"))
                if ep.get("path") and key not in seen_ep:
                    seen_ep.add(key)
                    doc.api_endpoints.append({"method": ep.get("method"), "path": ep.get("path")})


def _tech_stack(d: Deriver, comp) -> list[str]:
    tech = []
    if comp.framework:
        tech.append(comp.framework)
    if comp.language:
        tech.append(comp.language.capitalize())
    for file_path in comp.files[:50]:
        basename = os.path.basename(file_path).lower()
        if basename in ("tailwind.config.js", "tailwind.config.ts"):
            tech.append("TailwindCSS")
        elif basename == "tsconfig.json":
            tech.append("TypeScript")
        elif basename in (".eslintrc", "eslint.config.js"):
            tech.append("ESLint")
        elif basename in ("jest.config.js", "jest.config.ts"):
            tech.append("Jest")
        elif basename == "vitest.config.ts":
            tech.append("Vitest")
        elif basename == "webpack.config.js":
            tech.append("Webpack")
        elif basename in ("vite.config.ts", "vite.config.js"):
            tech.append("Vite")
    return sorted(set(tech))


def detect_patterns(comp) -> list[str]:
    patterns = []
    file_names = [os.path.basename(f).lower() for f in comp.files]

    has_view = any("view" in f for f in file_names)
    has_model = any("model" in f for f in file_names)
    has_controller = any("controller" in f for f in file_names)
    has_viewmodel = any("viewmodel" in f or "view_model" in f for f in file_names)
    has_presenter = any("presenter" in f for f in file_names)

    if has_view and has_model and has_viewmodel:
        patterns.append("MVVM")
    elif has_view and has_model and has_controller:
        patterns.append("MVC")
    elif has_view and has_model and has_presenter:
        patterns.append("MVP")

    if any("repository" in f or "repo" in f for f in file_names):
        patterns.append("Repository Pattern")
    if any("service" in f for f in file_names) and comp.type != "service":
        patterns.append("Service Layer")
    if any("observer" in f or "subscriber" in f or "publisher" in f for f in file_names):
        patterns.append("Observer/Pub-Sub")
    if any("store" in f or "reducer" in f or "slice" in f for f in file_names):
        patterns.append("State Management")
    if any("middleware" in f for f in file_names):
        patterns.append("Middleware")
    if any("plugin" in f or "extension" in f for f in file_names):
        patterns.append("Plugin Architecture")
    if any("factory" in f for f in file_names):
        patterns.append("Factory Pattern")
    if any("container" in f or "injector" in f or "provider" in f for f in file_names):
        patterns.append("Dependency Injection")
    if any("api" in f or "endpoint" in f or "route" in f for f in file_names):
        patterns.append("API Layer")

    if comp.testing:
        t = comp.testing
        total_tests = t.get("unit_tests", 0) + t.get("integration_tests", 0) + t.get("e2e_tests", 0)
        if total_tests > 0:
            patterns.append(f"Tests ({total_tests})")
        if t.get("coverage_percent") is not None and t["coverage_percent"] >= 80:
            patterns.append("Well-Tested")
        if t.get("e2e_tests", 0) > 0:
            patterns.append("E2E Tests")
    else:
        test_files = [f for f in file_names if "test" in f or "spec" in f]
        if test_files:
            ratio = len(test_files) / max(len(file_names), 1)
            if ratio > 0.3:
                patterns.append("Well-Tested")
            patterns.append(f"Tests ({len(test_files)} files)")

    return patterns
