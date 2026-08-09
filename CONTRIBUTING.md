# Contributing to Mothership

Thanks for helping make local AI tooling more inspectable. Keep changes small, evidence-backed, and inside the stated
authority boundary.

## Setup

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[test]"
```

## TDD workflow

1. Add the smallest failing test that expresses the intended public contract.
2. Run the focused test and confirm the failure is the expected one.
3. Implement the smallest change that makes it pass.
4. Run `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v`.
5. Run `python3 -m mothership verify`, `python3 -m mothership demo`, and `python3 tools/run_evaluation.py`.
6. Run `git diff --check` and inspect every changed byte before committing.

Do not weaken a guard or delete a regression test to make a change green.

## Protocol changes

The companion **schema owner** retains semantic ownership. A protocol contribution must identify the owner release and
source path, update the frozen schema and SHA-256, refresh registry edges and fixtures, update compatibility documents,
and pass package plus companion conformance tests.

Do not overwrite a versioned snapshot or infer compatibility from a similar shape.

## Claims and evidence

- Describe synthetic corpus results as synthetic.
- Keep test counts separate from accuracy claims.
- Link performance or security statements to reproducible artifacts.
- Record limits, denominators, environment, and commit range.
- Never claim publication, adoption, production readiness, or certification without external evidence.

## Safety boundaries

Changes must not add implicit model invocation, automatic routing, retries, fallback, credential access, companion
installation, background services, or approval from validation. Any proposal to change those boundaries needs a separate
human-approved design before implementation.

## Public-data hygiene

Do not commit secrets, personal paths, hostnames, private endpoints, prompt bodies, model output, or machine-specific
commands. Use fictional fixtures. Construct any sensitive-looking test token without embedding a real value.

## Pull requests

Explain the problem, boundary, test-first evidence, compatibility impact, and remaining limitations. Keep unrelated
refactors out of the change. A clean test run is necessary but does not replace review.
