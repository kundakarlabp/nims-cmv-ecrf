/* Real page/scripts and Chromium, deterministic API fixtures only. No live data. */
const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const base=path.join(__dirname,'..');
const subjects=[1,2].map(id=>({id,study_code:'TEST-STUDY-'+id,screening_code:'TEST-SCREEN-'+id,
 status:'enrolled',enrolled_on:'2026-10-02',donor_type:'living',ratg_induction:true,patient_id:'TEST-P-'+id,cr_number:'TEST-CR-'+id}));
subjects.push({id:3,screening_code:'TEST-SCREEN-3',status:'screened',enrolled_on:null,donor_type:'living',ratg_induction:true,patient_id:'TEST-P-3',cr_number:'TEST-CR-3'});
const people=[1,2,3].map(id=>({id:'TEST-P-'+id,name:'Synthetic participant '+id,cr_number:'TEST-CR-'+id,study_id:id<3?'TEST-STUDY-'+id:null}));
const f=(label,type='text',required=false)=>({label,type,required});
const forms={M_medication:{title:'M. Medication exposure',repeat:'event',supplementary:true,fields:{
 start_on:f('Effective date','date',true),source_reference:f('Source','text',true),
 dose_per_administration:f('Dose','number'),drug:f('Drug')}},
 N_laboratory:{title:'N. Laboratory',repeat:'event',supplementary:true,fields:{sample_on:f('Sample date','date',true)}},
 O_infection:{title:'O. Infection',repeat:'event',supplementary:true,fields:{onset_on:f('Onset','date',true)}}};

