"""Ciphertext-only channel for this private repository's pinned backup workflow.

No shell execution, arbitrary paths, SQL, staff sessions, or patient API access.
The agent never needs the database encryption key or browser cookies.
"""
import hashlib
import json
import os
from pathlib import Path
import re
from functools import lru_cache
import jwt
from fastapi import APIRouter, Header, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

router=APIRouter(prefix='/api/backup-channel',tags=['encrypted-backups'])
ISSUER='https://token.actions.githubusercontent.com'
AUDIENCE='nims-cmv-encrypted-backup'
REPO='kundakarlabp/nims-cmv-ecrf'
WORKFLOW=REPO+'/.github/workflows/clinical-backup.yml@refs/heads/main'
ID_RE=re.compile(r'^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$')
MAX_BUNDLE=32*1024*1024

@lru_cache(maxsize=1)
def key_client():
    return jwt.PyJWKClient(ISSUER+'/.well-known/jwks',timeout=5)

def validate_claims(claims):
    return (claims.get('repository')==REPO and
        str(claims.get('repository_id'))=='1455709378' and
        str(claims.get('repository_owner_id'))=='213684388' and
        claims.get('repository_visibility')=='private' and
        claims.get('workflow_ref')==WORKFLOW and
        claims.get('ref')=='refs/heads/main' and
        claims.get('sub')=='repo:'+REPO+':ref:refs/heads/main' and
        claims.get('event_name') in {'schedule','workflow_dispatch','workflow_run'} and
        str(claims.get('run_id','')).isdigit())

def authorize(authorization):
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(401,'Workflow identity required')
    token=authorization[7:]
    if len(token)>20000:raise HTTPException(401,'Invalid workflow identity')
    try:
        key=key_client().get_signing_key_from_jwt(token).key
        claims=jwt.decode(token,key,algorithms=['RS256'],audience=AUDIENCE,issuer=ISSUER,
            options={'require':['exp','iat','nbf','jti','sub','repository_id','repository_owner_id','workflow_ref','ref','run_id']})
        if not validate_claims(claims):raise ValueError('Scope mismatch')
        return claims
    except (jwt.PyJWTError,ValueError,OSError):
        raise HTTPException(401,'Workflow identity rejected')

def bundle_paths(bundle_id):
    if not ID_RE.fullmatch(bundle_id):raise HTTPException(404,'Backup unavailable')
    root=Path(os.getenv('CLINICAL_BACKUP_EXPORT_DIR','/run/clinical-backups'))
    return root/(bundle_id+'.tar'),root/(bundle_id+'.json')

@router.get('/latest')
def latest(response:Response,authorization:str|None=Header(default=None)):
    authorize(authorization)
    response.headers['Cache-Control']='no-store'
    root=Path(os.getenv('CLINICAL_BACKUP_EXPORT_DIR','/run/clinical-backups'))
    ids=sorted(p.stem for p in root.glob('*.json') if ID_RE.fullmatch(p.stem))
    if not ids:raise HTTPException(503,'Encrypted backup is being prepared')
    archive,manifest=bundle_paths(ids[-1])
    data=json.loads(manifest.read_text())
    if archive.is_symlink() or not archive.is_file() or archive.stat().st_size>MAX_BUNDLE:
        raise HTTPException(503,'Encrypted backup unavailable')
    # Explicit non-PHI metadata allowlist.
    return {k:data[k] for k in ('id','sha256','size','created_at','restore_verified')}

@router.get('/bundles/{bundle_id}')
def download(bundle_id:str,authorization:str|None=Header(default=None)):
    authorize(authorization)
    archive,manifest=bundle_paths(bundle_id)
    if archive.is_symlink() or not manifest.is_file() or not archive.is_file() or archive.stat().st_size>MAX_BUNDLE:
        raise HTTPException(404,'Encrypted backup unavailable')
    return FileResponse(archive,media_type='application/x-tar',filename=bundle_id+'.tar',
                        headers={'Cache-Control':'no-store'})

class Acknowledgment(BaseModel):
    bundle_id:str=Field(pattern=r'^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$')
    sha256:str=Field(pattern=r'^[0-9a-f]{64}$')
    artifact_id:int=Field(gt=0)

@router.post('/acknowledge')
def acknowledge(data:Acknowledgment,authorization:str|None=Header(default=None)):
    claims=authorize(authorization)
    archive,manifest=bundle_paths(data.bundle_id)
    if not archive.is_file() or not manifest.is_file():raise HTTPException(404,'Backup unavailable')
    local=json.loads(manifest.read_text())
    if local['sha256']!=data.sha256 or local.get('restore_verified') is not True:
        raise HTTPException(409,'Backup verification mismatch')
    directory=Path(os.getenv('CLINICAL_BACKUP_ACK_DIR','/run/backup-ack'))
    payload={**data.model_dump(),'run_id':str(claims['run_id'])}
    path=directory/(data.bundle_id+'.json')
    # An untrusted arbitrary filename cannot enter the host spool.
    temporary=directory/(data.bundle_id+'.tmp-'+os.urandom(8).hex())
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o640)
    os.fchmod(fd,0o640)
    with os.fdopen(fd,'w') as out:json.dump(payload,out)
    os.replace(temporary,path)
    return {'acknowledged':True,'clinical_activation':'host verifies the receipt before cutover'}
