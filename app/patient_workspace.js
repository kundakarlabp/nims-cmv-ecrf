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

style.textContent+=`
#pcr.tw-not-enrolled>*:not(h2):not(.hint):not(#tw-pcr-empty):not(#tw-pcr-status){display:none!important}
#pcr #tw-pcr-empty{padding:18px;border:1px solid #dbe6f3;border-radius:12px;background:#f6f9ff;margin:8px 0}
#pcr #tw-pcr-empty h3{margin:0 0 7px}
.tw-clinical-section{border:1px solid #e1e8f2;border-radius:11px;margin:10px 0;overflow:hidden;background:#fff;min-width:0}
.tw-clinical-section>summary{padding:12px 14px;cursor:pointer;background:#f6f8fd;
 color:#314d73;font-size:13px;font-weight:700;list-style:revert}
.tw-clinical-section>.study-card{margin:0;border:0;box-shadow:none}
#drug>.study-columns,#pcr>.study-columns{grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
#drug>.study-columns .tw-clinical-section,#pcr>.study-columns .tw-clinical-section{align-self:start;margin:0}
#tw-advanced-payload{max-width:100%;margin:9px 0}
#tw-advanced-payload #advancedPayload{padding:8px 12px}
#course #tw-course-actions{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px}
#course #tw-course-actions button{white-space:normal;text-align:left;padding:9px 11px;margin:0;font-size:12px}
#course #tw-course-records>.study-card{margin:9px 0}
#course #tw-course-records summary{cursor:pointer}
#course #tw-course-records dl{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
#course #tw-course-records dt{font-size:11px;color:#536988}
#course #tw-course-records dd{margin:0;overflow-wrap:anywhere;font-size:12px}
@media(max-width:1250px){#tw-workspace-main #tw-participant-context{grid-column:1!important}}
@media(max-width:750px){
 #drug>.study-columns,#pcr>.study-columns{grid-template-columns:minmax(0,1fr)}
 #course #tw-course-actions{grid-template-columns:repeat(2,minmax(0,1fr))}
}
`;

