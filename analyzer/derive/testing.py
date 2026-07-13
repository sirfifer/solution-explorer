"""Test-coverage detection (Tier 3), root-bounded per the P2-2 carry-over.

Re-expresses ``ArchitectureScanner._detect_testing`` and its helpers over the
store. The P2-2 item-3 fix lands here: ``_check_ci_tests`` and test-file
classification walk only within the scan root, never above it. The old engine
walked ``comp_dir`` up to the filesystem root, so a fixture living under the
host repo's ``tests/`` and ``.github/`` inherited the host's test files and CI
config as its own. Bounding to the scan root removes that false positive
(enumerated for the P4-7 gate).
"""

from __future__ import annotations

import json
import os
import re
from typing import Optional

from ..constants import (
    CI_CONFIG_FILES,
    CI_TEST_PATTERNS,
    CODE_LANGUAGES,
    COVERAGE_REPORT_FILES,
    E2E_DIR_NAMES,
    INTEGRATION_DIR_NAMES,
    LANGUAGE_MAP,
    PACKAGE_TEST_DEPS,
    TEST_DIR_NAMES,
    TEST_FRAMEWORK_INDICATORS,
    TEST_FUNCTION_PATTERNS,
)
from .context import Deriver


def detect_testing(d: Deriver) -> None:
    file_lookup = {fi.path: fi for fi in d._all_files}
    for rel_path, comp in d._component_map.items():
        comp_dir = rel_path  # rel path string, bounded to the scan root
        testing = _detect_component_testing(d, comp, comp_dir, file_lookup)
        if testing:
            comp.testing = testing


def _detect_component_testing(d: Deriver, comp, comp_dir: str, file_lookup) -> dict:
    test_files: list[tuple[str, str, int]] = []  # (rel_path, language, lines)

    for fpath in comp.files:
        fi = file_lookup.get(fpath)
        if not fi:
            continue
        if _is_test_file(fpath, fi.language):
            test_files.append((fpath, fi.language, fi.lines))

    for test_dir_name in TEST_DIR_NAMES:
        test_dir = f"{comp_dir}/{test_dir_name}" if comp_dir else test_dir_name
        _collect_test_files_from_dir(d, test_dir, test_files)

    if not test_files:
        frameworks = _detect_test_frameworks(d, comp, comp_dir)
        coverage_pct, coverage_src = _find_coverage_report(d, comp_dir)
        has_ci = _check_ci_tests(d, comp_dir)
        if not frameworks and not has_ci and coverage_pct is None:
            return {}
        return {
            "test_files": 0, "test_lines": 0, "unit_tests": 0,
            "integration_tests": 0, "e2e_tests": 0, "test_frameworks": frameworks,
            "coverage_percent": coverage_pct, "coverage_source": coverage_src,
            "has_ci_tests": has_ci,
        }

    unit_count = integration_count = e2e_count = total_test_lines = 0
    for fpath, lang, lines in test_files:
        total_test_lines += lines
        count = _count_test_functions(d, fpath, lang)
        category = _classify_test_category(fpath)
        if category == "e2e":
            e2e_count += count
        elif category == "integration":
            integration_count += count
        else:
            unit_count += count

    return {
        "test_files": len(test_files), "test_lines": total_test_lines,
        "unit_tests": unit_count, "integration_tests": integration_count,
        "e2e_tests": e2e_count,
        "test_frameworks": _detect_test_frameworks(d, comp, comp_dir),
        "coverage_percent": _find_coverage_report(d, comp_dir)[0],
        "coverage_source": _find_coverage_report(d, comp_dir)[1],
        "has_ci_tests": _check_ci_tests(d, comp_dir),
    }


def _is_test_file(rel_path: str, language: str) -> bool:
    name = os.path.basename(rel_path).lower()
    # Root-bounded: only ancestors within the scan root count as test dirs.
    for part in os.path.dirname(rel_path).split("/"):
        if part.lower() in TEST_DIR_NAMES:
            return True
    if language == "python":
        return name.startswith("test_") or name.endswith("_test.py")
    if language in ("typescript", "javascript"):
        return name.endswith((".test.ts", ".spec.ts", ".test.js", ".spec.js",
                              ".test.tsx", ".spec.tsx", ".test.jsx", ".spec.jsx"))
    if language == "swift":
        return "test" in name and name.endswith(".swift")
    if language == "go":
        return name.endswith("_test.go")
    if language == "rust":
        return name == "tests.rs" or "test" in name
    if language == "ruby":
        return name.endswith(("_spec.rb", "_test.rb"))
    if language in ("java", "kotlin"):
        return "test" in name
    return False


def _collect_test_files_from_dir(d: Deriver, test_dir: str, test_files: list) -> None:
    if test_dir not in d.view.dir_paths:
        return
    tracked = {tf[0] for tf in test_files}
    prefix = f"{test_dir}/"
    for p in d.view.all_paths:
        if not p.startswith(prefix):
            continue
        ext = os.path.splitext(p)[1].lower()
        lang = LANGUAGE_MAP.get(ext)
        if not lang or lang not in CODE_LANGUAGES or p in tracked:
            continue
        content = d.view.content(p)
        lines = len(content.splitlines()) if content else 0
        test_files.append((p, lang, lines))


