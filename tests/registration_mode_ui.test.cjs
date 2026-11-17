/* Node's built-in JS test runner: real registration functions, mocked fetch/DOM.
   No patient information or browser cookie enters this test. */
const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');

const html=fs.readFileSync(path.join(__dirname,'../app/ui.html'),'utf8');
const study=fs.readFileSync(path.join(__dirname,'../app/study_ui.js'),'utf8');
const start=html.indexOf('async function verifyDataEntryMode(){');
const end=html.indexOf('\nasync function login(){',start);
const registerStart=html.indexOf('async function register(){');
const registerEnd=html.indexOf('\nasync function newEntry(){',registerStart);
assert.ok(start>0 && end>start && registerStart>end && registerEnd>registerStart);
const functions='let lastVerifiedDataMode=null;\n'+
  html.slice(start,end)+'\n'+html.slice(registerStart,registerEnd)+'\n';
assert.match(html.slice(end,registerStart),/await verifyDataEntryMode\(\)/,
  'Login must verify the mode even without the deferred study helper');
assert.doesNotMatch(study,/register\s*=\s*async function\s*\(/,
  'Later dashboard script must never replace the authoritative registration');
assert.match(html,/study_ui\.js\?v=/,'Versioned study JS avoids old browser caches');

function screen({mode,cr='REAL-CASE-TEST',name='Trial source test',failure}){
 const nodes=new Map();
 function element(id){
  if(!nodes.has(id))nodes.set(id,{value:'',textContent:'',classList:{
    add(){},remove(){},toggle(){}
  }});
  return nodes.get(id);
 }
 element('cr').value=cr;
 element('patientName').value=name;
 element('study').value='';
 element('transplant').value='';
 const calls=[],notices=[];
 const context={
  $:element,document:{title:''},
  api:async(url,args)=>{
   calls.push({url,method:args?.method||'GET'});
   if(url==='/api/system/mode'){
    if(failure)throw Error('Network unavailable');
    return mode;
   }
   if(url==='/api/patients')return{id:'TEST-REG-ID'};
   throw Error('Unexpected endpoint '+url);
  },
  show:(id,message,isError)=>{notices.push({id,message,isError})},
  choose:async()=>{}
 };
 vm.createContext(context);
 vm.runInContext(functions+'globalThis.performRegistration=register;',context);
 return{context,calls,notices};
}

test('fresh server mode checked and real identifiers rejected in staging',async()=>{
 const t=screen({mode:{mode:'synthetic',clinical_registration_enabled:false}});
 await t.context.performRegistration();
 assert.deepEqual(t.calls.map(x=>x.url),['/api/system/mode']);
 assert.match(t.notices.at(-1).message,/synthetic staging/i);
});

test('synthetic identifiers still work for synthetic-only UAT',async()=>{
 const t=screen({mode:{mode:'synthetic',clinical_registration_enabled:false},
  cr:'TEST-EXAMPLE',name:'Synthetic Participant'});
 await t.context.performRegistration();
 assert.deepEqual(t.calls.map(x=>x.url),['/api/system/mode','/api/patients']);
});

test('clinical registration only after fresh positive server-mode response',async()=>{
 const t=screen({mode:{mode:'clinical',clinical_registration_enabled:true}});
 await t.context.performRegistration();
 assert.deepEqual(t.calls.map(x=>x.url),['/api/system/mode','/api/patients']);
 assert.equal(t.context.document.title,'NIMS CMV · Clinical EDC');
});

test('clinical mode with stale recovery proof cannot register real patients',async()=>{
 const t=screen({mode:{mode:'clinical',clinical_registration_enabled:false}});
 await t.context.performRegistration();
 assert.deepEqual(t.calls.map(x=>x.url),['/api/system/mode']);
});

test('network failure never falls back to an unverified cached mode',async()=>{
 const t=screen({failure:true});
 await t.context.performRegistration();
 assert.deepEqual(t.calls.map(x=>x.url),['/api/system/mode']);
 assert.match(t.notices.at(-1).message,/not saved/i);
});

test('invalid API mode response fails closed',async()=>{
 const t=screen({mode:{mode:'clinical',clinical_registration_enabled:'true'}});
 await t.context.performRegistration();
 assert.deepEqual(t.calls.map(x=>x.url),['/api/system/mode']);
 assert.match(t.notices.at(-1).message,/invalid data-entry mode/i);
});
