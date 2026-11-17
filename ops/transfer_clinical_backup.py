"""GitHub-hosted ciphertext transfer. No clinical login or decryption key."""
import hashlib
import base64
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import sys
import time
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.parse import urlparse,quote
from urllib.error import HTTPError,URLError

BASE='https://152-70-77-77.sslip.io'
AUD='nims-cmv-encrypted-backup'
MAX=32*1024*1024
scope_reported=False

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def read(url,headers=None,data=None,limit=16384,method=None):
    with build_opener(NoRedirect).open(Request(url,headers=headers or {},data=data,method=method),timeout=20) as response:
        result=response.read(limit+1)
        if len(result)>limit:raise ValueError('Response exceeds permitted size')
        return result

def identity():
    global scope_reported
    url=os.environ['ACTIONS_ID_TOKEN_REQUEST_URL']+'&audience='+AUD
    raw=read(url,{'Authorization':'Bearer '+os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN']})
    token=json.loads(raw)['value']
    print('::add-mask::'+token)
    if not scope_reported:
        # Diagnostic scope only, not a trust decision. Never print the token,
        # signature or any credential. The server still verifies signed JWTs.
        payload=token.split('.')[1]
        claims=json.loads(base64.urlsafe_b64decode(payload+'='*((-len(payload))%4)))
        allowed=('iss','aud','sub','event_name','repository_id','repository_owner_id',
                 'repository_visibility','workflow_ref','ref','iat','nbf','exp')
        print('Workflow identity scope: '+json.dumps({k:claims.get(k) for k in allowed},sort_keys=True))
        scope_reported=True
    return {'Authorization':'Bearer '+token,'Accept':'application/json'}

REPO='kundakarlabp/nims-cmv-ecrf'
API='https://api.github.com/repos/'+REPO

def github_headers():
    return {'Authorization':'Bearer '+os.environ['GITHUB_TOKEN'],
        'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2026-03-10',
        'User-Agent':'NIMS-CMV-encrypted-recovery','Cache-Control':'no-cache'}

def github_json(path,data=None):
    headers=github_headers()
    body=None if data is None else json.dumps(data).encode()
    if body is not None:headers['Content-Type']='application/json'
    try:return json.loads(read(API+path,headers,body,limit=1024*1024))
    except HTTPError as error:raise SystemExit('Private recovery storage API returned HTTP '+str(error.code))

def download_release_asset(asset_id):
    headers={**github_headers(),'Accept':'application/octet-stream'}
    try:return read(API+'/releases/assets/'+str(asset_id),headers,limit=MAX)
    except HTTPError as error:
        if error.code not in (302,303,307,308):
            raise SystemExit('Private encrypted readback returned HTTP '+str(error.code))
        destination=error.headers.get('Location','')
        url=urlparse(destination)
        if url.scheme!='https' or url.hostname not in {'release-assets.githubusercontent.com','objects.githubusercontent.com'} or url.username or url.password:
            raise SystemExit('Recovery download redirect rejected')
        # No Authorization header or cookie is forwarded to the asset CDN.
        try:return read(destination,{'Accept':'application/octet-stream'},limit=MAX)
        except (HTTPError,URLError,TimeoutError):
            raise SystemExit('Encrypted recovery CDN readback unavailable; signed URL not disclosed')

def store_release():
    root=Path('/tmp/nims-encrypted')
    metadata=json.loads((root/'metadata.json').read_text())
    raw=(root/'bundle.tar').read_bytes()
    if len(raw)>MAX or hashlib.sha256(raw).hexdigest()!=metadata['sha256']:
        raise SystemExit('Local ciphertext verification failed')
    repository=github_json('')
    if repository.get('id')!=1455709378 or repository.get('private') is not True:
        raise SystemExit('Private recovery repository identity check failed')
    # Monthly containers stay below GitHub's 1000-assets-per-release limit.
    # Draft releases do not publish notifications or source-code releases.
    month=datetime.fromisoformat(metadata['created_at']).strftime('%Y-%m')
    tag='cmv-encrypted-recovery-'+month
    releases=github_json('/releases?per_page=100')
    matching=[r for r in releases if r.get('tag_name')==tag]
    if len(matching)>1:raise SystemExit('Ambiguous private recovery release')
    release=matching[0] if matching else github_json('/releases',{
        'tag_name':tag,'target_commitish':'main','name':'Private encrypted CMV recovery '+month,
        'body':'Encrypted operational recovery archives only. Database and allocation keys are never included in plaintext.',
        'draft':True,'prerelease':True})
    release_id=release['id']
    if release.get('draft') is not True or not isinstance(release_id,int):
        raise SystemExit('Recovery release must remain a private draft')
    name='clinical-'+metadata['id']+'.tar'
    asset=None
    for page in range(1,11):
        assets=github_json('/releases/'+str(release_id)+'/assets?per_page=100&page='+str(page))
        asset=next((a for a in assets if a.get('name')==name),None)
        if asset or len(assets)<100:break
    if asset is None:
        headers={**github_headers(),'Content-Type':'application/x-tar'}
        url='https://uploads.github.com/repos/'+REPO+'/releases/'+str(release_id)+'/assets?name='+quote(name,safe='')
        try:asset=json.loads(read(url,headers,raw,limit=65536))
        except HTTPError as error:raise SystemExit('Encrypted recovery upload returned HTTP '+str(error.code))
    if asset.get('state')!='uploaded' or asset.get('size')!=len(raw):
        raise SystemExit('Recovery asset size/state mismatch')
    recovered=download_release_asset(asset['id'])
    if hashlib.sha256(recovered).hexdigest()!=metadata['sha256']:
        raise SystemExit('Offsite encrypted readback hash mismatch; no receipt issued')
    readback=Path('/tmp/nims-readback');readback.mkdir(mode=0o700,exist_ok=True)
    (readback/'bundle.tar').write_bytes(recovered)
    (root/'remote.json').write_text(json.dumps({'release_id':release_id,'asset_id':asset['id']}))
    print('Private encrypted release asset uploaded and independently read back; SHA-256 verified.')
    print('Recovery release ID: '+str(release_id)+'; asset ID: '+str(asset['id']))

def fetch():
    deadline=time.monotonic()+900
    while True:
        try:
            metadata=json.loads(read(BASE+'/api/backup-channel/latest',identity()))
            if metadata['restore_verified'] is not True:raise ValueError('Restore has not passed')
            raw=read(BASE+'/api/backup-channel/bundles/'+metadata['id'],identity(),limit=MAX)
            if hashlib.sha256(raw).hexdigest()!=metadata['sha256']:raise ValueError('Ciphertext mismatch')
            root=Path('/tmp/nims-encrypted');root.mkdir(mode=0o700,exist_ok=True)
            (root/'bundle.tar').write_bytes(raw)
            (root/'metadata.json').write_text(json.dumps(metadata))
            print('Retrieved encrypted archive; isolated database restore was verified on the host.')
            return
        except HTTPError as error:
            if error.code in (401,403):
                print('Server HTTP date: '+str(error.headers.get('Date','unavailable')))
                print('Runner UTC: '+datetime.now(timezone.utc).isoformat())
                raise SystemExit('Backup workflow identity rejected with HTTP '+str(error.code)+'. No error body or credential disclosed.')
            if time.monotonic()>=deadline:raise SystemExit('Encrypted backup preparation timed out; HTTP '+str(error.code))
            time.sleep(15)
        except (URLError,TimeoutError):
            if time.monotonic()>=deadline:
                try:
                    public=json.loads(read(BASE+'/readyz'))
                    print('Public transition: '+str(public.get('clinical_transition'))+'; step: '+str(public.get('clinical_failed_step')))
                except (HTTPError,URLError,TimeoutError):pass
                raise SystemExit('Encrypted backup preparation timed out; inspect host status')
            time.sleep(15)

def acknowledge():
    metadata=json.loads(Path('/tmp/nims-encrypted/metadata.json').read_text())
    actual=hashlib.sha256(Path('/tmp/nims-readback/bundle.tar').read_bytes()).hexdigest()
    if actual!=metadata['sha256']:raise SystemExit('Offsite readback hash mismatch')
    headers={**identity(),'Content-Type':'application/json'}
    remote=Path('/tmp/nims-encrypted/remote.json')
    storage=json.loads(remote.read_text()) if remote.exists() else {'artifact_id':int(os.environ['CLINICAL_ARTIFACT_ID'])}
    payload=json.dumps({'bundle_id':metadata['id'],'sha256':actual,**storage}).encode()
    result=json.loads(read(BASE+'/api/backup-channel/acknowledge',headers,payload))
    if result.get('acknowledged') is not True:raise SystemExit('Offsite acknowledgment failed')
    print('Offsite encrypted archive read back and SHA-256 verified; host receipt submitted.')

def verify():
    deadline=time.monotonic()+600
    while True:
        try:
            status=json.loads(read(BASE+'/readyz'))
            if status.get('service')=='clinical' and status.get('clinical_entry_available') is True:
                print('VERIFIED: clinical database reachable; clinical data entry active; mandatory MFA enforced.')
                return
        except (HTTPError,URLError,TimeoutError):pass
        if time.monotonic()>=deadline:raise SystemExit('Clinical activation not confirmed; inspect host maintenance status')
        time.sleep(15)

if __name__=='__main__':
    {'fetch':fetch,'store':store_release,'acknowledge':acknowledge,'verify':verify}[sys.argv[1]]()