def _count_test_functions(d: Deriver, rel_path: str, language: str) -> int:
    patterns = TEST_FUNCTION_PATTERNS.get(language, [])
    content = d.view.content(rel_path)
    if not patterns or not content:
        return 0
    return sum(len(re.findall(p, content, re.MULTILINE)) for p in patterns)


def _classify_test_category(rel_path: str) -> str:
    path_str = rel_path.lower()
    for part in rel_path.split("/"):
        pl = part.lower()
        if pl in E2E_DIR_NAMES:
            return "e2e"
        if pl in INTEGRATION_DIR_NAMES:
            return "integration"
    if ".e2e." in path_str:
        return "e2e"
    if ".integration." in path_str:
        return "integration"
    return "unit"


def _detect_test_frameworks(d: Deriver, comp, comp_dir: str) -> list[str]:
    frameworks: set[str] = set()
    for fname, fw_name in TEST_FRAMEWORK_INDICATORS.items():
        p = f"{comp_dir}/{fname}" if comp_dir else fname
        if (d.root / p).exists():
            frameworks.add(fw_name)
    for cfg in comp.config_files:
        cfg_type = cfg.get("type", "") if isinstance(cfg, dict) else ""
        if cfg_type == "package.json":
            p = f"{comp_dir}/package.json" if comp_dir else "package.json"
            content = d.view.content(p)
            if content:
                try:
                    pkg = json.loads(content)
                    all_deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                    for dep_name, fw_name in PACKAGE_TEST_DEPS.items():
                        if dep_name in all_deps:
                            frameworks.add(fw_name)
                except json.JSONDecodeError:
                    pass
        elif cfg_type == "pyproject.toml":
            p = f"{comp_dir}/pyproject.toml" if comp_dir else "pyproject.toml"
            content = d.view.content(p)
            if content and "pytest" in content:
                frameworks.add("pytest")
    if comp.language == "swift":
        for fpath in comp.files:
            if "test" in os.path.basename(fpath).lower():
                content = d.view.content(fpath)
                if content and "import XCTest" in content:
                    frameworks.add("XCTest")
                    break
    if comp.language == "go":
        if any(f.endswith("_test.go") for f in comp.files):
            frameworks.add("Go testing")
    return sorted(frameworks)


def _find_coverage_report(d: Deriver, comp_dir: str) -> tuple[Optional[float], Optional[str]]:
    for rel_report, fmt in COVERAGE_REPORT_FILES:
        p = f"{comp_dir}/{rel_report}" if comp_dir else rel_report
        content = d.view.content(p)
        if content is None:
            continue
        pct = _parse_coverage_report(content, fmt)
        if pct is not None:
            return (round(pct, 1), rel_report)
    return (None, None)


def _parse_coverage_report(content: str, fmt: str) -> Optional[float]:
    if fmt == "lcov":
        total = hit = 0
        for line in content.splitlines():
            if line.startswith("LF:"):
                try:
                    total += int(line[3:])
                except ValueError:
                    pass
            elif line.startswith("LH:"):
                try:
                    hit += int(line[3:])
                except ValueError:
                    pass
        if total > 0:
            return (hit / total) * 100
    elif fmt == "cobertura":
        m = re.search(r'<coverage[^>]*\bline-rate=["\']([^"\']+)', content)
        if m:
            try:
                return float(m.group(1)) * 100
            except ValueError:
                pass
    elif fmt == "istanbul":
        try:
            data = json.loads(content)
            pct = data.get("total", {}).get("lines", {}).get("pct")
            if pct is not None:
                return float(pct)
        except (json.JSONDecodeError, ValueError):
            pass
    return None


def _check_ci_tests(d: Deriver, comp_dir: str) -> bool:
    """Root-bounded CI-test detection (P2-2 item 3).

    Walks from ``comp_dir`` up to (and including) the scan root only, never
    above it. The old engine kept walking to the filesystem root, so a scan of
    a subdirectory could match a parent repo's CI config. Here the ascent stops
    at the empty-string root.
    """
    search_dir = comp_dir
    while True:
        for ci_pattern in CI_CONFIG_FILES:
            ci_path = f"{search_dir}/{ci_pattern}" if search_dir else ci_pattern
            node = d.root / ci_path
            if node.is_dir():
                for wf_file in node.iterdir():
                    if wf_file.suffix in (".yml", ".yaml"):
                        content = d.view.content(str(wf_file))
                        if content and any(re.search(p, content) for p in CI_TEST_PATTERNS):
                            return True
            elif node.is_file():
                content = d.view.content(ci_path)
                if content and any(re.search(p, content) for p in CI_TEST_PATTERNS):
                    return True
        if not search_dir:  # reached the scan root; do not ascend past it
            break
        search_dir = os.path.dirname(search_dir)
    return False
