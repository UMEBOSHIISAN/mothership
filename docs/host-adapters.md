# Host adapter guide

This guide is a practical map of the eight bounded routes in the
[integration catalog](integrations.md). Execution routes carry one exact
`github.merge_pr` action through a retained review boundary. Read-only routes
inspect detached evidence without restoring an action or granting authority;
the separately named `readback` command may perform one bounded public
observation. A host supplies
its own identity, context, credentials, transport, and effect decision. The
examples below use synthetic transport and caller-provided context; they do not
use API keys, account login, or a live GitHub endpoint. The explicit `readback`
route is documented separately below.

## Install the source candidate in one checkout

### Try the current candidate

For the reader through PR #59, use the unreleased source baseline
`fd8d4f0cbb80d3f87cd97ffd50f5e83468c94646`. It includes the six retained inputs,
legacy/v1 saved-result reading, and the optional expected-action digest check.
It also includes readback/inspect-sidecar, explicit JavaScript callback modes,
Python `SessionError.diagnostic`, and opt-in direct Node diagnostic forwarding.
This is a fixed snapshot, not a promise to include later changes or a published
release. Review the source and record the exact revision. Start in a new directory:

```sh
git clone https://github.com/UMEBOSHIISAN/mothership.git mothership-candidate
cd mothership-candidate
git fetch origin fd8d4f0cbb80d3f87cd97ffd50f5e83468c94646
git rev-parse --verify FETCH_HEAD
git checkout --detach fd8d4f0cbb80d3f87cd97ffd50f5e83468c94646
git rev-parse --verify HEAD

python3 -m venv .build-venv
.build-venv/bin/python -m pip install 'build>=1.2' 'setuptools>=77'
.build-venv/bin/python -m build --wheel --no-isolation --outdir wheels .
.build-venv/bin/python -m build --wheel --no-isolation --outdir wheels packages/mothership-github
.build-venv/bin/python -m build --wheel --no-isolation --outdir wheels packages/mothership-adapters

python3 -m venv .venv
.venv/bin/python -m pip install --no-index --no-deps \
  wheels/mothership_control_plane-0.5.0.dev0-py3-none-any.whl \
  wheels/mothership_github-0.3.0.dev0-py3-none-any.whl \
  wheels/mothership_adapters-0.1.0.dev0-py3-none-any.whl
.venv/bin/python -m pip check
.venv/bin/mothership-evidence inspect-result --help
```

Check that both printed revisions equal the selected full SHA. This recipe does
not claim that a package release or live host has been qualified. Python 3.12 or
later is required; all three wheels must come from this same checkout. Build-tool
installation may use the network; the local wheel install fetches no dependencies,
and result inspection is offline. Use the explicit `.venv/bin/` paths to avoid a
different installed reader. No Node or optional SDK extras are needed for reading.

### Reproduce the PR #56 reader

Keep `f9ef944bf54cb413824066f968010c0aaedc47ff` for the original legacy reader
walkthrough and the frozen six-case recipient exercise. This older runtime has
neither v1 saved-result binding nor the expected-digest option. The case data and
guides were added later and are supplied separately for that exercise. Start in
a separate new directory:

```sh
git clone https://github.com/UMEBOSHIISAN/mothership.git mothership-legacy-reader
cd mothership-legacy-reader
git fetch origin f9ef944bf54cb413824066f968010c0aaedc47ff
git rev-parse --verify FETCH_HEAD
git checkout --detach f9ef944bf54cb413824066f968010c0aaedc47ff
git rev-parse --verify HEAD

python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e . -e packages/mothership-github -e packages/mothership-adapters
```

Check both revisions against this historical SHA. Preserve its original editable
installation and legacy input meaning; do not convert inputs to claim v1 support.

### Reproduce the PR #45 runtime

