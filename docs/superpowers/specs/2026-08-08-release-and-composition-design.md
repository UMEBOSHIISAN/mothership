# Mothership release and composition design

## Goal

Ship Mothership `v0.1.1` as a reviewable, portable AI coding control plane
with clear, honest guidance for standalone use and composition with the other
UMEBOSHIISAN public repositories.

## Scope

1. Add a composition guide that explains four independently adoptable paths:
   Mothership alone; Agent Frontdoor with Mothership; Mothership with Secretary
   TUI; and optional Git Vibes or Toygarden use.
2. Link that guide from the English and Japanese entry points.
3. Describe the future Workflow Governance Model as a roadmap item only. It is
   not released, installed, or claimed as an existing integration.
4. Correct release metadata and checksum generation for `v0.1.1`.
5. Verify a clean checkout, tag the actual release commit, and create a GitHub
   Release.

## Composition boundary

The public repositories remain independent. The guide may describe a human-led
sequence (for example, validate a task at Agent Frontdoor, maintain portable
boundaries in Mothership, then observe local state with Secretary TUI), but it
must not claim package dependencies, automatic setup, runtime data transfer,
shared credentials, or cross-repository authority.

Git Vibes and Toygarden are optional adjacent tools, not gates in the control
plane. The future Workflow Governance Model is a clean-room extraction target
from the private governance OS and must not expose private paths, hosts,
services, credentials, business data, or production automation.

## Release contents

- `VERSION` changes from `0.1.0` to `0.1.1`.
- `CHANGELOG.md` records documentation, composition guidance, and reproducible
  integrity verification without claiming new runtime behavior.
- `SHA256SUMS` contains only tracked release files; it must exclude `.git` and
  the checksum file itself so a normal clone can verify it.
- The release tag `v0.1.1` targets the pushed `main` commit and the GitHub
  Release attaches `SHA256SUMS`.

## Verification

Run from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3 -m unittest discover -s tests -v
shasum -a 256 -c SHA256SUMS
```

Also check Markdown links, `git diff --check`, and scan release files for
private absolute paths, tokens, and private-key markers.

## Non-goals

- No automatic environment copying, tool installation, authentication, hook
  installation, model execution, or external action.
- No publication of the private governance OS or its operational artifacts.
- No claim that companion repositories are a bundled product.
