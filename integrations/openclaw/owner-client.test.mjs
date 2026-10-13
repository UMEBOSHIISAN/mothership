import assert from "node:assert/strict";
import { mkdtemp, readFile, readdir, rm } from "node:fs/promises";
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
process.env.PYTHONDONTWRITEBYTECODE = "1";

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

function makeClient(temp, options = {}) {
  const {
    getPullRequest,
    mergePullRequest,
    constructor: constructorForm = "object",
    aliases = "camel",
    omitModes = false,
    transport: suppliedTransport,
  } = options;
  const getMode = Object.hasOwn(options, "getPullRequestMode")
    ? options.getPullRequestMode : "object";
  const mergeMode = Object.hasOwn(options, "mergePullRequestMode")
    ? options.mergePullRequestMode : "object";
  const callbacks = suppliedTransport ?? {
    ...(omitModes ? {} : {
      getPullRequestMode: getMode,
      mergePullRequestMode: mergeMode,
    }),
    [aliases === "snake" ? "get_pull_request" : "getPullRequest"]:
      getPullRequest ?? (async (_parameters) => ({
        http_status: 200,
        state: "open",
        merged: false,
        head_sha: PARAMETERS.expected_head_sha,
        base_ref: PARAMETERS.expected_base,
      })),
    [aliases === "snake" ? "merge_pull_request" : "mergePullRequest"]:
      mergePullRequest ?? (async (_parameters) => ({
        http_status: 200,
        merged: true,
        merge_commit_sha: "b".repeat(40),
      })),
  };
  const contextProvider = async () => structuredClone(CONTEXT);
  if (constructorForm === "positional") {
    return new MergeOwnerClient(
      PYTHON,
      resolve(temp, "authority.jsonl"),
      resolve(temp, "attempts.jsonl"),
      contextProvider,
      callbacks,
    );
  }
  return new MergeOwnerClient({
    pythonExecutable: PYTHON,
    authorityPath: resolve(temp, "authority.jsonl"),
    attemptsPath: resolve(temp, "attempts.jsonl"),
    contextProvider,
    transport: callbacks,
  });
}

function getResult() {
  return {
    http_status: 200,
    state: "open",
    merged: false,
    head_sha: PARAMETERS.expected_head_sha,
    base_ref: PARAMETERS.expected_base,
  };
}

function mergeResult() {
  return { http_status: 200, merged: true, merge_commit_sha: "b".repeat(40) };
}

function callbackFor(type, shape, calls, failure) {
  const result = type === "get" ? getResult() : mergeResult();
  const invoke = (args) => {
    calls.push(args);
    if (failure === "sync") throw new Error("private callback detail");
    if (failure === "async") return Promise.reject(new Error("private callback detail"));
    return Promise.resolve(result);
  };
  if (shape === "trailing-default") {
    return type === "get"
      ? function(repository, pullRequest = 999) { return invoke([...arguments]); }
      : function(repository, pullRequest, expectedHeadSha, mergeMethod = "merge") {
          return invoke([...arguments]);
        };
  }
  if (shape === "rest") return function(...args) { return invoke(args); };
  if (shape === "object-high-arity") {
    return type === "get"
      ? function(value, unused) { return invoke([...arguments]); }
      : function(value, first, second, third) { return invoke([...arguments]); };
  }
  throw new Error(`unknown callback shape: ${shape}`);
}

