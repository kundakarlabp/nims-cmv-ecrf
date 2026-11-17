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

ROOT=Path(__file__).resolve().parents[1]


def systemctl(*args):
    try:
        value=subprocess.run(['systemctl', *args], capture_output=True, text=True,
                             timeout=5, check=False).stdout.strip()
        return value if re.fullmatch(r'[a-z-]{1,40}', value) else 'unknown'
    except (OSError, subprocess.TimeoutExpired):
        return 'unknown'


def write_status(root=ROOT):
    root=Path(root)
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
        'recorded_at':datetime.now(timezone.utc).isoformat(),
        'deployed_commit':commit if re.fullmatch(r'[0-9a-f]{40}',commit) else None,
        'timer_active':systemctl('is-active','nims-cmv-auto-deploy.timer'),
        'timer_enabled':systemctl('is-enabled','nims-cmv-auto-deploy.timer'),
        'last_deploy_result':systemctl('show','nims-cmv-auto-deploy.service',
                                       '--property=Result','--value'),
        'disk_free_mb':shutil.disk_usage(root).free//(1024*1024),
        'memory_available_mb':memory,
    }
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
    write_status()
