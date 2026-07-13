# multi-repo fixture

A minimal multi-repository solution for the analyzer test suite. `solution.json`
is the multi-repo config consumed by `MultiRepoOrchestrator`; it points at two
tiny local repos under `repos/`. This fixture exercises multi-repo id
prefixing (the `repo:<name>` containers and per-repo component/symbol ids) and
anchors the multi-repo half of the P4-1 parity snapshot.

Keep it tiny. Committed as real files.
