# Installation and Flight lifecycle

Mothership requires Python 3.12+ and has zero runtime dependencies. A source install can need build tooling already
available to pip; build requirements are not runtime dependencies. **Installation is the only package-changing step** in
the standard lifecycle. The installed CLI does not edit settings, credentials, schedulers, startup configuration, or
companion repositories.

## Clone-first install

```sh
git clone https://github.com/UMEBOSHIISAN/mothership.git
cd mothership
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
mothership verify
mothership demo safe
```

Git creates the checkout, `venv` creates `.venv`, and pip writes package/build metadata into the environment. The
Mothership commands are read-only. In a pre-provisioned offline environment, keep the public command unchanged and set
`PIP_NO_INDEX=1`, `PIP_NO_BUILD_ISOLATION=1`, and the pre-provisioned `PYTHONPATH` outside the document command.

## Wheel install

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --no-deps mothership_control_plane-0.2.1-py3-none-any.whl
mothership verify
```

`--no-deps` is valid because the wheel declares zero runtime requirements. Review the wheel and its digest before
installing; package-index availability is unmeasured here.

## Editable development install

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[test]"
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -v
```

The test extra contains build tooling, not runtime functionality.

## Verify

```sh
mothership verify
mothership demo safe
python tools/run_evaluation.py
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -v
```

`mothership verify` checks installed resources. The retained `mothership demo` command remains exact v0.2
`protocol-composition-only` evidence; `mothership demo safe` is the Flight demonstration.

## Import

Use `mothership import generic events.jsonl --out ./flight-001` to translate one explicitly supplied Generic JSONL file
into one explicit Flight Bundle directory. Import does not inspect a repository, home directory, process, or environment
dump.

## Verify a Flight Bundle

Use `mothership verify run ./flight-001` to recompute the bundle verdict from index, events, and selected artifacts. It
is read-only and does not grant authority, repair a bundle, retry missing work, or fetch evidence.

## Replay and report

Use `mothership replay ./flight-001` to print a causal lifecycle projection. Use
`mothership report ./flight-001 --format markdown` to emit a derived Markdown report to standard output. Replay and
report never re-execute an action and do not write a destination file; reports can be regenerated and are not trusted
bundle input.

## Update

There is no self-updater. Obtain an intended source commit, tag, or wheel through a trusted channel, review the
changelog/checksum evidence, install into a new environment, run `mothership verify` and applicable tests, then make
the environment switch yourself.

## Uninstall

```sh
python -m pip uninstall mothership-control-plane
```

Mothership leaves no managed daemon, scheduler, startup setting, or credential store.
