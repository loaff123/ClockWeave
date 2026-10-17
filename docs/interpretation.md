# Reading a result

ClockWeave tests observations against an explicit model. It does not identify the physical cause of inconsistent telemetry.

## Compatible qualified subset

There is a joint assignment of one additive correction per declared domain/epoch satisfying every selected endpoint inequality. The example assignment is normalized to the declared anchor. Feasibility says nothing about excluded or unresolved observations, so inspect coverage before drawing a conclusion.

Each displayed interval is the coordinate projection of the same coupled feasible set. Individually possible values need not be jointly possible in combination. Every finite endpoint has an original-constraint path proving that bound and a full feasible assignment attaining it. Every unbounded side has a directed reachability cut. Disconnected components have unrestricted relative translation; their displayed example values are arbitrary choices.

A feasible correction is not an offset measurement or a probability interval. Constant-offset assumptions can be a poor approximation under drift, clock steps or mixed timestamp sources. Explicit epoch segmentation expresses a separate constant model; no transition relation is invented.

## Incompatible qualified subset

A negative cycle sums to a strictly negative bound on zero. Its edges retain rule IDs, raw endpoint values, trace/span references and original file pointers. The contradiction establishes that those selected observations and domain/epoch/boundary/slack assumptions cannot all hold at once.

It is not necessarily the shortest cycle or minimum set of observations. It does not single out the faulty clock, instrumented operation or assumed boundary. A headers-only client versus a body-completing server can contradict enclosure even when the clocks are perfect. Changing slack cannot validate an incorrect semantic comparison.

## Insufficient evidence and errors

Unknown or declared-adjusted provenance, an absent anchor or zero qualified inequalities yields insufficient evidence. Domain identity, boundary ambiguity and missing endpoints remain counted even when other observations allow a qualified-subset result.

Malformed input/contract, unsupported format/schema/size and I/O errors are separate diagnostic outcomes. They are never converted into incompatibility or silently ignored to rescue a diagnosis.

## Replay versus rendering

`verify` rereads the exact input bytes and contract, independently reconstructs canonical observations and all qualification/inequalities, and checks the arithmetic/traversal witnesses. It does not call the production optimizer or the production semantic readers. Deliberate small duplication makes the result check less dependent on one extractor implementation; it is not a formal proof of software correctness.

The verification tests reject altered endpoints and mappings even if corresponding hashes are forged, missing constraints/observations, false ranges, non-attaining assignments, malformed cuts and false cycles. Hashes establish byte identity, not authentic collection, trustworthy assumptions or physical truth.

`render` checks complete supported structure and fixed limitation text only, and says so in its banner. Opening an HTML report does not independently verify it. Keep the original inputs and contract to run replay.

## Privacy and scope

Reports embed trace names, attributes and source labels. They use no external assets, telemetry or network access, but can reveal private application data if you share them. ClockWeave never uploads or republishes traces. Output alias checks and tested size limits address ordinary workflows; they are not guarantees against hostile concurrent filesystem races or arbitrary resource exhaustion.
