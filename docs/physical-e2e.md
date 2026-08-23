# Physical E2E Verification Record

Physical GitHub merge E2E path validated through bounded Mothership authority.

- **Operation**: `github.merge_pr`
- **Control Plane**: Mothership Decision / Authority Core
- **Pipeline**: Human Semantic Intent → generic DecisionCandidate → Frontdoor & WGM protocols → canonical Decision Card → Human Decision Approval → exact FrozenAction → One-Shot Consume → Bounded Executor → Execution Receipt → Moon Verification Bridge
- **Invariant**: Exactly one PUT, zero retries, fail-closed preflight, zero token leakage.
