# Community request: show us a drift the records can prove

Mothership can improve when real failure shapes are reduced to safe, explicit
evidence. We are looking for cases where an AI-agent success claim differed
from the authority, action, result, verification, or persistence records around
it.

## What to share

Please create a minimal synthetic reproduction containing only the fields
needed to explain the mismatch:

- the human intent in neutral words;
- the bounded scope or action class;
- the approval relationship, using invented identifiers;
- the claimed execution/result;
- the verification or persistence evidence that exposed the difference;
- the verdict you expected and why.

Replace organization names, repository names, users, hosts, task text, hashes,
timestamps, and artifact names with neutral fixture values. Preserve the causal
shape, not the production content.

## Before posting

- remove secrets, tokens, cookies, credentials, private keys, and environment
  values;
- remove private paths, usernames, hostnames, internal URLs, and customer data;
- remove raw prompts, proprietary source code, production logs, and personal
  information;
- do not paste credentials even if they are expired, redacted-looking, or from
  a test account;
- run the reproduction in a new temporary directory and confirm it needs no
  network or private service.

If the case cannot be made synthetic without losing its meaning, do not post
it publicly. Use the private security reporting path for vulnerabilities; use
an internal incident process for sensitive operational evidence.

## Suggested issue body

```text
Observed claim:
Approved scope/action class:
Supplied execution evidence:
Supplied verification/persistence evidence:
Expected verdict:
Minimal synthetic reproduction:
Why this causal shape matters:
```

Mothership verifies supplied records. A community example is evidence about a
fixture, not proof of an unobserved production event and not a grant of
authority.
