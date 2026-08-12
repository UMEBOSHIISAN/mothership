# Installation and Flight lifecycle

Mothership requires Python 3.12 or newer and has zero runtime dependencies. A source install can need build tooling
already available to pip; build requirements are not runtime dependencies.

## Source install

From a source checkout, create and activate a virtual environment, then run `python -m pip install .`. This is the only
standard lifecycle step that changes the package environment. `mothership verify` checks installed resources without
installing companions, changing configuration, or contacting a network service.

## Import

Use `mothership import generic events.jsonl --out ./flight-001` to translate one explicitly supplied Generic JSONL file
into one explicit Flight Bundle directory. Import does not inspect a repository, home directory, process, or environment
dump.

## Verify

Use `mothership verify run ./flight-001` to recompute the bundle verdict from index, events, and selected artifacts. It
is read-only and does not grant authority, repair a bundle, retry missing work, or fetch evidence.

## Replay

Use `mothership replay ./flight-001` to print a causal lifecycle projection. Replay reads a bundle and never re-executes
the action represented by an execution receipt.

## Report

Use `mothership report ./flight-001 --format markdown` to emit a derived Markdown report to standard output. It writes
only when supplied an explicit destination. Reports can be regenerated and are not trusted bundle input.

## Demonstrations

`mothership demo safe` verifies the safe bundle and exits 0 with `COMPLETE`. `mothership demo drift` verifies the drift
bundle and exits 21 with `DRIFTED`; that documented nonzero exit is a verdict, not corrupted output.

## Uninstall

Use your environment manager or `python -m pip uninstall mothership-control-plane` to intentionally remove an
installation. Mothership leaves no managed daemon, scheduler, startup setting, or credential store.
