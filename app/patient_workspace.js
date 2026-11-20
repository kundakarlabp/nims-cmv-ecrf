/* Patient-centred presentation over existing audited APIs; no clinical auto-submission. */
(function(){
'use strict';
const root=document.getElementById('workspace'),menu=root.querySelector('.tabs');
const context=document.getElementById('tw-participant-context');
const patientTabs=new Set(['registry','study','randomization','pcr','drug','crf','course','entry','dose']);
const style=document.createElement('style');
style.textContent=
 '#workspace{gap:14px}#workspace>.tabs .tw-legacy-nav{display:none!important}#workspace>.tabs:before{content:"NIMS CMV TRIAL"}'+
 '#workspace>.tabs .tw-main-nav{font-weight:700;display:flex;align-items:center;gap:9px}'+
 '#workspace>.tabs .tw-main-nav.active{background:#e9edff;color:#284fc2;box-shadow:inset 3px 0 #4167e6}'+
 '#workspace>.tabs .tw-main-nav[hidden]{display:none!important}'+
 '#tw-patient-banner{grid-column:2;display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:10px;padding:16px 20px;border-radius:14px;border:1px solid #dce5f4;background:#fff;min-width:0}'+
 '#tw-patient-banner h2{margin:3px 0;font-size:21px;overflow-wrap:anywhere}'+
 '#tw-patient-banner .tw-identity-secondary{font-size:13px;color:#52617e}'+
 '#tw-patient-banner .tw-stage-status{background:#eff4ff;color:#244e9b;padding:6px 10px;border-radius:20px;font-size:12px;font-weight:750}'+
 '#tw-patient-meta{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:#4e617a}'+
 '#tw-patient-subnav{grid-column:2;min-width:0;display:flex;align-items:center;gap:7px;flex-wrap:wrap;padding:5px 0}'+
 '#tw-patient-subnav button{margin:0;border-radius:9px;background:#edf1f9;color:#304764;padding:10px 12px;min-height:42px}'+
 '#tw-patient-subnav button.selected{background:#275bd9;color:#fff}'+
 '#workspace>#tw-participant-context{background:#fff;border:1px solid #e2e8f2;border-radius:12px;padding:13px 17px!important}'+
 '#tw-participant-context>label{display:inline-block;vertical-align:bottom;width:min(47%,400px);margin:3px 2% 3px 0}'+
 '#tw-participant-context #tw-context-detail{margin:7px 0 0}'+
 '#study .study-columns{display:block!important;max-width:1030px}'+
 '#study .tw-progress-stage{background:#fff;border:1px solid #dfe7f3;border-radius:13px;margin:10px 0;overflow:hidden}'+
 '#study .tw-progress-stage[open]{border-color:#a9bee9;box-shadow:0 1px 7px #213b7110}'+
 '#study .tw-progress-stage>summary{display:flex;align-items:center;justify-content:space-between;gap:8px;cursor:pointer;list-style:none;padding:15px 17px;font-weight:750;font-size:15px;background:#f6f8fd}'+
 '#study .tw-progress-stage>summary::-webkit-details-marker{display:none}'+
 '#study .tw-progress-stage>summary:after{content:"Expand";font-size:11px;color:#52729d;font-weight:500}'+
 '#study .tw-progress-stage[open]>summary:after{content:"Collapse"}'+
 '#study .tw-progress-stage .tw-progress-result{color:#597089;font-size:12px;font-weight:600;margin-left:auto}'+
 '#study .tw-progress-stage[data-step-status="complete"]>summary{background:#eff9f3}'+
 '#study .tw-progress-stage[data-step-status="complete"] .tw-progress-result{color:#207a49}'+
 '#study .tw-progress-stage[data-step-status="blocked"] .tw-progress-result{color:#b04b33}'+
 '#study .tw-progress-stage>.study-card{border:0;border-radius:0;margin:0;padding:16px 19px}'+
 '#study .tw-progress-stage>.study-card>h3{display:none}'+
 '#tw-more-screening{margin:12px 0;padding:10px 13px;border:1px solid #e2e8f2;border-radius:9px}'+
 '#tw-more-screening>summary{cursor:pointer;font-size:13px;font-weight:650;color:#3f5e85}'+
 '#tw-eligibility-fields label{display:grid;grid-template-columns:minmax(0,1fr) minmax(120px,165px);gap:10px;align-items:center;padding:6px 8px;border-bottom:1px solid #e9edf4;margin:0;min-height:48px}'+
 '#tw-eligibility-fields select{width:100%;max-width:165px}'+
 '#study #tw-inline-rand-submit:disabled{background:#c2cedc;cursor:not-allowed}'+
 '#study #tw-register-details{max-width:1030px;margin-top:16px}'+
 '#study #tw-register-details summary{cursor:pointer;color:#405b7e;font-size:13px}'+
 '#study #tw-enroll-randomize{display:none!important}'+
 '#tw-after-enrollment{max-width:1030px;margin:10px 0}#tw-after-enrollment button{margin:0}'+
 '@media(max-width:860px){#workspace>#tw-patient-banner,#workspace>#tw-patient-subnav{grid-column:1!important}'+
 '#tw-patient-banner{padding:12px;align-items:flex-start}#tw-patient-banner h2{font-size:17px}'+
 '#tw-patient-subnav{flex-wrap:nowrap;overflow-x:auto;padding:2px 0 5px}'+
 '#tw-patient-subnav button{white-space:nowrap;flex-shrink:0;font-size:12px}'+
 '#tw-participant-context>label{width:100%;margin:6px 0}'+
 '#study .tw-progress-stage>.study-card{padding:12px}#study .tw-progress-stage>summary{padding:13px;font-size:13px}}';
document.head.appendChild(style);

// Legacy route buttons retain their IDs and DOM state for the existing router.
for(const b of menu.querySelectorAll('button[id^="btn"]'))b.classList.add('tw-legacy-nav');
const mainButtons={};
const firstLegacyNavButton=menu.firstElementChild;
for(const [key,label,route] of [
 ['overview','Overview','dashboard'],['patients','Patients','study'],
 ['worklist','Worklist','tasks'],['reports','Review & reports','review'],
 ['staff','Staff access','staff'],['account','My account','security']]){
 const b=document.createElement('button');b.type='button';b.id='tw-nav-'+key;
 b.className='tw-main-nav';b.textContent=label;b.onclick=()=>{void tab(route);};
 menu.insertBefore(b,firstLegacyNavButton);mainButtons[key]=b;
}
const signOut=document.createElement('button');signOut.type='button';
signOut.id='tw-nav-logout';signOut.textContent='Log out';signOut.className='tw-main-nav secondary';
signOut.onclick=()=>{void logout();};menu.appendChild(signOut);

const banner=document.createElement('section');banner.id='tw-patient-banner';
banner.innerHTML='<div><div class="tw-identity-secondary">CURRENT PATIENT</div>'+
 '<h2 id="tw-banner-name">Select a patient</h2>'+
 '<div class="tw-identity-secondary" id="tw-banner-identifier">Search by hospital CR, name or study ID below.</div></div>'+
 '<div><span class="tw-stage-status" id="tw-banner-status">Not selected</span>'+
 '<div id="tw-patient-meta"></div></div>';
root.insertBefore(banner,context);
const subnav=document.createElement('nav');subnav.id='tw-patient-subnav';
subnav.setAttribute('aria-label','Patient workflow');
const subButtons={};
for(const [route,label] of [
 ['study','Start trial'],['pcr','Visits & PCR'],['drug','Treatment & safety'],
 ['course','Clinical record'],['registry','New patient']]){
 const b=document.createElement('button');b.type='button';b.id='tw-sub-'+route;
 b.textContent=label;b.onclick=()=>{void tab(route);};subnav.appendChild(b);subButtons[route]=b;
}
root.insertBefore(subnav,context.nextSibling);

// Progressive accordion stages keep the existing inputs and event handlers intact.
const study=document.getElementById('study'),columns=study.querySelector('.study-columns');
const randomCard=document.getElementById('tw-inline-rand-panel');
columns.appendChild(randomCard);
const headings=['Screening & consent','Eligibility','Confirm enrollment','Randomization'];
const steps=[];
for(const [index,card] of [...columns.children].entries()){
 const detail=document.createElement('details');detail.className='tw-progress-stage';
 detail.id='tw-progress-step-'+(index+1);
 const summary=document.createElement('summary');
 summary.innerHTML='<span>'+(index+1)+'. '+headings[index]+'</span>'+
  '<span class="tw-progress-result" id="tw-result-'+(index+1)+'">Pending</span>';
 card.replaceWith(detail);detail.appendChild(summary);detail.appendChild(card);
 steps.push(detail);
}
steps[0].open=true;
// Keep enrollment-critical fields visible; optional source metadata stays
// accessible without lengthening the routine screening path.
const moreScreening=document.createElement('details');
moreScreening.id='tw-more-screening';moreScreening.className='tw-extra-screening';
const extraHeading=document.createElement('summary');
extraHeading.textContent='Additional screening details (optional)';
moreScreening.appendChild(extraHeading);
const screeningCard=steps[0].querySelector('.study-card');
const screeningSave=document.getElementById('tw-screen-save');
screeningCard.insertBefore(moreScreening,screeningSave);
for(const id of ['tw-pis','tw-consent-language','tw-consent-obtained','tw-initials',
                 'tw-screen-age','tw-sex','tw-relationship']){
 const control=document.getElementById(id);
 if(control?.closest('label'))moreScreening.appendChild(control.closest('label'));
}
const register=document.getElementById('tw-register');
const registerDetails=document.createElement('details');registerDetails.id='tw-register-details';
const registerSummary=document.createElement('summary');
registerSummary.textContent='Screening and enrollment register · all subjects';
register.parentNode.insertBefore(registerDetails,register);
registerDetails.append(registerSummary,register);
const registerHeading=[...study.querySelectorAll('h3')].find(x=>x.textContent.includes('Screening and enrollment register'));
if(registerHeading)registerHeading.classList.add('hide');
const after=document.createElement('section');after.id='tw-after-enrollment';
const follow=document.createElement('button');follow.type='button';follow.className='secondary';
follow.textContent='Open visits and PCR';follow.onclick=()=>{void tab('pcr');};
after.appendChild(follow);study.insertBefore(after,registerDetails);
const doseShortcut=document.createElement('button');doseShortcut.id='tw-open-dose';
doseShortcut.className='secondary';doseShortcut.type='button';
doseShortcut.textContent='Open VGCV dose preview';doseShortcut.onclick=()=>{void tab('dose');};
document.getElementById('drug').insertAdjacentElement('afterbegin',doseShortcut);
const courseShortcut=document.createElement('button');courseShortcut.id='tw-open-generic';
courseShortcut.className='secondary';courseShortcut.type='button';
courseShortcut.textContent='Other dated clinical entries';courseShortcut.onclick=()=>{void tab('entry');};
document.getElementById('course').insertAdjacentElement('afterbegin',courseShortcut);

const previousTab=tab;
tab=async function(name){
 await previousTab(name);syncNavigation();
 if(activeTab==='study')await updateWorkflow();
};
const previousChoose=window.choose;
window.choose=async function(id){
 await previousChoose(id);
 if(selected===id){await updatePatientBanner();if(activeTab==='study')await updateWorkflow();}
};

let bannerRequest=0,workflowRequest=0,lastPatient=null,lastKey=null;
async function updatePatientBanner(){
 const id=selected,request=++bannerRequest;
 if(!id){
  document.getElementById('tw-banner-name').textContent='Select a patient';
  document.getElementById('tw-banner-identifier').textContent='Search by hospital CR, name or study ID below.';
  document.getElementById('tw-banner-status').textContent='Not selected';
  document.getElementById('tw-patient-meta').textContent='';return;
 }
 try{
  // IT administrators can use the registry, but should not read clinical
  // trial context unless the authenticated clinical workspace grants access.
  const clinicalRole=document.getElementById('currentRole').textContent.trim();
  const maySeeClinical=!!window.currentWorkspaceFullAccess||
   ['pi','consultant','scientist','nurse','pg','technician','microbiology','pharmacy','monitor'].includes(clinicalRole);
  const [patient,clinical]=await Promise.all([
   api('/api/patients/'+encodeURIComponent(id)),
   maySeeClinical?api('/api/trial/crf/patients/'+encodeURIComponent(id)+'/context'):Promise.resolve({subject:null})
  ]);
  if(selected!==id||request!==bannerRequest)return;
  const p=patient.patient||{},s=clinical.subject;
  document.getElementById('tw-banner-name').textContent=p.name||'Patient';
  document.getElementById('tw-banner-identifier').textContent='CR '+(p.cr_number||'—')+
   (s?.study_code?' · '+s.study_code:s?.screening_code?' · '+s.screening_code:'');
  document.getElementById('tw-banner-status').textContent=s?
   (s.status==='enrolled'?'Enrolled':s.status.replaceAll('_',' ')):'Registered';
  document.getElementById('tw-patient-meta').textContent='Transplant: '+(p.transplant_date||'not recorded')+
   (s?.donor_type?' · Donor: '+s.donor_type:'');
 }catch(e){if(request===bannerRequest)document.getElementById('tw-banner-status').textContent='Context unavailable';}
}
async function updateWorkflow(){
 const id=selected,request=++workflowRequest;
 if(!id){
  for(let i=0;i<steps.length;i++){
   steps[i].dataset.stepStatus='pending';
   document.getElementById('tw-result-'+(i+1)).textContent='Pending';
   steps[i].open=i===0;
  }
  return;
 }
 try{
  const clinical=await api('/api/trial/crf/patients/'+encodeURIComponent(id)+'/context');
  const s=clinical.subject;
  const eligibility=s?await api('/api/trial/subjects/'+s.id+'/eligibility'):null;
  if(request!==workflowRequest||selected!==id||activeTab!=='study')return;
  const eligible=eligibility?.eligibility?.baseline?.is_eligible===true;
  const checked=Boolean(eligibility?.eligibility);
  const randomized=Boolean(clinical.allocation?.randomized);
  const status=[
   {complete:!!s,blocked:s?.status==='consent_declined',label:s?'Saved':'Not started'},
   {complete:eligible,blocked:checked&&!eligible,label:eligible?'Confirmed':checked?'Not eligible':'Pending'},
   {complete:!!s?.enrolled_on,blocked:s?.status==='consent_declined',label:s?.enrolled_on?'Enrolled':'Pending'},
   {complete:randomized,blocked:s?.status==='consent_declined',label:randomized?'Randomized':'Pending'}
  ];
  for(let i=0;i<steps.length;i++){
   const stage=status[i];
   steps[i].dataset.stepStatus=stage.complete?'complete':stage.blocked?'blocked':'pending';
   document.getElementById('tw-result-'+(i+1)).textContent=stage.label;
  }
  const key=(s?.id||'none')+':'+s?.status+':'+eligible+':'+randomized;
  if(lastPatient!==id||lastKey!==key){
   let next=status.findIndex(x=>!x.complete&&!x.blocked);
   if(next<0)next=3;
   steps.forEach((step,i)=>{step.open=i===next;});
   lastPatient=id;lastKey=key;
  }
 }catch(e){if(request===workflowRequest)document.getElementById('tw-result-1').textContent='Reload to check';}
}
function syncNavigation(){
 const name=activeTab,isPatient=patientTabs.has(name);
 for(const [key,b] of Object.entries(mainButtons)){
  const match=key==='patients'?isPatient:key==='overview'?name==='dashboard':
   key==='worklist'?name==='tasks':key==='reports'?name==='review'||name==='due':
   key==='staff'?name==='staff':name==='security';
  b.classList.toggle('active',match);
  if(match)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');
 }
 mainButtons.staff.hidden=!window.currentAdmin&&!window.currentPiAuthorized;
 banner.classList.toggle('hide',!isPatient);
 context.classList.toggle('hide',!isPatient||!['pi','consultant','scientist','pg','nurse','technician','microbiology','pharmacy','monitor'].includes(document.getElementById('currentRole').textContent.trim()));
 subnav.classList.toggle('hide',!isPatient);
 const target=['study','randomization'].includes(name)?'study':
  ['crf','entry'].includes(name)?'course':name==='dose'?'drug':name;
 for(const [key,b] of Object.entries(subButtons))b.classList.toggle('selected',key===target);
}
window.addEventListener('cmv:workflow-updated',()=>{
 void updatePatientBanner();
 if(activeTab==='study')void updateWorkflow();
});
const previousFinish=window.finishLogin;
window.finishLogin=async function(result){
 await previousFinish(result);syncNavigation();
 if(selected)await updatePatientBanner();
};
const previousRegister=window.register;
window.register=async function(){
 const before=selected;await previousRegister();
 if(selected&&selected!==before){await updatePatientBanner();await tab('study');}
};
syncNavigation();
})();