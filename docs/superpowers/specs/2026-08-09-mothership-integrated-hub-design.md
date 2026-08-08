# Mothership Integrated Hub Design

**Date:** 2026-08-09
**Status:** HUMAN-SELECTED DESIGN
**Selected approach:** Mothership becomes the installable integration hub while companion repositories remain independently adoptable.
**Scope:** Public Mothership ecosystem only. Private operations, credentials, deployment, schedulers, and machine-specific configuration are excluded.

## 1. Goal

Turn Mothership from a collection of strong but manually composed public repositories into one coherent product experience.

Mothership becomes the only required starting point for discovery, installation, offline verification, protocol validation, and the synthetic ecosystem walkthrough. Agent Frontdoor, Workflow Governance Model, Mothership Router, and Secretary TUI remain focused companion products with their own repositories and release histories.

The result must make two facts clear at the same time:

1. Mothership is useful by itself as a portable, safety-first control plane.
2. The companion tools form a deliberate, versioned ecosystem rather than a set of unrelated links.

## 2. Product Position

Mothership is the hub, not an autonomous agent runtime.

Its public promise is:

> Bring the control plane for your AI coding environment across machines without bringing secrets, ambient authority, or invisible automation with it.

The hub owns:

- the public Python package and `mothership` command;
- the portable scope, approval, adapter-plan, diagnostic, and strict-contract APIs;
- the ecosystem protocol registry and bundled schema snapshots;
- the synthetic golden-path walkthrough;
- offline suite verification and release-integrity evidence;
- the canonical public explanation of how the ecosystem composes.

The hub does not own:

- task-intake policy implemented by Agent Frontdoor;
- workflow evidence semantics implemented by Workflow Governance Model;
- candidate selection and approval-bound dry-run manifests implemented by Mothership Router;
- terminal presentation implemented by Secretary TUI;
- model invocation, deployment, retries, fallback, credential management, hooks, schedulers, or background services.

## 3. Approaches Considered

### 3.1 Installable hub with independent companions — selected

Mothership provides the common package, CLI, protocol registry, fixtures, and documentation. Companions retain separate repositories and can still be installed and used independently.

This preserves clear authority boundaries and independent adoption while giving users a single starting point and a tested composition story.

### 3.2 Documentation-only umbrella — rejected

Improving only the README would leave users responsible for discovering compatibility, validating handoffs, and assembling the workflow manually. The result would improve presentation without creating an integrated product surface.

### 3.3 Public monorepo — rejected

Moving every companion into one repository would erase useful release and ownership boundaries, complicate language-specific tooling, and create a large migration unrelated to the user-facing integration problem.

## 4. Repository Topology

The public topology is fixed as follows:

| Repository | One responsibility | Independent use |
| --- | --- | --- |
| `mothership` | Installable hub, portable control-plane primitives, protocols, verification, and golden path | Yes |
| `agent-frontdoor` | Convert a bounded request into a fail-closed task card | Yes |
| `workflow-governance-model` | Validate workflow evidence and authority relationships | Yes |
| `mothership-router` | Match a reviewed request to a local registry and emit a human-gated dry-run manifest | Yes |
| `secretary-tui` | Display explicitly supplied local state without mutation | Yes |

Optional creative projects such as Git Vibes and Toygarden may be linked as adjacent projects. They are not members of the control-plane protocol chain and must not appear as required gates.

## 5. Installed Package and CLI

Mothership becomes a standard-library-only Python package requiring Python 3.12 or later.

The package exposes a console script and module entry point with identical behavior:

```sh
mothership --help
python -m mothership --help
```

The stable v0.2 command surface is:

```text
mothership verify
mothership doctor [ALIAS ...]
mothership protocol list
mothership protocol validate KIND FILE
mothership demo
```

### 5.1 `mothership verify`

Performs a read-only, offline integrity check of installed package resources:

- protocol registry structure and referenced bundled schemas;
- schema and fixture SHA-256 digests;
- golden-path stage ordering and identifier continuity;
- example executor configuration remaining non-executable;
- packaged version and public-resource inventory consistency.

It prints one closed JSON result and exits non-zero on any mismatch. It does not run the test suite, inspect unrelated user files, contact a network, or change the environment.

### 5.2 `mothership doctor`

Exposes the existing fixed diagnostic behavior for `codex-cli`, `claude-code-agent`, and `ollama-local`. It may run only the documented version and help/list probes in a sanitized child environment. It does not invoke a model, authenticate, install software, or edit settings.

