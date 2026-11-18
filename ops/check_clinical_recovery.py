"""Real disposable Docker recovery check. Refuses every non-CI execution."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

if os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('CLINICAL_RECOVERY_CI')!='true':
    raise SystemExit('Disposable GitHub Actions CI only')
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from ops import clinical_maintenance as m

def check():
    if (ROOT/'.env').exists():raise SystemExit('CI check refuses an existing private environment file')
    (ROOT/'.env').write_text('POSTGRES_PASSWORD='+os.environ['POSTGRES_PASSWORD']+'\nSITE_DOMAIN=http://localhost\n')
    (ROOT/'.env').chmod(0o600)
    with tempfile.TemporaryDirectory(prefix='clinical-recovery-ci-') as td:
        directory=Path(td);m.PRIVATE=directory/'private';m.STATE=directory/'state';m.STATE.mkdir()
        # Create only disposable named login fixtures in the staging container.
        source="""from app.main import User,SessionLocal,PH
from app.trial_models import UserTotp,StaffAccess
from datetime import datetime,timezone,timedelta
import pyotp
with SessionLocal() as s:
 u=User(username='ci-investigator',display_name='CI ONLY Bhanu Prasad fixture',role='admin',password_hash=PH.hash('DisposableCIOnlyLongPassword123!'));s.add(u);s.flush()
 s.add(UserTotp(user_id=u.id,secret=pyotp.random_base32(),enabled=True))
 s.add(StaffAccess(user_id=u.id,expires_at=datetime.now(timezone.utc)+timedelta(days=90)));s.commit()
 s.add(User(username='ci-nurse',display_name='CI ONLY named nurse fixture',role='nurse',password_hash=PH.hash('DisposableCIOnlyNursePassword123!')));s.commit()
"""
        dc=m.docker();m.run(m.staging(dc)+['exec','-T','api','python','-c',source])
        # Never depend on a developer/owner SSH private key in CI.
        key=directory/'ci-ssh-key'
        subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(key)],check=True)
        fakehome=directory/'home';(fakehome/'.ssh').mkdir(parents=True)
        shutil.copy(key.with_suffix('.pub'),fakehome/'.ssh/authorized_keys')
        previous_home=os.environ.get('HOME');os.environ['HOME']=str(fakehome)
        old_umask=os.umask(0o077)
        try:
            values=m.setup_paths()
            m.run(dc+['image','tag','nims-cmv-api','nims-cmv-clinical-api'])
            m.provision(dc);m.backup_and_restore(dc)
            manifests=list((m.PRIVATE/'export').glob('*.json'));assert len(manifests)==1
            record=json.loads(manifests[0].read_text());assert record['restore_verified'] is True
            archive=m.PRIVATE/'export'/(record['id']+'.tar')
            with tarfile.open(archive) as tf:
                assert set(tf.getnames())=={'database.dump.fernet','recovery-keys.age','manifest.json'}
                encrypted=tf.extractfile('database.dump.fernet').read()
                escrow=tf.extractfile('recovery-keys.age').read()
            # Actually decrypt the offsite escrow with the disposable external
            # private SSH key, then open the exact encrypted archive.
            recovered=json.loads(m.run(['age','-d','-i',key],data=escrow))
            from cryptography.fernet import Fernet
            assert Fernet(recovered['backup_fernet_key'].encode()).decrypt(encrypted).startswith(b'PGDMP')
            assert recovered['allocation_fernet_key']==(m.PRIVATE/'allocation.key').read_text().strip()
            assert m.sql(dc,'SELECT count(*) FROM patients;').strip()==b'0'
            assert m.sql(dc,'SELECT count(*) FROM users WHERE pi_authorized;').strip()==b'1'
            assert m.sql(dc,'SELECT count(*) FROM trial_user_totp WHERE enabled;').strip()==b'1'
            assert m.sql(dc,'SELECT count(*) FROM trial_staff_access;').strip()==b'2'
            assert m.sql(dc,'SELECT count(*) FROM sessions;').strip()==b'0'
            assert m.sql(dc,"SELECT has_schema_privilege('nims_clinical_app','public','CREATE');").strip()==b'f'
            assert not (m.PRIVATE/'backup-state/last_success').exists()
            assert archive.stat().st_mode & 0o777 == 0o644
            # Actual API UID can read ciphertext/auth mounts under umask 077.
            m.run(dc+['run','--rm','--network','none','--user','10001:65534',
                '-v',str(m.PRIVATE/'export')+':/run/export:ro',
                '-v',str(m.PRIVATE/'authorization.json')+':/run/authorization:ro',
                'nims-cmv-clinical-api','python','-c',
                "from pathlib import Path; import json; assert list(Path('/run/export').glob('*.tar')); [p.read_bytes() for p in Path('/run/export').glob('*')];json.loads(Path('/run/authorization').read_text())"])
            try:m.sql(dc,"UPDATE users SET active=false WHERE username='ci-investigator';",'nims_ecrf',True)
            except RuntimeError:pass
            else:raise AssertionError('Staging account mutations were not frozen during migration')
            print('PASS: real clinical schema, named login/MFA migration, encrypted dump, isolated PostgreSQL restore, external SSH escrow recovery, no participant/session import.')
            credentials=m.sql(dc,"SELECT username,password_hash FROM users ORDER BY username;")
            m.owner_workspace_update(dc)
            assert m.sql(dc,'SELECT count(*) FROM patients;').strip()==b'0'
            assert m.sql(dc,'SELECT count(*) FROM trial_subjects;').strip()==b'0'
            assert m.sql(dc,'SELECT count(*) FROM trial_randomization_plans;').strip()==b'1'
            assert m.sql(dc,'SELECT count(*) FROM trial_randomization_slots WHERE subject_id IS NOT NULL;').strip()==b'0'
            assert m.sql(dc,'SELECT count(*) FROM trial_user_totp;').strip()==b'0'
            assert credentials==m.sql(dc,"SELECT username,password_hash FROM users ORDER BY username;")
            # Real HTTP login against the password-only clinical container.
            login_check="""import urllib.request,json
