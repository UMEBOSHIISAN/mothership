import assert from "node:assert/strict";
import { chmod, mkdtemp, readFile, readdir, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { delimiter, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
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
const execFileAsync = promisify(execFile);

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
    ...(Object.hasOwn(options, "sessionDiagnostics") ? { sessionDiagnostics: options.sessionDiagnostics } : {}),
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

const PREFLIGHT_DIAGNOSTIC = {
  code: "preflight_transport_failed", phase: "preflight_transport",
  authority_use: "unknown", external_effect: "unknown",
  next_check: "authority_and_attempt_records", retry_allowed: false,
};

test("real child diagnostic is opt-in and detached after one failed GET", async () => {
  for (const enabled of [false, true]) {
    const temp = await mkdtemp(resolve(tmpdir(), "mothership-diagnostic-"));
    let gets = 0;
    let puts = 0;
    const client = makeClient(temp, {
      sessionDiagnostics: enabled,
      getPullRequest: async () => { gets++; throw new Error("secret-token /synthetic/callback"); },
      mergePullRequest: async () => { puts++; return mergeResult(); },
    });
    try {
      await assert.rejects(() => approveAndExecute(client), (error) => {
        assert.ok(error instanceof OwnerClientError);
        assert.equal(error.code, "session");
        assert.deepEqual(error.diagnostic, enabled ? PREFLIGHT_DIAGNOSTIC : null);
        if (enabled) {
          const detached = error.diagnostic;
          detached.phase = "changed";
          assert.deepEqual(error.diagnostic, PREFLIGHT_DIAGNOSTIC);
        }
        assert.doesNotMatch(JSON.stringify(error), /secret-token|synthetic\/callback/);
        return true;
      });
      await assert.rejects(() => client.execute(PARAMETERS));
      assert.equal(gets, 1);
      assert.equal(puts, 0);
      assert.equal((await readdir(temp)).includes("attempts.jsonl"), false);
    } finally {
      await client.close();
      await rm(temp, { recursive: true, force: true });
    }
  }
});

test("real child diagnostic keeps context drift scoped before companion", async () => {
  const temp = await mkdtemp(resolve(tmpdir(), "mothership-diagnostic-context-"));
  let gets = 0;
  let puts = 0;
  const current = structuredClone(CONTEXT);
  const client = new MergeOwnerClient({
    pythonExecutable: PYTHON, sessionDiagnostics: true,
    authorityPath: resolve(temp, "authority.jsonl"), attemptsPath: resolve(temp, "attempts.jsonl"),
    contextProvider: async () => structuredClone(current),
    transport: {
      getPullRequest: async () => { gets++; return getResult(); },
      mergePullRequest: async () => { puts++; return mergeResult(); },
    },
  });
  try {
    const request = await client.prepare(PARAMETERS, EXECUTOR_REF);
    current.actor_id = "private-changed-actor";
    await assert.rejects(() => client.review({
      schema_version: "authority-action-review-response.v0", decision: "approve",
      request_id: request.request_id, request_sha256: request.request_sha256,
      action_id: request.action.action_id, action_sha256: request.action_sha256,
    }), (error) => {
      assert.deepEqual(error.diagnostic, {
        code: "review_validation_failed", phase: "review_validation",
        authority_use: "not_attempted BY THIS CALL", external_effect: "not_attempted BY THIS CALL",
        next_check: "review_request", retry_allowed: false,
      });
      assert.doesNotMatch(JSON.stringify(error), /private-changed-actor/);
      return true;
    });
    assert.equal(gets, 0);
    assert.equal(puts, 0);
    assert.deepEqual(await readdir(temp), []);
  } finally {
    await client.close();
    await rm(temp, { recursive: true, force: true });
  }
});

test("real child diagnostic preserves missing finish after one synthetic merge", async () => {
  const temp = await mkdtemp(resolve(tmpdir(), "mothership-diagnostic-finish-"));
  const attempts = resolve(temp, "attempts.jsonl");
  let puts = 0;
  let startedBytes;
  const client = makeClient(temp, {
    sessionDiagnostics: true,
    mergePullRequest: async () => {
      puts++;
      startedBytes = await readFile(attempts, "utf8");
      await chmod(attempts, 0o400);
      return mergeResult();
    },
  });
  try {
    await assert.rejects(() => approveAndExecute(client), (error) => {
      assert.deepEqual(error.diagnostic, {
        code: "mutation_returned_failed", phase: "mutation_returned",
        authority_use: "unknown", external_effect: "unknown",
        next_check: "authority_and_attempt_records", retry_allowed: false,
      });
      return true;
    });
    assert.equal(puts, 1);
    assert.equal(await readFile(attempts, "utf8"), startedBytes);
    assert.equal(startedBytes.trim().split("\n").length, 1);
    assert.equal(JSON.parse(startedBytes.trim()).event_type, "attempt_started");
    const authorityBytes = await readFile(resolve(temp, "authority.jsonl"), "utf8");
    assert.equal(authorityBytes.trim().split("\n").map(JSON.parse)
      .filter((row) => row.event_type === "authority_action_consume").length, 1);
    await assert.rejects(() => client.execute(PARAMETERS));
    assert.equal(puts, 1);
    assert.equal(await readFile(attempts, "utf8"), startedBytes);
    assert.equal(await readFile(resolve(temp, "authority.jsonl"), "utf8"), authorityBytes);
  } finally {
    await client.close();
    await chmod(attempts, 0o600).catch(() => {});
    await rm(temp, { recursive: true, force: true });
  }
});

const BAD_DIAGNOSTICS = [
  { ...PREFLIGHT_DIAGNOSTIC, token: "secret" },
  { ...PREFLIGHT_DIAGNOSTIC, phase: "success" },
  { ...PREFLIGHT_DIAGNOSTIC, retry_allowed: true },
  { ...PREFLIGHT_DIAGNOSTIC, retry_allowed: 0 },
  { ...PREFLIGHT_DIAGNOSTIC, code: "review_validation_failed" },
  { ...PREFLIGHT_DIAGNOSTIC, next_check: "review_request" },
  { ...PREFLIGHT_DIAGNOSTIC, authority_use: "not_attempted BY THIS CALL" },
  { ...PREFLIGHT_DIAGNOSTIC, external_effect: "SUCCESS" },
  null, [], "secret",
  Object.fromEntries(Object.entries(PREFLIGHT_DIAGNOSTIC).filter(([key]) => key !== "phase")),
];

for (const [index, invalid] of BAD_DIAGNOSTICS.entries()) {
  test(`diagnostic malformed tuple ${index} rejects without caller observation`, async () => {
    const temp = await mkdtemp(resolve(tmpdir(), "mothership-diagnostic-invalid-"));
    const client = makeClient(temp, { sessionDiagnostics: true });
    try {
      const pending = installPending(client, "execute");
      const frame = { ...resultFrame(client, pending, { code: "session", diagnostic: invalid }),
        schema_version: "mothership-owner.v1", type: "error" };
      client._onData(Buffer.from(`${JSON.stringify(frame)}\n`));
      await assert.rejects(pending.promise, (error) => {
        assert.equal(error.code, "protocol");
        assert.equal(error.diagnostic, null);
        return true;
      });
    } finally {
      await client.close();
      await rm(temp, { recursive: true, force: true });
    }
  });
}

for (const [field, changed, code] of [
  ["schema_version", "mothership-owner.v0", "nonce"],
  ["owner_id", "another-owner", "nonce"],
  ["seq", 2, "sequence"],
  ["reply_to", 2, "reply"],
  ["request_id", "another-request", "protocol"],
  ["action_id", "another-action", "protocol"],
]) {
  test(`diagnostic foreign ${field} never reaches pending call`, async () => {
    const temp = await mkdtemp(resolve(tmpdir(), "mothership-diagnostic-foreign-"));
    const client = makeClient(temp, { sessionDiagnostics: true });
    try {
      client._requestId = "expected-request";
      client._actionId = "expected-action";
      const pending = installPending(client, "execute");
      const frame = { ...resultFrame(client, pending, { code: "session", diagnostic: PREFLIGHT_DIAGNOSTIC }),
        schema_version: "mothership-owner.v1", type: "error", [field]: changed };
      client._onData(Buffer.from(`${JSON.stringify(frame)}\n`));
      await assert.rejects(pending.promise, (error) => {
        assert.equal(error.code, code);
        assert.equal(error.diagnostic, null);
        return true;
      });
    } finally {
      await client.close();
      await rm(temp, { recursive: true, force: true });
    }
  });
}

test("terminal diagnostic example explains three stopped calls without live effects", async () => {
  for (const [mode, phase, gets, merges] of [
    ["review", "review_validation", 0, 0],
    ["preflight", "preflight_transport", 1, 0],
    ["finish", "mutation_returned", 1, 1],
  ]) {
    const { stdout, stderr } = await execFileAsync(process.execPath,
      [resolve(ROOT, "examples/owner_diagnostic_terminal.mjs"), mode],
      { cwd: ROOT, env: { ...process.env, PYTHON_EXECUTABLE: PYTHON } });
    assert.equal(stderr, "");
    assert.match(stdout, /synthetic local example; no network or live GitHub operation/);
    assert.ok(stdout.includes(`last observed phase: ${phase}\n`));
    assert.ok(stdout.includes(`callbacks: GET=${gets}, merge=${merges} (synthetic only)\n`));
    assert.match(stdout, /next read-only check: existing /);
    assert.match(stdout, /recovery: no re-execution; no reconsume/);
    assert.doesNotMatch(stdout, /private-callback|Traceback|\/private\/|SUCCESS/);
    if (mode !== "review") assert.match(stdout, /external effect: unknown/);
  }
});

test("diagnostic opt-in keeps successful results and one-use behavior", async () => {
  const temp = await mkdtemp(resolve(tmpdir(), "mothership-diagnostic-success-"));
  let puts = 0;
  const client = makeClient(temp, { sessionDiagnostics: true,
    mergePullRequest: async () => { puts++; return mergeResult(); } });
  try {
    const result = await approveAndExecute(client);
    assert.equal(result.receipt.status, "SUCCESS");
    assert.equal(result.verification, null);
    assert.equal(puts, 1);
    await assert.rejects(() => client.execute(PARAMETERS));
    assert.equal(puts, 1);
  } finally {
    await client.close();
    await rm(temp, { recursive: true, force: true });
  }
});

test("diagnostic opt-in native pipe loss has no invented Python observation", async () => {
  const temp = await mkdtemp(resolve(tmpdir(), "mothership-diagnostic-loss-"));
  let puts = 0;
  let client;
  client = makeClient(temp, { sessionDiagnostics: true,
    getPullRequest: async () => {
      client._child.stdin.emit("error", new Error("secret-pipe-error"));
      return getResult();
    },
    mergePullRequest: async () => { puts++; return mergeResult(); },
  });
  try {
    await assert.rejects(() => approveAndExecute(client), (error) => {
      assert.equal(error.code, "eof");
      assert.equal(error.diagnostic, null);
      assert.doesNotMatch(JSON.stringify(error), /secret-pipe-error/);
      return true;
    });
    await assert.rejects(() => client.execute(PARAMETERS));
    assert.equal(puts, 0);
  } finally {
    await client.close();
    await rm(temp, { recursive: true, force: true });
  }
});

test("diagnostic mode validates options and code-only compatibility", async () => {
  const temp = await mkdtemp(resolve(tmpdir(), "mothership-diagnostic-compat-"));
  try {
    for (const value of [null, 0, "true", {}, []]) {
      let created;
      try {
        assert.throws(() => { created = makeClient(temp, { sessionDiagnostics: value }); },
          (error) => error.code === "parameters" && error.diagnostic === null);
      } finally { if (created !== undefined) await created.close(); }
    }
    for (const [enabled, code, payload, want] of [
      [true, "phase", {}, "phase"],
      [true, "phase", { diagnostic: PREFLIGHT_DIAGNOSTIC }, "protocol"],
      [false, "session", { diagnostic: PREFLIGHT_DIAGNOSTIC }, "protocol"],
    ]) {
      const client = makeClient(temp, { sessionDiagnostics: enabled });
      try {
        const pending = installPending(client, "execute");
        const frame = { ...resultFrame(client, pending, { code, ...payload }), type: "error",
          schema_version: enabled ? "mothership-owner.v1" : "mothership-owner.v0" };
        client._onData(Buffer.from(`${JSON.stringify(frame)}\n`));
        await assert.rejects(pending.promise, (error) => {
          assert.equal(error.code, want);
          assert.equal(error.diagnostic, null);
          return true;
        });
      } finally { await client.close(); }
    }
  } finally { await rm(temp, { recursive: true, force: true }); }
});

test("diagnostic parser accepts the finite Session phase tuples", async () => {
  const early = "not_attempted BY THIS CALL";
  const rows = [
    ["unknown", "unknown", "existing_evidence_bundle"],
    ["review_validation", early, "review_request"],
    ["decision_record", early, "authority_records"],
    ["execution_validation", early, "review_request_and_existing_records"],
    ["companion_execution", "unknown", "authority_and_attempt_records"],
    ["preflight_transport", "unknown", "authority_and_attempt_records"],
    ["preflight_returned", "unknown", "authority_and_attempt_records"],
    ["mutation_guard", "unknown", "authority_and_attempt_records"],
    ["mutation_transport", "unknown", "authority_and_attempt_records"],
    ["mutation_returned", "unknown", "authority_and_attempt_records"],
    ["receipt_build", "unknown", "existing_evidence_bundle"],
    ["result_export", "unknown", "existing_evidence_bundle"],
  ];
  const temp = await mkdtemp(resolve(tmpdir(), "mothership-diagnostic-phases-"));
  try {
    for (const [phase, effect, nextCheck] of rows) {
      const client = makeClient(temp, { sessionDiagnostics: true });
      try {
        const diagnostic = { code: phase === "unknown" ? "unknown" : `${phase}_failed`, phase,
          authority_use: effect, external_effect: effect, next_check: nextCheck, retry_allowed: false };
        const pending = installPending(client, "execute");
        const frame = { ...resultFrame(client, pending, { code: "session", diagnostic }),
          schema_version: "mothership-owner.v1", type: "error" };
        client._onData(Buffer.from(`${JSON.stringify(frame)}\n`));
        await assert.rejects(pending.promise, (error) => {
          assert.deepEqual(error.diagnostic, diagnostic);
          return true;
        });
      } finally { await client.close(); }
    }
  } finally { await rm(temp, { recursive: true, force: true }); }
});

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
