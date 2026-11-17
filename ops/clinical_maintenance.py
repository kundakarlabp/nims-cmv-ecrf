#!/usr/bin/env python3
"""Fixed host maintenance: provision, encrypted recovery, authorized cutover.

Runs as the existing deployment owner. It never evaluates commands received
from the web. Clinical records and credentials stay on the VM. Existing staging
volumes are retained; no clinical volume is overwritten or restored in place.
"""
import base64
from datetime import datetime,timezone,timedelta
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
PRIVATE=Path.home()/'.local/share/nims-cmv-clinical'
STATE=ROOT/'.deploy-state'
UTC=timezone.utc
REPO_ID='1455709378'
PHASE='preparation'

def run(args,*,data=None,check=True):
    # Never inherit stderr containing SQL literals/passwords into CI/public logs.
    result=subprocess.run(list(map(str,args)),input=data,stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE,timeout=420)
    if check and result.returncode:
        if os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('CLINICAL_RECOVERY_CI')=='true':
            # This guarded path contains disposable CI databases/keys only.
            sys.stderr.write(result.stderr.decode(errors='replace')[-6000:])
        raise RuntimeError('Host maintenance command failed: '+Path(str(args[0])).name)
    return result.stdout

def atomic(path,data,mode=0o600):
    path=Path(path);tmp=path.with_name(path.name+'.tmp-'+secrets.token_hex(6))
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,mode)
    os.fchmod(fd,mode)
    with os.fdopen(fd,'wb') as out:out.write(data)
    os.replace(tmp,path)

def parse_env(path):
    return dict(line.split('=',1) for line in Path(path).read_text().splitlines()
                if line and not line.startswith('#') and '=' in line)

def write_env(values):
    if any('\n' in v or '\r' in v for v in values.values()):raise RuntimeError('Unsafe private configuration')
    atomic(PRIVATE/'clinical.env',''.join(k+'='+v+'\n' for k,v in values.items()).encode())