for username,password in [('ci-investigator','DisposableCIOnlyLongPassword123!'),('ci-nurse','DisposableCIOnlyNursePassword123!')]:
 req=urllib.request.Request('http://127.0.0.1:8000/api/login',data=json.dumps({'username':username,'password':password}).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req) as response:result=json.load(response)
 assert result['password_only'] is True and result['workspace_full_access'] is True
 assert result['mfa_setup_required'] is False and result['mfa_enabled'] is False
print('PASS: named owner and nurse logged in with password only; no OTP or enrollment.')
"""
            m.run(m.clinical(dc)+['exec','-T','api','python','-c',login_check])
            # A fresh entry after the reset must survive future maintenance,
            # even if the filesystem completion marker disappears.
            m.sql(dc,"INSERT INTO patients(id,cr_number,name,created_by,revision,created_at) SELECT 'CI-POST-RESET','TEST-AFTER-RESET','Synthetic after reset',id,1,now() FROM users WHERE pi_authorized;")
            (m.PRIVATE/'fresh-start-20261118-v1.complete').unlink()
            m.owner_workspace_update(dc)
            assert m.sql(dc,"SELECT count(*) FROM patients WHERE id='CI-POST-RESET';").strip()==b'1'
            assert m.sql(dc,"SELECT count(*) FROM audit_events WHERE action='owner_fresh_start_reset';").strip()==b'1'
            print('PASS: real one-time training reset, preserved password hashes, permanent fresh sequence, and crash-safe repeat maintenance.')
        finally:
            m.run(m.clinical(dc)+['down','-v'],check=False)
            (ROOT/'.env').unlink(missing_ok=True)
            if previous_home is None:os.environ.pop('HOME',None)
            else:os.environ['HOME']=previous_home
            os.umask(old_umask)

if __name__=='__main__':check()