style.textContent+=`
#tw-trial-history{margin:0;border:0}
#tw-trial-history.tw-in-progress>summary{display:none}
#tw-trial-history>summary{font-size:12px;padding:10px 13px;margin:4px 0 11px;
 color:#46658b;background:#f8faff;border:1px solid #dfe8f4;border-radius:10px;cursor:pointer}
#tw-completed-trial{margin:9px 0 14px;padding:18px;border:1px solid #cce1d3;
 background:#f5fbf7;border-radius:12px}
#tw-completed-trial.hide{display:none!important}
#tw-completed-trial h3{font-size:18px;color:#1f4937;margin:7px 0}
#tw-completed-trial .hint{margin:6px 0 12px}
.tw-completed-badge{display:inline-block;padding:4px 9px;background:#def4e5;
 color:#206f48;border-radius:20px;font-size:11px;font-weight:700}
.tw-completed-actions{display:flex;gap:8px;flex-wrap:wrap}
.tw-completed-actions>button{min-height:43px;margin:0}
.tw-eligibility-group{border:1px solid #dfe7f3;border-radius:10px;margin:10px 0;overflow:hidden}
.tw-eligibility-group>summary{display:flex;justify-content:space-between;gap:8px;
 align-items:center;padding:12px;background:#f5f7fc;cursor:pointer;font-weight:700;font-size:13px}
.tw-eligibility-group>summary strong{font-size:12px;color:#567393;white-space:nowrap}
.tw-eligibility-group[data-complete="true"]>summary{background:#eef9f1}
.tw-eligibility-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 12px;padding:8px}
#tw-eligibility-fields .tw-eligibility-grid label{display:grid;
 grid-template-columns:minmax(0,1fr) minmax(105px,130px);padding:6px 8px;
 min-height:48px;border-bottom:1px solid #e9eef5}
.tw-eligibility-progress{padding:9px 11px;background:#eff5ff;color:#3b5c89;
 font-weight:700;font-size:12px;border-radius:8px}
.tw-course-warning{padding:12px 14px;margin:10px 0;background:#fff8f2;
 border:1px solid #f0c2a9;border-radius:10px;color:#79442b;font-size:13px}
.tw-course-warning p{font-size:12px;line-height:1.5}
.tw-overview-header,.tw-section-title{display:flex;justify-content:space-between;align-items:center;gap:12px}
.tw-overview-header h2{margin:4px 0;font-size:21px}
.tw-overview-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:13px 0}
.tw-overview-kpi{background:#fff;border:1px solid #e0e8f3;border-radius:12px;padding:16px}
.tw-overview-kpi strong{font-size:25px;color:#25466b;display:block}
.tw-overview-kpi span{font-size:12px;color:#586e88}
.tw-compact-overview-card{padding:16px;background:#fff;border:1px solid #e0e8f3;border-radius:12px;margin:10px 0}
.tw-section-title h3{font-size:15px;margin:0 0 7px}
.tw-section-title span{font-size:12px;color:#667b93}
.tw-recruit-track{height:9px;background:#e9eff8;border-radius:20px;margin:9px 0;overflow:hidden}
.tw-recruit-track>div{height:100%;background:#3c66d6}
.tw-overview-action{width:100%;text-align:left;display:flex;align-items:start;flex-direction:column;
 gap:4px;background:#f8faff;color:#28476d;border:1px solid #e5ebf4;margin:6px 0;padding:11px 13px}
.tw-overview-action span{font-size:12px}
.tw-overview-action strong{font-size:13px}
.tw-overview-more{margin:12px 0;padding:13px 16px;background:#fff;border:1px solid #e1e8f2;border-radius:12px}
.tw-overview-more>summary{cursor:pointer;font-size:13px;font-weight:700;color:#3d628c}
.tw-overview-minis{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:12px 0}
.tw-overview-minis>div{background:#f5f8fd;padding:10px;border-radius:9px}
.tw-overview-minis strong{font-size:21px;display:block;color:#314f77}
.tw-overview-minis span{font-size:11px;color:#60758e}
@media(max-width:750px){
 .tw-eligibility-grid{grid-template-columns:1fr}
 .tw-overview-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}
 .tw-overview-minis{grid-template-columns:repeat(2,minmax(0,1fr))}
 .tw-completed-actions{flex-direction:column}
 .tw-completed-actions button{width:100%}
}
`;
style.textContent+=`
#reviewResults .tw-nested-fields{padding:6px 10px;margin:4px 0;border-left:2px solid #dae5f2;background:#f7f9fe}
#reviewResults .tw-nested-fields>div{padding:5px 0;border-bottom:1px solid #e5edf8}
#reviewResults .tw-long-source{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.6;padding:8px}
#reviewResults .tw-field-list{margin:5px 0;padding-left:19px;line-height:1.5}
#reviewResults .tw-review-fields>div dd>details>summary{font-size:12px;cursor:pointer;color:#496d9b}
`;
style.textContent+=`
#course #tw-course-actions{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}
#course .tw-course-group{border:1px solid #e2e8f3;border-radius:10px;
 background:#fff;overflow:hidden;align-self:start}
#course .tw-course-group>summary{padding:12px 13px;background:#f6f9fe;cursor:pointer;
 font-size:13px;color:#34537c;font-weight:700}
#course .tw-course-group-actions{display:flex;gap:6px;flex-direction:column;padding:9px}
#course .tw-course-group-actions button{text-align:left;margin:0;padding:10px 12px;min-height:42px}
#course .tw-course-source{white-space:pre-wrap;overflow-wrap:anywhere;padding:9px;line-height:1.5}
@media(max-width:750px){#course #tw-course-actions{grid-template-columns:minmax(0,1fr)}}
`;
style.textContent += "\n/* Nov mobile QA: form widths must follow available content width rather than\n   two-column desktop defaults on Chrome's scaled desktop-site viewport. */\n#study #tw-trial-layout{grid-template-columns:minmax(0,1fr)!important}\n#study #tw-next-steps{margin:0 0 10px;max-width:none}\n#study #tw-next-steps ul{display:flex;flex-wrap:wrap;gap:8px}\n#study #tw-next-steps li{flex:1 1 145px;border:0;background:#f6f9fe;border-radius:8px;padding:8px}\n#study .tw-progress-stage>.study-card{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));min-width:0}\n#study #tw-eligibility-fields{grid-column:1/-1;width:100%;min-width:0;display:block!important}\n#study #tw-eligibility-fields .tw-eligibility-grid{display:grid!important;grid-template-columns:minmax(0,1fr)!important;gap:0!important;min-width:0}\n#study #tw-eligibility-fields .tw-eligibility-grid label{display:grid!important;grid-template-columns:minmax(0,1fr) 132px!important;\n align-items:center;gap:12px;min-width:0!important;width:100%!important;\n overflow-wrap:normal;word-break:normal;white-space:normal;line-height:1.5;padding:9px 11px}\n#study #tw-eligibility-fields .tw-eligibility-grid label select{min-width:0!important;width:100%!important;\n max-width:132px!important;margin:0!important;font-size:13px}\n#study .tw-eligibility-group,#study .tw-eligibility-group>summary{min-width:0;width:100%}\n#tw-crf-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}\n#tw-crf-fields label.study-card{margin:0!important;padding:12px!important;min-width:0}\n#tw-crf-fields label.study-card [data-crf-field]{min-height:44px}\n#tw-patient-banner{position:relative}\n#tw-switch-patient{margin:0;min-height:36px;padding:7px 10px;font-size:12px;\n background:#edf3ff;color:#2b5a9a}\n#tw-participant-context #tw-record-switch{display:none!important}\n#tw-header-search .tw-search-native{display:none!important}\n#tw-search-suggestions{position:absolute;top:calc(100% + 3px);left:0;right:0;z-index:120;\n background:#fff;border:1px solid #cfdced;border-radius:12px;\n box-shadow:0 12px 28px #1e3a5b25;max-height:300px;overflow-y:auto;padding:5px}\n#tw-search-suggestions[hidden]{display:none!important}\n.tw-search-option{display:flex;align-items:center;gap:10px;width:100%;margin:0;\n color:#203e60;background:#fff;border-radius:8px;text-align:left;min-height:45px;\n font-size:13px;font-weight:500;overflow-wrap:anywhere}\n.tw-search-option:hover,.tw-search-option:focus-visible{background:#eaf2ff}\n.tw-search-help{font-size:12px;color:#637791;padding:9px 11px}\n#tw-search-suggestions .tw-search-option+.tw-search-option{border-top:1px solid #f0f2f7}\n#loginPanel{max-width:470px!important;border:1px solid #dce6f3!important;\n box-shadow:0 16px 46px #12274016!important;padding:28px!important;margin:40px auto!important}\n#loginPanel h2{font-size:23px;color:#1e365b;margin:8px 0 4px}\n#loginPanel .hint{font-size:13px}\n#loginPanel label{font-size:13px;font-weight:600;margin:16px 0 6px}\n#loginPanel input{min-height:48px;font-size:16px;border-radius:10px}\n#loginPanel>button[onclick=\"login()\"]{width:100%;min-height:47px;margin:18px 0 8px;font-size:15px}\n#tw-login-header{display:flex;align-items:center;gap:12px;background:#f3f7ff;\n padding:13px;border-radius:11px;color:#2e538c}\n#tw-login-header svg{width:27px;height:27px}\n#tw-login-header>div{font-size:12px;line-height:1.45}\n#tw-login-header strong{display:block;font-size:15px;color:#203c69}\n#tw-login-show-password{width:auto;margin:5px 0 0;padding:4px 1px;\n background:transparent;color:#345b9b;font-size:12px}\n#tw-login-activation{border-top:1px solid #e2e9f3;margin:20px 0 0;padding:14px 0 0}\n#tw-login-activation>summary{cursor:pointer;font-size:13px;font-weight:650;color:#476b99}\n#tw-login-activation>h3{font-size:14px;margin:12px 0}\n#loginPanel #tw-login-activation button{width:100%;min-height:42px}\n#loginPanel>hr{display:none}\n#dashboard>.dash-header{display:none!important}\n#dashboard>h2{display:none}\n#dashboard{padding-top:0!important}\n#dashboard .tw-overview-header{padding:2px 0 8px}\n#dashboard .tw-overview-kpi{padding:13px;border-radius:11px}\n#dashboard .tw-overview-header>div>p{margin:0}\n#dashboard .tw-overview-kpi strong{font-size:25px}\n#dashboard .tw-compact-overview-card{padding:13px;margin:9px 0}\n#dashboard .tw-overview-metrics{margin:7px 0}\n#dashboard .tw-overview-action{min-height:54px;margin:4px 0}\n#tw-pcr-status.err{background:#fff4ef}\n@media(max-width:1250px){\n #study #tw-eligibility-fields .tw-eligibility-grid label{grid-template-columns:minmax(0,1fr) minmax(110px,142px)!important}\n #tw-crf-fields{grid-template-columns:minmax(0,1fr)!important}\n #study #tw-next-steps ul{display:none}\n #study #tw-next-steps>h3{padding:8px 11px;font-size:12px}\n}\n@media(max-width:750px){\n #study .tw-progress-stage>.study-card{grid-template-columns:minmax(0,1fr)!important}\n #study #tw-eligibility-fields .tw-eligibility-grid label{grid-template-columns:minmax(0,1fr) 118px!important;gap:8px;padding:9px 4px}\n #tw-crf-fields label.study-card{padding:11px!important}\n #tw-patient-banner #tw-switch-patient{margin-left:auto}\n #tw-overview-more{margin:7px 0}\n #loginPanel{margin:16px 10px!important;padding:19px!important}\n}\n";
style.textContent += "\n#tw-pcr-visit-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:9px;margin:12px 0}\n.tw-pcr-visit{display:flex;flex-direction:column;align-items:stretch;gap:5px;text-align:left;\n margin:0;border:1px solid #d9e4f4;background:#f8fbff;color:#284a78;\n min-width:0;min-height:104px;padding:12px;box-shadow:none}\n.tw-pcr-visit:hover:not(:disabled){background:#eaf3ff}\n.tw-pcr-visit strong{font-size:15px;color:#23466f}\n.tw-pcr-visit span{font-size:12px;color:#667e9d}\n.tw-pcr-visit em{text-transform:capitalize;font-style:normal;font-size:12px;font-weight:700;color:#2a69a2}\n.tw-pcr-visit[data-pcr-status=\"verified\"]{background:#eaf7ee;border-color:#b8dfc4}\n.tw-pcr-visit[data-pcr-status=\"verified\"] em{color:#207749}\n.tw-pcr-visit[data-pcr-status=\"result_entered\"]{background:#fff9e9;border-color:#eedba9}\n.tw-pcr-visit[data-pcr-status=\"result_entered\"] em{color:#947019}\n.tw-pcr-visit:disabled{cursor:default;opacity:1}\n#tw-pcr-table-details{margin:12px 0}\n#tw-pcr-table-details>summary{font-size:12px}\n#tw-pcr-table{padding:10px;overflow-x:auto}\n@media(max-width:750px){#tw-pcr-visit-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}\n";
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
const switchPatientButton=document.createElement('button');
switchPatientButton.id='tw-switch-patient';switchPatientButton.type='button';
switchPatientButton.textContent='Switch patient';switchPatientButton.className='secondary';
switchPatientButton.onclick=()=>{
 const finder=document.getElementById('tw-context-find');
 finder.focus();finder.select();
};
banner.appendChild(switchPatientButton);
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


