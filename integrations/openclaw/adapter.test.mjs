import assert from 'node:assert/strict';
import test from 'node:test';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {delimiter,dirname,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {MergeOwnerClient} from './owner-client.mjs';
import { createSelectedMergeTool, OPENCLAW_PIN } from './adapter.mjs';

const params = { repository: 'example/repo', pull_request: 7, expected_head_sha: 'a'.repeat(40), expected_base: 'main', merge_method: 'merge' };
function fixture() {
  const calls = [];
  const request = { request_id: 'r', request_sha256: 'c'.repeat(64), action_sha256: 'd'.repeat(64), action: { action_id: 'a', execution_parameters: params } };
  const owner = { prepare: async () => { calls.push('prepare'); return structuredClone(request); },
    review: async r => { calls.push(r.decision); return r.decision; },
    execute: async p => { calls.push('execute'); assert.deepEqual(p, params); return {receipt:{status:'SUCCESS'}}; },
    cancel: async () => calls.push('cancel'), close: async () => calls.push('close') };
  return { calls, selected: createSelectedMergeTool({owner, parameters:params, executorRef:{ref_id:'x',sha256:'b'.repeat(64)}}) };
}
const event = () => ({toolName:'mothership_merge_pr',toolCallId:'call1',params:structuredClone(params)});

test('selected hook binds one allow-once and exact tool invocation', async () => {
  const {selected,calls} = fixture();
  assert.equal(OPENCLAW_PIN, '6cc8bb1a4b9e97b4461c5cbd9006adf4630b9ccc');
  const hook = await selected.beforeToolCall(event(), {toolCallId:'call1'});
  assert.deepEqual(hook.requireApproval.allowedDecisions,['allow-once','deny']);
  await hook.requireApproval.onResolution('allow-once');
  const result = await selected.tool.execute('call1',structuredClone(params));
  assert.equal(result.details.receipt.status,'SUCCESS');
  await assert.rejects(() => selected.tool.execute('call1',params));
  assert.deepEqual(calls,['prepare','approve','execute','close']);
});
test('direct body, foreign call, rewritten params and delegated path cannot execute', async () => {
  for (const mode of ['direct','id','params','delegated']) {
    const {selected,calls} = fixture();
    if (mode==='direct') await assert.rejects(() => selected.tool.execute('call1',params));
    else if (mode==='delegated') await assert.rejects(() => selected.beforeToolCall(event(), {toolCallId:'call1',delegated:true}));
    else {
      const hook = await selected.beforeToolCall(event(), {toolCallId:'call1'});
      await hook.requireApproval.onResolution('allow-once');
      await assert.rejects(() => selected.tool.execute(mode==='id'?'other':'call1',mode==='params'?{...params,pull_request:8}:params));
    }
    assert.ok(!calls.includes('execute'));
  }
});
test('deny, timeout, cancellation and allow-always are terminal without execute', async () => {
  for (const decision of ['deny','timeout','cancelled','allow-always']) {
    const {selected,calls} = fixture();
    const hook = await selected.beforeToolCall(event(), {toolCallId:'call1'});
    if (decision==='allow-always') await assert.rejects(() => hook.requireApproval.onResolution(decision));
    else await hook.requireApproval.onResolution(decision);
    await assert.rejects(() => selected.tool.execute('call1',params));
    assert.ok(!calls.includes('execute'));
    assert.ok(calls.includes('close'));
  }
});
test('duplicate resolution and second hook cannot admit another call', async () => {
  const {selected,calls} = fixture();
  const hook = await selected.beforeToolCall(event(), {toolCallId:'call1'});
  await hook.requireApproval.onResolution('allow-once');
  await assert.rejects(() => hook.requireApproval.onResolution('allow-once'));
  await assert.rejects(() => selected.beforeToolCall(event(), {}));
  assert.equal(calls.filter(x=>x==='prepare').length,1);
});
test('selected public schema matches the closed Core action; invalid targets never prepare', async () => {
  const {selected}=fixture();
  assert.equal(selected.tool.parameters.properties.merge_method.const,'merge');
  assert.deepEqual(selected.tool.parameters.properties.expected_base,
    {type:'string',minLength:1,maxLength:128,pattern:'^[A-Za-z0-9][A-Za-z0-9._/-]*$'});
  for(const override of [{merge_method:'squash'},{merge_method:'rebase'},
    {repository:'example/repo/other'},{repository:'example repo/x'},
    {expected_base:'-main'},{expected_base:'x'.repeat(129)},{expected_base:'main\n'},
    {expected_head_sha:'a'.repeat(40)+'\n'},{pull_request:true}]) {
    const invalid={...params,...override};
    let prepared=0,executed=0;
    const owner={prepare:async()=>{prepared++;},execute:async()=>{executed++;},close:async()=>{}};
    assert.throws(()=>createSelectedMergeTool({owner,parameters:invalid,executorRef:{}}));
    await assert.rejects(()=>selected.beforeToolCall({...event(),params:invalid},{}));
    assert.equal(prepared,0);assert.equal(executed,0);
  }
});
test('selected hook uses the real child and synthetic transport; abort stops effect', async () => {
  const root=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
  process.env.PYTHONPATH=[root,resolve(root,'packages/mothership-adapters'),resolve(root,'packages/mothership-github')].join(delimiter);
  for(const mode of ['allow','deny','abort']) {
    const temp=await mkdtemp(resolve(tmpdir(),'mothership-selected-'));
    let puts=0;
    const owner=new MergeOwnerClient({pythonExecutable:process.env.PYTHON_EXECUTABLE??resolve(root,'../ci-venv/bin/python'),
      authorityPath:resolve(temp,'authority.jsonl'),attemptsPath:resolve(temp,'attempts.jsonl'),
      contextProvider:()=>({host_id:'selected-test',session_id:'s',actor_id:'a',runtime_generation:'g',scope:['github.merge_pr']}),
      transport:{getPullRequest:async()=>({http_status:200,state:'open',merged:false,head_sha:params.expected_head_sha,base_ref:'main'}),
        mergePullRequest:async()=>{puts++;return {http_status:200,merged:true,merge_commit_sha:'b'.repeat(40)};}}});
    const selected=createSelectedMergeTool({owner,parameters:params,executorRef:{ref_id:'executor:selected',sha256:'c'.repeat(64)}});
    try {
      const abort=new AbortController();
      const hook=await selected.beforeToolCall(event(),{toolCallId:'call1',abortSignal:abort.signal});
      await hook.requireApproval.onResolution(mode==='deny'?'deny':'allow-once');
      if(mode==='abort')abort.abort();
      if(mode==='allow')assert.equal((await selected.tool.execute('call1',params)).details.receipt.status,'SUCCESS');
      else await assert.rejects(()=>selected.tool.execute('call1',params));
      assert.equal(puts,mode==='allow'?1:0);
      await owner.close();assert.equal(owner.cleanedUp,true);
    } finally {await owner.close();await rm(temp,{recursive:true,force:true});}
  }
});
