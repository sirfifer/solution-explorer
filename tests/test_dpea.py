"""Tests for the DPEA (Digest, Partition, Enhance, Assemble) pipeline components.

Covers:
- merge-ai-enhancements.py: forward-carry of AI-discovered relationships
- analyzer/incremental.py: build_architectural_neighbor_graph
- scripts/score-ai-enhancement-quality.py: schema validation and quality scoring
"""

import json
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers to import the merge script's functions directly
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"


def _load_merge_module():
    """Import the merge script as a module without running main()."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "merge_ai", SCRIPTS_DIR / "merge-ai-enhancements.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_score_module():
    """Import the quality scoring script as a module."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "score_ai", SCRIPTS_DIR / "score-ai-enhancement-quality.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


merge_mod = _load_merge_module()
score_mod = _load_score_module()


# ===========================================================================
# Tests for merge-ai-enhancements.py
# ===========================================================================


class TestMergeForwardCarry:
    """Test forward-carry of AI-discovered relationships."""

    def test_ai_discovered_relationship_carried_forward(self):
        """AI-discovered relationships in baseline should appear in target."""
        baseline = {
            "components": [{"id": "A", "ai_enhance": {"help_text": "test"}}],
            "relationships": [
                {
                    "source": "A",
                    "target": "B",
                    "type": "http",
                    "ai_enhance": {"data_flow_description": "normal"},
                },
                {
                    "source": "A",
                    "target": "C",
                    "type": "database",
                    "label": "Redis cache",
                    "ai_enhance": {
                        "ai_discovered": True,
                        "data_flow_description": "AI found this",
                        "importance": "secondary",
                    },
                },
            ],
        }
        target = {
            "components": [{"id": "A"}],
            "relationships": [
                {"source": "A", "target": "B", "type": "http"},
            ],
        }

        comp_stats, rel_stats = merge_mod.merge(baseline, target)

        # A->C should be carried forward
        assert len(target["relationships"]) == 2
        carried = [
            r
            for r in target["relationships"]
            if r.get("ai_enhance", {}).get("ai_discovered")
        ]
        assert len(carried) == 1
        assert carried[0]["source"] == "A"
        assert carried[0]["target"] == "C"
        assert carried[0]["type"] == "database"
        assert carried[0]["label"] == "Redis cache"
        assert rel_stats["ai_discovered_carried"] == 1

    def test_no_duplicate_when_target_already_has_relationship(self):
        """If the target already has the same (source, target, type), don't duplicate."""
        baseline = {
            "components": [],
            "relationships": [
                {
                    "source": "A",
                    "target": "C",
                    "type": "database",
                    "ai_enhance": {
                        "ai_discovered": True,
                        "data_flow_description": "found by AI",
                    },
                },
            ],
        }
        target = {
            "components": [],
            "relationships": [
                # Target already has A->C database (maybe from a new analyzer run)
                {"source": "A", "target": "C", "type": "database"},
            ],
        }

        merge_mod.merge(baseline, target)

        # Should not duplicate: the regular merge copies ai_enhance,
        # and the forward-carry sees the key already exists
        assert len(target["relationships"]) == 1
        assert target["relationships"][0].get("ai_enhance", {}).get("ai_discovered")

    def test_non_discovered_relationships_not_carried(self):
        """Only ai_discovered=True relationships should be forward-carried."""
        baseline = {
            "components": [],
            "relationships": [
                {
                    "source": "X",
                    "target": "Y",
                    "type": "import",
                    "ai_enhance": {
                        "data_flow_description": "normal relationship",
                    },
                },
            ],
        }
        target = {
            "components": [],
            "relationships": [],
        }

        merge_mod.merge(baseline, target)

        # X->Y import is NOT ai_discovered, so should NOT be carried
        assert len(target["relationships"]) == 0

    def test_empty_baseline_relationships(self):
        """Empty baseline relationships should not cause errors."""
        baseline = {"components": [], "relationships": []}
        target = {"components": [], "relationships": []}

        comp_stats, rel_stats = merge_mod.merge(baseline, target)

        assert rel_stats["ai_discovered_carried"] == 0
        assert len(target["relationships"]) == 0

    def test_target_without_relationships_key(self):
        """Forward-carry works even if target has no relationships key."""
        baseline = {
            "components": [],
            "relationships": [
                {
                    "source": "A",
                    "target": "B",
                    "type": "http",
                    "ai_enhance": {
                        "ai_discovered": True,
                        "data_flow_description": "found",
                    },
                },
            ],
        }
        target = {"components": []}

        merge_mod.merge(baseline, target)

        assert len(target["relationships"]) == 1
        assert target["relationships"][0]["source"] == "A"

    def test_multiple_ai_discovered_carried(self):
        """Multiple AI-discovered relationships should all be carried."""
        baseline = {
            "components": [],
            "relationships": [
                {
                    "source": "A",
                    "target": "B",
                    "type": "database",
                    "ai_enhance": {"ai_discovered": True, "data_flow_description": "r1"},
                },
                {
                    "source": "C",
                    "target": "D",
                    "type": "websocket",
                    "ai_enhance": {"ai_discovered": True, "data_flow_description": "r2"},
                },
            ],
        }
        target = {"components": [], "relationships": []}

        comp_stats, rel_stats = merge_mod.merge(baseline, target)

        assert len(target["relationships"]) == 2
        assert rel_stats["ai_discovered_carried"] == 2


