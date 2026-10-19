// Source-checkout example: real Python owner, synthetic callbacks and temporary
// ledgers only. No credentials, network, live approval or live GitHub operation.
import { chmod, mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { MergeOwnerClient, OwnerClientError } from "../integrations/openclaw/owner-client.mjs";

async function main() {
  const mode = process.argv[2] ?? "finish";
  if (process.argv.length > 3 || !["review", "preflight", "finish"].includes(mode)) {
    console.error("usage: node examples/owner_diagnostic_terminal.mjs [review|preflight|finish]");
    process.exitCode = 2;
    return;
  }
  const temp = await mkdtemp(resolve(tmpdir(), "mothership-diagnostic-example-"));
  const attemptsPath = resolve(temp, "attempts.jsonl");
  const parameters = {
    repository: "example/repo", pull_request: 7,
    expected_head_sha: "a".repeat(40), expected_base: "main", merge_method: "merge",
  };
  const context = {
    host_id: "synthetic-terminal", session_id: "example", actor_id: "example",
    runtime_generation: "example", scope: ["github.merge_pr"],
  };
  let gets = 0;
  let merges = 0;
  let owner;
  try {
    owner = new MergeOwnerClient({
      pythonExecutable: process.env.PYTHON_EXECUTABLE ?? "python3",
      sessionDiagnostics: true,
      authorityPath: resolve(temp, "authority.jsonl"), attemptsPath,
      contextProvider: async () => structuredClone(context),
      transport: {
        getPullRequest: async () => {
          gets++;
          if (mode === "preflight") throw new Error("private-callback");
          return { http_status: 200, state: "open", merged: false,
            head_sha: parameters.expected_head_sha, base_ref: parameters.expected_base };
        },
        mergePullRequest: async () => {
          merges++;
          const rows = (await readFile(attemptsPath, "utf8")).trim().split("\n").map(JSON.parse);
          if (rows.length !== 1 || rows[0].event_type !== "attempt_started") {
            throw new Error("unexpected synthetic fixture");
          }
          // Fail the existing strict ledger mode check before finish append.
          // Do not rewrite or repair the start row or authority records.
          await chmod(attemptsPath, 0o400);
          return { http_status: 200, merged: true, merge_commit_sha: "b".repeat(40) };
        },
      },
    });
    const request = await owner.prepare(parameters, { ref_id: "executor:synthetic-terminal", sha256: "c".repeat(64) });
    if (mode === "review") context.actor_id = "changed-example";
    // Synthetic review data, not a human approval ceremony or identity proof.
    await owner.review({
      schema_version: "authority-action-review-response.v0", decision: "approve",
      request_id: request.request_id, request_sha256: request.request_sha256,
      action_id: request.action.action_id, action_sha256: request.action_sha256,
    });
    await owner.execute(parameters);
    throw new Error("expected a stopped synthetic call");
  } catch (error) {
    const diagnostic = error instanceof OwnerClientError ? error.diagnostic : null;
    const expectedPhase = { review: "review_validation", preflight: "preflight_transport", finish: "mutation_returned" }[mode];
    if (diagnostic === null || diagnostic.phase !== expectedPhase) {
      console.error("example stopped without expected Session diagnostic; result unknown; no retry");
      process.exitCode = 2;
      return;
    }
    const checks = {
      review_request: "existing retained review request and expected host context",
      authority_and_attempt_records: "existing authority and attempt records for this action",
    };
    console.log("synthetic local example; no network or live GitHub operation");
    console.log("synthetic approval/consume may be written only to temporary fixture ledgers");
    console.log("same-call observation; not persisted evidence or independent confirmation");
    console.log(`last observed phase: ${diagnostic.phase}`);
    console.log(`reason: ${diagnostic.code}`);
    console.log(`authority use: ${diagnostic.authority_use}`);
    console.log(`external effect: ${diagnostic.external_effect}`);
    console.log(`next read-only check: ${checks[diagnostic.next_check]}`);
    console.log("recovery: no re-execution; no reconsume");
    console.log(`callbacks: GET=${gets}, merge=${merges} (synthetic only)`);
    if (mode === "finish") console.log("a returned synthetic response does not establish a durable finish or remote result");
  } finally {
    try {
      if (owner !== undefined) await owner.close();
    } finally {
      await chmod(attemptsPath, 0o600).catch(() => {});
      await rm(temp, { recursive: true, force: true });
    }
  }
}

main().catch(() => {
  console.error("example or cleanup failed; result unknown; no retry");
  process.exitCode = 2;
});
