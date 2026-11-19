"""User-bound OAuth authorization-code/PKCE with opaque, revocable tokens.

No model API, new identity provider, clinical schema mutation or token passthrough.
"""
import base64
import hashlib
import json
import os
import re
import secrets
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .main import (ENGINE, CLINICAL_MODE, AuthContext, User, LoginSession, current,
                   authorize_account, db, now, uid, sha, UTC, audit)
from .oauth_models import OAuthBase, OAuthClient, OAuthCode, OAuthGrant, OAuthToken

router=APIRouter(tags=['private-mcp-oauth'])
SCOPES={'cmv:read','cmv:write'}
ACCESS_SECONDS=900
CALLBACK_RE=re.compile(r'https://chatgpt[.]com/connector/oauth/[A-Za-z0-9_-]+\Z')
if not CLINICAL_MODE and os.getenv('CLINICAL_SCHEMA_BOOTSTRAP','false')!='true':
    OAuthBase.metadata.create_all(ENGINE)  # Same staging-only convention as main.


def origin():
    value=os.getenv('MCP_PUBLIC_ORIGIN','').rstrip('/')
    if not value:
        host=os.getenv('SITE_DOMAIN','')
        value='https://'+host if host and '://' not in host else host.rstrip('/')
    parsed=urlparse(value)
    if (parsed.scheme!='https' or not parsed.hostname or parsed.netloc!=parsed.hostname
        or parsed.path or parsed.query or parsed.fragment or parsed.username):
        raise HTTPException(503,'MCP public HTTPS origin is not configured')
    return value


def resource(): return origin()+'/mcp'
def expired(at): return at.replace(tzinfo=UTC)<=now()
def oauth_error(code='invalid_grant',status=400):
    return JSONResponse({'error':code},status_code=status,headers={'Cache-Control':'no-store','Pragma':'no-cache'})
def token_error():
    return HTTPException(401,'OAuth authorization required',headers={'WWW-Authenticate':
        f'Bearer resource_metadata="{origin()}/.well-known/oauth-protected-resource", scope="cmv:read"'})


@router.get('/.well-known/oauth-protected-resource')
@router.get('/.well-known/oauth-protected-resource/mcp')
def protected_resource():
    return {'resource':resource(),'authorization_servers':[origin()],
            'scopes_supported':sorted(SCOPES),'bearer_methods_supported':['header']}


@router.get('/.well-known/oauth-authorization-server')
def server_metadata():
    base=origin()
    return {'issuer':base,'authorization_endpoint':base+'/oauth/authorize',
        'token_endpoint':base+'/oauth/token','registration_endpoint':base+'/oauth/register',
        'revocation_endpoint':base+'/oauth/revoke','response_types_supported':['code'],
        'grant_types_supported':['authorization_code','refresh_token'],
        'token_endpoint_auth_methods_supported':['none'],
        'revocation_endpoint_auth_methods_supported':['none'],
        'code_challenge_methods_supported':['S256'],'scopes_supported':sorted(SCOPES),
        'authorization_response_iss_parameter_supported':True}


class ClientInput(BaseModel):
    client_name: str=Field(default='ChatGPT',max_length=100)
    redirect_uris: list[str]=Field(min_length=1,max_length=5)
    token_endpoint_auth_method: str='none'
    grant_types: list[str]=Field(default_factory=lambda:['authorization_code','refresh_token'])
    response_types: list[str]=Field(default_factory=lambda:['code'])


def allowed_redirect(value):
    return value=='https://chatgpt.com/connector_platform_oauth_redirect' or bool(CALLBACK_RE.fullmatch(value))


@router.post('/oauth/register')
def register_client(data:ClientInput,s:Session=Depends(db)):
    origin()  # Refuse creation until origin is configured.
    if (data.token_endpoint_auth_method!='none' or any(not allowed_redirect(v) for v in data.redirect_uris)
        or not set(data.grant_types)<= {'authorization_code','refresh_token'} or data.response_types!=['code']):
        return oauth_error('invalid_client_metadata')
    # Registration is public but bounded to ChatGPT callbacks and deduplicated.
    redirects=sorted(set(data.redirect_uris))
    key=sha(json.dumps(redirects))
    client=s.get(OAuthClient,key)
    if not client:
        if s.scalar(select(func.count()).select_from(OAuthClient))>=128:
            return oauth_error('temporarily_unavailable',429)
        client=OAuthClient(id=key,name='ChatGPT',redirects=redirects)
        try:
            with s.begin_nested():s.add(client);s.flush()
        except IntegrityError:
            s.expire_all()
            if not s.get(OAuthClient,key):raise
        s.commit()
    return JSONResponse({'client_id':key,'client_name':'ChatGPT','redirect_uris':redirects,
        'token_endpoint_auth_method':'none','grant_types':['authorization_code','refresh_token'],
        'response_types':['code']},status_code=201,headers={'Cache-Control':'no-store'})


