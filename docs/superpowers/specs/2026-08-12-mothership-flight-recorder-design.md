# Mothership Flight Recorder Design

**Date:** 2026-08-12
**Status:** HUMAN-APPROVED DESIGN
**Selected approach:** Position Mothership as the black box for AI agents: a human-governed control plane that records and verifies the complete work lifecycle without executing agents itself.
**Primary success metric:** Build toward 10,000 GitHub stars by becoming a useful, credible, interoperable evidence standard. The metric is aspirational and must never be presented as guaranteed adoption.
**Scope:** Public Mothership and its public companion protocols only. Private operations, credentials, deployment, schedulers, machine-specific configuration, and UMEBOSHI brand-identity assets are excluded.

## 1. Decision

Mothership's public face becomes:

> The black box for AI agents.
>
> Know what your agents were allowed to do—and prove what actually happened.

Its product category is a **human-governed agent control plane**. Its technical distinction is **Authority as Data**: intent, scope, approval, execution, evidence, verification, and persistence are explicit, linked records rather than assumptions hidden in prompts or logs.

This design evolves the existing installable integration hub. It does not turn Mothership into an agent runtime, replace the independently useful companion repositories, or weaken the current fail-closed boundary.

The previous phrase, “a portable, safety-first control plane for AI coding environments,” remains accurate technical detail. It is no longer the first sentence users must decode before understanding the product.

## 2. Why This Is the Selected Approach

Three product directions were considered:

1. **AI Agent Flight Recorder / black box — selected.** It gives a new user an immediate, concrete reason to install Mothership: determine what was requested, authorized, performed, verified, and durably preserved.
2. **Authority as Data standards suite.** This is the technical foundation and research narrative, but it is too abstract to be the primary product pitch.
3. **Complete AI Company OS.** This is the long-term vision, but exposing the whole operating system now would create an unbounded product surface and obscure the first useful action.

The selected positioning preserves the depth of the operating system while presenting one sharp entry point. Mothership can reveal more of the OS over time only through verified, independently useful public artifacts.

## 3. Product Promise and Boundaries

Mothership answers five questions about an agent run:

1. What was requested?
2. What scope and action class were allowed?
3. What was actually executed?
4. What evidence supports the claimed result?
5. Was the result verified and durably preserved?

Mothership owns:

- the composition protocol and version registry;
- a common flight-event envelope;
- deterministic import, validation, replay, and reporting;
- run-level completeness and drift evaluation;
- lineage between intent, authority, execution, evidence, and persistence;
- human-readable incident and closeout reports;
- public mappings to relevant security and interoperability frameworks;
- the synthetic safe-run and scope-drift demonstrations.

Mothership does not own:

- model or agent invocation;
- permission grants or authority promotion;
- credential, environment, secret, or prompt-body collection;
- automatic retry, repair, fallback, or continuation;
- deployment, scheduling, hooks, daemons, or infrastructure mutation;
- enforcement inside third-party runtimes;
- claims of certification by OWASP, NIST, vendors, or model providers.

The product records and verifies authority. It does not create authority.

## 4. The Complete Work Lifecycle

The canonical lifecycle is:

```text
Intent
  -> Scope
  -> Decision
  -> Approval binding
  -> Execution receipt
  -> Result evidence
  -> Verification
  -> Persistence proof
  -> Reusable asset (optional)
```

The minimum complete run ends at persistence proof. Reusable asset creation is an optional post-completion step and must never be inferred from the presence of a result.

Observation is not the final lifecycle stage. An observation is a projection over any stage or over the whole run. This corrects the misleading implication in the v0.2 synthetic chain that an `observation-snapshot` necessarily follows and completes execution.

## 5. Relationship to Existing Public Components

Mothership composes protocols without taking semantic ownership away from their repositories.

| Lifecycle responsibility | Existing owner | Mothership responsibility |
| --- | --- | --- |
| Intent and bounded scope | Agent Frontdoor | Reference and validate the task artifact |
| Evidence, claim, approval, receipt, verification semantics | Workflow Governance Model | Reuse the frozen semantics; do not define competing concepts |
| Approval-bound selection and manifest | Mothership Router | Verify the binding and link it into the run |
| Worker and team events | Agent Team Runtime | Import compatible events without launching workers |
| Append-only evidence | Evidence Spine Core | Reference and verify evidence records |
| Cross-run and artifact relationships | Run Lineage Core | Project lineage into replay and reports |
| Source freshness | Source Health Core | Carry explicit freshness evidence where relevant |
| Knowledge maturation | Knowledge Lifecycle Kit | Reference optional post-completion assets |
| Composition, run verdict, replay, presentation | Mothership | Own the flight bundle and whole-run evaluation |

