/* Structured clinical-trial workspace; no sensitive browser persistence. */
(function(){
'use strict';
var root=$('workspace'),menu=root.querySelector('.tabs');
var logoutBtn=Array.from(menu.querySelectorAll('button')).find(x=>x.textContent.trim()==='Log out');
var studySubjects=[],selectedId=null,pcrRecords=[],drugLots=[];
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
function error(id,e){show(id,e.message||String(e),true);}
function notify(id,s){show(id,s,false);}
async function task(id,callback){try{await callback();}catch(e){error(id,e);}}
function panel(id,title,html){
 var page=document.createElement('div');
 page.id=id;page.className='panel hide';
 page.style.cssText='grid-column:2;min-width:0;padding:22px;';
 page.innerHTML='<h2>'+title+'</h2><p class="hint">NIMS CMV study · synthetic-only until formal production sign-off. Paper source signatures and independent randomization remain mandatory.</p>'+html;
 root.appendChild(page);
 var button=document.createElement('button');button.id='btn'+id;
 button.textContent=title;button.onclick=()=>{void tab(id)};
 menu.insertBefore(button,logoutBtn);
}
var field=(title,id,type='text')=>'<label>'+title+'<input id="'+id+'" type="'+type+'"></label>';
var choose=(title,id,opts)=>'<label>'+title+'<select id="'+id+'">'+opts.map(o=>'<option value="'+o[0]+'">'+o[1]+'</option>').join('')+'</select></label>';
var btn=(label,id)=>'<button id="'+id+'">'+label+'</button>';
panel('study','Enrollment',
 '<div class="study-columns"><section class="study-card"><h3>1 · Screening</h3>'+
 choose('Registry record','tw-patient',[])+field('Screening date','tw-screen-date','date')+
 field('Informed consent signed','tw-consent-date','date')+
 field('Signed ICF version','tw-icf')+field('Signed PIS version','tw-pis')+
 choose('Consent language','tw-consent-language',[['English','English'],['Telugu','Telugu'],['Hindi','Hindi']])+
 field('Consent obtained by','tw-consent-obtained')+
 field('Signed consent document/source reference','tw-consent-source')+
 field('Participant initials (restricted)','tw-initials')+
 field('Age at transplant (years)','tw-screen-age','number')+
 choose('Sex (source record)','tw-sex',[['','Not recorded'],['female','Female'],['male','Male'],['other','Other']])+
 choose('Donor CMV IgG','tw-digg',[['positive','Positive'],['negative','Negative'],['unknown','Unknown']])+
 choose('Recipient CMV IgG','tw-rigg',[['positive','Positive'],['negative','Negative'],['unknown','Unknown']])+
 choose('Donor type','tw-donor',[['living','Living'],['deceased','Deceased']])+
 choose('Donor relationship','tw-relationship',[['living_related','Living related'],
    ['living_unrelated','Living unrelated'],['deceased','Deceased']])+
 choose('rATG induction','tw-ratg',[['','Undocumented'],['true','Yes'],['false','No']])+
 '<label><input id="tw-eligible" type="checkbox" style="width:auto"> Signed protocol eligibility reviewed</label>'+
 btn('Save screening','tw-screen-save')+'</section>'+
 '<section class="study-card"><h3>2 · Protocol inclusion/exclusion checklist</h3>'+
 choose('Screened subject','tw-checklist-subject',[])+
 '<div id="tw-eligibility-fields">Select a subject and complete all protocol criteria.</div>'+
 field('Age at randomization (years)','tw-age','number')+
 field('ANC (/µL)','tw-anc','number')+field('Platelets (/µL)','tw-platelets','number')+
 field('Hemoglobin (g/dL)','tw-hb','number')+
 field('Cockcroft–Gault CrCl (mL/min)','tw-crcl','number')+
 field('CBC date','tw-cbc-date','date')+field('Investigator review date','tw-review-on','date')+
 field('Signed eligibility source/reference','tw-source')+
 btn('Validate complete eligibility checklist','tw-checklist-save')+'</section>'+
 '<section class="study-card"><h3>3 · PI enrollment verification</h3>'+
 choose('Screened subject','tw-screened',[])+field('Enrollment date','tw-enroll-date','date')+
 field('Approved PCR anchor date','tw-anchor-date','date')+
 choose('Protocol PCR anchor','tw-anchor-basis',[['transplant_date','Transplant date only (protocol v5.0)']])+
 field('Approved protocol reference','tw-protocol')+
 '<label><input type="checkbox" id="tw-pi-consent" style="width:auto"> Consent, D+/R+ and eligibility verified</label>'+
 '<label><input type="checkbox" id="tw-pi-anchor" style="width:auto"> Protocol PCR timing explicitly verified</label>'+
 btn('Approve enrollment and seven PCR codes','tw-enroll-save')+'</section></div>'+
 '<h3>Screening and enrollment register</h3><div id="tw-register"></div><div id="tw-status" class="status hide"></div>'
);
panel('pcr','CMV PCR',
 choose('Enrolled subject','tw-pcr-subject',[])+
 '<h3>Seven protocol timepoints and repeat specimens</h3><div id="tw-pcr-table"></div>'+
 '<div class="study-columns"><section class="study-card"><h3>Specimen collection</h3>'+
 choose('Planned specimen','tw-collect-id',[])+field('Collection date','tw-collected','date')+
 field('Lab accession reference','tw-accession')+btn('Record collection','tw-collect-save')+
 '</section><section class="study-card"><h3>Laboratory result</h3>'+
 choose('Collected specimen','tw-result-id',[])+field('Reported date','tw-reported','date')+
 field('Assay/platform','tw-assay')+
 choose('Result category','tw-result-kind',[['not_detected','Not detected'],['quantified','Quantified'],['detected_below_loq','Below quantification'],['invalid','Invalid']])+
 field('CMV viral load (IU/mL; quantified only)','tw-viral-load','number')+
 field('Lower limit (IU/mL; if known)','tw-loq','number')+
 choose('Laboratory QC','tw-qc',[['pass','Pass'],['fail','Fail']])+
 field('Correction reason (if editing result)','tw-result-reason')+
 btn('Submit lab result for verification','tw-result-save')+'</section></div>'+
 '<section class="study-card"><h3>Independent data review</h3>'+
 choose('Submitted result','tw-verify-id',[])+field('Signed source review reason','tw-review-reason')+
 btn('Verify result','tw-verify-save')+'</section><div id="tw-pcr-status" class="status hide"></div>'
);
panel('drug','MSS drug accountability',
 choose('Enrolled subject','tw-drug-subject',[])+
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
 field('Authorized order ID','tw-order-id','number')+
 choose('Stock lot','tw-lot-id',[])+field('Issue date','tw-issue-date','date')+
 field('Number of tablets','tw-issued','number')+btn('Issue and generate MSS slip','tw-dispense-save')+
 '</section><section class="study-card"><h3>Record returned medication</h3>'+
 field('Dispense entry number','tw-dispense-id','number')+
 field('Returned quantity','tw-return-qty','number')+field('Returned date','tw-return-date','date')+
 choose('Disposition','tw-disposition',[['quarantine','Quarantine'],['destruction_pending','Destruction pending'],['destroyed','Destroyed']])+
 btn('Record return without restocking','tw-return-save')+'</section></div>'+
 '<div class="study-card"><h3>Accountability ledger</h3><div id="tw-ledger"></div></div>'+
 '<div class="study-card"><h3>MSS issue slip</h3><div id="tw-slip">Generate a confirmed issue to print and sign.</div></div>'+
 '<div id="tw-drug-status" class="status hide"></div>'
);
panel('crf','Structured eCRF · Sections C–L',
 choose('Study participant','tw-crf-subject',[])+
 choose('CRF section','tw-crf-section',[])+
 '<p class="hint" id="tw-crf-descriptor">Choose a form. Only signed protocol fields are displayed; optional fields may remain blank, but never invent values.</p>'+
 '<label>Event/assessment date<input type="date" id="tw-crf-date"></label>'+
 '<div id="tw-crf-fields" class="study-columns"></div>'+
 '<div id="tw-crf-draft-status" class="status">No draft loaded.</div>'+
 '<label>Correction reason (required only when revising submitted form)<input id="tw-crf-reason"></label>'+
 btn('Save private working draft','tw-crf-save')+' '+
 btn('Submit form for independent review','tw-crf-submit')+
 '<div class="study-card"><h3>Submitted forms and review states</h3>'+
 '<div id="tw-crf-entries"></div></div>'+
 '<div id="tw-crf-status" class="status hide"></div>'
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
 field('Unique username','tw-username')+field('Staff name','tw-fullname')+
 choose('Delegated role','tw-role',[['scientist','Project scientist'],['nurse','Research nurse'],['technician','Lab technician'],['microbiology','Microbiology'],['pharmacy','MSS pharmacist'],['consultant','Consultant'],['pg','PG resident'],['monitor','CRA / monitor']])+
 btn('Generate one-time staff activation','tw-invite-save')+
 '<div id="tw-invitation" class="status hide" style="white-space:pre-wrap"></div></div>'+
 '<div class="study-card"><h3>Named staff · 90-day authorization</h3><p class="hint">Each person keeps their own password. Access expires after 90 days, with investigator-controlled renewal or immediate revocation.</p><div id="tw-accounts"></div></div>'+
 '<p class="hint">Each person activates their account and chooses a private password. Never share a common account. MFA and permission review remain production gates.</p>'+
 '<div id="tw-staff-status" class="status hide"></div>'
);
var css=document.createElement('style');
css.textContent='.study-columns{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.study-card{padding:18px;margin:12px 0;border:1px solid #e3eaf4;border-radius:12px}.study-card h3{margin-top:0}.study-columns input[type=checkbox]{width:auto}.study-columns label{margin-bottom:8px}#tw-pcr-table,#tw-register,#tw-ledger{overflow:auto}#tw-pcr-table table,#tw-register table,#tw-ledger table{border-collapse:collapse;width:100%;font-size:12px}#tw-pcr-table td,#tw-pcr-table th,#tw-register td,#tw-register th,#tw-ledger td,#tw-ledger th{border-bottom:1px solid #e6ebf2;padding:9px;text-align:left;white-space:nowrap}@media(max-width:860px){.study-columns{grid-template-columns:1fr}#workspace>#study,#workspace>#pcr,#workspace>#drug,#workspace>#staff{grid-column:1!important}}';
document.head.appendChild(css);
var login=$('loginPanel');
login.insertAdjacentHTML('beforeend','<hr><h3>Activate individual staff account</h3>'+
 field('One-time activation token','tw-token')+
 '<label>Choose a private password<input type="password" id="tw-password" autocomplete="new-password"></label>'+
 btn('Activate account','tw-activate-save')+'<div id="tw-activate-status" class="status hide"></div>');
for(const id of ['tw-screen-date','tw-consent-date','tw-enroll-date','tw-anchor-date','tw-collected','tw-reported','tw-receipt-date','tw-rx-date','tw-issue-date','tw-return-date'])$(id).value=today();
var perms={crf:['pi','consultant','scientist','nurse','pg','technician','microbiology','pharmacy','monitor'],study:['pi','consultant','scientist'],pcr:['pi','consultant','scientist','nurse','technician','microbiology','monitor'],drug:['pi','consultant','scientist','pharmacy','monitor'],staff:['pi','admin'],security:['pi','admin','consultant','pg','scientist','nurse','technician','microbiology','pharmacy','monitor']};
function setRole(){
 var r=$('currentRole').textContent.trim();
 for(const k of Object.keys(perms))$('btn'+k).classList.toggle('hide',!perms[k].includes(r));
 for(const [id,roles] of [
  ['tw-screen-save',['pi','consultant','scientist']],['tw-checklist-save',['pi','consultant']],['tw-enroll-save',['pi']],
  ['tw-collect-save',['pi','consultant','scientist','nurse','technician','microbiology']],
  ['tw-result-save',['microbiology','technician']],
  ['tw-verify-save',['pi','consultant','scientist','monitor']],
  ['tw-stock-save',['pharmacy']],['tw-auth-save',['pi','consultant']],
  ['tw-dispense-save',['pharmacy']],['tw-return-save',['pharmacy']],
  ['tw-invite-save',['pi','admin']]
 ])$(id).classList.toggle('hide',!roles.includes(r));
}
var oldLogin=login;
var originalApply=applyRoleUI;
applyRoleUI=function(role){originalApply(role);setRole();};
var oldTab=tab;
tab=async function(name){
 if(['study','pcr','drug','staff','security','crf'].includes(name)){
  if(activeTab==='entry'){try{await saveDraftNow();}catch(e){show('msg','Draft not saved: '+e.message,true);return;}}
  activeTab=name;
  for(const section of ['dashboard','registry','review','entry','dose','due','study','pcr','drug','staff','security','crf']){
   $(section).classList.toggle('hide',section!==name);
   $('btn'+section).classList.toggle('selected',section===name);
  }
  root.querySelector('.grid').classList.add('hide');
  await task(name==='pcr'?'tw-pcr-status':name==='drug'?'tw-drug-status':'tw-status',async()=>{
   if(name==='study'){await loadRegistry();await loadSubjects();await loadEligibilitySchema();}
   if(name==='pcr'){await loadSubjects();await loadPCR();}
   if(name==='drug'){await loadSubjects();await loadDrug();}
   if(name==='staff'){await loadAccounts();}
   if(name==='crf'){await loadSubjects();await loadCrfSchema();await loadCrfEntries();}
  });
 }else{
  await oldTab(name);
  for(const k of Object.keys(perms)){$(k).classList.add('hide');$('btn'+k).classList.remove('selected');}
 }
};
async function loadRegistry(){
 var people=await api('/api/patients?limit=100');
 fill('tw-patient',people,'id',p=>(p.study_id||p.cr_number||'')+' · '+(p.name||''));
}
async function loadSubjects(){
 studySubjects=await api('/api/trial/subjects');
 fill('tw-screened',studySubjects.filter(x=>x.status==='screened'),'id',x=>x.screening_code);
 fill('tw-checklist-subject',studySubjects.filter(x=>x.status==='screened'),'id',x=>x.screening_code);
 var active=studySubjects.filter(x=>x.status==='enrolled');
 for(const id of ['tw-pcr-subject','tw-drug-subject','tw-crf-subject'])fill(id,active,'id',x=>x.study_code);
 $('tw-register').innerHTML='<table><thead><tr><th>Study code</th><th>Status</th><th>D+/R+</th><th>Signed consent</th></tr></thead><tbody>'+
 studySubjects.map(x=>'<tr><td>'+txt(x.study_code||x.screening_code)+'</td><td>'+txt(x.status)+'</td><td>'+String(x.d_plus_r_plus)+'</td><td>'+String(x.consent_recorded)+'</td></tr>').join('')+'</tbody></table>';
}
async function loadPCR(){
 selectedId=n('tw-pcr-subject');if(!selectedId)return;
 pcrRecords=(await api('/api/trial/subjects/'+selectedId+'/pcr')).pcr_records;
 $('tw-pcr-table').innerHTML='<table><thead><tr><th>Code</th><th>Month</th><th>Target</th><th>Status</th><th>Viral load (IU/mL)</th></tr></thead><tbody>'+
 pcrRecords.map(x=>'<tr><td>'+txt(x.specimen_code)+'</td><td>'+x.scheduled_month+'</td><td>'+txt(x.target_on)+'</td><td>'+txt(x.status)+'</td><td>'+txt(x.quantitative_iu_ml??'—')+'</td></tr>').join('')+'</tbody></table>';
 fill('tw-collect-id',pcrRecords.filter(x=>x.status==='planned'),'id',x=>x.specimen_code);
 fill('tw-result-id',pcrRecords.filter(x=>['collected','result_entered','verified'].includes(x.status)),'id',x=>x.specimen_code);
 fill('tw-verify-id',pcrRecords.filter(x=>x.status==='result_entered'),'id',x=>x.specimen_code);
}
async function loadDrug(){
 selectedId=n('tw-drug-subject');if(!selectedId)return;
 if(['pharmacy','scientist','pi','monitor','admin'].includes($('currentRole').textContent.trim())){
  drugLots=await api('/api/trial/pharmacy/lots');
  fill('tw-lot-id',drugLots,'id',x=>x.lot_number+' ('+x.quantity_on_hand+' remaining)');
 }
 var p=await api('/api/trial/subjects/'+selectedId+'/pharmacy');
 $('tw-ledger').innerHTML='<table><thead><tr><th>MSS slip code</th><th>Issued</th><th>Returned</th><th>Unreconciled</th></tr></thead><tbody>'+
 p.dispenses.map(x=>'<tr><td>'+txt(x.slip_code)+'</td><td>'+x.quantity_issued+'</td><td>'+x.total_returned+'</td><td>'+x.remaining_unreconciled+'</td></tr>').join('')+'</tbody></table>';
}
$('tw-pcr-subject').onchange=()=>{void task('tw-pcr-status',loadPCR);};
$('tw-drug-subject').onchange=()=>{void task('tw-drug-status',loadDrug);};
$('tw-screen-save').onclick=()=>{void task('tw-status',async()=>{
 var r=await api('/api/trial/screening',{method:'POST',body:JSON.stringify({
  patient_id:value('tw-patient'),screening_on:value('tw-screen-date'),consent_on:value('tw-consent-date')||null,
  consent_version:value('tw-icf')||null,donor_cmv_igg:value('tw-digg'),recipient_cmv_igg:value('tw-rigg'),
  donor_type:value('tw-donor'),donor_relationship:value('tw-relationship'),
  participant_initials:value('tw-initials')||null,
  age_at_transplant:value('tw-screen-age')?n('tw-screen-age'):null,
  sex_at_birth:value('tw-sex')||null,pis_version:value('tw-pis')||null,
  consent_language:value('tw-consent-language')||null,
  consent_obtained_by:value('tw-consent-obtained')||null,
  signed_consent_source_ref:value('tw-consent-source')||null,
  ratg_induction:value('tw-ratg')===''?null:value('tw-ratg')==='true',
  eligibility_attested:$('tw-eligible').checked})});
 notify('tw-status','Screening code '+r.screening_code+' assigned. No randomization performed.');
 await loadSubjects();
});};
$('tw-enroll-save').onclick=()=>{void task('tw-status',async()=>{
 var id=n('tw-screened');if(!id)throw Error('Select a screened subject');
 var r=await api('/api/trial/subjects/'+id+'/enroll',{method:'POST',body:JSON.stringify({
  enrolled_on:value('tw-enroll-date'),pcr_anchor_on:value('tw-anchor-date'),
  pcr_anchor_basis:value('tw-anchor-basis'),protocol_reference:value('tw-protocol'),
  reviewed_eligibility_and_consent:$('tw-pi-consent').checked,approved_visit_anchor:$('tw-pi-anchor').checked})});
 notify('tw-status',r.subject.study_code+' enrolled; seven coded PCR orders generated. Obtain independent randomization.');
 await loadSubjects();
});};
$('tw-collect-save').onclick=()=>{void task('tw-pcr-status',async()=>{
 var r=await api('/api/trial/pcr/'+n('tw-collect-id')+'/collect',{method:'POST',
  body:JSON.stringify({collected_on:value('tw-collected'),lab_accession:value('tw-accession')})});
 notify('tw-pcr-status','Collected '+r.specimen_code);await loadPCR();
});};
$('tw-result-save').onclick=()=>{void task('tw-pcr-status',async()=>{
 var r=pcrRecords.find(x=>x.id===n('tw-result-id'));if(!r)throw Error('Select a collected specimen');
 var updated=await api('/api/trial/pcr/'+r.id+'/result',{method:'PUT',body:JSON.stringify({
  expected_revision:r.revision,reported_on:value('tw-reported'),assay_platform:value('tw-assay'),
  result_kind:value('tw-result-kind'),quantitative_iu_ml:value('tw-viral-load')?n('tw-viral-load'):null,
  lower_limit_iu_ml:value('tw-loq')?n('tw-loq'):null,qc_status:value('tw-qc'),
  correction_reason:value('tw-result-reason')||null})});
 notify('tw-pcr-status',updated.specimen_code+' result saved, awaiting independent review');await loadPCR();
});};
$('tw-verify-save').onclick=()=>{void task('tw-pcr-status',async()=>{
 var r=pcrRecords.find(x=>x.id===n('tw-verify-id'));if(!r)throw Error('Select submitted result');
 var verified=await api('/api/trial/pcr/'+r.id+'/verify',{method:'POST',body:JSON.stringify({
  expected_revision:r.revision,review_reason:value('tw-review-reason')})});
 notify('tw-pcr-status',verified.specimen_code+' verified by independent reviewer');await loadPCR();
});};
$('tw-stock-save').onclick=()=>{void task('tw-drug-status',async()=>{
 var r=await api('/api/trial/pharmacy/lots',{method:'POST',body:JSON.stringify({
  lot_number:value('tw-lot'),expiry_on:value('tw-expiry'),received_on:value('tw-receipt-date'),
  strength_mg:450,quantity_received:n('tw-received')})});
 notify('tw-drug-status','Lot '+r.lot_id+' received: '+r.remaining+' tablets');await loadDrug();
});};
$('tw-auth-save').onclick=()=>{void task('tw-drug-status',async()=>{
 var r=await api('/api/trial/subjects/'+n('tw-drug-subject')+'/drug-authorization',{method:'POST',
  body:JSON.stringify({prescription_ref:value('tw-rx'),signed_on:value('tw-rx-date'),
   allocation_reference:value('tw-allocation'),renal_assessment_ref:value('tw-renal'),
   authorized_dose_instruction:value('tw-instruction')})});
 $('tw-order-id').value=r.id;notify('tw-drug-status','Authorized order reference '+r.id);await loadDrug();
});};
$('tw-dispense-save').onclick=()=>{void task('tw-drug-status',async()=>{
 var r=await api('/api/trial/subjects/'+n('tw-drug-subject')+'/dispense',{method:'POST',
  body:JSON.stringify({authorization_id:n('tw-order-id'),lot_id:n('tw-lot-id'),
   quantity_issued:n('tw-issued'),issued_on:value('tw-issue-date')})});
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
 var r=await api('/api/trial/pharmacy/dispenses/'+n('tw-dispense-id')+'/return',{method:'POST',
  body:JSON.stringify({quantity_returned:n('tw-return-qty'),returned_on:value('tw-return-date'),
   disposition:value('tw-disposition')})});
 notify('tw-drug-status','Returned quantity recorded. Remaining unreconciled: '+r.unreconciled_quantity);await loadDrug();
});};
$('tw-invite-save').onclick=()=>{void task('tw-staff-status',async()=>{
 var r=await api('/api/trial/staff/invite',{method:'POST',body:JSON.stringify({
  username:value('tw-username'),display_name:value('tw-fullname'),role:value('tw-role')})});
 $('tw-invitation').classList.remove('hide');
 $('tw-invitation').textContent='Private activation for '+r.username+' ('+r.role+')\n'+
 r.activation_token+'\nInitial invitation expires in 7 days. After activation the staff account remains valid for 90 days. Hand the code privately.';
 notify('tw-staff-status','Inactive named account created. Activated access lasts 90 days.');
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
 notify('tw-mfa-status','MFA enabled. Future logins require your password and authenticator code.');
});};

let eligibilityItems=null;
async function loadEligibilitySchema(){
 eligibilityItems=await api('/api/trial/eligibility-schema');
 const makeFields=(group,items,label)=>{
  return '<h4>'+label+'</h4>'+Object.entries(items).map(([key,value])=>
   '<label>'+txt(value)+'<select data-eligibility="'+group+'" data-key="'+txt(key)+'">'+
   '<option value="">Not assessed</option><option value="true">Yes</option>'+
   '<option value="false">No</option></select></label>').join('');
 };
 $('tw-eligibility-fields').innerHTML=makeFields('inclusion',eligibilityItems.inclusion,'Inclusion: all must be Yes')+
  makeFields('exclusion',eligibilityItems.exclusion,'Exclusion: all must be No');
}
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
   reviewed_on:value('tw-review-on'),signed_source_reference:value('tw-source')
  })});
 notify('tw-status',r.eligible?
  'All protocol criteria checked and eligible; PI enrollment may proceed.':
  'Screening exclusion detected; enrollment is blocked. Preserve signed source.');
});};
for(const id of ['tw-cbc-date','tw-review-on'])$(id).value=today();
async function loadAccounts(){
 const accounts=await api('/api/trial/staff/accounts');
 $('tw-accounts').innerHTML='<table><thead><tr><th>Username</th><th>Role</th>'+
   '<th>Valid until</th><th>MFA</th><th>State</th><th>Access</th></tr></thead><tbody>'+
   accounts.map(x=>'<tr><td>'+txt(x.username)+'</td><td>'+txt(x.role)+'</td>'+
   '<td>'+txt(x.access_expires_at?x.access_expires_at.slice(0,10):'Legacy / no time limit')+'</td>'+
   '<td>'+(x.mfa_enabled?'Yes':'Not yet')+'</td>'+
   '<td>'+(x.active?'Active':'Inactive')+'</td><td>'+
   (x.active?'<button data-staff-id="'+txt(x.id)+'" data-staff-action="renew" class="secondary">Renew 90 days</button> '+
   '<button data-staff-id="'+txt(x.id)+'" data-staff-action="revoke">Revoke</button>':'—')+
   '</td></tr>').join('')+'</tbody></table>';
}
$('tw-accounts').addEventListener('click',e=>{
 const button=e.target.closest('button[data-staff-action]');if(!button)return;
 const action=button.dataset.staffAction,id=button.dataset.staffId;
 if(!confirm(action==='revoke'?'Immediately revoke this account and end all sessions?':
       'Authorize this person for another 90 days and end current sessions?'))return;
 void task('tw-staff-status',async()=>{
  const explanation=prompt('Enter an audit reason (at least 8 characters):');
  if(!explanation||explanation.trim().length<8)return;
  const result=await api('/api/trial/staff/accounts/'+encodeURIComponent(id)+'/'+action,
   {method:'POST',body:JSON.stringify({reason:explanation})});
  notify('tw-staff-status',result.username+' — '+(action==='renew'?'90-day access renewed':'Access revoked'));
  await loadAccounts();
 });
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
 return {occurred_on:value('tw-crf-date'),payload:crfValues(),occurrence_key:crfKey()};
}
async function crfSaveDraft(){
 clearTimeout(crfDraftTimer);
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
 const r=await api('/api/trial/crf/subjects/'+n('tw-crf-subject')+
  '/drafts/'+encodeURIComponent(value('tw-crf-section'))+
  '?occurrence_key='+encodeURIComponent(key));
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
function crfRender(){
 currentCrfSpec=currentCrfSchema?.[value('tw-crf-section')]||null;
 crfLoadedSection=value('tw-crf-section');crfLoadedSubject=n('tw-crf-subject');
 currentCrfEntry=null;
 $('tw-crf-descriptor').textContent=currentCrfSpec?
  currentCrfSpec.title+' · '+currentCrfSpec.repeat+' · CRF v3.0 (14 August 2026)':
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
 crfRender();await crfRestoreDraft();
}
async function loadCrfEntries(){
 const subject=n('tw-crf-subject');
 if(!subject){$('tw-crf-entries').textContent='Select a study participant';return;}
 const records=(await api('/api/trial/crf/subjects/'+subject+'/entries')).entries;
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
    x.updated_by!==$('currentUserId')?.value?
    '<button data-crf-review="'+x.id+'">Review</button>':'')+'</td></tr>').join('')+
  '</tbody></table></div>';
 $('tw-crf-entries')._records=records;
}
$('tw-crf-section').onchange=()=>{void task('tw-crf-status',async()=>{
 try{await crfSaveDraft();}catch(e){throw Error('Cannot change form with unsaved data: '+e.message);}
 crfRender();await crfRestoreDraft();await loadCrfEntries();
});};
$('tw-crf-subject').onchange=()=>{void task('tw-crf-status',async()=>{
 try{await crfSaveDraft();}catch(e){throw Error('Cannot change participant with unsaved data: '+e.message);}
 crfRender();await crfRestoreDraft();await loadCrfEntries();
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
 if(!currentCrfEntry&&!confirm('Submit this CRF form for independent verification?'))return;
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
  ' submitted, revision '+result.revision+' · independent review pending');
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
   const reason=prompt('Reason for independent CRF review (minimum 8 characters):');
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


/* The study overview is grounded in persisted counts, never demo values. */
const originalStudyDashboard=loadDashboard;
loadDashboard=async function(){
 await originalStudyDashboard();
 const target=$('dashboardResults');
 try{
  const [trial,forms]=await Promise.all([
   api('/api/trial/overview'),api('/api/trial/crf/completeness')
  ]);
  const lab=trial.pcr||{}, drug=trial.drug_accountability||{};
  const cards=[
   ['Screened',trial.screened,'Coded screening records'],
   ['Enrolled',trial.ever_enrolled,'Includes withdrawn/closed participants'],
   ['PCR scheduled',trial.scheduled_pcr_slots,'Seven protocol slots per enrolled subject'],
   ['PCR verified',trial.verified_protocol_pcr_slots,'Independent review completed'],
   ['Stock remaining',drug.tablets_in_stock,'450-mg tablets in study inventory'],
   ['Unreconciled issues',drug.tablets_not_yet_reconciled,'Not necessarily taken or lost']
  ];
  const kpi='<div class="dash-kpis">'+cards.map((x,i)=>
    '<div class="dash-card dash-kpi"><span class="accent" style="background:'+
    ['#405fe4','#27ba9c','#6e87bc','#2495aa','#ac8a37','#d77b42'][i]+'"></span>'+
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
   '<p class="dash-note">Count of submitted and independently verified CRF visits. PCR result verification is tracked separately.</p>'+
   '<div style="overflow-x:auto"><table style="width:100%;font-size:12px;border-collapse:collapse">'+
   '<thead><tr><th>Timepoint</th><th>Submitted</th><th>Verified</th><th>Needs correction</th></tr></thead>'+
   '<tbody>'+rows+'</tbody></table></div></div>';
  const note='<p class="warn-demo">Study status is computed from persisted records. '+
   'Enrollment and PCR completion do not imply endpoint adjudication or data lock. '+
   'Clinical activation remains blocked until go-live validation and recovery drills are signed off.</p>';
  target.insertAdjacentHTML('afterbegin',
    '<h3 style="margin-top:8px">Clinical trial progress</h3>'+note+kpi+visits+
    '<h3 style="margin:20px 0 12px">Registry and entry-review activity</h3>');
 }catch(err){
  target.insertAdjacentHTML('afterbegin','<p class="dash-note">Clinical trial metrics unavailable: '+txt(err.message)+'</p>');
 }
};

})();