"""NIMS transplant registry foundation. For staging/UAT only pending validation."""
import hashlib
import os
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from fastapi import FastAPI, Depends, HTTPException, Response, Request
from fastapi.responses import FileResponse,JSONResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import create_engine, String, Integer, DateTime, ForeignKey, Date, JSON, Text, select, func, URL, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
import pyotp
from .clinical_gate import startup_deficiencies, runtime_startup_deficiencies, backup_fresh, restore_verified, metadata_fingerprint
from .build_identity import build_fingerprint
from .workspace_policy import enabled as team_workspace, password_only, clinical_path as clinical_workspace_path

DATABASE_URL=os.getenv('DATABASE_URL','')
if not DATABASE_URL and os.getenv('DB_HOST'):
    DATABASE_URL=URL.create('postgresql+psycopg',username=os.getenv('DB_USER','nims_ecrf'),password=os.environ['POSTGRES_PASSWORD'],host=os.getenv('DB_HOST'),port=5432,database=os.getenv('DB_NAME','nims_ecrf'))
if not DATABASE_URL: DATABASE_URL='sqlite:///./local_uat.sqlite3'
COOKIE_SECURE=os.getenv('COOKIE_SECURE','true').lower()=='true'
SESSION_HOURS=int(os.getenv('SESSION_HOURS','12'))
SESSION_IDLE_SECONDS=30*60
ENGINE=create_engine(DATABASE_URL, pool_pre_ping=True, connect_args={'check_same_thread': False} if str(DATABASE_URL).startswith('sqlite:') else {})
SessionLocal=sessionmaker(ENGINE, expire_on_commit=False)
PH=PasswordHasher(time_cost=3,memory_cost=65536,parallelism=2)
UTC=timezone.utc

def now(): return datetime.now(UTC)
def uid(): return str(uuid.uuid4())
def sha(x:str): return hashlib.sha256(x.encode()).hexdigest()

class Base(DeclarativeBase): pass
class User(Base):
    __tablename__='users'
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    username: Mapped[str]=mapped_column(String(100),unique=True,nullable=False)
    display_name: Mapped[str]=mapped_column(String(150),nullable=False)
    role: Mapped[str]=mapped_column(String(40),nullable=False)
    pi_authorized: Mapped[bool]=mapped_column(default=False,nullable=False)
    password_hash: Mapped[str]=mapped_column(Text,nullable=False)
    active: Mapped[bool]=mapped_column(default=True,nullable=False)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class LoginSession(Base):
    __tablename__='sessions'
    token_hash: Mapped[str]=mapped_column(String(64),primary_key=True)
    user_id: Mapped[str]=mapped_column(ForeignKey('users.id'),index=True)
    csrf_hash: Mapped[str]=mapped_column(String(64),nullable=False)
    expires_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    mfa_verified: Mapped[bool]=mapped_column(default=False,nullable=False)
class Patient(Base):
    __tablename__='patients'
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    cr_number: Mapped[str]=mapped_column(String(100),unique=True,index=True,nullable=False)
    name: Mapped[str]=mapped_column(String(250),nullable=False)
    study_id: Mapped[str|None]=mapped_column(String(100),unique=True,nullable=True)
    transplant_date: Mapped[date|None]=mapped_column(Date,nullable=True)
    created_by: Mapped[str]=mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    revision: Mapped[int]=mapped_column(Integer,default=1,nullable=False)
class Entry(Base):
    __tablename__='entries'
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    patient_id: Mapped[str]=mapped_column(ForeignKey('patients.id'),index=True,nullable=False)
    kind: Mapped[str]=mapped_column(String(30),nullable=False,index=True)
    occurred_on: Mapped[date]=mapped_column(Date,nullable=False)
    payload: Mapped[dict[str,Any]]=mapped_column(JSON,nullable=False)
    revision: Mapped[int]=mapped_column(Integer,default=1,nullable=False)
    created_by: Mapped[str]=mapped_column(ForeignKey('users.id'),nullable=False)
    updated_by: Mapped[str]=mapped_column(ForeignKey('users.id'),nullable=False)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class Audit(Base):
    __tablename__='audit_events'
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    patient_id: Mapped[str|None]=mapped_column(String(36),index=True)
    actor_id: Mapped[str]=mapped_column(ForeignKey('users.id'),nullable=False)
    action: Mapped[str]=mapped_column(String(40),nullable=False)
    entity_type: Mapped[str]=mapped_column(String(30),nullable=False)
    entity_id: Mapped[str]=mapped_column(String(36),nullable=False)
    old_record: Mapped[dict|None]=mapped_column(JSON)
    new_record: Mapped[dict|None]=mapped_column(JSON)
    reason: Mapped[str]=mapped_column(Text,nullable=False)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,nullable=False)

class EntryDraft(Base):
    """Autosaved working copy. Not a submitted or verified study record."""
    __tablename__='entry_drafts'
    __table_args__=(UniqueConstraint('user_id','patient_id','kind'),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    user_id: Mapped[str]=mapped_column(ForeignKey('users.id'),index=True,nullable=False)
    patient_id: Mapped[str]=mapped_column(ForeignKey('patients.id'),index=True,nullable=False)
    kind: Mapped[str]=mapped_column(String(30),nullable=False)
    occurred_on: Mapped[date]=mapped_column(Date,nullable=False)
    payload: Mapped[dict[str,Any]]=mapped_column(JSON,nullable=False)
    revision: Mapped[int]=mapped_column(Integer,default=1,nullable=False)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,nullable=False)

class EntryReview(Base):
    """Staging review history. This is not an immutable regulatory audit trail."""
    __tablename__='entry_reviews'
    __table_args__=(UniqueConstraint('entry_id','entry_revision'),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    entry_id: Mapped[str]=mapped_column(ForeignKey('entries.id'),index=True,nullable=False)
    entry_revision: Mapped[int]=mapped_column(Integer,nullable=False)
    decision: Mapped[str]=mapped_column(String(30),nullable=False)
    reason: Mapped[str]=mapped_column(Text,nullable=False)
    reviewer_id: Mapped[str]=mapped_column(ForeignKey('users.id'),nullable=False)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,nullable=False)