// Compact patient progress indicator, matching the approved screen. The true
// status is read from existing persisted records; buttons never save automatically.
const progressTrack=document.createElement('nav');
progressTrack.id='tw-progress-track';progressTrack.setAttribute('aria-label','Start trial stages');
const progressLabels=['Screening','Eligibility','Enroll','Randomize'];
const progressButtons=[];
for(let i=0;i<4;i++){
 const b=document.createElement('button');b.type='button';b.id='tw-track-'+(i+1);
 b.innerHTML='<span>'+(i+1)+'</span><span>'+progressLabels[i]+'</span>';
 b.onclick=()=>{steps.forEach((step,j)=>{step.open=j===i;});};
 progressTrack.appendChild(b);progressButtons.push(b);
}
study.insertBefore(progressTrack,columns);
const trialLayout=document.createElement('div');trialLayout.id='tw-trial-layout';
study.insertBefore(trialLayout,columns);
const guidance=document.createElement('aside');guidance.id='tw-next-steps';
guidance.innerHTML='<h3>What happens next</h3><ul>'+
 '<li id="tw-next-id">Permanent NCMV Study ID generated after confirmed enrollment</li>'+
 '<li id="tw-next-pcr">Seven CMV PCR targets scheduled from transplant date</li>'+
 '<li id="tw-next-rand">One irreversible concealed allocation after final confirmation</li></ul>';
