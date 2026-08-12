# Mothership publication checklist

Local draft — no remote mutation is authorized or implied by this document.
Run each section only after separate target-specific approval. Record measured
output beside the item; a checked intention is not evidence.

## 1. Branch publication

- [ ] Confirm the exact repository, local branch, and source HEAD.
- [ ] Verify the commit exists locally with `git cat-file -e <sha>^{commit}`.
- [ ] After an approved push, fetch the named remote branch.
- [ ] Verify the commit reached origin with `git merge-base --is-ancestor <sha> origin/<branch>`.
- [ ] Record remote repository, branch, full SHA, fetch time, and verifier.

Do not combine eleven pushes into one approval. Agent Frontdoor has no measured
upstream in the source checkout; remote parity must not be inferred.

## 2. Review and merge

- [ ] Open or update a PR only under separate approval for that repository.
- [ ] Re-run its recorded native suite on the exact proposed commit.
- [ ] Inspect the rendered README at desktop and narrow widths.
- [ ] Confirm image alt text, local asset resolution, and the single Mothership
      star destination.
- [ ] After an approved merge, fetch the default branch and measure that the
      result commit is reachable.

## 3. Repository metadata

Apply one entry at a time from
[`repository-metadata.json`](repository-metadata.json), whose status must remain
`draft-not-applied` until measured otherwise.

- [ ] Compare the current repository description with the draft.
- [ ] Apply the repository description only under target-specific approval.
- [ ] Compare current topics; apply the exact deduplicated topic set only under
      target-specific approval.
- [ ] Read the repository back through the GitHub API and record exact returned
      description and topics.
- [ ] Keep homepage empty unless a durable public page is separately measured.

## 4. Social previews

Paths in `repository-metadata.json` resolve from the Mothership rollout commit;
they are upload sources, not files that must be added to a companion repository.

- [ ] Render the declared local social preview and verify dimensions/contrast.
- [ ] Confirm atmospheric art is not described as behavioral evidence.
- [ ] Upload a social preview only under repository-specific approval.
- [ ] Open the public repository card in a fresh session and visually verify the
      remote image, crop, and absence of stale cache artifacts.

## 5. Release and tag

- [ ] Select an exact version and tag in a separate release decision.
- [ ] Re-run the full Mothership suite from the exact release candidate.
- [ ] Verify tag signature or annotated-tag bytes as required by project policy.
- [ ] After an approved push/release, fetch tags and measure release reachability
      from the public default branch.
- [ ] Confirm release notes still say only what the published bytes prove.

## 6. Announcements

- [ ] Choose the reviewed English or Japanese copy and the intended account.
- [ ] Re-check every command, link, image, limitation, and authority disclaimer.
- [ ] Post only under account- and message-specific approval.
- [ ] Read the public post back and record its durable URL and visible media.

## 7. Outcome measurement

- [ ] Record the pre-publication star count and timestamp from GitHub.
- [ ] Record later star count observations with the same source and timezone.
- [ ] Do not attribute a star change to one post without campaign evidence.
- [ ] GitHub traffic remains UNKNOWN unless an authorized account exposes a
      measured traffic view or API response.
- [ ] Conversion rate remains UNKNOWN without both attributable traffic and a
      defined observation window.

## Stop conditions

Stop the affected item on a mismatched SHA, failing test, unexpected remote
state, stale rendered asset, missing approval, unavailable account authority,
or any secret/private-path finding. Do not retry a mutation invisibly and do
not mark a local commit as published.