# Audit-backed archival avoids altering the signed clinical schema. The person
# and attribution history remain intact; active workspace lists exclude the
# archived record and no new clinical entry may be attached to it.
ARCHIVE_ACTION='archive_patient'

def active_patient_filter():
    return ~Patient.id.in_(select(Audit.entity_id).where(
        Audit.entity_type=='patient',Audit.action==ARCHIVE_ACTION))

def patient_archived(s:Session,patient_id:str)->bool:
    return s.scalar(select(Audit.id).where(
        Audit.entity_type=='patient',Audit.action==ARCHIVE_ACTION,
        Audit.entity_id==patient_id).limit(1)) is not None

# Register structured study models before the staging metadata is built.
from .trial_models import TrialSubject, PCRRecord, DrugLot, DrugAuthorization, DrugDispense, DrugReturn, UserInvitation, LoginThrottle, UserTotp, StaffAccess, TrialEligibility, TrialCRFEntry, TrialCRFDraft, TrialCRFReview, TrialScreeningMeta, RandomizationPlan, RandomizationSlot

app=FastAPI(title='NIMS Transplant Registry — staging foundation',docs_url=None,redoc_url=None)
# Fail closed if someone enables real-patient mode without the independent go-live
# attestation and authenticated/staff MFA configuration. Production schema must
# be installed by an independently reviewed migration, never by create_all.
CLINICAL_MODE=os.getenv('CLINICAL_DATA_ENABLED','false').lower()=='true'
if CLINICAL_MODE:
    # A clinic sign-off must be tied to the exact approved file; DB and recovery
    # must be independently provisioned before this process may start.
    missing=runtime_startup_deficiencies()
    if missing:
        raise RuntimeError('Clinical startup BLOCKED: '+', '.join(missing))
    from sqlalchemy import inspect, text as sql_text
    try:
        actual=set(inspect(ENGINE).get_table_names())
        absent=set(Base.metadata.tables)-actual
        if absent:
            raise RuntimeError('Clinical schema incomplete: reviewed migrations required')
        with ENGINE.connect() as check_conn:
            database_identity=check_conn.execute(sql_text(
                "SELECT current_database(), current_user"
            )).one()
            if tuple(database_identity)!=("nims_cmv_clinical","nims_clinical_app"):
                raise RuntimeError('Clinical database identity is not the approved restricted target')
            if check_conn.execute(sql_text(
                "SELECT has_schema_privilege(current_user, 'public', 'CREATE')"
            )).scalar():
                raise RuntimeError('Clinical application database role has unsafe schema creation rights')
            revision=check_conn.execute(sql_text(
                "SELECT fingerprint FROM clinical_schema_baseline WHERE revision='initial-2026-11'"
            )).scalar_one_or_none()
            if revision!=metadata_fingerprint(Base.metadata):
                raise RuntimeError('Clinical schema version/fingerprint mismatch; reviewed migration required')
    except SQLAlchemyError as error:
        raise RuntimeError('Clinical database/permissions could not be verified') from error
elif os.getenv('CLINICAL_SCHEMA_BOOTSTRAP','false').lower()=='true':
    # One-time operator CLI must verify a fresh, dedicated DB before creating
    # the initial schema. The API never performs this action automatically.
    pass
else:
    Base.metadata.create_all(bind=ENGINE)  # Synthetic staging only
    # Additive compatibility migration for existing staging accounts only.
    # Clinical schemas are provisioned explicitly and never altered by the API.
    from sqlalchemy import inspect, text as sql_text
    with ENGINE.begin() as conn:
        for table,column in [('users','pi_authorized'),('sessions','mfa_verified')]:
            if column not in {c['name'] for c in inspect(conn).get_columns(table)}:
                conn.execute(sql_text(f'ALTER TABLE {table} ADD COLUMN {column} BOOLEAN NOT NULL DEFAULT false'))

ROLES={'pi','admin','consultant','pg','scientist','nurse','technician','microbiology','pharmacy','monitor','randomization_custodian'}

@app.middleware('http')
async def account_migration_guard(request,call_next):
    path=request.url.path
    if (not CLINICAL_MODE and request.method not in {'GET','HEAD','OPTIONS'} and
        (path=='/api/users' or path.startswith('/api/trial/staff/')) and
        Path('/run/operations/account-migration.lock').is_file()):
        return JSONResponse(status_code=503,content={'detail':
            'Clinical account migration in progress. Account changes resume after clinical activation.'},
            headers={'Cache-Control':'no-store, private'})
    response=await call_next(request)
    if path.startswith('/api/') or path=='/operations':response.headers['Cache-Control']='no-store, private'
    return response
WRITE_ROLES={
 'admission':{'pi','consultant','pg','scientist','nurse'},
 'visit':{'pi','consultant','pg','scientist','nurse'},
 'lab':{'pi','consultant','pg','scientist','nurse','technician','microbiology'},
 'infection':{'pi','consultant','pg','scientist','nurse','microbiology'},
 'medication':{'pi','consultant','pg','scientist','nurse','pharmacy'},
 'transplant':{'pi','consultant','pg','scientist'},
 'safety':{'pi','consultant','scientist','nurse'},
 'pharmacy':{'pi','scientist','pharmacy'},
 'rejection':{'pi','consultant','pg','scientist'},
}

def db():
    with SessionLocal() as s: yield s

def as_dict(p):
    return jsonable_encoder({c.name:getattr(p,c.name) for c in p.__table__.columns})

class AuthContext(BaseModel):
    user_id: str
    role: str
    name: str
    csrf_hash: str
    pi_authorized: bool=False
    session_hash: str=''
    workspace_full_access: bool=False
    model_config=ConfigDict(frozen=True)