trialLayout.append(columns,guidance);
// After allocation, replace long completed entry forms with current trial actions.
const completedTrial=document.createElement('section');
completedTrial.id='tw-completed-trial';completedTrial.className='hide';
completedTrial.innerHTML='<div class="tw-completed-badge">Trial initiated</div>'+
 '<h3 id="tw-completed-title">Enrolled participant</h3>'+
 '<p class="hint">Screening and allocation remain in the permanent study history.</p>'+
 '<div class="tw-completed-actions">'+
 '<button type="button" data-tw-workflow-link="pcr">Visits & PCR</button>'+
 '<button type="button" data-tw-workflow-link="drug">Treatment & safety</button>'+
 '<button type="button" data-tw-workflow-link="course">Clinical record</button></div>';
const historicalTrial=document.createElement('details');
historicalTrial.id='tw-trial-history';historicalTrial.open=true;
historicalTrial.classList.add('tw-in-progress');
historicalTrial.innerHTML='<summary>Screening, eligibility, enrollment and randomization history</summary>';
study.insertBefore(completedTrial,progressTrack);
study.insertBefore(historicalTrial,progressTrack);
historicalTrial.append(progressTrack,trialLayout,after);
completedTrial.querySelectorAll('[data-tw-workflow-link]').forEach(b=>{
 b.onclick=()=>{void tab(b.dataset.twWorkflowLink);};
});
const activity=document.createElement('details');activity.id='tw-activity';
activity.innerHTML='<summary>Recent activity (audit history)</summary>'+
 '<div id="tw-activity-rows" aria-live="polite"><p class="hint">Select a patient.</p></div>';
study.insertBefore(activity,registerDetails);
let auditRequest=0;
async function loadActivity(){
 const id=selected,request=++auditRequest,target=document.getElementById('tw-activity-rows');
 if(!id){target.textContent='Select a patient to see recorded changes.';return;}
 try{
  const rows=await api('/api/patients/'+encodeURIComponent(id)+'/audit');
  if(selected!==id||request!==auditRequest)return;
  target.innerHTML=rows.length?rows.slice(0,12).map(row=>
   '<div class="tw-activity-line"><strong>'+escapeHTML(String(row.action||'Change').replaceAll('_',' '))+'</strong>'+
   '<span>'+escapeHTML(String(row.created_at||'').replace('T',' ').slice(0,16))+'</span>'+
   '<span>'+escapeHTML(String(row.entity_type||'Record'))+'</span></div>').join(''):
   '<p class="hint">No attributed events recorded yet.</p>';
 }catch(e){
  if(selected===id&&request===auditRequest)
   target.textContent='Activity details are unavailable for this account; the audit record remains on the server.';
 }
}
// The linked study-record picker stays available, but not as a second
// mandatory patient selection on every clinical page.
const switchRecord=document.createElement('details');switchRecord.id='tw-record-switch';
const switchLabel=document.createElement('summary');switchLabel.textContent='Change linked study record';
switchRecord.appendChild(switchLabel);
switchRecord.appendChild(document.getElementById('tw-context-subject').closest('label'));
context.insertBefore(switchRecord,document.getElementById('tw-context-error'));
// One study record is normally linked to one patient. This low-frequency
// selector belongs in the patient's optional tools, never the main form.
const recordTools=document.createElement('details');
recordTools.id='tw-patient-record-tools';
const recordToolsSummary=document.createElement('summary');
recordToolsSummary.textContent='Record tools';
recordTools.append(recordToolsSummary,switchRecord);
banner.appendChild(recordTools);
switchLabel.textContent='Advanced: change linked study record';
const avatar=document.createElement('span');avatar.className='tw-avatar';avatar.setAttribute('aria-hidden','true');
banner.insertBefore(avatar,banner.firstChild);
const pcr=document.getElementById('pcr'),emptyPcr=document.createElement('div');
const pcrGrid=document.createElement('div');
pcrGrid.id='tw-pcr-visit-grid';pcrGrid.setAttribute('aria-label','Protocol PCR visit status');
const firstPcrHeading=[...pcr.querySelectorAll('h3')].find(el=>
 el.textContent.includes('Seven protocol timepoints'));
