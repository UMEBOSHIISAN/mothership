# Installation and lifecycle

Mothership requires Git for clone-based workflows and Python 3.12 or newer. Runtime commands have no third-party Python
dependencies. Package installation may resolve build tooling; normal verification and demo commands run offline.

**Installation is the only package-changing step** in the standard lifecycle. The installed `mothership` CLI does not
edit settings, credentials, schedulers, startup configuration, or companion repositories.

## Clone-first install

Use this path to inspect the current main source before installing. It includes
the v0.4.2 documentation and offline walkthrough added after v0.4.1; the
walkthrough is a source-checkout example and is not part of either the v0.4.1
or v0.4.2 release tag or wheel.

The published v0.4.2 release remains the historical stable baseline. The
published `v0.5.0.dev0` prerelease and the unpublished dev1 source candidate
are separate revisions. The remote default branch includes the portable review
API merged through PR #43 and readback / inspect-sidecar functionality merged
through PR #45. A main checkout and a published release tag are separate
revisions; compare their SHAs. For the published three-wheel reader, use the
dev0 recipe under [Wheel install](#wheel-install). To reproduce an earlier
source-pinned reader candidate, use the fixed setup in the
[host adapter guide](host-adapters.md#try-the-current-candidate); that is a
source checkout recipe, not the published wheel install. The historical PR #56
and PR #45 recipes remain separate there, and the six-case recipient exercise
retains its historical reader pin.
For a historical pinned Core and companion runtime, use the
[portable review installation](action-review.md#install-the-source-candidate).
Optional SDK extras remain opt-in. The clone-first commands below install Core
only; they do not provide `mothership-evidence`.

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
environment. The source-checkout walkthrough writes only a temporary ledger and removes it on exit; `mothership verify`
is read-only. Neither uses an external service.

## Wheel install

### Published v0.5.0.dev0: three-wheel reader

Download these three wheel assets and the `SHA256SUMS` asset from the
[v0.5.0.dev0 GitHub Release](https://github.com/UMEBOSHIISAN/mothership/releases/tag/v0.5.0.dev0)
into one directory. These are the exact published wheel names and SHA-256
values reported by the release asset metadata and its downloaded manifest:

| Wheel asset | SHA-256 |
| --- | --- |
| `mothership_control_plane-0.5.0.dev0-py3-none-any.whl` | `d0a2622d71a3873871ab9d487ec67ad68892935bf7d652e50d636cb20437f9ce` |
| `mothership_github-0.3.0.dev0-py3-none-any.whl` | `4f1bbe4a6df615a57b24b8233ad16b50c07a4bd389fdd5f1edaedd1c065895ef` |
| `mothership_adapters-0.1.0.dev0-py3-none-any.whl` | `676ab9d7129c1575b6b470e63a3b62489c8bd0866ee6a70dcac518a2afcc64ce` |

The Release asset `SHA256SUMS` lists all six distribution archives (three
wheels and three sdists). The repository-root `SHA256SUMS` has the same name
but inventories tracked source files; it is not the release-wheel manifest.
Save this as `verify_wheels.py` beside the downloaded files. It checks each wheel
against both the published digest below and the downloaded Release asset:

```python
from hashlib import sha256
from pathlib import Path

manifest = {}
for line in Path("SHA256SUMS").read_text(encoding="ascii").splitlines():
    digest, name = line.split(maxsplit=1)
    manifest[name] = digest

expected = {
    "mothership_control_plane-0.5.0.dev0-py3-none-any.whl":
        "d0a2622d71a3873871ab9d487ec67ad68892935bf7d652e50d636cb20437f9ce",
    "mothership_github-0.3.0.dev0-py3-none-any.whl":
        "4f1bbe4a6df615a57b24b8233ad16b50c07a4bd389fdd5f1edaedd1c065895ef",
    "mothership_adapters-0.1.0.dev0-py3-none-any.whl":
        "676ab9d7129c1575b6b470e63a3b62489c8bd0866ee6a70dcac518a2afcc64ce",
}
for name, expected_digest in expected.items():
    manifest_digest = manifest.get(name)
    actual = sha256(Path(name).read_bytes()).hexdigest()
    if manifest_digest != expected_digest or actual != expected_digest:
        raise SystemExit(f"missing manifest entry or SHA-256 mismatch: {name}")
    print(f"OK {name}")
```

Run `python3.12 verify_wheels.py` from that directory, then install the verified
files with these commands:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --no-index --no-deps \
  mothership_control_plane-0.5.0.dev0-py3-none-any.whl \
  mothership_github-0.3.0.dev0-py3-none-any.whl \
  mothership_adapters-0.1.0.dev0-py3-none-any.whl
.venv/bin/python -m pip check
.venv/bin/mothership verify
.venv/bin/mothership-evidence inspect-result --help
```

`--no-index --no-deps` is appropriate for these matching wheels: the companion
and adapters declare their exact Mothership package dependencies, and the
recorded wheel set has no external runtime dependencies. This prerelease is a
GitHub Release, not a claim of package-index availability. Node host wrappers
and the Dots skill are source-tree files, not wheel contents; optional SDK
extras require their own dependency installation.

### Unpublished v0.5.0.dev1 source candidate

The following names describe an unpublished source candidate, not Release assets.
Use them only after building and reviewing all three wheels from the same fixed
source checkout and checking their separate artifact hashes:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --no-index --no-deps \
  mothership_control_plane-0.5.0.dev1-py3-none-any.whl \
  mothership_github-0.3.0.dev1-py3-none-any.whl \
  mothership_adapters-0.1.0.dev1-py3-none-any.whl
.venv/bin/python -m pip check
.venv/bin/mothership verify
.venv/bin/mothership-evidence inspect-result --help
```

For a source-pinned installation without a published candidate, use the
[fixed source setup](host-adapters.md#try-the-current-candidate). Optional SDK
extras remain opt-in.

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
4. From a source checkout, run the Authority Core walkthrough; then run `mothership verify`, `mothership demo`, and the
   applicable tests. A wheel-only install should use the installed `mothership verify` command and omit the source-only
   walkthrough.
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