def docker():
    if subprocess.run(['docker','info'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:
        return ['docker']
    run(['sudo','-n','docker','info']);return ['sudo','-n','docker']

def clinical(dc):return dc+['compose','--env-file',str(PRIVATE/'clinical.env'),'-f',str(ROOT/'compose.clinical.yaml')]
def staging(dc):return dc+['compose','--env-file',str(ROOT/'.env'),'-f',str(ROOT/'compose.yaml')]

def sql(dc,query,database='nims_cmv_clinical',stage=False):
    compose=staging(dc) if stage else clinical(dc)
    user='nims_ecrf' if stage else 'nims_clinical_owner'
    return run(compose+['exec','-T','db','psql','-X','-v','ON_ERROR_STOP=1','-At','-U',user,'-d',database],data=query.encode())

def setup_paths():
    from ops.prepare_clinical import prepare,create_once
    prepare(PRIVATE)
    export=PRIVATE/'export';export.mkdir(exist_ok=True);export.chmod(0o755)
    ack=PRIVATE/'ack';ack.mkdir(exist_ok=True)
    if ack.is_symlink():raise RuntimeError('Ack directory cannot be a symlink')
    # Only this narrow acknowledgement spool is writable by API UID10001.
    run(['sudo','-n','chown',f'10001:{os.getgid()}',ack]);run(['sudo','-n','chmod','2770',ack])
    create_once(PRIVATE/'backup.key',base64.urlsafe_b64encode(secrets.token_bytes(32))+b'\n')
    values=parse_env(PRIVATE/'clinical.env')
    authorization=(ROOT/'ops/clinical-authorization.json').read_bytes()
    approved=json.loads(authorization)
    atomic(PRIVATE/'authorization.json',authorization,0o644)
    values.update(CLINICAL_SITE_DOMAIN=approved['site_domain'],
        CLINICAL_OWNER_AUTHORIZATION_PATH=str(PRIVATE/'authorization.json'),
        CLINICAL_SIGNOFF_PATH=str(PRIVATE/'authorization.json'),
        CLINICAL_GOLIVE_SHA256=hashlib.sha256(authorization).hexdigest(),
        CLINICAL_BACKUP_EXPORT_DIR=str(export),CLINICAL_BACKUP_ACK_DIR=str(ack))
    write_env(values)
    return values

def provision(dc):
    cc=clinical(dc)
    run(cc+['up','-d','--wait','--wait-timeout','120','db'])
    installed=sql(dc,"SELECT to_regclass('public.clinical_schema_baseline') IS NOT NULL;").strip()==b't'
    if not installed:
        count=sql(dc,"SELECT count(*) FROM information_schema.tables WHERE table_schema='public';").strip()
        if count!=b'0':raise RuntimeError('Existing unrecognized clinical database; no overwrite attempted')
        run(cc+['run','--rm','--no-deps','schema-bootstrap'])
    users=sql(dc,'SELECT count(*) FROM users;').strip()
    if users==b'0':
        freeze_source_accounts(dc)
        # JSON data travels directly inside this host process, never a command
        # argument, report, artifact, plaintext file, or external API.
        tables=['users','trial_user_totp','trial_staff_access','trial_user_invitations']
        available=set(sql(dc,"SELECT tablename FROM pg_tables WHERE schemaname='public';",'nims_ecrf',True).decode().split())
        snapshot={name:json.loads(sql(dc,f"SELECT coalesce(json_agg(t),'[]') FROM {name} t;",'nims_ecrf',True))
                  for name in tables if name in available}
        rows=[u for u in snapshot['users'] if not u['username'].lower().startswith('test')
              and not u['display_name'].lower().startswith('synthetic')]
        owners=[u for u in rows if u['active'] and u['role'] in {'admin','pi'}
                and all(word in u['display_name'].lower() for word in ['bhanu','prasad'])]
        if len(owners)!=1:raise RuntimeError('Could not uniquely identify the authorized investigator account')
        owner=owners[0]['id'];ids={u['id'] for u in rows}
        # Exact existing hashes and MFA records survive. Active sessions do not.
        for user in rows:user['pi_authorized']=user['id']==owner
        snapshot['users']=rows
        for name in list(snapshot):
            if name!='users':snapshot[name]=[r for r in snapshot[name] if r.get('user_id') in ids]
        payload=json.dumps(snapshot).encode()
        run(cc+['run','--rm','--no-deps','-T','admin-bootstrap',
                'python','/srv/import_clinical_accounts.py'],data=payload)
    if not (PRIVATE/'provisioned').exists() and not (STATE/'clinical-active').exists():
        # Sequence reset is owner-only and only before initial activation.
        # The restricted application role deliberately cannot call setval.
        sql(dc,"SELECT setval(pg_get_serial_sequence('trial_user_invitations','id'), coalesce(max(id),1), count(*)>0) FROM trial_user_invitations;")
    atomic(PRIVATE/'provisioned',b'clinical schema and named accounts ready\n')

def freeze_source_accounts(dc):
    # Freeze both HTTP and database mutation paths before taking the account
    # snapshot. Trigger DDL waits for in-flight writers to finish, then rejects
    # later writes (including requests that passed the HTTP guard earlier).
    public=ROOT/'ops/public-status';public.mkdir(exist_ok=True)
    atomic(public/'account-migration.lock',b'Clinical account migration in progress\n',0o644)
    statement="""
    BEGIN;
    CREATE OR REPLACE FUNCTION public.freeze_cmv_account_migration()
    RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'Clinical account migration in progress' USING ERRCODE='55000'; END $$;
    """
    for table in ('users','trial_user_totp','trial_staff_access','trial_user_invitations'):
        statement+=f'CREATE OR REPLACE TRIGGER clinical_account_migration_freeze BEFORE INSERT OR UPDATE OR DELETE ON public.{table} FOR EACH ROW EXECUTE FUNCTION public.freeze_cmv_account_migration();\n'
    sql(dc,statement+'COMMIT;','nims_ecrf',True)

def ensure_crypto():
    try:
        from cryptography.fernet import Fernet
        if shutil.which('age') and shutil.which('curl'):return Fernet
    except ImportError:pass
    run(['sudo','-n','apt-get','update','-qq'])
    run(['sudo','-n','apt-get','install','-y','-qq','age','curl','python3-cryptography'])
    from cryptography.fernet import Fernet
    return Fernet

def backup_and_restore(dc,force=False):
    Fernet=ensure_crypto()
    latest=sorted((PRIVATE/'export').glob('*.json'))
    if latest and not force:
        created=datetime.fromisoformat(json.loads(latest[-1].read_text())['created_at'])
        if datetime.now(UTC)-created<timedelta(hours=2):return
    cc=clinical(dc)
    raw=run(cc+['exec','-T','db','pg_dump','-U','nims_clinical_owner','-d',
                'nims_cmv_clinical','-Fc','--no-owner','--no-acl'])
    if not raw.startswith(b'PGDMP'):raise RuntimeError('Clinical dump format verification failed')
    key=(PRIVATE/'backup.key').read_bytes().strip();sealed=Fernet(key).encrypt(raw)
    # Test decryption of the exact encrypted archive before isolated pg_restore.
    restored=Fernet(key).decrypt(sealed)
    if hashlib.sha256(restored).digest()!=hashlib.sha256(raw).digest():raise RuntimeError('Encrypted archive mismatch')
    target='nims_restore_'+secrets.token_hex(8)
    created=False
    try:
        sql(dc,'CREATE DATABASE '+target+';');created=True
        run(cc+['exec','-T','db','pg_restore','--exit-on-error','--no-owner','--no-acl',
                '-U','nims_clinical_owner','-d',target],data=restored)
        check=sql(dc,"SELECT fingerprint FROM clinical_schema_baseline WHERE revision='initial-2026-11';",target).strip()
        expected=sql(dc,"SELECT fingerprint FROM clinical_schema_baseline WHERE revision='initial-2026-11';").strip()
        if not check or check!=expected:raise RuntimeError('Restored schema fingerprint mismatch')
        sql(dc,'SELECT count(*) FROM audit_events; SELECT count(*) FROM patients;',target)
    finally:
        if created:sql(dc,'DROP DATABASE '+target+';')
    # Key escrow includes BOTH recovery key and sealed-allocation key. Only
    # owner-held existing SSH private keys can open this age ciphertext.
    recipient_file=Path.home()/'.ssh/authorized_keys'
    if not recipient_file.is_file():raise RuntimeError('Owner SSH public recipients unavailable')
    recipients=[]
    for line in recipient_file.read_text().splitlines():
        fields=line.split()
        if len(fields)>1 and fields[0] in {'ssh-rsa','ssh-ed25519'}:recipients.append(' '.join(fields[:2]))
    if not recipients:raise RuntimeError('No supported owner SSH public recovery key')
    escrow=json.dumps({'backup_fernet_key':key.decode(),
        'allocation_fernet_key':(PRIVATE/'allocation.key').read_text().strip()}).encode()
    with tempfile.TemporaryDirectory(prefix='nims-escrow-',dir=PRIVATE) as td:
        pub=Path(td)/'recipients';pub.write_text('\n'.join(recipients)+'\n')
        escrow_sealed=run(['age','-R',pub],data=escrow)
    stamp=datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')
    bundle_id=stamp+'-'+secrets.token_hex(6)
    inner={'created_at':datetime.now(UTC).isoformat(),'database':'nims_cmv_clinical',
           'schema_fingerprint':expected.decode(),'encrypted_dump_sha256':hashlib.sha256(sealed).hexdigest(),
           'restore_verified':True,'key_recovery':'age: existing owner SSH private key required'}
    buf=io.BytesIO()
    with tarfile.open(fileobj=buf,mode='w') as archive:
        for name,data in [('database.dump.fernet',sealed),('recovery-keys.age',escrow_sealed),
                          ('manifest.json',json.dumps(inner).encode())]:
            info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o600;archive.addfile(info,io.BytesIO(data))
    bundle=buf.getvalue()
    if len(bundle)>32*1024*1024:raise RuntimeError('Encrypted backup exceeds configured transfer limit; capacity review required')
    digest=hashlib.sha256(bundle).hexdigest()
    export=PRIVATE/'export'
    atomic(export/(bundle_id+'.tar'),bundle,0o644)
    manifest={'id':bundle_id,'sha256':digest,'size':len(bundle),
              'created_at':inner['created_at'],'stamp':stamp,'restore_verified':True}
    atomic(export/(bundle_id+'.json'),json.dumps(manifest).encode(),0o644)
    # Bounded local ciphertext retention. Never remove an archive under eight
    # hours old, so a concurrent readback/acknowledgment remains possible.
    cutoff=datetime.now(UTC)-timedelta(hours=24)
    for path in export.glob('*.json'):
        if datetime.fromisoformat(json.loads(path.read_text())['created_at'])<cutoff:
            (export/(path.stem+'.tar')).unlink(missing_ok=True);path.unlink()

def offsite_reference(claimed):
    artifact=claimed.get('artifact_id')
    release=claimed.get('release_id');asset=claimed.get('asset_id')
    if type(artifact) is int and artifact>0 and release is None and asset is None:
        return f'github-artifact:{REPO_ID}:{artifact}'
    if artifact is None and type(release) is int and release>0 and type(asset) is int and asset>0:
        return f'github-release:{REPO_ID}:{release}:{asset}'
    return None

def accept_receipts():
    for ack in sorted((PRIVATE/'ack').glob('*.json')):
        if ack.is_symlink() or not re.fullmatch(r'[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}',ack.stem):continue
        try:
            claimed=json.loads(ack.read_text());manifest=json.loads((PRIVATE/'export'/(ack.stem+'.json')).read_text())
            remote=offsite_reference(claimed)
            if (claimed['bundle_id']!=ack.stem or claimed['sha256']!=manifest['sha256']
                or manifest.get('restore_verified') is not True or remote is None):continue
            receipt=f"{manifest['stamp']} {manifest['sha256']} {remote}\n".encode()
            state=PRIVATE/'backup-state'
            old=(state/'last_success').read_text().split()[0] if (state/'last_success').exists() else ''
            if manifest['stamp']>=old:
                atomic(state/'last_success',receipt,0o644)
                atomic(state/'last_restore',receipt,0o644)
        except (OSError,ValueError,KeyError,TypeError):continue

def cutover(dc,values):
    from app.clinical_gate import backup_fresh,restore_verified
    evidence={'CLINICAL_BACKUP_RECEIPT_PATH':str(PRIVATE/'backup-state/last_success'),
              'CLINICAL_RESTORE_RECEIPT_PATH':str(PRIVATE/'backup-state/last_restore')}
    marker=STATE/'clinical-active'
    initial=not marker.exists()
    writable=backup_fresh(evidence) and restore_verified(evidence)
    if initial and not writable:return 'awaiting_offsite_readback'
    cc=clinical(dc)
    # Verify application and restricted DB before touching the public proxy.
    run(cc+['up','-d','--no-build','--wait','--wait-timeout','150','api'])
    status=json.loads(run(cc+['exec','-T','api','python','-c',
        "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/readyz').read().decode())"]))
    if status.get('service')!='clinical' or (initial and status.get('clinical_entry_available') is not True):
        raise RuntimeError('Clinical readiness did not pass; staging retained')
    # Marker is permanent before the first public clinical write. Future
    # deployments and failures stay on this DB; no fallback to staging.
    if initial:atomic(marker,b'dedicated clinical database; never restart staging API\n')
    run(staging(dc)+['stop','api','caddy'])
    try:
        run(cc+['up','-d','--no-build','--wait','--wait-timeout','120','caddy'])
    except RuntimeError:
        raise RuntimeError('Clinical proxy needs recovery; clinical DB retained, staging not reactivated')
    run(staging(dc)+['stop','db'])
    # Verify the real TLS listener on this host without DNS/NAT hairpin routing.
    domain=values['CLINICAL_SITE_DOMAIN']
    public=json.loads(run(['curl','--fail','--silent','--show-error','--retry','4','--retry-connrefused','--retry-delay','2',
        '--max-time','8','--resolve',domain+':443:127.0.0.1','https://'+domain+'/readyz']))
    if public.get('service')!='clinical':raise RuntimeError('Clinical HTTPS listener not ready')
    return 'clinical_active' if public.get('clinical_entry_available') is True else 'clinical_recovery_only'

def main():
    os.chdir(ROOT);os.umask(0o077);STATE.mkdir(exist_ok=True)
    with open(STATE/'clinical-maintenance.lock','w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        # Deployment and maintenance never mutate containers concurrently.
        with open(STATE/'deploy.lock','a') as deploy:
            try:fcntl.flock(deploy,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:return
            global PHASE
            dc=docker();values=setup_paths()
            if not (STATE/'clinical-active').exists():
                run(dc+['image','tag','nims-cmv-api','nims-cmv-clinical-api'])
            PHASE='database_provisioning';print('Clinical maintenance:',PHASE,flush=True)
            provision(dc)
            PHASE='encrypted_backup_and_isolated_restore';print('Clinical maintenance:',PHASE,flush=True)
            backup_and_restore(dc)
            PHASE='offsite_receipt';accept_receipts()
            PHASE='clinical_cutover';phase=cutover(dc,values)
            atomic(STATE/'clinical-maintenance.json',json.dumps({'checked_at':datetime.now(UTC).isoformat(),
                'phase':phase,'database_provisioned':True,'isolated_restore_verified':True}).encode(),0o644)
            print('Clinical maintenance:',phase)

if __name__=='__main__':
    try:
        if '--prepare' in sys.argv:setup_paths()
        else:main()
    except Exception:
        # Reason enum only. No raw exception could expose credentials or SQL.
        STATE.mkdir(exist_ok=True)
        atomic(STATE/'clinical-maintenance.json',json.dumps({'checked_at':datetime.now(UTC).isoformat(),
            'phase':'maintenance_failed','failed_step':PHASE,
            'database_provisioned':(PRIVATE/'provisioned').exists()}).encode(),0o644)
        print('Clinical maintenance failed at '+PHASE+'; private host reconciliation needed.',file=sys.stderr)
        raise SystemExit(1)