if(firstPcrHeading)firstPcrHeading.insertAdjacentElement('afterend',pcrGrid);
const originalPcrTable=document.getElementById('tw-pcr-table');
const pcrTableDetails=document.createElement('details');
pcrTableDetails.id='tw-pcr-table-details';pcrTableDetails.className='tw-clinical-section';
const pcrDetailSummary=document.createElement('summary');
pcrDetailSummary.textContent='Show specimen codes and full result table';
originalPcrTable.parentNode.insertBefore(pcrTableDetails,originalPcrTable);
pcrTableDetails.append(pcrDetailSummary,originalPcrTable);
window.cmvRenderPcrVisits=function(records,sid){
 pcrGrid.replaceChildren();
 if(!sid||!records?.length)return;
 for(const record of records){
  const status=record.status||'planned';
  const control=status==='planned'?'tw-collect-id':
    status==='collected'?'tw-result-id':
    status==='result_entered'?'tw-verify-id':null;
  const button=document.createElement('button');button.type='button';
  button.className='tw-pcr-visit';
  button.dataset.pcrStatus=status;
  const heading=document.createElement('strong');
  heading.textContent='Month '+record.scheduled_month;
  const target=document.createElement('span');
  target.textContent='Target '+(record.target_on||'not documented');
  const statusEl=document.createElement('em');
  statusEl.textContent=status.replaceAll('_',' ');
  button.append(heading,target,statusEl);
  if(!control){button.disabled=true;button.title='Result already source-verified';}
  else button.onclick=()=>{
   if(Number(document.getElementById('tw-pcr-subject').value)!==sid)return;
   const select=document.getElementById(control);
   if(![...select.options].some(x=>x.value===String(record.id)))return;
   select.value=String(record.id);
   const details=select.closest('details.tw-clinical-section');
   if(details)details.open=true;
   select.scrollIntoView({block:'center',behavior:'smooth'});
   select.focus();
  };
  pcrGrid.append(button);
 }
};
function disclosure(card){
 const heading=card.querySelector('h3');
 if(!heading)return;
 const wrap=document.createElement('details');wrap.className='tw-clinical-section';
 const summary=document.createElement('summary');summary.textContent=heading.textContent;
 card.parentNode.insertBefore(wrap,card);
 wrap.append(summary,card);heading.classList.add('hide');
}
for(const card of [...pcr.querySelectorAll('section.study-card')])disclosure(card);
const drug=document.getElementById('drug');
for(const card of [...drug.querySelectorAll('section.study-card')])disclosure(card);
const genericPayload=document.getElementById('advancedPayload');
const payloadDetails=document.createElement('details');
payloadDetails.className='tw-clinical-section';payloadDetails.id='tw-advanced-payload';
const payloadSummary=document.createElement('summary');payloadSummary.textContent='Advanced structured data (optional)';
genericPayload.parentNode.insertBefore(payloadDetails,genericPayload);
payloadDetails.append(payloadSummary,genericPayload);
emptyPcr.id='tw-pcr-empty';emptyPcr.className='study-card hide';
emptyPcr.innerHTML='<h3>No scheduled PCR available yet</h3>'+
 '<p class="hint">Select an enrolled patient. Screening records do not have protocol PCR specimens until enrollment assigns a Study ID and the seven targets.</p>'+
 '<button id="tw-pcr-start" type="button">Open Start Trial</button>';
pcr.insertBefore(emptyPcr,pcr.children[2]||null);
document.getElementById('tw-pcr-start').onclick=()=>{void tab('study');};


/* Reports intentionally use two distinct sources: registry entries and the
   protocol eCRF review queue. No raw patient JSON is dumped on the page. */