def current(request:Request,s:Session=Depends(db)) -> AuthContext:
    token=request.cookies.get('nims_session')
    if not token: raise HTTPException(401,'Login required')
    active=s.get(LoginSession,sha(token))
    if not active or active.expires_at.replace(tzinfo=UTC)<now(): raise HTTPException(401,'Session expired')
    user=s.get(User,active.user_id)
    context=authorize_account(request,s,user,active.mfa_verified)
    if request.method not in ('GET','HEAD','OPTIONS'):
        supplied=request.headers.get('x-csrf-token','')
        if not supplied or not secrets.compare_digest(sha(supplied),active.csrf_hash):
            raise HTTPException(403,'Missing or invalid CSRF token')
    return context.model_copy(update={'csrf_hash':active.csrf_hash,'session_hash':active.token_hash})

def authorize_account(request:Request,s:Session,user:User,mfa_verified:bool) -> AuthContext:
    if not user or not user.active: raise HTTPException(401,'Account disabled')
    if os.getenv('MFA_REQUIRED','false').lower()=='true' and not mfa_verified:
        allowed={'/api/me','/api/session','/api/logout','/api/trial/staff/mfa-setup','/api/trial/staff/mfa-confirm'}
        if request.url.path not in allowed:
            raise HTTPException(403,'Complete your authenticator setup to access the clinical workspace')
    access=s.get(StaffAccess,user.id)
    if access and access.expires_at.replace(tzinfo=UTC)<=now():
        raise HTTPException(403,'Account access expired; contact the study administrator')
    if CLINICAL_MODE and user.role not in {'admin','pi'} and not access:
        raise HTTPException(403,'Named staff authorization required')
    # Freeze clinical writes when offsite backup or the monthly restore proof is
    # stale; account sign-in and read-only review remain available.
    clinical_path=request.url.path
    if (CLINICAL_MODE and request.method not in ('GET','HEAD','OPTIONS')
        and (clinical_path.startswith(('/api/patients','/api/entries',
                                      '/api/trial/screening','/api/trial/subjects',
                                      '/api/trial/pcr','/api/trial/pharmacy',
                                      '/api/trial/crf','/api/trial/randomization/subjects',
                                      '/api/assistant')))):
        if not backup_fresh() or not restore_verified():
            raise HTTPException(503,'Clinical write temporarily paused: backup or restore verification overdue')

    shared=team_workspace() and clinical_workspace_path(request.url.path)
    if shared and request.method not in ('GET','HEAD','OPTIONS') and not s.scalar(
        select(Audit.id).where(Audit.action=='owner_fresh_start_reset').limit(1)):
        raise HTTPException(503,'The requested fresh start is being prepared; sign in again when setup completes')
    if user.role=='randomization_custodian' and not shared and not (
        request.url.path.startswith('/api/trial/randomization/')
        or request.url.path in {'/api/me','/api/logout','/api/system/mode',
          '/api/trial/staff/change-password','/api/trial/staff/mfa-setup',
          '/api/trial/staff/mfa-confirm'}
    ):
        raise HTTPException(403,'Allocation custodian has no patient/eligibility or treatment record access')
    return AuthContext(user_id=user.id,role='pi' if shared else user.role,
                       name=user.display_name,csrf_hash='',
                       pi_authorized=user.pi_authorized,workspace_full_access=shared)

def audit(s:Session,u:AuthContext,action:str,entity_type:str,entity_id:str,patient_id:str|None,old:dict|None,new:dict|None,reason:str):
    s.add(Audit(actor_id=u.user_id,action=action,entity_type=entity_type,entity_id=entity_id,patient_id=patient_id,old_record=jsonable_encoder(old),new_record=jsonable_encoder(new),reason=reason))

def permission(u,kind):
    if u.role not in (WRITE_ROLES.get(kind) or set()) and u.role!='admin':
        raise HTTPException(403,'Insufficient delegated role permission')

REVIEW_ROLES={'pi','consultant','scientist','monitor'}
def review_permission(u):
    if u.workspace_full_access:return
    if u.role not in REVIEW_ROLES and not u.pi_authorized: raise HTTPException(403,'Reviewer role required')

def review_state(s:Session,e:Entry):
    r=s.scalar(select(EntryReview).where(EntryReview.entry_id==e.id,EntryReview.entry_revision==e.revision))
    return r.decision if r else 'pending'

class LoginInput(BaseModel):
    username:str=Field(min_length=2,max_length=100)
    password:str=Field(min_length=1,max_length=200)
    otp:str|None=Field(default=None,min_length=6,max_length=6,pattern=r'^[0-9]{6}$')

@app.get('/')
def home():
    # A stale script must never retain a clinical/staging permission UI across
    # deployments. No patient data is cached in a shared or private browser.
    return FileResponse(Path(__file__).parent/'ui.html',
                        headers={'Cache-Control':'no-store, max-age=0',
                                 'Pragma':'no-cache'})
@app.get('/study_ui.js')
def study_script():
    return FileResponse(Path(__file__).parent/'study_ui.js',
                        media_type='application/javascript',
                        headers={'Cache-Control':'no-store, max-age=0',
                                 'Pragma':'no-cache'})

@app.get('/patient_workspace.js')
def patient_workspace_script():
    return FileResponse(Path(__file__).parent/'patient_workspace.js',
                        media_type='application/javascript',
                        headers={'Cache-Control':'no-store, max-age=0',
                                 'Pragma':'no-cache'})

@app.get('/nims-logo.svg', include_in_schema=False)
def institution_logo():
    # Locally hosted institutional emblem supplied by the project owner.
    return FileResponse(Path(__file__).parent/'nims_logo.svg',
                        media_type='image/svg+xml',
                        headers={'Cache-Control':'public, max-age=86400'})


