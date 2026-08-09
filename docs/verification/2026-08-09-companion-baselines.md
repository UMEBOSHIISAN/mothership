# Companion conformance baselines

Date: 2026-08-09

This record freezes local repository state before Mothership 0.2 companion-conformance work. Checkout locations are
intentionally omitted from this public document. No push, tag, release, deployment, or original-checkout cleanup was
performed.

## Repository state

| Repository | Original HEAD | `origin/main` | Original state | Latest tag | Isolated branch | Worktree base |
| --- | --- | --- | --- | --- | --- | --- |
| Agent Frontdoor | `4717635aa5786d2ff7d81798da96080905b8ff33` | `20e0274938c0a5947445601cf2fda1eabb9beea0` | local branch ahead; pre-existing `.audit_tmp3/` untracked | none | `codex/mothership-0.2-conformance-frontdoor` | `origin/main` |
| Workflow Governance Model | `1d8cebcacca3cdd4cab9cabd0e52fe2274dac4c2` | same | clean | `v0.2.1` | `codex/mothership-0.2-conformance-wgm` | `origin/main` |
| Mothership Router | `6f760f43d200d2f13ac0db864ce23974cde5b529` | same | clean | `v0.2.0` | `codex/mothership-0.2-conformance-router` | `origin/main` |
| Secretary TUI | `4060ec5dcf7fd49fd660f65dc386ccb64678238c` | `6ba4f94d3fa0845f650bca80a287ada16d35d3f1` | one reviewed README-only commit ahead | `v1.1.1` | `codex/mothership-0.2-conformance-secretary` | local `4060ec5` |

Secretary's ahead commit changes only the README repository-tree description and passes `git diff --check`. It is
intended user work, so the isolated branch preserves it. Frontdoor, WGM, and Router are based on their public
`origin/main` commits as required by the conformance plan.

## Rules precheck

The root README in every repository was read in full. Root `CLAUDE.md`, `AGENTS.md`, and `active_next.md` were absent in
all four repositories. No more-specific repository policy conflicts with the Mothership Wave 3 plan.

## Native baseline verification

| Repository | Toolchain | Command | Result |
| --- | --- | --- | --- |
| Agent Frontdoor | CPython 3.14.6, pytest 9.1.1, jsonschema 4.26.0 | `PYTHONPATH=src python -m pytest -q` | 616 passed |
| Workflow Governance Model | CPython 3.14.6 | `PYTHONPATH=src python -m unittest discover -s tests` | 11 passed |
| Mothership Router | CPython 3.14.6 | `PYTHONPATH=src python -m unittest discover -s tests` | 8 passed |
| Secretary TUI | Go 1.26.4 darwin/arm64 | `go test ./...`, `go vet ./...`, `go build ./...` | all passed |

The machine's default `python3` is unsupported Python 3.9.6, so it was not used as acceptance evidence. Go was not
installed system-wide. The exact official Go 1.26.4 Darwin ARM64 archive was used from a temporary directory after its
SHA-256 matched `b62ad2b6d7d2464f12a5bcad7ff47f19d08325773b5efd21610e445a05a9bf53`; no system path or installation changed.

## Isolation proof

After baseline tests, all four isolated branches were clean. Original HEADs and statuses matched the pre-work snapshot:
the Frontdoor `.audit_tmp3/` path remained untouched, WGM and Router remained clean, and Secretary remained at its
reviewed local README commit. These exact values are the comparison baseline for final closeout.
