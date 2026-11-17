"""Host-only, stdin account migration; no patient records or active sessions."""
import json
import os
import sys
from datetime import datetime,timedelta,timezone
from sqlalchemy import text
if os.getenv('CLINICAL_SCHEMA_BOOTSTRAP')!='true' or os.getenv('DB_NAME')!='nims_cmv_clinical':
    raise SystemExit('Dedicated clinical bootstrap required')
from app.main import ENGINE,Base
if ENGINE.dialect.name!='postgresql':raise SystemExit('Dedicated PostgreSQL required')
data=json.load(sys.stdin)
allowed={'users','trial_user_totp','trial_staff_access','trial_user_invitations'}
if set(data)-allowed:raise SystemExit('Non-account data refused')
with ENGINE.begin() as conn:
    if conn.execute(text('SELECT count(*) FROM users')).scalar()!=0:raise SystemExit('Existing clinical accounts preserved; import refused')
    for table in ('users','trial_staff_access','trial_user_totp','trial_user_invitations'):
        for row in data.get(table,[]):
            columns=set(Base.metadata.tables[table].columns.keys())
            filtered={k:v for k,v in row.items() if k in columns}
            # PostgreSQL json_populate_record preserves timestamps and typed
            # fields without Python coercion or concatenating values into SQL.
            conn.execute(text(f'INSERT INTO {table} SELECT (json_populate_record(NULL::{table},CAST(:record AS json))).*'),
                         {'record':json.dumps(filtered)})
    owners=data['users'];owner=next(row for row in owners if row.get('pi_authorized'))
    # Retain explicit current access windows. Older active named accounts
    # predate that table; the owner's activation instruction authorizes their
    # normal 90-day onboarding, without reviving expired/revoked authorizations.
    existing_access={row['user_id'] for row in data.get('trial_staff_access',[])}
    for user in owners:
        if user['active'] and user['role'] not in {'admin','pi'} and user['id'] not in existing_access:
            conn.execute(text('INSERT INTO trial_staff_access(user_id,activated_at,expires_at,renewed_by) VALUES (:id,:activated,:expires,:owner)'),
                {'id':user['id'],'activated':datetime.now(timezone.utc),
                 'expires':datetime.now(timezone.utc)+timedelta(days=90),'owner':owner['id']})
    conn.execute(text("INSERT INTO audit_events(id,actor_id,action,entity_type,entity_id,reason,created_at) VALUES (:id,:actor,'clinical_activation','user',:actor,'Owner-authorized clinical activation; named accounts retained; no staging patient records imported',now())"),
                 {'id':__import__('uuid').uuid4().hex,'actor':owner['id']})
print('Named study accounts imported. No participant records or sessions copied.')
