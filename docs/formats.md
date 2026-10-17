# Supported evidence formats

All inputs are read-only UTF-8 files. No network reads, directory recursion, compressed input or protobuf decoding is implicit.

## OTLP JSON / JSONL

Supported JSON is an `ExportTraceServiceRequest` containing `resourceSpans`, resource attributes, `scopeSpans`, scope metadata and `spans`. The older `instrumentationLibrarySpans` container is accepted only when `scopeSpans` is absent. Both present is invalid. Unknown OTLP fields are ignored for extraction while the original file bytes remain hash-bound. The protobuf default-empty request `{}` is valid and yields insufficient evidence; an explicitly selected OTLP reader also ignores unknown fields when resourceSpans is absent. A nonempty unrecognized auto-detected object remains unsupported.

JSONL has one complete request object per nonblank line. Source references include the physical line number, document index, JSON Pointer, filename and SHA-256. `.jsonl` and `.ndjson` are auto-detected; use `--format otlp-jsonl` for another extension. Multiline records are not guessed.

Timestamps accept unsigned decimal strings or JSON integer tokens through 2^64−1. Booleans, floats, exponent notation, null and negative values are invalid timestamps. Arithmetic is arbitrary-precision integer nanoseconds. Kind is numeric enum 0..5; omitted is unspecified (0). Symbolic enum strings are unsupported OTLP encoding. Trace/span IDs are nonzero hex with lengths 32/16; case is normalized. Empty/zero parent IDs mean no parent.

AnyValue supports string, bool, int, finite double, bytes, array and kvlist metadata, with one value alternative. Duplicate attributes and duplicate JSON object keys are invalid. Complex metadata stays visible but has no inferred clock meaning. Canonical report metadata uses distinct bytes and kvlist tags, including nested values, so a user key cannot disguise a different AnyValue type. Missing endpoints are evidence gaps; malformed present endpoints invalidate input. A negative individual duration is retained and excluded from qualification.

These choices follow [OTLP's JSON mapping](https://opentelemetry.io/docs/specs/otlp/#json-protobuf-encoding), including hex IDs, integer enums and lowerCamelCase fields. This is a bounded export reader, not a general OTLP receiver.

## Legacy Jaeger JSON

The supported envelope is `{"data": [{"traceID": "...", "spans": [...], "processes": {...}}]}`. Standalone trace objects, Jaeger protobuf and Zipkin JSON are not this format.

`startTime` and `duration` are nonnegative integer microseconds, multiplied exactly by 1000. End is start + duration. Legacy 16-digit trace IDs are padded to 32; span IDs have 16 hex digits. Process tags become resource metadata; `serviceName` becomes resource `service.name` for inventory. Span tags stay typed. A recognized string `span.kind` tag maps to the corresponding enum.

Exactly one same-trace CHILD_OF reference provides a parent candidate. Multiple CHILD_OF references are ambiguous. FOLLOWS_FROM never becomes synchronous containment. Missing process metadata or parents remains visible. Warning text is retained; absent/null warnings mean none, while malformed non-array warning values are rejected.

## Duplicate and partial captures

Across the selected file set, `(trace_id, span_id)` identifies one observation. Exact imported-semantic duplicates retain all source references. Conflicts in endpoints, names, kinds, parent, attributes or scope fail explicitly, including boolean-versus-integer attribute conflicts. Ignored vendor fields do not participate in semantic equality.

Empty captures and captures without qualified edges produce insufficient evidence rather than unconstrained “success.” Conflicting format signatures, unknown formats and unsupported schema versions are distinct from malformed input. No file is silently dropped to produce a partial diagnosis.

Reports use decimal strings for every nanosecond value and null for unbounded endpoints. JSON numbers are retained for ordinary counts/enums. There are no floating-point epoch calculations or silently adjusted timestamps.

## Admission defaults

The default capture limit is 8 MiB combined input bytes and 10,000 observed span records, including duplicates. Qualified analysis accepts at most 64 declared domain/epoch variables. Exceeding a limit is an explicit unsupported-size result, never a partial diagnosis. These are measured ordinary-workflow limits, not hostile-input resource guarantees. Large report views can still be substantial; retain the authoritative JSON for replay.