# ===========================================================================
# Tests for analyzer/incremental.py - build_architectural_neighbor_graph
# ===========================================================================


class TestArchitecturalNeighborGraph:
    """Test the all-relationship-types neighbor graph."""

    def test_basic_undirected_graph(self):
        from analyzer.incremental import build_architectural_neighbor_graph

        baseline = {
            "relationships": [
                {"source": "A", "target": "B", "type": "http"},
                {"source": "B", "target": "C", "type": "import"},
            ]
        }
        graph = build_architectural_neighbor_graph(baseline)

        assert graph["A"] == {"B"}
        assert graph["B"] == {"A", "C"}
        assert graph["C"] == {"B"}

    def test_all_relationship_types_included(self):
        from analyzer.incremental import build_architectural_neighbor_graph

        baseline = {
            "relationships": [
                {"source": "A", "target": "B", "type": "http"},
                {"source": "A", "target": "C", "type": "database"},
                {"source": "A", "target": "D", "type": "websocket"},
                {"source": "A", "target": "E", "type": "import"},
            ]
        }
        graph = build_architectural_neighbor_graph(baseline)

        assert graph["A"] == {"B", "C", "D", "E"}

    def test_self_loops_excluded(self):
        from analyzer.incremental import build_architectural_neighbor_graph

        baseline = {
            "relationships": [
                {"source": "A", "target": "A", "type": "import"},
                {"source": "A", "target": "B", "type": "http"},
            ]
        }
        graph = build_architectural_neighbor_graph(baseline)

        assert graph["A"] == {"B"}
        assert graph["B"] == {"A"}

    def test_empty_relationships(self):
        from analyzer.incremental import build_architectural_neighbor_graph

        baseline = {"relationships": []}
        graph = build_architectural_neighbor_graph(baseline)

        assert graph == {}

    def test_missing_relationships_key(self):
        from analyzer.incremental import build_architectural_neighbor_graph

        baseline = {}
        graph = build_architectural_neighbor_graph(baseline)

        assert graph == {}

    def test_bidirectional_from_single_relationship(self):
        """A single A->B relationship should create neighbors in both directions."""
        from analyzer.incremental import build_architectural_neighbor_graph

        baseline = {
            "relationships": [
                {"source": "server", "target": "database", "type": "database"},
            ]
        }
        graph = build_architectural_neighbor_graph(baseline)

        assert "database" in graph["server"]
        assert "server" in graph["database"]

    def test_compared_to_import_only_graph(self):
        """Architectural graph should find more neighbors than import-only graph."""
        from analyzer.incremental import (
            build_architectural_neighbor_graph,
            build_component_dependency_graph,
        )

        baseline = {
            "relationships": [
                {"source": "client", "target": "server", "type": "http"},
                {"source": "server", "target": "db", "type": "database"},
                {"source": "server", "target": "lib", "type": "import"},
            ]
        }

        import_graph = build_component_dependency_graph(baseline)
        arch_graph = build_architectural_neighbor_graph(baseline)

        # Import graph only has lib -> {server} (reverse import)
        assert len(import_graph) == 1
        assert "lib" in import_graph
        assert import_graph["lib"] == {"server"}

        # Architectural graph has all 4 components connected
        assert len(arch_graph) == 4
        assert "client" in arch_graph
        assert "db" in arch_graph