To reproduce the historical readback/inspect-sidecar runtime reviewed for
[PR #45](https://github.com/UMEBOSHIISAN/mothership/pull/45), keep its original pin
`91f474ed9ba96f5c00925d44f3dd84739d41cdc7`. It excludes the later callback-mode
change and Session diagnostics. Use the documentation at that revision when
reproducing historical behavior; do not apply later API examples to it.
Start in a separate new directory:

```sh
git clone https://github.com/UMEBOSHIISAN/mothership.git mothership-readback
cd mothership-readback
git fetch origin 91f474ed9ba96f5c00925d44f3dd84739d41cdc7
git rev-parse --verify FETCH_HEAD
git checkout --detach 91f474ed9ba96f5c00925d44f3dd84739d41cdc7
git rev-parse --verify HEAD
```

Check that both printed revisions equal the historical full SHA, then run the
historical venv and editable three-package commands from the PR #56 section in
this historical checkout.
Keep historical test evidence separate from current-candidate evidence.

For source development, the three editable installs must use the same checkout.
Optional SDK extras are opt-in; select only the extras required by the routes you
use. The following additional command selects all three SDK extras in an activated
development venv:

```sh
python -m pip install -e 'packages/mothership-adapters[agents,langgraph,mcp]'
```

These extras pin `openai-agents==0.23.1`, `langgraph==1.2.12`, and
`mcp==2.3.0`. Record the `FETCH_HEAD` and detached `HEAD` values alongside the
test evidence; do not reconstruct a live session from an exported JSON request.

## Saved reference results

The reference consumer's `--verify-result --save-result` saves finite JSONL,
not a `host-evidence-bundle.v0`. The offline `inspect-result` command reads that
existing file directly. It does not manufacture a portable review request,
approval, consume event or Receipt to make it fit `inspect`.

### Read files someone handed you

The [recipient guide with six retained synthetic inputs](../examples/saved-results/README.en.md)
([日本語](../examples/saved-results/README.md)) starts from the received files;
it does not require running the producer. It pins the three-package reader to
`f9ef944bf54cb413824066f968010c0aaedc47ff` (PR #56), which contains
`inspect-result`. The six case files are later data-only additions, held
separately from that runtime pin; they are not claimed to be inside its wheels.
Follow the guide's explicit venv path so another installed version is not used.

Give recipients only the inputs and guides initially. Keep the separate answer
key until responses are recorded. Record actual time, questions, mistaken
completion claims and next records selected; an AI response does not supply
human acceptance evidence. All six inputs are synthetic material, not the
history of a real PR, and no live effect or human acceptance is implied.

### Reader source candidate from one checkout

For legacy/v1 reading and the expected-digest option, use the
[fixed current candidate](#try-the-current-candidate) above. For the original
legacy walkthrough, keep the separate PR #56 recipe. Use the same checkout for
`mothership_adapters/saved_result.py` and `examples/github_merge_reference.py`,
and `examples/reference_result_handoff.py`. V1 is not included in the PR #56
pin or the published v0.4.2 / v0.4.3.dev0 distributions. A producer and reader
from that historical pin reproduce the legacy walkthrough, not v1 binding.
The historical PR #55 pin `6082bf8` and PR #49 pin `bd6a2e8` do not include
the reader. Record the selected exact source commit with
`git rev-parse HEAD` before installing. For an uncommitted local candidate,
retain its baseline plus the reviewed patch/file manifest as well. Do not label
an ancestor pin as containing this reader or mix files from different revisions.

After the current three-wheel installation above, run from its source root:

```sh
.venv/bin/mothership-evidence inspect-result --help
.venv/bin/python -m examples.reference_result_handoff > synthetic-result.jsonl
.venv/bin/mothership-evidence inspect-result --human < synthetic-result.jsonl
```

Installation may resolve build tooling; the example and reader are offline.
The example runs the **real reference consumer and saver** with synthetic
transport, readback and fixture approval in temporary ledgers. It emits the
saved JSONL on stdout and a synthetic-only notice on stderr. It neither contacts
GitHub nor authenticates a human. The synthetic executor reports success while
the supplied readback reports an unmerged PR: expect `receipt: SUCCESS` and
`verification: UNKNOWN`, not a completed-operation claim. Keep stdout/stderr
separate. Inspecting the resulting file does not create or consume authority.
For a real file already saved by the consumer, replace only the redirected
input with that explicitly selected `result.jsonl`; do not rerun an operation
to create evidence for this reader.

For inspection outside the checkout, use the absolute path to this installed
`.venv/bin/mothership-evidence` and redirect an explicitly selected input. The
producer example remains source-only; the installed reader does not need the
source tree or `PYTHONPATH`. The companion's
[distribution regression](../packages/mothership-github/README.md#installed-wheel-verification)
checks this boundary, including legacy inputs, v1 and the digest guard. These
additional regression tests belong to this documentation/test update; the
`fd8d4f0` runtime pin does not contain them. Keep current-tree test results
separate from verification of that exact runtime pin.

The command accepts an empty file or a complete ordered prefix of at most
three saved events: `frozen_action`, `execution_result`, `verification_result`.
Every nonempty input line must be a complete LF-terminated JSON object.
Whole-input size, JSON depth/node/string bounds, duplicates, unknown fields,
reordered events and inconsistent action/hash/record links are checked before
any operation summary. Torn/invalid input returns exit `2` with no summary;
do not silently drop its tail. Output failure also returns `2`; discard partial
output. Exit `0` means readable valid records, including UNKNOWN, not successful
execution. JSON output without `--human` exposes the same non-authorizing view.

| Supplied records | Meaning and next check |
| --- | --- |
| Empty or frozen action only | Operation identity may be absent; outcome unknown. These records do not identify cancellation or prove no effect. Check explicitly retained source records. |
| Execution summary only after action | Consumer-reported status; no bound Receipt/independent confirmation supplied. Check existing authority and attempt records. |
| Receipt, no Verification | Executor report only; inspect an existing independent Verification if available. |
| Receipt plus bound Verification/sidecar | Recorded independent observation, its status/reason/time and structural hash binding; not authenticated origin, causation or current external truth. Receipt/Verification statuses may differ. |
| Unavailable Receipt/finish | Leave absent records absent; inspect existing authority/attempt records. No Receipt is constructed. |
| Corrupt or mixed action/hash records | Reject without an operation summary. No repair or automatic external action. |

This format never supplies the original review request, full approval or consume
rows. Legacy execution summaries lack an action/run identifier and timestamp:
sequence alone cannot detect a same-shaped row replaced from another run.
V1 checks claimed action identity as described below; neither format treats a
summary without a Receipt as bound completion.
It validates existing pair/Receipt/action and Verification/sidecar hashes when
provided, but mutually consistent falsified records cannot be authenticated.
It opens no input paths, discovers no records, and changes no input or ledger.
Bundled schemas are still read by the existing validators. It performs no
network, execution, consume, retry or observation, and does not prove freshness
or successful process exit. The existing bundle `inspect`/MCP and explicit
network-capable `readback` contracts are unchanged.

### Saved-result format compatibility

| Input producer | Reader | Interpretation |
| --- | --- | --- |
| Old consumer / existing six retained cases | Updated reader | Legacy positional-only execution summary; existing meaning unchanged. |
| Updated consumer with `--save-result` | Reader from the same updated checkout | V1 action ID/digest association, structural only. |
| Updated consumer with `--save-result` | PR #56 `f9ef944` reader or another legacy-only reader | Rejected for unsupported fields; do not strip fields to force acceptance. |
| Updated consumer without `--save-result` | Existing terminal consumer | Original unversioned terminal event shapes; no result file is produced. |

V1 adds `saved_result_schema: mothership.reference-result.v1` to every saved row.
The first `frozen_action` has the existing action/digest/expiry. Later
`execution_result` and `verification_result` rows require top-level `action_id`
and `action_sha256` matching that first action, including exception and
unavailable reports. No executor-supplied identity overrides the retained action.
Fields are closed per event and version. Unknown versions, missing or partial
identity, mixed old/new rows and mismatches are rejected before a summary. A
new-format validation failure is never reinterpreted as legacy.

An empty file remains unversioned missing evidence. A complete one-, two- or
three-row prefix is readable in its selected format; an action-only prefix has
no execution linkage. A matched execution summary without a Receipt remains
UNKNOWN. JSON/human output reports structural matching separately from completion
and retains false authority, source-authentication and external-verification flags.

IDs/digests do not authenticate origin or prove freshness, successful execution
or causation. Coherent forgery, substitution within the same action, and complete
rewriting into valid legacy input are not detected by this association check.
Do not convert historical files or rebuild missing records. The original six
cases, their guides and held human-acceptance packet remain unchanged.

### Check the expected operation

Internal consistency alone does not tell the recipient which task they intended
to inspect: another complete, internally valid result can describe another
action. In this updated source checkout, `inspect-result` optionally compares
the validated action against a digest the recipient **already retained from the
original task or review**, separately from the inspected file. The existing
canonical action digest covers the action ID, exact execution parameters and
derived display, so no second ID option or new saved format is needed.

With `expected_action_sha256` already set to that retained value:

```sh
mothership-evidence inspect-result --human \
  --expect-action-sha256 "$expected_action_sha256" < result.jsonl
```

Do not extract the expected value from the file being checked just to make this
comparison pass. If no independent expectation was retained, use the existing
unguarded inspection and describe the supplied target without claiming it is
the intended task. This option does not discover or authenticate an expectation.

The option accepts exactly one 64-character lowercase hexadecimal digest.
Malformed or repeated options return exit `2`. After the existing full-input
validation, a different digest or an input with no action also returns `2`,
with no operation summary. A matching legacy or v1 input produces the same
JSON or human output as unguarded inspection. A matching action-only prefix
remains UNKNOWN. Without the option, empty/prefix behavior and the original
six-case outputs are unchanged. Exit `0` still does not mean operation success.

The Python equivalents are
`inspect_saved_result(raw, expected_action_sha256=retained_digest)` and
`summarize_saved_result(raw, expected_action_sha256=retained_digest)`;
omitting the keyword or passing `None` selects the existing unguarded behavior.
Malformed expectations, missing action or mismatch raise `EvidenceError`.
Both functions retain the existing return shape and status meanings.

The digest matches the claimed action only. It does not authenticate origin,
freshness, successful process exit, causation or current external state, and
cannot distinguish substituted records for that same action. The command stays
offline and never follows input paths, changes records or creates authority.
This optional guard requires the updated reader; the historical `f9ef944` pin
does not support the flag or keyword. Retain that pin and the six legacy cases
for their existing reproduction/held human-acceptance purpose. Record the exact
source revision and any local patch used for this new guard.

### Check the exact saved input

The action guard identifies the intended operation; two different saved files
can still describe that same action. In this local update, the separate optional
`--expect-input-sha256` guard compares the exact bounded input bytes with a
SHA-256 retained separately **when the file was handed off**. It reuses the
existing `input_sha256` calculation; there is no new file format or manifest.

For example, the sender can run `shasum -a 256 result.jsonl` on the original file
and retain/share its digest separately. With both independently retained values
already set, the recipient runs:

```sh
mothership-evidence inspect-result --human \
  --expect-action-sha256 "$expected_action_sha256" \
  --expect-input-sha256 "$expected_input_sha256" \
  --explain-error < result.jsonl 2> rejection.json
```

Do not copy the expectation out of the received input or compute it from that
input just to pass the guard. If no separate checksum exists, inspect without
this guard and do not claim that the supplied bytes match the intended handoff.
The reader neither discovers nor authenticates the expectation.

The option accepts exactly one 64-character lowercase hexadecimal digest.
Malformed/repeated expectations reject before stdin is read. All existing
record validation runs before either comparison; an invalid record remains
`invalid_saved_result` even if its bytes match. The action comparison runs first
when both guards are supplied. Valid records with differing input bytes return
exit `2`, no summary, and (with `--explain-error`) `expected_input_mismatch`.
The next check directs the recipient to the separately retained checksum; it
never includes either digest or input content. Default errors stay unchanged.

This hashes raw bytes, including whitespace and newlines, not canonical JSON.
It detects a cleanly removed trailing row against a retained full-file checksum.
An explicitly expected empty input remains UNKNOWN without the action guard;
with the action guard it still rejects because no action was supplied. A
matching valid prefix remains incomplete. Accepted JSON/human output is
unchanged for legacy and v1, including the original six cases.

Python APIs accept the keyword-only `expected_input_sha256=retained_checksum`
on both `inspect_saved_result` and `summarize_saved_result`, alongside
`expected_action_sha256`. Omitted/`None` means no input comparison. A `str`
input is hashed as UTF-8 bytes. Invalid expectations or mismatches raise
`EvidenceError`. There are no additional file reads, network calls, execution,
reconsume or repairs. Matching proves bytes against the supplied expectation,
not source, freshness, process exit, causation or external truth.

Availability: this flag/keyword requires the local patch based on full revision
`6c37212cbcfbf9f17757157ae502a7c4922e1039`; checking out that base alone does
**not** include the patch. Record the base and exact reviewed patch, then build
all three wheels from that updated checkout using the wheel commands above in
fresh build/install directories. Check its installed `inspect-result --help`
for this flag. The PR #59 setup pin remains a historical reproducible baseline
for v1/action checking, and the PR #56/PR #45 pins and six-case exercise stay
unchanged. No published release or human acceptance is claimed for this addition.

### Explain a rejected saved result

The updated local source candidate adds the opt-in `--explain-error` flag to
`inspect-result`. Use it with either output mode and keep the fixed diagnostic
on stderr separate from the saved-result projection on stdout:

```sh
mothership-evidence inspect-result --human \
  --expect-action-sha256 "$expected_action_sha256" \
  --explain-error < result.jsonl 2> rejection.json
```

For a rejected input, the command still returns exit `2` and does not produce
an accepted operation/result summary. When stdout has a partial display because
its write or flush failed, discard that partial output. When stderr is writable,
the opt-in diagnostic is one fixed JSON line with schema
`mothership.saved-result-rejection.v0`; it contains only `code`,
`next_read_only_check`, `accepted_result: false`, `authority: false`,
`source_authenticated: false`, `external_effect_verified: false`, and
`recovery: "no re-execution; no reconsume"`. The values come from a fixed
allowlist. The diagnostic never adopts an input action ID or digest and never
includes raw input, hashes, paths or exception text. It does not establish an
operation outcome or authenticate the source. There is no repair, retry,
reconsume, network request or implicit input-path read. A short or failed
diagnostic write returns `2` without retrying the diagnostic write.

Accepted input has the same stdout/stderr, exit status and status meanings with
or without this flag. Normal argparse grammar and help errors retain argparse's
behavior; this option does not promise a JSON diagnostic for arbitrary command
line syntax errors.

The rejection codes and bounded next checks are:

| Code | Safe next read-only check |
| --- | --- |
| `invalid_expectation` | Check the digest and command separately retained from the original task. |
| `input_unavailable` | Check the original bytes and the bounded input access; preserve what was supplied. |
| `invalid_saved_result` | Preserve the supplied bytes and compare a separately retained checksum or original with the sender. |
| `expected_action_unavailable` | Inspect the separately retained original task or action record; missing action identity is not proof of no operation. |
| `expected_action_mismatch` | Compare the separately retained original task digest; never take the expectation from the rejected file. |
| `expected_input_mismatch` | Compare the separately retained handoff checksum; preserve original bytes and do not replace the expectation from the input. |
| `output_incomplete` | Discard partial display and inspect the selected output destination. This code is only for stdout write/flush failure. |
| `inspection_unavailable` | Preserve the input and inspect the reader environment when serialization, import or another runtime failure is unclassified. |

`invalid_saved_result` is for a supplied record that fails full validation,
including corrupt, torn or mixed records. A fully validated record with a
different retained expected action is `expected_action_mismatch`; a valid input
without an action is `expected_action_unavailable`, including empty input plus
an expectation. Serialization, import and unclassified runtime failures remain
`inspection_unavailable`, never corrupt evidence; only stdout write/flush
failure is `output_incomplete`. Wrong expectations are checked only after full
input validation, so a malformed record is never reclassified as a validated
mismatch.

The flag is present only in this updated, unreleased local source candidate. It
is not part of the existing full pins
`fd8d4f0cbb80d3f87cd97ffd50f5e83468c94646`,
`f9ef944bf54cb413824066f968010c0aaedc47ff` or
`91f474ed9ba96f5c00925d44f3dd84739d41cdc7`, nor of a published release. Do
not describe an uncommitted working-tree change as part of an older installed
pin. Keep those historical/current pins and the original six-case recipient
guides unchanged.

Human usability acceptance remains separate: give success, unconfirmed and
stopped saved cases to a person unfamiliar with the implementation, and record
time to understand, author questions, mistaken completion claims and the next
record they select. Synthetic/agent checks do not supply these human metrics.
No daily-host activation or human-study completion is implied by this example.

## One retained session and synthetic transport

Every execution route wraps the same `MergeReviewSession`. It retains the live
`FrozenAction`, the original request, the caller-attested response, and the
same separate authority and attempt ledger paths. The context provider is
called again at review and effect boundaries. A transport callback must check
the parameters it receives against the retained action.

The smallest synthetic shape is:

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from mothership_adapters.session import MergeReviewSession

parameters = {
    "repository": "example/repo",
    "pull_request": 7,
    "expected_head_sha": "a" * 40,
    "expected_base": "main",
    "merge_method": "merge",
}
context = {
    "host_id": "synthetic-host",
    "session_id": "session-1",
    "actor_id": "caller-1",
    "runtime_generation": "generation-1",
    "scope": ["github.merge_pr"],
}

class SyntheticTransport:
    def get_pull_request(self, repository, pull_request):
        assert (repository, pull_request) == ("example/repo", 7)
        return {
            "http_status": 200, "state": "open", "merged": False,
            "head_sha": "a" * 40, "base_ref": "main",
        }

    def merge_pull_request(self, **received):
        assert received == {
            "repository": "example/repo", "pull_request": 7,
            "expected_head_sha": "a" * 40, "merge_method": "merge",
        }
        return {"http_status": 200, "merged": True,
                "merge_commit_sha": "b" * 40}

scratch = TemporaryDirectory(prefix="mothership-example-")
ledger_dir = Path(scratch.name)  # A fresh private mode0700 parent.
session = MergeReviewSession(
    parameters,
    context_provider=lambda: dict(context),
    authority_path=ledger_dir / "authority.jsonl",
    attempts_path=ledger_dir / "attempts.jsonl",
    transport=SyntheticTransport(),
    executor_ref={"ref_id": "executor:synthetic", "sha256": "c" * 64},
)
request = session.request
response = {
    "schema_version": "authority-action-review-response.v0",
    "decision": "approve",
    "request_id": request["request_id"],
    "request_sha256": request["request_sha256"],
    "action_id": request["action"]["action_id"],
    "action_sha256": request["action_sha256"],
}
assert session.review(response) == "approve"
result = session.execute(parameters)
assert result["receipt"]["status"] == "SUCCESS"
scratch.cleanup()
```

The example uses a fresh private temporary directory and removes its synthetic
ledgers. A real host retains its ledgers in a private mode0700 parent directory;
`authority_path` and `attempts_path` must be different. The companion owns one bounded effect attempt, and a missing finish
or uncertain transport result is preserved as rejection or UNKNOWN according
to the existing contract. There is no retry, restart, or reconsume path.

## Session failures and existing evidence

The Python diagnostic API is included in the [current candidate](#try-the-current-candidate)
pinned above. The historical PR #45 revision does not contain it. Record the
selected revision; this is not a released-package or live-host qualification.

Python callers can read `SessionError.diagnostic` without exposing callback or
ledger exception text. It is a detached mapping: changing the returned mapping
does not change the error or session. Existing exception messages, terminal
states and execution results remain unchanged.

```python
import json
from mothership_adapters.session import SessionError

retained_request = session.request  # Keep the request before this invocation.
try:
    result = session.execute(parameters)  # The host's one approved invocation.
except SessionError as error:
    print("same-call diagnostic (caller observation):",
          retained_request["request_id"],
          retained_request["request_sha256"],
          retained_request["action"]["action_id"],
          retained_request["action_sha256"])
    print(json.dumps(error.diagnostic, sort_keys=True))
    print("Diagnostic unknown fields describe this call's observation; "
          "they do not override retained source records.")
    print("A failed phase code does not establish the remote outcome.")
    # Keep the existing records for inspection; do not execute again here.
```

The caller knows this relationship because it retained the request and caught
the error from that invocation in the same handler. The diagnostic mapping has
no action or request ID of its own. Printing the identifiers does not create a
durable binding or authenticate the observation. Do not attach a saved
diagnostic to a bundle by matching filenames, dates or phases. If that same-call
context or diagnostic was not retained, report it as unavailable.

The mapping contains `code`, `phase`, `authority_use`, `external_effect`,
`next_check`, and `retry_allowed` (always false). Codes and phases come from a
fixed vocabulary, never from raw exceptions, paths or host input. The phase is
the last local boundary observed, not a certified exact failure location.

| Observed phase | What to inspect |
| --- | --- |
| `review_validation` | Retained request and response; their action, expiry and context binding |
| `decision_record` | Existing authority records; the decision write may have persisted before raising |
| `execution_validation` | Retained request and supplied parameters/context, plus existing records |
| `companion_execution`, `preflight_transport`, `preflight_returned` | Existing authority and attempt records; the last phase does not prove whether consume/start persisted |
| `mutation_guard`, `mutation_transport`, `mutation_returned` | Existing authority and attempt records; transport return does not prove external success or finish persistence |
| `receipt_build`, `result_export` | Existing evidence and source records; do not manufacture a Receipt or missing record |
| `unknown` | Existing evidence and source records; this includes owner/phase errors and unclassified errors |

`authority_use` means one-shot consume, not writing an approval/rejection.
`not_attempted BY THIS CALL` is limited to the current call before companion
entry; it says nothing about earlier calls, other tools or host callback effects.
Once the companion is entered, authority use and external effect are both
`unknown`. This intentionally does not infer a durable consume or remote outcome
from an exception or from the absence of a record.

The fixed `next_check` values select these read-only categories:
`review_request`, `authority_records`, `review_request_and_existing_records`,
`authority_and_attempt_records`, or `existing_evidence_bundle`. They are guidance,
not executable commands or permission to create replacement evidence. The
owner/JavaScript protocol defaults to its existing generic error. The updated
paired client/owner can explicitly forward this mapping as described under
[Node Session diagnostics](#node-session-diagnostics). This is not automatic
forwarding through every host adapter.

If an evidence bundle has already been retained or exported through the existing
validated exporter, inspect it offline:

```sh
mothership-evidence inspect --human < existing-bundle.json
```

This command requires that existing file. Diagnostics do not save or assemble a
bundle and do not read a ledger themselves. Preserve original records and bind
any exported bundle using the existing [evidence route](#read-only-evidence-routes).
The host may supply records it retained, or read its explicitly retained source
paths, to `export_evidence(retained_request, ...)`. Supply only available rows
for that request; the exporter validates their relationships. It does not locate
records, choose a newest file, restore the session, or bind an arbitrary
diagnostic to the bundle. Keep the same-call diagnostic display separate from
the provided-record summary and structural inspection limits. A decision or
consume write can persist before an exception: use the actual source records
rather than treating the exception as proof that nothing was saved.
If export or inspection rejects the supplied records or sidecar, produce no
operation summary. A caller can still display its separately retained expected
request as caller context, clearly stating that the rejected input has not been
bound to it. Next, compare the explicitly supplied record/sidecar IDs and hashes
with that retained request. If the caller context is unavailable too, leave the
operation identity unknown; do not infer it from rejected input or repair records.
A missing finish remains missing: inspection can explain the missing Receipt and
Verification, but `readback` still accepts only complete execution evidence with
`missing == ["verification"]`. Do not insert a finish, mint a Receipt, retry a
mutation or consume again to make the bundle eligible. Inspecting records is not
proof of their origin or the current external state.

## Python host routes

The optional SDK adapters do not replace the retained session or serialize it
for later restoration.

| Host | Exact calls | What is retained |
| --- | --- | --- |
| Agents SDK | `adapter = AgentsMergeAdapter(session)`; `prepared = await adapter.prepare(agent, input)`; `result = await adapter.resume(response)` | The typed `mothership_github_merge_pr` tool, its call identity, raw arguments, cloned agent, and SDK approval state |
| LangGraph | `adapter = LangGraphMergeAdapter(session)`; `prepared = adapter.prepare(thread_id)`; `result = adapter.resume(response, thread_id=prepared["thread_id"], interrupt_id=prepared["interrupt_id"])` | The original thread and interrupt IDs; the internal `InMemorySaver` carries review data, never the live session |
| UME-HARNESS | `bridge = HarnessMergeBridge(...)`; `bridge.review(response)`; `bridge.execute(parameters)`; `bridge.suspend()` / `bridge.resume()` | The local lease observation and the same host context; the lease does not become external permission |

The Agents SDK route accepts only an `Agent` with `hooks=None`; caller-supplied
`AgentHooks` are rejected before the runner starts. The adapter clones that agent
and owns the fixed function tool and its run hooks. Changing the tool callback,
schema, guardrails, approval policy, or dispatch identity stops the route before
review or execution. This qualification does not cover private SDK mutation or
arbitrary Python monkeypatching.

For a real Harness fixture qualification, set the test-only source root to the
pinned fixture before running the focused test. The recorded fixture is
`v0.1.7` at commit
`d7640a03b4b823d960f6e382607ad04aa8678c84`; without the variable, the fixture
qualification is explicitly skipped:

```sh
MOTHERSHIP_HARNESS_ROOT=/path/to/pinned-harness \
python -m unittest packages/mothership-adapters/tests/test_harness.py
```

This command is a qualification recipe, not evidence that a Harness runtime
was activated by this package.

## JavaScript owner, OpenClaw, and Lobster

`MergeOwnerClient` owns one Python child process and exposes only the fixed
sequence `prepare(parameters, executorRef)`, `review(response)`,
`execute(parameters)`, `cancel()`, and `close()`. The host passes callbacks for
context and the exact two transport operations:
`getPullRequest(repository, pullRequest)` and
`mergePullRequest(repository, pullRequest, expectedHeadSha, mergeMethod)`.
These positional signatures are the default, including callbacks with default
or rest parameters. `transport.getPullRequestMode` and
`transport.mergePullRequestMode` select each callback's contract independently:
omitting a mode or passing `undefined` selects `"positional"`; `"object"` passes
one detached payload object. Only these two strings are accepted. Other values,
including `null`, raise `OwnerClientError("parameters")` before child creation.
The constructor retains each selected mode; later transport-property changes do
not change it. Both constructor forms accept these transport options, and the
`get_pull_request` / `merge_pull_request` aliases use the same camel-case mode
keys. Existing callbacks that expect one payload object must opt in explicitly:

```js
transport: {
  getPullRequestMode: "object",
  mergePullRequestMode: "object",
  getPullRequest: objectGetPullRequest,
  mergePullRequest: objectMergePullRequest,
}
```

Callbacks that ignore all arguments need no change. Callback arity is not used
to infer a contract, and callback exceptions do not trigger a second call.
The owner checks callback parameters against the retained action and uses a
30-second bounded command deadline. A child failure after consume is
unresolved; the caller must not restart or replay it.

Owner `result` and `error` frames correlate a reply with one command through
`seq`, `reply_to`, and the retained owner/request/action IDs. The payload still
has the meaning of that command: `prepare` returns a review request, `review`
returns a caller-attested decision, and `execute` returns an execution report
with its Receipt. Receiving a reply is not a separate grant of authority or
independent Verification. There is no standalone ACK message or durable owner
resume protocol.

If the final execution reply is lost, do not resend `execute`, including with
the same IDs or changed parameters. Inspect records already retained by the
caller; an absent reply does not establish whether an effect occurred. Repeated
offline export/inspection of retained records neither recreates the live owner
nor spends authority. Missing Verification remains missing. The
[bounded delivery traces](composition.md#delivery-replies-and-one-use-authority)
exercise this connection with synthetic callbacks and temporary fixture records.

### Node Session diagnostics

This unreleased addition requires the updated `owner-client.mjs` and Python
owner from this same checkout. The PR #55 baseline pinned above includes this
opt-in. Historical PR #49 and PR #45 revisions predate it; installing their
pinned packages does not add later client/owner files.

The object constructor accepts `sessionDiagnostics: true`. Omitting it, passing
`undefined`/`false`, or using the positional constructor retains
`mothership-owner.v0` and its strict code-only errors. Other values, including
`null`, fail before child creation. The opt-in launches the same single owner
with the fixed `--session-diagnostics` flag and uses `mothership-owner.v1` for
every frame. There is no version negotiation, restart, downgrade or fallback.
An old client with the updated owner continues using v0. An opt-in client with
an old owner fails at launch/protocol handling; do not retry with another mode.

Only an actual Python `SessionError` adds the six-field diagnostic to a v1
`{code: "session", diagnostic: ...}` reply. Other owner errors remain code-only.
Parent callback errors must remain code-only in either version. A malformed
callback rejected inside Session can become Session's own sanitized UNKNOWN
diagnostic; a diagnostic supplied by the parent is never adopted. The client
validates the closed diagnostic tuples and existing schema/owner/seq/reply/
request/action correspondence before exposing the matched error.

```js
const owner = new MergeOwnerClient({
  pythonExecutable, authorityPath, attemptsPath, contextProvider, transport,
  sessionDiagnostics: true,
});
try {
  // Use this retained owner's normal prepare/review/execute flow.
} catch (error) {
  // OwnerClientError.diagnostic is a detached mapping or null.
  // Retain it with this call's context; never use it to authorize a retry.
} finally {
  await owner.close();
}
```

`OwnerClientError.diagnostic` returns a detached mapping on every read, or
`null` when no Session diagnostic was received. Native EOF/EPIPE, child loss,
timeouts, parameter errors and invalid wire diagnostics do not acquire an
invented Python phase. Both `null` and a valid UNKNOWN diagnostic leave the
external result unconfirmed. Correlation is not source authentication or durable
evidence binding. Keep this same-call observation separate from any supplied
bundle's `inspect --human` output; it does not create a Receipt or Verification.

Run the real-child terminal example from this updated checkout with Python
3.12+ and Node 22+:

```sh
PYTHONPATH=.:packages/mothership-github:packages/mothership-adapters \
  PYTHON_EXECUTABLE=python3 node examples/owner_diagnostic_terminal.mjs finish
```

Use `review` for context drift before approval recording, `preflight` for a
synthetic GET failure after companion entry, or `finish` (the default) for a
synthetic finish-save refusal after one merge callback. All callbacks are
synthetic, with no credentials, network or live GitHub operation. The example
does create synthetic review/consume records in temporary fixture ledgers. In
`finish`, it changes only that temporary attempts file's mode from 0600 to 0400,
so the existing writer refuses to append; it never fills in a missing finish.
The child is closed and temporary files removed in `finally`.

The display separates the last observed phase, unknown effects, next existing
records to inspect and no re-execution/reconsume. A returned synthetic transport
value is not confirmation of a remote result. OpenClaw/Lobster wrappers still
map their errors to generic messages: this example accepts the direct Node
client/terminal path only, not deployed wrappers or a selected daily host.
They do not qualify a Hermes delivery path or an actual host deployment.

The selected OpenClaw route registers one typed `mothership_merge_pr` tool and
one `beforeToolCall` seam. The hook retains the exact tool-call ID and
parameters, returns an allow-once/deny review checkpoint, and closes the owner
on timeout, cancellation, mismatch, or failure. It deliberately excludes
nested, delegated, client/native, and unwrapped tool paths.

The selected registration seam is:

```js
const selected = createSelectedMergeTool({ owner, parameters, executorRef });
const checkpoint = await selected.beforeToolCall(
  { toolName: selected.tool.name, toolCallId, params: parameters },
  { toolCallId, delegated: false, nested: false },
);
```

The host resolves `checkpoint.requireApproval` and later invokes the same
selected tool with the retained call ID and parameters. It does not register a
global hook or claim coverage for other OpenClaw tool paths.

The Lobster route uses an embedded runtime with a private fixed registry for
`mothership.preview`, `mothership.approve`, and `mothership.merge`. A resume
token only resumes the embedded checkpoint; it never selects or restores the
owner. Use the retained owner and the same `parameters`/`executorRef`:

```js
const owner = new MergeOwnerClient({
  pythonExecutable,
  authorityPath,
  attemptsPath,
  contextProvider,
  transport: { getPullRequest, mergePullRequest },
});
const adapter = new LobsterMergeAdapter({
  owner, runtime, stateDir, parameters, executorRef,
});
const pending = await adapter.prepare();
const result = await adapter.resume(reviewResponse, {
  token: pending.resumeToken,
});
```

The OpenClaw and Lobster source pins are part of the qualification record:
OpenClaw snapshot
`6cc8bb1a4b9e97b4461c5cbd9006adf4630b9ccc`, and Lobster embedded runtime
commit `74db2679fe34c6b04b067eebea943eaabd8b789f`. The selected checks do not
qualify a full gateway, production wrapper, credentials, or live GitHub merge;
independent selected-wrapper review passed.

## Read-only evidence routes

The MCP server is launched by `mothership-evidence-mcp` over inherited stdio.
It exposes exactly three read-only tools:

* `receipt_validate`
* `receipt_verification_validate`
* `evidence_inspect`

Export and default inspection are stdin-only and offline. Pass bytes
through the host's supported local command interface, for example the
repository-local Dots fixture:

```sh
mothership-evidence inspect < integrations/dots/example-bundle.json
mothership-evidence inspect --human < integrations/dots/example-bundle.json
```

The explicit `readback` command is the only CLI route that may perform the
companion's public observation. It accepts one complete
`host-evidence-bundle.v0` whose derived Receipt is present and whose
`missing` list is exactly `["verification"]`. It validates the bundle, action
digest, Receipt lineage, and absence of an existing Verification before any
network call; malformed, foreign, incomplete, or already-verified input is
rejected without a GET. It writes a new bundle and leaves the input untouched:

```sh
mothership-evidence readback < original.json > verified.json 2> readback-evidence.json
```

Require exit status `0` and retain `readback-evidence.json`. The Python helper
`mothership_adapters.readback.readback_evidence(bundle, *, opener=None)` returns
`{"bundle": ..., "evidence": ...}`; the stderr file is that complete sanitized
`evidence` sidecar. Its canonical SHA-256 must equal the `sha256` in `verified.json`'s
`verification.evidence_refs`; this sidecar is caller-retained and is not a
source-authentication record. A single invocation makes at most two public
tokenless GETs, sends no credentials or `Authorization` header, and never
retries, polls, consumes authority, calls an executor, or writes a ledger.
The command emits the sidecar to stderr before attempting the new bundle on
stdout. Successful stderr is data, not an error log; do not merge the streams
with `2>&1`. Input and setup failures report a fixed sanitized diagnostic on
stderr with a nonzero exit status. Stream failures stop with a nonzero exit;
when the error sink is still writable, the fixed diagnostic may be reported,
but a failed stderr write is not retried. Discard both redirected files,
including any partial stream, unless the exit status is `0` and the canonical
hash check passes. A valid observation that is `UNKNOWN` or `MISMATCH` remains
a successful read-back bundle with its status preserved.

JSON export and inspection emit one complete newline-terminated value and require
a successful flush before exit `0`. A short write, invalid write count, or stream
failure returns nonzero without retry; discard partial output. Successful JSON
bytes and the inspection schema are unchanged.

The default command retains its JSON inspection contract. `--human` selects a
bounded text explanation for the local Terminal: recorded approval, recorded
authority use, Receipt, independent Verification, missing records, the supplied
observation summary, and a next read-only check. A missing
Verification record means independent confirmation has not been established by
this bundle; it does not prove verification never occurred. Missing decision or
consume records do not prove cancellation or absence of an effect. The current
Bundles produced by this read-back producer carry its allowlisted fixed reason
code and bounded explanation inside `observed_state.summary`; existing or
caller-supplied Verification summaries remain arbitrary caller-reported text.
The producer's structured sibling `evidence.reason` remains in the
caller-retained sidecar. Without an explicit sidecar, the formatter displays the supplied summary after
escaping it and does not parse prose into a trusted reason or authenticate the
source. The displayed text is not a diagnosis or instruction. The separate
`structured reason: unavailable in bundle` label refers to the absent structured
field, even when the caller-reported summary includes a reason string. The
next read-only check compares the referenced evidence’s canonical hash with
`verification.evidence_refs`; it does not require another readback.
The explanation keeps source-unverified visible and never suggests re-execution
or reconsume as recovery. It performs no read-back or other network request.

To inspect the retained sidecar as well, use the optional local-file input:

```sh
mothership-evidence inspect --human --readback-evidence readback-evidence.json < verified.json
```

`--readback-evidence` requires `--human`; it does not change the default JSON
inspection or MCP contract. The bundle still comes from stdin. Only the explicit
sidecar path is opened, with no-follow/nonblocking access and a regular-file
check. Final-component symlinks, FIFOs, devices and directories are rejected. Each input has the
existing 262,144-byte limit and strict JSON/type/depth/node bounds. Unsupported
file-access safeguards fail closed. No URL or path inside evidence is opened.

The offline reader validates the current `github-merge-readback.v0` shape and
matches the sidecar's canonical SHA-256 to the single `github-readback:` evidence
reference, its action ID/digest to the bundle, and its state hash to Verification.
It then displays the structured reason as **caller-reported**, with the recorded
observation time and conservative guidance. `clock_rollback` remains readable as
`UNKNOWN`: timestamps must use the zero-padded, uppercase UTC form
`YYYY-MM-DDTHH:MM:SSZ`, but ordering and external semantics are not re-evaluated.
Unknown well-formed reason codes receive generic guidance.

Bad input or a binding mismatch returns exit status 2 with a fixed diagnostic
and no human explanation. A complete explanation requires a complete write and
successful flush; discard partial output on failure. Exit 0 means inspection
completed, including for `UNKNOWN` and `MISMATCH`, not that the action succeeded.
This check proves internal binding only; it does not authenticate the source,
transport, actor, timing or causation, and it does not establish current remote
state. No network, retry, re-execution, reconsume or ledger write occurs.

The Python equivalent is `summarize_evidence(bundle, readback_evidence=sidecar)`
from `mothership_adapters.evidence`. Omitting the keyword preserves the existing
human output. Retain both original inputs for later inspection.

`mothership-evidence export` accepts a bounded request/envelope on stdin and
produces a deterministic `host-evidence-bundle.v0`. Export, inspect, inspect
`--human`, and MCP routes
preserve `caller-attested`, `source_authenticated=false`,
`authority=false`, and `external_effect_verified=false`. A self-consistent
bundle is still not authenticated external evidence.

Dots uses the repository-local `mothership-evidence-inspect` skill and the
default stdin-only inspection route. The skill is not installed or activated by this repository;
local and cloud Dots runtime qualification remains unperformed.

## Qualification boundaries

These routes are bounded adapters around the current `github.merge_pr` profile.
They are not a generic executor, socket service, daemon, retry mechanism,
credential manager, identity authenticator, or automatic UME-HARNESS bridge.
They do not add a new operation profile. Keep Receipt and independent
Verification separate, preserve missing finish and UNKNOWN, and stop on
context/action/expiry drift before transport. A future storage, device, or
other operation needs its own exact profile and independent review evidence.