The v0.2 protocol chain remains supported:

```text
frontdoor-task
  -> governance-handoff
  -> router-manifest
  -> observation-snapshot
```

In v0.3, it becomes one supported projection inside a larger flight bundle rather than the definition of a completed real-world run.

## 6. Flight Bundle

### 6.1 Bundle Shape

A flight bundle is a local, portable directory:

```text
flight-001/
  flight.json
  events.jsonl
  artifacts/
  report.md            # optional derived output
```

`flight.json` is the bundle index. `events.jsonl` is an ordered transport log, not proof that real-world events occurred in that order. `artifacts/` may contain explicitly imported, content-addressed public or synthetic evidence. A report is always derived, can be regenerated, and is excluded from bundle integrity calculations.

The bundle must be valid without embedding raw prompts, model responses, credentials, or private absolute paths. External artifacts may be represented by identifiers and SHA-256 digests without copying their content into the bundle.

### 6.2 Flight Index

The index records at minimum:

- bundle schema version;
- stable run identifier;
- creation time and producer identity class;
- ordered event identifiers;
- required lifecycle stages for this run profile;
- protocol registry snapshot identifier;
- bundle content digest;
- declared privacy profile;
- derived verdict, or an explicit marker that no verdict has been computed.

The index cannot grant authority. A declared verdict is untrusted until independently recomputed.

The bundle content digest is computed over canonical `flight.json` content with the digest and derived verdict fields omitted, plus the exact `events.jsonl` bytes and sorted content-addressed artifact entries. This avoids a self-referential digest and keeps regenerated reports outside the trusted input set.

### 6.3 Event Envelope

Every event uses a common envelope with:

- event schema version;
- event identifier and run identifier;
- event type and lifecycle stage;
- observed or produced timestamp;
- producer identity class and optional tool identifier;
- predecessor event identifiers;
- subject protocol kind, version, location, and content digest;
- scope digest and action class when applicable;
- authority effect and execution effect flags;
- outcome status;
- redaction metadata;
- optional extension namespace owned by the source protocol.

The envelope carries references and integrity metadata. Domain-specific meaning remains in the referenced owner protocol.

### 6.4 Privacy Profiles

The initial release supports two explicit profiles:

- `metadata-only` — default; stores identifiers, hashes, types, timestamps, scope/action classifications, and verification results.
- `portable-evidence` — includes only artifacts explicitly selected for bundling after secret and path checks.

There is no automatic “capture everything” profile. Importers must reject or require explicit redaction for secret-like keys, credentials, environment dumps, raw prompt bodies, private paths, and unsupported binary content.

## 7. Command-Line Experience

The intended v0.3 surface is:

```sh
mothership import generic events.jsonl --out ./flight-001
mothership verify run ./flight-001
mothership replay ./flight-001
mothership report ./flight-001 --format markdown
```

An optional explicit writer may be added only if it preserves the same boundary:

```sh
mothership record event.json --ledger ./mothership/events.jsonl
```

Command behavior:

- `import` reads one explicitly supplied source and writes only to the explicit output directory.
- `verify run` is read-only and recomputes the run verdict from bundle contents.
- `replay` is read-only and prints the causal lifecycle; it never re-executes an action.
- `report` prints to standard output by default and writes only when an explicit output path is supplied.
- `record`, if implemented, appends one validated event to one explicit ledger; it does not discover processes or watch directories.

The stable v0.2 commands remain available. Migration and deprecation require a separate versioned decision.

## 8. Verdict and Failure Semantics

Mothership emits exactly one run verdict:

| Verdict | Meaning |
| --- | --- |
| `COMPLETE` | Every required stage is present, valid, linked, within authority, evidence-backed, verified, and durably preserved |
| `INCOMPLETE` | Required evidence or a required lifecycle stage is absent, so completion cannot be established |
| `DRIFTED` | Valid records establish that execution exceeded or contradicted declared scope, approval, action class, result, or persistence |
| `INVALID` | The bundle cannot be trusted because its syntax, schema, identity, digest, or reference graph is malformed or contradictory |