# ===========================================================================
# Tests for score-ai-enhancement-quality.py
# ===========================================================================


class TestSchemaValidation:
    """Phase 4a: Schema validation tests."""

    def _make_valid_ai_enhance(self, **overrides):
        """Create a minimal valid component ai_enhance block."""
        base = {
            "help_text": "Sentence one. Sentence two. Sentence three.",
            "data_handled": "User data and session tokens",
            "criticality": "important",
            "ai_enhanced_at": "2026-03-01T12:00:00Z",
            "ai_enhance_version": 2,
        }
        base.update(overrides)
        return base

    def test_valid_component_passes(self):
        ai = self._make_valid_ai_enhance(architectural_role="business-logic")
        errors = score_mod.validate_component_ai_enhance("test-comp", ai)
        assert errors == []

    def test_missing_required_field(self):
        ai = self._make_valid_ai_enhance()
        del ai["help_text"]
        errors = score_mod.validate_component_ai_enhance("test-comp", ai)
        assert any("missing required field 'help_text'" in e for e in errors)

    def test_invalid_criticality(self):
        ai = self._make_valid_ai_enhance(criticality="very-important")
        errors = score_mod.validate_component_ai_enhance("test-comp", ai)
        assert any("invalid criticality" in e for e in errors)

    def test_invalid_architectural_role(self):
        ai = self._make_valid_ai_enhance(architectural_role="mega-service")
        errors = score_mod.validate_component_ai_enhance("test-comp", ai)
        assert any("invalid architectural_role" in e for e in errors)

    def test_invalid_testing_maturity(self):
        ai = self._make_valid_ai_enhance(testing_maturity="partial")
        errors = score_mod.validate_component_ai_enhance("test-comp", ai)
        assert any("invalid testing_maturity" in e for e in errors)

    def test_unexpected_field_flagged(self):
        ai = self._make_valid_ai_enhance(hallucinated_field="oops")
        errors = score_mod.validate_component_ai_enhance("test-comp", ai)
        assert any("unexpected field 'hallucinated_field'" in e for e in errors)

    def test_wrong_version_flagged(self):
        ai = self._make_valid_ai_enhance(ai_enhance_version=1)
        errors = score_mod.validate_component_ai_enhance("test-comp", ai)
        assert any("unexpected ai_enhance_version" in e for e in errors)

    def test_null_criticality_flagged_as_missing(self):
        ai = self._make_valid_ai_enhance(criticality=None)
        errors = score_mod.validate_component_ai_enhance("test-comp", ai)
        assert any("missing required field 'criticality'" in e for e in errors)

    def test_non_dict_ai_enhance(self):
        errors = score_mod.validate_component_ai_enhance("test-comp", "not a dict")
        assert len(errors) == 1
        assert "not a dict" in errors[0]

    def test_valid_relationship_passes(self):
        ai = {
            "data_flow_description": "Client sends REST requests.",
            "importance": "primary",
            "ai_enhanced_at": "2026-03-01T12:00:00Z",
        }
        errors = score_mod.validate_relationship_ai_enhance(
            ("A", "B", "http"), ai
        )
        assert errors == []

    def test_ai_discovered_relationship_looser_requirements(self):
        """AI-discovered relationships only need data_flow_description + importance."""
        ai = {
            "ai_discovered": True,
            "data_flow_description": "Found Redis connection.",
            "importance": "secondary",
        }
        errors = score_mod.validate_relationship_ai_enhance(
            ("A", "B", "database"), ai
        )
        assert errors == []

    def test_relationship_invalid_importance(self):
        ai = {
            "data_flow_description": "test",
            "importance": "critical",
            "ai_enhanced_at": "2026-03-01T12:00:00Z",
        }
        errors = score_mod.validate_relationship_ai_enhance(
            ("A", "B", "http"), ai
        )
        assert any("invalid importance" in e for e in errors)

    def test_valid_observation_passes(self):
        obs = {
            "category": "missing_relationship",
            "description": "Redis connection not detected.",
            "confidence": "high",
        }
        errors = score_mod.validate_observation(obs, 0)
        assert errors == []

    def test_observation_invalid_category(self):
        obs = {
            "category": "bad_vibes",
            "description": "Something off.",
            "confidence": "high",
        }
        errors = score_mod.validate_observation(obs, 0)
        assert any("invalid category" in e for e in errors)

    def test_observation_missing_description(self):
        obs = {
            "category": "naming_issue",
            "confidence": "medium",
        }
        errors = score_mod.validate_observation(obs, 0)
        assert any("missing description" in e for e in errors)

    def test_invalid_iso_timestamp_component(self):
        ai = self._make_valid_ai_enhance(ai_enhanced_at="not-a-date")
        errors = score_mod.validate_component_ai_enhance("test-comp", ai)
        assert any("not a valid ISO timestamp" in e for e in errors)

    def test_valid_iso_timestamp_passes(self):
        ai = self._make_valid_ai_enhance(ai_enhanced_at="2026-03-01T12:00:00Z")
        errors = score_mod.validate_component_ai_enhance("test-comp", ai)
        assert not any("timestamp" in e for e in errors)

    def test_relationship_unexpected_field_flagged(self):
        ai = {
            "data_flow_description": "test",
            "importance": "primary",
            "ai_enhanced_at": "2026-03-01T12:00:00Z",
            "typo_field": "oops",
        }
        errors = score_mod.validate_relationship_ai_enhance(
            ("A", "B", "http"), ai
        )
        assert any("unexpected field 'typo_field'" in e for e in errors)

    def test_relationship_invalid_timestamp(self):
        ai = {
            "data_flow_description": "test",
            "importance": "primary",
            "ai_enhanced_at": "yesterday",
        }
        errors = score_mod.validate_relationship_ai_enhance(
            ("A", "B", "http"), ai
        )
        assert any("not a valid ISO timestamp" in e for e in errors)

    def test_relationship_valid_optional_fields_pass(self):
        ai = {
            "data_flow_description": "test",
            "importance": "primary",
            "ai_enhanced_at": "2026-03-01T12:00:00Z",
            "authentication_detail": "JWT bearer tokens",
            "payload_examples": ["user profile JSON"],
            "error_handling": "Returns 4xx with error body",
            "security_notes": "TLS 1.3",
        }
        errors = score_mod.validate_relationship_ai_enhance(
            ("A", "B", "http"), ai
        )
        assert errors == []


