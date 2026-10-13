import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { TextDecoder } from "node:util";

const SCHEMA_VERSION = "mothership-owner.v0";
const MAX_FRAME_BYTES = 65_536;
const MAX_DEPTH = 16;
const MAX_NODES = 2_048;
const MAX_CONTAINER = 256;
const MAX_STRING_BYTES = 16_384;
const STOP_DEADLINE_MS = 30_000;
const FRAME_KEYS = new Set([
  "schema_version", "type", "seq", "reply_to", "owner_id", "request_id", "action_id", "payload",
]);
const TYPES = new Set([
  "prepare", "review", "execute", "cancel", "context", "get", "merge", "result", "error",
]);
const CALLBACK_TYPES = new Set(["context", "get", "merge"]);
const COMMAND_TYPES = new Set(["prepare", "review", "execute", "cancel"]);
const ERROR_CODES = new Set([
  "closed", "context", "eof", "internal", "malformed", "nonce", "oversized", "parameters",
  "parent_lost", "phase", "protocol", "reply", "sequence", "session", "transport",
]);

const decoder = new TextDecoder("utf-8", { fatal: true });

export class OwnerClientError extends Error {
  constructor(code) {
    const safeCode = ERROR_CODES.has(code) ? code : "internal";
    super(`owner ${safeCode}`);
    this.name = "OwnerClientError";
    this.code = safeCode;
  }
}

function fail(code) {
  throw new OwnerClientError(code);
}

function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    && Object.getPrototypeOf(value) === Object.prototype;
}

function checkBounds(value) {
  const stack = [[value, 1]];
  let nodes = 0;
  while (stack.length) {
    const [current, depth] = stack.pop();
    nodes += 1;
    if (nodes > MAX_NODES || depth > MAX_DEPTH) fail("oversized");
    if (typeof current === "string") {
      if (Buffer.byteLength(current, "utf8") > MAX_STRING_BYTES) fail("oversized");
      continue;
    }
    if (current === null || typeof current === "boolean") continue;
    if (typeof current === "number") {
      if (!Number.isFinite(current)) fail("malformed");
      continue;
    }
    if (Array.isArray(current)) {
      if (current.length > MAX_CONTAINER) fail("oversized");
      for (const child of current) stack.push([child, depth + 1]);
      continue;
    }
    if (!isPlainObject(current)) fail("malformed");
    const entries = Object.entries(current);
    if (entries.length > MAX_CONTAINER) fail("oversized");
    for (const [key, child] of entries) {
      if (Buffer.byteLength(key, "utf8") > MAX_STRING_BYTES) fail("oversized");
      stack.push([child, depth + 1]);
    }
  }
}

function detach(value) {
  checkBounds(value);
  let encoded;
  try {
    encoded = JSON.stringify(value);
    if (encoded === undefined) fail("malformed");
    return JSON.parse(encoded);
  } catch (error) {
    if (error instanceof OwnerClientError) throw error;
    fail("malformed");
  }
}

