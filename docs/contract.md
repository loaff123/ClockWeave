# Qualification contract v1

Start with `examples/loopback/contract.json` for the application-owned reference or `examples/tiny/contract.json` for the tiny original fixtures. Never assume that another application's boundaries follow those semantics.

## Root

Required: `schema: "clockweave.contract.v1"`, `provenance`, `identities`, `boundaries`, `anchor`. Optional: `description` (empty string), `exclusions` (empty array). Unknown fields are rejected so typos cannot silently weaken qualification.

`provenance` has `state` (`raw`, `unknown`, `adjusted`), a nonblank `assumption`, and a nonempty list of source-reference strings called `evidence`. Only raw-declared input permits diagnosis. This declaration is an operator assumption, not proof that a viewer never adjusted the data. The explicit metadata attribute `clockweave.timestamp.state=adjusted` blocks a raw diagnosis; Jaeger warning text is retained as a hint, not an all-purpose detector.

`anchor` names the exact `{ "domain": "A", "epoch": "driver" }` to normalize to zero. There is no fallback if it is absent. Every example and endpoint-attaining assignment uses this anchor. Disconnected components retain arbitrary relative translation.

## Selectors

A selector is an object with these optional members:

- `names`: exact span-name membership
- `kinds`: numeric OTLP enum membership, 0 through 5
- `scope_names`: exact instrumentation-scope membership
- `resource`: resource attribute key/value equalities
- `attributes`: span attribute key/value equalities

Every supplied group is ANDed. Membership inside a list is ORed. Empty selector matches all; an empty membership list matches none. Attribute equality is type-sensitive and accepts string, boolean or integer scalar values. There is no regex, wildcard or coercion. Complex/double/bytes metadata is retained but cannot become a selector scalar or identity implicitly.

## Domain and epoch identity

Each identity rule has `id`, `select`, `domain`, `epoch`, `assumption`, `evidence`. Domain and epoch are each exactly one of:

```json
{"resource_attribute": "clockweave.clock.domain"}
{"span_attribute": "application.clock.epoch"}
{"literal": "explicit-window"}
```

Resolved identities must be nonempty strings. Multiple matching identity rules are ambiguous, even if they appear to produce the same values. Missing identity attributes remain unresolved.

A domain/epoch tuple means one constant correction for this analysis set. Distinct epochs have no implicit equality. A literal epoch deliberately assumes the capture fits one correction epoch. A service name, host label or process ID can be used only by an explicit rule with its assumption shown; the program never chooses one for you.

## Endpoint boundaries

A boundary has `id`, `client` selector, `server` selector, `link: "parent"`, and a nonempty `relations` list. The server must have the selected client as its same-trace parent. Multiple matching boundary rules are unresolved. Generic parenthood and span kinds never create a boundary rule.

Each relation declares `kind`, `slack_ns` (nonnegative integer decimal string), a nonblank `assumption`, and nonempty `evidence` references. At most one of each relation kind is allowed:

- `start_order`: corrected client start ≤ corrected server start + slack
- `end_enclosure`: corrected server end ≤ corrected client end + slack

Either may be qualified separately. A missing end does not erase an available qualified start relation; the missing end is reported. A negative individual raw duration makes that span unavailable under this model.

For corrections xC/xS and original endpoints cs/ce/ss/se, start_order gives xC − xS ≤ ss − cs + slack. End enclosure gives xS − xC ≤ ce − se + slack. Each slack is an independent conservative inequality relaxation, not a shared endpoint-error variable or statistical confidence interval. Nonnegative decimal slacks remain arbitrary-precision, including values beyond Python’s default decimal-conversion digit threshold; no interpreter-wide setting is changed. It cannot make semantically incomparable boundaries comparable.

An ordinary HTTP client span may end at response headers. Do not add end enclosure merely because both spans look synchronous. The reference harness explicitly closes its fully consumed client span after reading the body and its server span before releasing response bytes; the headers-only control selects only starts.

## Exclusions and inspection

An exclusion has `id`, `select` and nonblank `reason`. It removes matching spans from boundary qualification but retains inventory and identity information. PRODUCER/CONSUMER or FOLLOWS_FROM relations never become synchronous containment automatically.

Run `inspect` with the contract before relying on a solve. It lists each span identity and every observed parent candidate, selected rule/relations and exclusion/unresolved reason. Missing parents, incomplete endpoints, ambiguous identities and unmatched boundaries remain visible. “Compatible” can therefore apply to a small qualified subset; review coverage.

Evidence references are recorded as text. They are not fetched or treated as executable instructions, and ClockWeave does not certify their truth. One contract can be reused on new captures whose emitted identities and stable instrumentation labels obey those assumptions.
