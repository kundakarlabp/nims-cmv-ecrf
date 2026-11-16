"""One-time initial clinical schema provisioner; NOT a runtime migration.

Run ONLY in a new, empty nims_cmv_clinical database, with owner credentials.
It refuses existing tables, stamps a structural baseline and grants application
access to a separate role without schema-creation permission. Later structural
changes require reviewed explicit migrations and updated baseline.
Never run against staging or a populated patient database.
"""
import os
from sqlalchemy import inspect, text
from psycopg import sql

if os.environ.get("CLINICAL_SCHEMA_BOOTSTRAP")!="true":
    raise SystemExit("Explicit CLINICAL_SCHEMA_BOOTSTRAP=true required")
if os.environ.get("CLINICAL_DATA_ENABLED","false").lower()=="true":
    raise SystemExit("Cannot provision while clinical data entry is enabled")
if os.environ.get("DB_NAME")!="nims_cmv_clinical" or os.environ.get("DB_USER")!="nims_clinical_owner":
    raise SystemExit("Dedicated clinical DB owner/target required")
secret=os.environ.get("CLINICAL_DB_APP_PASSWORD","")
if len(secret)<24:
    raise SystemExit("A separate random app-role password of >=24 characters is required")

from app.main import Base, ENGINE
from app.clinical_gate import metadata_fingerprint

if ENGINE.dialect.name!="postgresql":
    raise SystemExit("PostgreSQL required for clinical provisioning")
with ENGINE.connect() as check:
    info=check.execute(text("SELECT current_database(), current_user")).one()
    if tuple(info)!=("nims_cmv_clinical","nims_clinical_owner"):
        raise SystemExit("Refusing unexpected database or owner")
    existing=inspect(check).get_table_names(schema="public")
    if existing:
        raise SystemExit("Database already contains tables; refuse overwrite or implicit migration")
    if check.execute(text("SELECT 1 FROM pg_roles WHERE rolname='nims_clinical_app'")).first():
        raise SystemExit("Clinical app role already exists; request reviewed reconciliation")

fingerprint=metadata_fingerprint(Base.metadata)
with ENGINE.begin() as conn:
    Base.metadata.create_all(bind=conn)
    conn.execute(text("""CREATE TABLE public.clinical_schema_baseline(
          revision varchar(40) PRIMARY KEY,
          fingerprint varchar(64) NOT NULL,
          installed_at timestamptz NOT NULL DEFAULT current_timestamp
        )"""))
    conn.execute(text("""INSERT INTO public.clinical_schema_baseline(revision,fingerprint)
                       VALUES ('initial-2026-11',:fingerprint)"""),{"fingerprint":fingerprint})
    # psycopg SQL composables safely quote role names and secret literals.
    driver=conn.connection.driver_connection
    with driver.cursor() as cur:
        cur.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
            sql.Identifier("nims_clinical_app"),sql.Literal(secret)))
        cur.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        cur.execute("GRANT USAGE ON SCHEMA public TO nims_clinical_app")
        cur.execute("""GRANT SELECT, INSERT, UPDATE, DELETE
                       ON ALL TABLES IN SCHEMA public TO nims_clinical_app""")
        cur.execute("""GRANT USAGE, SELECT
                       ON ALL SEQUENCES IN SCHEMA public TO nims_clinical_app""")
        cur.execute("""REVOKE UPDATE, DELETE, TRUNCATE
                       ON TABLE public.audit_events FROM nims_clinical_app""")
        cur.execute("""REVOKE INSERT, UPDATE, DELETE, TRUNCATE
                       ON TABLE public.clinical_schema_baseline FROM nims_clinical_app""")
        cur.execute("""CREATE FUNCTION public.prevent_trial_audit_mutation()
                       RETURNS trigger LANGUAGE plpgsql AS $$
                       BEGIN RAISE EXCEPTION 'Audit records are append-only'; END $$""")
        cur.execute("""CREATE TRIGGER protect_trial_audit_update_delete
                       BEFORE UPDATE OR DELETE ON public.audit_events
                       FOR EACH ROW EXECUTE FUNCTION public.prevent_trial_audit_mutation()""")
        cur.execute("""CREATE TRIGGER protect_trial_audit_truncate
                       BEFORE TRUNCATE ON public.audit_events
                       FOR EACH STATEMENT EXECUTE FUNCTION public.prevent_trial_audit_mutation()""")
print("New dedicated clinical baseline provisioned with separate, restricted app role.")
print("Schema revision: initial-2026-11")
print("Structural fingerprint:",fingerprint)
print("NO participant data imported. Independent UAT, backup/restore and release are still mandatory.")
