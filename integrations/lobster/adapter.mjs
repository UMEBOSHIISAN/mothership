// Embedded runtime only. A resume token never selects/restores an owner.
export const LOBSTER_PIN='74db2679fe34c6b04b067eebea943eaabd8b789f';
const fail=()=>{throw new Error('lobster merge unavailable');};
const canonical=v=>v===null||typeof v!=='object'?JSON.stringify(v):Array.isArray(v)
  ?`[${v.map(canonical).join(',')}]`:`{${Object.keys(v).sort().map(k=>`${JSON.stringify(k)}:${canonical(v[k])}`).join(',')}}`;

export class LobsterMergeAdapter {
  #owner;#runtime;#ctx;#parameters;#ref;#phase='new';#request;#token;#armed=false;
  #effectEntered=false;#nativeSettled=false;#cleanupPromise;
  constructor({owner,runtime,stateDir,parameters,executorRef}) {
    if(!runtime||typeof runtime.runToolRequest!=='function'||typeof runtime.resumeToolRequest!=='function'
      ||typeof stateDir!=='string'||!stateDir.startsWith('/'))fail();
    this.#owner=owner;this.#runtime=runtime;
    this.#parameters=structuredClone(parameters);this.#ref=structuredClone(executorRef);
    const commands=new Map([
      ['mothership.preview',{name:'mothership.preview',meta:{sideEffects:[],resumeSafeBeforeInput:true},
        run:async()=>{if(this.#phase!=='preparing')fail();return {output:[structuredClone(this.#request)]};}}],
      ['mothership.approve',{name:'mothership.approve',meta:{sideEffects:[],resumeSafeBeforeInput:true},
        run:async({input})=>{
          const rows=[];for await(const row of input)rows.push(row);
          if(this.#phase!=='preparing'||canonical(rows)!==canonical([this.#request]))fail();
          return {halt:true,output:[{type:'approval_request',prompt:JSON.stringify(this.#request),items:rows}]};
        }}],
      ['mothership.merge',{name:'mothership.merge',meta:{sideEffects:['github.merge_pr']},
        run:async({input})=>{
          if(this.#phase!=='executing'||!this.#armed)fail();
          this.#armed=false;
          const rows=[];for await(const row of input)rows.push(row);
          if(canonical(rows)!==canonical([this.#request]))fail();
          this.#effectEntered=true;
          const result=await this.#owner.execute(this.#parameters);
          return {output:[result]};
        }}],
    ]);
    this.#ctx={env:{LOBSTER_STATE_DIR:stateDir},registry:{get:name=>commands.get(name),list:()=>[...commands.keys()]}};
  }
  async prepare() {
    if(this.#phase!=='new')fail();
    this.#phase='preparing';
    try {
      this.#request=await this.#owner.prepare(this.#parameters,this.#ref);
      if(this.#phase!=='preparing')fail();
      const result=await this.#runtime.runToolRequest({pipeline:'mothership.preview | mothership.approve | mothership.merge',ctx:this.#ctx});
      if(typeof result.requiresApproval?.resumeToken==='string')this.#token=result.requiresApproval.resumeToken;
      if(result.ok!==true||result.status!=='needs_approval'||typeof result.requiresApproval?.resumeToken!=='string'
        ||canonical(result.requiresApproval.items)!==canonical([this.#request])||this.#phase!=='preparing')fail();
      this.#token=result.requiresApproval.resumeToken;this.#phase='pending';
      return {status:'needs_approval',request:structuredClone(this.#request),resumeToken:this.#token};
    } catch {this.#phase='failed';await this.#finishClose();fail();}
  }
  async resume(response,{token}={}) {
    if(this.#phase!=='pending')fail();
    this.#phase='reviewing';
    try {
      if(token!==this.#token)fail();
      const decision=await this.#owner.review(response);
      if(this.#phase!=='reviewing'||!['approve','reject'].includes(decision))fail();
      this.#phase=decision==='approve'?'executing':'rejected';
      this.#armed=decision==='approve';
      const result=await this.#runtime.resumeToolRequest({token:this.#token,approved:decision==='approve',ctx:this.#ctx});
      if(result.ok!==true)fail();
      if(decision==='reject') {
        if(result.status!=='cancelled')fail();
        this.#nativeSettled=true;
        return {status:'cancelled'};
      }
      if(result.status!=='ok'||!Array.isArray(result.output)||result.output.length!==1||this.#armed)fail();
      this.#phase='finished';
      this.#nativeSettled=true;
      return structuredClone(result.output[0]);
    } catch {this.#phase='failed';fail();}
    finally {this.#armed=false;await this.#finishClose();}
  }
  async #finishClose() {
    try {
      if(this.#token&&!this.#effectEntered&&!this.#nativeSettled) {
        // Claim one native cancellation attempt before yielding. No execution replay.
        this.#cleanupPromise??=(async()=>{
          const result=await this.#runtime.resumeToolRequest({token:this.#token,cancel:true,ctx:this.#ctx});
          if(result.ok!==true||result.status!=='cancelled')throw new Error('lobster pending cleanup unverified');
          this.#nativeSettled=true;
        })();
        await this.#cleanupPromise;
      }
    } finally {await this.#owner.close();}
  }
  async close() {this.#phase='closed';this.#armed=false;await this.#finishClose();}
}
