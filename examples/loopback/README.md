# Application-owned loopback HTTP reference

This original reference workflow performs real loopback HTTP requests with the OpenTelemetry Python SDK. It is deliberately narrow: a driver and two service processes run on one physical host. Their timestamp offsets are injected at instrumentation boundaries, not measured clocks. No system clock is changed.

Install the optional `opentelemetry-sdk` and `opentelemetry-exporter-otlp-proto-http` development dependencies, then run:

```
python examples/loopback/capture.py --output /tmp/clockweave-capture
```

The output directory must not already exist. The script writes the original SDK protobuf, official-encoder-derived OTLP JSON, JSONL, an explicitly microsecond-rounded Jaeger comparison view, and process lifecycle metadata.

## Clock identity

The application supplies `clockweave.clock.domain` and `clockweave.clock.epoch` resource attributes. A is the stable driver. B and C are separate spawned processes. C is stopped and a new C process is started with a new epoch and a different deliberate instrumentation offset. Start/stop acknowledgments and PIDs document the actual restart. Epochs are part of the model, not inferred from service names.

## Qualified boundaries

- `fully-consumed-rpc` starts before sending and ends after reading the body.
- `handler-before-response` starts after receiving and ends before response bytes are released.
- `client-until-headers` legitimately ends when response headers arrive while `server-through-response-body` continues. The contract includes only their request-start ordering.
- Background producer/consumer work outlives its producer and is explicitly excluded.

The unchanged `contract.json` selects those stable labels and explicit identity attributes. Generated trace/span IDs and service epoch IDs need no per-capture edits. It can be reused on multiple independent runs. Authoring these instrumentation boundaries, attributes and contract assumptions is a one-time setup cost; arbitrary existing automatic instrumentation is not automatically qualified.

The comparison utility in `tools/compare_jaeger.py` executes an operator-supplied official, checksum-verified Jaeger 2.22.0 binary. It starts local transient in-memory instances with correction disabled/enabled and retains exact shared query exports plus per-span adjustments/warnings. Jaeger's successful display corrections are useful; global declared-model diagnosis has a different purpose.
