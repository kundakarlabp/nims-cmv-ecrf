#!/usr/bin/env python3
"""Publish nonpatient host health using fixed read-only commands; no raw logs."""
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import tempfile
import configparser

ROOT=Path(__file__).resolve().parents[1]


def backup_configuration_present(path):
    """Inspect only the named backup config; expose no configuration values."""
    try:
        parser=configparser.ConfigParser(interpolation=None)
        with Path(path).open() as source:
            parser.read_file(source)
        return (parser.get('ecrfcrypt','type',fallback='')=='crypt'
                and bool(parser.get('ecrfcrypt','remote',fallback=''))
                and bool(parser.get('ecrfcrypt','password',fallback='')))
    except FileNotFoundError:
        return False
    except (OSError,UnicodeError,configparser.Error):
        return None



def drive_backup_configuration_present(path):
    """Report only whether OCI's Drive OAuth config targets the private folder."""
    try:
        parser=configparser.ConfigParser(interpolation=None)
        config=Path(path)
        if config.stat().st_mode & 0o077:return False
        with config.open() as source:parser.read_file(source)
        return (parser.get('nims_cmv_drive','type',fallback='')=='drive'
                and parser.get('nims_cmv_drive','root_folder_id',fallback='')
                    =='1Mnzme95zuQM5WKuHWtsv2-nzhtPUK_EM'
                and bool(parser.get('nims_cmv_drive','token',fallback='')
                    or parser.get('nims_cmv_drive','service_account_file',fallback='')))
    except FileNotFoundError:return False
    except (OSError,UnicodeError,configparser.Error):return None


def drive_receipt_present(home):
    """Receipt presence only, not currentness or a successful cloud probe."""
    path=Path(home)/'.local/share/nims-cmv-clinical/backup-state/last_success'
    try:
        fields=path.read_text().split()
        return (len(fields)==3 and fields[2].startswith(
            'gdrive:1Mnzme95zuQM5WKuHWtsv2-nzhtPUK_EM:clinical-'))
    except FileNotFoundError:return False
    except (OSError,UnicodeError):return None

def systemctl(*args):
    try:
        value=subprocess.run(['systemctl', *args], capture_output=True, text=True,
                             timeout=5, check=False).stdout.strip()
        return value if re.fullmatch(r'[a-z-]{1,40}', value) else 'unknown'
    except (OSError, subprocess.TimeoutExpired):
        return 'unknown'



def git_commit(root, ref):
    """Read a fixed or validated local Git reference, never an external command."""
    try:
        value=subprocess.run(['git','rev-parse','--verify',ref],cwd=root,
                             capture_output=True,text=True,timeout=5,check=True).stdout.strip()
        return value if re.fullmatch(r'[0-9a-f]{40}',value) else None
    except (OSError,subprocess.SubprocessError):
        return None


def latest_approved_release(root):
    """Report the newest fetched staging tag; no claim about live CI state."""
    try:
        result=subprocess.run(['git','tag','--list','cmv-staging-*','--sort=-refname'],
                              cwd=root,capture_output=True,text=True,timeout=5,check=True)
    except (OSError,subprocess.SubprocessError):
        return None
    tags=result.stdout.splitlines()
    if not tags:
        return None
    tag=tags[0]
    match=re.fullmatch(r'cmv-staging-[0-9]{8}T[0-9]{6}Z-([0-9a-f]{40})',tag)
    if not match:
        return None
    target=match.group(1)
    return target if git_commit(root,tag+'^{commit}')==target else None


def write_status(root=ROOT, attempt_result='running'):
    root=Path(root)
    # Persist outside tracked files so rollback to a pre-feature revision
    # cannot make generated receipts dirty the checkout and block retries.
    try:
        gitdir=subprocess.run(['git','rev-parse','--git-path','info/exclude'],
            cwd=root,capture_output=True,text=True,timeout=5,check=True).stdout.strip()
        excluded=Path(gitdir)
        if not excluded.is_absolute(): excluded=root/excluded
        pattern='/ops/public-status/'
        existing=excluded.read_text() if excluded.exists() else ''
        if pattern not in existing.splitlines():
            excluded.parent.mkdir(parents=True,exist_ok=True)
            with excluded.open('a') as ignore: ignore.write('\n'+pattern+'\n')
    except (OSError,subprocess.SubprocessError):
        # Do not publish inside a Git checkout unless rollback-safe ignore
        # has been installed. Non-Git test roots have no checkout to dirty.
        if (root/'.git').exists(): raise
    directory=root/'ops/public-status'
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(0o755)
    try:
        commit=(root/'.deploy-state/current-commit').read_text().strip()
    except OSError:
        commit=''
    memory=None
    try:
        for line in Path('/proc/meminfo').read_text().splitlines():
            if line.startswith('MemAvailable:'):
                memory=int(line.split()[1])//1024
    except (OSError, ValueError, IndexError):
        pass
    receipt={
        'clinical_private_configuration_present':(Path.home()/'.local/share/nims-cmv-clinical/clinical.env').is_file(),
        'backup_tool_installed':shutil.which('rclone') is not None,
        'encrypted_backup_configuration_present':backup_configuration_present(
            os.environ.get('RCLONE_CONFIG',str(Path.home()/'.config/rclone/rclone.conf'))),
        'google_drive_backup_configuration_present':drive_backup_configuration_present(
            os.environ.get('RCLONE_CONFIG',str(Path.home()/'.config/rclone/rclone.conf'))),
        'google_drive_backup_receipt_present':drive_receipt_present(Path.home()),
        'last_update_attempt':attempt_result,
        'recorded_at':datetime.now(timezone.utc).isoformat(),
        'deployed_commit':commit if re.fullmatch(r'[0-9a-f]{40}',commit) else None,
        'github_main_commit':git_commit(root,'refs/remotes/origin/main'),
        'approved_release_commit':latest_approved_release(root),
        'timer_active':systemctl('is-active','nims-cmv-auto-deploy.timer'),
        'timer_enabled':systemctl('is-enabled','nims-cmv-auto-deploy.timer'),
        'last_deploy_result':systemctl('show','nims-cmv-auto-deploy.service',
                                       '--property=Result','--value'),
        'disk_free_mb':shutil.disk_usage(root).free//(1024*1024),
        'memory_available_mb':memory,
    }
    try:
        clinical=json.loads((root/'.deploy-state/clinical-maintenance.json').read_text())
        receipt['clinical_transition']=clinical.get('phase')
        receipt['clinical_failed_step']=clinical.get('failed_step')
    except (OSError,ValueError,TypeError):pass
    fd, temporary=tempfile.mkstemp(prefix='.status-',dir=directory)
    try:
        with os.fdopen(fd,'w') as output:
            json.dump(receipt,output)
            output.write('\n')
        os.chmod(temporary,0o644)
        os.replace(temporary,directory/'status.json')
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--attempt-result',choices=['running','success','failed'],default='running')
    args=parser.parse_args()
    write_status(root=args.root,attempt_result=args.attempt_result)

