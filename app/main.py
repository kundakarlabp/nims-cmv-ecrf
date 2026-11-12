"""NIMS transplant registry foundation. For staging/UAT only pending validation."""
import hashlib
import os
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from fastapi import FastAPI, Depends, HTTPException, Response, Request
from fastapi.responses import FileResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import create_engine, String, Integer, DateTime, ForeignKey, Date, JSON, Text, select, func, URL
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError

DATABASE_URL=os.getenv('DATABASE_URL','')
if not DATABASE_URL and os.getenv('DB_HOST'):
    DATABASE_URL=URL.create('postgresql+psycopg',username=os.getenv('DB_USER','nims_ecrf'),password=os.environ['POSTGRES_PASSWORD'],host=os.getenv('DB_HOST'),port=5432,database=os.getenv('DB_NAME','nims_ecrf'))
if not DATABASE_URL: DATABASE_URL='sqlite:///./local_uat.sqlite3'
COOKIE_SECURE=os.getenv('COOKIE_SECURE','true').lower()=='true'
SESSION_HOURS=int(os.getenv('SESSION_HOURS','12'))
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
    password_hash: Mapped[str]=mapped_column(Text,nullable=False)
    active: Mapped[bool]=mapped_column(default=True,nullable=False)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class LoginSession(Base):
    __tablename__='sessions'
    token_hash: Mapped[str]=mapped_column(String(64),primary_key=True)
    user_id: Mapped[str]=mapped_column(ForeignKey('users.id'),index=True)
    csrf_hash: Mapped[str]=mapped_column(String(64),nullable=False)
    expires_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
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

app=FastAPI(title='NIMS Transplant Registry — staging foundation',docs_url=None,redoc_url=None)
Base.metadata.create_all(bind=ENGINE)  # Staging convenience; replace with reviewed migrations before production

ROLES={'pi','admin','consultant','pg','scientist','nurse','technician','microbiology','pharmacy','monitor'}
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
    model_config=ConfigDict(frozen=True)

def current(request:Request,s:Session=Depends(db)) -> AuthContext:
    token=request.cookies.get('nims_session')
    if not token: raise HTTPException(401,'Login required')
    active=s.get(LoginSession,sha(token))
    if not active or active.expires_at.replace(tzinfo=UTC)<now(): raise HTTPException(401,'Session expired')
    user=s.get(User,active.user_id)
    if not user or not user.active: raise HTTPException(401,'Account disabled')
    if request.method not in ('GET','HEAD','OPTIONS'):
        supplied=request.headers.get('x-csrf-token','')
        if not supplied or not secrets.compare_digest(sha(supplied),active.csrf_hash):
            raise HTTPException(403,'Missing or invalid CSRF token')
    return AuthContext(user_id=user.id,role=user.role,name=user.display_name,csrf_hash=active.csrf_hash)

def audit(s:Session,u:AuthContext,action:str,entity_type:str,entity_id:str,patient_id:str|None,old:dict|None,new:dict|None,reason:str):
    s.add(Audit(actor_id=u.user_id,action=action,entity_type=entity_type,entity_id=entity_id,patient_id=patient_id,old_record=old,new_record=new,reason=reason))

def permission(u,kind):
    if u.role not in (WRITE_ROLES.get(kind) or set()) and u.role!='admin':
        raise HTTPException(403,'Insufficient delegated role permission')

class LoginInput(BaseModel):
    username:str=Field(min_length=2,max_length=100)
    password:str=Field(min_length=1,max_length=200)

@app.get('/')
def home(): return FileResponse(Path(__file__).parent/'ui.html')
@app.get('/healthz')
def health(): return {'ok':True,'service':'staging'}
@app.get('/readyz')
def ready():
    try:
        with ENGINE.connect() as connection:
            connection.execute(select(1))
    except SQLAlchemyError:
        raise HTTPException(503,'Service temporarily unavailable')
    return {'ok':True,'service':'staging','database':'reachable'}
