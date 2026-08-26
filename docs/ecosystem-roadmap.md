# Mothership roadmap

This roadmap separates implemented current capability, preserved compatibility, candidates, and exclusions. It does
not promise dates, adoption, publication, deployment, or automatic integration.

## Implemented

- Exact bounded `FrozenAction` for the closed `github.merge_pr` operation profile.
- Canonical action SHA-256, core-derived display, and a per-issuance short TTL. Because the digest excludes expiry,
  fresh action IDs and exact live-issuance response correlation remain integration requirements.
- Structured caller-attested human decision tied to the exact action ID and digest; identity authentication remains an
  integration responsibility.
- Replay rejection and one-shot consumption in one trusted, non-rollbackable live ledger history. Successful event
  writes are file-fsynced; new ledger directory entries are not claimed crash-durable.
- Decision Card / Decision Approval review evidence with no authority or execution effect.
- Read-only default CLI for verification, diagnostics, protocol compatibility, and decision presentation.
- Preserved 0.2 protocol compatibility suite, schema hashes, fixtures, conformance evidence, and synthetic demo.
- Preserved legacy invocation-evidence, routing, safety, registry, and import compatibility surfaces.

## Candidates

- Cross-platform replication for declared Python and operating-system combinations.
- An independently authored or blinded request corpus for external evaluation.
- Artifact-paper materials, baselines, ablations, and third-party reproduction.
- Additional evidence and verification for the current closed authority profile without broadening it.

Candidates remain unshipped until separately approved, implemented, and verified. They do not imply a new action,
executor, protocol, or top-level product.

## Not current or planned

- autonomous or automatic approval;
- ambient or global authority;
- model or agent execution;
- local worker routing;
- automatic retry or fallback;
- credential management;
- generic or arbitrary executor selection;
- generic deployment, publishing, or repository mutation authority;
- automatic companion installation;
- background service, daemon, scheduler, hook manager, or autonomous action loop;
- inference that compatibility validation grants Action Authority.

Changing these exclusions requires a separate design and explicit human decision. They are not TODO items hidden behind
the current roadmap.
