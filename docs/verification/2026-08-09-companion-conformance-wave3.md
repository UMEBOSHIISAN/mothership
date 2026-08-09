# Companion conformance Wave 3 verification

Date: 2026-08-09

Subject: unreleased Mothership 0.2.0 candidate and four pinned companion candidates

Mothership code HEAD measured by this evidence record: `332b45170c4b5627462dd1fff2fb378362998166`

This is a local verification record. No branch was pushed, no tag or GitHub Release was created, no package was
uploaded, and no system was deployed. The measurements below describe synthetic conformance and packaging behavior;
they are not production-accuracy or generalization claims.

## Closed-suite result

The explicit four-root conformance audit passed with this frozen owner set:

| Owner | Commit | Protocol | Schema SHA-256 |
| --- | --- | --- | --- |
| Agent Frontdoor | `4bcfcb6c1868a87076502999a38127e28e275e70` | `frontdoor-task` `intake.v0` | `6d6ed4aea9d3f5612c5292a2f46c72634776dc27998b61cdcdbdba3f35e7ca7e` |
| Workflow Governance Model | `98576b4f3f755aceccc657bc83df7c94260d4fc0` | `governance-handoff` `1.1` | `75f96909fa31a8bcf65d74d243aeea0e8b43185b13974f19f60f47cf769125c7` |
| Mothership Router | `a23f4b651e1a8baf39a1266a66188bec21c3265c` | `router-manifest` `1.0` | `273b1def57ec35957750c4979c737480c4cbb7f4db2294993dd5475b54fc673b` |
| Secretary TUI | `f3cb61e61bc88e7c4cfd09efe93006c812258fe9` | `observation-snapshot` `1.0` | `587ef29c693a834ffada7789b28b2b76cbefbad819386b91507a510def3facb2` |

The auditor accepted 4/4 owner manifests, matched 4/4 owner schema digests, confirmed 4/4 bundled snapshots were
byte-identical to their owners, and accepted 4/4 public examples. The synthetic chain preserved task identity,
`code-review` capability, Router status, and Secretary observation continuity. All four owner manifests and the final
chain reported `authority_effect: false` and `execution_effect: false`.

The audit was run with:

```sh
PYTHONDONTWRITEBYTECODE=1 "$PYTHON314" tools/check_companion_conformance.py \
  --frontdoor-root "$FRONTDOOR_ROOT" \
  --wgm-root "$WGM_ROOT" \
  --router-root "$ROUTER_ROOT" \
  --secretary-root "$SECRETARY_ROOT"
```

The `PYTHON314` variable identified the preprovisioned CPython 3.14.6 interpreter, and the root variables identified
four explicit, normalized local checkout roots. The canonical result was path-free JSON.

## Native verification

| Repository | Toolchain | Final result |
| --- | --- | --- |
| Mothership | CPython 3.14.6 | 225/225 unittest cases passed in a fresh shallow clone |
| Agent Frontdoor | CPython 3.14.6 | 628/628 pytest cases passed; the final documentation-only command reproduction passed 12/12 |
| Workflow Governance Model | CPython 3.14.6 | 18/18 unittest cases passed; checksum manifest passed |
| Mothership Router | CPython 3.14.6 | 20/20 unittest cases passed; checksum manifest passed |
| Secretary TUI | Go 1.26.5 darwin/arm64 | `go test ./...`, `go test -race ./...`, `go vet ./...`, build, and snapshot checks passed |

The Mothership clone-first command was:

```sh
PYTHONDONTWRITEBYTECODE=1 "$PYTHON314" -m unittest discover -s tests -v
```

An earlier run from a bare `git archive` executed 218 tests and stopped only because the Markdown-link test deliberately
calls `git ls-files`; the archive has no `.git` metadata. No product assertion was accepted from that run. Repeating the
same suite in a depth-one clone restored the required tracked-file inventory. The final depth-one clone at
`332b45170c4b5627462dd1fff2fb378362998166` passed all 225 tests in 18.395 seconds.

## Synthetic evaluation

`PYTHONDONTWRITEBYTECODE=1 python3 tools/run_evaluation.py` reproduced the tracked result:

| Measurement | Result |
| --- | ---: |
| Valid protocol acceptance | 4/4 |
| Invalid protocol rejection | 20/20 |
| Total conformance agreement | 24/24 |
| Demo determinism | 8/8 runs, one byte-identical output |
| Resource integrity | passed |
| Authority-capable protocols | 0/4 |
| Execution-capable protocols | 0/4 |

The corpus SHA-256 is `9e53e824eccbc3aa477626db3455e3dece7733c40acf39e3c8402cc47df6d7f4`.
These are hand-authored synthetic conformance cases, not an independent field sample. In particular, 24/24 must not be
presented as a population accuracy or safety rate.

## Clean distribution evidence

Exactly one Mothership wheel and one source distribution were built from the clean shallow clone with:

```sh
"$PYTHON314" -m build --no-isolation --outdir "$DIST_DIR" .
```

| Artifact | SHA-256 |
| --- | --- |
| `mothership_control_plane-0.2.0-py3-none-any.whl` | `7efcdac1a5f995b2dda32d7e1c16ca28c6cf8a596ae5169a6494a644e0711ebc` |
| `mothership_control_plane-0.2.0.tar.gz` | `63041e4d87fb62efe02fbca3f7753d4761349e0a96b5e6b1b381810888cf8063` |

The wheel was installed with `--no-deps` into a fresh environment and exercised outside every repository. The console
script and `python -m mothership` forms passed for `verify`, `protocol list`, and `demo`. A separate editable
installation produced byte-identical output for all three read-only commands. The output SHA-256 values were:

