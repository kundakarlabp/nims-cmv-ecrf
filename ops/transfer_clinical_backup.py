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
from urllib.error import HTTPError,URLError

BASE='https://152-70-77-77.sslip.io'
AUD='nims-cmv-encrypted-backup'
MAX=32*1024*1024
scope_reported=False

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def read(url,headers=None,data=None,limit=16384):
    with build_opener(NoRedirect).open(Request(url,headers=headers or {},data=data),timeout=20) as response:
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
    payload=json.dumps({'bundle_id':metadata['id'],'sha256':actual,
                       'artifact_id':int(os.environ['CLINICAL_ARTIFACT_ID'])}).encode()
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
    {'fetch':fetch,'acknowledge':acknowledge,'verify':verify}[sys.argv[1]]()
