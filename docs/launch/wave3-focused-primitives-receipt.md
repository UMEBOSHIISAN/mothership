# Wave 3 focused-primitive rollout receipt

Measured on 2026-08-12. Each source checkout was clean before an isolated
`docs/mothership-10000-stars` worktree was created. Each result branch is clean
and passes `git diff --check`.

| Repository | Base HEAD | Result HEAD | Native verification | Boundary verification | README lines |
| --- | --- | --- | --- | --- | ---: |
| Agent Team Runtime | `0c13bee3cf65115116320d0d9448416923672f93` | `9ae42a4d58380b4e04c6c704f8fdeb17960e440e` | `PYTHONPATH=src python -m unittest discover -s tests -v` — 76 passed | local-only/no-dispatch assertions included in suite | 34 |
| Evidence Spine Core | `a0a9b83d73d8950c4e5b9c8424eaea9271b84892` | `6f5453d98e782fc0329befa8601f4cb704eb5135` | public-tree unittest discovery — 29 passed | `tools/check_public_boundary.py .` — passed | 36 |
| Run Lineage Core | `e13de91718743af802027efba7afeae6397dc7b3` | `7291aaf41161e0536363982f6d9579dd3c803c48` | unittest discovery — 18 passed | `tools/check_public_boundary.py .` — passed | 65 |
| Source Health Core | `b7c362e04c9daab13f207a9d37025f3907493fae` | `322a007ba323bed3d3e026c6b5a057ef747bc593` | unittest discovery — 50 passed | `tools/verify_public_boundary.py .` — `PASS`, 49 files, zero detections | 189 |
| Agent Decision Core | `a0bb51d2616cf83ae5bc37ce45c88b4525e4ab78` | `f944bfe94a2eefd995cad56b163d05307aab9796` | public-tree `npm test` — 11 passed | `tools/check-public-boundary.js .` — passed | 44 |
| Knowledge Lifecycle Kit | `a8d8a79f11a58316b5a9279e023fa96903ead426` | `940073ac2308ff3c1eb594eca2eee8a24c18fe55` | unittest discovery — 13 passed | public-boundary and public-layout assertions included in suite | 62 |

No Tier 2 README exceeds 220 lines.

## Visual and relationship evidence

Each repository has one local, editable SVG with `<title>` and `<desc>`. All
six SVGs parsed as XML and were rendered to PNG for visual inspection; no
clipping, overlap, or unreadable contrast was observed. The diagrams show the
repository's measured behavior: replay reduction, an append-only evidence
chain, exact versus proposed joins, source-envelope claim limits, an
advisory-only decision gate, and a human lifecycle gate.

Every README states `Part of the Mothership constellation.`, links discovery
to Mothership, preserves independent adoption, and says Mothership does not
install, invoke, or configure the primitive. No runtime or schema changed.

## Environment notes

- Source Health declares `jsonschema` in its test extra. The global Python
  lacked that extra, so tests used the existing isolated Python 3.14.6 test
  environment with `jsonschema` 4.26.0. Generated `__pycache__` directories
  were kept outside the public tree, and the final boundary scan passed.
- Evidence Spine Core and Agent Decision Core ignore a `.git` directory, but
  Git worktrees use an absolute-path-bearing `.git` file. Their unchanged
  scanners correctly passed against `.git`-free temporary copies representing
  the publishable tree. `git diff --check` and clean-state checks were run
  separately in the real worktrees.