@app.get('/healthz')
def health():
    from .operations import SHA
    from .operations import read_host_status
    commit=os.getenv('APP_COMMIT','')
    return {'ok':True,'service':'clinical' if CLINICAL_MODE else 'staging',
            'app_commit':commit if SHA.fullmatch(commit) else None,
            'build_fingerprint':build_fingerprint(),
            'clinical_transition':read_host_status().get('clinical_transition','unknown'),
            'clinical_failed_step':read_host_status().get('clinical_failed_step','unknown')}
@app.get('/readyz')
def ready():
    try:
        with ENGINE.connect() as connection:
            connection.execute(select(1))
    except SQLAlchemyError:
        raise HTTPException(503,'Service temporarily unavailable')
    with SessionLocal() as session:
        plan_ready=bool(session.scalar(select(RandomizationPlan.id).where(RandomizationPlan.active.is_(True)).limit(1)))
        fresh=bool(session.scalar(select(Audit.id).where(Audit.action=='owner_fresh_start_reset').limit(1)))
    return {**health(),'database':'reachable',
            'authentication_mode':'username_password' if password_only() else 'standard',
            'shared_clinical_workspace':team_workspace(),
            'randomization_ready':plan_ready,'fresh_start_completed':fresh,
            'clinical_entry_available':bool(CLINICAL_MODE and backup_fresh() and restore_verified() and (not team_workspace() or fresh))}

@app.get('/api/authentication-policy')
def authentication_policy():
    return {'password_only':password_only(),'shared_clinical_workspace':team_workspace()}
@app.get('/api/system/mode')
def system_mode(response:Response,u:AuthContext=Depends(current)):
    # Authenticated per-request current mode; never cache or infer from page URL.
    response.headers['Cache-Control']='no-store, private, max-age=0'
    writable=bool(CLINICAL_MODE and backup_fresh() and restore_verified())
    if team_workspace():
        with SessionLocal() as session:
            writable=writable and bool(session.scalar(select(Audit.id).where(Audit.action=='owner_fresh_start_reset').limit(1)))
    return {'mode':'clinical' if CLINICAL_MODE else 'synthetic',
            'clinical_registration_enabled':writable,
            'institutional_release_required':not CLINICAL_MODE,
            'backup_verified':bool(CLINICAL_MODE and backup_fresh()),
            'restore_verified':bool(CLINICAL_MODE and restore_verified()),
            'message':('Clinical database authorized and operational' if writable else
              'Staging only: real patient identifiers must not be entered' if not CLINICAL_MODE else
              'Clinical write temporarily paused: backup/restore proof is overdue')}
@app.get('/operations')
def operations_page(u:AuthContext=Depends(current)):
    if u.role!='admin': raise HTTPException(403,'System administrator required')
    return FileResponse(Path(__file__).parent/'operations.html',
                        headers={'Cache-Control':'no-store, private, max-age=0'})

@app.get('/api/system/operations')
def operations_status(response:Response,u:AuthContext=Depends(current)):
    if u.role!='admin': raise HTTPException(403,'System administrator required')
    from .operations import read_host_status, SHA
    response.headers['Cache-Control']='no-store, private, max-age=0'
    database='unavailable'
    try:
        with ENGINE.connect() as connection:
            connection.execute(select(1))
        database='reachable'
    except SQLAlchemyError:
        pass
    commit=os.getenv('APP_COMMIT','')
    # Evaluate the current container's configuration, not an unseen clinical
    # deployment. Return reason codes only, never env values, keys or paths.
    clinical_configuration=dict(os.environ,CLINICAL_DATA_ENABLED='true')
    return {
        'checked_at':now().isoformat(),
        'app_commit':commit if SHA.fullmatch(commit) else None,
        'database':database,
        'mode':'clinical' if CLINICAL_MODE else 'synthetic',
        'clinical_registration_enabled':bool(CLINICAL_MODE and backup_fresh() and restore_verified()),
        'current_container_release_deficiencies':startup_deficiencies(clinical_configuration),
        'host':read_host_status(),
        'update_channel':'CI-approved GitHub staging releases',
        'host_command_execution':False,
    }

@app.post('/api/login')
def login(data:LoginInput,response:Response,s:Session=Depends(db)):
    username=data.username.strip().lower()
    throttle=s.get(LoginThrottle,username)
    if throttle and throttle.locked_until and throttle.locked_until.replace(tzinfo=UTC)>now():
        raise HTTPException(429,'Account temporarily locked; contact the study administrator')
    u=s.scalar(select(User).where(User.username==username))
    try:
        password_ok=bool(u and u.active and PH.verify(u.password_hash,data.password))
    except (VerifyMismatchError,VerificationError):
        password_ok=False
    if password_ok:
        access=s.get(StaffAccess,u.id)
        if access and access.expires_at.replace(tzinfo=UTC)<=now():
            raise HTTPException(403,'90-day staff access expired; request renewal')
        if CLINICAL_MODE and u.role not in {'admin','pi'} and not access:
            raise HTTPException(403,'Staff access authorization required')
    mfa=s.get(UserTotp,u.id) if password_ok else None
    otp_ok=bool(password_ok and (password_only() or not mfa or not mfa.enabled or
        (data.otp and pyotp.TOTP(mfa.secret).verify(data.otp,valid_window=1))))
    setup_required=bool(password_ok and os.getenv('MFA_REQUIRED','false').lower()=='true' and (not mfa or not mfa.enabled))
    if not password_ok or not otp_ok:
        # Per-username persistent lockout. Deploy IP-based rate limiting at the
        # TLS reverse proxy as a separate production control.
        if u:
            if not throttle:
                throttle=LoginThrottle(username=username,failures=0)
                s.add(throttle)
            throttle.failures+=1
            if throttle.failures>=5:
                throttle.locked_until=now()+timedelta(minutes=15)
            s.commit()
        raise HTTPException(401,'Invalid credentials or authenticator code')
    if throttle and not setup_required:
        throttle.failures=0
        throttle.locked_until=None
    token=secrets.token_urlsafe(48);csrf=sha('nims-csrf:'+token)
    seconds=600 if setup_required else SESSION_IDLE_SECONDS
    expiry=now()+timedelta(seconds=seconds)
    s.add(LoginSession(token_hash=sha(token),user_id=u.id,csrf_hash=sha(csrf),expires_at=expiry,
                       mfa_verified=bool(mfa and mfa.enabled and otp_ok)))
    s.commit()
    response.set_cookie('nims_session',token,max_age=600 if setup_required else SESSION_HOURS*3600,
        httponly=True,secure=COOKIE_SECURE,samesite='strict',path='/')
    return {'username':u.username,'role':u.role,'display_name':u.display_name,
            'csrf_token':csrf,'mfa_enabled':bool(mfa and mfa.enabled and not password_only()),
            'mfa_setup_required':setup_required,'pi_authorized':u.pi_authorized,
            'workspace_full_access':team_workspace(),'password_only':password_only(),
            'idle_timeout_seconds':SESSION_IDLE_SECONDS,'expires_at':expiry}

