const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const html=fs.readFileSync('app/ui.html','utf8');
const source=html.slice(html.indexOf('let sessionDeadline='),html.indexOf('function debounceList()'));
function screen(){
 const events={},calls=[],timers=[];let finished=null,reloaded=false;
 const context={csrf:'fixture-csrf',Date,Number,Math,
  $:()=>({classList:{contains:()=>false}}),
  document:{hidden:false,addEventListener:(n,fn)=>{events[n]=fn;}},
  setTimeout:(fn,ms)=>{timers.push({fn,ms});return timers.length;},clearTimeout(){},
  setInterval:fn=>{events.interval=fn;},
  location:{reload:()=>{reloaded=true;}},show(){},
  api:async(path,options)=>{calls.push({path,options});return {
   csrf_token:'fixture-csrf',expires_at:new Date(Date.now()+1800000).toISOString()};},
  finishLogin:async r=>{finished=r;}
 };
 vm.createContext(context);vm.runInContext(source,context);
 return {context,events,calls,timers,get finished(){return finished;},get reloaded(){return reloaded;}};
}
test('refresh restores the workspace from the cookie session',async()=>{
 const s=screen();await s.context.restoreSignedInSession();
 assert.equal(s.calls[0].path,'/api/session');assert.equal(s.finished.csrf_token,'fixture-csrf');
});
test('idle polling never renews, real user input renews once',async()=>{
 const s=screen();s.context.setSessionDeadline(new Date(Date.now()+1800000).toISOString());
 await s.events.interval();assert.equal(s.calls.length,0);
 s.events.input({isTrusted:false});await s.events.interval();assert.equal(s.calls.length,0);
 s.events.input({isTrusted:true});await s.events.interval();
 assert.equal(s.calls.length,1);assert.equal(s.calls[0].path,'/api/session/activity');
 await s.events.interval();assert.equal(s.calls.length,1);
});
test('expired foreground session clears patient UI, another active tab can extend it',async()=>{
 const s=screen();await s.context.checkSessionExpiry();assert.equal(s.reloaded,false);
 s.context.api=async()=>{const e=new Error('Session expired');e.status=401;throw e;};
 await s.context.checkSessionExpiry();assert.equal(s.reloaded,true);
});
