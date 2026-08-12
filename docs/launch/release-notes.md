Local draft — not published

# Mothership Flight Recorder

This local release-note draft introduces an evidence-first flight model for
AI-agent runs. It makes no tag, release, deployment, or remote-availability
claim.

## Proof included

- `mothership demo safe` emits a canonical `COMPLETE` verdict and exits 0.
- `mothership demo drift` emits a canonical `DRIFTED` verdict with
  `FLIGHT.DRIFT.ACTION_CLASS` and exits 21.
- Generic JSONL import, run verification, causal replay, and Markdown reporting
  operate on explicit caller-supplied paths.
- Generated CLI evidence and a deterministic terminal GIF are checked into the
  repository and tested against current command bytes.

## Compatibility

- Python 3.12 or newer is required.
- The measured local environment is Python 3.14.6 on macOS.
- The package has zero runtime dependencies.
- Existing v0.2 protocol and public-facade behavior remains covered by the
  regression suite.

## Safety limits

Mothership records no ambient state and does not launch an agent, call a model,
grant authority, retry work, repair evidence, or deploy anything. Verification
is limited to supplied records and cannot prove omitted or unobserved actions.

## Release decision still open

Version, tag, GitHub release, branch publication, repository metadata, social
preview, and announcement timing require separate explicit decisions and
measured remote verification.