function reportSafe(x){return escapeHTML(x===null||x===undefined?'—':String(x));}
function clinicalFieldValue(value,depth=0){
 if(value===null||value===undefined||value==='')return '<em>Not documented</em>';
 if(typeof value==='string'){
  const t=value.trim();
  if((t.startsWith('{')&&t.endsWith('}'))||(t.startsWith('[')&&t.endsWith(']'))){
   try{const parsed=JSON.parse(t);
    if(parsed&&typeof parsed==='object')return clinicalFieldValue(parsed,depth+1);
   }catch(_ignored){}
  }
  if(t.length>260)return '<details><summary>Read full source text</summary><div class="tw-long-source">'+
    reportSafe(t)+'</div></details>';
  return reportSafe(t);
 }
 if(Array.isArray(value)){
  return '<ul class="tw-field-list">'+value.map(x=>'<li>'+
   clinicalFieldValue(x,depth+1)+'</li>').join('')+'</ul>';
 }
 if(typeof value==='object'){
  if(depth>=4)return '<em>Nested source detail available in the original entry</em>';
  return '<dl class="tw-nested-fields">'+Object.entries(value).filter(([key])=>!key.startsWith('_'))
   .map(([key,v])=>'<div><dt>'+reportSafe(key.replaceAll('_',' '))+'</dt><dd>'+
    clinicalFieldValue(v,depth+1)+'</dd></div>').join('')+'</dl>';
 }
 return reportSafe(value);
}
function fieldSummary(payload){
 const entries=Object.entries(payload||{}).filter(([key])=>!key.startsWith('_'));
 if(!entries.length)return '<p class="hint">No submitted source fields.</p>';
 return '<dl class="tw-review-fields">'+entries.map(([key,val])=>
  '<div><dt>'+reportSafe(key.replaceAll('_',' '))+'</dt><dd>'+
  clinicalFieldValue(val)+'</dd></div>').join('')+'</dl>';
}
function reviewGroup(rows,title,registry){
 const all=rows||[],pending=all.filter(x=>x.review_status==='pending'||x.review_status==='needs_correction'),
  earlier=all.filter(x=>x.review_status!=='pending'&&x.review_status!=='needs_correction');
 const item=row=>{
  const label=registry?(row.study_id||row.cr_number||'Registry record'):(row.section+' · participant '+row.subject_id);
  const openTitle=registry?row.kind:row.occurrence_key;
  const reasonId='reason-'+row.entry_id;
  const action=registry&&row.review_status==='pending'?
   '<label>Review reason<input id="'+reportSafe(reasonId)+'" maxlength="500" placeholder="Source checked / correction required"></label>'+
   '<button onclick="submitReview(\''+reportSafe(row.entry_id)+'\','+Number(row.revision)+',\'verified\')">Verify</button> '+
   '<button class="secondary" onclick="submitReview(\''+reportSafe(row.entry_id)+'\','+Number(row.revision)+',\'needs_correction\')">Request correction</button>':
   (!registry?'<button class="secondary" data-review-crf="'+Number(row.subject_id)+'">Open patient eCRF</button>':'');
  return '<details class="tw-review-item"><summary><span><strong>'+reportSafe(label)+
   '</strong> · '+reportSafe(openTitle)+' · '+reportSafe(row.occurred_on)+'</span>'+
   '<span class="tw-review-status">'+reportSafe(row.review_status)+'</span></summary>'+
   '<div><p class="hint">Revision '+Number(row.revision)+' · source fields</p>'+fieldSummary(row.payload)+action+'</div></details>';
 };
 return '<section class="tw-review-group"><h3>'+title+
  ' <small>('+pending.length+' need attention · '+earlier.length+' reviewed)</small></h3>'+
  (pending.length?pending.map(item).join(''):'<p class="hint">No source reviews outstanding in this category.</p>')+
  (earlier.length?'<details class="tw-reviewed-history"><summary>Verified / earlier entries ('+earlier.length+')</summary>'+
   earlier.map(item).join('')+'</details>':'')+'</section>';
}
async function loadReview(){
 const display=document.getElementById('reviewResults');
 const metrics=document.getElementById('tw-report-metrics');
 const visits=document.getElementById('tw-report-visits');
 display.textContent='Loading source reviews…';
 const urls=['/api/trial/overview','/api/trial/crf/completeness',
             '/api/review-queue','/api/trial/crf/review-queue'];
 const results=await Promise.allSettled(urls.map(url=>api(url)));
 const good=i=>results[i].status==='fulfilled'?results[i].value:null;
 const trial=good(0),completion=good(1),registry=good(2),crfs=good(3);
 const row=(title,value,desc)=>'<div class="tw-metric"><strong>'+reportSafe(value)+
  '</strong><span>'+title+'</span><div class="hint">'+desc+'</div></div>';
 metrics.innerHTML=trial?[
  row('Screened',trial.screened??0,'Screening records'),
  row('Enrolled',trial.ever_enrolled??trial.enrolled??0,'Approved enrollments'),
  row('Randomized',trial.randomized??0,'Of 344 target'),
  row('PCR verified',trial.verified_protocol_pcr_slots??0,'Protocol specimen results')
 ].join(''):'<p class="hint">Trial metrics are unavailable for this account.</p>';
 visits.innerHTML=completion?
  '<div style="overflow-x:auto"><table><thead><tr><th>Follow-up</th><th>Submitted</th>'+
  '<th>Verified</th><th>Correction needed</th></tr></thead><tbody>'+
  [1,2,3,4,6,9,12].map(month=>{
   const slot=completion.visit_completion?.[String(month)]||{};
   return '<tr><td>Month '+month+'</td><td>'+Number(slot.submitted||0)+
    '</td><td>'+Number(slot.verified||0)+'</td><td>'+Number(slot.needs_correction||0)+'</td></tr>';
  }).join('')+'</tbody></table></div>':
  '<p class="hint">Follow-up completeness is unavailable for this account.</p>';
 display.innerHTML=(registry?reviewGroup(registry,'Registry source verification',true):
  '<p class="hint">Registry review records are unavailable for this account.</p>')+
  (crfs?reviewGroup(crfs,'Study eCRF verification',false):
   '<p class="hint">eCRF review records are unavailable for this account.</p>');
}
window.loadReview=loadReview;
root.addEventListener('click',event=>{if(event.target.closest('#tw-report-reload'))void loadReview();});
document.getElementById('reviewResults').addEventListener('click',e=>{
 const b=e.target.closest('button[data-review-crf]');if(!b)return;
 void (async()=>{
  try{
   const sid=Number(b.dataset.reviewCrf);
   const record=await api('/api/trial/crf/subjects/'+sid+'/context');
   if(!record.patient_id)throw Error('Participant could not be resolved');
   await window.choose(record.patient_id);await tab('crf');
  }catch(err){document.getElementById('reviewResults').insertAdjacentHTML('afterbegin',
   '<p class="status err">Could not open selected patient eCRF: '+reportSafe(err.message)+'</p>');}
 })();
});

