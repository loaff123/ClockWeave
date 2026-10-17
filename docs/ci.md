# CI scope and pinned actions

The checked-in workflow targets Linux, macOS and Windows with Python 3.10, 3.12 and 3.13. This configuration alone is not evidence that any external job ran.

The following official v7 tag references were read from GitHub's API on 2026-10-08, dereferenced to commits and checked against each official action.yml. The workflow pins these immutable commits rather than a moving major tag:

- actions/checkout: [3d3c42e5aac5ba805825da76410c181273ba90b1](https://github.com/actions/checkout/commit/3d3c42e5aac5ba805825da76410c181273ba90b1)
- actions/setup-python: [5fda3b95a4ea91299a34e894583c3862153e4b97](https://github.com/actions/setup-python/commit/5fda3b95a4ea91299a34e894583c3862153e4b97)

Checkout uses `persist-credentials: false`; workflow permissions are read-only contents.

## What ordinary CI does and does not run

Ordinary CI installs the built wheel with the OpenTelemetry integration extra and runs pytest with `-rs` so all skip reasons appear. This includes standard-library graph/replay tests and the actual loopback capture workflow.

The external Jaeger runtime comparison is opt-in. It is skipped unless both `CLOCKWEAVE_JAEGER_BINARY` and `CLOCKWEAVE_BASELINE_CAPTURE` are explicitly set. Its skip is not a pass. The separate local qualification did supply the checksum-verified official binary and original capture and actually executed this test.

The larger SciPy/HiGHS differential oracle is a separate development command, `tools/oracle_check.py`. Ordinary matrix jobs neither install SciPy nor run this tool. The job summary explicitly states when SciPy is absent and labels the oracle NOT RUN. Even if SciPy happens to be installed, presence alone is not an oracle pass. The retained 1,000-case local oracle results are separate executed evidence.

The workflow prints this distinction to both its log and job summary before testing. Skipped or unexecuted checks are never counted as passing checks. If OpenTelemetry is not installed in a local environment, pytest also reports that optional integration test as skipped; the ordinary workflow deliberately installs it.