class TestQualityScoring:
    """Phase 4b: Quantitative quality scoring tests."""

    def test_perfect_score_with_all_fields(self):
        ai = {
            "help_text": "Sentence one. Sentence two. Sentence three.",
            "data_handled": "User profiles and auth tokens",
            "criticality": "critical",
            "ai_enhanced_at": "2026-03-01T12:00:00Z",
            "ai_enhance_version": 2,
            "architectural_role": "api-gateway",
            "tech_context": "Express.js with TypeScript.",
        }
        comp = {"language": "typescript", "framework": "express"}
        score, details = score_mod.score_component("test", ai, comp)
        assert score == 100.0

    def test_missing_role_reduces_score(self):
        ai = {
            "help_text": "One. Two. Three.",
            "data_handled": "data",
            "criticality": "supporting",
            "ai_enhanced_at": "2026-03-01T12:00:00Z",
            "ai_enhance_version": 2,
        }
        score, details = score_mod.score_component("test", ai)
        # No role, and architectural_role always counts as optional
        assert score < 100.0
        assert "optional_populated" in details

    def test_help_text_too_short_penalized(self):
        ai = {
            "help_text": "Very short.",
            "data_handled": "data",
            "criticality": "supporting",
            "ai_enhanced_at": "2026-03-01T12:00:00Z",
            "ai_enhance_version": 2,
            "architectural_role": "worker",
        }
        score_short, _ = score_mod.score_component("test", ai)

        ai["help_text"] = "One. Two. Three."
        score_good, _ = score_mod.score_component("test", ai)

        assert score_good > score_short

    def test_context_aware_optional_scoring(self):
        """Optional fields scored only when context data exists."""
        ai = {
            "help_text": "One. Two. Three.",
            "data_handled": "data",
            "criticality": "important",
            "ai_enhanced_at": "2026-03-01T12:00:00Z",
            "ai_enhance_version": 2,
            "architectural_role": "business-logic",
            "actions_summary": "5 buttons and 2 forms.",
            "key_user_flows": ["Submit form", "Navigate"],
        }
        comp_with_actions = {"actions": [{"type": "button"}]}
        comp_without_actions = {}

        score_with, det_with = score_mod.score_component("test", ai, comp_with_actions)
        score_without, det_without = score_mod.score_component("test", ai, comp_without_actions)

        # With actions context, the populated action fields boost the score
        # Without actions context, those fields are irrelevant
        # Both should be high since role is populated
        assert score_with >= score_without

    def test_sentence_count(self):
        assert score_mod._count_sentences("One. Two. Three.") == 3
        assert score_mod._count_sentences("Just one sentence.") == 1
        assert score_mod._count_sentences("") == 0
        assert score_mod._count_sentences("A. B. C. D. E.") == 5

    def test_non_dict_ai_scores_zero(self):
        score, details = score_mod.score_component("test", "not a dict")
        assert score == 0.0


