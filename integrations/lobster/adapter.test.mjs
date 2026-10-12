import assert from 'node:assert/strict';
import {mkdtemp,readFile,readdir,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {delimiter,dirname,resolve} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import test from 'node:test';
import {LobsterMergeAdapter,LOBSTER_PIN} from './adapter.mjs';
import {MergeOwnerClient} from '../openclaw/owner-client.mjs';

const ROOT=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const modulePath=process.env.LOBSTER_CORE_MODULE;
const runtime=modulePath ? await import(pathToFileURL(resolve(modulePath)).href) : null;
process.env.PYTHONPATH=[ROOT,resolve(ROOT,'packages/mothership-github'),resolve(ROOT,'packages/mothership-adapters')].join(delimiter);
const parameters={repository:'example/repo',pull_request:7,expected_head_sha:'a'.repeat(40),expected_base:'main',merge_method:'merge'};
const context={host_id:'lobster-test',session_id:'session',actor_id:'actor',runtime_generation:'gen',scope:['github.merge_pr']};
const ref={ref_id:'executor:lobster-test',sha256:'c'.repeat(64)};
const respond=(request,decision='approve')=>({schema_version:'authority-action-review-response.v0',decision,
  request_id:request.request_id,request_sha256:request.request_sha256,action_id:request.action.action_id,action_sha256:request.action_sha256});
async function fixture(t,mode,runtimeOverride=runtime) {
  const temp=await mkdtemp(resolve(tmpdir(),'mothership-lobster-'));
  let puts=0;
  const current=structuredClone(context);
  const owner=new MergeOwnerClient({pythonExecutable:process.env.PYTHON_EXECUTABLE??resolve(ROOT,'../ci-venv/bin/python'),
    authorityPath:resolve(temp,'authority.jsonl'),attemptsPath:resolve(temp,'attempts.jsonl'),
    contextProvider:async()=>structuredClone(current),transport:{
      getPullRequest:async()=>{
        if(mode==='drift-get')current.actor_id='changed';
        return {http_status:200,state:'open',merged:false,head_sha:parameters.expected_head_sha,base_ref:'main'};
      },mergePullRequest:async()=>{puts++;if(mode==='unknown')throw new Error('private');return {http_status:200,merged:true,merge_commit_sha:'b'.repeat(40)};},
    }});
  const adapter=new LobsterMergeAdapter({owner,runtime:runtimeOverride,stateDir:resolve(temp,'lobster'),parameters,executorRef:ref});
  t.after(async()=>{await adapter.close();await rm(temp,{recursive:true,force:true});});
  return {adapter,owner,current,temp,puts:()=>puts};
}
async function assertNoPendingState(f) {
  const entries=await readdir(resolve(f.temp,'lobster'));
  const data=await Promise.all(entries.filter(n=>n.endsWith('.json')).map(n=>readFile(resolve(f.temp,'lobster',n),'utf8')));
  assert.ok(!entries.some(n=>n.startsWith('approval_')), 'approval index survives cleanup');
  assert.ok(!data.some(s=>JSON.parse(s).type!=='lobster.consumed-resume-state.v1'), 'pending state survives cleanup');
}
test('closing a pending native continuation deletes its state and approval index', {skip:!runtime},async t=>{
  const f=await fixture(t);await f.adapter.prepare();
  assert.ok((await readdir(resolve(f.temp,'lobster'))).some(n=>n.startsWith('approval_')));
  await f.adapter.close();
  await assertNoPendingState(f);assert.equal(f.puts(),0);assert.equal(f.owner.cleanedUp,true);
  await f.adapter.close();
});
test('close during native prepare deletes the late returned continuation', {skip:!runtime},async t=>{
  let release,started;
  const gate=new Promise(r=>{release=r;});const ready=new Promise(r=>{started=r;});
  const f=await fixture(t,undefined,{...runtime,runToolRequest:async options=>{
    const result=await runtime.runToolRequest(options);started();await gate;return result;
  }});
  const pending=f.adapter.prepare();const rejected=assert.rejects(()=>pending);
  await ready;await f.adapter.close();release();await rejected;
  await assertNoPendingState(f);assert.equal(f.puts(),0);assert.equal(f.owner.cleanedUp,true);
});
test('close during review cannot arm the native merge', {skip:!runtime},async t=>{
  const f=await fixture(t);const first=await f.adapter.prepare();
  const review=f.owner.review.bind(f.owner);let release,started;
  const gate=new Promise(r=>{release=r;});const ready=new Promise(r=>{started=r;});
  f.owner.review=async response=>{const result=await review(response);started();await gate;return result;};
  const pending=f.adapter.resume(respond(first.request),{token:first.resumeToken});
  const rejected=assert.rejects(()=>pending);
  await ready;await f.adapter.close();release();await rejected;
  await assertNoPendingState(f);assert.equal(f.puts(),0);assert.equal(f.owner.cleanedUp,true);
});
test('actual pinned runtime pauses before consume, resumes once, cleans child', {skip:!runtime},async t=>{
  assert.equal(LOBSTER_PIN,'74db2679fe34c6b04b067eebea943eaabd8b789f');
  const f=await fixture(t);
  const first=await f.adapter.prepare();
  assert.equal(first.status,'needs_approval');
  assert.equal(f.puts(),0);
  await assert.rejects(()=>readFile(resolve(f.temp,'authority.jsonl')),{code:'ENOENT'});
  const result=await f.adapter.resume(respond(first.request),{token:first.resumeToken});
  assert.equal(result.receipt.status,'SUCCESS');assert.equal(f.puts(),1);
  await assert.rejects(()=>f.adapter.resume(respond(first.request),{token:first.resumeToken}));
  assert.equal(f.owner.cleanedUp,true);
});
test('reject, changed token, changed context and closed owner stop without PUT', {skip:!runtime},async t=>{
  for(const mode of ['reject','token','context','closed']) {
    const f=await fixture(t);const first=await f.adapter.prepare();
    if(mode==='context')f.current.actor_id='changed';
    if(mode==='closed')await f.owner.close();
    if(mode==='reject')assert.equal((await f.adapter.resume(respond(first.request,'reject'),{token:first.resumeToken})).status,'cancelled');
    else await assert.rejects(()=>f.adapter.resume(respond(first.request),{token:mode==='token'?'foreign':first.resumeToken}));
    assert.equal(f.puts(),0);
    await assertNoPendingState(f);
  }
});
test('post-consume transport uncertainty and context GET drift never replay', {skip:!runtime},async t=>{
  for(const mode of ['unknown','drift-get']) {
    const f=await fixture(t,mode);const first=await f.adapter.prepare();
    const result=await f.adapter.resume(respond(first.request),{token:first.resumeToken});
    assert.equal(result.receipt.status,'UNKNOWN');assert.equal(f.puts(),mode==='unknown'?1:0);
    const rows=(await readFile(resolve(f.temp,'authority.jsonl'),'utf8')).trim().split('\n');
    assert.equal(rows.length,2);
    await assert.rejects(()=>f.adapter.resume(respond(first.request),{token:first.resumeToken}));
  }
});