| Command | SHA-256 |
| --- | --- |
| `verify` | `aa3ef4ec653c8a0a4add506a8eb602a1b0da16e827e73fdd0d662b23cbf80d56` |
| `protocol list` | `ca3d4a9b22b64eca03d1f73804f5452b6ee671697578a2ba28e7309ad0c411b7` |
| `demo` | `55e41eb2aef2ddf22adabe47303dc87d41c5b665bf894bfe99826a75d1853b98` |

The companion artifact checks also passed:

| Artifact | SHA-256 |
| --- | --- |
| Frontdoor wheel | `c2550ff771d9d8ffd5ad9ccc9fbe15068075f1e872fd71fd4e98fd60c3e12d01` |
| Frontdoor source distribution | `6c1127f43382ede9ffd2ab45fb2b76cac2fef275cfa3f9829e794cd60057ac73` |
| WGM wheel | `6f30a3035fc72d56f2c5569c7896833870a13dc07e030974217e4b0cc8e40bab` |
| WGM source distribution | `7136a7db98dd3689be2d475dcb0a76143b24a76d7140002d7fe4a14556356e75` |
| Router wheel | `1b20cf2e0eebdd9364038bf8b4ad4b9ece7d532dc956e491201878f6086e9e1d` |
| Router source distribution | `2f217173bd06ce04a688a7bc86006a80bfdf110ebcb8b34b90e6ed7caeadf272` |
| Secretary deterministic binary | `4b9eef85bc51cdba7758819b322625e8624520a60d4c177a448f701471dd3bae` |

The Python companion builds emitted a setuptools license-table deprecation warning with a 2027-02-18 deadline. It did
not affect package creation or smoke tests, but the metadata should be modernized before that deadline. Frontdoor's
fresh wheel smoke supplied its declared `jsonschema` runtime dependency from an existing dependency-complete
environment; the wheel itself was still installed with `--no-deps`. WGM and Router passed truly dependency-free wheel
smokes. Secretary produced the same binary digest in two builds using `-trimpath -buildvcs=false -ldflags=-buildid=`.

## Review fixes

Final review found and closed three fail-closed input-shape gaps:

1. WGM now rejects non-string `schema_version` values instead of allowing an unhashable JSON shape to raise.
2. Router now rejects non-string risk, schema-version, and executor-risk values before membership comparisons.
3. Secretary now rejects duplicate JSON object keys, so a later safe-looking key cannot conceal an earlier effectful
   value. It also rejects trailing JSON.

Frontdoor's conformance instructions now use the repository virtual environment with `PYTHONPATH=src`, matching the
commands that passed on macOS even when the hidden `.venv` directory is not processed as an editable site directory.
Mothership's auditor now reads companion evidence from pinned commit objects rather than dirty worktree bytes,
disables Git replacement objects and lazy fetching, and reads local resources through bounded no-follow file
descriptors. The optional `doctor` diagnostic also has a fixed five-second subprocess timeout and fails closed.
Commit-level Codex review reported no remaining actionable findings for these Mothership fixes or for the WGM,
Router, Secretary, and preceding Frontdoor documentation fixes.

## Security and boundary scan

The fixed `grep-audit` scan covered Mothership and all four companion trees:

| Check | Status | Count | Reviewed disposition |
| --- | --- | ---: | --- |
| `keys_env_ref` | ok | 0 | no finding |
| `direct_env_file` | hit | 3 | two archive-rejection fixtures and one Mothership path-rejection fixture; no environment-file read |
| `os_environ_secret` | ok | 0 | no finding |
| `hardcoded_secret_like` | hit | 3 | synthetic Frontdoor scanner fixtures; no usable credential |
| `exec_primitives` | hit | 91 | tests, deterministic evaluators, fixed local diagnostics, Git archive inspection, and a human-attended bounded acceptance lab |

The non-test process sites were reviewed. Mothership invokes only fixed local diagnostic probes when `doctor` is
explicitly requested, local Python demo evaluation, and Git commit inspection for the explicit conformance roots.
Frontdoor's process sites are isolated friend-pack build and human-attended acceptance tools with time, output, and
process-group bounds; they are not imported by the Frontdoor classifier. No finding adds credential access, implicit
model work, installation, authentication, scheduler or service mutation, deployment, retry persistence, or network
discovery.

## Original-checkout isolation

Final status checks found all five implementation worktrees clean at the exact Mothership and companion commits
recorded above. The pre-existing WGM and Router main checkouts remained clean at their baseline HEADs
`1d8cebcacca3cdd4cab9cabd0e52fe2274dac4c2` and `6f760f43d200d2f13ac0db864ce23974cde5b529`.

The pre-existing Frontdoor and Secretary main checkouts were also clean at closeout, but other concurrent work had
advanced them from their recorded baselines to `d75a006efacaf9ff18a631b83a9b40d8a31721a5` and
`03d0d3aeac90418b39b2de5a5bdd9033dcb755f5`. This record therefore does not claim those two original checkouts were
byte-for-byte unchanged during the elapsed period. Mothership conformance work used only the separately registered
companion worktrees and did not clean, stage, or commit either original checkout.

## Claim and handoff boundary

This evidence supports a local artifact-paper candidate about fail-closed protocol composition and authority as
versioned data. It does not support claims of production accuracy, formal verification, universal attack prevention,
causal productivity improvement, or external adoption. Publication, push, tag, release, package upload, deployment,
and companion-repository publication remain separate human-authorized decisions.
