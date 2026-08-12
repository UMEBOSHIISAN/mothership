# Wave 2 proof-product rollout receipt

Measured on 2026-08-12. Each change was made on an isolated
`docs/mothership-10000-stars` branch. The source checkouts and result worktrees
were clean at their respective measurement points.

| Repository | Source state | Isolated worktree | Base HEAD | Result HEAD | Verification | Result state |
| --- | --- | --- | --- | --- | --- | --- |
| Agent Frontdoor | `main`; upstream not configured; clean | `.worktrees-10000-stars/agent-frontdoor` | `5ba58b262fd6a81fe19fa8f01d3c4e95e1607f73` | `9acf17a2b38fc7d43181f9e747ac91aa3bfbf8ef` | `../../agent-frontdoor/.venv/bin/python -m pytest -q` — 629 passed | clean; `git diff --check` passed |
| Workflow Governance Model | `main`; upstream ahead/behind `0/0`; clean | `.worktrees-10000-stars/workflow-governance-model` | `b94a85eb555f9e420ee528fe1cfa026aa549afb8` | `77f027d0142eca127cff0fbbadd58024007aa202` | `PYTHONPATH=src python -m unittest discover -s tests -v` — 18 passed; README contract — 1 passed | clean; `git diff --check` passed |
| Mothership Router | `main`; upstream ahead/behind `0/0`; clean | `.worktrees-10000-stars/mothership-router` | `8783f1495ec91aeb6716aba4735db8717d6d7fe2` | `a9eb0f13c67c68f34c5052c9f6a4fd2a288a5bce` | `PYTHONPATH=src ../../agent-frontdoor/.venv/bin/python -m unittest discover -s tests -v` — 20 passed; README contract — 1 passed | clean; `git diff --check` passed |
| Secretary TUI | `main`; upstream ahead/behind `0/0`; clean | `.worktrees-10000-stars/secretary-tui` | `8264692dbd36f75aee226ed8469f11f59a202624` | `92d2fb29a9426707d886866171e347e7530e48a8` | `go test ./...` — passed | clean; `git diff --check` passed |

## Environment note

The first Frontdoor and Router baseline attempts used the global Python 3.14.6
interpreter and stopped during collection because that interpreter did not have
the declared `jsonschema` test dependency. No dependency or repository file was
changed to mask the result. Both suites were rerun with the existing isolated
Frontdoor test environment, also Python 3.14.6, with `jsonschema` 4.26.0.

## Relationship boundary

All four repositories now identify themselves as independently adoptable parts
of the Mothership constellation and link to Mothership for whole-flight
authority, evidence, replay, or drift. The copy explicitly states that
Mothership does not install, invoke, or configure the companion. No runtime,
schema, command, exit-code, execution, or authority behavior changed.