class AuthorizationInput(BaseModel):
    client_id: str=Field(max_length=64)
    redirect_uri: str=Field(max_length=500)
    response_type: str
    scope: str=Field(default='cmv:read',max_length=100)
    state: str=Field(min_length=1,max_length=2048)
    resource: str
    code_challenge: str
    code_challenge_method: str


def validate_authorization(data,s):
    client=s.get(OAuthClient,data.client_id)
    if not client or data.redirect_uri not in client.redirects:
        raise HTTPException(400,'Unregistered OAuth client or redirect URI')
    scopes=set(data.scope.split())
    if data.response_type!='code' or not scopes<=SCOPES or 'cmv:read' not in scopes:
        raise HTTPException(400,'Unsupported response type or scopes')
    if (data.resource!=resource() or data.code_challenge_method!='S256'
        or not re.fullmatch(r'[A-Za-z0-9_-]{43}',data.code_challenge)):
        raise HTTPException(400,'Exact resource and S256 PKCE challenge required')
    return ' '.join(sorted(scopes))


@router.get('/oauth/authorize',response_class=HTMLResponse)
def consent_page(request:Request,s:Session=Depends(db)):
    if len(request.query_params.multi_items())!=len(request.query_params):
        raise HTTPException(400,'Duplicate authorization parameter')
    try:data=AuthorizationInput.model_validate(dict(request.query_params))
    except ValueError:raise HTTPException(400,'Invalid authorization request')
    validate_authorization(data,s)
    return HTMLResponse((Path(__file__).parent/'oauth.html').read_text(),headers={
        'Cache-Control':'no-store','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; form-action 'self'",
        'Referrer-Policy':'no-referrer','X-Frame-Options':'DENY'})


@router.get('/oauth-ui.js')
def oauth_script():
    from fastapi.responses import FileResponse
    return FileResponse(Path(__file__).parent/'oauth_ui.js',media_type='application/javascript',headers={'Cache-Control':'no-store'})


@router.post('/oauth/authorize')
def consent(data:AuthorizationInput,request:Request,u:AuthContext=Depends(current),s:Session=Depends(db)):
    scope=validate_authorization(data,s)
    user=s.get(User,u.user_id)
    # Recheck underlying assistant access, including custodian exclusion.
    authorize_account(assistant_request(False),s,user,s.get(LoginSession,u.session_hash).mfa_verified)
    code=secrets.token_urlsafe(48)
    s.add(OAuthCode(digest=sha(code),client_id=data.client_id,user_id=u.user_id,
        redirect_uri=data.redirect_uri,challenge=data.code_challenge,resource=data.resource,
        scope=scope,credential_version=sha(user.password_hash),
        mfa_verified=s.get(LoginSession,u.session_hash).mfa_verified,
        expires_at=now()+timedelta(minutes=5)))
    audit(s,u,'oauth_authorize','oauth_client',data.client_id[:36],None,None,
          {'client':'ChatGPT','scope':scope},'User approved private ChatGPT connection')
    s.commit()
    return JSONResponse({'redirect_url':data.redirect_uri+'?'+urlencode({
        'code':code,'state':data.state,'iss':origin()})},headers={'Cache-Control':'no-store'})


def assistant_request(writing):
    # Reuse the exact same current-account and clinical-write policy as the
    # browser assistant routes. Bearer auth never skips or edits that policy.
    return Request({'type':'http','method':'POST' if writing else 'GET',
        'scheme':'https','server':('localhost',443),'path':'/api/assistant/mcp',
        'headers':[],'query_string':b''})


def grant_actor(s,grant,writing=False):
    if not grant or grant.revoked or expired(grant.expires_at):raise token_error()
    user=s.get(User,grant.user_id)
    if not user or not user.active or not secrets.compare_digest(sha(user.password_hash),grant.credential_version):
        raise token_error()
    return authorize_account(assistant_request(writing),s,user,grant.mfa_verified)


def issue_tokens(s,grant):
    access=secrets.token_urlsafe(48);refresh=secrets.token_urlsafe(64)
    for raw,kind,seconds in [(access,'access',ACCESS_SECONDS),(refresh,'refresh',30*86400)]:
        s.add(OAuthToken(digest=sha(raw),grant_id=grant.id,kind=kind,
            expires_at=min(now()+timedelta(seconds=seconds),grant.expires_at.replace(tzinfo=UTC))))
    return {'access_token':access,'token_type':'Bearer','expires_in':ACCESS_SECONDS,
            'refresh_token':refresh,'scope':grant.scope}


async def form_data(request):
    if request.headers.get('content-type','').split(';')[0]!='application/x-www-form-urlencoded':
        raise HTTPException(415,'Form-encoded OAuth request required')
    raw=await request.body()
    if len(raw)>8192:raise HTTPException(413,'OAuth request too large')
    try:parsed=parse_qs(raw.decode(),keep_blank_values=True)
    except UnicodeError:raise HTTPException(400,'Invalid OAuth encoding')
    if any(len(v)!=1 for v in parsed.values()):raise HTTPException(400,'Duplicate OAuth parameter')
    return {k:v[0] for k,v in parsed.items()}