### 5.3 `mothership protocol`

`list` prints the bundled protocol kinds, owner repositories, versions, schema identifiers, and SHA-256 digests.

`validate KIND FILE` strictly decodes one local JSON document and validates it against the selected bundled schema. Unknown kinds, versions, fields, duplicate keys, non-finite numbers, unsafe files, and malformed UTF-8 fail closed.

### 5.4 `mothership demo`

Validates the bundled synthetic golden path from beginning to end. It reads only packaged fixtures and produces a deterministic summary. It does not invoke companion commands, discover local repositories, use credentials, call a model, or make a network request.

## 6. Public Python APIs

The current implementations remain authoritative during the compatibility transition. New public modules provide stable names without a destructive code move:

| Public module | Initial implementation source | Public purpose |
| --- | --- | --- |
| `mothership.scope` | `orchestration.lib.paths` | Validate, measure, stage, lock, and safely create bounded local artifacts |
| `mothership.approval` | `orchestration.lib.ledger` | Record, consume, and finish single-use approval-bound attempts |
| `mothership.adapters` | `orchestration.lib.adapters` | Build immutable adapter plans and run fixed diagnostics |
| `mothership.contracts` | canonical/jsonio/contracts/registry modules | Strict JSON, canonical hashing, bundled contract validation, registry loading |
| `mothership.protocols` | new protocol registry and validator | Inspect and validate ecosystem interchange documents |

Compatibility exports are explicit and tested. Existing imports continue to work during v0.2. No implementation is copied into a second independent code path.

The existing `frontdoor.route` remains temporarily available for compatibility but is no longer presented as the ecosystem intake product. The public documentation points to Agent Frontdoor for intake and Mothership Router for reviewed routing. Removal, if ever selected, requires a later major-version decision.

## 7. Ecosystem Protocol Registry

Mothership owns a composition registry, not the domain semantics of every companion.

Each entry records:

- stable protocol kind;
- schema version;
- owning repository;
- upstream source path;
- bundled schema path;
- exact SHA-256 of the bundled schema;
- accepted predecessor and successor kinds;
- whether the document can carry authority or execution effects;
- the Mothership release that froze the compatibility snapshot.

The first ordered chain is:

```text
frontdoor-task
  -> governance-handoff
  -> router-manifest
  -> observation-snapshot
```

The registry and bundled snapshots are the suite-release SSOT. The owning companion remains the semantic owner of its schema. Updating a schema requires a coordinated change that refreshes the owner release, bundled snapshot, digest, fixtures, compatibility table, and conformance tests.

No protocol may contain credentials, provider endpoints, prompt bodies, model output, private absolute paths, ambient execution permission, or a claim that recommendation equals approval.

## 8. Synthetic Golden Path

`examples/golden-path/` contains fictional, credential-free documents for every stage:

```text
01-frontdoor-task.json
02-governance-handoff.json
03-router-manifest.json
04-observation-snapshot.json
expected-summary.json
```

The fixtures share one fictional task identifier and capability. Each transition is checked for:

- supported predecessor and successor kinds;
- exact schema version;
- identifier continuity;
- non-escalating risk and capability fields;
- `authority_effect: false` and `execution_effect: false` where applicable;
- absence of secret-like keys, private paths, commands, and raw content fields.

The demo proves protocol composition only. It must not be described as proof that a real task was approved, executed, completed, or verified.

## 9. README and Public Documentation

The root README is redesigned as the primary product page, not a repository inventory.

Its fixed narrative order is:

1. compact logo, product name, one-sentence promise, and useful badges;
2. a 60-second install, verify, and demo sequence;
3. an actual deterministic demo transcript or terminal recording;
4. the user problem and Mothership's answer;
5. the hub-and-spoke architecture diagram;
6. clear standalone and composed adoption paths;
7. the safety guarantees and non-goals;
8. a concise comparison with copying a home directory, an agent framework, and a model router;
9. public API and protocol links;
10. compatibility, contributing, security, roadmap, Japanese guide, and license.

README claims must be executable or traceable to tests and source. It may be ambitious in tone but must not imply autonomous execution, universal sandboxing, secret management, automatic installation of companions, production readiness, or user adoption metrics that have not been measured.

The Japanese README follows the same product story rather than becoming a shortened disclaimer page. Architecture, installation, composition, security, and protocol documentation must agree with the root README.

## 10. Safety and Authority Boundary

The integrated hub preserves the strictest existing boundary:

- no model or agent invocation;
- no automatic companion installation;
- no network access at runtime;
- no retry or fallback;
- no scheduler, daemon, hook, or background service;
- no credential or environment-file access;
- no configuration mutation;
- no repository mutation outside explicit development work;
- no approval inferred from a valid document;
- no recommendation promoted to selection or execution;
- no Secretary display promoted to freshness or operational truth.

Installation through `pip` is an attended user action. Runtime commands remain read-only except for the existing explicitly called scope-staging and output APIs used by a programmer in their own code; the default CLI does not expose those mutation-capable library operations.

## 11. Compatibility and Migration

The implementation must preserve these existing public behaviors:

- `bootstrap/doctor.sh` continues to work;
- `orchestration/bin/llm-doctor` and `orchestration/bin/llm-seat` continue to work;
- current `orchestration.lib` imports remain valid;
- current contract schemas retain their accepted and rejected shapes unless a protocol owner releases a versioned change;
- the existing 132-test Python 3.12+ suite remains green;
- Mothership remains usable directly from a clone without installing it.

The new package adds an easier path; it does not force current users onto a new configuration or remove the clone-first workflow.

## 12. Implementation Waves

### Wave 1 — Mothership hub

- packaging metadata and public module facades;
- CLI parser and read-only commands;
- protocol registry, bundled schemas, golden-path fixtures, and validators;
- TDD coverage for every new public behavior;
- backward-compatibility tests.

### Wave 2 — Product documentation

- root README rebuild;
- Japanese README parity;
- architecture, installation, composition, security, and protocol documents;
- deterministic demo asset generated from the real CLI;
- release checklist and checksum inventory updates.

### Wave 3 — Companion conformance

- each clean companion checkout validates its public output against the frozen suite protocol;
- compatibility documents name the exact supported protocol and Mothership release;
- pre-existing dirty work in Agent Frontdoor and unpushed Secretary TUI commits is preserved and reviewed before any overlapping edit;
- companion releases remain separate and require their own verification and publication decisions.

## 13. Testing and Verification

Implementation follows test-first development.

Required verification includes:

- unit tests for CLI grammar, output shape, exit codes, and failure precedence;
- protocol registry and schema digest tests;
- one failing-then-passing test for every golden-path transition;
- negative fixtures for unknown fields, stale versions, identifier drift, authority escalation, secret-like keys, private paths, malformed JSON, duplicate keys, and oversized files;
- clone-first tests and editable-install tests in a fresh Python 3.12+ environment;
- wheel build, wheel install, console-script, and `python -m mothership` parity tests;
- existing full-suite regression tests;
- README command extraction and execution tests;
- Markdown link validation for local and public links;
- checksum regeneration and verification only after final bytes are frozen;
- scoped secret, private-path, and execution-primitive review;
- final worktree ownership and diff audit before every commit.

The companion conformance wave requires each repository's own full test command. Passing Mothership tests alone cannot prove suite-wide completion.

## 14. Release and Publication Boundary

Local implementation, tests, documentation, and commits do not equal publication.

Each repository requires separate evidence for:

- clean intended diff;
- full tests and build;
- version and changelog decision;
- checksum or artifact integrity;
- remote commit reachability;
- GitHub-rendered README and links;
- tag or release state when applicable.

No push, tag, release, package-index upload, deployment, or environment mutation is implied by this design selection.

## 15. Completion Criteria

This design is implemented only when all of the following are proven against current state:

1. A fresh Python 3.12+ environment can install Mothership and run all five stable command forms.
2. Clone-first use and every pre-existing public command remain compatible.
3. Protocol registry, bundled schemas, fixtures, and digests agree exactly.
4. The synthetic golden path passes, and every required negative control fails closed for the intended reason.
5. Public module facades expose the documented scope, approval, adapter, contract, and protocol APIs without duplicated implementations.
6. The root and Japanese READMEs provide a tested 60-second path and accurately describe the hub-and-spoke ecosystem.
7. Architecture, installation, composition, security, protocol, release, and changelog documents contain no contradictory responsibility or authority claims.
8. Mothership's full regression, package, build, clean-install, README-command, link, integrity, privacy, and boundary checks pass.
9. Agent Frontdoor, WGM, Router, and Secretary TUI each record and pass conformance for the frozen suite protocol without overwriting unrelated work.
10. GitHub state, release reachability, and rendered documentation are measured before any claim that the public rollout is complete.

Popularity cannot be guaranteed. The README and product surface must be built to a standard suitable for broad adoption, while every factual claim remains tied to inspectable evidence.
