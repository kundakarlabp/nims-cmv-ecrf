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

def test_main_accepts_connector_readback_before_cutover(tmp_path,monkeypatch):
    root=tmp_path/'repo';root.mkdir();state=root/'.deploy-state'
    private=tmp_path/'private';private.mkdir()
    monkeypatch.setattr(maintenance,'ROOT',root)
    monkeypatch.setattr(maintenance,'STATE',state)
    monkeypatch.setattr(maintenance,'PRIVATE',private)
    monkeypatch.setattr(maintenance.os,'chdir',lambda path:None)
    order=[]
    monkeypatch.setattr(maintenance,'docker',lambda:['docker'])
    monkeypatch.setattr(maintenance,'run',lambda *args,**kwargs:b'')
    monkeypatch.setattr(maintenance,'setup_paths',lambda:{'CLINICAL_SITE_DOMAIN':'clinical.test.invalid'})
    monkeypatch.setattr(maintenance,'provision',lambda dc:None)
    monkeypatch.setattr(maintenance,'provision_oauth',lambda dc:None)
    monkeypatch.setattr(maintenance,'owner_workspace_update',lambda dc:None)
    monkeypatch.setattr(maintenance,'backup_and_restore',lambda dc:order.append('backup'))
    monkeypatch.setattr(maintenance,'accept_receipts',lambda:order.append('accept'))
    monkeypatch.setattr(maintenance,'cutover',lambda dc,values:order.append('cutover') or 'clinical_active')
    monkeypatch.setattr('ops.drive_offsite.sync_latest',lambda private, **kwargs:order.append('sync') or False)
    maintenance.main()
    assert order==['backup','accept','sync','cutover']
