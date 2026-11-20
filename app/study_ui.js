/* Structured clinical-trial workspace; no sensitive browser persistence. */
(function(){
'use strict';
var root=$('workspace'),menu=root.querySelector('.tabs');
var logoutBtn=Array.from(menu.querySelectorAll('button')).find(x=>x.textContent.trim()==='Log out');
var studySubjects=[],pcrRecords=[],drugLots=[],pcrLoadedSubject=null,drugLoadedSubject=null;
var lastIssuedSlip=null;
function txt(s){return escapeHTML(String(s==null?'':s));}
function value(id){return ($(id).value||'').trim();}
function n(id){return Number(value(id));}
function today(){return new Date().toLocaleDateString('en-CA',{timeZone:'Asia/Kolkata'});}
function fill(id,records,key,render){
 var el=$(id),prior=el.value;
 el.innerHTML='<option value="">Choose…</option>'+records.map(x=>'<option value="'+txt(x[key])+'">'+txt(render(x))+'</option>').join('');
 if(prior)el.value=prior;
 if(!el.value&&records.length)el.value=String(records[0][key]);
}
function error(id,e){
 let message=e.message||String(e);
 try {
  const issues=JSON.parse(message);
  if(Array.isArray(issues)){
   message=issues.map(x=>{
    const field=Array.isArray(x.loc)?x.loc[x.loc.length-1]:'field';
    if(field==='username')return 'Username: use at least 3 letters/numbers; it will be stored in lowercase (example: saisree).';
    if(field==='display_name')return 'Staff name: enter the person’s name (at least 3 characters).';
    if(field==='role')return 'Select an authorized delegated role.';
    return String(field)+': '+(x.msg||'Invalid entry');
   }).join(' ');
  }
 }catch(_ignored){}
 show(id,message,true);
}
function notify(id,s){show(id,s,false);}
async function task(id,callback){try{await callback();}catch(e){error(id,e);}}
function panel(id,title,html){
 var page=document.createElement('div');
 page.id=id;page.className='panel hide';
 page.style.cssText='grid-column:2;min-width:0;padding:22px;';
 page.innerHTML='<h2>'+title+'</h2><p class="hint">NIMS CMV trial · enter source-verified records and submit for source review.</p>'+html;
 root.appendChild(page);
 var button=document.createElement('button');button.id='btn'+id;
 button.textContent=title;button.onclick=()=>{void tab(id)};
 menu.insertBefore(button,logoutBtn);
}
var field=(title,id,type='text')=>'<label>'+title+'<input id="'+id+'" type="'+type+'"></label>';
var choose=(title,id,opts)=>'<label>'+title+'<select id="'+id+'">'+opts.map(o=>'<option value="'+o[0]+'">'+o[1]+'</option>').join('')+'</select></label>';
var btn=(label,id)=>'<button id="'+id+'">'+label+'</button>';
panel('tasks','Daily worklist',
 '<p class="hint">Actionable items from saved trial records. Dates are scheduled targets, not approved visit windows. No entries or allocations are created by opening an item.</p>'+
 '<div class="worklist-controls"><label>Filter actions<select id="tw-task-filter">'+
 '<option value="">All actions</option><option value="Enrollment">Screening and enrollment</option>'+
 '<option value="Randomization">Randomization</option><option value="PCR">CMV PCR</option>'+
 '<option value="eCRF">eCRF review / corrections</option><option value="SAE">Safety reporting checks</option></select></label>'+
 btn('Refresh worklist','tw-task-refresh')+'</div>'+
 '<div id="tw-task-counts" class="worklist-summary" aria-live="polite"></div>'+
 '<div id="tw-task-items"></div><div id="tw-task-status" class="status hide"></div>'
);
panel('study','Enrollment',
 '<div class="study-columns"><section class="study-card"><h3>1 · Screening</h3>'+
 choose('Registry record','tw-patient',[])+field('Screening date','tw-screen-date','date')+
 field('Informed consent signed','tw-consent-date','date')+
 field('Signed ICF version','tw-icf')+field('Signed PIS version','tw-pis')+
 choose('Consent language','tw-consent-language',[['','Select recorded language'],['English','English'],['Telugu','Telugu'],['Hindi','Hindi']])+
 field('Consent obtained by','tw-consent-obtained')+
 field('Participant initials (restricted)','tw-initials')+
 field('Age at transplant (years)','tw-screen-age','number')+
 choose('Sex (source record)','tw-sex',[['','Not recorded'],['female','Female'],['male','Male'],['other','Other']])+
 choose('Donor CMV IgG','tw-digg',[['','Select verified result'],['positive','Positive'],['negative','Negative'],['unknown','Unknown / not available']])+
 choose('Recipient CMV IgG','tw-rigg',[['','Select verified result'],['positive','Positive'],['negative','Negative'],['unknown','Unknown / not available']])+
 choose('Donor type','tw-donor',[['','Select verified donor type'],['living','Living'],['deceased','Deceased']])+
 choose('Donor relationship','tw-relationship',[['','Select verified relationship'],['living_related','Living related'],
    ['living_unrelated','Living unrelated'],['deceased','Deceased']])+
 choose('rATG induction','tw-ratg',[['','Undocumented'],['true','Yes'],['false','No']])+

 btn('Save screening','tw-screen-save')+' '+btn('Record consent declined','tw-decline-consent')+'</section>'+
 '<section class="study-card"><h3>2 · Protocol inclusion/exclusion checklist</h3>'+
 choose('Screened subject','tw-checklist-subject',[])+
 '<div id="tw-eligibility-fields">Select a subject and complete all protocol criteria.</div>'+
 field('Age at randomization (years)','tw-age','number')+
 field('ANC (/µL)','tw-anc','number')+field('Platelets (/µL)','tw-platelets','number')+
 field('Hemoglobin (g/dL)','tw-hb','number')+
 field('Cockcroft–Gault CrCl (mL/min)','tw-crcl','number')+
 field('CBC date','tw-cbc-date','date')+field('Investigator review date','tw-review-on','date')+
 btn('Validate complete eligibility checklist','tw-checklist-save')+'</section>'+
 '<section class="study-card"><h3>3 · Enrollment verification</h3>'+
 choose('Screened subject','tw-screened',[])+field('Enrollment date','tw-enroll-date','date')+
 field('Approved PCR anchor date','tw-anchor-date','date')+
 choose('Protocol PCR anchor','tw-anchor-basis',[['transplant_date','Transplant date only (protocol v5.0)']])+
 '<label><input type="checkbox" id="tw-pi-consent" style="width:auto"> I confirm signed consent, eligibility, CMV status and transplant date for follow-up.</label>'+

 '<p class="hint">A permanent Study ID (for example, NCMV001) will be generated by the server on approved enrollment. Screening does not assign a Study ID.</p>'+
 '<div id="tw-assigned-study-id" class="status" role="status" aria-live="polite">Study ID pending approved enrollment.</div>'+
 btn('Confirm enrollment and proceed to randomization','tw-enroll-save')+'</section></div>'+
 '<section class="study-card" id="tw-inline-rand-panel"><h3>4 · Randomization</h3>'+
 '<p id="tw-inline-rand-status" class="hint" role="status">Complete enrollment to enable randomization.</p>'+
 '<label><input id="tw-inline-rand-confirm" type="checkbox" style="width:auto"> I confirm the participant identity, signed consent, completed eligibility and donor/induction stratum.</label>'+
 btn('Confirm and randomize','tw-inline-rand-submit')+'</section>'+
 btn('Advanced randomization view','tw-enroll-randomize')+
 '<h3>Screening and enrollment register</h3><div id="tw-register"></div><div id="tw-status" class="status hide"></div>'
);
panel('pcr','CMV PCR',
 choose('Enrolled subject','tw-pcr-subject',[])+
 '<h3>Seven protocol timepoints and repeat specimens</h3><div id="tw-pcr-table"></div>'+
 '<section class="study-card"><h3>Microbiology specimen requisition</h3>'+
 '<p class="hint">Print an individual coded requisition for an existing protocol specimen. Printing does not record collection or laboratory completion.</p>'+
 choose('Scheduled PCR specimen','tw-pcr-print-id',[])+btn('Print coded PCR requisition','tw-pcr-print')+'</section>'+
 '<div class="study-columns"><section class="study-card"><h3>Specimen collection</h3>'+
 choose('Planned specimen','tw-collect-id',[])+field('Collection date','tw-collected','date')+
 field('Lab accession reference','tw-accession')+btn('Record collection','tw-collect-save')+
 '</section><section class="study-card"><h3>Laboratory result</h3>'+
 choose('Collected specimen','tw-result-id',[])+field('Reported date','tw-reported','date')+
 field('Assay/platform','tw-assay')+
 choose('Result category','tw-result-kind',[['','Select reported category'],['not_detected','Not detected'],['quantified','Quantified'],['detected_below_loq','Below quantification'],['invalid','Invalid']])+
 field('CMV viral load (IU/mL; quantified only)','tw-viral-load','number')+
 field('Lower limit (IU/mL; if known)','tw-loq','number')+
 choose('Laboratory QC','tw-qc',[['','Select reported QC'],['pass','Pass'],['fail','Fail']])+
 field('Correction reason (if editing result)','tw-result-reason')+
 btn('Submit lab result for verification','tw-result-save')+'</section></div>'+
 '<section class="study-card"><h3>Source review</h3>'+
 choose('Submitted result','tw-verify-id',[])+field('Signed source review reason','tw-review-reason')+
 btn('Verify result','tw-verify-save')+'</section><div id="tw-pcr-status" class="status hide"></div>'
);
panel('drug','MSS drug accountability',
 choose('Enrolled subject','tw-drug-subject',[])+
 '<div id="tw-drug-allocation" class="hint">No randomized allocation verified.</div>'+
 '<div class="study-columns"><section class="study-card"><h3>Receive valganciclovir stock</h3>'+
 field('Batch/lot reference','tw-lot')+field('Received on','tw-receipt-date','date')+
 field('Expires on','tw-expiry','date')+field('Number of 450 mg tablets','tw-received','number')+
 btn('Receive stock','tw-stock-save')+'</section>'+
 '<section class="study-card"><h3>Authorize against signed clinical order</h3>'+
 field('Paper prescription reference','tw-rx')+field('Signed date','tw-rx-date','date')+
 field('Independently verified allocation reference','tw-allocation')+
 field('Renal adjustment assessment reference','tw-renal')+
 field('Prescribed dosing instruction','tw-instruction')+
 btn('Record prescription authorization','tw-auth-save')+'</section>'+
 '<section class="study-card"><h3>Issue study medication</h3>'+
 choose('Authorized order for this participant','tw-order-id',[])+
 choose('Stock lot','tw-lot-id',[])+field('Issue date','tw-issue-date','date')+
 field('Number of tablets','tw-issued','number')+btn('Issue and generate MSS slip','tw-dispense-save')+
 '</section><section class="study-card"><h3>Record returned medication</h3>'+
 choose('Dispense entry for this participant','tw-dispense-id',[])+
 field('Returned quantity','tw-return-qty','number')+field('Returned date','tw-return-date','date')+
 choose('Disposition','tw-disposition',[['quarantine','Quarantine'],['destruction_pending','Destruction pending'],['destroyed','Destroyed']])+
 btn('Record return without restocking','tw-return-save')+'</section></div>'+
 '<div class="study-card"><h3>Accountability ledger</h3><div id="tw-ledger"></div></div>'+
 '<div class="study-card"><h3>MSS issue slip</h3><div id="tw-slip">Generate a confirmed issue to print and sign.</div>'+
 btn('Print confirmed MSS slip','tw-mss-print')+'</div>'+
 '<div id="tw-drug-status" class="status hide"></div>'
);
panel('crf','Structured eCRF and clinical logs',
 choose('Study participant','tw-crf-subject',[])+
 choose('CRF section','tw-crf-section',[])+
 '<p class="hint" id="tw-crf-descriptor">C–L map to CRF v3.0. M–P add dated source details for clinical care already received; they do not add mandatory tests or alter treatment.</p>'+
 '<label>Event/assessment date<input type="date" id="tw-crf-date"></label>'+
 '<div id="tw-crf-fields" class="study-columns"></div>'+
 '<div id="tw-crf-source" class="study-card hide" aria-live="polite"></div>'+
 btn('Use reviewed eligibility measurements','tw-crf-source-copy')+
 '<div id="tw-crf-draft-status" class="status">No draft loaded.</div>'+
 '<label>Correction reason (required only when revising submitted form)<input id="tw-crf-reason"></label>'+
 btn('Save private working draft','tw-crf-save')+' '+
 btn('Submit form for source review','tw-crf-submit')+
 '<div class="study-card"><h3>Submitted forms and review states</h3>'+
 '<div id="tw-crf-entries"></div></div>'+
 '<div id="tw-crf-status" class="status hide"></div>'
);
panel('randomization','Concealed randomization',
 '<div class="study-card"><h3>1:1 concealed assignment</h3>'+
 '<p class="hint">Variable permuted blocks stratified by rATG (yes/no) × living/deceased donor. '+
 'The next assignment is released after enrollment and recorded eligibility. Each participant receives one permanent allocation.</p>'+
 '<div id="tw-rand-overview" class="hint">Checking signed sequence readiness…</div></div>'+
 '<div class="study-card" id="tw-rand-registry-panel"><h3>Find registered patient by CR number</h3>'+
 field('Search hospital CR number, name or study ID','tw-rand-search','search')+
 btn('Fetch registry records','tw-rand-fetch')+
 choose('Registry patient · CR number','tw-rand-patient',[])+
 '<p id="tw-rand-progress" class="hint" role="status">Choose a registered patient. Screening and enrollment status will appear here.</p>'+
 btn('Continue selected patient to enrollment','tw-rand-continue')+'</div>'+
 '<div class="study-card" id="tw-rand-assign-panel"><h3>Release next concealed allocation</h3>'+
 choose('Enrolled participant · CR number / study ID','tw-rand-subject',[])+
 '<div id="tw-rand-subject-status" class="hint">Choose an eligible enrolled subject.</div>'+
 '<label><input type="checkbox" id="tw-rand-eligibility-confirm" style="width:auto"> '+
 'I confirm signed consent and all eligibility criteria, including induction and donor type.</label>'+
 btn('Confirm and randomize participant','tw-rand-assign')+
 '<p class="hint">A single irreversible allocation is released. Nominal arms require Cockcroft–Gault renal adjustment and a separate signed prescription.</p></div>'+
 '<div class="study-card" id="tw-rand-custodian-panel"><h3>Independent statistician/custodian only</h3>'+
 '<p class="hint">Upload the signed allocation package generated independently offline. '+
 'Only its fingerprint and stratum capacities are displayed; future treatment groups are never shown. '+
 'A plan cannot be replaced, edited or regenerated after locking.</p>'+
 '<label>Locally held signed sequence JSON<input id="tw-rand-file" type="file" accept=".json,application/json"></label>'+
 '<div id="tw-rand-file-info" class="hint">No confidential sequence uploaded.</div>'+
 '<p class="hint">Before import or generation, reconcile any earlier worksheet allocations against signed source records. Never rerandomize an existing participant. Include this reconciliation reference in an imported package.</p>'+
 btn('Permanently lock signed sequence','tw-rand-lock')+'<hr><h4>Generate and lock here</h4><p>The independent custodian must personally approve the final specification before the first randomization. Future allocations are never displayed.</p>'+field('Custodian name and appointment reference','tw-rand-custodian-ref')+field('Signed final specification reference','tw-rand-spec-ref')+field('Prior-allocation reconciliation / no prior enrollment signed reference','tw-rand-reconcile-ref')+field('Prespecified variable block sizes (comma separated)','tw-rand-sizes')+'<label><input id="tw-rand-independent" type="checkbox"> I am independently appointed and do not determine eligibility.</label>'+btn('Generate and permanently lock official sequence','tw-rand-generate')+'</div>'+
 '<div class="study-card" id="tw-rand-groups-panel"><h3>Independent custodian: realized balance only</h3>'+
 '<div id="tw-rand-groups" class="hint">Only assigned participants are counted.</div></div>'+
 '<div id="tw-rand-status" class="status hide" role="status"></div>'
);
panel('security','Account security',
 '<div class="study-card"><h3>Register two-factor authenticator</h3>'+
 '<p class="hint">Use a trusted authenticator application. Treat the setup secret as a password; never share it or post it into chat.</p>'+
 btn('Generate private authenticator secret','tw-mfa-setup')+
 '<div id="tw-mfa-secret" class="status hide" style="white-space:pre-wrap"></div>'+
 field('Enter a current 6-digit authenticator code','tw-mfa-code')+
 btn('Confirm and enable authenticator','tw-mfa-confirm')+
 '<div id="tw-mfa-status" class="status hide"></div></div>'+
 '<div class="study-card"><h3>Change my password</h3>'+
 '<label>Current password<input type="password" id="tw-oldpassword" autocomplete="current-password"></label>'+
 '<label>New password<input type="password" id="tw-newpassword" autocomplete="new-password"></label>'+
 field('Authenticator code if enabled','tw-password-otp')+btn('Change password and sign out all devices','tw-change-password')+'</div>'
);
panel('staff','Staff access',
 '<div class="study-card"><h3>Individual account invitation</h3>'+
 '<label>Unique username (e.g., saisree)<input id="tw-username" type="text" minlength="3" maxlength="100" autocapitalize="off" spellcheck="false" autocomplete="off" placeholder="saisree"></label>'+
 field('Staff name','tw-fullname')+
 choose('Delegated role','tw-role',[['scientist','Project scientist'],['nurse','Research nurse'],['technician','Lab technician'],['microbiology','Microbiology'],['pharmacy','MSS pharmacist'],['consultant','Consultant'],['pg','PG resident'],['monitor','CRA / monitor'],['randomization_custodian','Independent allocation custodian (admin invitation only)']])+
 btn('Generate one-time staff activation','tw-invite-save')+
 '<div id="tw-invitation" class="status hide" style="white-space:pre-wrap"></div></div>'+
 '<div class="study-card"><h3>Bulk provision 1–15 staff</h3>'+
 '<p class="hint">One per line: unique_username | Staff full name | delegated_role. Each receives a separate private activation; no shared passwords. Roles: scientist, nurse, technician, microbiology, pharmacy, consultant, pg, monitor.</p>'+
 '<textarea id="tw-bulk-input" rows="7" placeholder="username | Name | role"></textarea>'+
 btn('Generate named invitations for this batch','tw-bulk-save')+
 '<pre id="tw-bulk-result" class="status hide" style="white-space:pre-wrap;overflow:auto"></pre></div>'+
 '<div class="study-card"><h3>Named staff · 90-day authorization</h3><p class="hint">Each person keeps their own password. Access expires after 90 days, with investigator-controlled renewal or immediate revocation.</p><div id="tw-accounts"></div></div>'+
 '<p class="hint">Each person activates their account and chooses a private password. Never share a common account. Use your individual username and password. Account access remains administrator-controlled.</p>'+
 '<div id="tw-staff-status" class="status hide"></div>'
);
var css=document.createElement('style');
css.textContent='.study-columns{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.study-card{padding:18px;margin:12px 0;border:1px solid #e3eaf4;border-radius:12px}.study-card h3{margin-top:0}.study-columns input[type=checkbox]{width:auto}.study-columns label{margin-bottom:8px}#tw-pcr-table,#tw-register,#tw-ledger{overflow:auto}#tw-pcr-table table,#tw-register table,#tw-ledger table{border-collapse:collapse;width:100%;font-size:12px}#tw-pcr-table td,#tw-pcr-table th,#tw-register td,#tw-register th,#tw-ledger td,#tw-ledger th{border-bottom:1px solid #e6ebf2;padding:9px;text-align:left;white-space:nowrap}@media(max-width:860px){.study-columns{grid-template-columns:1fr}#workspace>#study,#workspace>#pcr,#workspace>#drug,#workspace>#staff{grid-column:1!important}}';
document.head.appendChild(css);
var loginPanelElement=$('loginPanel');
loginPanelElement.insertAdjacentHTML('beforeend','<hr><h3>Activate individual staff account</h3>'+
 field('One-time activation token','tw-token')+
 '<label>Choose a private password<input type="password" id="tw-password" autocomplete="new-password"></label>'+
 btn('Activate account','tw-activate-save')+'<div id="tw-activate-status" class="status hide"></div>');
for(const id of ['tw-screen-date','tw-consent-date','tw-enroll-date','tw-anchor-date','tw-collected','tw-reported','tw-receipt-date','tw-rx-date','tw-issue-date','tw-return-date'])$(id).value=today();
var perms={tasks:['pi','consultant','scientist','nurse','pg','technician','microbiology','pharmacy','monitor','admin'],randomization:['pi','consultant','pharmacy','scientist','monitor','randomization_custodian'],crf:['pi','consultant','scientist','nurse','pg','technician','microbiology','pharmacy','monitor'],study:['pi','consultant','scientist'],pcr:['pi','consultant','scientist','nurse','technician','microbiology','monitor'],drug:['pi','consultant','scientist','pharmacy','monitor'],staff:['pi','admin'],security:['pi','admin','consultant','pg','scientist','nurse','technician','microbiology','pharmacy','monitor','randomization_custodian']};
function setRole(){
 var r=$('currentRole').textContent.trim();
 for(const k of Object.keys(perms))$('btn'+k).classList.toggle('hide',!perms[k].includes(r));
 if($('tw-role')){
   const option=Array.from($('tw-role').options).find(o=>o.value==='randomization_custodian');
   if(option)option.disabled=!window.currentAdmin;
 }
 if(r==='randomization_custodian'){
   for(const btn of menu.querySelectorAll('button')){
     if(!['btnrandomization','btnsecurity'].includes(btn.id) && btn!==logoutBtn){
       btn.classList.add('hide');
     }
   }
 }
 for(const [id,roles] of [
  ['tw-screen-save',['pi','consultant','scientist']],['tw-checklist-save',['pi','consultant']],['tw-enroll-save',['pi']],
  ['tw-collect-save',['pi','consultant','scientist','nurse','technician','microbiology']],
  ['tw-result-save',['microbiology','technician']],
  ['tw-verify-save',['pi','consultant','scientist','monitor']],
  ['tw-stock-save',['pharmacy']],['tw-auth-save',['pi','consultant']],
  ['tw-dispense-save',['pharmacy']],['tw-return-save',['pharmacy']],
  ['tw-invite-save',['pi','admin']]
 ])$(id).classList.toggle('hide',!roles.includes(r)&&!window.currentWorkspaceFullAccess);
 if(window.currentWorkspaceFullAccess){
  $('btnstaff').classList.toggle('hide',!window.currentAdmin&&!window.currentPiAuthorized);
  const option=Array.from($('tw-role').options).find(o=>o.value==='randomization_custodian');
  if(option){option.disabled=true;option.hidden=true;}
 }
 $('tw-mfa-setup').closest('.study-card').classList.toggle('hide',!!window.passwordOnlyLogin);
 $('tw-password-otp').parentElement.classList.toggle('hide',!!window.passwordOnlyLogin);
}
var originalApply=applyRoleUI;
applyRoleUI=function(role){originalApply(role);setRole();};
var oldTab=tab;
tab=async function(name){
 if(activeTab==='crf'&&name!=='crf'){
  try{await crfSaveDraft();}catch(e){show('tw-crf-status','Cannot leave CRF with unsaved changes: '+e.message,true);return;}
 }
 if(activeTab==='staff'&&name!=='staff'){
  $('tw-invitation').textContent='';$('tw-invitation').classList.add('hide');
  $('tw-bulk-result').textContent='';$('tw-bulk-result').classList.add('hide');
 }
 if(['tasks','study','pcr','drug','staff','security','crf','randomization'].includes(name)){
  if(activeTab==='entry'){try{await saveDraftNow();}catch(e){show('msg','Draft not saved: '+e.message,true);return;}}
  activeTab=name;
  for(const section of ['dashboard','registry','review','entry','dose','due','tasks','study','pcr','drug','staff','security','crf','randomization']){
   $(section).classList.toggle('hide',section!==name);
   $('btn'+section).classList.toggle('selected',section===name);
  }
  root.querySelector('.grid').classList.add('hide');
  await task(name==='pcr'?'tw-pcr-status':name==='drug'?'tw-drug-status':name==='randomization'?'tw-rand-status':'tw-status',async()=>{
   if(name==='tasks'){await loadTasks();}
    if(name==='study'){
     $('tw-assigned-study-id').textContent='Study ID: loading selected participant…';
     await loadRegistry();await loadSubjects();await loadEligibilitySchema();await selectEnrollmentPatient();
     await refreshInlineRandomization();
   }
   if(name==='pcr'){await loadSubjects();await loadPCR();}
   if(name==='drug'){await loadSubjects();await loadDrug();}
   if(name==='staff'){await loadAccounts();}
   if(name==='randomization'){await loadRandomization();}
   if(name==='crf'){await loadSubjects();await loadCrfSchema();await loadCrfEntries();}
  });
 }else{
  await oldTab(name);
  // An older asynchronous dashboard load may finish after a newer tab opens.
  // Never let that stale completion hide the newly selected study panel.
  if(activeTab!==name)return;
  for(const k of Object.keys(perms)){$(k).classList.add('hide');$('btn'+k).classList.remove('selected');}
 }
};
function registryLabel(p){return (p.cr_number?'CR '+p.cr_number+' · ':'')+(p.name||'')+(p.study_id?' · '+p.study_id:'');}
function subjectLabel(s){return (s.cr_number?'CR '+s.cr_number+' · ':'')+(s.study_code||s.screening_code)+' · '+s.status;}
async function loadRegistry(){
 const people=await api('/api/patients?limit=100');
 // A selected patient may be outside the newest 100 records; fetch that record
 // explicitly instead of silently falling back to another person's first row.
 if(selected&&!people.some(p=>p.id===selected)){
  people.unshift((await api('/api/patients/'+encodeURIComponent(selected))).patient);
 }
 fill('tw-patient',people,'id',registryLabel);
 $('tw-patient').value=selected||'';
}
function showEnrollmentStudyId(){
 // Only the authoritative selected registry patient may supply this label;
 // never fall back to a prior form value while the next context is loading.
 const subject=studySubjects.find(s=>s.patient_id===selected);
 $('tw-assigned-study-id').textContent=subject?.study_code?
  'Study ID: '+subject.study_code+' · permanently assigned at approved enrollment.':
  'Study ID: pending · automatically assigned only after enrollment is approved.';
}
async function selectEnrollmentPatient(){
 $('tw-patient').value=selected||'';
 showEnrollmentStudyId();
 const subject=studySubjects.find(s=>s.patient_id===selected);
 for(const id of ['tw-screened','tw-checklist-subject'])$(id).value=subject?.status==='screened'?String(subject.id):'';
 if(participantContext?.patient_id===selected&&participantContext.transplant_on)$('tw-anchor-date').value=participantContext.transplant_on;
 await loadEligibilityReview();
}
$('tw-patient').onchange=()=>{void task('tw-status',async()=>{
 const id=value('tw-patient');
 if(!id){clearParticipant();await selectEnrollmentPatient();return;}
 await window.choose(id);await selectEnrollmentPatient();
});};
async function loadSubjects(){
 const gathered=[];let before=null;
 for(let page=0;page<100;page++){
  const records=await api('/api/trial/subjects?limit=200'+(before?'&before_id='+before:''));
  gathered.push(...records);
  if(records.length<200)break;
  const next=records[records.length-1].id;
  if(before!==null&&next>=before)throw Error('Participant paging cursor did not advance');
  before=next;
 }
 studySubjects=gathered;
 fill('tw-screened',studySubjects.filter(x=>x.status==='screened'),'id',subjectLabel);
 fill('tw-checklist-subject',studySubjects.filter(x=>x.status==='screened'),'id',subjectLabel);
 var active=studySubjects.filter(x=>x.enrolled_on);
 for(const id of ['tw-pcr-subject','tw-drug-subject','tw-crf-subject','tw-rand-subject']){
  fill(id,id==='tw-rand-subject'?active.filter(x=>x.status==='enrolled'):active,'id',subjectLabel);$(id).value=participantSubject?String(participantSubject):'';
 }
 fill('tw-context-subject',studySubjects,'id',subjectLabel);
 $('tw-context-subject').value=participantSubject?String(participantSubject):'';
 $('tw-register').innerHTML='<table><thead><tr><th>CR number / Study code</th><th>Status</th><th>D+/R+</th><th>Signed consent</th></tr></thead><tbody>'+
 studySubjects.map(x=>'<tr><td>'+txt(subjectLabel(x))+'</td><td>'+txt(x.status)+'</td><td>'+String(x.d_plus_r_plus)+'</td><td>'+String(x.consent_recorded)+'</td></tr>').join('')+'</tbody></table>';
}
/* Patient-centred workflow: allocation remains a separate confirmed transaction
   within the enrollment page; never release it when enrollment is saved. */
let inlineRandomizationRequest=0;
async function refreshInlineRandomization(){
 const request=++inlineRandomizationRequest,patient=selected,sid=participantSubject;
 const target=$('tw-inline-rand-status'),button=$('tw-inline-rand-submit');
 button.disabled=true;$('tw-inline-rand-confirm').checked=false;
 const subject=studySubjects.find(x=>x.id===sid&&x.patient_id===patient);
 if(!subject){target.textContent='Select and screen this patient first.';return;}
 if(!subject.enrolled_on||subject.status!=='enrolled'){
  target.textContent='Enrollment must be confirmed before randomization.';return;
 }
 try{
  const allocation=await api('/api/trial/randomization/subjects/'+sid+'/allocation');
  if(request!==inlineRandomizationRequest||selected!==patient||participantSubject!==sid)return;
  if(allocation.randomized){
   target.textContent='Already randomized · '+allocation.allocation_code+'. A second allocation is not permitted.';
   return;
  }
  const check=await api('/api/trial/randomization/subjects/'+sid+'/preflight');
  if(request!==inlineRandomizationRequest||selected!==patient||participantSubject!==sid)return;
  target.textContent=check.ready?
   'Ready: '+subject.study_code+' · '+check.stratum+'. One irreversible concealed assignment will be released on confirmation.':
   'Not ready: '+check.reason;
  button.disabled=!check.ready;
 }catch(e){if(request===inlineRandomizationRequest){target.textContent=e.message;button.disabled=true;}}
}
$('tw-inline-rand-submit').onclick=()=>{void task('tw-status',async()=>{
 const sid=participantSubject,patient=selected,button=$('tw-inline-rand-submit');
 const subject=studySubjects.find(x=>x.id===sid&&x.patient_id===patient);
 if(!subject?.study_code||button.disabled)throw Error('Choose one enrolled participant with a ready randomization preflight');
 if(!$('tw-inline-rand-confirm').checked)
  throw Error('Confirm the signed consent, eligibility and stratum before randomization');
 if(!confirm('Randomize '+subject.study_code+' for CR '+subject.cr_number+'? The next concealed assignment cannot be undone.'))return;
 button.disabled=true;
 try{
  const r=await api('/api/trial/randomization/subjects/'+sid+'/assign',{
    method:'POST',body:JSON.stringify({investigator_confirmation:true,stratification_verified:true})
  });
  if(selected===patient){
   notify('tw-status','Randomized '+r.study_code+' · allocation '+r.allocation_code+
     ' · nominal '+r.assigned_arm_mg+' mg OD. Use the signed renal-adjusted prescription for dispensing.');
   await loadSubjects();await selectParticipantSubject(sid);await refreshInlineRandomization();
   window.dispatchEvent(new Event('cmv:workflow-updated'));
  }
 }catch(e){await refreshInlineRandomization();throw e;}
 });};

/* Action worklist: read-only navigation, never an allocation/clinical write. */
var taskEntries=[];
async function loadTasks(){
 const r=await api('/api/trial/action-worklist?limit=200');
 taskEntries=r.actions||[];
 const summary=$('tw-task-counts');
 summary.textContent=r.total+' outstanding action(s) · '+r.as_of+' · '+Object.entries(r.counts||{})
   .map(([name,count])=>name+': '+count).join(' · ');
 renderTasks();
}
function renderTasks(){
 const filter=value('tw-task-filter').toLowerCase();
 const items=taskEntries.filter(a=>!filter||
   (filter==='enrollment' && /eligibility|enrollment/i.test(a.category))||
   a.category.toLowerCase().includes(filter));
 $('tw-task-items').innerHTML=items.length?items.map((a,i)=>
  '<article class="worklist-item"><div><span class="worklist-category">'+txt(a.category)+'</span>'+
  '<strong>'+txt(a.study_code||'Screened participant')+'</strong>'+
  '<p>'+txt(a.detail)+'</p>'+
  (a.target_on?'<small>Scheduled target '+txt(a.target_on)+'</small>':'')+'</div>'+
  '<button class="secondary" data-task-idx="'+taskEntries.indexOf(a)+'" aria-label="Open '+txt(a.category)+' for '+txt(a.study_code)+'">Open</button></article>'
 ).join(''):'<p class="hint">No matching actions. This does not imply that all trial data are verified or complete.</p>';
}
$('tw-task-filter').onchange=renderTasks;
$('tw-task-refresh').onclick=()=>{void task('tw-task-status',loadTasks);};
$('tw-task-items').onclick=e=>{const btn=e.target.closest('[data-task-idx]');if(!btn)return;
 void task('tw-task-status',async()=>{
  const item=taskEntries[Number(btn.dataset.taskIdx)];
  if(!item)throw Error('Refresh the worklist before opening this item');
  await window.choose(item.patient_id);
  if(selected!==item.patient_id)throw Error('Patient context changed; select the action again');
  await tab(item.route==='randomization'?'study':item.route);
 });
};

async function loadPCR(){
 const sid=n('tw-pcr-subject');resetPCRControls();if(!sid)return;
 if(!await selectParticipantSubject(sid))return;
 const contextVersion=participantRequest;
 const records=(await api('/api/trial/subjects/'+sid+'/pcr')).pcr_records;
 if(contextVersion!==participantRequest||sid!==participantSubject||sid!==n('tw-pcr-subject'))return;
 pcrRecords=records;pcrLoadedSubject=sid;
 $('tw-pcr-table').innerHTML='<table><thead><tr><th>Code</th><th>Month</th><th>Target</th><th>Status</th><th>Viral load (IU/mL)</th></tr></thead><tbody>'+
 pcrRecords.map(x=>'<tr><td>'+txt(x.specimen_code)+'</td><td>'+x.scheduled_month+'</td><td>'+txt(x.target_on)+'</td><td>'+txt(x.status)+'</td><td>'+txt(x.quantitative_iu_ml??'—')+'</td></tr>').join('')+'</tbody></table>';
 fill('tw-pcr-print-id',pcrRecords.filter(x=>x.attempt===1),'id',
   x=>x.specimen_code+' · Month '+x.scheduled_month+' · '+x.status);
 $('tw-pcr-print').disabled=!n('tw-pcr-print-id');
 fill('tw-collect-id',pcrRecords.filter(x=>x.status==='planned'),'id',x=>x.specimen_code);
 fill('tw-result-id',pcrRecords.filter(x=>['collected','result_entered','verified'].includes(x.status)),'id',x=>x.specimen_code);
 fill('tw-verify-id',pcrRecords.filter(x=>x.status==='result_entered'),'id',x=>x.specimen_code);
 for(const [button,selection] of [['tw-collect-save','tw-collect-id'],['tw-result-save','tw-result-id'],['tw-verify-save','tw-verify-id']])$(button).disabled=!n(selection);
}
async function loadDrug(){
 const sid=n('tw-drug-subject');drugLoadedSubject=null;
 for(const id of ['tw-auth-save','tw-dispense-save','tw-return-save'])$(id).disabled=true;
 if(!sid){resetDrugControls();return;}
 if(!await selectParticipantSubject(sid))return;
 const contextVersion=participantRequest;
 if(['pharmacy','scientist','pi','monitor','admin'].includes($('currentRole').textContent.trim())){
  drugLots=await api('/api/trial/pharmacy/lots');
  fill('tw-lot-id',drugLots,'id',x=>x.lot_number+' ('+x.quantity_on_hand+' remaining)');
 }
 var p=await api('/api/trial/subjects/'+sid+'/pharmacy');
 if(contextVersion!==participantRequest||sid!==participantSubject||sid!==n('tw-drug-subject'))return;
 if(['pi','consultant','pharmacy'].includes($('currentRole').textContent.trim())){
   const allocation=await api('/api/trial/randomization/subjects/'+sid+'/allocation');
   if(contextVersion!==participantRequest||sid!==participantSubject||sid!==n('tw-drug-subject'))return;
   const banner=$('tw-drug-allocation');
   if(banner)banner.textContent=allocation.randomized?
    'Verified assignment '+allocation.allocation_code+' · nominal '+allocation.assigned_arm_mg+' mg OD (renal-adjusted prescribing required)':
    'No randomized allocation: prescriptions and dispensing must not proceed.';
   if(allocation.randomized)$('tw-allocation').value=allocation.allocation_code;
 }
 $('tw-ledger').innerHTML='<table><thead><tr><th>MSS slip code</th><th>Issued</th><th>Returned</th><th>Unreconciled</th></tr></thead><tbody>'+
 p.dispenses.map(x=>'<tr><td>'+txt(x.slip_code)+'</td><td>'+x.quantity_issued+'</td><td>'+x.total_returned+'</td><td>'+x.remaining_unreconciled+'</td></tr>').join('')+'</tbody></table>';
 drugLoadedSubject=sid;
 fill('tw-order-id',p.orders||[],'id',x=>x.prescription_ref+(x.authorized_dose_instruction?' · '+x.authorized_dose_instruction:''));
 fill('tw-dispense-id',p.dispenses||[],'id',x=>x.slip_code+' · '+x.remaining_unreconciled+' unreconciled');
 for(const id of ['tw-auth-save','tw-dispense-save','tw-return-save'])$(id).disabled=false;
}
$('tw-pcr-subject').onchange=()=>{void task('tw-pcr-status',loadPCR);};
$('tw-drug-subject').onchange=()=>{void task('tw-drug-status',loadDrug);};
/* Keep the next clinical step physically visible, even if async status checks
   are still completing. This never submits a form or releases an allocation. */
function openStudyStage(number){
 const step=$('tw-progress-step-'+number);
 if(!step)return false; // legacy UI without progressive wrapper
 for(const item of document.querySelectorAll('#study .tw-progress-stage'))item.open=item===step;
 step.scrollIntoView({block:'nearest'});
 return true;
}
$('tw-screen-save').onclick=()=>{void task('tw-status',async()=>{
 for(const [id,label] of [['tw-digg','donor CMV IgG'],['tw-rigg','recipient CMV IgG'],['tw-donor','donor type']])
   if(!value(id))throw Error('Select the source-verified '+label+'; an unassessed default is not permitted');
  var r=await api('/api/trial/screening',{method:'POST',body:JSON.stringify({
  patient_id:value('tw-patient'),screening_on:value('tw-screen-date'),consent_on:value('tw-consent-date')||null,
  consent_version:value('tw-icf')||null,donor_cmv_igg:value('tw-digg'),recipient_cmv_igg:value('tw-rigg'),
  donor_type:value('tw-donor'),donor_relationship:value('tw-relationship'),
  participant_initials:value('tw-initials')||null,
  age_at_transplant:value('tw-screen-age')?n('tw-screen-age'):null,
  sex_at_birth:value('tw-sex')||null,pis_version:value('tw-pis')||null,
  consent_language:value('tw-consent-language')||null,
  consent_obtained_by:value('tw-consent-obtained')||null,
  signed_consent_source_ref:null,
  ratg_induction:value('tw-ratg')===''?null:value('tw-ratg')==='true',
  eligibility_attested:false})});
 notify('tw-status','Screening code '+r.screening_code+' assigned. Complete the eligibility checklist, then enrollment.');
 await loadSubjects();await selectParticipantSubject(r.id);await selectEnrollmentPatient();
 openStudyStage(2);
 window.dispatchEvent(new Event('cmv:workflow-updated'));
 if(!$('tw-progress-step-2'))$('tw-checklist-subject').scrollIntoView({block:'center'});
});};
$('tw-decline-consent').onclick=()=>{void task('tw-status',async()=>{
 const subject=studySubjects.find(x=>x.patient_id===selected&&x.status==='screened');
 if(!subject)throw Error('Save screening for this patient before recording consent declined');
 if(subject.consent_recorded)throw Error('Signed consent is already recorded; verify the existing source before changing status');
 if(!confirm('Mark the selected screened patient as consent declined? No enrollment or randomization will occur.'))return;
 await api('/api/trial/subjects/'+subject.id+'/consent-declined',{
  method:'POST',body:JSON.stringify({confirmed:true})});
 notify('tw-status','Consent declined recorded. This screening remains in the audit history and is excluded from enrollment.');
 await loadSubjects();await selectEnrollmentPatient();
 window.dispatchEvent(new Event('cmv:workflow-updated'));
});};

$('tw-enroll-save').onclick=()=>{void task('tw-status',async()=>{
 var id=n('tw-screened');if(!id)throw Error('Select a screened subject');
 var r=await api('/api/trial/subjects/'+id+'/enroll',{method:'POST',body:JSON.stringify({
  enrolled_on:value('tw-enroll-date'),pcr_anchor_on:value('tw-anchor-date'),
  pcr_anchor_basis:value('tw-anchor-basis'),
  reviewed_eligibility_and_consent:$('tw-pi-consent').checked,approved_visit_anchor:$('tw-pi-consent').checked})});
 notify('tw-status','Enrollment approved. Study ID '+(r.study_id||r.subject.study_code)+' assigned permanently; seven PCR orders generated. Continue to randomization.');
 await loadSubjects();
 showEnrollmentStudyId();
 await selectParticipantSubject(r.subject.id);
 await refreshInlineRandomization();
 openStudyStage(4);
 window.dispatchEvent(new Event('cmv:workflow-updated'));
 if(!$('tw-progress-step-4'))$('tw-inline-rand-panel').scrollIntoView({block:'center'});
});};
$('tw-collect-save').onclick=()=>{void task('tw-pcr-status',async()=>{
 requireProcedureSubject('pcr');
 if(!pcrRecords.some(x=>x.id===n('tw-collect-id')&&x.status==='planned'))throw Error('Choose a planned specimen for this participant');
 var r=await api('/api/trial/pcr/'+n('tw-collect-id')+'/collect',{method:'POST',
  body:JSON.stringify({collected_on:value('tw-collected'),lab_accession:value('tw-accession')})});
 notify('tw-pcr-status','Collected '+r.specimen_code);await loadPCR();
});};
$('tw-result-save').onclick=()=>{void task('tw-pcr-status',async()=>{
 requireProcedureSubject('pcr');
 var r=pcrRecords.find(x=>x.id===n('tw-result-id'));if(!r)throw Error('Select a collected specimen');
 var updated=await api('/api/trial/pcr/'+r.id+'/result',{method:'PUT',body:JSON.stringify({
  expected_revision:r.revision,reported_on:value('tw-reported'),assay_platform:value('tw-assay'),
  result_kind:value('tw-result-kind'),quantitative_iu_ml:value('tw-viral-load')?n('tw-viral-load'):null,
  lower_limit_iu_ml:value('tw-loq')?n('tw-loq'):null,qc_status:value('tw-qc'),
  correction_reason:value('tw-result-reason')||null})});
 notify('tw-pcr-status',updated.specimen_code+' result saved, awaiting source review');await loadPCR();
});};
$('tw-verify-save').onclick=()=>{void task('tw-pcr-status',async()=>{
 requireProcedureSubject('pcr');
 var r=pcrRecords.find(x=>x.id===n('tw-verify-id'));if(!r)throw Error('Select submitted result');
 var verified=await api('/api/trial/pcr/'+r.id+'/verify',{method:'POST',body:JSON.stringify({
  expected_revision:r.revision,review_reason:value('tw-review-reason')})});
 notify('tw-pcr-status',verified.specimen_code+' source verified by the named reviewer');await loadPCR();
});};
$('tw-stock-save').onclick=()=>{void task('tw-drug-status',async()=>{
 var r=await api('/api/trial/pharmacy/lots',{method:'POST',body:JSON.stringify({
  lot_number:value('tw-lot'),expiry_on:value('tw-expiry'),received_on:value('tw-receipt-date'),
  strength_mg:450,quantity_received:n('tw-received')})});
 notify('tw-drug-status','Lot '+r.lot_id+' received: '+r.remaining+' tablets');await loadDrug();
});};
$('tw-auth-save').onclick=()=>{void task('tw-drug-status',async()=>{
 requireProcedureSubject('drug');
 var r=await api('/api/trial/subjects/'+n('tw-drug-subject')+'/drug-authorization',{method:'POST',
  body:JSON.stringify({prescription_ref:value('tw-rx'),signed_on:value('tw-rx-date'),
   allocation_reference:value('tw-allocation'),renal_assessment_ref:value('tw-renal'),
   authorized_dose_instruction:value('tw-instruction')})});
 notify('tw-drug-status','Authorized order reference '+r.id);await loadDrug();$('tw-order-id').value=String(r.id);
});};
$('tw-dispense-save').onclick=()=>{void task('tw-drug-status',async()=>{
 requireProcedureSubject('drug');
 var r=await api('/api/trial/subjects/'+n('tw-drug-subject')+'/dispense',{method:'POST',
  body:JSON.stringify({authorization_id:n('tw-order-id'),lot_id:n('tw-lot-id'),
   quantity_issued:n('tw-issued'),issued_on:value('tw-issue-date')})});
 lastIssuedSlip=Object.freeze({...r,issued_on:value('tw-issue-date'),
   prescription_ref:($('tw-order-id').selectedOptions[0]?.textContent||'').split(' · ')[0]});
 $('tw-mss-print').disabled=false;
 $('tw-slip').innerHTML='<h3>NIMS · ICMR CMV STUDY · MSS SIGNATURE SLIP</h3>'+
  '<p>Study ID: '+txt(r.study_code)+' | Slip code: '+txt(r.slip_code)+'</p>'+
  '<p>Valganciclovir 450 mg tablets | Quantity issued: '+r.quantity_issued+'</p>'+
  '<p>Lot: '+txt(r.lot_number)+' | Expiry: '+txt(r.expiry_on)+'</p>'+
  '<p>Prescriber signature: ____________________</p><p>Pharmacist signature: ____________________</p>'+
  '<p>Recipient signature: ____________________  Date: ______________</p>'+
  '<p class="hint">Valid only with checked signed prescription and allocation.</p>';
 notify('tw-drug-status','Issued '+r.slip_code+'. Print the slip and obtain physical signatures.');await loadDrug();
});};
$('tw-return-save').onclick=()=>{void task('tw-drug-status',async()=>{
 requireProcedureSubject('drug');
 var r=await api('/api/trial/pharmacy/dispenses/'+n('tw-dispense-id')+'/return',{method:'POST',
  body:JSON.stringify({quantity_returned:n('tw-return-qty'),returned_on:value('tw-return-date'),
   disposition:value('tw-disposition')})});
 notify('tw-drug-status','Returned quantity recorded. Remaining unreconciled: '+r.unreconciled_quantity);await loadDrug();
});};
$('tw-invite-save').onclick=()=>{void task('tw-staff-status',async()=>{
 const username=value('tw-username').toLowerCase();
 const display_name=value('tw-fullname');
 if(!/^[a-z][a-z0-9_.-]{2,99}$/.test(username))
  throw Error('Enter a unique username of at least 3 characters, beginning with a letter (e.g., saisree).');
 if(display_name.length<3)throw Error('Enter the full staff name (at least 3 characters).');
 var r=await api('/api/trial/staff/invite',{method:'POST',body:JSON.stringify({
  username,display_name,role:value('tw-role')})});
 $('tw-invitation').classList.remove('hide');
 $('tw-invitation').textContent='Private activation for '+r.username+' ('+r.role+')\n'+
 r.activation_token+'\nInitial invitation expires in 7 days. After activation the staff account remains valid for 90 days. Hand the code privately.';
 notify('tw-staff-status','Inactive named account created. Activated access lasts 90 days.');
 await loadAccounts();
});};

$('tw-bulk-save').onclick=()=>{void task('tw-staff-status',async()=>{
 const lines=value('tw-bulk-input').split(/\r?\n/).map(x=>x.trim()).filter(Boolean);
 if(!lines.length||lines.length>15)throw Error('Enter 1–15 distinct named staff records');
 const staff=lines.map(line=>{
  const parts=line.split('|').map(x=>x.trim());
  if(parts.length!==3||parts.some(x=>!x))throw Error('Use username | Staff full name | delegated role');
  const [entered,display_name,role]=parts;
  const username=entered.toLowerCase();
  if(!/^[a-z][a-z0-9_.-]{2,99}$/.test(username))throw Error('Invalid username: '+entered+'. Use at least 3 letters/numbers, starting with a letter.');
  if(display_name.length<3)throw Error('Full staff name required for '+username);
  if(!['scientist','nurse','technician','microbiology','pharmacy','consultant','pg','monitor'].includes(role))
   throw Error('Unrecognized delegated role: '+role);
  return {username,display_name,role};
 });
 if(new Set(staff.map(x=>x.username)).size!==staff.length)
  throw Error('The batch includes the same username twice; remove duplicates.');
 if(!confirm('Create '+staff.length+' inactive named accounts and one-time personal activation tokens?'))return;
 const result=await api('/api/trial/staff/invite-batch',{
  method:'POST',body:JSON.stringify({staff})
 });
 const container=$('tw-bulk-result');container.classList.remove('hide');
 container.textContent=result.invitations.map(x=>
  x.display_name+' | '+x.username+' | '+x.role+
  '\nPRIVATE ONE-TIME TOKEN: '+x.activation_token+
  '\nInitial activation within 7 days; thereafter 90-day account access.\n'
 ).join('\n');
 $('tw-bulk-input').value='';
 notify('tw-staff-status',result.created+' named inactive accounts created. Distribute codes individually to identified staff.');
 await loadAccounts();
});};
$('tw-activate-save').onclick=()=>{void task('tw-activate-status',async()=>{
 var r=await api('/api/trial/staff/activate',{method:'POST',body:JSON.stringify({
  token:value('tw-token'),password:value('tw-password')})});
 $('tw-token').value='';$('tw-password').value='';
 notify('tw-activate-status','Account '+r.username+' activated for 90 days. Sign in above.');
});};

$('tw-mfa-setup').onclick=()=>{void task('tw-mfa-status',async()=>{
 var r=await api('/api/trial/staff/mfa-setup',{method:'POST'});
 $('tw-mfa-secret').classList.remove('hide');
 $('tw-mfa-secret').textContent='Private authenticator secret:\n'+r.secret+
 '\nEnter this in your authenticator app, then confirm the generated code below.';
 notify('tw-mfa-status','Confirm your code before logging out.');
});};
$('tw-mfa-confirm').onclick=()=>{void task('tw-mfa-status',async()=>{
 var r=await api('/api/trial/staff/mfa-confirm',{method:'POST',
  body:JSON.stringify({otp:value('tw-mfa-code')})});
 $('tw-mfa-code').value='';$('tw-mfa-secret').textContent='';
 $('tw-mfa-secret').classList.add('hide');
 location.reload();
});};

let eligibilityItems=null;
let eligibilityRequest=0;
async function loadEligibilityReview(){
 const request=++eligibilityRequest,sid=n('tw-checklist-subject');
 for(const el of document.querySelectorAll('[data-eligibility]'))el.value='';
 for(const id of ['tw-age','tw-anc','tw-platelets','tw-hb','tw-crcl','tw-cbc-date'])$(id).value='';
 $('tw-review-on').value=today();
 if(!sid)return;
 const r=await api('/api/trial/subjects/'+sid+'/eligibility');
 if(request!==eligibilityRequest||sid!==n('tw-checklist-subject'))return;
 const e=r.eligibility;
 if(!e){prefillObjectiveEligibility();return;}
 for(const el of document.querySelectorAll('[data-eligibility]')){
  const v=e[el.dataset.eligibility]?.[el.dataset.key];el.value=typeof v==='boolean'?String(v):'';
 }
 const b=e.baseline||{};
 for(const [id,key] of Object.entries({'tw-age':'age_years','tw-anc':'anc_per_ul','tw-platelets':'platelets_per_ul','tw-hb':'hemoglobin_g_dl','tw-crcl':'crcl_cg_ml_min','tw-cbc-date':'baseline_cbc_on'}))$(id).value=b[key]??'';
 $('tw-review-on').value=e.reviewed_on||today();
 prefillObjectiveEligibility();updateEligibilityProgress();
}
for(const id of ['tw-checklist-subject','tw-screened'])$(id).onchange=()=>{void task('tw-status',async()=>{
 const sid=n(id);if(!sid)return;
 await selectParticipantSubject(sid);await selectEnrollmentPatient();
});};
/* Full signed checklist retained, grouped for quick, accountable review. */
function updateEligibilityProgress(){
 for(const group of ['inclusion','exclusion']){
  const controls=[...document.querySelectorAll('[data-eligibility="'+group+'"]')];
  const done=controls.filter(x=>x.value!=='').length,total=controls.length;
  const label=$('tw-review-'+group+'-count');
  if(label)label.textContent=done+' / '+total+' reviewed'+(done===total?' ✓':'');
  const wrap=$('tw-review-'+group+'-group');
  if(wrap)wrap.dataset.complete=String(done===total);
 }
 const done=[...document.querySelectorAll('[data-eligibility]')].filter(x=>x.value!=='').length;
 const total=document.querySelectorAll('[data-eligibility]').length;
 const status=$('tw-eligibility-progress');
 if(status)status.textContent=done+' of '+total+
  ' items assessed · verify all source records before approving eligibility.';
}
async function loadEligibilitySchema(){
 eligibilityItems=await api('/api/trial/eligibility-schema');
 const makeFields=(group,items,label)=>{
  return '<details class="tw-eligibility-group" id="tw-review-'+group+'-group" open>'+
   '<summary><span>'+label+'</span><strong id="tw-review-'+group+
     '-count">0 / '+Object.keys(items).length+' reviewed</strong></summary>'+
   '<div class="tw-eligibility-grid">'+Object.entries(items).map(([key,description])=>
    '<label>'+txt(description)+'<select data-eligibility="'+group+'" data-key="'+txt(key)+'">'+
    '<option value="">Not assessed</option><option value="true">Yes</option>'+
    '<option value="false">No</option></select></label>').join('')+'</div></details>';
 };
 $('tw-eligibility-fields').innerHTML=
  '<p class="hint">Source-verified values are suggested where available. Review all clinical criteria explicitly.</p>'+
  '<div class="tw-eligibility-progress" id="tw-eligibility-progress" role="status"></div>'+
  makeFields('inclusion',eligibilityItems.inclusion,'Inclusion criteria — all Yes')+
  makeFields('exclusion',eligibilityItems.exclusion,'Exclusion criteria — all No');
 for(const el of document.querySelectorAll('[data-eligibility]'))
  el.addEventListener('change',()=>{el.dataset.autoChecked='';updateEligibilityProgress();});
 prefillObjectiveEligibility();updateEligibilityProgress();
}
/* Populate only deterministic eligibility values from recorded source measurements.
   Clinical judgement criteria remain unanswered until a staff member reviews them. */
function prefillObjectiveEligibility(){
 const sid=n('tw-checklist-subject');
 const subject=studySubjects.find(x=>x.id===sid&&x.patient_id===selected);
 if(!subject)return;
 function set(group,key,result){
  if(result===null||result===undefined)return;
  const el=Array.from(document.querySelectorAll('[data-eligibility="'+group+'"]'))
   .find(x=>x.dataset.key===key);
  if(el&&(el.value===''||el.dataset.autoChecked==='yes')){
   el.value=String(Boolean(result));el.dataset.autoChecked='yes';
  }
 }
 function numeric(id){
  const entered=value(id);return entered===''?null:Number(entered);
 }
 const age=numeric('tw-age'),anc=numeric('tw-anc'),
  platelets=numeric('tw-platelets'),hb=numeric('tw-hb'),crcl=numeric('tw-crcl');
 if(age===null&&Number.isInteger(subject.age_at_transplant)){
  $('tw-age').value=String(subject.age_at_transplant);
 }
 const confirmedAge=numeric('tw-age');
 if(confirmedAge!==null)set('inclusion','age_ge_18',confirmedAge>=18);
 if(anc!==null)set('inclusion','anc_ge_1500',anc>=1500);
 if(platelets!==null)set('inclusion','platelets_ge_50000',platelets>=50000);
 if(hb!==null)set('inclusion','hemoglobin_ge_7',hb>=7);
 if(anc!==null&&platelets!==null&&hb!==null)
  set('exclusion','blood_counts_below_threshold',anc<1500||platelets<50000||hb<7);
 if(crcl!==null)set('exclusion','crcl_below_10',crcl<10);
 if(['positive','negative'].includes(subject.donor_cmv_igg))
  set('inclusion','donor_cmv_positive',subject.donor_cmv_igg==='positive');
 if(['positive','negative'].includes(subject.recipient_cmv_igg))
  set('inclusion','recipient_cmv_positive',subject.recipient_cmv_igg==='positive');
 if(typeof subject.consent_recorded==='boolean')
  set('inclusion','written_consent',subject.consent_recorded);
 updateEligibilityProgress();
}
for(const id of ['tw-age','tw-anc','tw-platelets','tw-hb','tw-crcl'])
 $(id).addEventListener('input',prefillObjectiveEligibility);
$('tw-checklist-save').onclick=()=>{void task('tw-status',async()=>{
 if(!eligibilityItems)await loadEligibilitySchema();
 const subject=n('tw-checklist-subject');if(!subject)throw Error('Select a screened subject');
 const make=(group,items)=>{
  const result={};
  for(const key of Object.keys(items)){
   const el=Array.from(document.querySelectorAll('[data-eligibility="'+group+'"]'))
    .find(e=>e.dataset.key===key);
   if(!el||el.value==='')throw Error('Complete every inclusion and exclusion item before review');
   result[key]=el.value==='true';
  }return result;
 };
 const r=await api('/api/trial/subjects/'+subject+'/eligibility',{
  method:'PUT',body:JSON.stringify({
   inclusion:make('inclusion',eligibilityItems.inclusion),
   exclusion:make('exclusion',eligibilityItems.exclusion),
   age_years:n('tw-age'),anc_per_ul:n('tw-anc'),
   platelets_per_ul:n('tw-platelets'),hemoglobin_g_dl:n('tw-hb'),
   crcl_cg_ml_min:n('tw-crcl'),baseline_cbc_on:value('tw-cbc-date'),
   reviewed_on:value('tw-review-on')
  })});
 notify('tw-status',r.eligible?
  'Eligible. Confirm enrollment below to generate the Study ID and proceed to randomization.':
  'Not eligible. Enrollment and randomization are unavailable.');
 if(r.eligible)openStudyStage(3);
 window.dispatchEvent(new Event('cmv:workflow-updated'));
 if(r.eligible&&!$('tw-progress-step-3'))$('tw-enroll-save').scrollIntoView({block:'center'});
});};
$('tw-cbc-date').value=''; // Laboratory source date must be entered explicitly.
$('tw-review-on').value=today(); // Review is an action performed now.
async function loadAccounts(){
 const accounts=await api('/api/trial/staff/accounts');
 $('tw-accounts').innerHTML='<div style="overflow-x:auto"><table><thead><tr>'+
   '<th>Username / name</th><th>Role</th><th>Valid until</th><th>MFA</th><th>State</th><th>Actions</th>'+
   '</tr></thead><tbody>'+
   accounts.map(x=>{
    const state=x.status||(x.active?'active':'awaiting_activation');
    const actions= x.active ?
      '<button data-staff-id="'+txt(x.id)+'" data-staff-action="renew" class="secondary">Renew 90 days</button> '+
      '<button data-staff-id="'+txt(x.id)+'" data-staff-action="revoke">Revoke</button>' :
      state==='revoked' ?
      '<button data-staff-id="'+txt(x.id)+'" data-staff-action="reissue" data-restoring="true" class="secondary">Reinstate + new activation</button>' :
      '<button data-staff-id="'+txt(x.id)+'" data-staff-action="reissue" data-restoring="false" class="secondary">Reissue activation</button>';
    return '<tr><td><strong>'+txt(x.username)+'</strong><div class="hint">'+txt(x.display_name)+'</div></td>'+
    '<td>'+txt(x.role)+'</td>'+
    '<td>'+txt(x.active&&x.access_expires_at?x.access_expires_at.slice(0,10):'—')+'</td>'+
    '<td>'+(x.mfa_enabled?'Enabled':'Not yet')+'</td>'+
    '<td>'+txt(state.replaceAll('_',' '))+'</td><td>'+actions+'</td></tr>';
   }).join('')+'</tbody></table></div>';
}
$('tw-accounts').addEventListener('click',e=>{
 const button=e.target.closest('button[data-staff-action]');if(!button)return;
 const action=button.dataset.staffAction,id=button.dataset.staffId;
 const reinstating=button.dataset.restoring==='true';
 const promptText=action==='reissue'?(reinstating?
   'This account was previously revoked. Explicitly approve reinstatement with a new one-time activation code?':
   'Issue a fresh private activation code; old codes will become invalid?'):
  action==='revoke'?'Immediately revoke this account and end all sessions?':
   'Authorize this person for another 90 days and end current sessions?';
 if(!confirm(promptText))return;
 void task('tw-staff-status',async()=>{
  const explanation=prompt('Enter an audit reason (at least 8 characters):');
  if(explanation===null)return;
  if(explanation.trim().length<8)throw Error('Audit reason must have at least 8 characters.');
  const data=action==='reissue'?
   {reason:explanation.trim(),restore_revoked:reinstating}:
   {reason:explanation.trim()};
  const result=await api('/api/trial/staff/accounts/'+encodeURIComponent(id)+'/'+action,
   {method:'POST',body:JSON.stringify(data)});
  if(action==='reissue'){
   $('tw-invitation').classList.remove('hide');
   $('tw-invitation').textContent='PRIVATE new activation for '+result.username+' ('+result.role+
     ')\n'+result.activation_token+
     '\nThis one-time code expires in 7 days. On activation, personal access lasts 90 days.'+
     '\nGive only to the identity-verified named staff member. Do not share their password.';
   notify('tw-staff-status','Fresh activation generated for '+result.username+
      '. Give the private code to that person and ask them to choose their own password on the login page.');
  }else{
   notify('tw-staff-status',result.username+' — '+(action==='renew'?
     '90-day access renewed':'Access revoked'));
  }
  await loadAccounts();
 });
});
$('tw-username').addEventListener('blur',()=>{
 $('tw-username').value=value('tw-username').toLowerCase();
});
$('tw-change-password').onclick=()=>{void task('tw-mfa-status',async()=>{
 const result=await api('/api/trial/staff/change-password',{method:'POST',body:JSON.stringify({
  old_password:value('tw-oldpassword'),new_password:value('tw-newpassword'),
  otp:value('tw-password-otp')||null})});
 $('tw-oldpassword').value='';$('tw-newpassword').value='';$('tw-password-otp').value='';
 notify('tw-mfa-status','Password changed; all sessions revoked. Please sign in with your new password.');
});};


/* Source-aligned CRF forms with private, revision-checked server drafts. */
let currentCrfSchema=null,currentCrfSpec=null,currentCrfEntry=null;
let baselineSource=null,baselineSourceRequest=0;
let crfLoadedSection=null,crfLoadedSubject=null;
let crfDraftRevision=null,crfDraftKey=null,crfDraftLast=null,crfDraftTimer=null,crfDraftQueue=Promise.resolve();
const crfEditable={
 C_baseline:['pi','consultant','scientist'],
 D_adherence:['pi','consultant','scientist','nurse','pharmacy'],
 E_followup:['pi','consultant','scientist','nurse','pg'],
 F_unscheduled_pcr:['pi','consultant','scientist','microbiology','technician'],
 G_cmv_event:['pi','consultant','scientist'],
 H_adverse_event:['pi','consultant','scientist','nurse'],
 I_clinical_outcome:['pi','consultant','scientist','nurse','pg'],
 J_deviation:['pi','consultant','scientist'],
 K_resource_cost:['pi','scientist','pharmacy'],
 L_final_status:['pi','consultant','scientist']
 ,M_medication:['pi','consultant','scientist','nurse','pg']
 ,N_laboratory:['pi','consultant','scientist','nurse','pg','microbiology','technician']
 ,O_infection:['pi','consultant','scientist','nurse','pg']
 ,P_transplant:['pi','consultant','scientist','nurse','pg']
};
const crfCanEdit=()=>crfEditable[crfLoadedSection||value('tw-crf-section')]?.includes($('currentRole').textContent.trim());
const crfKey=()=>{
 if(!currentCrfSpec)return 'NEW';
 if(currentCrfSpec.repeat==='single')return 'MAIN';
 if(currentCrfSpec.repeat==='month'){
  const month=document.querySelector('#tw-crf-fields [data-crf-field="scheduled_month"]')?.value;
  return month?'M'+month.padStart(2,'0'):'NEW';
 }
 return 'NEW';
};
function crfValues(){
 const payload={};
 if(!currentCrfSpec)throw Error('Choose a CRF section first');
 for(const [key,spec] of Object.entries(currentCrfSpec.fields)){
  const control=Array.from($('tw-crf-fields').querySelectorAll('[data-crf-field]'))
   .find(el=>el.dataset.crfField===key);
  if(!control)continue;
  const val=control.value.trim();
  if(val==='')continue;
  if(spec.type==='integer'){
   if(!Number.isInteger(Number(val)))throw Error('Whole number expected for '+spec.label);
   payload[key]=Number(val);
  }else if(spec.type==='number'){
   if(!Number.isFinite(Number(val)))throw Error('Numeric entry expected for '+spec.label);
   payload[key]=Number(val);
  }else payload[key]=val;
 }
 return payload;
}
function crfSetValues(payload){
 for(const el of $('tw-crf-fields').querySelectorAll('[data-crf-field]')){
  const v=payload?.[el.dataset.crfField];
  el.value=v===undefined||v===null?'':String(v);
 }
}
function crfCurrentData(){
 if(!(crfLoadedSubject||n('tw-crf-subject'))||!(crfLoadedSection||value('tw-crf-section')))throw Error('Select subject and CRF section');
 if(!value('tw-crf-date'))throw Error('Event date required');
 const payload=crfValues();
 const primary={M_medication:'start_on',N_laboratory:'sample_on',O_infection:'onset_on'}[crfLoadedSection];
 if(primary&&payload[primary])$('tw-crf-date').value=payload[primary];
 return {occurred_on:value('tw-crf-date'),payload,occurrence_key:crfKey()};
}
async function crfSaveDraft(){
 clearTimeout(crfDraftTimer);
 if(!crfLoadedSubject||!crfLoadedSection)return;
 if(!crfCanEdit())return;
 const snapshot=crfCurrentData();
 const body=JSON.stringify(snapshot);
 if(body===crfDraftLast||(!Object.keys(snapshot.payload).length&&crfDraftRevision===null))return;
 const subjectId=crfLoadedSubject||n('tw-crf-subject');
 const section=crfLoadedSection||value('tw-crf-section'),key=snapshot.occurrence_key;
 const endpoint='/api/trial/crf/subjects/'+subjectId+'/drafts/'+encodeURIComponent(section);
 crfDraftQueue=crfDraftQueue.catch(()=>{}).then(async()=>{
  const r=await api(endpoint,{method:'PUT',
    body:JSON.stringify({...snapshot,expected_revision:crfDraftKey===key?crfDraftRevision:null})});
  if(n('tw-crf-subject')===subjectId&&value('tw-crf-section')===section&&crfKey()===key){
   crfDraftKey=key;crfDraftRevision=r.revision;crfDraftLast=body;
   $('tw-crf-draft-status').textContent='Saved on server · private revision '+r.revision+
      ' · not yet part of submitted CRF';
  }
 });
 try{await crfDraftQueue;}
 catch(e){$('tw-crf-draft-status').textContent='DRAFT UNSAVED: '+e.message;throw e;}
}
async function crfRestoreDraft(){
 clearTimeout(crfDraftTimer);
 crfDraftRevision=null;crfDraftKey=null;crfDraftLast=null;
 const savedMonth=currentCrfSpec?.repeat==='month' ?
    document.querySelector('#tw-crf-fields [data-crf-field="scheduled_month"]')?.value:null;
 crfSetValues({});
 if(savedMonth){const control=document.querySelector('#tw-crf-fields [data-crf-field="scheduled_month"]');if(control)control.value=savedMonth;}
 $('tw-crf-date').value=today();
 if(!crfCanEdit()){$('tw-crf-draft-status').textContent='Read-only review access';return;}
 if(!n('tw-crf-subject')||!value('tw-crf-section'))return;
 const key=crfKey();
 const subjectId=n('tw-crf-subject'),section=value('tw-crf-section');
 const r=await api('/api/trial/crf/subjects/'+subjectId+
  '/drafts/'+encodeURIComponent(section)+
  '?occurrence_key='+encodeURIComponent(key));
 if(subjectId!==n('tw-crf-subject')||section!==value('tw-crf-section')||key!==crfKey())return;
 crfDraftKey=key;
 if(r.draft){
  crfSetValues(r.draft.payload);
  $('tw-crf-date').value=r.draft.occurred_on;
  crfDraftRevision=r.draft.revision;
  crfDraftLast=JSON.stringify({occurred_on:r.draft.occurred_on,
   payload:r.draft.payload,occurrence_key:key});
  $('tw-crf-draft-status').textContent='Private saved draft restored · revision '+r.draft.revision;
 }else $('tw-crf-draft-status').textContent='New private draft · autosaves after changes';
}
function crfScheduleSave(){
 clearTimeout(crfDraftTimer);
 if(!crfCanEdit())return;
 $('tw-crf-draft-status').textContent='Unsaved changes · server autosave pending';
 crfDraftTimer=setTimeout(()=>{void crfSaveDraft().catch(()=>{});},1300);
}

async function loadBaselineSource(){
 const request=++baselineSourceRequest;
 baselineSource=null;
 const card=$('tw-crf-source'),copy=$('tw-crf-source-copy');
 card.classList.add('hide');copy.classList.add('hide');
 if(crfLoadedSection!=='C_baseline'||!crfLoadedSubject)return;
 const allowed=['pi','consultant','scientist','monitor'].includes($('currentRole').textContent.trim());
 if(!allowed)return;
 try{
  const response=await api('/api/trial/subjects/'+crfLoadedSubject+'/eligibility');
  if(request!==baselineSourceRequest || crfLoadedSection!=='C_baseline' ||
     crfLoadedSubject!==n('tw-crf-subject'))return;
  const record=response.eligibility;
  if(!record||!record.baseline){card.textContent='No investigator-reviewed eligibility measurements are available.';card.classList.remove('hide');return;}
  baselineSource=record.baseline;
  const fields=[
   ['CBC date',baselineSource.baseline_cbc_on],
   ['ANC (/µL)',baselineSource.anc_per_ul],
   ['Platelets (/µL)',baselineSource.platelets_per_ul],
   ['Hemoglobin (g/dL)',baselineSource.hemoglobin_g_dl],
   ['Cockcroft–Gault CrCl (mL/min)',baselineSource.crcl_cg_ml_min],
   ['Eligibility signed source',baselineSource.signed_source_reference]
  ];
  card.innerHTML='<h3>Reviewed eligibility source · read-only</h3>'+
   '<p class="hint">Measurements below come from the eligibility checklist. They may not represent a different baseline date. They are never copied without explicit confirmation.</p>'+
   fields.map(([label,val])=>'<p><strong>'+txt(label)+':</strong> '+txt(val??'Not recorded')+'</p>').join('');
  card.classList.remove('hide');
  copy.classList.toggle('hide',!crfCanEdit());
 }catch(e){if(request===baselineSourceRequest){card.textContent='Eligibility source unavailable for this account.';card.classList.remove('hide');}}
}
$('tw-crf-source-copy').onclick=()=>{
 if(!baselineSource||crfLoadedSection!=='C_baseline'||!crfCanEdit())return;
 const sourceDate=baselineSource.baseline_cbc_on;
 if(sourceDate&&value('tw-crf-date')<sourceDate){
  error('tw-crf-status',Error('Baseline assessment date precedes the source laboratory date. Correct it before copying.'));return;
 }
 if(!confirm('Copy only currently BLANK measurements from the investigator-reviewed '+sourceDate+
    ' eligibility source into baseline? Verify that the same source results apply to this assessment date.'))return;
 const mapping={anc_per_ul:'anc_per_ul',platelets_per_ul:'platelets_per_ul',
  hemoglobin_g_dl:'hemoglobin_g_dl',crcl_cg_ml_min:'cockcroft_gault_crcl_ml_min'};
 for(const [src,dest] of Object.entries(mapping)){
  const node=$('twcrf-'+dest);
  if(node&&!node.value&&baselineSource[src]!==null&&baselineSource[src]!==undefined)
   node.value=String(baselineSource[src]);
 }
 crfScheduleSave();
 notify('tw-crf-status','Reviewed measurements copied into blank fields only. Verify clinical dates and sign the baseline source before submission.');
};
function crfRender(){
 currentCrfSpec=currentCrfSchema?.[value('tw-crf-section')]||null;
 crfLoadedSection=value('tw-crf-section');crfLoadedSubject=n('tw-crf-subject');
 currentCrfEntry=null;
 void loadBaselineSource();
 $('tw-crf-descriptor').textContent=currentCrfSpec?
  currentCrfSpec.title+' · '+currentCrfSpec.repeat+(currentCrfSpec.supplementary?
   ' · supplementary source-detail log (no additional mandatory investigations)':' · CRF v3.0 (14 August 2026)'):
  'Select one signed CRF section';
 $('tw-crf-fields').innerHTML=currentCrfSpec?
  Object.entries(currentCrfSpec.fields).map(([key,item])=>{
   const id='twcrf-'+key;
   let control;
   if(item.type==='select'){
    control='<select data-crf-field="'+txt(key)+'" id="'+txt(id)+'"><option value="">Not documented</option>'+
     (item.choices||[]).map(o=>'<option value="'+txt(o)+'">'+txt(o.replaceAll('_',' '))+'</option>').join('')+'</select>';
   }else if(item.type==='textarea'){
    control='<textarea id="'+txt(id)+'" data-crf-field="'+txt(key)+'" rows="2"></textarea>';
   }else{
    const type=['date','number','integer'].includes(item.type)?
     (item.type==='integer'?'number':item.type):'text';
    const step=item.type==='integer'?'1':item.type==='number'?'any':null;
    control='<input id="'+txt(id)+'" data-crf-field="'+txt(key)+'" type="'+type+'"'+
      (step?' step="'+step+'"':'')+
      (item.min!==undefined?' min="'+item.min+'"':'')+
      (item.max!==undefined?' max="'+item.max+'"':'')+'>';
   }
   return '<label class="study-card">'+txt(item.label)+(item.required?' *':'')+control+'</label>';
  }).join(''):'';
 $('tw-crf-save').classList.toggle('hide',!crfCanEdit());
 $('tw-crf-submit').classList.toggle('hide',!crfCanEdit());
}
async function loadCrfSchema(){
 const r=await api('/api/trial/crf/schema');
 currentCrfSchema=r.forms;
 fill('tw-crf-section',Object.entries(r.forms).map(([id,s])=>({id,title:s.title})),
     'id',x=>x.title);
 crfRender();await populateCrfLinkedIdentifiers();await crfRestoreDraft();
 if(n('tw-crf-subject'))await selectParticipantSubject(n('tw-crf-subject'));
}
async function loadCrfEntries(){
 const subject=n('tw-crf-subject');
 if(!subject){$('tw-crf-entries').textContent='Select a study participant';return;}
 const records=(await api('/api/trial/crf/subjects/'+subject+'/entries')).entries;
 if(subject!==n('tw-crf-subject'))return;
 $('tw-crf-entries').innerHTML='<div style="overflow-x:auto"><table><thead><tr>'+
  '<th>Section</th><th>Event</th><th>Occurrence</th><th>Status</th><th>Revision</th><th>Action</th>'+
  '</tr></thead><tbody>'+
  records.map(x=>'<tr><td>'+txt(x.section)+'</td><td>'+txt(x.occurred_on)+
   '</td><td>'+txt(x.occurrence_key)+'</td><td>'+txt(x.review_status)+
   '</td><td>'+x.revision+'</td><td>'+
   (crfEditable[x.section]?.includes($('currentRole').textContent.trim())?
    '<button class="secondary" data-crf-edit="'+x.id+'">Edit</button> ':'')+
   (x.review_status==='pending'&&x.updated_by!==undefined&&
    ['pi','consultant','scientist','monitor'].includes($('currentRole').textContent.trim())&&
    (window.currentWorkspaceFullAccess||x.updated_by!==$('currentUserId')?.value)?
    '<button data-crf-review="'+x.id+'">Review</button>':'')+'</td></tr>').join('')+
  '</tbody></table></div>';
 $('tw-crf-entries')._records=records;
}
$('tw-crf-section').onchange=()=>{void task('tw-crf-status',async()=>{
 try{await crfSaveDraft();}catch(e){throw Error('Cannot change form with unsaved data: '+e.message);}
 crfRender();await populateCrfLinkedIdentifiers();await crfRestoreDraft();await loadCrfEntries();
});};
$('tw-crf-subject').onchange=()=>{void task('tw-crf-status',async()=>{
 try{await crfSaveDraft();}catch(e){throw Error('Cannot change participant with unsaved data: '+e.message);}
 await selectParticipantSubject(n('tw-crf-subject'));
 crfRender();await populateCrfLinkedIdentifiers();await crfRestoreDraft();await loadCrfEntries();
});};
$('tw-crf-fields').addEventListener('input',crfScheduleSave);
$('tw-crf-fields').addEventListener('change',crfScheduleSave);
$('tw-crf-date').addEventListener('change',crfScheduleSave);
$('tw-crf-save').onclick=()=>{void task('tw-crf-status',async()=>{
 await crfSaveDraft();notify('tw-crf-status','Private server draft saved.');
});};
$('tw-crf-submit').onclick=()=>{void task('tw-crf-status',async()=>{
 await crfSaveDraft();
 const snapshot=crfCurrentData();
 if(!currentCrfEntry&&!confirm('Submit this CRF form for source verification?'))return;
 const isCorrection=!!currentCrfEntry;
 const body=isCorrection?{
    occurred_on:snapshot.occurred_on,payload:snapshot.payload,
    expected_revision:currentCrfEntry.revision,reason:value('tw-crf-reason')
  }:{section:value('tw-crf-section'),occurred_on:snapshot.occurred_on,
       payload:snapshot.payload};
 const url=isCorrection?'/api/trial/crf/entries/'+currentCrfEntry.id:
    '/api/trial/crf/subjects/'+n('tw-crf-subject')+'/entries';
 const result=await api(url,{method:isCorrection?'PUT':'POST',body:JSON.stringify(body)});
 notify('tw-crf-status',(isCorrection?'CRF correction':'CRF entry')+
  ' submitted, revision '+result.revision+' · source review pending');
 if(crfDraftRevision!==null){
  try{await api('/api/trial/crf/subjects/'+n('tw-crf-subject')+
     '/drafts/'+encodeURIComponent(value('tw-crf-section'))+
     '?occurrence_key='+encodeURIComponent(crfDraftKey)+
     '&expected_revision='+crfDraftRevision,{method:'DELETE'});}
  catch(e){notify('tw-crf-status','Submitted, but private draft cleanup needs attention: '+e.message);}
 }
 currentCrfEntry=null;crfDraftRevision=null;crfDraftKey=null;crfDraftLast=null;
 crfSetValues({});$('tw-crf-reason').value='';
 await loadCrfEntries();await crfRestoreDraft();
});};
$('tw-crf-entries').addEventListener('click',e=>{
 const edit=e.target.closest('button[data-crf-edit]');
 const review=e.target.closest('button[data-crf-review]');
 if(!edit&&!review)return;
 const id=Number((edit||review).dataset.crfEdit||(edit||review).dataset.crfReview);
 const row=($('tw-crf-entries')._records||[]).find(x=>x.id===id);
 if(!row)return;
 void task('tw-crf-status',async()=>{
  if(edit){
   if(value('tw-crf-section')!==row.section){
    $('tw-crf-section').value=row.section;crfRender();
   }
   currentCrfEntry=row;crfSetValues(row.payload);
   $('tw-crf-date').value=row.occurred_on;
   $('tw-crf-draft-status').textContent='Editing submitted entry '+id+
    ' · correction reason required · no change until explicit submission';
  }else{
   if(row.review_status!=='pending')throw Error('This revision has already been reviewed');
   const reason=prompt('Reason for CRF source review (minimum 8 characters):');
   if(!reason||reason.trim().length<8)return;
   const decision=confirm('Verify this record? Select Cancel to request correction.')?
     'verified':'needs_correction';
   const result=await api('/api/trial/crf/entries/'+id+'/review',{
     method:'POST',body:JSON.stringify({expected_revision:row.revision,decision,reason})});
   notify('tw-crf-status','Review recorded: '+result.review_status);
   await loadCrfEntries();
  }
 });
});


/* Clinical registration verification lives in the core page, which checks the
   server mode after login AND at every registration attempt. This external
   study workspace must not override or cache that safety check. */
const savedFinishLogin=window.finishLogin;
window.finishLogin=async function(r){
 await savedFinishLogin(r);
 if(!$('workspace').classList.contains('hide')&&
    $('currentRole').textContent.trim()==='randomization_custodian'){
    await tab('randomization');
 }else if(!$('workspace').classList.contains('hide')&&perms.course.includes($('currentRole').textContent.trim())){
    await loadSubjects();
 }
};
const originalStudyDashboard=loadDashboard;
loadDashboard=async function(){
 await originalStudyDashboard();
 const target=$('dashboardResults');
 try{
  const [trial,forms,actions,build]=await Promise.all([
   api('/api/trial/overview'),api('/api/trial/crf/completeness'),
   api('/api/trial/action-worklist?limit=8'),api('/healthz')
  ]);
  $('tw-live-build').textContent='Running server · '+(build.app_commit?
    'commit '+build.app_commit.slice(0,10):
    'build '+String(build.build_fingerprint||'unavailable').slice(0,12))+
    ' · '+(build.service||'mode unavailable');
  const lab=trial.pcr||{}, drug=trial.drug_accountability||{};
  const cards=[
   ['Screened',trial.screened,'Coded screening records'],
   ['Enrolled',trial.ever_enrolled,'Includes withdrawn/closed participants'],
   ['Randomized',trial.randomized,'Approved protocol recruitment target: 344; Study ID capacity: 350'],
   ['PCR scheduled',trial.scheduled_pcr_slots,'Seven protocol slots per enrolled subject'],
   ['PCR verified',trial.verified_protocol_pcr_slots,'Independent review completed'],
   ['Stock remaining',drug.tablets_in_stock,'450-mg tablets in study inventory'],
   ['Unreconciled issues',drug.tablets_not_yet_reconciled,'Not necessarily taken or lost']
  ];
  const kpi='<div class="dash-kpis">'+cards.map((x,i)=>
    '<div class="dash-card dash-kpi"><span class="accent" style="background:'+
    ['#405fe4','#27ba9c','#7460d9','#6e87bc','#2495aa','#ac8a37','#d77b42'][i]+'"></span>'+
    '<span class="num">'+Number(x[1]||0).toLocaleString('en-IN')+'</span>'+
    '<div class="label">'+txt(x[0])+'</div><div class="explain">'+txt(x[2])+'</div></div>'
  ).join('')+'</div>';
  const months=['1','2','3','4','6','9','12'];
  const rows=months.map(m=>{
   const slot=forms.visit_completion[m]||{};
   return '<tr><td>Month '+m+'</td><td>'+(slot.submitted||0)+'</td>'+
    '<td>'+(slot.verified||0)+'</td>'+
    '<td>'+(slot.needs_correction||0)+'</td></tr>';
  }).join('');
  const visits='<div class="dash-card" style="margin:16px 0">'+
   '<h3>Protocol follow-up completeness</h3>'+
   '<p class="dash-note">Count of submitted and source-verified CRF visits. PCR result verification is tracked separately.</p>'+
   '<div style="overflow-x:auto"><table style="width:100%;font-size:12px;border-collapse:collapse">'+
   '<thead><tr><th>Timepoint</th><th>Submitted</th><th>Verified</th><th>Needs correction</th></tr></thead>'+
   '<tbody>'+rows+'</tbody></table></div></div>';
  const note='<p class="warn-demo">Study status is computed from persisted records. '+
   'Enrollment and PCR completion do not imply endpoint adjudication or data lock. '+
   'Medication exposure, renal adjustment and adjudication require source verification.</p>';
  const operations='<div class="dash-card" style="margin:12px 0">'+
   '<h3>Actions requiring attention</h3><p class="dash-note">'+
   Number(actions.total||0)+' outstanding worklist item(s) · next '+Number((actions.actions||[]).length)+' shown. '+
   'Each item links to an existing participant; no actions are automatically approved.</p>'+
   (actions.actions||[]).slice(0,5).map(a=>'<p class="dash-note">'+
    '<strong>'+txt(a.study_code)+' · '+txt(a.category)+'</strong> · '+txt(a.detail)+'</p>').join('')+
   '<button id="tw-open-task-list" type="button">Open daily worklist</button></div>';
  target.insertAdjacentHTML('afterbegin',
    '<h3 style="margin-top:8px">Clinical trial progress</h3>'+note+kpi+operations+visits+
    '<h3 style="margin:20px 0 12px">Registry and entry-review activity</h3>');
  $('tw-open-task-list').onclick=()=>{void tab('tasks');};
 }catch(err){
  target.insertAdjacentHTML('afterbegin','<p class="dash-note">Clinical trial metrics unavailable: '+txt(err.message)+'</p>');
 }
};


async function populateCrfLinkedIdentifiers(){
 if(!currentCrfSpec||!crfLoadedSubject)return;
 let fieldName,values=[],render;
 if(crfLoadedSection==='E_followup'){
  fieldName='pcr_specimen_code';
  const r=await api('/api/trial/subjects/'+crfLoadedSubject+'/pcr');
  values=r.pcr_records||[];
  render=x=>x.specimen_code+' · month '+x.scheduled_month+' · '+x.status;
 }else if(crfLoadedSection==='D_adherence'){
  fieldName='dispensing_slip_code';
  const r=await api('/api/trial/subjects/'+crfLoadedSubject+'/pharmacy');
  values=r.dispenses||[];
  render=x=>x.slip_code+' · '+x.quantity_issued+' tablets issued';
 }else return;
 const previous=document.querySelector('#tw-crf-fields [data-crf-field="'+fieldName+'"]');
 if(!previous)return;
 const parent=previous.parentElement,initial=previous.value;
 const select=document.createElement('select');
 select.id=previous.id;select.setAttribute('data-crf-field',fieldName);
 select.innerHTML='<option value="">No linked record / not yet collected</option>'+
  values.map(x=>'<option value="'+txt(fieldName==='pcr_specimen_code'?x.specimen_code:x.slip_code)+'">'+
      txt(render(x))+'</option>').join('');
 parent.replaceChild(select,previous);
 if(initial)select.value=initial;
}


/* Independent, concealed sequence import and PI-only randomized assignment. */
let lockedSequenceFile=null,registrySearchRequest=0,registrySearchTimer;
async function loadRandomizationRegistry(){
 const request=++registrySearchRequest,q=value('tw-rand-search');
 const people=await api('/api/patients?limit=100&q='+encodeURIComponent(q));
 if(request!==registrySearchRequest)return;
 if(!q&&selected&&!people.some(p=>p.id===selected)){
  people.unshift((await api('/api/patients/'+encodeURIComponent(selected))).patient);
 }
 if(request!==registrySearchRequest)return;
 fill('tw-rand-patient',people,'id',registryLabel);
 $('tw-rand-patient').value=!q&&people.some(p=>p.id===selected)?selected:'';
 if(!$('tw-rand-patient').value){
  $('tw-rand-progress').textContent=people.length?'Select the matching CR number below. Up to 100 matches are shown; refine the search if needed.':'No registry record matches this search.';
  $('tw-rand-continue').disabled=true;
 }else updateRandomizationProgress();
}
function updateRandomizationProgress(){
 const patient=value('tw-rand-patient'),s=participantContext?.patient_id===patient?participantContext.subject:null;
 const target=$('tw-rand-progress');
 $('tw-rand-continue').disabled=!patient||s?.status==='enrolled';
 $('tw-rand-continue').textContent=s?'Continue to eligibility and enrollment':'Continue to screening';
 if(!patient){target.textContent='Choose a registry patient by CR number.';return;}
 const label=$('tw-rand-patient').selectedOptions[0]?.textContent||'';
 target.textContent=label+' · '+(!s?'Registered. Screening, consent, eligibility and enrollment have not yet been recorded.':
  s.status==='screened'?'Screened. Complete or review the eligibility checklist and approve enrollment before allocation.':
  s.status==='enrolled'?'Enrolled. Allocation status is shown below.':'Study status: '+s.status+'. New allocation is unavailable.');
 if(s&&s.status!=='enrolled')$('tw-rand-continue').disabled=s.status!=='screened';
}
function invalidateRandomizationSearch(){
 participantRequest++;$('tw-rand-patient').value='';$('tw-rand-continue').disabled=true;
 $('tw-rand-subject').value='';$('tw-rand-assign').disabled=true;
 $('tw-rand-subject-status').textContent='Select the matching CR number after searching.';
}
$('tw-rand-fetch').onclick=()=>{invalidateRandomizationSearch();clearTimeout(registrySearchTimer);void task('tw-rand-status',loadRandomizationRegistry);};
$('tw-rand-search').oninput=()=>{
 registrySearchRequest++;invalidateRandomizationSearch();
 clearTimeout(registrySearchTimer);registrySearchTimer=setTimeout(()=>{void task('tw-rand-status',loadRandomizationRegistry);},250);
};
$('tw-rand-patient').onchange=()=>{void task('tw-rand-status',async()=>{
 $('tw-rand-assign').disabled=true;
 const patient=value('tw-rand-patient');
 if(!patient){clearParticipant();updateRandomizationProgress();return;}
 await window.choose(patient);updateRandomizationProgress();await loadRandSubject();
});};
$('tw-rand-continue').onclick=()=>{void task('tw-rand-status',async()=>{
 const patient=value('tw-rand-patient');if(!patient)throw Error('Choose a registry CR number first');
 await window.choose(patient);await tab('study');
 (n('tw-checklist-subject')?$('tw-checklist-subject'):$('tw-patient')).scrollIntoView({block:'center'});
});};
async function loadRandomization(){
 clearTimeout(registrySearchTimer);$('tw-rand-search').value='';
 const role=$('currentRole').textContent.trim();
 const shared=!!window.currentWorkspaceFullAccess;
 const isCustodian=role==='randomization_custodian'&&!shared;
 $('tw-rand-assign-panel').classList.toggle('hide',role!=='pi'&&!shared);
 $('tw-rand-registry-panel').classList.toggle('hide',isCustodian);
 $('tw-rand-assign').disabled=true;
 // Shared accounts must explicitly provide an actual signed source and
 // verify eligibility and stratum; never silently synthesize a source.
 $('tw-rand-eligibility-confirm').parentElement.classList.remove('hide');
 $('tw-rand-custodian-panel').classList.toggle('hide',!isCustodian);
 $('tw-rand-groups-panel').classList.toggle('hide',!isCustodian);
 if(!isCustodian){
  await loadSubjects();
  await loadRandomizationRegistry();
  await loadRandSubject();
 }
 const r=await api('/api/trial/randomization/readiness');
 $('tw-rand-overview').textContent=
  (r.allocation_management==='owner_managed'?'Owner-managed allocation · no separate custodian approval. ':'')+
  'Trial randomization: '+(r.sequence_locked&&r.activation_ready?'ready':'unavailable')+
  ' · Randomized '+r.randomized+' of 344'+
  ' · '+(r.clinical_mode?'Clinical mode':'Test mode');
 if(isCustodian){
  const groups=await api('/api/trial/randomization/assigned-group-counts');
  $('tw-rand-groups').textContent=
   'Already randomized: '+groups.randomized+
   ' | 450-mg nominal group: '+groups.group_450+
   ' | 900-mg nominal group: '+groups.group_900+
   '. No undisclosed future allocations or block details are visible.';
 }
}
async function loadRandSubject(){
 const subject=n('tw-rand-subject'),searchVersion=registrySearchRequest;
 const target=$('tw-rand-subject-status');
 $('tw-rand-assign').disabled=true;
 if(!subject){target.textContent='No enrolled participant selected. Fetch the CR number above and continue any unfinished screening or enrollment.';return;}
 if(!await selectParticipantSubject(subject)||searchVersion!==registrySearchRequest)return;
 const request=participantRequest;
 const r=await api('/api/trial/randomization/subjects/'+subject+'/allocation');
 if(searchVersion!==registrySearchRequest||request!==participantRequest||subject!==participantSubject||subject!==n('tw-rand-subject'))return;
 if(Array.from($('tw-rand-patient').options).some(o=>o.value===selected))$('tw-rand-patient').value=selected;
 updateRandomizationProgress();
 // The server performs identical read-only prerequisite checks for the UI
 // and for irreversible allocation. No future arm is read or returned.
 const check=r.randomized?null:await api('/api/trial/randomization/subjects/'+subject+'/preflight');
 if(searchVersion!==registrySearchRequest||request!==participantRequest||
    subject!==participantSubject||subject!==n('tw-rand-subject'))return;
 target.textContent=r.randomized?
  'Already randomized · '+r.allocation_code+
    (r.assigned_arm_mg?' · '+r.assigned_arm_mg+' mg nominal':'')+
    '. Repeat randomization is prohibited.':
  (check.ready?'Ready to randomize · study ID '+r.study_code+
   ' · '+check.stratum+'. Confirm eligibility below.':
   'Not ready · study ID '+r.study_code+' · '+check.reason);
 $('tw-rand-assign').disabled=r.randomized||!check?.ready;
}
$('tw-rand-subject').onchange=()=>{void task('tw-rand-status',loadRandSubject);};
$('tw-rand-assign').onclick=()=>{void task('tw-rand-status',async()=>{
 const sid=n('tw-rand-subject');
 if(!sid)throw Error('Select an enrolled participant');
 if(!$('tw-rand-eligibility-confirm').checked)
  throw Error('Check the signed eligibility, consent and stratum confirmation before requesting an allocation');
 if(!confirm($('tw-rand-subject').selectedOptions[0].textContent+'\nPermanently allocate the NEXT concealed assignment in the approved stratum? '+
      'You cannot select or undo this treatment arm.'))return;
 // Double-taps cannot send concurrent releases from this tab.
 $('tw-rand-assign').disabled=true;
 let r;
 try{
  r=await api('/api/trial/randomization/subjects/'+sid+'/assign',{
   method:'POST',body:JSON.stringify({investigator_confirmation:true,
    stratification_verified:true})});
 }catch(e){await loadRandSubject();throw e;}
 notify('tw-rand-status','Randomization completed: '+r.study_code+
  ' · '+r.allocation_code+' · '+r.assigned_arm_mg+
  ' mg nominal arm. Follow signed renal-adjusted prescription and record allocation code at MSS.');
 $('tw-rand-eligibility-confirm').checked=false;
 await loadRandomization();
});};
$('tw-rand-file').onchange=()=>{void task('tw-rand-status',async()=>{
 const file=$('tw-rand-file').files?.[0];
 lockedSequenceFile=null;
 if(!file){$('tw-rand-file-info').textContent='No file selected.';return;}
 if(file.size>2000000)throw Error('Allocation package exceeds 2 MB');
 const raw=JSON.parse(await file.text());
 if(!Array.isArray(raw.entries)||!raw.entries.length||
     !raw.sequence_sha256||!raw.independent_sequence_attested)
  throw Error('Invalid unsigned sequence package. Use independently approved generator output.');
 lockedSequenceFile=raw;
 $('tw-rand-file-info').textContent=
  'Package read locally · '+raw.entries.length+' allocation positions · fingerprint '+
  raw.sequence_sha256+
  ' · no future group assignments displayed. Verify signed statistician specification.';
});};
$('tw-rand-lock').onclick=()=>{void task('tw-rand-status',async()=>{
 if(!lockedSequenceFile)throw Error('Select the independently signed allocation package');
 if(!confirm('PERMANENT sequence lock: this cannot be replaced or regenerated after first import. '+
    'Confirm independent statistician specification and protocol v5.0?'))return;
 const result=await api('/api/trial/randomization/sequence/lock',{
  method:'POST',body:JSON.stringify(lockedSequenceFile)});
 lockedSequenceFile=null;$('tw-rand-file').value='';
 $('tw-rand-file-info').textContent='Sequence locked; local plaintext selection cleared.';
 notify('tw-rand-status','Signed sealed sequence locked · SHA-256 '+result.sequence_sha256+
  '. All unreleased treatment assignments remain encrypted.');
 await loadRandomization();
});};


$('tw-rand-generate').onclick=()=>{void task('tw-rand-status',async()=>{
 if(!$('tw-rand-independent').checked)throw Error('Independent custodian attestation required');
 const sizes=value('tw-rand-sizes').split(',').map(x=>Number(x.trim()));
 if(!confirm('Permanently lock the official protocol v5 sequence? It cannot be replaced or regenerated.'))return;
 const result=await api('/api/trial/randomization/sequence/generate-and-lock',{method:'POST',body:JSON.stringify({
  statistician_reference:value('tw-rand-custodian-ref'),signed_specification_reference:value('tw-rand-spec-ref'),
  legacy_reconciliation_reference:value('tw-rand-reconcile-ref'),
  independent_sequence_attested:true,block_sizes:sizes})});
 notify('tw-rand-status','Official concealed sequence locked. SHA-256 '+result.sequence_sha256);
 await loadRandomization();
});};

/* One coded participant context across every module; never browser storage. */
let participantSubject=null,participantContext=null,participantRequest=0,timelineCursor=null;
const contextBox=document.createElement('section');
contextBox.id='tw-participant-context';contextBox.className='study-card';
contextBox.style.cssText='grid-column:2;min-width:0;margin:0;';
contextBox.innerHTML=
 '<label>Find patient by CR number, name or Study ID<input id="tw-context-find" type="search" autocomplete="off" placeholder="Enter at least 3 characters"></label>'+
 '<label>Matching registry records<select id="tw-context-find-results"><option value="">Search to find a patient</option></select></label>'+
 choose('Current study participant','tw-context-subject',[])+
 '<strong id="tw-context-allocation">Select a participant to view verified allocation.</strong>'+
 '<p id="tw-context-detail" class="hint"></p><div id="tw-context-error" role="alert"></div>'+
 btn('Open patient course','tw-open-course');
root.insertBefore(contextBox,root.querySelector('.grid'));
/* The same authoritative registry search is available above every study tab.
   An explicit match is required; a search never selects the first patient. */
let contextFindVersion=0,contextFindTimer=null;
$('tw-context-find').oninput=()=>{
 const q=value('tw-context-find'),version=++contextFindVersion;
 clearTimeout(contextFindTimer);
 $('tw-context-find-results').innerHTML='<option value="">'+
  (q.length<3?'Enter at least 3 characters':'Searching…')+'</option>';
 if(q.length<3)return;
 contextFindTimer=setTimeout(()=>{void task('tw-context-error',async()=>{
  const rows=await api('/api/patients?limit=100&q='+encodeURIComponent(q));
  if(version!==contextFindVersion)return;
  $('tw-context-find-results').innerHTML='<option value="">'+
   (rows.length?'Choose an exact match':'No matching active registry record')+'</option>'+
   rows.map(p=>'<option value="'+txt(p.id)+'">'+txt(registryLabel(p))+'</option>').join('');
  $('tw-context-find-results').value='';
 });},250);
};
$('tw-context-find-results').onchange=()=>{void task('tw-context-error',async()=>{
 const id=value('tw-context-find-results');
 if(!id)return;
 if(activeTab==='entry')await saveDraftNow();
 await window.choose(id);
 if(selected!==id)throw Error('Could not confirm patient selection; no entry was changed');
 // Refresh the active tab from the resolved shared participant context.
 if(activeTab==='study'){await selectEnrollmentPatient();await refreshInlineRandomization();}
 if(activeTab==='pcr')await loadPCR();
 if(activeTab==='drug')await loadDrug();
 if(activeTab==='randomization')await loadRandSubject();
 if(activeTab==='course')await loadClinicalCourse();
 $('tw-context-find').value='';
 $('tw-context-find-results').innerHTML='<option value="">Patient selected · search again to switch</option>';
});};
css.textContent+='@media(max-width:860px){#workspace>#tw-participant-context,#workspace>.panel{grid-column:1!important}}';
panel('course','Patient course',
 '<p class="hint">Dated source records supplement the approved CRF. Record each changed regimen separately; distinguish orders from doses actually given. Blank results remain unknown.</p>'+
 '<div id="tw-course-actions"></div>'+btn('Refresh clinical timeline','tw-course-refresh')+
 '<div id="tw-course-records"></div>'+btn('Load earlier records','tw-course-more')+
 '<div id="tw-course-status" class="status hide"></div>');
perms.course=['pi','consultant','scientist','nurse','pg','pharmacy','monitor','microbiology','technician'];
const contextRoleUI=applyRoleUI;
applyRoleUI=function(role){contextRoleUI(role);contextBox.classList.toggle('hide',!perms.course.includes(role));};
function resetPCRControls(){
 pcrRecords=[];pcrLoadedSubject=null;
 for(const id of ['tw-collect-id','tw-result-id','tw-verify-id','tw-pcr-print-id'])$(id).innerHTML='<option value="">Choose participant first</option>';
 $('tw-pcr-print').disabled=true;
 for(const id of ['tw-collect-save','tw-result-save','tw-verify-save'])$(id).disabled=true;
 $('tw-pcr-table').textContent='Select an enrolled participant to load specimens.';
}
function resetDrugControls(){
 drugLoadedSubject=null;
 for(const id of ['tw-auth-save','tw-dispense-save','tw-return-save'])$(id).disabled=true;
 for(const id of ['tw-order-id','tw-dispense-id','tw-return-qty','tw-issued','tw-rx','tw-allocation','tw-renal','tw-instruction'])$(id).value='';
 for(const id of ['tw-order-id','tw-dispense-id'])$(id).innerHTML='<option value="">Choose participant first</option>';
 $('tw-ledger').textContent='Select an enrolled participant.';
 $('tw-slip').textContent='Generate a confirmed issue to print and sign.';
 lastIssuedSlip=null;$('tw-mss-print').disabled=true;
 $('tw-drug-allocation').textContent='No randomized allocation verified.';
}
function requireProcedureSubject(kind){
 const loaded=kind==='pcr'?pcrLoadedSubject:drugLoadedSubject;
 if(!participantSubject||loaded!==participantSubject||n('tw-'+kind+'-subject')!==participantSubject)
  throw Error('Reload procedures for the selected enrolled participant before saving');
}
function clearParticipant(){
 participantRequest++;participantSubject=null;participantContext=null;timelineCursor=null;
 selected=null;
 $('currentPatient').textContent='None';$('records').textContent='Select a participant.';$('entryList').textContent='';
 $('doseResult').textContent='';$('arm').disabled=false;
 resetPCRControls();resetDrugControls();
 $('tw-context-subject').value='';$('tw-context-allocation').textContent='No participant selected.';
 $('tw-context-detail').textContent='';$('tw-course-records').textContent='';
 for(const id of ['tw-pcr-subject','tw-drug-subject','tw-crf-subject','tw-rand-subject'])$(id).value='';
 $('tw-rand-assign').disabled=true;
}
function renderParticipant(context){
 if(context.patient_id!==participantContext?.patient_id){
  resetPCRControls();resetDrugControls();
  for(const id of ['tw-consent-date','tw-icf','tw-pis','tw-consent-obtained','tw-initials','tw-screen-age','tw-sex','tw-ratg','tw-anchor-date'])$(id).value='';
  for(const id of ['tw-pi-consent'])$(id).checked=false;
  for(const id of ['tw-collected','tw-accession','tw-reported','tw-assay','tw-result-kind','tw-viral-load','tw-loq','tw-qc','tw-result-reason','tw-review-reason','tw-rx-date','tw-issue-date','tw-return-date'])$(id).value='';
  $('tw-rand-eligibility-confirm').checked=false;
  for(const id of ['age','weight','creatinine','sex'])$(id).value='';
 }
 participantContext=context;participantSubject=context.subject?.id||null;
 // Synchronize the screening registry picker as soon as a patient is resolved.
 // The identity change must not await extra patient-banner/network requests.
 if(Array.from($('tw-patient').options).some(o=>o.value===context.patient_id))
   $('tw-patient').value=context.patient_id;
 showEnrollmentStudyId();
 $('tw-context-subject').value=participantSubject?String(participantSubject):'';
 const a=context.allocation||{};
 $('doseResult').textContent='';
 $('arm').disabled=!!a.assigned_arm_mg;
 if(a.assigned_arm_mg)$('arm').value=a.assigned_arm_mg;
 $('tw-context-allocation').textContent=!context.subject?'Registry record not yet screened':
  (context.subject.study_code||context.subject.screening_code)+' · '+
  (a.randomized?(a.assigned_arm_mg?'Allocated '+a.assigned_arm_mg+' mg OD nominal arm':'Allocation concealed for this role')+
   ' · '+a.allocation_code:'Not randomized');
 $('tw-context-detail').textContent=context.subject?
  'Transplant: '+(context.transplant_on||'not recorded')+' · '+context.subject.status+
  ' · rATG: '+(context.subject.ratg_induction===null?'unknown':context.subject.ratg_induction?'yes':'no')+
  ' · donor: '+context.subject.donor_type+
  (a.assigned_arm_mg?' · Assignment is permanent; actual dose follows the dated renal-adjusted signed prescription.':''):'';
 for(const id of ['tw-pcr-subject','tw-drug-subject','tw-crf-subject','tw-rand-subject']){
  $(id).value=Array.from($(id).options).some(o=>o.value===String(participantSubject))?String(participantSubject):'';
 }
}
async function selectParticipantSubject(id){
 if(activeTab==='entry')await saveDraftNow();
 if(!id){clearParticipant();return false;}
 if(id!==participantSubject){resetPCRControls();resetDrugControls();}
 const request=++participantRequest;
 $('tw-context-allocation').textContent='Checking participant and allocation…';
 $('tw-context-detail').textContent='';$('tw-context-error').textContent='';
 try{
  const context=await api('/api/trial/crf/subjects/'+id+'/context');
  if(request===participantRequest){
   if(context.patient_id!==selected){
    if(activeTab==='entry')await saveDraftNow();
    selected=context.patient_id;await loadPatients();await loadRecord();
    if(activeTab==='entry')await restoreDraft();
   }
   if(request===participantRequest)renderParticipant(context);
  }
 }catch(e){if(request===participantRequest){clearParticipant();$('tw-context-error').textContent=e.message;}throw e;}
 return request===participantRequest;
}
$('tw-context-subject').onchange=()=>{
 // Invalidate old-patient procedure buttons before asynchronous context reads.
 resetPCRControls();resetDrugControls();
 $('tw-inline-rand-submit').disabled=true;
 $('tw-rand-assign').disabled=true;
 const switchPromise=task('tw-context-error',async()=>{
 const previous=participantSubject;
 try{if(activeTab==='crf')await crfSaveDraft();if(activeTab==='entry')await saveDraftNow();}
 catch(e){$('tw-context-subject').value=previous?String(previous):'';throw e;}
 await selectParticipantSubject(n('tw-context-subject'));
 if(activeTab==='study'){
  await selectEnrollmentPatient();
  await refreshInlineRandomization();
  window.dispatchEvent(new Event('cmv:workflow-updated'));
 }
 if(activeTab==='crf'){crfRender();await populateCrfLinkedIdentifiers();await crfRestoreDraft();await loadCrfEntries();}
 if(activeTab==='pcr')await loadPCR();
 if(activeTab==='drug')await loadDrug();
 if(activeTab==='randomization')await loadRandSubject();
 if(activeTab==='course')await loadClinicalCourse();
 });
 window.cmvPatientContextSwitch=switchPromise;
 void switchPromise.finally(()=>{
  if(window.cmvPatientContextSwitch===switchPromise)window.cmvPatientContextSwitch=null;
 });
};
const participantChoose=window.choose;
window.choose=async function(id){
 if(activeTab==='crf')try{await crfSaveDraft();}catch(e){error('tw-crf-status',e);return;}
 await participantChoose(id);
 if(selected!==id)return;
 if(!perms.course.includes($('currentRole').textContent.trim())){
  participantRequest++;participantSubject=null;participantContext=null;
  resetPCRControls();resetDrugControls();return;
 }
 const request=++participantRequest;
 $('tw-context-allocation').textContent='Checking participant and allocation…';
 $('tw-context-detail').textContent='';
 try{const context=await api('/api/trial/crf/patients/'+encodeURIComponent(id)+'/context');
  if(request===participantRequest){await loadSubjects();if(request!==participantRequest)return;renderParticipant(context);
   if(activeTab==='crf'){crfRender();await populateCrfLinkedIdentifiers();await crfRestoreDraft();await loadCrfEntries();}}
 }catch(e){if(request===participantRequest){clearParticipant();$('tw-context-error').textContent=e.message;}}
};
const participantLogout=logout;
logout=async function(){
 if(activeTab==='crf')try{await crfSaveDraft();}catch(e){error('tw-crf-status',e);return;}
 if(activeTab==='entry')try{await saveDraftNow();}catch(e){show('msg',e.message,true);return;}
 await participantLogout();clearParticipant();
};
const courseTab=tab;
tab=async function(name){
 if(name==='course'){
  if(activeTab==='crf')try{await crfSaveDraft();}catch(e){error('tw-crf-status',e);return;}
  if(activeTab==='entry')try{await saveDraftNow();}catch(e){show('msg',e.message,true);return;}
  await courseTab('security');$('security').classList.add('hide');$('btnsecurity').classList.remove('selected');
  activeTab='course';$('course').classList.remove('hide');$('btncourse').classList.add('selected');
  await task('tw-course-status',async()=>{await loadSubjects();await loadClinicalCourse();});
 }else{await courseTab(name);if(activeTab!=='course'){$('course').classList.add('hide');$('btncourse').classList.remove('selected');}}
};
/* Patient course: independent reads fail gracefully. Never treat a network
   failure as evidence that no clinical records exist. */
let clinicalCourseRequest=0;
async function loadClinicalCourse(earlier=false){
 const target=$('tw-course-records'),status=$('tw-course-status');
 const sid=participantSubject,request=++clinicalCourseRequest;
 if(!sid){target.textContent='Choose a participant above.';
  $('tw-course-more').classList.add('hide');return;}
 const history=earlier?target.innerHTML:'';
 if(!earlier)target.innerHTML='<p class="hint">Loading clinical records…</p>';
 status.classList.add('hide');
 const suffix=earlier&&timelineCursor?'?before_on='+encodeURIComponent(timelineCursor.before_on)+
  '&before_id='+timelineCursor.before_id:'';
 const [schemaResult,recordsResult]=await Promise.allSettled([
  api('/api/trial/crf/schema'),
  api('/api/trial/crf/subjects/'+sid+'/timeline'+suffix)
 ]);
 if(request!==clinicalCourseRequest||sid!==participantSubject)return;
 const actions=$('tw-course-actions');
 if(schemaResult.status==='fulfilled'){
  const schema=schemaResult.value;
  actions.innerHTML=Object.entries(schema.forms).filter(([k])=>
   ['C_baseline','E_followup','D_adherence','M_medication','N_laboratory',
    'O_infection','P_transplant','G_cmv_event','H_adverse_event','I_clinical_outcome'].includes(k))
   .map(([k,v])=>'<button class="secondary" data-course-form="'+txt(k)+'">'+
     txt(v.title)+'</button>').join(' ');
 }else{
  actions.innerHTML='<div class="tw-course-warning">The clinical entry menu could not load. '+
    'Existing records may still be available. <button class="secondary" type="button" '+
    'data-course-retry>Retry</button></div>';
 }
 if(recordsResult.status==='rejected'){
  const message=recordsResult.reason?.message||'Unable to retrieve clinical history.';
  target.innerHTML=(earlier?history:'')+
   '<div class="tw-course-warning" role="alert"><strong>Clinical records could not be loaded.</strong>'+
   '<p>'+txt(message)+'</p><button type="button" data-course-retry>Retry clinical records</button></div>';
  if(!earlier)$('tw-course-more').classList.add('hide');
  show('tw-course-status','Clinical record fetch failed. This does not mean records are absent.',true);
  return;
 }
 const records=recordsResult.value;
 const entries=records.entries||[];
 const cards=entries.map(row=>
  '<details class="study-card"><summary>'+txt(row.occurred_on)+
  ' · '+txt(row.title)+' · '+txt(row.review_status)+' · revision '+row.revision+
  '</summary><dl>'+Object.entries(row.payload||{}).filter(([k])=>!k.startsWith('_'))
    .map(([k,v])=>'<dt>'+txt(row.fields?.[k]?.label||k)+
    '</dt><dd>'+txt(v===null?'Not documented':typeof v==='object'?JSON.stringify(v):v)+'</dd>')
    .join('')+'</dl></details>').join('');
 if(earlier)target.innerHTML=history+cards;
 else target.innerHTML='<p class="hint">'+txt(records.note||'Dated, source-verified records')+'</p>'+
  (cards||'<p class="hint">No submitted clinical records for this participant.</p>');
 timelineCursor=records.next_cursor;
 $('tw-course-more').classList.toggle('hide',!timelineCursor);
 if(schemaResult.status==='rejected')
  show('tw-course-status','Clinical history loaded; entry menu unavailable. Select Retry to reload.',true);
}
$('tw-course-records').addEventListener('click',event=>{
 if(event.target.closest('[data-course-retry]'))
  void task('tw-course-status',()=>loadClinicalCourse());
});
$('tw-course-actions').addEventListener('click',event=>{
 if(event.target.closest('[data-course-retry]'))
  void task('tw-course-status',()=>loadClinicalCourse());
});

$('tw-course-actions').onclick=e=>{const button=e.target.closest('[data-course-form]');if(!button)return;
 void task('tw-course-status',async()=>{await tab('crf');if(activeTab!=='crf')return;
  $('tw-crf-section').value=button.dataset.courseForm;crfRender();await populateCrfLinkedIdentifiers();await crfRestoreDraft();await loadCrfEntries();});
};
$('tw-open-course').onclick=()=>{void tab('course');};
$('tw-course-refresh').onclick=()=>{void task('tw-course-status',()=>loadClinicalCourse());};
$('tw-course-more').onclick=()=>{void task('tw-course-status',()=>loadClinicalCourse(true));};
$('tw-enroll-randomize').onclick=()=>{void tab('randomization');};

/* Print only server-confirmed specimen codes and dispenses; do not fabricate a slip. */
const printSheet=document.createElement('article');
printSheet.id='tw-print-sheet';document.body.appendChild(printSheet);
function printStudySlip(title,fields,notice){
 printSheet.replaceChildren();
 const head=document.createElement('h1');head.textContent='NIMS, Hyderabad · ICMR CMV Trial';printSheet.appendChild(head);
 const subtitle=document.createElement('h2');subtitle.textContent=title;printSheet.appendChild(subtitle);
 for(const [label,text] of fields){
  const line=document.createElement('div');line.className='print-field';
  line.textContent=label+': '+String(text??'');printSheet.appendChild(line);
 }
 const footer=document.createElement('p');footer.className='print-warning';footer.textContent=notice;printSheet.appendChild(footer);
 window.print();
}
$('tw-pcr-print').onclick=()=>{
 try{
  requireProcedureSubject('pcr');
  const row=pcrRecords.find(x=>x.id===n('tw-pcr-print-id'));
  if(!row||row.attempt!==1)throw Error('Select an existing scheduled PCR specimen');
  const subject=studySubjects.find(x=>x.id===participantSubject);
  if(!subject?.study_code)throw Error('Study ID is required for a protocol requisition');
  printStudySlip('Clinical Microbiology · coded CMV PCR requisition',[
   ['Study ID',subject.study_code],['Unique specimen code',row.specimen_code],
   ['Protocol visit','Month '+row.scheduled_month],
   ['Target date',row.target_on],
   ['Current recorded status',row.status],
   ['Actual collection date/time','____________________________'],
   ['Collection staff signature','____________________________'],
   ['Laboratory accession number','____________________________'],
   ['Reported date / Microbiology signature','____________________________']
  ],'Seven scheduled study PCRs are linked to transplant date. Confirm the participant and source record before specimen collection. Printing is not specimen collection or a laboratory result.');
 }catch(e){error('tw-pcr-status',e)}
};
$('tw-mss-print').disabled=true;
$('tw-mss-print').onclick=()=>{
 try{
  requireProcedureSubject('drug');
  if(!lastIssuedSlip||!lastIssuedSlip.slip_code)throw Error('Issue study tablets before printing an MSS slip');
  printStudySlip('Main Sub Store · signed study-drug issue slip',[
   ['Study ID',lastIssuedSlip.study_code],['Unique MSS slip code',lastIssuedSlip.slip_code],
   ['Signed prescription reference',lastIssuedSlip.prescription_ref],
   ['Study medication','Valganciclovir 450 mg tablets'],
   ['Quantity issued',lastIssuedSlip.quantity_issued],
   ['Batch / lot',lastIssuedSlip.lot_number],
   ['Batch expiry',lastIssuedSlip.expiry_on],
   ['Issue date',lastIssuedSlip.issued_on],
   ['Prescriber signature','____________________________'],
   ['MSS pharmacist signature','____________________________'],
   ['Recipient signature / date','____________________________']
  ],'Valid only against the signed clinical prescription and allocated nominal arm; actual renal-adjusted dosing remains subject to signed clinical orders.');
 }catch(e){error('tw-drug-status',e)}
};

/* Single, accessible mobile navigation; existing sections retain their IDs. */
const mobileMenu=document.createElement('button');
mobileMenu.id='tw-mobile-menu';mobileMenu.type='button';
mobileMenu.setAttribute('aria-controls','tw-study-navigation');
mobileMenu.setAttribute('aria-expanded','false');
mobileMenu.textContent='Menu · Study sections';
menu.id='tw-study-navigation';
root.insertBefore(mobileMenu,menu);
mobileMenu.onclick=()=>{
 const open=root.classList.toggle('mobile-nav-open');
 mobileMenu.setAttribute('aria-expanded',String(open));
 mobileMenu.textContent=open?'Close study menu':'Menu · Study sections';
};
menu.addEventListener('click',event=>{
 if(!event.target.closest('button'))return;
 root.classList.remove('mobile-nav-open');
 mobileMenu.setAttribute('aria-expanded','false');
 mobileMenu.textContent='Menu · Study sections';
});

})();

// Defer cookie-session recovery until all workspace hooks have been installed.
void restoreSignedInSession();