@app.get('/api/session')
def recover_session(request:Request,response:Response,u:AuthContext=Depends(current),s:Session=Depends(db)):
    """Recover memory-only CSRF/UI state using the existing HttpOnly cookie.

    Reading or refreshing this endpoint does not extend the idle deadline.
    The deterministic token is bound to the secret session cookie and remains
    stable across tabs. Upgrade legacy random-CSRF sessions once on refresh.
    """
    active=s.get(LoginSession,u.session_hash)
    user=s.get(User,u.user_id)
    csrf=sha('nims-csrf:'+request.cookies['nims_session'])
    if not secrets.compare_digest(active.csrf_hash,sha(csrf)):
        active.csrf_hash=sha(csrf);s.commit()
    response.headers['Cache-Control']='no-store'
    setup=bool(os.getenv('MFA_REQUIRED','false').lower()=='true' and not active.mfa_verified)
    return {'user_id':user.id,'username':user.username,'role':user.role,
            'display_name':user.display_name,'csrf_token':csrf,
            'pi_authorized':user.pi_authorized,'workspace_full_access':team_workspace(),
            'password_only':password_only(),'mfa_setup_required':setup,
            'idle_timeout_seconds':SESSION_IDLE_SECONDS,'expires_at':active.expires_at.replace(tzinfo=UTC)}

@app.post('/api/session/activity')
def session_activity(request:Request,response:Response,u:AuthContext=Depends(current),s:Session=Depends(db)):
    """Only foreground user activity renews a valid, CSRF-checked session."""
    active=s.get(LoginSession,u.session_hash)
    active.expires_at=now()+timedelta(seconds=SESSION_IDLE_SECONDS)
    s.commit()
    response.set_cookie('nims_session',request.cookies['nims_session'],max_age=SESSION_HOURS*3600,
        httponly=True,secure=COOKIE_SECURE,samesite='strict',path='/')
    response.headers['Cache-Control']='no-store'
    return {'expires_at':active.expires_at.replace(tzinfo=UTC)}
@app.get('/api/me')
def me(u:AuthContext=Depends(current)):
    return {'user_id':u.user_id,'role':u.role,'display_name':u.name,'pi_authorized':u.pi_authorized}
@app.post('/api/logout')
def logout(request:Request,response:Response,u:AuthContext=Depends(current),s:Session=Depends(db)):
    token=request.cookies.get('nims_session')
    if token: s.query(LoginSession).filter(LoginSession.token_hash==sha(token)).delete();s.commit()
    response.delete_cookie('nims_session',path='/')
    return {'ok':True}
class NewUser(BaseModel):
    username:str=Field(min_length=3,max_length=100)
    display_name:str=Field(min_length=3,max_length=150)
    role:str
    password:str=Field(min_length=14,max_length=200)
@app.post('/api/users')
def create_user(data:NewUser,u:AuthContext=Depends(current),s:Session=Depends(db)):
    if u.role not in ('admin','pi'): raise HTTPException(403)
    if data.role not in ROLES: raise HTTPException(422,'Unknown role')
    if data.role in {'pi','admin','randomization_custodian'} and u.role!='admin':
        raise HTTPException(403,'Only administrator can delegate privileged access')
    if CLINICAL_MODE:
        raise HTTPException(403,'Use named invitations rather than administrator-selected credentials')
    obj=User(username=data.username,display_name=data.display_name,role=data.role,password_hash=PH.hash(data.password))
    s.add(obj)
    try: s.commit()
    except IntegrityError: s.rollback();raise HTTPException(409,'Username already used')
    return {'id':obj.id,'username':obj.username,'role':obj.role}
class PatientIn(BaseModel):
    cr_number:str=Field(min_length=1,max_length=100)
    name:str=Field(min_length=1,max_length=250)
    study_id:str|None=Field(default=None,max_length=100)
    transplant_date:date|None=None
@app.post('/api/patients')
def create_patient(data:PatientIn,u:AuthContext=Depends(current),s:Session=Depends(db)):
    if u.role not in {'admin','pi','consultant','scientist'}: raise HTTPException(403)
    # Enrollment, not registration, assigns the immutable trial Study ID.
    # Reserve the NCMV numeric namespace in UAT too; old non-trial test
    # identifiers remain readable for backwards-compatible test fixtures.
    if data.study_id and (CLINICAL_MODE or
            ((data.study_id.startswith('NCMV-') and data.study_id[5:].isdigit()) or
             (data.study_id.startswith('NCMV') and data.study_id[4:].isdigit()))):
        raise HTTPException(422,'Study ID is generated automatically only after approved enrollment')
    if not CLINICAL_MODE:
        if not (data.cr_number.upper().startswith('TEST-') and data.name.lower().startswith('synthetic')):
            raise HTTPException(403,'Synthetic-only staging: identifiable patient registration is disabled')
    p=Patient(**data.model_dump(),created_by=u.user_id)
    try:
        s.add(p);s.flush();audit(s,u,'create','patient',p.id,p.id,None,as_dict(p),'Initial registration')
        s.commit()
    except IntegrityError: s.rollback();raise HTTPException(409,'Duplicate CR number or study ID')
    return {'id':p.id,'revision':p.revision}
