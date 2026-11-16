"""Interactive admin MFA bootstrap, run in the authorized clinical API container.

Operator must verify local admin identity. OTP secret displayed only on the
operator's protected terminal; never transfer it to GitHub, chat or logs.
"""
import os
from getpass import getpass
import pyotp
from sqlalchemy import select

if os.getenv("CLINICAL_SCHEMA_BOOTSTRAP")!="true" or os.getenv("DB_NAME")!="nims_cmv_clinical":
    raise SystemExit("Run only during authorized clinical schema onboarding")
from app.main import SessionLocal, User
from app.trial_models import UserTotp

username=input("Verified initial admin username: ").strip().lower()
with SessionLocal() as session:
    admin=session.scalar(select(User).where(User.username==username))
    if not admin or not admin.active or admin.role!="admin":
        raise SystemExit("No such active clinical admin")
    record=session.get(UserTotp,admin.id)
    if record and record.enabled:
        raise SystemExit("MFA already enabled; use supervised account recovery")
    secret=pyotp.random_base32()
    print("Enter this OTPAuth URI only into the verified admin's authenticator.")
    print(pyotp.TOTP(secret).provisioning_uri(name=username,issuer_name="NIMS CMV Trial"))
    entered=getpass("Enter a current authenticator code to confirm: ")
    if not pyotp.TOTP(secret).verify(entered,valid_window=1):
        raise SystemExit("OTP did not verify; no MFA secret stored")
    if record is None:
        record=UserTotp(user_id=admin.id,secret=secret,enabled=True)
        session.add(record)
    else:
        record.secret=secret
        record.enabled=True
    from app.main import now
    record.confirmed_at=now()
    session.commit()
print("Verified clinical admin authenticator activated.")
