# Executed qualification and limits

Qualification date: 2026-10-08. See `qualification-results.json` for machine-readable observed counts, exact cycle sums and workload measurements. These are original controlled tests, not production defect reproductions.

## Reusable application-owned integration

Two independent actual SDK/HTTP captures each contain 16 spans, seven qualified start relations, six qualified end relations and four explicit domain/epochs. One unchanged contract is reused with zero per-capture manual annotations. Each execution starts B and C as separate processes, terminates C and starts another C with a fresh epoch and a deliberately different instrumentation timestamp offset. PIDs and start/stop acknowledgments record the genuine process restart.

The known injected corrections satisfy every selected inequality. Merging epochs under a deliberately stronger literal-epoch contract is incompatible (cycle sums −408,860,975 ns and −408,830,216 ns in the retained runs). This tests explicit segmentation, not actual machine-clock changes.

The headers-only request contributes start ordering without end enclosure. A deliberately unsound control adding end enclosure is incompatible, with roughly −39 ms cycle sums. The asynchronous producer/consumer pair outlives its producer and is excluded.

A separately labeled post-export +200 ms shift to one server span creates a global contradiction while every individual fully qualified RPC band remains nonempty. This corruption control is separate from the real restart. Exact cycle sums in the retained runs are −196,771,549 ns and −198,754,096 ns. Raw input hashes remain unchanged through analysis/replay.

Original protobuf, OTLP JSON/JSONL, lifecycle metadata and exact shared Jaeger exports are included under `examples/loopback/captures/run1` and `run2`. The SDK is 1.45.1. One physical host is used throughout; there is no measured physical calibration or arbitrary auto-instrumentation claim.

## Mature runtime comparison

The official Jaeger 2.22.0 Linux amd64 binary was downloaded from its official release and checked against its published SHA-256. Binary hash: `fa574f53e2f739301f301f66e5608c84d0b9a90cdd08e4f6cba8809d171854e1`.

The comparison floors both raw endpoints to integer microseconds before OTLP ingestion, then queries the actual Jaeger runtime with correction disabled and enabled. Every endpoint in the disabled-adjustment legacy export roundtrips exactly. ClockWeave analyzes that exact queried raw export too; it is compatible under the reusable contract. The original OTLP nanosecond analysis remains separate.

Jaeger successfully adjusts nine of the 16 spans in each retained capture, with explicit adjustment warnings. It was also executed on both separately corrupted captures, again producing its intended recursive display corrections. These are baseline successes, not evidence that the viewer “failed” to perform a different diagnostic task. The original captures contain the headers and real restart controls; epoch-merging and naive enclosure change only ClockWeave's declared assumptions.

`tools/compare_jaeger.py` executes the real binary and records commands, exact raw/adjusted exports and differences. No baseline algorithm is reimplemented. It starts transient loopback-only services, and isolates self-telemetry exporter settings for those child processes only. No upstream binary/code is redistributed in this package.

## Exact graph and independent replay checks

- 1,000 seeded graphs agreed with a separately implemented integer Floyd-Warshall oracle and SciPy/HiGHS feasibility: 668 compatible and 332 incompatible.
- 5,360 projected endpoints agreed with the exact oracle; 3,743 finite endpoints also agreed with LP optimization.
- Twenty small bounded graphs agreed with exhaustive integer enumeration.
- Every returned example, endpoint-attaining assignment, path/cut and negative-cycle arithmetic witness was checked.
- Ten reports from the genuine captures, altered assumptions, separate corruption controls and exact shared raw Jaeger inputs independently replayed successfully.
- Mutation tests reject endpoint changes even with updated hashes, remapped domains/epochs, missing observations/constraints, false coverage, wrong ranges, non-attaining assignments, broken/untrue cycles and false unbounded cuts.
- Replay runs with imports of production ingestion, contract/extraction and graph modules blocked. Its semantic interpreter is separate; it checks raw evidence plus integer arithmetic/traversal without calling the optimizer.

This is substantial testing, not formal verification. In particular, user-provided assumptions and collection authenticity remain outside the proof.

## Resource measurements and admission

The tested ladder covered 1,000/10,000/50,000 span records, 8/32/64 domain-epochs, sparse and dense qualified graphs, plus metadata-padded input near 8 MiB. Measurements include load, inspect, analysis with all range witnesses, independent replay, JSON serialization and HTML generation in separate Linux Python 3.12.14 processes.

The final near-boundary case uses 10,000 records, 64 domain-epochs, 4,032 aggregated edges and 548 metadata bytes per span. Its input is 8,380,507 bytes; the observed full workflow takes 9.93 seconds with a 321.0 MiB peak RSS. Its pretty JSON is 30,158,720 bytes and HTML is 39,132,925 bytes. These report sizes matter when sharing or opening large captures.

The 50,000-record cases used roughly 1.2–1.3 GiB and the densest 64-domain case took 32.4 seconds, so they are outside the selected default envelope. Defaults are therefore 10,000 observed span records including duplicates, 64 declared domain/epochs and 8 MiB combined input bytes. Inputs beyond them receive a clear unsupported-size outcome without a partial diagnosis. The larger measurements preceded admission checks and are retained to show why the limit was narrowed.

These measurements are specific generated, qualified workloads on the recorded machine. They are not latency promises, hard memory bounds or hostile-input security guarantees. Complex attributes, contracts and HTML viewing behavior can differ. No system resource sandbox is provided.

## Portability and remaining checks

Linux clean-venv wheel and source installation, complete package tests, actual loopback capture and official Jaeger comparison are release-candidate checks. The repository contains a Linux/macOS/Windows × Python 3.10/3.12/3.13 workflow; configured jobs are not claims of passing CI on those platforms. [CI scope](ci.md) records verified immutable official action pins, disabled checkout credential persistence, and explicit Jaeger/SciPy skip reporting. Exact-head external CI has not run in this local build stage.

Escaping, structural validation, source links and standalone HTML generation are tested. Chromium could not initialize its local socket under this execution environment, including the approved retry, so a browser screenshot/layout pass remains unexecuted. The HTML itself is available for inspection. Rendering clearly labels structural validation and does not imply raw evidence replay.

Independent whole-tree review identified six input/replay/rendering and admission issues. They were reproduced with failing regressions, repaired, and followed by 168 passing source tests including actual capture and upstream runtime checks, another full graph oracle run and all ten retained raw replays. A focused independent follow-up then confirmed all six repairs using 35 targeted tests, 89 adjacent ingest/render/replay/CLI tests and additional reviewer-authored acceptance probes. Those checks are independent evidence; the complete 168-test source/package runs are author evidence. No second whole-design review or repeat of the unchanged full numerical suite was needed. No calibration or broad adoption claim follows from these controlled checks.
