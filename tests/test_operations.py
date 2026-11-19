"""No patient records or server credentials are used by these checks."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.operations import read_host_status
from app.main import app, current, AuthContext


def test_operations_requires_session_and_admin_role():
    with TestClient(app) as client:
        assert client.get('/api/system/operations').status_code == 401
        assert client.get('/operations').status_code == 401
        try:
            app.dependency_overrides[current] = lambda: AuthContext(
                user_id='test', role='pg', name='Test', csrf_hash='test')
            assert client.get('/api/system/operations').status_code == 403
            assert client.get('/operations').status_code == 403
            app.dependency_overrides[current] = lambda: AuthContext(
                user_id='test', role='admin', name='Test', csrf_hash='test')
            response = client.get('/api/system/operations')
            assert response.status_code == 200
            assert 'no-store' in response.headers['cache-control']
            assert response.json()['database'] == 'reachable'
            assert response.json()['mode'] == 'synthetic'
            assert response.json()['clinical_registration_enabled'] is False
            assert client.get('/operations').status_code == 200
            # The endpoint accepts no remote command or filesystem parameter.
            assert client.post('/api/system/operations', json={'command':'id'}).status_code == 405
        finally:
            app.dependency_overrides.pop(current, None)


def test_host_status_filters_secrets_and_rejects_stale_receipts(tmp_path):
    at = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)
    report = tmp_path/'status.json'
    report.write_text(json.dumps({
        'recorded_at':at.isoformat(), 'deployed_commit':'a'*40,
        'timer_active':'active', 'timer_enabled':'enabled',
        'last_deploy_result':'success', 'disk_free_mb':1234,
        'memory_available_mb':321, 'password':'NEVER-EXPOSE-ME',
        'logs':['PRIVATE'], 'environment':{'secret':'PRIVATE'}}))
    data = read_host_status(report, at)
    assert data['fresh'] is True
    assert data['deployed_commit'] == 'a'*40
    assert 'NEVER-EXPOSE-ME' not in json.dumps(data)
    assert 'PRIVATE' not in json.dumps(data)
    assert read_host_status(report, at+timedelta(minutes=16))['fresh'] is False
    assert read_host_status(report, at-timedelta(minutes=1))['fresh'] is False


@pytest.mark.parametrize('body', ['not json', '[]', '{"recorded_at":null}', 'x'*17000])
def test_unreadable_or_invalid_report_does_not_break_operations(tmp_path, body):
    report=tmp_path/'status.json'
    report.write_text(body)
    assert read_host_status(report)['available'] is False
    assert read_host_status(tmp_path/'missing')['available'] is False


def test_invalid_host_fields_do_not_appear_as_commands_or_html(tmp_path):
    report=tmp_path/'status.json'
    report.write_text(json.dumps({'recorded_at':datetime.now(timezone.utc).isoformat(),
        'deployed_commit':'not-a-sha', 'timer_active':'<script>secret</script>',
        'disk_free_mb':-1, 'memory_available_mb':True}))
    data=read_host_status(report)
    assert data['deployed_commit'] is None
    assert data['timer_active'] == 'unknown'
    assert data['disk_free_mb'] is None
    assert data['memory_available_mb'] is None


def test_host_publisher_is_atomic_readable_and_never_collects_environment(tmp_path, monkeypatch):
    from ops import operations_status as publisher
    state=tmp_path/'.deploy-state'
    state.mkdir()
    (state/'current-commit').write_text('b'*40)
    monkeypatch.setenv('POSTGRES_PASSWORD','PRIVATE-NEVER-COLLECT')
    monkeypatch.setattr(publisher,'systemctl',lambda *args: 'active' if args[0]=='is-active' else 'enabled' if args[0]=='is-enabled' else 'success')
    publisher.write_status(tmp_path)
    report=tmp_path/'ops/public-status/status.json'
    assert report.stat().st_mode & 0o004
    assert report.parent.stat().st_mode & 0o005
    data=read_host_status(report)
    assert data['fresh'] and data['deployed_commit']=='b'*40
    assert 'PRIVATE-NEVER-COLLECT' not in report.read_text()
    assert not list(report.parent.glob('.status-*'))


def test_generated_receipt_remains_ignored_after_rollback(tmp_path, monkeypatch):
    import subprocess
    from ops import operations_status as publisher
    def git(*args):
        return subprocess.run(['git',*args],cwd=tmp_path,check=True,capture_output=True,text=True).stdout.strip()
    git('init');git('config','user.email','test@example.invalid');git('config','user.name','Test')
    (tmp_path/'base').write_text('base')
    git('add','base');git('commit','-m','base')
    previous=git('rev-parse','HEAD')
    directory=tmp_path/'ops/public-status';directory.mkdir(parents=True)
    (directory/'.gitignore').write_text('*\n!.gitignore\n')
    git('add','ops/public-status/.gitignore');git('commit','-m','feature')
    monkeypatch.setattr(publisher,'systemctl',lambda *args:'unknown')
    publisher.write_status(tmp_path,attempt_result='failed')
    git('checkout','--detach',previous)
    assert git('status','--porcelain') == ''
    data=read_host_status(directory/'status.json')
    assert data['last_update_attempt']=='failed'


def test_failed_fetch_publishes_completed_failure(tmp_path):
    import shutil
    import subprocess
    import os
    root=Path(__file__).resolve().parents[1]
    (tmp_path/'ops').mkdir()
    for file in ('auto_deploy.sh','operations_status.py'):
        shutil.copy(root/'ops'/file,tmp_path/'ops'/file)
    bindir=tmp_path/'bin';bindir.mkdir()
    fake=bindir/'git'
    fake.write_text('#!/bin/sh\nexit 42\n')
    fake.chmod(0o755)
    env=dict(os.environ,PATH=str(bindir)+os.pathsep+os.environ['PATH'])
    result=subprocess.run(['bash',str(tmp_path/'ops/auto_deploy.sh')],
        env=env,capture_output=True,text=True,timeout=20)
    assert result.returncode==42
    data=read_host_status(tmp_path/'ops/public-status/status.json')
    assert data['fresh'] and data['last_update_attempt']=='failed'


def test_backup_configuration_probe_returns_only_presence(tmp_path):
    from ops.operations_status import backup_configuration_present
    config=tmp_path/'rclone.conf'
    assert backup_configuration_present(config) is False
    config.write_text('[ecrfcrypt]\ntype = drive\npassword = PRIVATE\n')
    assert backup_configuration_present(config) is False
    config.write_text('[ecrfcrypt]\ntype = crypt\nremote = PRIVATE\npassword = PRIVATE\n')
    assert backup_configuration_present(config) is True
    config.write_text('RCLONE_ENCRYPT_V0:\nPRIVATE')
    assert backup_configuration_present(config) is None


def test_git_provenance_is_read_only_and_reconciles_only_valid_tags(tmp_path):
    """Host receipt includes fixed SHA references, not secrets or mutable raw logs."""
    import subprocess
    from ops.operations_status import git_commit, latest_approved_release, write_status

    def command(*args):
        return subprocess.run(['git',*args],cwd=tmp_path,capture_output=True,
                              text=True,check=True).stdout.strip()

    command('init','-b','main')
    command('config','user.email','test@example.invalid')
    command('config','user.name','Test')
    (tmp_path/'README').write_text('test only')
    command('add','README')
    command('commit','-m','safe build')
    sha=command('rev-parse','HEAD')
    command('update-ref','refs/remotes/origin/main',sha)
    assert git_commit(tmp_path,'refs/remotes/origin/main')==sha
    assert latest_approved_release(tmp_path) is None
    command('tag','-a',f'cmv-staging-20261119T093000Z-{sha}','-m','approved',sha)
    assert latest_approved_release(tmp_path)==sha

    write_status(tmp_path)
    report=read_host_status(tmp_path/'ops/public-status/status.json')
    assert report['fresh']
    assert report['github_main_commit']==sha
    assert report['approved_release_commit']==sha
    assert not any(key in report for key in ('logs','environment','secret'))

    command('tag','-a','cmv-staging-20261119T094000Z-'+'0'*40,
            '-m','mismatched release',sha)
    assert latest_approved_release(tmp_path) is None