const previousTab=tab;
tab=async function(name){
 // Do not switch clinical modules while the selected participant's validated
 // server context is still loading. This prevents stale patient PCR/pharmacy UI.
 if(window.cmvPatientContextSwitch)await window.cmvPatientContextSwitch;
 await previousTab(name);syncNavigation();
 if(activeTab==='study'){await updateWorkflow();void loadActivity();}
};
const previousChoose=window.choose;
window.choose=async function(id){
 await previousChoose(id);
 if(selected===id){await updatePatientBanner();if(activeTab==='study'){await updateWorkflow();void loadActivity();}}
};

let bannerRequest=0,workflowRequest=0,lastPatient=null,lastKey=null,lastHistoricalState=null;
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
  document.getElementById('tw-banner-status').textContent=
   clinical.allocation?.randomized?'Randomized':
   (s?s.status.replaceAll('_',' '):'Registered');
  document.getElementById('tw-patient-meta').textContent='Transplant: '+(p.transplant_date||'not recorded')+
   (s?.donor_type?' · Donor: '+s.donor_type:'');
 }catch(e){if(request===bannerRequest)document.getElementById('tw-banner-status').textContent='Context unavailable';}
}
async function updateWorkflow(){
 const id=selected,request=++workflowRequest;
 if(!id){
  completedTrial.classList.add('hide');historicalTrial.open=true;
  historicalTrial.classList.add('tw-in-progress');
  lastHistoricalState=null;subButtons.study.textContent='Start trial';
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
   {complete:!!s&&!!s.consent_recorded&&s.status!=='consent_declined',
    blocked:s?.status==='consent_declined',
    label:s?.status==='consent_declined'?'Consent declined':s?.consent_recorded?'Consent recorded':s?'Consent pending':'Not started'},
   {complete:eligible,blocked:checked&&!eligible,label:eligible?'Confirmed':checked?'Not eligible':'Pending'},
   {complete:!!s?.enrolled_on,blocked:s?.status==='consent_declined',label:s?.enrolled_on?'Enrolled':'Pending'},
   {complete:randomized,blocked:s?.status==='consent_declined',label:randomized?'Randomized':'Pending'}
  ];
  for(let i=0;i<steps.length;i++){
   const stage=status[i];
   steps[i].dataset.stepStatus=stage.complete?'complete':stage.blocked?'blocked':'pending';
   document.getElementById('tw-result-'+(i+1)).textContent=stage.label;
  }
  progressButtons.forEach((b,i)=>{
   b.classList.toggle('done',status[i].complete);
   b.classList.toggle('current',!status[i].complete&&!status[i].blocked &&
     status.slice(0,i).every(x=>x.complete));
   b.querySelector('span:first-child').textContent=status[i].complete?'✓':String(i+1);
  });
  document.getElementById('tw-next-id').classList.toggle('done',!!s?.study_code);
  document.getElementById('tw-next-pcr').classList.toggle('done',!!s?.enrolled_on);
  document.getElementById('tw-next-rand').classList.toggle('done',randomized);
  const complete=Boolean(s?.enrolled_on&&randomized);
  completedTrial.classList.toggle('hide',!complete);
  historicalTrial.classList.toggle('tw-in-progress',!complete);
  const historyKey=String(id)+':'+complete;
  if(lastHistoricalState!==historyKey){
   historicalTrial.open=!complete;
   lastHistoricalState=historyKey;
  }
  subButtons.study.textContent=complete?'Trial summary':'Start trial';
  if(complete){
   document.getElementById('tw-completed-title').textContent=
    (s.study_code||'Study participant')+' · Randomized';
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
 directory.classList.toggle('hide',name!=='registry');
 legacyGrid.classList.add('hide');
 const enrolledPatient=Boolean(document.getElementById('tw-pcr-subject').value);
 pcr.classList.toggle('tw-not-enrolled',name==='pcr'&&!enrolledPatient);
 emptyPcr.classList.toggle('hide',name!=='pcr'||enrolledPatient);
 const searchHeader=document.getElementById('tw-header-search');
 if(searchHeader)searchHeader.classList.toggle('hide',root.classList.contains('hide')||!csrf);
 const toolsHome=document.getElementById('tw-account-links');
 if(toolsHome)for(const id of ['chatgptConnectionLink','operationsLink']){
  const link=document.getElementById(id);if(link&&link.parentNode!==toolsHome)toolsHome.appendChild(link);
 }
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
// The existing select remains the authoritative exact-match control for
// accessibility and regression tests; visible search results are simple
// tap targets rather than a second full-width native dropdown.
resultLabel.classList.add('tw-search-native');
const suggestions=document.createElement('div');
suggestions.id='tw-search-suggestions';suggestions.hidden=true;
suggestions.setAttribute('role','listbox');
suggestions.setAttribute('aria-label','Patient search results');
searchHeader.appendChild(suggestions);
let visibleSuggestionRequest=0;
function drawSuggestions(){
 const q=searchInput.value.trim();
 suggestions.replaceChildren();
 if(q.length<3){suggestions.hidden=true;return;}
 const opts=[...searchResult.options].filter(x=>x.value);
 if(!opts.length){
  const p=document.createElement('p');p.className='tw-search-help';
  p.textContent=searchResult.options[0]?.textContent||'Searching…';
  suggestions.append(p);
 }else{
  opts.slice(0,12).forEach(opt=>{
   const button=document.createElement('button');button.type='button';
   button.className='tw-search-option';
   button.setAttribute('role','option');
   button.textContent=opt.textContent;
   button.onclick=()=>{
    const chosen=opt.value;
    if(![...searchResult.options].some(x=>x.value===chosen))return;
    searchResult.value=chosen;
    suggestions.hidden=true;
    searchHeader.classList.remove('tw-searching');
    searchResult.dispatchEvent(new Event('change',{bubbles:true}));
    searchInput.value='';
   };
   suggestions.append(button);
  });
 }
 suggestions.hidden=false;
}
new MutationObserver(drawSuggestions).observe(searchResult,{childList:true,subtree:true});
searchInput.addEventListener('input',()=>{visibleSuggestionRequest++;drawSuggestions();});
searchInput.addEventListener('keydown',event=>{
 if(event.key==='Escape'){suggestions.hidden=true;searchHeader.classList.remove('tw-searching');}
 if(event.key==='Enter'){
  const first=suggestions.querySelector('.tw-search-option');
  if(first){event.preventDefault();first.click();}
 }
});
searchInput.addEventListener('blur',()=>{setTimeout(()=>{
 if(!searchHeader.contains(document.activeElement)){suggestions.hidden=true;}
},150);});
const loginPanel=document.getElementById('loginPanel');
loginPanel.querySelector('h2').textContent='Study staff sign in';
const intro=document.createElement('div');intro.id='tw-login-header';
intro.innerHTML='<span aria-hidden="true" style="font-size:24px;font-weight:800">+</span>'+
 '<div><strong>NIMS CMV Trial · eCRF</strong><span>Secure clinical data workspace</span></div>';
loginPanel.insertBefore(intro,loginPanel.firstChild);
const pass=document.getElementById('loginPass');
const showPassword=document.createElement('button');showPassword.type='button';
showPassword.id='tw-login-show-password';
showPassword.textContent='Show password';
showPassword.onclick=()=>{const shown=pass.type==='text';
 pass.type=shown?'password':'text';showPassword.textContent=shown?'Show password':'Hide password';};
pass.closest('label').insertAdjacentElement('afterend',showPassword);
for(const id of ['loginName','loginPass','loginOtp']){
 document.getElementById(id).addEventListener('keydown',e=>{
  if(e.key==='Enter'){
   e.preventDefault();loginPanel.querySelector('button[onclick="login()"]').click();
  }
 });
}
const activationHeading=[...loginPanel.children].find(el=>
 el.tagName==='H3'&&el.textContent.includes('Activate individual staff account'));
if(activationHeading){
 const activation=document.createElement('details');activation.id='tw-login-activation';
 const title=document.createElement('summary');title.textContent='First time? Activate your staff account';
 activation.append(title);
 let node=activationHeading.previousElementSibling;
 while(node){
  const next=node.nextElementSibling;
  activation.append(node);
  node=next;
 }
 loginPanel.append(activation);
}

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