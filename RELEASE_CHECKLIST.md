# Release Checklist

The checked items below record an earlier Core-only local handoff. They are not
evidence that the current three-package source candidate has been published.

## Core 0.5.0.dev0 + companion 0.3.0.dev0 + adapters 0.1.0.dev0

Use this section for a prospective GitHub prerelease. A local build or a green
source CI run alone is not a published distribution. Keep the source revision,
artifact hashes, installed validation, and GitHub Release record together.

- [ ] Freeze one reviewed source revision and check that the Core, companion,
  and adapters versions and exact dependencies agree.
- [ ] Confirm the changelog, Japanese and English READMEs, installation guide,
  and compatibility limits describe that revision. Do not claim stable, medical,
  normal-host, human-acceptance, or all-tool coverage from the isolated canary.
- [ ] Build three wheels and three source distributions from that exact clean
  revision. Inspect package contents and metadata. The Python wheels do not
  contain the source-tree Node wrappers or Dots skill.
- [ ] Inspect every artifact for secrets and private host material; review
  findings instead of treating a pattern scan as proof of safety.
- [ ] Install the three wheels together into a fresh Python 3.12+ environment
  without fetching runtime dependencies. Run `pip check`, `mothership verify`,
  both installed evidence CLI forms on the six retained synthetic cases, and
  the distribution tests relevant to the release tree.
- [ ] Build wheels back from all three source distributions and compare their
  payloads with the direct wheels. Record any intentional differences.
- [ ] Generate an artifact `SHA256SUMS` only after final bytes are fixed and
  verify all six files. Keep it separate from the tracked source-tree manifest.
- [ ] Confirm the required CI and review on the exact final source revision.
- [ ] Obtain target-specific authority before creating the tag or GitHub
  Release. A source-build approval does not authorize publication.
- [ ] After publication, read back the tag target, release assets, and hashes;
  install the published bytes in a fresh environment. Do not replay a live
  GitHub merge to validate packaging.

## Historical Core-only local handoff

This historical checklist prepared a local package handoff. Completing it did
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
