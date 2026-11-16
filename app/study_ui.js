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
 field('Informed consent signed','tw-consent-date','date')+field('Signed ICF version','tw-icf')+
 choose('Donor CMV IgG','tw-digg',[['positive','Positive'],['negative','Negative'],['unknown','Unknown']])+
 choose('Recipient CMV IgG','tw-rigg',[['positive','Positive'],['negative','Negative'],['unknown','Unknown']])+
 choose('Donor type','tw-donor',[['living','Living'],['deceased','Deceased']])+
 choose('rATG induction','tw-ratg',[['','Undocumented'],['true','Yes'],['false','No']])+
 '<label><input id="tw-eligible" type="checkbox" style="width:auto"> Signed protocol eligibility reviewed</label>'+
 btn('Save screening','tw-screen-save')+'</section>'+
 '<section class="study-card"><h3>2 · PI enrollment verification</h3>'+
 choose('Screened subject','tw-screened',[])+field('Enrollment date','tw-enroll-date','date')+
 field('Approved PCR anchor date','tw-anchor-date','date')+
 choose('Schedule anchor source','tw-anchor-basis',[['transplant_date','Transplant date'],['enrollment_date','Enrollment date'],['randomization_date','Randomization date'],['prophylaxis_start_date','Prophylaxis start date']])+
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
panel('staff','Staff access',
 '<div class="study-card"><h3>Individual account invitation</h3>'+
 field('Unique username','tw-username')+field('Staff name','tw-fullname')+
 choose('Delegated role','tw-role',[['scientist','Project scientist'],['nurse','Research nurse'],['technician','Lab technician'],['microbiology','Microbiology'],['pharmacy','MSS pharmacist'],['consultant','Consultant'],['pg','PG resident'],['monitor','CRA / monitor']])+
 btn('Generate one-time staff activation','tw-invite-save')+
 '<div id="tw-invitation" class="status hide" style="white-space:pre-wrap"></div></div>'+
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
var perms={study:['pi','consultant','scientist'],pcr:['pi','consultant','scientist','nurse','technician','microbiology','monitor'],drug:['pi','consultant','scientist','pharmacy','monitor'],staff:['pi','admin']};
function setRole(){
 var r=$('currentRole').textContent.trim();
 for(const k of Object.keys(perms))$('btn'+k).classList.toggle('hide',!perms[k].includes(r));
 for(const [id,roles] of [
  ['tw-screen-save',['pi','consultant','scientist']],['tw-enroll-save',['pi']],
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
 if(['study','pcr','drug','staff'].includes(name)){
  if(activeTab==='entry'){try{await saveDraftNow();}catch(e){show('msg','Draft not saved: '+e.message,true);return;}}
  activeTab=name;
  for(const section of ['dashboard','registry','review','entry','dose','due','study','pcr','drug','staff']){
   $(section).classList.toggle('hide',section!==name);
   $('btn'+section).classList.toggle('selected',section===name);
  }
  root.querySelector('.grid').classList.add('hide');
  await task(name==='pcr'?'tw-pcr-status':name==='drug'?'tw-drug-status':'tw-status',async()=>{
   if(name==='study'){await loadRegistry();await loadSubjects();}
   if(name==='pcr'){await loadSubjects();await loadPCR();}
   if(name==='drug'){await loadSubjects();await loadDrug();}
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
 var active=studySubjects.filter(x=>x.status==='enrolled');
 for(const id of ['tw-pcr-subject','tw-drug-subject'])fill(id,active,'id',x=>x.study_code);
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
  donor_type:value('tw-donor'),ratg_induction:value('tw-ratg')===''?null:value('tw-ratg')==='true',
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
 r.activation_token+'\nExpires in 48 hours. Hand over individually, never in public chat.';
 notify('tw-staff-status','Account created inactive. Recipient sets their own password on activation.');
});};
$('tw-activate-save').onclick=()=>{void task('tw-activate-status',async()=>{
 var r=await api('/api/trial/staff/activate',{method:'POST',body:JSON.stringify({
  token:value('tw-token'),password:value('tw-password')})});
 $('tw-token').value='';$('tw-password').value='';
 notify('tw-activate-status','Account '+r.username+' activated. Sign in above.');
});};
})();