feat: Implement true incremental re-analysis (Stream K)

- Add build_component_dependency_graph() for reverse import mapping with one-level-deep expansion
- Add rescan_component() for selective file re-scanning using standard parsers
- Add merge_component_into_baseline() to patch rescanned data back into baseline
- Add redetect_relationships() for incremental import and port-based relationship detection
- Add baseline caching with file-index.json and import-graph.json alongside architecture.json
- Rewrite IncrementalAnalyzer.run() to use true incremental pipeline (full rescan as fallback)
- Update CLI to use save_baseline_cache for three-file cache strategy
- Add 76 tests across 14 test classes covering all new functions and integration scenarios
