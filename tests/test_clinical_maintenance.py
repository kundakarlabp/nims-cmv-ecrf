import json
import os
from pathlib import Path
import pytest
from datetime import datetime, timezone

@pytest.mark.parametrize('utc_time,expected',[
    ('2026-11-19T01:59:00',False),('2026-11-19T02:00:00',True),
    ('2026-11-19T11:29:00',True),('2026-11-19T11:30:00',False),
    ('2026-11-19T18:00:00',False)])
def test_routine_backups_run_only_0730_to_1700_india(utc_time,expected):
    assert maintenance.routine_backup_window(datetime.fromisoformat(utc_time).replace(tzinfo=timezone.utc)) is expected
from ops import clinical_maintenance as maintenance
from app import clinical_gate

def test_atomic_permissions_override_strict_umask_without_exposing_secrets(tmp_path):
    previous=os.umask(0o077)
    try:
        for mode in (0o600,0o640,0o644):
            target=tmp_path/str(mode);maintenance.atomic(target,b'CI fixture',mode)
            assert target.stat().st_mode & 0o777 == mode
    finally:os.umask(previous)

def test_interrupted_cutover_resumes_proxy_and_never_reactivates_staging(tmp_path,monkeypatch):
    state=tmp_path/'state';state.mkdir();private=tmp_path/'private';private.mkdir()
    monkeypatch.setattr(maintenance,'STATE',state);monkeypatch.setattr(maintenance,'PRIVATE',private)
    monkeypatch.setattr(clinical_gate,'backup_fresh',lambda *args:True)
    monkeypatch.setattr(clinical_gate,'restore_verified',lambda *args:True)
    calls=[];fail=[True]
    def run(args,**kw):
        calls.append(args)
        if 'up' in args and 'caddy' in args and fail[0]:
            fail[0]=False;raise RuntimeError('CI simulated proxy failure')
        if args[0]=='curl' or 'python' in args:return json.dumps({'service':'clinical','clinical_entry_available':True}).encode()
        return b''
    monkeypatch.setattr(maintenance,'run',run)
    values={'CLINICAL_SITE_DOMAIN':'clinical.test.invalid'}
    with pytest.raises(RuntimeError):maintenance.cutover(['docker'],values)
    assert (state/'clinical-active').exists()
    calls.clear()
    assert maintenance.cutover(['docker'],values)=='clinical_active'
    assert any('up' in a and 'caddy' in a and 'compose.clinical.yaml' in ' '.join(a) for a in calls)
    assert not any('up' in a and 'compose.yaml' in ' '.join(a) and 'compose.clinical.yaml' not in ' '.join(a) for a in calls)

def test_existing_clinical_stack_can_recover_when_offsite_proof_is_stale(tmp_path,monkeypatch):
    state=tmp_path/'state';state.mkdir();(state/'clinical-active').write_text('permanent clinical DB')
    monkeypatch.setattr(maintenance,'STATE',state);monkeypatch.setattr(maintenance,'PRIVATE',tmp_path)
    monkeypatch.setattr(clinical_gate,'backup_fresh',lambda *args:False)
    monkeypatch.setattr(clinical_gate,'restore_verified',lambda *args:False)
    calls=[]
    def run(args,**kw):
        calls.append(args)
        return json.dumps({'service':'clinical','clinical_entry_available':False}).encode()
    monkeypatch.setattr(maintenance,'run',run)
    assert maintenance.cutover(['docker'],{'CLINICAL_SITE_DOMAIN':'clinical.test.invalid'})=='clinical_recovery_only'
    assert any('up' in a and 'api' in a for a in calls)
