'use strict';
const byId=id=>document.getElementById(id);
const params=Object.fromEntries(new URLSearchParams(location.search));
let csrf='';
async function api(path,options={}){
  const r=await fetch(path,{credentials:'same-origin',...options});
  const data=await r.json();if(!r.ok)throw new Error(typeof data.detail==='string'?data.detail:'Request failed');return data;
}
async function session(){
  try{const me=await api('/api/session');csrf=me.csrf_token;
    byId('login').hidden=true;
    if(location.pathname==='/oauth/connections'){
      byId('connections').hidden=false;await connections();return;
    }
    byId('identity').textContent='Signed in as '+me.display_name;
    byId('consent').hidden=false;
    byId('write-option').hidden=!(params.scope||'').split(' ').includes('cmv:write');
  }catch(e){byId('login').hidden=false;byId('consent').hidden=true;}
}
byId('login').addEventListener('submit',async e=>{e.preventDefault();
  const f=e.target;const password=f.elements.password.value;
  try{const result=await api('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({username:f.elements.username.value,password,otp:f.elements.otp.value||null})});
    f.elements.password.value='';if(result.mfa_setup_required)throw new Error('Complete authenticator setup in the dashboard first.');
    byId('message').textContent='';await session();
  }catch(err){f.elements.password.value='';byId('message').textContent=err.message;}
});
byId('approve').addEventListener('click',async()=>{
  byId('approve').disabled=true;
  try{const scope=byId('write').checked?params.scope:'cmv:read';
    const out=await api('/oauth/authorize',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},
      body:JSON.stringify({...params,scope})});location.assign(out.redirect_url);
  }catch(e){byId('message').textContent=e.message;byId('approve').disabled=false;}
});
async function connections(){
  const list=byId('connection-list');list.replaceChildren();
  for(const c of await api('/api/oauth/connections')){
    const row=document.createElement('p');row.textContent=c.client+' · '+c.scope+(c.revoked?' · Revoked':'');
    if(!c.revoked){const b=document.createElement('button');b.textContent='Revoke connection';
      b.addEventListener('click',async()=>{try{await api('/api/oauth/connections/'+encodeURIComponent(c.id),
        {method:'DELETE',headers:{'X-CSRF-Token':csrf}});await connections();}catch(e){byId('message').textContent=e.message;}});row.append(b);}
    list.append(row);
  }
}
session();