@router.post('/oauth/token')
async def token_endpoint(request:Request,s:Session=Depends(db)):
    data=await form_data(request)
    if data.get('resource')!=resource():return oauth_error('invalid_target')
    if not s.get(OAuthClient,data.get('client_id','')):return oauth_error('invalid_client')
    if data.get('grant_type')=='authorization_code':
        row=s.get(OAuthCode,sha(data.get('code','')))
        verifier=data.get('code_verifier','')
        challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
        if (not row or row.consumed or expired(row.expires_at) or row.client_id!=data['client_id']
            or row.redirect_uri!=data.get('redirect_uri') or row.resource!=data['resource']
            or not re.fullmatch(r'[A-Za-z0-9._~-]{43,128}',verifier)
            or not secrets.compare_digest(row.challenge,challenge)):
            return oauth_error()
        # Conditional consume prevents concurrent code redemption across workers.
        consumed=s.execute(update(OAuthCode).where(OAuthCode.digest==row.digest,
            OAuthCode.consumed.is_(False)).values(consumed=True))
        if consumed.rowcount!=1:s.rollback();return oauth_error()
        grant=OAuthGrant(id=uid(),user_id=row.user_id,client_id=row.client_id,
            resource=row.resource,scope=row.scope,credential_version=row.credential_version,
            mfa_verified=row.mfa_verified,expires_at=now()+timedelta(days=90),revoked=False)
        try:grant_actor(s,grant)
        except HTTPException:s.rollback();return oauth_error()
        s.add(grant);s.flush()
    elif data.get('grant_type')=='refresh_token':
        token=s.get(OAuthToken,sha(data.get('refresh_token','')))
        if not token or token.kind!='refresh' or expired(token.expires_at):return oauth_error()
        grant=s.scalar(select(OAuthGrant).where(OAuthGrant.id==token.grant_id).with_for_update())
        if not grant or grant.client_id!=data['client_id'] or grant.resource!=data['resource']:return oauth_error()
        try:grant_actor(s,grant)
        except HTTPException:return oauth_error()
        consumed=s.execute(update(OAuthToken).where(OAuthToken.digest==token.digest,
            OAuthToken.consumed.is_(False)).values(consumed=True))
        if consumed.rowcount!=1:
            grant.revoked=True;s.commit();return oauth_error()
        requested=data.get('scope')
        if requested is not None and set(requested.split())!=set(grant.scope.split()):
            s.rollback();return oauth_error('invalid_scope')
    else:return oauth_error('unsupported_grant_type')
    result=issue_tokens(s,grant);s.commit()
    return JSONResponse(result,headers={'Cache-Control':'no-store','Pragma':'no-cache'})


@router.post('/oauth/revoke')
async def revoke_endpoint(request:Request,s:Session=Depends(db)):
    data=await form_data(request)
    token=s.get(OAuthToken,sha(data.get('token','')))
    if token:
        grant=s.get(OAuthGrant,token.grant_id)
        if grant and grant.client_id==data.get('client_id'):
            grant.revoked=True;s.commit()
    return JSONResponse({},headers={'Cache-Control':'no-store'})


def bearer_actor(request,s,writing=False):
    header=request.headers.get('authorization','')
    if not header.startswith('Bearer ') or len(header)>512:raise token_error()
    token=s.get(OAuthToken,sha(header[7:]))
    if not token or token.kind!='access' or token.consumed or expired(token.expires_at):raise token_error()
    grant=s.get(OAuthGrant,token.grant_id)
    actor=grant_actor(s,grant,writing)
    if grant.resource!=resource():raise token_error()
    if not ({'cmv:read','cmv:write'} if writing else {'cmv:read'})<=set(grant.scope.split()):
        raise HTTPException(403,'OAuth scope insufficient',headers={'WWW-Authenticate':
            'Bearer error="insufficient_scope", scope="cmv:read cmv:write"'})
    return actor,grant


@router.get('/api/oauth/connections')
def list_connections(u:AuthContext=Depends(current),s:Session=Depends(db)):
    return [{'id':g.id,'client':'ChatGPT','scope':g.scope,'expires_at':g.expires_at,'revoked':g.revoked}
        for g in s.scalars(select(OAuthGrant).where(OAuthGrant.user_id==u.user_id))]


@router.delete('/api/oauth/connections/{grant_id}')
def revoke_connection(grant_id:str,u:AuthContext=Depends(current),s:Session=Depends(db)):
    grant=s.get(OAuthGrant,grant_id)
    if not grant or grant.user_id!=u.user_id:raise HTTPException(404,'Connection not found')
    grant.revoked=True
    audit(s,u,'oauth_revoke','oauth_grant',grant.id,None,None,None,'User revoked ChatGPT connection')
    s.commit();return {'revoked':True}
