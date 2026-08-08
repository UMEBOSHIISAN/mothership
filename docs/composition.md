# Composition guide

Mothership can stand on its own or sit beside other focused tools. The
companion repositories are independent projects: install, configure, and
review each repository separately. This guide describes human-led adoption
choices, not package dependencies, automatic setup, runtime integrations,
shared credentials, or cross-repository authority.

## Mothership alone

Use Mothership alone when you want a portable, reviewable control plane for a
local AI coding environment. Start by reviewing its contracts, templates,
diagnostics, and tests; then make any local configuration choices yourself.

Mothership is installed, configured, and reviewed separately from every other
repository. It does not require a companion repository, install one, or make
configuration or execution choices on its behalf.

## Agent Frontdoor, then Mothership

[Agent Frontdoor](https://github.com/UMEBOSHIISAN/agent-frontdoor) can provide
a preflight task-card boundary before you use Mothership's portable contracts
and local review surface. A human can first inspect the task card, then decide
whether and how to use Mothership locally.

Agent Frontdoor and Mothership are installed, configured, and reviewed
separately. Their order in this recipe does not create a dependency, automatic
handoff, shared configuration, or authority transfer.

## Mothership, then Secretary TUI

After using Mothership to establish and review local control-plane boundaries,
you may use [Secretary TUI](https://github.com/UMEBOSHIISAN/secretary-tui) to
observe local operational state. Secretary TUI remains an observability tool;
it does not change Mothership configuration or grant execution authority.

Mothership and Secretary TUI are installed, configured, and reviewed
separately. The sequence is a human workflow, not an automatic connection,
data transfer, or shared credential arrangement.

## Optional Git Vibes and Toygarden

[Git Vibes](https://github.com/UMEBOSHIISAN/git-vibes) can add optional,
non-blocking human feedback around commits. [Toygarden](https://github.com/UMEBOSHIISAN/toygarden)
is an adjacent terminal-native creative toolkit for exploring agent-facing
visualization and composition ideas. Neither is a required control-plane gate.

Git Vibes, Toygarden, and Mothership are installed, configured, and reviewed
separately. Choosing either optional tool does not enable automatic setup,
execution, shared credentials, or authority across repositories.