Aggregate precedence is:

```text
INVALID > DRIFTED > INCOMPLETE > COMPLETE
```

Validation order is deterministic:

1. safe file access, decoding, schema, and digest integrity;
2. run identity, event identity, and reference-graph integrity;
3. scope, action class, and approval binding;
4. execution receipt, result claim, and supporting evidence;
5. verification and persistence proof.

Rules:

- Missing required material produces `INCOMPLETE`.
- Present but malformed, substituted, hash-mismatched, or internally contradictory material produces `INVALID`.
- Valid evidence of unauthorized action, false success, or persistence mismatch produces `DRIFTED`.
- A recommendation, valid manifest, or worker success label never implies approval, verification, or completion.
- Unknown versions, fields where strict closure applies, action classes, event types, and verdicts fail closed.
- Validation never repairs input, retries a failed operation, fetches missing material, or searches ambient directories.
- Errors identify the failed rule and safe relative reference without echoing secret values or private absolute paths.

Stable process exits are reserved as follows:

| Exit | Meaning |
| --- | --- |
| `0` | `COMPLETE` |
| `20` | `INCOMPLETE` |
| `21` | `DRIFTED` |
| `22` | `INVALID` |
| `64` | Invalid command usage |
| `70` | Internal Mothership failure |

Machine-readable JSON output contains the verdict, failed rule identifiers, event references, and remediation-neutral facts. It must not issue commands or propose unauthorized repair.

## 9. Demonstrations

The top-level README presents two deterministic, credential-free demonstrations.

### 9.1 Safe Run

A synthetic task supplies all required records from request through persistence. The result is:

```text
COMPLETE — 8/8 required lifecycle stages verified
```

The demo proves that Mothership can validate the supplied evidence graph. It does not prove that a real model, agent, filesystem, or remote service was used.

### 9.2 Scope Drift

A synthetic run carries read-only approval but contains a valid file-write execution receipt. The result is:

```text
DRIFTED — observed file_write exceeds approved read_only scope
```

Mothership reports the mismatch and stops. It does not inherit authority from the executor, modify the record, undo the action, or suggest that a subsequent success makes the action acceptable.

## 10. Adapter Strategy

Adapters translate explicit source records into the common flight envelope. They are importers, not runtime integrations.

Priority order:

1. Generic JSONL
2. OpenAI Agents SDK
3. LangGraph
4. Claude Code and Codex CLI
5. AutoGen

The generic importer is the only adapter in the first vertical slice. Later adapters require evidence of stable upstream event surfaces and must be developed independently so one vendor change cannot destabilize the core bundle verifier.

By default, adapters retain only:

- stable or locally derived identifiers;
- scope and action class;
- event and artifact digests;
- authority and execution flags;
- result and verification metadata;
- timestamps needed for causal reconstruction.

Adapters do not retain raw prompts, completions, secrets, tokens, environment dumps, or unrelated telemetry by default.

## 11. Verification Strategy

### 11.1 Product Reliability Gate

Before public repositioning, ordinary installation, demo, and test workflows must not invalidate each other. In particular, Python bytecode generation and isolated build-backend availability must not make a clean user workflow appear broken.

The supported Python and operating-system matrix must be explicit and measured. The initial target is Python 3.12–3.14 on Linux and macOS, subject to the package metadata and CI environments actually verified during implementation.

### 11.2 Golden and Adversarial Fixtures

Required deterministic fixtures include:

- one complete safe run;
- one scope-drift run;
- missing approval;
- stale or substituted approval;
- action-class escalation;
- result success without evidence;
- evidence digest substitution;
- missing verification;
- claimed persistence without a matching durable artifact;
- remote/persistence revision mismatch;
- duplicate event identifier;
- broken predecessor reference;
- unknown schema or event version;
- secret-like or private-path material rejected by the selected privacy profile.

Tests mutate one invariant at a time and assert the exact verdict, rule identifier, and safe error surface.

### 11.3 Boundary Tests

The v0.3 CLI must prove:

- no model invocation;
- no external network access;
- no credential or environment-file access;
- no subprocess execution by import, verify, replay, or report;
- no ambient repository or home-directory discovery;
- no mutation outside an explicit output target;
- no automatic retry or repair;
- deterministic output for identical inputs.

