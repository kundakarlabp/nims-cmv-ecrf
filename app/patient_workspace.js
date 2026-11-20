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

/* Screenshot-matched workspace: a compact desktop shell and a real mobile
   single-column layout, including Android browsers using desktop-site view. */
style.textContent+=`
html,body{max-width:100%;overflow-x:hidden}
body{background:#f5f7fb;color:#182b46}
body>header.tw-app-header{display:grid;grid-template-columns:minmax(205px,1fr) minmax(280px,500px) auto;
 gap:20px;align-items:center;padding:13px 3vw;border-bottom:1px solid #e4ebf5;box-shadow:0 1px 5px #14283e09}
.tw-app-header>div:first-child{display:grid;grid-template-columns:38px minmax(0,1fr);gap:1px 10px;align-items:center}
.tw-hospital-mark{grid-row:1/span 2;grid-column:1;width:37px;height:37px;border-radius:50%;background:#e8efff;
 border:2px solid #375b99;color:#375b99;display:grid;place-items:center;font-size:26px;font-weight:800}
.tw-app-header h1{grid-column:2;font-size:19px;letter-spacing:-.45px;line-height:1.3}
.tw-site-name{grid-column:2;font-size:12px;color:#65758d}
.tw-app-header #who{text-align:right;white-space:nowrap;font-size:12px;color:#405372}
.tw-app-header #tw-header-search{position:relative;min-width:0;max-width:100%;align-self:center}
#tw-header-search>label:first-child{display:block;margin:0}
#tw-header-search>label:first-child input{padding:12px 13px;border:1px solid #cdd7e6;border-radius:12px;
 min-height:44px;background:#fff;box-shadow:0 1px 4px #24384d09;font-size:14px}
#tw-header-search>label:nth-child(2){display:none;position:absolute;left:0;right:0;top:100%;z-index:16;
 padding:9px 10px;background:#fff;box-shadow:0 9px 22px #152a4740;border:1px solid #cad7e8;border-radius:0 0 12px 12px;margin:0}
#tw-header-search.tw-searching>label:nth-child(2){display:block}
#tw-header-search select{min-height:44px;max-width:100%}
#tw-header-search option{white-space:normal}
#workspace{display:grid!important;grid-template-columns:194px minmax(0,1fr);align-items:start;
 gap:17px;padding:17px 20px;max-width:1520px;margin:0 auto}
#workspace.hide{display:none!important}
#workspace>.tabs{grid-column:1!important;grid-row:1!important;position:sticky;top:15px;width:100%;
 border:1px solid #e1e8f2;border-radius:13px;padding:12px 9px;gap:3px;background:#fff}
#workspace>.tabs:before{content:"NIMS CMV TRIAL";padding:5px 10px 11px}
#workspace>.tabs .tw-main-nav{min-height:43px;line-height:1.35;padding:10px 12px;font-size:13px}
#workspace>.tabs .tw-main-nav.active{background:#e9efff;color:#2550aa;box-shadow:inset 3px 0 #3568d5}
#workspace>.tabs a{font-size:12px;color:#46648c;word-break:break-word}
#workspace>#tw-workspace-main{grid-column:2;grid-row:1;min-width:0;display:flex;flex-direction:column;gap:12px}
#tw-workspace-main>.grid{display:none!important}
#tw-workspace-main>.panel,#tw-workspace-main>#dashboard,#tw-workspace-main>.study-card,
#tw-workspace-main>#review{grid-column:auto!important;grid-row:auto!important;width:100%;min-width:0;margin:0}
#tw-workspace-main>.panel{padding:18px;border:1px solid #e1e8f2;border-radius:14px;box-shadow:0 2px 10px #152d4708}
#tw-workspace-main>.panel.hide,#tw-workspace-main>section.hide{display:none!important}
#tw-workspace-main #tw-patient-banner{display:flex;gap:14px;align-items:center;justify-content:flex-start;
 background:#fff;border:1px solid #dde6f3;border-radius:14px;padding:14px 18px;margin:0;min-width:0}
#tw-workspace-main #tw-patient-banner>div:first-of-type{flex:1;min-width:190px}
#tw-workspace-main #tw-patient-banner h2{font-size:21px;font-weight:750;margin:3px 0;letter-spacing:-.35px}
.tw-avatar{width:47px;height:47px;flex:0 0 47px;border-radius:50%;background:#e4ebf8;position:relative}
.tw-avatar:before{content:"";position:absolute;top:9px;left:18px;width:12px;height:12px;border-radius:50%;background:#7e96b4}
.tw-avatar:after{content:"";position:absolute;bottom:8px;left:11px;width:26px;height:15px;border-radius:60% 60% 30% 30%;background:#7e96b4}
#tw-workspace-main #tw-patient-banner .tw-stage-status{display:inline-block;background:#eaf2ff;padding:5px 10px;border-radius:20px}
#tw-workspace-main #tw-patient-meta{margin-top:7px;line-height:1.5}
#tw-workspace-main #tw-patient-subnav{margin:0;padding:0 8px;display:flex;gap:4px;
 background:transparent;border-bottom:1px solid #dbe4f2;min-height:40px}
#tw-workspace-main #tw-patient-subnav button{border:0;border-bottom:3px solid transparent;border-radius:0;
 background:transparent;color:#415779;font-size:13px;font-weight:650;white-space:nowrap;padding:10px 14px;min-height:42px}
#tw-workspace-main #tw-patient-subnav button.selected{background:transparent;border-bottom-color:#3468d5;color:#2054b2}
#tw-workspace-main #tw-patient-subnav #tw-sub-registry{margin-left:auto;color:#2356b7}
#tw-workspace-main #tw-participant-context{border:1px solid #e1e7f1;border-radius:10px;
 margin:0!important;padding:9px 15px!important;display:flex;flex-wrap:wrap;gap:8px 12px;align-items:center}
#tw-participant-context #tw-context-allocation{font-size:13px;font-weight:650;color:#3b5374}
#tw-participant-context #tw-context-detail{display:none}
#tw-participant-context #tw-open-course{display:none}
#tw-participant-context #tw-record-switch{margin:0 0 0 auto;max-width:100%}
#tw-record-switch summary{cursor:pointer;color:#466999;font-size:12px}
#tw-record-switch label{margin:8px 0;width:min(410px,100%)}
#tw-context-error:empty{display:none}
#tw-patient-subnav.hide,#tw-patient-banner.hide,#tw-participant-context.hide{display:none!important}
#study>h2{font-size:20px;letter-spacing:-.4px;margin:0 0 6px}
#study>.hint{margin:0 0 10px}
#study #tw-progress-track{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px;
 padding:6px 0 13px;border-bottom:1px solid #e4eaf2;margin-bottom:12px}
#tw-progress-track button{display:flex;align-items:center;justify-content:center;gap:8px;
 border:0;background:transparent;color:#5a6f8b;padding:8px 3px;margin:0;min-height:40px;
 text-align:left;font-size:12px;font-weight:650}
#tw-progress-track button>span:first-child{width:27px;height:27px;flex:0 0 27px;border:1px solid #c9d4e3;
 display:grid;place-items:center;border-radius:50%;background:#f3f6fb;font-size:12px}
#tw-progress-track button.done>span:first-child{background:#208456;color:#fff;border-color:#208456}
#tw-progress-track button.current>span:first-child{background:#e2edff;color:#245ac2;border:2px solid #376ada}
#tw-progress-track button.done{color:#28734f}
#study .tw-progress-stage{margin:0 0 10px;border-color:#dce6f2;border-radius:11px}
#study .tw-progress-stage[open]{box-shadow:0 2px 8px #1636540c}
#study .tw-progress-stage>summary{background:#f4f7fc;border-bottom:1px solid #e2e9f4;
 padding:12px 14px;font-size:14px}
#study .tw-progress-stage[data-step-status="complete"]>summary{background:#eaf7ef}
#study .tw-progress-stage>.study-card{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));
 gap:8px 14px;padding:14px}
#study .tw-progress-stage>.study-card label{font-size:12px;margin:2px 0;min-width:0}
#study .tw-progress-stage>.study-card input:not([type="checkbox"]),
#study .tw-progress-stage>.study-card select{margin-top:4px;min-height:40px;padding:8px 10px}
#study .tw-progress-stage>.study-card>p,#study .tw-progress-stage>.study-card>div,
#study .tw-progress-stage>.study-card>details,#study .tw-progress-stage>.study-card>h4{grid-column:1/-1}
#study .tw-progress-stage>.study-card>button{justify-self:start;margin:4px 0;grid-column:1/-1}
#tw-eligibility-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 13px}
#tw-eligibility-fields h4,#tw-eligibility-fields p{grid-column:1/-1;margin:8px 0}
#tw-eligibility-fields label{grid-template-columns:minmax(0,1fr) minmax(95px,130px);line-height:1.35}
#tw-eligibility-fields select{min-height:37px}
#tw-trial-layout{display:grid;grid-template-columns:minmax(0,1fr) 225px;align-items:start;gap:14px}
#tw-trial-layout .study-columns{min-width:0;margin:0}
#tw-next-steps{background:#fff;border:1px solid #dbe5f4;border-radius:12px;overflow:hidden;align-self:start}
#tw-next-steps h3{margin:0;padding:12px;background:#edf4ff;color:#244670;font-size:15px}
#tw-next-steps ul{list-style:none;padding:4px 12px;margin:0}
#tw-next-steps li{display:flex;gap:7px;border-bottom:1px solid #edf0f6;padding:11px 0;font-size:12px;line-height:1.5}
#tw-next-steps li:last-child{border:0}
#tw-next-steps li:before{content:"•";color:#7690b3;font-size:17px;line-height:1}
#tw-next-steps li.done:before{content:"✓";color:#248756}
#tw-activity{margin-top:10px;padding:10px 14px;border:1px solid #e0e7f1;border-radius:11px}
#tw-activity summary{cursor:pointer;font-size:13px;font-weight:700;color:#405a79}
#tw-activity .tw-activity-line{display:flex;flex-wrap:wrap;gap:6px 10px;border-bottom:1px solid #edf0f6;
 padding:6px 0;font-size:12px;color:#4b617b}
#tw-activity p.hint{font-size:12px}
#tw-workspace-main #tw-directory-panel{max-width:none}
.tw-directory-columns{display:grid;grid-template-columns:minmax(0,1fr) minmax(270px,1fr);gap:18px}
.tw-directory-finder,#registerPanel{padding:15px;border:1px solid #e5eaf3;border-radius:12px;min-width:0}
.tw-directory-finder .patient{border:1px solid #e5ebf4;padding:11px}
#registerPanel h2{margin-top:0!important}
#registry{margin-top:0!important}
#tw-workspace-main #review{padding:18px}
.tw-page-heading{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:9px}
.tw-page-heading h2{margin:4px 0;font-size:21px}
.tw-page-heading .hint{margin:4px 0}
.tw-eyebrow{color:#657b9d;font-size:11px;font-weight:800;letter-spacing:.7px}
.tw-report-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px;margin:12px 0}
.tw-report-metrics .tw-metric{border:1px solid #e0e7f2;border-radius:10px;padding:12px;background:#f8faff}
.tw-metric strong{display:block;font-size:25px;color:#24446c}
.tw-metric span{font-size:11px;color:#60718b}
.tw-report-completeness{border:1px solid #e2e8f1;border-radius:12px;margin:12px 0;padding:12px 15px}
.tw-report-completeness h3,.tw-report-subtitle{font-size:15px;margin:0 0 6px}
.tw-report-completeness table{width:100%;border-collapse:collapse;font-size:12px}
.tw-report-completeness th,.tw-report-completeness td{text-align:left;padding:8px 5px;border-bottom:1px solid #e6ecf4}
#reviewResults .tw-review-item{border:1px solid #e1e8f2;border-radius:10px;margin:8px 0;overflow:hidden}
#reviewResults .tw-review-item>summary{cursor:pointer;display:flex;gap:8px;align-items:center;justify-content:space-between;
 padding:11px 13px;background:#f8faff;font-size:13px}
#reviewResults .tw-review-item>div{padding:12px}
#reviewResults .tw-review-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:4px 14px}
#reviewResults .tw-review-fields div{padding:7px 0;border-bottom:1px solid #edf1f5}
#reviewResults .tw-review-fields dt{font-size:11px;color:#637690}
#reviewResults .tw-review-fields dd{font-size:12px;color:#20364f;margin:3px 0;overflow-wrap:anywhere}
#reviewResults .tw-review-status{font-size:11px;color:#537197}
#tw-workspace-main>.panel,#tw-workspace-main>.panel .study-card{overflow-wrap:anywhere}
#tw-workspace-main button{touch-action:manipulation}
#tw-system-details{border-top:1px solid #e2e7ee;margin:16px 0;padding:12px 0}
#tw-system-details summary{font-size:12px;color:#587198;cursor:pointer}
#tw-system-details small{display:block;font-size:11px;margin:5px 0}
#tw-account-links{display:flex;gap:10px;flex-wrap:wrap}
#tw-account-links a{font-size:12px}
#tw-mobile-menu{display:none}
@media(max-width:1250px){
 #workspace{display:block!important;max-width:940px;padding:10px 12px}
 #workspace>#tw-workspace-main{width:100%;min-width:0;gap:9px}
 #workspace>.tabs{display:none;position:static;width:100%;margin:8px 0;box-shadow:none}
 #workspace.mobile-nav-open>.tabs{display:flex}
 body>header.tw-app-header{grid-template-columns:minmax(0,1fr) auto;gap:9px;padding:10px 13px}
 #tw-mobile-menu{display:flex;grid-column:2;grid-row:1;align-items:center;justify-content:center;
 background:#eaf0ff;color:#2b4e8c;padding:8px 11px;font-size:12px;min-height:40px;max-width:200px;margin:0}
 .tw-app-header>div:first-child{grid-column:1;grid-row:1}
 #tw-header-search{grid-column:1 / -1;grid-row:2}
 .tw-app-header #who{grid-column:1 / -1;text-align:left;font-size:11px}
 #tw-patient-banner{padding:12px!important}
 #tw-trial-layout{grid-template-columns:minmax(0,1fr) 190px;gap:10px}
}
@media(max-width:750px){
 #workspace{padding:8px 10px}
 #tw-workspace-main #tw-patient-banner{gap:9px;flex-wrap:wrap}
 #tw-workspace-main #tw-patient-banner>div:first-of-type{flex:1;min-width:160px}
 #tw-workspace-main #tw-patient-banner h2{font-size:17px}
 .tw-avatar{width:38px;height:38px;flex:0 0 38px}
 .tw-avatar:before{left:14px;top:6px}.tw-avatar:after{left:7px}
 #tw-workspace-main #tw-patient-subnav{overflow-x:auto;flex-wrap:nowrap}
 #tw-workspace-main #tw-patient-subnav button{padding:9px 10px;font-size:12px;flex-shrink:0}
 #tw-trial-layout{grid-template-columns:minmax(0,1fr)}
 #tw-next-steps{order:-1}
 #tw-next-steps ul{display:flex;gap:12px;flex-wrap:wrap}
 #tw-next-steps li{border:0;flex:1 1 150px}
 #tw-eligibility-fields{grid-template-columns:1fr}
 .tw-directory-columns{grid-template-columns:1fr}
 .tw-report-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}
}
@media(max-width:430px){
 #workspace{padding:6px 8px}
 #study .tw-progress-stage>.study-card{grid-template-columns:1fr}
 #study #tw-progress-track{gap:1px}
 #tw-progress-track button{display:flex;flex-direction:column;gap:2px;align-items:center;font-size:10px}
 #tw-eligibility-fields label{grid-template-columns:minmax(0,1fr) 112px}
 #tw-workspace-main>.panel{padding:12px}
 .tw-app-header h1{font-size:15px}
 #reviewResults .tw-review-fields{grid-template-columns:1fr}
}
`;
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
// Keep one sign-out action; the original application sign-out is replaced,
// not duplicated. Leave the legacy button's handler in place for older routes.
const legacyLogout=[...menu.querySelectorAll('button')].find(b=>b.textContent.trim()==='Log out');
if(legacyLogout)legacyLogout.classList.add('tw-legacy-nav');
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
root.insertBefore(subnav,context);

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