(async()=>{
 const executablePath=process.env.CMV_TEST_CHROME||
  ['/usr/bin/google-chrome','/usr/bin/chromium'].find(p=>fs.existsSync(p));
 const browser=await chromium.launch({headless:true,executablePath});
 try{
  const page=await browser.newPage({viewport:{width:1280,height:900}});
  const errors=[],writes=[],drafts=new Map(),contextReads=[];let blinded=false,holdOldDraft=false,releaseOldDraft=null;
  const eligibility=new Map(),allocations=new Map();let assignedFresh=false,holdSearchContext=false,releaseSearchContext=null;
  let holdOldPCR=false,releaseOldPCR=null,holdScreenedContext=false,releaseScreenedContext=null;
  let signedIn=false;
  const session=()=>({username:'synthetic-nurse',display_name:'Synthetic nurse',role:'nurse',
    csrf_token:'synthetic-csrf',password_only:true,workspace_full_access:false,
    expires_at:new Date(Date.now()+1800000).toISOString(),idle_timeout_seconds:1800});
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('http://cmv-ui.test/**',async route=>{
   const url=new URL(route.request().url());const p=url.pathname;
   if(p==='/')return route.fulfill({contentType:'text/html',body:fs.readFileSync(path.join(base,'app/ui.html'),'utf8')});
   if(p==='/study_ui.js')return route.fulfill({contentType:'application/javascript',body:fs.readFileSync(path.join(base,'app/study_ui.js'),'utf8')});
   if(p==='/patient_workspace.js')return route.fulfill({contentType:'application/javascript',body:fs.readFileSync(path.join(base,'app/patient_workspace.js'),'utf8')});
   const method=route.request().method();let result={};
   if(p==='/api/session'){
    if(!signedIn)return route.fulfill({status:401,contentType:'application/json',body:JSON.stringify({detail:'Login required'})});
    result=session();
   }else if(p==='/api/login'){signedIn=true;result=session();
   }else if(p==='/api/session/activity'){result={expires_at:session().expires_at};
   }else if(p==='/api/patients'){
    if(method==='POST'){
     const data=route.request().postDataJSON();people.push({id:'TEST-P-4',...data});result={id:'TEST-P-4',revision:1};
    }else{const q=(url.searchParams.get('q')||'').toLowerCase();result=people.filter(x=>JSON.stringify(x).toLowerCase().includes(q));}
   }else if(p==='/api/system/mode')result={mode:'clinical',clinical_registration_enabled:true};
   else if(p==='/api/trial/screening'){
    const data=route.request().postDataJSON();writes.push({p,body:data});
    const person=people.find(x=>x.id===data.patient_id);
    result={id:4,patient_id:person.id,cr_number:person.cr_number,screening_code:'TEST-SCREEN-4',status:'screened',enrolled_on:null,donor_type:data.donor_type,ratg_induction:data.ratg_induction};subjects.push(result);
   }else if(p.endsWith('/eligibility')){
    const id=Number(p.split('/')[4]);
    if(method==='PUT'){
     const data=route.request().postDataJSON();writes.push({p,body:data});
     eligibility.set(id,{inclusion:data.inclusion,exclusion:data.exclusion,baseline:data,reviewed_on:data.reviewed_on});result={eligible:true};
    }else result={eligibility:eligibility.get(id)||null};
   }else if(p.endsWith('/consent-declined')){
    const id=Number(p.split('/')[4]);const subject=subjects.find(x=>x.id===id);
    if(subject.consent_recorded||subject.status!=='screened')throw Error('Only unconsented screening may close');
    subject.status='consent_declined';result=subject;writes.push({p,body:route.request().postDataJSON()});
   }else if(p.endsWith('/enroll')){
    const id=Number(p.split('/')[4]),data=route.request().postDataJSON();writes.push({p,body:data});
    const subject=subjects.find(x=>x.id===id);Object.assign(subject,{status:'enrolled',study_code:'NCMV001',enrolled_on:data.enrolled_on});
    people.find(x=>x.id===subject.patient_id).study_id=subject.study_code;
    result={subject,study_id:subject.study_code,pcr_orders:7};
   }else if(p==='/api/trial/action-worklist')result={as_of:'2026-11-18',total:1,counts:{'Enrollment pending':1},
    actions:[{category:'Enrollment pending',study_code:'TEST-SCREEN-3',detail:'Finish enrollment',
     patient_id:'TEST-P-3',subject_id:3,route:'study',priority:1,target_on:null}]};
   else if(p==='/healthz')result={ok:true,app_commit:'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',service:'clinical'};
   else if(p==='/api/trial/randomization/readiness')result={sequence_locked:true,activation_ready:true,allocation_management:'owner_managed'};
   else if(p.endsWith('/allocation')){
    const id=Number(p.split('/')[5]);result=allocations.get(id)||{randomized:false,study_code:'TEST-STUDY-'+id};
   }else if(p.endsWith('/preflight')){
    const id=Number(p.split('/')[5]);
    result=allocations.has(id)?{ready:false,randomized:true,reason:'Already randomized'}:
     {ready:true,randomized:false,study_code:'TEST-STUDY-'+id,stratum:'rATG:living',reason:'Signed confirmation required'};
   }else if(p.endsWith('/assign')){
    const id=Number(p.split('/')[5]);writes.push({p,body:route.request().postDataJSON()});assignedFresh=true;
    result={randomized:true,study_code:'TEST-STUDY-'+id,allocation_code:'TEST-ALLOC-'+id,assigned_arm_mg:'450'};allocations.set(id,result);
   }else if(p==='/api/trial/pharmacy/lots')result=[];
   else if(p.endsWith('/pharmacy'))result={orders:[],dispenses:[]};
   else if(p==='/api/authentication-policy')result={password_only:true,shared_clinical_workspace:true};
   else if(/^\/api\/patients\/TEST-P-/.test(p))result={patient:people.find(x=>x.id===p.split('/')[3]),entries:[]};
   else if(p==='/api/trial/subjects')result=subjects;
   else if(p==='/api/trial/eligibility-schema')result={inclusion:{age_ge_18:'Age at least 18',written_consent:'Written consent'},exclusion:{crcl_below_10:'CrCl below 10'}};
   else if(p.endsWith('/context')){
    contextReads.push(p);
    const id=p.includes('/patients/')?Number(p.match(/TEST-P-(\d+)/)[1]):Number(p.split('/')[5]);
    const subject=subjects.find(x=>x.id===id)||null;
    result={subject,patient_id:'TEST-P-'+id,transplant_on:'2026-10-01',
      allocation:allocations.get(id)||(id<3?{randomized:true,allocation_code:'TEST-ALLOC-'+id,...(blinded?{}:{assigned_arm_mg:id===1?'450':'900'})}:{randomized:false})};
    if(holdSearchContext&&id===1){holdSearchContext=false;await new Promise(resolve=>{releaseSearchContext=resolve;});}
    if(holdScreenedContext&&id===3){holdScreenedContext=false;await new Promise(resolve=>{releaseScreenedContext=resolve;});}
   }else if(p.endsWith('/pcr')){
    const sid=Number(p.split('/')[4]);result={pcr_records:[{id:sid*10+1,status:'planned',specimen_code:'TEST-PCR-'+sid,scheduled_month:1,target_on:'2026-11-01'}]};
    if(holdOldPCR&&sid===1){holdOldPCR=false;await new Promise(resolve=>{releaseOldPCR=resolve;});}
   }else if(p==='/api/trial/crf/schema')result={forms};
   else if(p.includes('/drafts/')){
    const key=p+'?occurrence_key=NEW';
    if(method==='PUT'){const body=route.request().postDataJSON();writes.push({p,body});
      const revision=(drafts.get(key)?.revision||0)+1;drafts.set(key,{...body,revision});result={revision};}
    else {result={draft:drafts.get(key)||null};
     if(holdOldDraft&&p.includes('/subjects/1/')){
      holdOldDraft=false;await new Promise(resolve=>{releaseOldDraft=resolve;});
     }
    }
   }else if(p.endsWith('/entries'))result={entries:[]};
   else if(p.endsWith('/timeline'))result={entries:[],next_cursor:null,note:'Synthetic test timeline'};
   return route.fulfill({contentType:'application/json',body:JSON.stringify(result)});
  });
  await page.goto('http://cmv-ui.test/');
  await page.waitForSelector('#tw-context-subject',{state:'attached'});
  await page.waitForFunction(()=>window.passwordOnlyLogin===true);
  assert.equal(await page.isVisible('#loginOtpLabel'),false);
  await page.fill('#loginName','synthetic-nurse');
  await page.fill('#loginPass','Synthetic-fixture-password-only');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await page.waitForFunction(()=>$('who').textContent.includes('Synthetic nurse'));
  await page.reload();
  await page.waitForFunction(()=>$('who').textContent.includes('Synthetic nurse'));
  assert.equal(await page.isVisible('#loginPanel'),false,'Refresh must recover the existing staff session');
  await page.evaluate(async()=>{
   $('workspace').classList.remove('hide');$('loginPanel').classList.add('hide');
   $('currentRole').textContent='nurse';applyRoleUI('nurse');await tab('study');
  });
  assert.deepEqual(errors,[],'Actual deferred script must initialize without JavaScript errors');
  assert.deepEqual(await page.evaluate(()=>{
   const ids=Array.from(document.querySelectorAll('[id]'),el=>el.id);
   return ids.filter((id,index)=>ids.indexOf(id)!==index);
  }),[],'Every page and control ID must be unique; Enrollment must not collide with registry Study ID');
  // Global clinical patient search remains accessible from every tab and
  // resolves one exact record by CR, name or assigned Study ID.
  for(const query of ['TEST-CR-2','Synthetic participant 2','TEST-STUDY-2']){
   await page.fill('#tw-context-find',query);
   await page.waitForFunction(()=>$('tw-context-find-results').querySelector('option[value="TEST-P-2"]'));
   assert.equal(await page.locator('#tw-context-find-results option[value="TEST-P-2"]').count(),1);
  }
  await page.selectOption('#tw-context-find-results','TEST-P-2');
  await page.waitForFunction(()=>$('tw-context-subject').value==='2'&&selected==='TEST-P-2');
  assert.equal(await page.inputValue('#tw-patient'),'TEST-P-2');
  await page.evaluate(async()=>{await tab('pcr');});
  await page.waitForFunction(()=>$('tw-pcr-subject').value==='2');
  await page.evaluate(async()=>{await tab('crf');});
  await page.waitForFunction(()=>$('tw-crf-subject').value==='2');
  await page.selectOption('#tw-context-subject','1');
  await page.waitForFunction(()=>$('tw-context-allocation').textContent.includes('450 mg'));
  assert.equal(await page.evaluate(()=>selected),'TEST-P-1');
  assert.equal(await page.inputValue('#arm'),'450');
  assert.equal(await page.isDisabled('#arm'),true);
  await page.evaluate(()=>{$('age').value='70';$('weight').value='80';$('creatinine').value='1.6';});
  await page.evaluate(async()=>{await tab('crf');});
  await page.fill('#twcrf-start_on','2026-10-04');
  await page.fill('#twcrf-source_reference','TEST-SOURCE-ALPHA');
  await page.fill('#twcrf-dose_per_administration','360');
  await page.fill('#twcrf-drug','mycophenolate_sodium');
  await page.selectOption('#tw-context-subject','2');
  await page.waitForFunction(()=>$('tw-context-allocation').textContent.includes('900 mg'));
  assert.equal(await page.evaluate(()=>selected),'TEST-P-2');
  assert.equal(await page.inputValue('#arm'),'900');
  assert.equal(await page.inputValue('#creatinine'),'');
  assert.ok(writes.some(x=>x.p.includes('/subjects/1/')&&x.body.payload.source_reference==='TEST-SOURCE-ALPHA'));
  assert.ok(!writes.some(x=>x.p.includes('/subjects/2/')&&x.body.payload.source_reference==='TEST-SOURCE-ALPHA'));
  assert.equal(await page.inputValue('#twcrf-source_reference'),'');
  // Patient directory navigation must use the real global chooser, not the
  // similarly named form-control builder inside the deferred script.
  await page.evaluate(async()=>{await choose('TEST-P-1');});
  assert.match(await page.textContent('#tw-context-allocation'),/450 mg/);
  assert.equal(await page.inputValue('#twcrf-source_reference'),'TEST-SOURCE-ALPHA');
  // A delayed old participant draft response must not overwrite the next one.
  await page.selectOption('#tw-context-subject','2');
  await page.waitForFunction(()=>$('tw-crf-subject').value==='2'&&$('twcrf-source_reference').value==='');
  holdOldDraft=true;
  await page.selectOption('#tw-context-subject','1');
  for(let i=0;i<100&&!releaseOldDraft;i++)await new Promise(resolve=>setTimeout(resolve,20));
  assert.ok(releaseOldDraft,'Held old-participant draft request must start');
  await page.selectOption('#tw-context-subject','2');
  await page.waitForFunction(()=>$('tw-crf-subject').value==='2'&&$('tw-context-allocation').textContent.includes('900 mg'));
  releaseOldDraft();
  await page.waitForTimeout(150);
  assert.equal(await page.inputValue('#twcrf-source_reference'),'');
  await page.evaluate(async()=>{await tab('course');});
  assert.match(await page.textContent('#tw-context-allocation'),/900 mg/);
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.locator('#tw-participant-context').evaluate(el=>getComputedStyle(el).gridColumnStart),'1');
  blinded=true;
  await page.evaluate(()=>{$('currentRole').textContent='monitor';applyRoleUI('monitor');});
  await page.selectOption('#tw-context-subject','1');
  await page.waitForFunction(()=>$('tw-context-allocation').textContent.includes('concealed'));
  assert.doesNotMatch(await page.textContent('#tw-context-allocation'),/450|900/);
  await page.evaluate(()=>{$('currentRole').textContent='pi';applyRoleUI('pi');});
  await page.evaluate(async()=>{await tab('pcr');});
  await page.selectOption('#tw-context-subject','1');
  await page.waitForFunction(()=>$('tw-collect-id').value==='11');
  holdOldPCR=true;
  await page.selectOption('#tw-context-subject','1');
  for(let i=0;i<200&&!releaseOldPCR;i++)await new Promise(resolve=>setTimeout(resolve,20));
  assert.ok(releaseOldPCR,'Old participant specimen request must be held');
  holdScreenedContext=true;
  await page.selectOption('#tw-context-subject','3');
  assert.equal(await page.isDisabled('#tw-collect-save'),true,'Patient switch must disable collection immediately');
  for(let i=0;i<200&&!releaseScreenedContext;i++)await new Promise(resolve=>setTimeout(resolve,20));
  assert.ok(releaseScreenedContext,'New participant context must still be loading');
  releaseOldPCR();await page.waitForTimeout(150);
  assert.equal(await page.isDisabled('#tw-collect-save'),true,'A delayed old specimen response cannot re-enable collection');
  releaseScreenedContext();
  await page.waitForFunction(()=>$('tw-context-allocation').textContent.includes('TEST-SCREEN-3')&&$('tw-collect-id').value==='');
  assert.equal(await page.isDisabled('#tw-collect-save'),true);
  assert.equal(await page.inputValue('#tw-pcr-subject'),'');
  await page.selectOption('#tw-context-subject','');
  assert.equal(await page.isDisabled('#tw-result-save'),true);
  assert.equal(await page.isDisabled('#tw-verify-save'),true);
  // Ordinary IT administrators retain authorized registry use, while the
  // restricted clinical allocation context stays unavailable to them.
  await page.evaluate(()=>{$('currentRole').textContent='admin';applyRoleUI('admin');});
  const previousReads=contextReads.length;
  await page.evaluate(async()=>{await choose('TEST-P-2');});
  assert.equal(await page.evaluate(()=>selected),'TEST-P-2');
  assert.equal(contextReads.length,previousReads);
  assert.equal(await page.isVisible('#tw-participant-context'),false);
  await page.evaluate(()=>{
   window.currentWorkspaceFullAccess=true;window.passwordOnlyLogin=true;
   window.currentAdmin=false;window.currentPiAuthorized=false;
   $('currentRole').textContent='pi';applyRoleUI('pi');
  });
  assert.equal(await page.locator('#tw-result-save').evaluate(el=>el.classList.contains('hide')),false);
  assert.equal(await page.locator('#tw-dispense-save').evaluate(el=>el.classList.contains('hide')),false);
  assert.equal(await page.locator('#btnstaff').evaluate(el=>el.classList.contains('hide')),true);
  assert.equal(await page.locator('#tw-mfa-setup').evaluate(el=>el.closest('.study-card').classList.contains('hide')),true);
  // Start exactly where the reported defect occurs: a new registry record,
  // not a fixture that is already enrolled before the page opens.
  await page.setViewportSize({width:1280,height:900});blinded=false;
  await page.evaluate(async()=>{await tab('registry');});
  assert.equal(await page.locator('#registryStudyId').count(),0,'Study ID cannot be entered at registration');
  await page.fill('#cr','TEST-CR-4');await page.fill('#patientName','Synthetic fresh registry');
  await page.fill('#transplant','2026-10-01');
  await page.evaluate(async()=>{await register();});
  assert.equal(await page.evaluate(()=>selected),'TEST-P-4');
  await page.evaluate(async()=>{await tab('randomization');});
  assert.match(await page.textContent('#tw-rand-progress'),/TEST-CR-4.*Registered/);
  assert.equal(await page.isDisabled('#tw-rand-assign'),true);
  assert.equal(assignedFresh,false,'Registry lookup cannot allocate or invent consent');
  await page.fill('#tw-rand-search','TEST-CR-4');await page.click('#tw-rand-fetch');
  await page.waitForFunction(()=>$('tw-rand-patient').options.length===2);
  await page.selectOption('#tw-rand-patient','TEST-P-4');
  await page.waitForFunction(()=>$('tw-rand-progress').textContent.includes('Registered.'));
  await page.click('#tw-rand-continue');
  await page.waitForFunction(()=>activeTab==='study'&&$('tw-patient').value==='TEST-P-4' &&
   $('tw-assigned-study-id').textContent.includes('pending'));
  assert.match(await page.textContent('#tw-assigned-study-id'),/pending/);
  await page.fill('#tw-screen-date','2026-10-02');await page.fill('#tw-consent-date','2026-10-02');
  await page.selectOption('#tw-digg','positive');await page.selectOption('#tw-rigg','positive');
  await page.selectOption('#tw-donor','living');await page.selectOption('#tw-relationship','living_related');
  await page.selectOption('#tw-consent-language','English');
  for(const [id,v] of Object.entries({'tw-icf':'ICF v3','tw-pis':'PIS v3','tw-consent-obtained':'Synthetic investigator','tw-initials':'TS','tw-screen-age':'50'}))await page.fill('#'+id,v);
  await page.selectOption('#tw-sex','male');await page.selectOption('#tw-ratg','true');
  await page.click('#tw-screen-save');
  await page.waitForFunction(()=>$('tw-checklist-subject').value==='4'&&$('tw-screened').value==='4');
  assert.match(await page.locator('#tw-checklist-subject option:checked').textContent(),/TEST-CR-4/);
  for(const [id,v] of Object.entries({'tw-age':'50','tw-anc':'3000','tw-platelets':'180000','tw-hb':'11','tw-crcl':'68',}))await page.fill('#'+id,v);
  await page.fill('#tw-cbc-date','2026-10-02');await page.fill('#tw-review-on','2026-10-02');
  for(const el of await page.locator('[data-eligibility]').all())await el.selectOption(await el.getAttribute('data-eligibility')==='inclusion'?'true':'false');
  await page.click('#tw-checklist-save');await page.waitForFunction(()=>$('tw-status').textContent.includes('Eligible.'));
  await page.evaluate(async()=>{await tab('randomization');});
  assert.match(await page.textContent('#tw-rand-progress'),/Screened/);
  assert.equal(await page.isDisabled('#tw-rand-assign'),true);
  await page.click('#tw-rand-continue');
  await page.waitForFunction(()=>activeTab==='study'&&$('tw-checklist-subject').value==='4');
  assert.equal(await page.inputValue('#tw-anchor-date'),'2026-10-01');
  await page.selectOption('#tw-context-subject','3');
  await page.waitForFunction(()=>$('tw-checklist-subject').value==='3');
  assert.equal(await page.inputValue('#tw-anc'),'','Another screened patient cannot inherit baseline values');
  assert.equal(await page.inputValue('#tw-cbc-date'),'','Another screened patient cannot inherit a CBC date');
  await page.selectOption('#tw-context-subject','4');
  await page.waitForFunction(()=>$('tw-screened').value==='4');
  await page.fill('#tw-enroll-date','2026-10-03');await page.check('#tw-pi-consent');
  await page.click('#tw-enroll-save');
  await page.waitForFunction(()=>$('tw-context-allocation').textContent.includes('NCMV001'));
  assert.match(await page.textContent('#tw-assigned-study-id'),/Study ID: NCMV001/);
  assert.equal(people.find(x=>x.id==='TEST-P-4').study_id,'NCMV001');
  await page.waitForFunction(()=>activeTab==='study'&&!$('tw-inline-rand-submit').disabled);
  assert.equal(await page.isVisible('#tw-inline-rand-confirm'),true,'Clinical attestation must remain visible on the enrollment screen');
  assert.equal(await page.locator('#tw-rand-source').count(),0,'No extra reference field is required');
  await page.click('#tw-inline-rand-submit');
  await page.waitForFunction(()=>$('tw-status').textContent.includes('Confirm the signed consent'));
  assert.equal(writes.filter(x=>x.p.endsWith('/assign')).length,0,'Unchecked confirmation cannot release allocation');
  await page.check('#tw-inline-rand-confirm');
  page.once('dialog',dialog=>{assert.match(dialog.message(),/TEST-CR-4/);return dialog.accept();});
  await page.click('#tw-inline-rand-submit');
  await page.waitForFunction(()=>$('tw-context-allocation').textContent.includes('TEST-ALLOC-4')&&$('tw-inline-rand-submit').disabled);
  assert.equal(await page.isVisible('#tw-progress-step-4'),true,'One patient workflow contains all four trial stages');
  assert.equal(writes.filter(x=>x.p.endsWith('/assign')).length,1,'Only one explicit allocation request');
  assert.equal(writes.find(x=>x.p.endsWith('/assign')).body.signed_randomization_source_ref,
   undefined,'No randomization source text is required');
  assert.ok(writes.some(x=>x.p==='/api/trial/screening'&&x.body.patient_id==='TEST-P-4'));
  assert.equal(writes.find(x=>x.p==='/api/trial/screening').body.eligibility_attested,false);
  assert.equal(writes.find(x=>x.p==='/api/trial/subjects/4/eligibility').body.signed_source_reference,undefined);
  assert.ok(writes.some(x=>x.p==='/api/trial/subjects/4/eligibility'));
  assert.ok(writes.some(x=>x.p==='/api/trial/subjects/4/enroll'&&x.body.pcr_anchor_on==='2026-10-01'));
  for(const module of ['pcr','drug','course','randomization']){
   await page.evaluate(async name=>{await tab(name);},module);
   assert.match(await page.textContent('#tw-context-allocation'),/TEST-ALLOC-4/);
   assert.equal(await page.evaluate(()=>selected),'TEST-P-4');
  }
  await page.evaluate(async()=>{await tab('study');});
  assert.match(await page.textContent('#tw-assigned-study-id'),/Study ID: NCMV001/);
  await page.evaluate(async()=>{await tab('randomization');});
  // Unknown CR must never fall back to the first enrolled person or leave
  // the previous allocation action available.
  holdSearchContext=true;
  await page.selectOption('#tw-rand-subject','1');
  for(let i=0;i<200&&!releaseSearchContext;i++)await new Promise(resolve=>setTimeout(resolve,20));
  assert.ok(releaseSearchContext,'Prior enrolled participant context must still be pending');
  await page.fill('#tw-rand-search','DOES-NOT-EXIST');await page.click('#tw-rand-fetch');
  await page.waitForFunction(()=>$('tw-rand-progress').textContent.includes('No registry record'));
  releaseSearchContext();await page.waitForTimeout(150);
  assert.equal(await page.inputValue('#tw-rand-patient'),'');
  assert.equal(await page.inputValue('#tw-rand-subject'),'');
  assert.equal(await page.isDisabled('#tw-rand-assign'),true);
  // Visible phone navigation and a real worklist route, not merely CSS screenshots.
  await page.setViewportSize({width:393,height:852});
  await page.evaluate(async()=>{await tab('tasks');});
  await page.waitForFunction(()=>$('tw-task-items').textContent.includes('TEST-SCREEN-3'));
  assert.equal(await page.isVisible('#tw-mobile-menu'),true);
  assert.equal(await page.isVisible('#tw-study-navigation'),false);
  await page.click('#tw-mobile-menu');
  assert.equal(await page.isVisible('#tw-study-navigation'),true);
  assert.equal(await page.getAttribute('#tw-mobile-menu','aria-expanded'),'true');
  await page.click('#tw-nav-overview');
  await page.waitForFunction(()=>activeTab==='dashboard');
  assert.equal(await page.isVisible('#tw-study-navigation'),false);
  assert.equal(await page.getAttribute('#tw-mobile-menu','aria-expanded'),'false');
  await page.waitForFunction(()=>$('tw-live-build').textContent.includes('aaaaaaaaaa'));
  assert.match(await page.textContent('#tw-live-build'),/aaaaaaaaaa/);
  await page.evaluate(async()=>{await tab('tasks');});
  await page.click('#tw-task-items [data-task-idx="0"]');
  await page.waitForFunction(()=>activeTab==='study'&&selected==='TEST-P-3');
  // Layout must remain within the mobile viewport; data tables scroll inside
  // their own containers, never force the whole clinical page horizontally.
  for(const width of [360,393,768]){
   await page.setViewportSize({width,height:852});
   for(const section of ['dashboard','tasks','study','pcr','drug','crf','randomization','course']){
    await page.evaluate(async name=>{await tab(name);},section);
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth);
    assert.ok(overflow<=2,'Horizontal page overflow '+overflow+'px in '+section+' at '+width+'px');
   }
  }
  assert.equal(await page.locator('#tw-progress-stage-notfound').count(),0);
  assert.equal(await page.locator('#tw-progress-step-4').count(),1,'Patient trial workflow has exactly four stages');
  assert.deepEqual(errors,[]);
  console.log('Real browser passed: patient-centric navigation, in-page allocation, cross-patient draft isolation and mobile layout');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