@app.get('/api/patients')
def patients(q:str='',limit:int=50,u:AuthContext=Depends(current),s:Session=Depends(db)):
    limit=min(max(limit,1),100)
    st=select(Patient).where(active_patient_filter())
    restricted=u.role in {'microbiology','pharmacy','technician','monitor'} and not u.workspace_full_access
    if q.strip():
        if restricted:
            st=st.where(Patient.study_id.ilike('%'+q.strip()+'%'))
        else:
            st=st.where(Patient.name.ilike('%'+q.strip()+'%') |
                Patient.cr_number.ilike('%'+q.strip()+'%') |
                Patient.study_id.ilike('%'+q.strip()+'%') |
                Patient.id.in_(select(TrialSubject.patient_id).where(TrialSubject.screening_code.ilike('%'+q.strip()+'%'))))
    ps=s.scalars(st.order_by(Patient.created_at.desc()).limit(limit)).all()
    return [{'id':p.id,'cr_number':None if restricted else p.cr_number,
             'name':None if restricted else p.name,'study_id':p.study_id,
             'transplant_date':p.transplant_date,'revision':p.revision} for p in ps]
@app.get('/api/patients/{patient_id}')
def patient(patient_id:str,u:AuthContext=Depends(current),s:Session=Depends(db)):
    p=s.get(Patient,patient_id)
    if not p or patient_archived(s,patient_id): raise HTTPException(404)
    es=s.scalars(select(Entry).where(Entry.patient_id==patient_id).order_by(Entry.occurred_on.desc(),Entry.created_at.desc())).all()
    data=as_dict(p)
    if u.role in {'microbiology','pharmacy','technician','monitor'} and not u.workspace_full_access:
        data.pop('name',None);data.pop('cr_number',None)
        # Lab, pharmacy and external monitors never receive unrelated clinical entry payloads.
        permitted={'lab'} if u.role in {'microbiology','technician'} else ({'pharmacy'} if u.role=='pharmacy' else set())
        es=[e for e in es if e.kind in permitted]
    return {'patient':data,'entries':[dict(as_dict(e),review_status=review_state(s,e)) for e in es]}
class EntryIn(BaseModel):
    kind:Literal['admission','visit','lab','infection','medication','transplant','safety','pharmacy','rejection']
    occurred_on:date
    payload:dict[str,Any]
@app.post('/api/patients/{patient_id}/entries')
def new_entry(patient_id:str,data:EntryIn,u:AuthContext=Depends(current),s:Session=Depends(db)):
    permission(u,data.kind)
    if not s.get(Patient,patient_id): raise HTTPException(404)
    if patient_archived(s,patient_id): raise HTTPException(409,'Registry record archived')
    if len(str(data.payload))>20000: raise HTTPException(413,'Record too large; use approved structured fields')
    e=Entry(patient_id=patient_id,**data.model_dump(),created_by=u.user_id,updated_by=u.user_id)
    s.add(e);s.flush();audit(s,u,'create',e.kind,e.id,patient_id,None,as_dict(e),'Initial entry');s.commit()
    return {'id':e.id,'revision':1}
class EntryEdit(BaseModel):
    expected_revision:int=Field(ge=1)
    payload:dict[str,Any]
    occurred_on:date
    reason:str=Field(min_length=5,max_length=500)
@app.put('/api/entries/{entry_id}')
def edit_entry(entry_id:str,data:EntryEdit,u:AuthContext=Depends(current),s:Session=Depends(db)):
    e=s.get(Entry,entry_id)
    if not e: raise HTTPException(404)
    if patient_archived(s,e.patient_id): raise HTTPException(409,'Registry record archived')
    permission(u,e.kind)
    if len(str(data.payload))>20000: raise HTTPException(413)
    if e.revision!=data.expected_revision: raise HTTPException(409,'Revision conflict; reload and reconcile')
    old=as_dict(e)
    # Conditional update avoids a concurrent overwrite even if reads race.
    from sqlalchemy import update
    result=s.execute(update(Entry).where(Entry.id==entry_id,Entry.revision==data.expected_revision).values(payload=data.payload,occurred_on=data.occurred_on,updated_by=u.user_id,updated_at=now(),revision=Entry.revision+1))
    if result.rowcount!=1: s.rollback();raise HTTPException(409,'Concurrent edit detected')
    s.flush();s.refresh(e)
    audit(s,u,'update',e.kind,e.id,e.patient_id,old,as_dict(e),data.reason);s.commit()
    return {'id':entry_id,'revision':e.revision}
# Server-held drafts are kept separate from final CRF entries and audit/review queues.
# They are per user/patient/module, with optimistic concurrency for multiple tabs.
DRAFT_KINDS=Literal['admission','visit','lab','infection','medication','transplant','safety','pharmacy','rejection']
class DraftInput(BaseModel):
    occurred_on:date
    payload:dict[str,Any]
    expected_revision:int|None=Field(default=None,ge=1)

def draft_patient(s:Session,patient_id:str,u:AuthContext,kind:str):
    permission(u,kind)
    if not s.get(Patient,patient_id): raise HTTPException(404,'Patient not found')
    if patient_archived(s,patient_id): raise HTTPException(409,'Registry record archived')

@app.get('/api/patients/{patient_id}/drafts/{kind}')
def read_draft(patient_id:str,kind:DRAFT_KINDS,u:AuthContext=Depends(current),s:Session=Depends(db)):
    draft_patient(s,patient_id,u,kind)
    d=s.scalar(select(EntryDraft).where(EntryDraft.patient_id==patient_id,
        EntryDraft.user_id==u.user_id,EntryDraft.kind==kind))
    return {'draft': as_dict(d) if d else None}

