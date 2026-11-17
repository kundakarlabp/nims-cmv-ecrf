"""Read-only, allowlisted operational receipts. No shell or patient-data access."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import re

SHA = re.compile(r'^[0-9a-f]{40}$')


def read_host_status(path=Path('/run/operations/status.json'), at=None):
    at = at or datetime.now(timezone.utc)
    unavailable = {'available':False, 'fresh':False}
    try:
        path=Path(path)
        if path.stat().st_size > 16384:
            return unavailable
        value=json.loads(path.read_text())
        if not isinstance(value, dict):
            return unavailable
        stamp=datetime.fromisoformat(value['recorded_at'])
        if stamp.tzinfo is None:
            return unavailable
        fresh=timedelta(0) <= at-stamp <= timedelta(minutes=15)
    except (OSError, ValueError, TypeError, KeyError):
        return unavailable
    result={'available':True, 'fresh':fresh, 'recorded_at':stamp.isoformat()}
    commit=value.get('deployed_commit')
    result['deployed_commit']=commit if isinstance(commit,str) and SHA.fullmatch(commit) else None
    for key, allowed in {
        'timer_active':{'active','inactive','failed','activating','deactivating'},
        'timer_enabled':{'enabled','disabled','static','masked'},
        'last_deploy_result':{'success','exit-code','timeout','signal','core-dump',
                              'resources','start-limit-hit'},
    }.items():
        field=value.get(key)
        result[key]=field if isinstance(field,str) and field in allowed else 'unknown'
    for key in ('disk_free_mb','memory_available_mb'):
        field=value.get(key)
        result[key]=field if type(field) is int and 0 <= field <= 10**12 else None
    return result