@app.post('/api/login')
def login(data:LoginInput,response:Response,s:Session=Depends(db)):
    # Production gate: add external identity provider/MFA and persistent rate limiting.
    u=s.scalar(select(User).where(User.username==data.username))
    try: matched=bool(u and u.active and PH.verify(u.password_hash,data.password))
    except (VerifyMismatchError,VerificationError): matched=False
    if not matched: raise HTTPException(401,'Invalid credentials')
    token=secrets.token_urlsafe(48); csrf=secrets.token_urlsafe(32)
    expiry=now()+timedelta(hours=SESSION_HOURS)
    s.add(LoginSession(token_hash=sha(token),user_id=u.id,csrf_hash=sha(csrf),expires_at=expiry));s.commit()
    response.set_cookie('nims_session',token,max_age=SESSION_HOURS*3600,httponly=True,secure=COOKIE_SECURE,samesite='strict',path='/')
    return {'username':u.username,'role':u.role,'display_name':u.display_name,'csrf_token':csrf}
@app.get('/api/me')
def me(u:AuthContext=Depends(current)):
    return {'user_id':u.user_id,'role':u.role,'display_name':u.name}
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
    p=Patient(**data.model_dump(),created_by=u.user_id)
    try:
        s.add(p);s.flush();audit(s,u,'create','patient',p.id,p.id,None,as_dict(p),'Initial registration')
        s.commit()
    except IntegrityError: s.rollback();raise HTTPException(409,'Duplicate CR number or study ID')
    return {'id':p.id,'revision':p.revision}
@app.get('/api/patients')
def patients(q:str='',limit:int=50,u:AuthContext=Depends(current),s:Session=Depends(db)):
    limit=min(max(limit,1),100)
    st=select(Patient)
    if q.strip(): st=st.where(Patient.name.ilike('%'+q.strip()+'%')|Patient.cr_number.ilike('%'+q.strip()+'%')|Patient.study_id.ilike('%'+q.strip()+'%'))
    ps=s.scalars(st.order_by(Patient.created_at.desc()).limit(limit)).all()
    return [{'id':p.id,'cr_number':p.cr_number,'name':p.name,'study_id':p.study_id,'transplant_date':p.transplant_date,'revision':p.revision} for p in ps]
@app.get('/api/patients/{patient_id}')
def patient(patient_id:str,u:AuthContext=Depends(current),s:Session=Depends(db)):
    p=s.get(Patient,patient_id)
    if not p: raise HTTPException(404)
    es=s.scalars(select(Entry).where(Entry.patient_id==patient_id).order_by(Entry.occurred_on.desc(),Entry.created_at.desc())).all()
    return {'patient':as_dict(p),'entries':[as_dict(e) for e in es]}
class EntryIn(BaseModel):
    kind:Literal['admission','visit','lab','infection','medication','transplant','safety','pharmacy','rejection']
    occurred_on:date
    payload:dict[str,Any]
@app.post('/api/patients/{patient_id}/entries')
def new_entry(patient_id:str,data:EntryIn,u:AuthContext=Depends(current),s:Session=Depends(db)):
    permission(u,data.kind)
    if not s.get(Patient,patient_id): raise HTTPException(404)
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
@app.get('/api/patients/{patient_id}/audit')
def audit_history(patient_id:str,u:AuthContext=Depends(current),s:Session=Depends(db)):
    if u.role not in {'admin','pi','consultant','monitor','scientist'}: raise HTTPException(403)
    rows=s.scalars(select(Audit).where(Audit.patient_id==patient_id).order_by(Audit.created_at.desc()).limit(500)).all()
    return [as_dict(x) for x in rows]

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
    today=date.today(); records=[]
    for p in s.scalars(select(Patient).where(Patient.transplant_date!=None)).all():
        # Calendar month target dates; windows require investigator approval.
        from calendar import monthrange
        for month in (1,2,3,4,6,9,12):
            y=p.transplant_date.year+(p.transplant_date.month-1+month)//12
            m=(p.transplant_date.month-1+month)%12+1
            day=min(p.transplant_date.day,monthrange(y,m)[1]); target=date(y,m,day)
            if (target-today).days in range(-30,15):
                visits=s.scalars(select(Entry).where(Entry.patient_id==p.id,Entry.kind=='visit')).all()
                if not any(v.payload.get('scheduled_month')==month and v.payload.get('visit_complete') for v in visits):
                    records.append({'patient_id':p.id,'cr_number':p.cr_number,'scheduled_month':month,'target_date':target.isoformat(),'days_until':(target-today).days})
    return sorted(records,key=lambda x:x['days_until'])