class TestArchitectureScoring:
    """Test full architecture scoring."""

    def _make_arch(self, num_components=3, enhanced=True):
        """Build a minimal architecture JSON with optional ai_enhance."""
        components = []
        for i in range(num_components):
            comp = {"id": f"comp-{i}", "name": f"Component {i}"}
            if enhanced:
                comp["ai_enhance"] = {
                    "help_text": f"Help for comp {i}. Second sentence. Third sentence.",
                    "data_handled": "test data",
                    "criticality": "supporting",
                    "architectural_role": "business-logic",
                    "ai_enhanced_at": "2026-03-01T12:00:00Z",
                    "ai_enhance_version": 2,
                }
            components.append(comp)

        return {
            "components": components,
            "relationships": [
                {
                    "source": "comp-0",
                    "target": "comp-1",
                    "type": "import",
                    "ai_enhance": {
                        "data_flow_description": "imports",
                        "importance": "internal",
                        "ai_enhanced_at": "2026-03-01T12:00:00Z",
                    },
                }
            ],
            "ai_enhance": {
                "summary": "Test system.",
                "data_flow_narrative": "Data flows through.",
                "ai_enhanced_at": "2026-03-01T12:00:00Z",
                "ai_enhance_version": 2,
            },
        }

    def test_fully_enhanced_passes(self):
        arch = self._make_arch(num_components=3, enhanced=True)
        report = score_mod.score_architecture(arch)

        assert report["coverage_pct"] == 100.0
        assert report["enhanced_components"] == 3
        assert len(report["missing_ai_enhance"]) == 0
        assert report["pass"] is True

    def test_missing_ai_enhance_fails(self):
        arch = self._make_arch(num_components=3, enhanced=True)
        # Remove ai_enhance from one component
        del arch["components"][2]["ai_enhance"]

        report = score_mod.score_architecture(arch)

        assert report["coverage_pct"] < 100.0
        assert report["pass"] is False
        assert "comp-2" in report["missing_ai_enhance"]

    def test_missing_root_ai_enhance_fails(self):
        arch = self._make_arch(num_components=2, enhanced=True)
        del arch["ai_enhance"]

        report = score_mod.score_architecture(arch)

        assert report["pass"] is False
        assert any("Missing root-level ai_enhance" in e for e in report["validation_errors"])

    def test_nested_components_scored(self):
        """Components nested inside children should also be scored."""
        arch = {
            "components": [
                {
                    "id": "parent",
                    "name": "Parent",
                    "ai_enhance": {
                        "help_text": "Parent help. Two. Three.",
                        "data_handled": "parent data",
                        "criticality": "critical",
                        "ai_enhanced_at": "2026-03-01T12:00:00Z",
                        "ai_enhance_version": 2,
                    },
                    "children": [
                        {
                            "id": "child",
                            "name": "Child",
                            "ai_enhance": {
                                "help_text": "Child help. Two. Three.",
                                "data_handled": "child data",
                                "criticality": "supporting",
                                "ai_enhanced_at": "2026-03-01T12:00:00Z",
                                "ai_enhance_version": 2,
                            },
                        }
                    ],
                }
            ],
            "relationships": [],
            "ai_enhance": {
                "summary": "Test.",
                "data_flow_narrative": "Test flow.",
                "ai_enhanced_at": "2026-03-01T12:00:00Z",
                "ai_enhance_version": 2,
            },
        }

        report = score_mod.score_architecture(arch)

        assert report["total_components"] == 2
        assert report["enhanced_components"] == 2
        assert report["coverage_pct"] == 100.0

    def test_criticality_and_role_distribution_tracked(self):
        arch = self._make_arch(num_components=3, enhanced=True)
        # Mix up criticalities
        arch["components"][0]["ai_enhance"]["criticality"] = "critical"
        arch["components"][1]["ai_enhance"]["criticality"] = "important"
        arch["components"][2]["ai_enhance"]["criticality"] = "supporting"

        arch["components"][0]["ai_enhance"]["architectural_role"] = "api-gateway"
        arch["components"][1]["ai_enhance"]["architectural_role"] = "data-store"

        report = score_mod.score_architecture(arch)

        assert report["criticality_distribution"] == {
            "critical": 1,
            "important": 1,
            "supporting": 1,
        }
        assert report["role_distribution"]["api-gateway"] == 1
        assert report["role_distribution"]["data-store"] == 1


