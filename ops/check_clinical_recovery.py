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
"""
        dc=m.docker();m.run(m.staging(dc)+['exec','-T','api','python','-c',source])
        # Never depend on a developer/owner SSH private key in CI.
        key=directory/'ci-ssh-key'
        subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(key)],check=True)
        fakehome=directory/'home';(fakehome/'.ssh').mkdir(parents=True)
        shutil.copy(key.with_suffix('.pub'),fakehome/'.ssh/authorized_keys')
        previous_home=os.environ.get('HOME');os.environ['HOME']=str(fakehome)
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
            assert m.sql(dc,'SELECT count(*) FROM sessions;').strip()==b'0'
            assert m.sql(dc,"SELECT has_schema_privilege('nims_clinical_app','public','CREATE');").strip()==b'f'
            assert not (m.PRIVATE/'backup-state/last_success').exists()
            print('PASS: real clinical schema, named login/MFA migration, encrypted dump, isolated PostgreSQL restore, external SSH escrow recovery, no participant/session import.')
        finally:
            m.run(m.clinical(dc)+['down','-v'],check=False)
            if previous_home is None:os.environ.pop('HOME',None)
            else:os.environ['HOME']=previous_home

if __name__=='__main__':check()