Major public security claims require an external reproducer or independently maintained corpus before being described as established beyond the bundled fixtures.

OWASP and NIST mappings are documentation crosswalks, not endorsements or certification claims.

## 12. README and Public Story

The root README narrative becomes:

1. existing whale banner and concise product identity;
2. “The black box for AI agents” headline and proof-oriented subheading;
3. a 60-second safe-run / scope-drift demonstration;
4. the before / during / after lifecycle;
5. exact guarantees and non-goals;
6. commands for importing, verifying, replaying, and reporting;
7. the Authority as Data explanation;
8. protocol owners and independently adoptable companion projects;
9. framework adapters and compatibility status;
10. threat model, research evidence, contributing, and roadmap.

The existing “fourteen ways in” constellation moves below the primary product story. The first architecture visual must show the work lifecycle, because the user needs to understand the result before exploring the ecosystem.

Each companion README may point toward Mothership as the whole-run verifier. It must continue to state that the companion works independently and that Mothership does not install, invoke, or authorize it.

## 13. First Vertical Slice

The first implementation specification is deliberately narrow:

- preserve the v0.2 registry, fixtures, commands, and public compatibility surface;
- add the v0.3 flight index and event-envelope schemas;
- add safe-run and scope-drift bundles;
- implement the Generic JSONL importer;
- implement `verify run`, `replay`, and Markdown `report`;
- add deterministic verdicts, rule identifiers, and stable exit codes;
- add the adversarial fixture corpus needed for those commands;
- eliminate the known clean-user verification friction before changing the public headline;
- rebuild the English README around the two demonstrations;
- update Japanese onboarding with semantic parity.

Explicitly deferred:

- vendor and framework adapters;
- background capture or runtime instrumentation;
- dashboards, hosted services, or remote synchronization;
- enforcement plugins;
- signatures requiring key management;
- organization policy engines;
- benchmarking claims based only on synthetic fixtures;
- release, deployment, or CI changes without their separate required approvals.

## 14. Adoption Gates Toward 10,000 Stars

GitHub stars measure attention, not safety or product correctness. They are a growth objective, while completion remains evidence-based.

### Gate A — 0 to 100

- installation works from a clean supported environment;
- the value is understandable within 60 seconds;
- safe-run and scope-drift results are visually and technically credible;
- README claims trace to commands, fixtures, and tests;
- first-time contributors can reproduce the result without private infrastructure.

### Gate B — 100 to 1,000

- at least two high-demand framework adapters are stable;
- external users publish independently reproducible bundles or incident fixtures;
- integration guides and issue templates reduce adoption friction;
- maintainers publish compatibility and breaking-change policy;
- reports are useful in real code review, incident review, or compliance preparation.

### Gate C — 1,000 to 10,000

- the flight bundle becomes a practical interchange artifact across multiple runtimes;
- independent projects emit or consume the format;
- a public adversarial corpus and benchmark are maintained transparently;
- framework mappings and security crosswalks are evidence-backed and current;
- external maintainers and integrations reduce dependence on one author;
- the community recognizes Mothership as a neutral proof layer rather than another agent framework.

No gate is achieved by a star count alone. Product reliability, external reproduction, and protocol adoption are the evidence.

## 15. Success Criteria for the First Slice

The first vertical slice is complete only when:

- the v0.2 behavior remains compatible and its tests pass;
- the safe bundle evaluates to `COMPLETE` for the documented reasons;
- the drift bundle evaluates to `DRIFTED` for the documented reason;
- every required negative fixture produces its exact expected verdict and rule identifier;
- replay reconstructs causal links without executing anything;
- report output is deterministic and contains no secret or private-path leakage;
- a clean supported installation can run the quickstart and test workflow without bytecode/build-backend interference;
- security and non-goal claims are backed by tests or clearly labeled limitations;
- English and Japanese onboarding agree on the product boundary;
- no release, push, deployment, credential, scheduler, or CI mutation has occurred without its own authority.

## 16. Decision Record

- 2026-08-12: The human selected the Flight Recorder approach as the strongest path toward a serious 10,000-star OSS goal.
- 2026-08-12: The human approved the public face, two-demo onboarding, component map, strict verdict model, graph-based flight bundle, and vertical-slice-first delivery strategy.
- 2026-08-12: The design retained the existing safety boundary and independent companion repositories instead of expanding Mothership into an autonomous runtime or public monorepo.
