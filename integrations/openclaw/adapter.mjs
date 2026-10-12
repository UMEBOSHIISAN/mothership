// Selected plugin-tool contract only; no global/native/client-tool interception.
export const OPENCLAW_PIN = '6cc8bb1a4b9e97b4461c5cbd9006adf4630b9ccc';
const keys = ['repository','pull_request','expected_head_sha','expected_base','merge_method'];
const same = (a,b) => a && Object.getPrototypeOf(a) === Object.prototype
  && Object.keys(a).length === keys.length && keys.every(k => Object.hasOwn(a,k) && a[k] === b[k]);
const fail = () => { throw new Error('selected merge unavailable'); };
const fullMatch = (pattern,value) => typeof value === 'string' && pattern.exec(value)?.[0] === value;
const valid = p => same(p,p)
  && fullMatch(/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/,p.repository)
  && Number.isSafeInteger(p.pull_request) && p.pull_request >= 1
  && fullMatch(/^[0-9a-f]{40}$/,p.expected_head_sha)
  && p.expected_base.length >= 1 && p.expected_base.length <= 128
  && fullMatch(/^[A-Za-z0-9][A-Za-z0-9._/-]*$/,p.expected_base)
  && p.merge_method === 'merge';

export function createSelectedMergeTool({owner, parameters, executorRef}) {
  if (!valid(parameters)) fail();
  const retained = structuredClone(parameters);
  let phase = 'new', callId, request, signal;
  async function stop() {
    phase = 'failed';
    await owner.close();
  }
  const tool = {
    name:'mothership_merge_pr', label:'Mothership exact PR merge',
    description:'One exact GitHub PR merge after allow-once review. Host supplies identity and transport.',
    parameters:{type:'object',additionalProperties:false,required:keys,properties:{
      repository:{type:'string',minLength:3,pattern:'^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$'},pull_request:{type:'integer',minimum:1},
      expected_head_sha:{type:'string',pattern:'^[0-9a-f]{40}$'},
      expected_base:{type:'string',minLength:1,maxLength:128,pattern:'^[A-Za-z0-9][A-Za-z0-9._/-]*$'},merge_method:{type:'string',const:'merge'},
    }},
    async execute(id, params) {
      if (phase !== 'approved') fail();
      phase = 'executing';
      try {
        if (id !== callId || !same(params,retained) || signal?.aborted) fail();
        const result = await owner.execute(retained);
        phase = 'finished';
        return {content:[{type:'text',text:JSON.stringify(result)}],details:result};
      } catch {
        phase = 'failed';
        fail();
      } finally { await owner.close(); }
    },
  };
  async function beforeToolCall(event, context={}) {
    if (event.toolName !== tool.name) return undefined;
    if (phase !== 'new') fail();
    phase = 'preparing';
    try {
      if (typeof event.toolCallId !== 'string' || !event.toolCallId
          || (context.toolCallId !== undefined && context.toolCallId !== event.toolCallId)
          || context.delegated === true || context.nested === true
          || !valid(event.params) || !same(event.params,retained) || context.abortSignal?.aborted) fail();
      callId = event.toolCallId;
      signal = context.abortSignal;
      request = await owner.prepare(retained,executorRef);
      phase = 'pending';
      return {requireApproval:{
        title:'Review exact PR merge', description:JSON.stringify(request),
        allowedDecisions:['allow-once','deny'],timeoutMs:30_000,
        async onResolution(decision) {
          if (phase !== 'pending') fail();
          phase = 'reviewing';
          try {
            if (signal?.aborted || decision === 'timeout' || decision === 'cancelled') {
              await owner.cancel(); phase = 'canceled'; await owner.close(); return;
            }
            if (!['allow-once','deny'].includes(decision)) fail();
            const expected = decision === 'allow-once' ? 'approve' : 'reject';
            const result = await owner.review({
              schema_version:'authority-action-review-response.v0',decision:expected,
              request_id:request.request_id,request_sha256:request.request_sha256,
              action_id:request.action.action_id,action_sha256:request.action_sha256,
            });
            if (result !== expected) fail();
            phase = expected === 'approve' ? 'approved' : 'rejected';
            if (phase === 'rejected') await owner.close();
          } catch { await stop(); fail(); }
        },
      }};
    } catch { await stop(); fail(); }
  }
  return Object.freeze({tool,beforeToolCall,close:stop});
}
