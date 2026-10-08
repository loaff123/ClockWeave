# ClockWeave

Exact trace-clock consistency under explicit assumptions.

ClockWeave asks whether selected raw trace observations can coexist under one constant additive timestamp correction per declared clock domain and epoch. It reads OTLP JSON/JSONL or legacy Jaeger JSON and returns coupled admissible ranges with attaining assignments, or a source-linked negative cycle. Original timestamps stay unchanged.

This is a local Python library and CLI for teams that can qualify their instrumentation. A compatible answer is not a physical clock measurement. An incompatible answer rejects the joint observations and assumptions; it does not identify which clock, RPC or instrumentation is responsible.

## Quickstart from the source archive

Python 3.10 or newer; no runtime dependencies.

```sh
python -m pip install .
clockweave inspect examples/tiny/compatible.otlp.json --contract examples/tiny/contract.json --json inventory.json
clockweave analyze examples/tiny/compatible.otlp.json --contract examples/tiny/contract.json --json report.json --html report.html
clockweave verify report.json examples/tiny/compatible.otlp.json --contract examples/tiny/contract.json
```

The original tiny fixture yields A = 0, B ∈ [−20, −18] ns, C ∈ [−48, −46] ns. These are coordinate projections of a coupled feasible set. You cannot choose every interval endpoint independently. Every finite endpoint includes a full jointly feasible assignment attaining it and an original-edge path proving the bound. Disconnected and one-sided ranges remain explicitly unbounded.

Try the incompatible fixture:

```sh
clockweave analyze examples/tiny/incompatible.otlp.json --contract examples/tiny/contract.json --json contradiction.json --html contradiction.html
```

It exits 1 and records an exact −6 ns negative cycle whose equations point to the observed span endpoints. It does not rewrite the trace.

## Qualification comes first

- Clock identity is explicit. A service name is never silently treated as a clock.
- Each domain/epoch tuple gets a distinct variable. Restart epochs are not silently merged.
- Request-start ordering and response-end enclosure are separate declarations. HTTP clients may end at headers while the server continues the body.
- Parent links and CLIENT/SERVER span kinds are not enough to infer either boundary relation.
- Each nonnegative slack independently relaxes one inequality. It is not a shared latent-error or probability model.
- Unknown/adjusted provenance, missing anchors, and absent qualified relations produce `insufficient_evidence`.
- Partial captures retain unresolved/excluded counts. “Compatible” applies only to the qualified subset.

The [contract reference](docs/contract.md) explains the small reusable JSON language. [Input formats](docs/formats.md) documents exact supported exports, identifiers, timestamps and conservative error handling. [Interpretation](docs/interpretation.md) explains what the results establish.

## Real reference workflow

[The loopback example](examples/loopback/README.md) uses actual OpenTelemetry SDK spans, context propagation, HTTP requests and separately spawned B/C service processes. C is genuinely stopped and restarted with a new epoch and a deliberately different instrumentation offset. One unchanged contract works across fresh captures without per-capture span annotations. A headers-only control retains its start inequality; asynchronous work remains excluded.

This is one physical host with injected timestamp offsets. It is not multi-host calibration or certification of arbitrary automatic instrumentation. See [qualification results and limits](docs/qualification.md) for executed checks, the official Jaeger runtime comparison and remaining checks.

## CLI

```text
clockweave inspect INPUT [INPUT ...] [--format FORMAT] [--contract CONTRACT] [--json OUT]
clockweave analyze INPUT [INPUT ...] --contract CONTRACT --json OUT [--html OUT]
clockweave verify REPORT INPUT [INPUT ...] --contract CONTRACT [--json OUT]
clockweave render REPORT --html OUT
```

Formats: `auto`, `otlp-json`, `otlp-jsonl`, `jaeger-json`. Mixed inputs use `auto`. JSON output `-` goes to stdout; summaries go to stderr. Existing outputs require `--force`; source/contract/report aliases, including existing hardlinks, are refused even with `--force`. These are ordinary overwrite protections, not hostile concurrent-race defenses.

Exit codes: 0 success/compatible/verified; 1 incompatible; 2 invalid input/contract, usage or I/O; 3 insufficient evidence; 4 unsupported format/schema/size; 5 verification failed.

`render` validates report structure only. Its HTML explicitly says independent verification requires the original inputs and contract. `verify` independently parses those originals, rebuilds qualification and all inequalities, and checks assignments, paths, attaining witnesses, cuts or cycles without invoking the optimizer. Hashes bind the supplied bytes, not their authenticity or physical truth.

Reports can contain trace names and attributes. They stay local unless you share them. HTML uses no remote scripts, fonts or analytics.

## Python

```python
from pathlib import Path
from clockweave import InputSource, load_capture, load_contract, analyze, verify_report

inputs = [InputSource(Path("capture.otlp.json"))]
contract_path = Path("contract.json")
report = analyze(load_capture(inputs), load_contract(contract_path))
verification = verify_report(report, inputs, contract_path)
assert verification["valid"]
```

Also available: `inspect_capture(capture, contract=None)` and `render_html(report)`. Errors carry `kind`, `code`, `message` and an optional source pointer. API/report version 0.1 is experimental; future schema versions are not silently accepted.

## Measured admission defaults

At most 10,000 observed span records (duplicates count), 64 declared domain/epochs and 8 MiB combined input-file bytes. Larger evidence returns an unsupported-size diagnostic. These limits were selected after measured sparse/dense and metadata-padded workflows; they do not guarantee runtime or memory usage for every possible input. See [qualification](docs/qualification.md).

## Development

```sh
python -m pip install -e '.[dev,integration]'
python -m pytest
python -m build
```

The upstream Jaeger integration test is opt-in via `CLOCKWEAVE_JAEGER_BINARY` and `CLOCKWEAVE_BASELINE_CAPTURE`; it is not counted as passed when skipped. SciPy/HiGHS is a development oracle only; ordinary CI does not install or run that separate oracle. CI uses `pytest -rs` and an explicit job-summary note so the opt-in Jaeger skip and any absent SciPy are never presented as passes. See [CI scope and pinned actions](docs/ci.md). The runtime graph engine and independent replay use the standard library.

## Existing tools and prior art

ClockWeave does not introduce a new graph algorithm. Trace Compass already supports custom application-event matching, pairwise convex-hull synchronization, constant/linear transforms and graph composition. Jaeger and Zipkin provide useful recursive display correction; Perfetto uses recorded clock snapshots. A small distributed-tracing-correlator project already describes the same offset bands. See [the full comparison](docs/prior-art.md). The prospective value here is the bounded export/qualification/epoch/diagnosis/replay workflow, with adoption still unproven.

MIT licensed. Original example data is generated by the included harness; no third-party issue trace fixture is redistributed.
