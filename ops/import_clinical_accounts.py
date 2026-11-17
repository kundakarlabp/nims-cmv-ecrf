"""Host-only, stdin account migration; no patient records or active sessions."""
import json
import os
import sys
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
    conn.execute(text("SELECT setval(pg_get_serial_sequence('trial_user_invitations','id'), coalesce(max(id),1), count(*)>0) FROM trial_user_invitations"))
    owners=data['users'];owner=next(row for row in owners if row.get('pi_authorized'))
    conn.execute(text("INSERT INTO audit_events(id,actor_id,action,entity_type,entity_id,reason,created_at) VALUES (:id,:actor,'clinical_activation','user',:actor,'Owner-authorized clinical activation; named accounts retained; no staging patient records imported',now())"),
                 {'id':__import__('uuid').uuid4().hex,'actor':owner['id']})
print('Named study accounts imported. No participant records or sessions copied.')