@app.put('/api/patients/{patient_id}/drafts/{kind}')
def save_draft(patient_id:str,kind:DRAFT_KINDS,data:DraftInput,
               u:AuthContext=Depends(current),s:Session=Depends(db)):
    draft_patient(s,patient_id,u,kind)
    if len(str(data.payload))>20000: raise HTTPException(413,'Draft too large')
    d=s.scalar(select(EntryDraft).where(EntryDraft.patient_id==patient_id,
        EntryDraft.user_id==u.user_id,EntryDraft.kind==kind))
    if d is None:
        if data.expected_revision is not None:
            raise HTTPException(409,'Draft was removed or replaced; reload')
        d=EntryDraft(user_id=u.user_id,patient_id=patient_id,kind=kind,
                     occurred_on=data.occurred_on,payload=data.payload)
        s.add(d)
        try: s.commit()
        except IntegrityError: s.rollback();raise HTTPException(409,'Draft created elsewhere; reload')
        return {'id':d.id,'revision':d.revision,'updated_at':d.updated_at}
    if data.expected_revision!=d.revision:
        raise HTTPException(409,'Draft changed in another tab; reload to reconcile')
    from sqlalchemy import update
    updated=s.execute(update(EntryDraft).where(EntryDraft.id==d.id,
        EntryDraft.revision==data.expected_revision).values(
        occurred_on=data.occurred_on,payload=data.payload,
        revision=EntryDraft.revision+1,updated_at=now()))
    if updated.rowcount!=1:
        s.rollback();raise HTTPException(409,'Concurrent draft edit; reload')
    s.commit()
    s.refresh(d)
    return {'id':d.id,'revision':d.revision,'updated_at':d.updated_at}

@app.delete('/api/patients/{patient_id}/drafts/{kind}')
def delete_draft(patient_id:str,kind:DRAFT_KINDS,expected_revision:int,
                 u:AuthContext=Depends(current),s:Session=Depends(db)):
    draft_patient(s,patient_id,u,kind)
    from sqlalchemy import delete
    result=s.execute(delete(EntryDraft).where(EntryDraft.patient_id==patient_id,
        EntryDraft.user_id==u.user_id,EntryDraft.kind==kind,
        EntryDraft.revision==expected_revision))
    if result.rowcount!=1:
        s.rollback();raise HTTPException(409,'Draft revision changed; not deleted')
    s.commit()
    return {'ok':True}

@app.get('/api/patients/{patient_id}/audit')
def audit_history(patient_id:str,u:AuthContext=Depends(current),s:Session=Depends(db)):
    if u.role not in {'admin','pi','consultant','monitor','scientist'}: raise HTTPException(403)
    rows=s.scalars(select(Audit).where(Audit.patient_id==patient_id).order_by(Audit.created_at.desc()).limit(500)).all()
    if u.role=='monitor':
        # No identity-bearing old/new JSON snapshots in the blinded monitor view.
        return [{'id':x.id,'actor_id':x.actor_id,'action':x.action,
                 'entity_type':x.entity_type,'created_at':x.created_at}
                for x in rows]
    return [as_dict(x) for x in rows]

@app.get('/api/dashboard')
def dashboard(u:AuthContext=Depends(current),s:Session=Depends(db)):
    # A single left join avoids per-entry review queries as the study grows.
    from sqlalchemy import and_
    rows=s.execute(select(Entry.kind,Entry.occurred_on,EntryReview.decision)
        .join(Patient,Entry.patient_id==Patient.id)
        .outerjoin(EntryReview,and_(EntryReview.entry_id==Entry.id,
                                   EntryReview.entry_revision==Entry.revision))
        .where(active_patient_filter())).all()
    counts={'pending':0,'verified':0,'needs_correction':0}
    by_kind={}; monthly={}
    for kind,occurred_on,decision in rows:
        counts[decision or 'pending']+=1
        by_kind[kind]=by_kind.get(kind,0)+1
        month=occurred_on.strftime('%Y-%m')
        monthly[month]=monthly.get(month,0)+1
    return {'patients':s.scalar(select(func.count(Patient.id)).where(active_patient_filter())),
            'study_ids_assigned':s.scalar(select(func.count(Patient.id)).where(Patient.study_id.is_not(None),active_patient_filter())),
            'entries':len(rows),'review':counts,'by_kind':by_kind,
            'monthly_entries':[{'month':m,'count':monthly[m]} for m in sorted(monthly)[-12:]],
            'scope':'clinical study database' if CLINICAL_MODE else 'staging synthetic data only'}

@app.get('/api/review-queue')
def review_queue(u:AuthContext=Depends(current),s:Session=Depends(db)):
    review_permission(u)
    rows=s.execute(select(Entry,Patient).join(Patient,Entry.patient_id==Patient.id)
                   .where(active_patient_filter())
                   .order_by(Entry.updated_at.desc()).limit(200)).all()
    return [{'entry_id':e.id,'patient_id':p.id,'study_id':p.study_id,'cr_number':None if u.role=='monitor' else p.cr_number,
             'kind':e.kind,'occurred_on':e.occurred_on,'revision':e.revision,
             'review_status':review_state(s,e),'payload':e.payload,
             'updated_by':e.updated_by} for e,p in rows]

class ReviewInput(BaseModel):
    expected_revision:int=Field(ge=1)
    decision:Literal['verified','needs_correction']
    reason:str=Field(min_length=5,max_length=500)

