"""Run interactively in API container after startup; never use default passwords."""
import getpass
from app.main import SessionLocal,User,PH,ROLES
from sqlalchemy import select
username=input('Admin username: ').strip()
name=input('Display name: ').strip()
password=getpass.getpass('Strong admin password (14+ chars): ')
confirm=getpass.getpass('Confirm password: ')
if len(password)<14 or password!=confirm or len(username)<3 or not name:
    raise SystemExit('Invalid username, display name or password. Nothing saved.')
with SessionLocal() as db:
    if db.scalar(select(User).where(User.username==username)):
        raise SystemExit('Account already exists')
    db.add(User(username=username,display_name=name,role='admin',password_hash=PH.hash(password)))
    db.commit()
print('Admin created; enroll MFA/identity provider before production.')
