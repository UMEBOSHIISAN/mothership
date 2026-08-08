# Security model

Mothership is designed to make the safe boundary visible rather than hide it behind automation.

## No shipped secrets

The repository contains no access tokens, credentials, endpoints, personal paths, or usable command arrays. Configuration examples are placeholders only. Before publishing a fork or a change, scan it for secrets and machine-specific data.

## Local configuration belongs to the operator

If you adapt `config/executors.example.json`, treat the result as local configuration owned and reviewed by you. Keep it out of public commits unless every value is safe to disclose. Supply credentials only through your own local environment and never paste them into issues, commits, or configuration examples.

## Non-authorizing by design

Mothership can validate data, create an advisory result, or report local adapter availability. It cannot grant approval, choose an executor, invoke a model, deploy software, or make an external request. A valid local result never substitutes for a human decision.

## No ambient mutation

The package does not install hooks, modify Codex or editor settings, write scheduler entries, or update a user's environment. Any integration beyond the repository requires an explicit, separately reviewed action by the user.

## Reporting a concern

Do not include secrets, private paths, or personal information in a public report. Provide the smallest reproducible example that demonstrates the behavior, with sensitive values removed.