function canonical(value) {
  checkBounds(value);
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(",")}}`;
}

function exactObject(value, keys) {
  if (!isPlainObject(value) || Object.keys(value).length !== keys.length
      || !keys.every((key) => Object.prototype.hasOwnProperty.call(value, key))) fail("protocol");
  return value;
}

function idValue(value, nullable = true) {
  if (value === null && nullable) return null;
  if (typeof value !== "string" || value.length === 0 || value.includes("\n") || value.includes("\r")) fail("protocol");
  return value;
}

function parametersValue(value) {
  const data = exactObject(value, ["repository", "pull_request", "expected_head_sha", "expected_base", "merge_method"]);
  if (typeof data.repository !== "string" || !/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(data.repository)
      || !Number.isSafeInteger(data.pull_request) || data.pull_request <= 0
      || typeof data.expected_head_sha !== "string" || !/^[0-9a-f]{40}$/.test(data.expected_head_sha)
      || typeof data.expected_base !== "string" || data.expected_base.length === 0
      || typeof data.merge_method !== "string" || !["merge", "squash", "rebase"].includes(data.merge_method)) {
    fail("parameters");
  }
  return data;
}

function executorRefValue(value) {
  const data = exactObject(value, ["ref_id", "sha256"]);
  if (typeof data.ref_id !== "string" || data.ref_id.length < 1 || data.ref_id.length > 256
      || !/^[A-Za-z0-9][A-Za-z0-9._:-]*$/.test(data.ref_id)
      || typeof data.sha256 !== "string" || !/^[0-9a-f]{64}$/.test(data.sha256)) fail("parameters");
  return data;
}

function callbackPayload(type, payload) {
  if (type === "context") {
    if (!isPlainObject(payload) || Object.keys(payload).length !== 0) fail("protocol");
    return payload;
  }
  if (type === "get") {
    const value = exactObject(payload, ["repository", "pull_request"]);
    if (typeof value.repository !== "string" || !Number.isSafeInteger(value.pull_request)) fail("parameters");
    return value;
  }
  const value = exactObject(payload, ["repository", "pull_request", "expected_head_sha", "merge_method"]);
  if (typeof value.repository !== "string" || !Number.isSafeInteger(value.pull_request)
      || typeof value.expected_head_sha !== "string" || typeof value.merge_method !== "string") fail("parameters");
  return value;
}

function assertRetainedCallbackParameters(type, value, retained) {
  if (!isPlainObject(retained)) fail("phase");
  const expected = type === "get"
    ? { repository: retained.repository, pull_request: retained.pull_request }
    : {
      repository: retained.repository,
      pull_request: retained.pull_request,
      expected_head_sha: retained.expected_head_sha,
      merge_method: retained.merge_method,
    };
  if (canonical(value) !== canonical(expected)) fail("parameters");
}

function contextValue(value) {
  const data = exactObject(value, ["host_id", "session_id", "actor_id", "runtime_generation", "scope"]);
  for (const key of ["host_id", "session_id", "actor_id", "runtime_generation"]) {
    if (typeof data[key] !== "string" || !/^[A-Za-z0-9][A-Za-z0-9._:-]*$/.test(data[key])
        || data[key].length > 128) fail("context");
  }
  if (!Array.isArray(data.scope) || data.scope.length > 64
      || new Set(data.scope).size !== data.scope.length
      || data.scope.some((item) => typeof item !== "string" || item.length === 0 || item.length > 128
        || !/^[a-z][a-z0-9_.:-]*$/.test(item))) fail("context");
  return data;
}

function getResultValue(value) {
  const data = exactObject(value, ["http_status", "state", "merged", "head_sha", "base_ref"]);
  if (!Number.isSafeInteger(data.http_status) || typeof data.state !== "string"
      || typeof data.merged !== "boolean" || typeof data.head_sha !== "string"
      || typeof data.base_ref !== "string") fail("transport");
  return data;
}

function mergeResultValue(value) {
  if (!isPlainObject(value)) fail("transport");
  const allowed = new Set(["http_status", "status_code", "merged", "merge_commit_sha", "sha", "ambiguous", "redirect_rejected"]);
  if (Object.keys(value).some((key) => !allowed.has(key))) fail("transport");
  if (value.http_status !== undefined && !Number.isSafeInteger(value.http_status)) fail("transport");
  if (value.status_code !== undefined && !Number.isSafeInteger(value.status_code)) fail("transport");
  if (value.merged !== undefined && typeof value.merged !== "boolean") fail("transport");
  for (const key of ["merge_commit_sha", "sha"]) {
    if (value[key] !== undefined && typeof value[key] !== "string") fail("transport");
  }
  for (const key of ["ambiguous", "redirect_rejected"]) {
    if (value[key] !== undefined && typeof value[key] !== "boolean") fail("transport");
  }
  return value;
}

function parseJsonWithDuplicateCheck(raw) {
  let index = 0;
  let nodes = 0;
  const text = raw.endsWith("\n") ? raw.slice(0, -1) : raw;
  const whitespace = () => {
    while (index < text.length && " \t\r\n".includes(text[index])) index += 1;
  };
  const parseString = () => {
    if (text[index] !== '"') fail("malformed");
    const start = index;
    index += 1;
    while (index < text.length) {
      const code = text.charCodeAt(index);
      if (code === 0x22) {
        index += 1;
        try {
          return JSON.parse(text.slice(start, index));
        } catch {
          fail("malformed");
        }
      }
      if (code < 0x20) fail("malformed");
      if (code === 0x5c) {
        index += 1;
        if (index >= text.length) fail("malformed");
        if (text[index] === "u") index += 4;
      }
      index += 1;
    }
    fail("malformed");
  };
  const parseValue = (depth) => {
    nodes += 1;
    if (nodes > MAX_NODES || depth > MAX_DEPTH) fail("oversized");
    whitespace();
    const char = text[index];
    if (char === "{") {
      index += 1;
      whitespace();
      const keys = new Set();
      let count = 0;
      if (text[index] === "}") {
        index += 1;
        return;
      }
      while (index < text.length) {
        const key = parseString();
        if (keys.has(key)) fail("malformed");
        keys.add(key);
        count += 1;
        if (count > MAX_CONTAINER) fail("oversized");
        whitespace();
        if (text[index++] !== ":") fail("malformed");
        parseValue(depth + 1);
        whitespace();
        if (text[index] === "}") {
          index += 1;
          return;
        }
        if (text[index++] !== ",") fail("malformed");
        whitespace();
      }
      fail("malformed");
    }
    if (char === "[") {
      index += 1;
      whitespace();
      let count = 0;
      if (text[index] === "]") {
        index += 1;
        return;
      }
      while (index < text.length) {
        count += 1;
        if (count > MAX_CONTAINER) fail("oversized");
        parseValue(depth + 1);
        whitespace();
        if (text[index] === "]") {
          index += 1;
          return;
        }
        if (text[index++] !== ",") fail("malformed");
        whitespace();
      }
      fail("malformed");
    }
    if (char === '"') {
      parseString();
      return;
    }
    if (text.startsWith("true", index)) {
      index += 4;
      return;
    }
    if (text.startsWith("false", index)) {
      index += 5;
      return;
    }
    if (text.startsWith("null", index)) {
      index += 4;
      return;
    }
    const number = text.slice(index).match(/^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/);
    if (number) {
      index += number[0].length;
      return;
    }
    fail("malformed");
  };
  parseValue(1);
  whitespace();
  if (index !== text.length) fail("malformed");
  try {
    return JSON.parse(text);
  } catch {
    fail("malformed");
  }
}

function parseFrame(buffer, ownerId) {
  if (buffer.length > MAX_FRAME_BYTES || buffer[buffer.length - 1] !== 0x0a) fail("oversized");
  let raw;
  try {
    raw = decoder.decode(buffer);
  } catch {
    fail("malformed");
  }
  const value = parseJsonWithDuplicateCheck(raw);
  checkBounds(value);
  if (!isPlainObject(value) || Object.keys(value).length !== FRAME_KEYS.size
      || !Object.keys(value).every((key) => FRAME_KEYS.has(key))) fail("protocol");
  if (value.schema_version !== SCHEMA_VERSION || value.owner_id !== ownerId) fail("nonce");
  if (typeof value.type !== "string" || !TYPES.has(value.type)) fail("protocol");
  if (!Number.isSafeInteger(value.seq) || value.seq <= 0) fail("sequence");
  if (value.reply_to !== null && (!Number.isSafeInteger(value.reply_to) || value.reply_to <= 0)) fail("reply");
  idValue(value.request_id);
  idValue(value.action_id);
  if (value.type === "prepare") {
    if (value.reply_to !== null || value.request_id !== null || value.action_id !== null) fail("protocol");
    const data = exactObject(value.payload, ["parameters", "executor_ref"]);
    parametersValue(data.parameters);
    executorRefValue(data.executor_ref);
  } else if (value.type === "review") {
    if (value.reply_to !== null) fail("protocol");
    const response = exactObject(value.payload, ["schema_version", "decision", "request_id", "request_sha256", "action_id", "action_sha256"]);
    if (response.schema_version !== "authority-action-review-response.v0"
        || !["approve", "reject"].includes(response.decision)
        || typeof response.request_id !== "string" || typeof response.request_sha256 !== "string"
        || typeof response.action_id !== "string" || typeof response.action_sha256 !== "string") fail("parameters");
  } else if (value.type === "execute") {
    if (value.reply_to !== null) fail("protocol");
    parametersValue(value.payload);
  } else if (value.type === "cancel") {
    if (value.reply_to !== null || !isPlainObject(value.payload) || Object.keys(value.payload).length !== 0) fail("protocol");
  } else if (CALLBACK_TYPES.has(value.type)) {
    if (value.reply_to !== null) fail("protocol");
    callbackPayload(value.type, value.payload);
  } else if (value.type === "result") {
    if (value.reply_to === null) fail("reply");
  } else if (value.type === "error") {
    if (value.reply_to === null) fail("reply");
    const data = exactObject(value.payload, ["code"]);
    if (typeof data.code !== "string" || !ERROR_CODES.has(data.code)) fail("protocol");
  }
  return value;
}

function frameBytes(frame) {
  checkBounds(frame.payload);
  let raw;
  try {
    raw = `${JSON.stringify(frame)}\n`;
  } catch {
    fail("malformed");
  }
  const bytes = Buffer.from(raw, "utf8");
  if (bytes.length > MAX_FRAME_BYTES) fail("oversized");
  return bytes;
}

export class MergeOwnerClient {
  constructor(options = {}, authorityPath, attemptsPath, contextProvider, transport) {
    const config = isPlainObject(options)
      ? options
      : { pythonExecutable: options, authorityPath, attemptsPath, contextProvider, transport };
    const { pythonExecutable, authorityPath: authority, attemptsPath: attempts, contextProvider: context, transport: callbacks } = config;
    if (typeof pythonExecutable !== "string" || pythonExecutable.length === 0
        || typeof authority !== "string" || authority.length === 0
        || typeof attempts !== "string" || attempts.length === 0
        || authority === attempts || typeof context !== "function"
        || callbacks === null || typeof callbacks !== "object") fail("parameters");
    const getPullRequest = callbacks.getPullRequest ?? callbacks.get_pull_request;
    const mergePullRequest = callbacks.mergePullRequest ?? callbacks.merge_pull_request;
    if (typeof getPullRequest !== "function" || typeof mergePullRequest !== "function") fail("parameters");
    this._ownerId = randomUUID();
    this._pythonExecutable = pythonExecutable;
    this._authorityPath = authority;
    this._attemptsPath = attempts;
    this._contextProvider = context;
    this._getPullRequest = getPullRequest;
    this._mergePullRequest = mergePullRequest;
    this._parentSeq = 1;
    this._childSeq = 1;
    this._buffer = Buffer.alloc(0);
    this._pending = null;
    this._phase = "new";
    this._requestId = null;
    this._actionId = null;
    this._originalParameters = null;
    this._parameters = null;
    this._childPid = null;
    this._exitObserved = false;
    this._cleanupObserved = false;
    this._closed = false;
    this._handlingCallback = false;
    this._child = null;
    this._cleanupPromise = null;
    try {
      this._child = spawn(
        pythonExecutable,
        ["-m", "mothership_adapters.owner", "--owner-id", this._ownerId,
          "--parent-pid", String(process.pid), "--authority-path", authority, "--attempts-path", attempts],
        { shell: false, env: process.env, stdio: ["pipe", "pipe", "pipe"] },
      );
      this._childPid = this._child.pid ?? null;
      this._child.stdin.on("error", () => this._fatal("eof"));
      this._child.stdout.on("data", (chunk) => this._onData(chunk));
      this._child.stdout.on("error", () => this._childFailure("eof"));
      this._child.stderr.on("data", () => {});
      this._child.on("error", () => this._childFailure("eof"));
      this._child.on("exit", (code, signal) => {
        this._exitObserved = true;
        this._exitCode = code;
        this._exitSignal = signal;
      });
      this._child.on("close", () => {
        this._exitObserved = true;
        this._cleanupObserved = true;
        if (this._pending !== null) {
          const pending = this._pending;
          this._pending = null;
          clearTimeout(pending.timer);
          this._phase = pending.type === "execute" ? "unresolved" : "failed";
          pending.reject(new OwnerClientError(pending.type === "execute" ? "eof" : "closed"));
        }
      });
    } catch {
      this._phase = "failed";
      fail("closed");
    }
  }

  get ownerId() { return this._ownerId; }
  get childPid() { return this._childPid; }
  get pid() { return this._childPid; }
  get exited() { return this._exitObserved; }
  get cleanedUp() { return this._cleanupObserved; }
  get cleanupComplete() { return this._cleanupObserved; }
  get exitCode() { return this._exitCode ?? null; }
  get exitSignal() { return this._exitSignal ?? null; }
  get phase() { return this._phase; }

  _childFailure(code) {
    if (this._pending === null) return;
    const pending = this._pending;
    this._pending = null;
    clearTimeout(pending.timer);
    this._phase = pending.type === "execute" ? "unresolved" : "failed";
    pending.reject(new OwnerClientError(code));
  }

  _send(type, payload, requestId = this._requestId, actionId = this._actionId, replyTo = null) {
    if (this._closed || this._child === null || this._exitObserved || this._child.stdin.destroyed) fail("closed");
    const frame = {
      schema_version: SCHEMA_VERSION,
      type,
      seq: this._parentSeq,
      reply_to: replyTo,
      owner_id: this._ownerId,
      request_id: requestId,
      action_id: actionId,
      payload,
    };
    if (!COMMAND_TYPES.has(type) && type !== "result" && type !== "error") fail("protocol");
    if (type === "prepare") {
      if (requestId !== null || actionId !== null) fail("protocol");
      const data = exactObject(payload, ["parameters", "executor_ref"]);
      parametersValue(data.parameters);
      executorRefValue(data.executor_ref);
    } else if (type === "review") {
      const response = exactObject(payload, ["schema_version", "decision", "request_id", "request_sha256", "action_id", "action_sha256"]);
      if (response.schema_version !== "authority-action-review-response.v0"
          || !["approve", "reject"].includes(response.decision)
          || typeof response.request_id !== "string" || typeof response.request_sha256 !== "string"
          || typeof response.action_id !== "string" || typeof response.action_sha256 !== "string") fail("parameters");
    } else if (type === "execute") {
      parametersValue(payload);
    } else if (type === "cancel") {
      if (!isPlainObject(payload) || Object.keys(payload).length !== 0) fail("protocol");
    }
    const bytes = frameBytes(frame);
    try {
      this._child.stdin.write(bytes);
    } catch {
      fail("closed");
    }
    const seq = this._parentSeq;
    this._parentSeq += 1;
    return seq;
  }

  _command(type, payload) {
    if (this._pending !== null) return Promise.reject(new OwnerClientError("phase"));
    let seq;
    try {
      seq = this._send(type, payload, type === "prepare" ? null : this._requestId, type === "prepare" ? null : this._actionId);
    } catch (error) {
      return Promise.reject(error instanceof OwnerClientError ? error : new OwnerClientError("closed"));
    }
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        if (this._pending === null || this._pending.seq !== seq) return;
        this._pending = null;
        this._phase = type === "execute" ? "unresolved" : "failed";
        this._terminate();
        reject(new OwnerClientError("closed"));
      }, STOP_DEADLINE_MS);
      this._pending = { seq, type, resolve, reject, timer };
    });
  }

  _onData(chunk) {
    if (this._closed) return;
    this._buffer = Buffer.concat([this._buffer, Buffer.from(chunk)]);
    if (this._buffer.length > MAX_FRAME_BYTES && !this._buffer.includes(0x0a)) {
      this._fatal("oversized");
      return;
    }
    while (true) {
      const newline = this._buffer.indexOf(0x0a);
      if (newline < 0) {
        if (this._buffer.length > MAX_FRAME_BYTES) this._fatal("oversized");
        return;
      }
      const line = this._buffer.subarray(0, newline + 1);
      this._buffer = this._buffer.subarray(newline + 1);
      try {
        const frame = parseFrame(line, this._ownerId);
        if (frame.seq !== this._childSeq) fail("sequence");
        this._childSeq += 1;
        void this._handleFrame(frame).catch((error) => this._fatal(error.code ?? "protocol"));
      } catch (error) {
        this._fatal(error.code ?? "protocol");
        return;
      }
    }
  }

  async _handleFrame(frame) {
    if (CALLBACK_TYPES.has(frame.type)) {
      if (this._pending === null || this._handlingCallback) fail("phase");
      const pending = this._pending;
      if (!new Set(["prepare", "review", "execute"]).has(pending.type)
          || (pending.type !== "execute" && frame.type !== "context")) fail("protocol");
      const expectedRequest = pending.type === "prepare" ? null : this._requestId;
      const expectedAction = pending.type === "prepare" ? null : this._actionId;
      if (frame.request_id !== expectedRequest || frame.action_id !== expectedAction) fail("protocol");
      this._handlingCallback = true;
      try {
        let payload;
        if (frame.type === "context") {
          payload = contextValue(detach(await this._contextProvider()));
        } else if (frame.type === "get") {
          const value = detach(frame.payload);
          assertRetainedCallbackParameters(frame.type, value, this._parameters);
          const callback = this._getPullRequest;
          payload = callback.length >= 2
            ? await callback(value.repository, value.pull_request)
            : await callback(value);
          payload = getResultValue(detach(payload));
        } else {
          const callback = this._mergePullRequest;
          const value = detach(frame.payload);
          assertRetainedCallbackParameters(frame.type, value, this._parameters);
          payload = callback.length >= 4
            ? await callback(value.repository, value.pull_request, value.expected_head_sha, value.merge_method)
            : await callback(value);
          payload = mergeResultValue(detach(payload));
        }
        this._send("result", payload, frame.request_id, frame.action_id, frame.seq);
      } catch (error) {
        const code = error instanceof OwnerClientError
          ? error.code
          : frame.type === "context" ? "context" : "transport";
        try {
          this._send("error", { code }, frame.request_id, frame.action_id, frame.seq);
        } catch {
          this._fatal("closed");
        }
      } finally {
        this._handlingCallback = false;
      }
      return;
    }
    if (!new Set(["result", "error"]).has(frame.type) || this._pending === null) fail("reply");
    const pending = this._pending;
    if (frame.reply_to !== pending.seq) fail("reply");
    if (pending.type === "prepare") {
      if (frame.type === "result") {
        if (!isPlainObject(frame.payload) || typeof frame.payload.request_id !== "string"
            || !isPlainObject(frame.payload.action) || typeof frame.payload.action.action_id !== "string") fail("protocol");
        if (frame.request_id !== frame.payload.request_id || frame.action_id !== frame.payload.action.action_id) fail("protocol");
      } else if (frame.request_id !== null || frame.action_id !== null) fail("protocol");
    } else if (frame.request_id !== this._requestId || frame.action_id !== this._actionId) {
      fail("protocol");
    }
    if (frame.type === "error") {
      this._pending = null;
      clearTimeout(pending.timer);
      this._phase = pending.type === "execute" ? "failed" : "failed";
      pending.reject(new OwnerClientError(frame.payload.code));
      return;
    }
    const validatedPayload = detach(frame.payload);
    let prepareRequest = null;
    let prepareAction = null;
    if (pending.type === "prepare") {
      if (!isPlainObject(validatedPayload) || typeof validatedPayload.request_id !== "string"
          || !isPlainObject(validatedPayload.action) || typeof validatedPayload.action.action_id !== "string") fail("protocol");
      const executionParameters = parametersValue(detach(validatedPayload.action.execution_parameters));
      if (this._originalParameters === null
          || canonical(executionParameters) !== canonical(this._originalParameters)) fail("parameters");
      prepareRequest = validatedPayload.request_id;
      prepareAction = validatedPayload.action.action_id;
      this._parameters = executionParameters;
    } else if (pending.type === "review") {
      if (validatedPayload !== "approve" && validatedPayload !== "reject") fail("protocol");
    } else if (pending.type === "execute") {
      if (!isPlainObject(validatedPayload)) fail("protocol");
    } else if (pending.type === "cancel") {
      if (validatedPayload !== null) fail("protocol");
    }
    this._pending = null;
    clearTimeout(pending.timer);
    if (pending.type === "prepare") {
      this._requestId = prepareRequest;
      this._actionId = prepareAction;
      this._phase = "prepared";
    } else if (pending.type === "review") {
      this._phase = validatedPayload === "approve" ? "approved" : "rejected";
    } else if (pending.type === "execute") {
      this._phase = "finished";
    } else if (pending.type === "cancel") {
      this._phase = "canceled";
    }
    pending.resolve(validatedPayload);
  }

  _fatal(code) {
    const safeCode = ERROR_CODES.has(code) ? code : "protocol";
    if (this._pending !== null) {
      const pending = this._pending;
      this._pending = null;
      clearTimeout(pending.timer);
      this._phase = pending.type === "execute" ? "unresolved" : "failed";
      pending.reject(new OwnerClientError(safeCode));
    }
    void this._terminate();
  }

  async _terminate() {
    if (this._cleanupPromise !== null) return this._cleanupPromise;
    this._cleanupPromise = this._terminateOnce();
    return this._cleanupPromise;
  }

  async _terminateOnce() {
    if (this._child === null || this._exitObserved) {
      this._cleanupObserved = this._exitObserved;
      return;
    }
    try { this._child.kill("SIGTERM"); } catch {}
    await new Promise((resolve) => setTimeout(resolve, 250));
    if (!this._exitObserved) {
      try { this._child.kill("SIGKILL"); } catch {}
    }
    await new Promise((resolve) => {
      if (this._exitObserved) resolve();
      else this._child.once("close", resolve);
    });
    this._cleanupObserved = true;
  }

  async prepare(parameters, executorRef) {
    if (this._phase !== "new") return Promise.reject(new OwnerClientError("phase"));
    const retainedParameters = parametersValue(detach(parameters));
    const retainedRef = executorRefValue(detach(executorRef));
    this._originalParameters = retainedParameters;
    const result = await this._command("prepare", { parameters: retainedParameters, executor_ref: retainedRef });
    if (!isPlainObject(result)) fail("protocol");
    return detach(result);
  }

  async review(response) {
    if (this._phase !== "prepared") return Promise.reject(new OwnerClientError("phase"));
    const result = await this._command("review", detach(response));
    return result;
  }

  async execute(parameters) {
    if (this._phase !== "approved") return Promise.reject(new OwnerClientError("phase"));
    const retained = parametersValue(detach(parameters));
    if (this._originalParameters === null || this._parameters === null
        || canonical(retained) !== canonical(this._originalParameters)
        || canonical(retained) !== canonical(this._parameters)) {
      return Promise.reject(new OwnerClientError("parameters"));
    }
    const result = await this._command("execute", retained);
    return detach(result);
  }

  async cancel() {
    if (!["prepared", "approved"].includes(this._phase)) return Promise.reject(new OwnerClientError("phase"));
    await this._command("cancel", {});
    return undefined;
  }

  async close() {
    if (this._closed && this._cleanupObserved) return;
    this._closed = true;
    if (this._pending !== null) {
      const pending = this._pending;
      this._pending = null;
      clearTimeout(pending.timer);
      pending.reject(new OwnerClientError("closed"));
    }
    await this._terminate();
    this._cleanupObserved = true;
  }
}

export default MergeOwnerClient;
