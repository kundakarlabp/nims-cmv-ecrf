/* Real page/scripts and Chromium, deterministic API fixtures only. No live data. */
const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const base=path.join(__dirname,'..');
const subjects=[1,2].map(id=>({id,study_code:'TEST-STUDY-'+id,screening_code:'TEST-SCREEN-'+id,
 status:'enrolled',enrolled_on:'2026-10-02',donor_type:'living',ratg_induction:true}));
subjects.push({id:3,screening_code:'TEST-SCREEN-3',status:'screened',enrolled_on:null,donor_type:'living',ratg_induction:true});
const people=[1,2,3].map(id=>({id:'TEST-P-'+id,name:'Synthetic participant '+id,cr_number:'TEST-CR-'+id}));
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
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('http://cmv-ui.test/**',async route=>{
   const url=new URL(route.request().url());const p=url.pathname;
   if(p==='/')return route.fulfill({contentType:'text/html',body:fs.readFileSync(path.join(base,'app/ui.html'),'utf8')});
   if(p==='/study_ui.js')return route.fulfill({contentType:'application/javascript',body:fs.readFileSync(path.join(base,'app/study_ui.js'),'utf8')});
   const method=route.request().method();let result={};
   if(p==='/api/patients')result=people;
   else if(p==='/api/authentication-policy')result={password_only:true,shared_clinical_workspace:true};
   else if(/^\/api\/patients\/TEST-P-/.test(p))result={patient:people.find(x=>x.id===p.split('/')[3]),entries:[]};
   else if(p==='/api/trial/subjects')result=subjects;
   else if(p==='/api/trial/eligibility-schema')result={inclusion:{},exclusion:{}};
   else if(p.endsWith('/context')){
    contextReads.push(p);
    const id=p.includes('/patients/')?Number(p.match(/TEST-P-(\d+)/)[1]):Number(p.split('/')[5]);
    result={subject:subjects[id-1],patient_id:'TEST-P-'+id,transplant_on:'2026-10-01',
      allocation:{randomized:true,allocation_code:'TEST-ALLOC-'+id,...(blinded?{}:{assigned_arm_mg:id===1?'450':'900'})}};
   }else if(p.endsWith('/pcr')){
    const sid=Number(p.split('/')[4]);result={pcr_records:[{id:sid*10+1,status:'planned',specimen_code:'TEST-PCR-'+sid,scheduled_month:1,target_on:'2026-11-01'}]};
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
  await page.evaluate(async()=>{
   $('workspace').classList.remove('hide');$('loginPanel').classList.add('hide');
   $('currentRole').textContent='nurse';applyRoleUI('nurse');await tab('study');
  });
  assert.deepEqual(errors,[],'Actual deferred script must initialize without JavaScript errors');
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
  await page.selectOption('#tw-context-subject','3');
  await page.waitForFunction(()=>$('tw-context-subject').value==='3'&&$('tw-collect-id').value==='');
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
  assert.deepEqual(errors,[]);
  console.log('Real browser passed: scripts, patient identity, source-date autosave, cross-patient draft isolation, allocation persistence, mobile layout and blinded banner');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
