#!/usr/bin/env python3
"""Prepare private server configuration; never start services or authorize use.

Generated passwords/keys stay outside the Git checkout, without being printed.
Existing operator files are preserved. No source records or accounts are copied.
"""
import base64
import os
from pathlib import Path
import secrets

PRIVATE_ROOT=Path.home()/'.local/share/nims-cmv-clinical'


def create_once(path, content, mode=0o600):
    # O_EXCL prevents accidental credential rotation on repeated deployments.
    try:
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,mode)
    except FileExistsError:
        if Path(path).is_symlink() or not Path(path).is_file():
            raise RuntimeError('Private configuration target must be a regular file')
        os.chmod(path,mode)
        return
    with os.fdopen(fd,'wb') as output:
        output.write(content)
    os.chmod(path,mode)


def prepare(private=PRIVATE_ROOT):
    private=Path(private)
    if private.is_symlink():
        raise RuntimeError('Private configuration directory cannot be a symlink')
    private.mkdir(parents=True,exist_ok=True)
    private.chmod(0o700)
    key=private/'allocation.key'
    config=private/'clinical.env'
    # The private parent remains owner-only. Only this file's group is made
    # readable inside the API's read-only bind mount via group_add.
    create_once(key,base64.urlsafe_b64encode(secrets.token_bytes(32))+b'\n',0o640)
    # These are configuration placeholders, never claims of approval or UAT.
    fields={
        'CLINICAL_DB_OWNER_PASSWORD':secrets.token_urlsafe(40),
        'CLINICAL_DB_APP_PASSWORD':secrets.token_urlsafe(40),
        'CLINICAL_INSTITUTIONAL_APPROVAL':'unverified',
        'CLINICAL_UAT_APPROVED':'unverified',
        'CLINICAL_SITE_DOMAIN':'unconfigured.invalid',
        'CLINICAL_SIGNOFF_PATH':'/dev/null',
        'CLINICAL_BACKUP_STATE_DIR':str(private/'backup-state'),
        'CLINICAL_RANDOMIZATION_KEY_PATH':str(key),
        'CLINICAL_KEY_READER_GID':str(key.stat().st_gid),
    }
    create_once(config,(''.join(k+'='+v+'\n' for k,v in fields.items())).encode())
    try:
        decoded=base64.b64decode(key.read_bytes().strip(),altchars=b'-_',validate=True)
        values=dict(line.split('=',1) for line in config.read_text().splitlines()
                    if line and not line.startswith('#') and '=' in line)
        passwords=[values.get(name,'') for name in
                   ('CLINICAL_DB_OWNER_PASSWORD','CLINICAL_DB_APP_PASSWORD')]
        if (len(decoded)!=32 or min(map(len,passwords))<20 or passwords[0]==passwords[1]
            or values.get('CLINICAL_KEY_READER_GID')!=str(key.stat().st_gid)):
            raise ValueError('Incomplete configuration')
    except (ValueError,UnicodeError) as error:
        raise RuntimeError('Existing private clinical configuration needs review; nothing was rotated') from error
    (private/'backup-state').mkdir(exist_ok=True)
    (private/'backup-state').chmod(0o755)
    # Older deployment launchers already call this helper before Compose.
    # Create bind sources as the deployment owner, preventing Docker from
    # creating root-owned directories during the first feature rollout.
    for name,mode in [('export',0o755),('ack',0o700)]:
        directory=private/name
        if directory.is_symlink():raise RuntimeError('Private bind source cannot be a symlink')
        if not directory.exists():
            directory.mkdir(mode=mode);directory.chmod(mode)
    return {'configuration_prepared':True,'allocation_key_prepared':True}


if __name__=='__main__':
    prepare()
    print('Private clinical configuration prepared; clinical activation is unchanged.')

