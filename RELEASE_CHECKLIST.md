# Release Checklist

This checklist is for preparing a local package handoff. Completing it does
not publish, deploy, install, or otherwise distribute Mothership.

## Package contents

- [x] Confirm `VERSION`, `CHANGELOG.md`, `LICENSE`, and `README.md` describe
  the intended release.
- [x] Confirm `README.md` renders the Original Whale Mark from
  `assets/mothership-banner.png`.
- [x] Confirm example configuration contains no endpoints, access material, or
  machine-specific command paths.
- [x] Confirm the package contains only public source, tests, contracts,
  documentation, and approved assets.

## Safety review

- [x] Scan for credentials, tokens, private absolute paths, and host-specific
  configuration before handoff.
- [x] Review every scan finding; do not treat a clean pattern scan as a
  substitute for review.
- [x] Verify no package command installs software, accepts application credentials, changes settings, or performs
  consequential external mutations; review read-only GitHub observation and inherited system proxy behavior separately.

## Verification and integrity

- [x] Run `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v`.
- [x] Build exactly one wheel and one source distribution in a clean temporary
  source copy.
- [x] Inspect the wheel manifest, metadata, package resources, and runtime
  dependency set with `tests.test_distribution`.
- [x] Install the wheel without dependencies in a fresh environment and run
  the console-script and `python -m mothership` forms outside the repository.
- [x] Install the source tree in editable mode in a separate fresh environment
  and compare all read-only command bytes with the wheel installation.
- [x] Repeat the clone-first regression suite without installing Mothership.
- [x] Verify `mothership verify` passes from the installed wheel and that its
  packaged resource inventory is complete.
- [x] Generate `SHA256SUMS` after all package files are finalized.
- [x] Verify the manifest with `shasum -a 256 -c SHA256SUMS`.
- [x] Record the exact commands and results in the delivery report.

## Handoff

- [x] Provide the package directory and its `SHA256SUMS` manifest together.
- [x] State clearly that this is a local package only and requires an explicit
  separate decision for any publication, deployment, or installation.