async function approveAndExecute(client) {
  const request = await client.prepare(PARAMETERS, EXECUTOR_REF);
  assert.equal(await client.review({
    schema_version: "authority-action-review-response.v0",
    decision: "approve",
    request_id: request.request_id,
    request_sha256: request.request_sha256,
    action_id: request.action.action_id,
    action_sha256: request.action_sha256,
  }), "approve");
  return client.execute(PARAMETERS);
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

for (const [shape, modeOptions] of [
  ["trailing-default", { omitModes: true }],
  ["rest", { getPullRequestMode: "positional", mergePullRequestMode: "positional" }],
]) {
  test(`real child dispatches ${shape} GET and merge callbacks positionally`, async () => {
    const temp = await mkdtemp(resolve(tmpdir(), "mothership-owner-callback-mode-"));
    const getCalls = [];
    const mergeCalls = [];
    const client = makeClient(temp, {
      ...modeOptions,
      getPullRequest: callbackFor("get", shape, getCalls),
      mergePullRequest: callbackFor("merge", shape, mergeCalls),
    });
    try {
      const result = await approveAndExecute(client);
      assert.equal(result.receipt.status, "SUCCESS");
      assert.deepEqual(getCalls, [[PARAMETERS.repository, PARAMETERS.pull_request]]);
      assert.deepEqual(mergeCalls, [[
        PARAMETERS.repository,
        PARAMETERS.pull_request,
        PARAMETERS.expected_head_sha,
        PARAMETERS.merge_method,
      ]]);
    } finally {
      await client.close();
      await rm(temp, { recursive: true, force: true });
    }
  });
}

test("undefined callback modes default to positional for the real child", async () => {
  const temp = await mkdtemp(resolve(tmpdir(), "mothership-owner-callback-mode-"));
  const getCalls = [];
  const mergeCalls = [];
  const client = makeClient(temp, {
    getPullRequestMode: undefined,
    mergePullRequestMode: undefined,
    getPullRequest: callbackFor("get", "rest", getCalls),
    mergePullRequest: callbackFor("merge", "rest", mergeCalls),
  });
  try {
    const result = await approveAndExecute(client);
    assert.equal(result.receipt.status, "SUCCESS");
    assert.deepEqual(getCalls, [[PARAMETERS.repository, PARAMETERS.pull_request]]);
    assert.deepEqual(mergeCalls, [[
      PARAMETERS.repository,
      PARAMETERS.pull_request,
      PARAMETERS.expected_head_sha,
      PARAMETERS.merge_method,
    ]]);
  } finally {
    await client.close();
    await rm(temp, { recursive: true, force: true });
  }
});

test("explicit object modes pass one detached payload to high-arity callbacks", async () => {
  const temp = await mkdtemp(resolve(tmpdir(), "mothership-owner-callback-mode-"));
  const getCalls = [];
  const mergeCalls = [];
  const client = makeClient(temp, {
    getPullRequestMode: "object",
    mergePullRequestMode: "object",
    getPullRequest: callbackFor("get", "object-high-arity", getCalls),
    mergePullRequest: callbackFor("merge", "object-high-arity", mergeCalls),
  });
  try {
    const result = await approveAndExecute(client);
    assert.equal(result.receipt.status, "SUCCESS");
    assert.deepEqual(getCalls, [[{
      repository: PARAMETERS.repository,
      pull_request: PARAMETERS.pull_request,
    }]]);
    assert.deepEqual(mergeCalls, [[{
      repository: PARAMETERS.repository,
      pull_request: PARAMETERS.pull_request,
      expected_head_sha: PARAMETERS.expected_head_sha,
      merge_method: PARAMETERS.merge_method,
    }]]);
  } finally {
    await client.close();
    await rm(temp, { recursive: true, force: true });
  }
});

test("independent captured modes survive later transport mode mutation", async () => {
  const cases = [
    { getMode: "object", getShape: "object-high-arity", mergeMode: "positional", mergeShape: "rest" },
    { getMode: "positional", getShape: "rest", mergeMode: "object", mergeShape: "object-high-arity" },
  ];
  for (const current of cases) {
    const temp = await mkdtemp(resolve(tmpdir(), "mothership-owner-callback-mode-"));
    const getCalls = [];
    const mergeCalls = [];
    const transport = {
      getPullRequestMode: current.getMode,
      mergePullRequestMode: current.mergeMode,
      getPullRequest: callbackFor("get", current.getShape, getCalls),
      mergePullRequest: callbackFor("merge", current.mergeShape, mergeCalls),
    };
    const client = makeClient(temp, { transport });
    try {
      transport.getPullRequestMode = "unexpected-after-construction";
      transport.mergePullRequestMode = null;
      const result = await approveAndExecute(client);
      assert.equal(result.receipt.status, "SUCCESS");
      assert.deepEqual(getCalls, [current.getMode === "object"
        ? [{ repository: PARAMETERS.repository, pull_request: PARAMETERS.pull_request }]
        : [PARAMETERS.repository, PARAMETERS.pull_request]]);
      assert.deepEqual(mergeCalls, [current.mergeMode === "object"
        ? [{
            repository: PARAMETERS.repository,
            pull_request: PARAMETERS.pull_request,
            expected_head_sha: PARAMETERS.expected_head_sha,
            merge_method: PARAMETERS.merge_method,
          }]
        : [
            PARAMETERS.repository,
            PARAMETERS.pull_request,
            PARAMETERS.expected_head_sha,
            PARAMETERS.merge_method,
          ]]);
    } finally {
      await client.close();
      await rm(temp, { recursive: true, force: true });
    }
  }
});

for (const constructor of ["object", "positional"]) {
  for (const aliases of ["camel", "snake"]) {
    test(`${constructor} constructor preserves ${aliases} callback aliases`, async () => {
      const temp = await mkdtemp(resolve(tmpdir(), "mothership-owner-callback-mode-"));
      const getCalls = [];
      const mergeCalls = [];
      const client = makeClient(temp, {
        constructor,
        aliases,
        getPullRequestMode: "object",
        mergePullRequestMode: "positional",
        getPullRequest: callbackFor("get", "object-high-arity", getCalls),
        mergePullRequest: callbackFor("merge", "trailing-default", mergeCalls),
      });
      try {
        const result = await approveAndExecute(client);
        assert.equal(result.receipt.status, "SUCCESS");
        assert.deepEqual(getCalls, [[{
          repository: PARAMETERS.repository,
          pull_request: PARAMETERS.pull_request,
        }]]);
        assert.deepEqual(mergeCalls, [[
          PARAMETERS.repository,
          PARAMETERS.pull_request,
          PARAMETERS.expected_head_sha,
          PARAMETERS.merge_method,
        ]]);
      } finally {
        await client.close();
        await rm(temp, { recursive: true, force: true });
      }
    });
  }
}

for (const failure of ["sync", "async"]) {
  test(`GET ${failure} callback failure is one sanitized transport error`, async () => {
    const temp = await mkdtemp(resolve(tmpdir(), "mothership-owner-callback-mode-"));
    const getCalls = [];
    const client = makeClient(temp, {
      getPullRequestMode: "positional",
      mergePullRequestMode: "positional",
      getPullRequest: callbackFor("get", "rest", getCalls, failure),
    });
    try {
      await assert.rejects(() => approveAndExecute(client), (error) => (
        error instanceof OwnerClientError && error.code === "session"
      ));
      assert.equal(getCalls.length, 1);
    } finally {
      await client.close();
      await rm(temp, { recursive: true, force: true });
    }
  });

  test(`merge ${failure} callback failure is one UNKNOWN attempt`, async () => {
    const temp = await mkdtemp(resolve(tmpdir(), "mothership-owner-callback-mode-"));
    const mergeCalls = [];
    const client = makeClient(temp, {
      getPullRequestMode: "positional",
      mergePullRequestMode: "positional",
      mergePullRequest: callbackFor("merge", "rest", mergeCalls, failure),
    });
    try {
      const result = await approveAndExecute(client);
      assert.equal(result.receipt.status, "UNKNOWN");
      assert.equal(mergeCalls.length, 1);
      assert.equal(result.attempt_finished.outcome, "reconciliation_required");
    } finally {
      await client.close();
      await rm(temp, { recursive: true, force: true });
    }
  });
}

test("argument-ignoring wrappers continue to work with positional defaults", async () => {
  const temp = await mkdtemp(resolve(tmpdir(), "mothership-owner-callback-mode-"));
  const getCalls = [];
  const mergeCalls = [];
  const client = makeClient(temp, {
    omitModes: true,
    getPullRequest: function() { getCalls.push([...arguments]); return Promise.resolve(getResult()); },
    mergePullRequest: function() { mergeCalls.push([...arguments]); return Promise.resolve(mergeResult()); },
  });
  try {
    const result = await approveAndExecute(client);
    assert.equal(result.receipt.status, "SUCCESS");
    assert.equal(getCalls.length, 1);
    assert.equal(mergeCalls.length, 1);
  } finally {
    await client.close();
    await rm(temp, { recursive: true, force: true });
  }
});

for (const constructor of ["object", "positional"]) {
  for (const key of ["getPullRequestMode", "mergePullRequestMode"]) {
    for (const invalid of [null, "auto", "", 0, false, {}, [], () => "object", Symbol("object")]) {
      test(`${constructor} constructor rejects ${key}=${String(invalid)} before spawning`, async () => {
        const temp = await mkdtemp(resolve(tmpdir(), "mothership-owner-callback-mode-"));
        let client;
        try {
          assert.throws(() => {
            client = makeClient(temp, {
              constructor,
              [key]: invalid,
            });
          }, (error) => error instanceof OwnerClientError && error.code === "parameters");
          assert.deepEqual(await readdir(temp), []);
        } finally {
          await client?.close();
          await rm(temp, { recursive: true, force: true });
        }
      });
    }
  }
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

test("asynchronous stdin EPIPE rejects execution and leaves no live child", async () => {
  const temp = await mkdtemp(resolve(tmpdir(), "mothership-owner-node-"));
  let getCalls = 0;
  let mergeCalls = 0;
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
    mergePullRequest: async () => {
      mergeCalls += 1;
      return { http_status: 200, merged: true, merge_commit_sha: "b".repeat(40) };
    },
  });
  const stdin = client._child.stdin;
  const originalWrite = stdin._write;
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
    stdin._write = (_chunk, _encoding, callback) => {
      setImmediate(() => {
        const error = new Error("synthetic EPIPE");
        error.code = "EPIPE";
        callback(error);
      });
    };
    await assertRejectsWithoutStall(client.execute(PARAMETERS), ["eof"]);
    await client._cleanupPromise;
    assert.equal(client.phase, "unresolved");
    assert.equal(client.exited, true);
    assert.equal(client.cleanedUp, true);
    assert.equal(getCalls, 0);
    assert.equal(mergeCalls, 0);
    await assert.rejects(() => client.execute(PARAMETERS), (error) => (
      error instanceof OwnerClientError && error.code === "phase"
    ));
  } finally {
    stdin._write = originalWrite;
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
