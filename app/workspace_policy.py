"""Owner-requested password-only, shared clinical workspace. No public write access."""
import json
import os
from pathlib import Path

POLICY_ID='owner-password-team-20261118'

def enabled(env=None):
    env=os.environ if env is None else env
    if env.get('TEAM_WORKSPACE_ENABLED','false').lower()!='true':return False
    if env.get('CLINICAL_DATA_ENABLED','false').lower()!='true':return True
    from .clinical_gate import owner_authorized
    if not owner_authorized(env):return False
    try:
        data=json.loads(Path(env['CLINICAL_OWNER_AUTHORIZATION_PATH']).read_text())
        return (data.get('workspace_policy')==POLICY_ID and
                data.get('password_only_requested') is True and
                data.get('training_examples_confirmed') is True and
                data.get('independent_custodian_required') is False)
    except (KeyError,OSError,ValueError,TypeError):return False

def password_only(env=None):
    env=os.environ if env is None else env
    return enabled(env) and env.get('PASSWORD_ONLY_LOGIN','false').lower()=='true'

def clinical_path(path):
    # Account invitation/revocation, passwords and system operations retain
    # their original administrator permissions, even with shared clinical use.
    return path.startswith(('/api/patients','/api/entries','/api/review-queue',
        '/api/trial/subjects','/api/trial/screening','/api/trial/eligibility-schema',
        '/api/trial/pcr','/api/trial/pharmacy','/api/trial/crf','/api/trial/randomization',
        '/api/trial/overview','/api/dashboard','/api/due','/api/dose-preview'))
