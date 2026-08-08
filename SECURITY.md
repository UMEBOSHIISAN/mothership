# Security policy

## Supported version

Security fixes are evaluated for the latest public Mothership release candidate. Until 0.2.0 is actually published, the
repository state and its verification record are the only support reference; no release availability is implied.

## Report privately

Use a [GitHub Security Advisory](https://github.com/UMEBOSHIISAN/mothership/security/advisories/new) to report a
suspected vulnerability privately.

**Do not open a public issue** containing credentials, private paths, personal data, live exploit details, or anything
that could expose another user's environment.

Include only what is needed to reproduce the issue:

- affected commit or version;
- operating system and Python version;
- command or public API surface;
- sanitized input or a minimal fictional fixture;
- expected and actual closed behavior;
- whether the issue crosses confidentiality, integrity, authority, or execution boundaries.

Do not send real tokens, private repository contents, or unredacted machine configuration.

## Response boundary

A report is evidence for review, not permission to access another system, rotate credentials, publish details, or deploy
a fix. Maintainers will reproduce with sanitized local data, scope the impact, add a regression test, and coordinate
disclosure separately.

## Security model

Read [docs/security.md](docs/security.md) for defended surfaces, diagnostic loopback behavior, installation risk, and
residual limitations.
