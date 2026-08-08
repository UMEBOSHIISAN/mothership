# Release Checklist

This checklist is for preparing a local package handoff. Completing it does
not publish, deploy, install, or otherwise distribute Mothership.

## Package contents

- [ ] Confirm `VERSION`, `CHANGELOG.md`, `LICENSE`, and `README.md` describe
  the intended release.
- [ ] Confirm `README.md` renders the packaged logo from
  `assets/mothership-logo.png`.
- [ ] Confirm example configuration contains no endpoints, access material, or
  machine-specific command paths.
- [ ] Confirm the package contains only public source, tests, contracts,
  documentation, and approved assets.

## Safety review

- [ ] Scan for credentials, tokens, private absolute paths, and host-specific
  configuration before handoff.
- [ ] Review every scan finding; do not treat a clean pattern scan as a
  substitute for review.
- [ ] Verify no package command installs software, authenticates, changes
  settings, or performs external actions.

## Verification and integrity

- [ ] Run `PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -v`.
- [ ] Build exactly one wheel and one source distribution in a clean temporary
  source copy.
- [ ] Inspect the wheel manifest, metadata, package resources, and runtime
  dependency set with `tests.test_distribution`.
- [ ] Install the wheel without dependencies in a fresh environment and run
  the console-script and `python -m mothership` forms outside the repository.
- [ ] Install the source tree in editable mode in a separate fresh environment
  and compare all read-only command bytes with the wheel installation.
- [ ] Repeat the clone-first regression suite without installing Mothership.
- [ ] Verify `mothership verify` passes from the installed wheel and that its
  packaged resource inventory is complete.
- [ ] Generate `SHA256SUMS` after all package files are finalized.
- [ ] Verify the manifest with `shasum -a 256 -c SHA256SUMS`.
- [ ] Record the exact commands and results in the delivery report.

## Handoff

- [ ] Provide the package directory and its `SHA256SUMS` manifest together.
- [ ] State clearly that this is a local package only and requires an explicit
  separate decision for any publication, deployment, or installation.