@app.post('/api/entries/{entry_id}/review')
def review_entry(entry_id:str,data:ReviewInput,u:AuthContext=Depends(current),s:Session=Depends(db)):
    review_permission(u)
    e=s.get(Entry,entry_id)
    if not e: raise HTTPException(404)
    if patient_archived(s,e.patient_id): raise HTTPException(409,'Registry record archived')
    if e.revision!=data.expected_revision: raise HTTPException(409,'Revision changed; reload before review')
    if u.user_id in (e.created_by,e.updated_by) and not u.workspace_full_access: raise HTTPException(403,'Independent reviewer required')
    if review_state(s,e)!='pending': raise HTTPException(409,'This revision was already reviewed')
    r=EntryReview(entry_id=e.id,entry_revision=e.revision,decision=data.decision,
                  reason=data.reason,reviewer_id=u.user_id)
    s.add(r)
    audit(s,u,'review',e.kind,e.id,e.patient_id,None,
          {'entry_revision':e.revision,'decision':data.decision},data.reason)
    try: s.commit()
    except IntegrityError: s.rollback();raise HTTPException(409,'This revision was already reviewed')
    return {'entry_id':e.id,'revision':e.revision,'review_status':data.decision}

DOSE_TABLE={
    'low':'Withhold protocol tablets; clinician review',
    '10_24':'450 mg twice weekly',
    '25_39':'450 mg every 48 hours',
    '40_59':'450 mg once daily'
}
def cg_dose(age:int,weight_kg:float,creatinine_mg_dl:float,sex_factor:float,arm:int)->dict:
    if not (18<=age<=120 and 20<=weight_kg<=300 and 0.2<=creatinine_mg_dl<=20 and sex_factor in (1.0,0.85) and arm in (450,900)):
        raise ValueError('Invalid inputs')
    crcl=(140-age)*weight_kg/(72*creatinine_mg_dl)*sex_factor
    if crcl<10: regimen=DOSE_TABLE['low']
    elif crcl<25: regimen=DOSE_TABLE['10_24']
    elif crcl<40: regimen=DOSE_TABLE['25_39']
    elif crcl<60: regimen=DOSE_TABLE['40_59']
    else: regimen=f'{arm} mg once daily'
    return {'crcl_ml_min':round(crcl,2),'suggested_regimen':regimen,'source':'NIMS CMV protocol v5.0, 14 August 2026','requires_clinician_confirmation':True,'warning':'Only for research review; never an automatic prescription. Requires validated weight convention and stable creatinine.'}
class DoseInput(BaseModel):
    age:int
    weight_kg:float
    creatinine_mg_dl:float
    sex_for_cg:Literal['male','female']
    nominal_arm:Literal[450,900]
@app.post('/api/dose-preview')
def dose_preview(data:DoseInput,u:AuthContext=Depends(current)):
    try: return cg_dose(data.age,data.weight_kg,data.creatinine_mg_dl,0.85 if data.sex_for_cg=='female' else 1.0,data.nominal_arm)
    except ValueError: raise HTTPException(422,'Invalid calculation inputs')
@app.get('/api/due')
def due(u:AuthContext=Depends(current),s:Session=Depends(db)):
    # Current staging schedule uses the transplant date ONLY as a placeholder.
    # Final protocol worklists must anchor to verified enrollment/randomization date.
    from zoneinfo import ZoneInfo
    today=datetime.now(ZoneInfo('Asia/Kolkata')).date()
    if CLINICAL_MODE:
        # Use the actual approved enrollment-generated PCR schedule. Generic
        # visit entries never imply that a protocol PCR has been completed.
        rows=s.execute(select(PCRRecord,TrialSubject).join(TrialSubject,
            TrialSubject.id==PCRRecord.subject_id).where(
            TrialSubject.status=='enrolled',PCRRecord.status!='verified')
            .order_by(PCRRecord.target_on,PCRRecord.id)).all()
        return [{'study_id':subject.study_code,'scheduled_month':record.scheduled_month,
            'target_on':record.target_on,'days_until':(record.target_on-today).days,
            'status':record.status,'specimen_code':record.specimen_code,
            'anchor_basis':subject.pcr_anchor_basis} for record,subject in rows]
    records=[]
    completed=set()
    for visit in s.scalars(select(Entry).join(Patient,Entry.patient_id==Patient.id)
                           .where(Entry.kind=='visit',active_patient_filter())).all():
        if visit.payload.get('visit_complete') is True:
            try: completed.add((visit.patient_id,int(visit.payload.get('scheduled_month'))))
            except (ValueError,TypeError): continue
    for p in s.scalars(select(Patient).where(Patient.transplant_date.is_not(None),active_patient_filter())).all():
        # Calendar month target dates; windows require investigator approval.
        from calendar import monthrange
        for month in (1,2,3,4,6,9,12):
            y=p.transplant_date.year+(p.transplant_date.month-1+month)//12
            m=(p.transplant_date.month-1+month)%12+1
            day=min(p.transplant_date.day,monthrange(y,m)[1]); target=date(y,m,day)
            if (target-today).days in range(-30,15):
                if (p.id,month) not in completed:
                    records.append({'patient_id':p.id,'cr_number':p.cr_number,
                        'scheduled_month':month,'target_date':target.isoformat(),
                        'days_until':(target-today).days,'date_basis':'transplant_date_placeholder',
                        'warning':'Do not use for clinical visit scheduling; verify enrolled-date anchor and approved windows.'})
    return sorted(records,key=lambda x:x['days_until'])


# Trial-specific closed-loop endpoints, registered after the shared auth helpers.
from .trial_api import router as trial_router
app.include_router(trial_router)

from .trial_crf import router as crf_router
app.include_router(crf_router)

from .randomization import router as randomization_router
app.include_router(randomization_router)

from .backup_channel import router as backup_router
app.include_router(backup_router)

# Same-origin assistant adapter: inherits named staff session and clinical gates.
from .assistant_api import router as assistant_router
app.include_router(assistant_router)



# OAuth uses separate additive metadata; the clinical baseline is unchanged.
from .oauth_api import router as oauth_router
from .mcp_api import router as mcp_router
from .mcp_backup_transfer import router as mcp_backup_transfer_router
app.include_router(oauth_router)
app.include_router(mcp_router)
app.include_router(mcp_backup_transfer_router)
