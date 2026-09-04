# Installation and lifecycle

Mothership requires Git for clone-based workflows and Python 3.12 or newer. Runtime commands have no third-party Python
dependencies. Package installation may resolve build tooling; normal verification and demo commands run offline.

**Installation is the only package-changing step** in the standard lifecycle. The installed `mothership` CLI does not
edit settings, credentials, schedulers, startup configuration, or companion repositories.

## Clone-first install

Use this path to inspect source before installing:

```sh
git clone https://github.com/UMEBOSHIISAN/mothership.git
cd mothership
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
python examples/authority_core_walkthrough.py
mothership verify
```

Side effects: Git creates the checkout, `venv` creates `.venv`, and pip installs Mothership and build metadata into the
environment. The walkthrough and verification command are read-only and use no external service.

## Wheel install

After obtaining a reviewed wheel and its SHA-256 through a trusted channel:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --no-deps mothership_control_plane-0.4.1-py3-none-any.whl
mothership verify
```

`--no-deps` is valid because the wheel declares zero runtime requirements. Verify the expected digest before install.
Mothership 0.4.1 has not been claimed as available on a package index.

## Editable development install

Contributors can expose the checkout directly:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[test]"
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -v
```

Side effects: pip writes editable-install metadata into `.venv`; tests create only temporary data when the bytecode flag
is set. The test extra contains build tooling, not runtime functionality.

## Verify

Run both artifact and source checks when preparing a release candidate:

```sh
mothership verify
mothership demo
python tools/run_evaluation.py
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -v
```

`verify` checks the installed resource inventory. `demo` proves the bundled `protocol-composition-only` chain.
`run_evaluation.py` measures the tracked synthetic corpus. The full test suite covers source and distribution behavior.
None of these commands grants `authority_effect` or `execution_effect`.

## Diagnostics

Use `mothership doctor` only when you intentionally want local CLI availability observations. Codex and Claude probes
run fixed version/help shapes. The Ollama detail probe may query an existing default loopback daemon. Diagnostics never
authenticate, install a tool, invoke a model, or repair an unavailable alias.

## Update

There is no self-updater.

1. Obtain the intended source commit, tag, or wheel through a trusted channel.
2. Read `CHANGELOG.md` and verify its checksum evidence.
3. Install into a new virtual environment rather than overwriting the working one.
4. Run the Authority Core walkthrough, `mothership verify`, `mothership demo`, and the applicable tests.
5. Switch your own workflow only after reviewing the result.

The operator owns the environment switch and rollback.

## Uninstall

For a virtual-environment install:

```sh
python -m pip uninstall mothership-control-plane
```

For an isolated project environment, removing that environment is sufficient. A source checkout can be removed through
the operator's normal file-management process. Mothership leaves no managed daemon, scheduler, editor setting, or
credential store behind.

## Troubleshooting

| Symptom | Closed interpretation | Next check |
| --- | --- | --- |
| Python is older than 3.12 | unsupported environment | choose a supported interpreter |
| `verify` returns 1 | installed resources did not validate | reinstall from reviewed bytes |
| `doctor` returns 1 | one or more local probes are unavailable | inspect its sanitized JSON |
| protocol validation returns 1 | the kind, file, or document is invalid | review without weakening checks |
| pip needs network access | build tooling is not locally available | pre-provision reviewed build tools |
