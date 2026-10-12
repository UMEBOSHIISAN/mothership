import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { delimiter, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { MergeOwnerClient, OwnerClientError } from "./owner-client.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "../..");
const PYTHON = process.env.PYTHON_EXECUTABLE ?? resolve(ROOT, "../ci-venv/bin/python");
process.env.PYTHONPATH = [
  ROOT,
  resolve(ROOT, "packages/mothership-adapters"),
  resolve(ROOT, "packages/mothership-github"),
].join(delimiter);

const PARAMETERS = {
  repository: "example/repo",
  pull_request: 7,
  expected_head_sha: "a".repeat(40),
  expected_base: "main",
  merge_method: "merge",
};
const CONTEXT = {
  host_id: "node-owner-test",
  session_id: "session",
  actor_id: "actor",
  runtime_generation: "generation",
  scope: ["github.merge_pr"],
};
const EXECUTOR_REF = { ref_id: "executor:node-owner-test", sha256: "c".repeat(64) };

async function makeClient(temp, { getPullRequest, mergePullRequest } = {}) {
  return new MergeOwnerClient({
    pythonExecutable: PYTHON,
    authorityPath: resolve(temp, "authority.jsonl"),
    attemptsPath: resolve(temp, "attempts.jsonl"),
    contextProvider: async () => structuredClone(CONTEXT),
    transport: {
      getPullRequest: getPullRequest ?? (async ({ repository, pull_request }) => ({
        http_status: 200,
        state: "open",
        merged: false,
        head_sha: PARAMETERS.expected_head_sha,
        base_ref: PARAMETERS.expected_base,
      })),
      mergePullRequest: mergePullRequest ?? (async (_parameters) => ({
        http_status: 200,
        merged: true,
        merge_commit_sha: "b".repeat(40),
      })),
    },
  });
}

function installPending(client, type) {
  let resolve;
  let reject;
  const promise = new Promise((nextResolve, nextReject) => {
    resolve = nextResolve;
    reject = nextReject;
  });
  promise.catch(() => {});
  const seq = client._parentSeq;
  client._pending = { seq, type, resolve, reject, timer: undefined };
  return { promise, seq };
}

function resultFrame(client, pending, payload, {
  requestId = client._requestId,
  actionId = client._actionId,
} = {}) {
  return {
    schema_version: "mothership-owner.v0",
    type: "result",
    seq: 1,
    reply_to: pending.seq,
    owner_id: client.ownerId,
    request_id: requestId,
    action_id: actionId,
    payload,
  };
}

function callbackFrame(client, type, payload) {
  return {
    schema_version: "mothership-owner.v0",
    type,
    seq: 1,
    reply_to: null,
    owner_id: client.ownerId,
    request_id: client._requestId,
    action_id: client._actionId,
    payload,
  };
}

async function injectFrame(client, frame) {
  try {
    await client._handleFrame(frame);
  } catch (error) {
    client._fatal(error.code ?? "protocol");
  }
}

async function assertRejectsWithoutStall(promise, codes = ["protocol"]) {
  const timeout = new Promise((_, reject) => {
    setTimeout(() => reject(new Error("pending promise stalled")), 500);
  });
  await assert.rejects(Promise.race([promise, timeout]), (error) => (
    error instanceof OwnerClientError && codes.includes(error.code)
  ));
}

test("one real child carries prepare/review/execute and exposes measured cleanup", async () => {
  const temp = await mkdtemp(resolve(tmpdir(), "mothership-owner-node-"));
  const client = await makeClient(temp);
  try {
    assert.equal(typeof client.childPid, "number");
    assert.ok(client.childPid > 0);
    const request = await client.prepare(PARAMETERS, EXECUTOR_REF);
    assert.deepEqual(request.action.execution_parameters, PARAMETERS);
    assert.equal(await client.review({
      schema_version: "authority-action-review-response.v0",
      decision: "approve",
      request_id: request.request_id,
      request_sha256: request.request_sha256,
      action_id: request.action.action_id,
      action_sha256: request.action_sha256,
    }), "approve");
    const result = await client.execute(PARAMETERS);
    assert.equal(result.receipt.status, "SUCCESS");
    await client.close();
    assert.equal(client.exited, true);
    assert.equal(client.cleanedUp, true);
  } finally {
    await client.close();
    await rm(temp, { recursive: true, force: true });
  }
});

test("reject and cancel stay terminal and changed parameters never reach the child", async () => {
  const temp = await mkdtemp(resolve(tmpdir(), "mothership-owner-node-"));
  const client = await makeClient(temp);
  try {
    const request = await client.prepare(PARAMETERS, EXECUTOR_REF);
    const response = {
      schema_version: "authority-action-review-response.v0",
      decision: "reject",
      request_id: request.request_id,
      request_sha256: request.request_sha256,
      action_id: request.action.action_id,
      action_sha256: request.action_sha256,
    };
    assert.equal(await client.review(response), "reject");
    await assert.rejects(() => client.execute(PARAMETERS), (error) => error instanceof OwnerClientError && ["phase", "session"].includes(error.code));
    await client.close();
  } finally {
    await client.close();
    await rm(temp, { recursive: true, force: true });
  }
});

test("constructor paths stay outside JSON and concurrent execute cannot create a second call", async () => {
  const temp = await mkdtemp(resolve(tmpdir(), "mothership-owner-node-"));
  const client = await makeClient(temp);
  try {
    const request = await client.prepare(PARAMETERS, EXECUTOR_REF);
    await client.review({
      schema_version: "authority-action-review-response.v0",
      decision: "approve",
      request_id: request.request_id,
      request_sha256: request.request_sha256,
      action_id: request.action.action_id,
      action_sha256: request.action_sha256,
    });
    const first = client.execute(PARAMETERS);
    await assert.rejects(() => client.execute({ ...PARAMETERS, pull_request: 8 }), (error) => error.code === "busy" || error.code === "parameters");
    const result = await first;
    assert.equal(result.receipt.status, "SUCCESS");
    const attempts = JSON.parse((await readFile(resolve(temp, "attempts.jsonl"), "utf8")).split("\n")[0]);
    assert.equal(attempts.event_type, "attempt_started");
  } finally {
    await client.close();
    await rm(temp, { recursive: true, force: true });
  }
});

test("child loss during execution rejects as terminal uncertainty and leaves no live child", async () => {
  const temp = await mkdtemp(resolve(tmpdir(), "mothership-owner-node-"));
  const client = await makeClient(temp);
  try {
    const request = await client.prepare(PARAMETERS, EXECUTOR_REF);
    await client.review({
      schema_version: "authority-action-review-response.v0",
      decision: "approve",
      request_id: request.request_id,
      request_sha256: request.request_sha256,
      action_id: request.action.action_id,
      action_sha256: request.action_sha256,
    });
    process.kill(client.childPid, "SIGKILL");
    await assert.rejects(() => client.execute(PARAMETERS), (error) => ["child_lost", "eof", "closed"].includes(error.code));
    assert.equal(client.exited, true);
    assert.equal(client.cleanedUp, true);
  } finally {
    await client.close();
    await rm(temp, { recursive: true, force: true });
  }
});

test("transport exception is retained as one UNKNOWN attempt without replay", async () => {
  const temp = await mkdtemp(resolve(tmpdir(), "mothership-owner-node-"));
  const client = await makeClient(temp, { mergePullRequest: async () => { throw new Error("private transport detail"); } });
  try {
    const request = await client.prepare(PARAMETERS, EXECUTOR_REF);
    await client.review({
      schema_version: "authority-action-review-response.v0",
      decision: "approve",
      request_id: request.request_id,
      request_sha256: request.request_sha256,
      action_id: request.action.action_id,
      action_sha256: request.action_sha256,
    });
    const result = await client.execute(PARAMETERS);
    assert.equal(result.receipt.status, "UNKNOWN");
    await assert.rejects(() => client.execute(PARAMETERS), (error) => error.code === "phase");
  } finally {
    await client.close();
    await rm(temp, { recursive: true, force: true });
  }
});

test("GET callback parameters are bound to the retained action before host dispatch", async () => {
  const temp = await mkdtemp(resolve(tmpdir(), "mothership-owner-node-"));
  let getCalls = 0;
  const client = await makeClient(temp, {
    getPullRequest: async () => {
      getCalls += 1;
      return {
        http_status: 200,
        state: "open",
        merged: false,
        head_sha: PARAMETERS.expected_head_sha,
        base_ref: PARAMETERS.expected_base,
      };
    },
  });
  try {
    const request = await client.prepare(PARAMETERS, EXECUTOR_REF);
    await client.review({
      schema_version: "authority-action-review-response.v0",
      decision: "approve",
      request_id: request.request_id,
      request_sha256: request.request_sha256,
      action_id: request.action.action_id,
      action_sha256: request.action_sha256,
    });
    const pending = installPending(client, "execute");
    await client._handleFrame(callbackFrame(client, "get", {
      repository: "other/repository",
      pull_request: PARAMETERS.pull_request,
    }));
    assert.equal(getCalls, 0);
    await client.close();
    await pending.promise.catch(() => {});
  } finally {
    await client.close();
    await rm(temp, { recursive: true, force: true });
  }
});

test("merge callback parameters are bound to the retained action before host dispatch", async () => {
  const temp = await mkdtemp(resolve(tmpdir(), "mothership-owner-node-"));
  let mergeCalls = 0;
  const client = await makeClient(temp, {
    mergePullRequest: async () => {
      mergeCalls += 1;
      return { http_status: 200, merged: true, merge_commit_sha: "b".repeat(40) };
    },
  });
  try {
    const request = await client.prepare(PARAMETERS, EXECUTOR_REF);
    await client.review({
      schema_version: "authority-action-review-response.v0",
      decision: "approve",
      request_id: request.request_id,
      request_sha256: request.request_sha256,
      action_id: request.action.action_id,
      action_sha256: request.action_sha256,
    });
    const pending = installPending(client, "execute");
    await client._handleFrame(callbackFrame(client, "merge", {
      repository: PARAMETERS.repository,
      pull_request: PARAMETERS.pull_request,
      expected_head_sha: "b".repeat(40),
      merge_method: PARAMETERS.merge_method,
    }));
    assert.equal(mergeCalls, 0);
    await client.close();
    await pending.promise.catch(() => {});
  } finally {
    await client.close();
    await rm(temp, { recursive: true, force: true });
  }
});

test("prepare result execution parameters must equal the caller's original parameters", async () => {
  const temp = await mkdtemp(resolve(tmpdir(), "mothership-owner-node-"));
  const client = await makeClient(temp);
  try {
    client._originalParameters = structuredClone(PARAMETERS);
    const pending = installPending(client, "prepare");
    const payload = {
      request_id: "request",
      request_sha256: "a".repeat(64),
      action: {
        action_id: "action",
        action_sha256: "b".repeat(64),
        execution_parameters: { ...PARAMETERS, pull_request: PARAMETERS.pull_request + 1 },
      },
    };
    const frame = resultFrame(client, pending, payload, { requestId: "request", actionId: "action" });
    await injectFrame(client, frame);
    await assertRejectsWithoutStall(pending.promise, ["parameters"]);
    await client.close();
    assert.equal(client.cleanedUp, true);
  } finally {
    await client.close();
    await rm(temp, { recursive: true, force: true });
  }
});

for (const [type, payload] of [
  ["review", null],
  ["execute", null],
  ["cancel", "unexpected"],
]) {
  test(`malformed ${type} result rejects the pending call and cleans up`, async () => {
    const temp = await mkdtemp(resolve(tmpdir(), "mothership-owner-node-"));
    const client = await makeClient(temp);
    try {
      client._requestId = "request";
      client._actionId = "action";
      const pending = installPending(client, type);
      await injectFrame(client, resultFrame(client, pending, payload));
      await assertRejectsWithoutStall(pending.promise);
      await client.close();
      assert.equal(client.cleanedUp, true);
      assert.ok(["failed", "unresolved"].includes(client.phase));
    } finally {
      await client.close();
      await rm(temp, { recursive: true, force: true });
    }
  });
}