/* A single two-column shell fixes the grid-row gaps in the current app.
   Existing sections remain in the DOM with the same IDs and API handlers. */
const legacyGrid=root.querySelector('.grid');
const directory=legacyGrid.querySelector('section.panel:first-child');
directory.id='tw-directory-panel';
directory.classList.add('hide');
const registration=directory.querySelector('#registerPanel');
const directoryFinder=document.createElement('section');
directoryFinder.className='tw-directory-finder';
const searchLabel=document.createElement('label');
searchLabel.textContent='Find a patient';
searchLabel.appendChild(document.getElementById('search'));
directoryFinder.append(searchLabel,document.getElementById('patients'));
const directoryLayout=document.createElement('div');
directoryLayout.className='tw-directory-columns';
directory.insertBefore(directoryLayout,directory.firstChild);
directoryLayout.append(directoryFinder,registration);
directory.querySelector('h2')?.remove();
for(const id of ['review','registry','entry','dose','due']){
 const node=document.getElementById(id);
 if(node){node.classList.add('tw-workspace-panel');root.appendChild(node);}
}
root.appendChild(directory);
document.getElementById('review').classList.add('panel');
document.getElementById('review').querySelector('h2').textContent='Reports & source verification';
document.getElementById('review').insertAdjacentHTML('afterbegin',
 '<div class="tw-page-heading"><div><span class="tw-eyebrow">STUDY REPORTS</span>'+
 '<h2>Reports & verification</h2><p class="hint">Live study metrics, scheduled follow-up completeness and source verification.</p></div>'+
 '<button id="tw-report-reload" type="button" class="secondary">Refresh reports</button></div>'+
 '<div id="tw-report-metrics" class="tw-report-metrics" aria-live="polite"></div>'+
 '<section class="tw-report-completeness"><h3>Protocol follow-up completeness</h3>'+
 '<p class="hint">Seven protocol months; submitted forms and source verification are reported separately from PCR results.</p>'+
 '<div id="tw-report-visits"></div></section>'+
 '<h3 class="tw-report-subtitle">Entries requiring source review</h3>');