class TestPartitionScoring:
    """Test partition result scoring."""

    def test_partition_with_valid_data(self):
        data = {
            "components": {
                "comp-a": {
                    "help_text": "One. Two. Three.",
                    "data_handled": "data",
                    "criticality": "critical",
                    "architectural_role": "api-gateway",
                    "ai_enhanced_at": "2026-03-01T12:00:00Z",
                    "ai_enhance_version": 2,
                },
            },
            "relationships": {
                "comp-a|comp-b|http": {
                    "data_flow_description": "REST calls.",
                    "importance": "primary",
                    "ai_enhanced_at": "2026-03-01T12:00:00Z",
                },
            },
        }
        result = score_mod.score_partition(data)

        assert result["component_count"] == 1
        assert result["average_score"] > 80
        assert result["relationship_count"] == 1
        assert result["relationship_valid"] == 1

    def test_empty_partition(self):
        data = {"components": {}, "relationships": {}}
        result = score_mod.score_partition(data)

        assert result["component_count"] == 0
        assert result["average_score"] == 0.0


class TestScoringScriptCLI:
    """Test the quality scoring script CLI integration."""

    def test_architecture_mode(self, tmp_path):
        """Test --architecture mode with a valid file."""
        arch = {
            "components": [
                {
                    "id": "A",
                    "name": "A",
                    "ai_enhance": {
                        "help_text": "Help one. Help two. Help three.",
                        "data_handled": "data",
                        "criticality": "critical",
                        "architectural_role": "api-gateway",
                        "ai_enhanced_at": "2026-03-01T12:00:00Z",
                        "ai_enhance_version": 2,
                    },
                }
            ],
            "relationships": [],
            "ai_enhance": {
                "summary": "Test system.",
                "data_flow_narrative": "Data flows.",
                "ai_enhanced_at": "2026-03-01T12:00:00Z",
                "ai_enhance_version": 2,
            },
        }
        arch_file = tmp_path / "arch.json"
        arch_file.write_text(json.dumps(arch))

        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "score-ai-enhancement-quality.py"),
             "--architecture", str(arch_file)],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        assert "PASS" in result.stdout

    def test_architecture_mode_with_errors(self, tmp_path):
        """Test --architecture mode detects missing ai_enhance."""
        arch = {
            "components": [{"id": "A", "name": "A"}],
            "relationships": [],
        }
        arch_file = tmp_path / "arch.json"
        arch_file.write_text(json.dumps(arch))

        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "score-ai-enhancement-quality.py"),
             "--architecture", str(arch_file)],
            capture_output=True, text=True
        )

        assert result.returncode == 1
        assert "FAIL" in result.stdout

    def test_partition_mode(self, tmp_path):
        """Test --partition mode."""
        data = {
            "components": {
                "A": {
                    "help_text": "One. Two. Three.",
                    "data_handled": "data",
                    "criticality": "critical",
                    "architectural_role": "api-gateway",
                    "ai_enhanced_at": "2026-03-01T12:00:00Z",
                    "ai_enhance_version": 2,
                },
            },
            "relationships": {},
        }
        part_file = tmp_path / "result-0.json"
        part_file.write_text(json.dumps(data))

        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "score-ai-enhancement-quality.py"),
             "--partition", str(part_file)],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        assert "PASS" in result.stdout

    def test_partition_mode_with_errors(self, tmp_path):
        """Test --partition mode detects validation errors and exits non-zero."""
        data = {
            "components": {
                "A": {
                    "help_text": "Short.",
                    "criticality": "mega-critical",
                },
            },
            "relationships": {},
        }
        part_file = tmp_path / "result-0.json"
        part_file.write_text(json.dumps(data))

        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "score-ai-enhancement-quality.py"),
             "--partition", str(part_file)],
            capture_output=True, text=True
        )

        assert result.returncode == 1
        assert "FAIL" in result.stdout

    def test_output_file_written(self, tmp_path):
        """Test --output writes machine-readable JSON."""
        arch = {
            "components": [
                {
                    "id": "A",
                    "name": "A",
                    "ai_enhance": {
                        "help_text": "One. Two. Three.",
                        "data_handled": "data",
                        "criticality": "critical",
                        "architectural_role": "api-gateway",
                        "ai_enhanced_at": "2026-03-01T12:00:00Z",
                        "ai_enhance_version": 2,
                    },
                }
            ],
            "relationships": [],
            "ai_enhance": {
                "summary": "Test.",
                "data_flow_narrative": "Flow.",
                "ai_enhanced_at": "2026-03-01T12:00:00Z",
                "ai_enhance_version": 2,
            },
        }
        arch_file = tmp_path / "arch.json"
        arch_file.write_text(json.dumps(arch))
        out_file = tmp_path / "scores.json"

        subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "score-ai-enhancement-quality.py"),
             "--architecture", str(arch_file),
             "--output", str(out_file)],
            capture_output=True, text=True
        )

        assert out_file.exists()
        report = json.loads(out_file.read_text())
        assert "total_components" in report
        assert "average_score" in report
