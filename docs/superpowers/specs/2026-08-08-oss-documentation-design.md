# Mothership OSS Documentation Design

## Goal

Make the public Mothership repository understandable and safely usable by a
new contributor without private context. The repository will present an
English-first README, a short Japanese introduction, practical setup and
architecture references, and clear visual aids.

## Audience and language

- The primary audience is OSS users evaluating or installing the project.
- The README and detailed reference material are written in English.
- A short Japanese entry point links Japanese-speaking users to a concise
  Japanese guide.

## Documentation structure

`README.md` becomes the product entry point. It contains:

1. Existing whale logo and a one-sentence project definition.
2. A Japanese link and a clear statement of the local, non-authorizing safety
   boundary.
3. Feature list and explicit non-goals.
4. A Mermaid architecture diagram showing the front door, contracts,
   orchestration helpers, safety policy, and local configuration.
5. Quick start: clone, choose Python 3.12+, run diagnostics and tests.
6. Safe configuration guidance, verification, update, removal, and links to
   the detailed guides.

`docs/architecture.md` describes the components, the data flow, and the
decision/authority boundary.

`docs/installation.md` provides requirements, install, configuration,
diagnostic, verification, updating, removal, and troubleshooting steps.

`docs/security.md` describes no-secret defaults, local configuration, and the
actions Mothership intentionally does not perform.

`docs/ja/README.md` is a short Japanese onboarding guide with the equivalent
safe quick-start route and links to the English detail.

## Visual design

- Keep `assets/mothership-logo.png` as the repository identity.
- Generate one original, dark-navy pixel-art illustration of a friendly
  whale-shaped mothership. It will be used as a README banner, not as a claim
  about system functionality.
- Use Mermaid diagrams for architecture so the visuals remain editable,
  accessible as source text, and render directly on GitHub.
- Provide descriptive alt text for each raster image.

## Accuracy and safety constraints

- Document only observed behavior: local helpers, staged contracts,
  diagnostics, and user-reviewed configuration.
- Never imply that Mothership installs hooks, edits settings, authorizes
  actions, invokes models, manages credentials, or deploys software.
- Configuration examples remain placeholders and contain no personal paths,
  commands, endpoints, or credentials.
- Commands must be copyable and limited to clone, inspect, diagnostic, and
  test operations.

## Verification

- Run the full test suite after documentation and asset changes.
- Confirm all documentation links resolve locally.
- Scan new files for credential-like values and private absolute paths.
- Review the rendered README and Mermaid syntax on GitHub after publication.

## Scope

This change adds documentation and original visual assets only. It does not
change runtime behavior, install hooks, or alter the core safety model.