document.getElementById('review').querySelector('h2:not(.tw-page-heading h2)')?.classList.add('hide');
const main=document.createElement('main');main.id='tw-workspace-main';
root.appendChild(main);
for(const node of [...root.children]){
 if(node!==menu&&node.id!=='tw-mobile-menu'&&node!==main)main.appendChild(node);
}
// Patient identity, tabs and clinical status stay adjacent in one continuous column.
main.prepend(banner,subnav,context);
legacyGrid.classList.add('hide');
// Put the one authoritative CR/name/study-ID search in the page header.
// Moving the actual controls preserves the validated search and selection handlers.
const header=document.querySelector('body>header'),brand=header.querySelector('div:first-child');
header.classList.add('tw-app-header');
brand.querySelector('h1').textContent='NIMS CMV Trial · eCRF';
const site=document.createElement('span');site.className='tw-site-name';site.textContent='NIMS Hyderabad';
brand.insertBefore(site,document.getElementById('environmentStatus'));
brand.insertAdjacentHTML('afterbegin','<span class="tw-hospital-mark" aria-hidden="true">+</span>');
const searchHeader=document.createElement('div');searchHeader.id='tw-header-search';
const searchInput=document.getElementById('tw-context-find');
const searchResult=document.getElementById('tw-context-find-results');
const findLabel=searchInput.closest('label'),resultLabel=searchResult.closest('label');
searchHeader.append(findLabel,resultLabel);
header.insertBefore(searchHeader,document.getElementById('who'));
searchInput.placeholder='Search patient name, CR number or study ID';
searchInput.setAttribute('aria-label','Search patient name, CR number or study ID');
findLabel.firstChild.textContent='';
resultLabel.firstChild.textContent='Select matching patient';
const showMatches=()=>{searchHeader.classList.toggle('tw-searching',searchInput.value.trim().length>=3);};
searchInput.addEventListener('input',showMatches);
searchResult.addEventListener('change',()=>{searchHeader.classList.remove('tw-searching');});
const menuToggle=document.getElementById('tw-mobile-menu');
header.insertBefore(menuToggle,searchHeader);
// Hide secondary status labels on everyday views but preserve them for
// environment and release diagnostics.
const details=document.createElement('details');details.id='tw-system-details';
details.innerHTML='<summary>System information</summary>';
details.append(document.getElementById('environmentStatus'),document.getElementById('tw-live-build'));
document.getElementById('security').append(details);
// Keep ChatGPT and system operations under account tools, not as odd menu items.
const links=document.createElement('div');links.id='tw-account-links';
document.getElementById('security').append(links);
for(const id of ['chatgptConnectionLink','operationsLink']){
 const link=document.getElementById(id);if(link)links.appendChild(link);
}

syncNavigation();
})();