# NIMS Kidney Transplant Registry + ICMR CMV eCRF

Private source repository: `kundakarlabp/nims-cmv-ecrf`.

## Simple working arrangement

Describe a correction in ChatGPT and identify this repository. ChatGPT can inspect the
current files through the GitHub connector, prepare a branch/PR and report checks.
GitHub keeps the code and change history; Oracle will run the application and database.
Chat messages do not automatically synchronize into the application or change patient
records. Never paste patient records into GitHub issues or chat for software fixes.

Current status: **OCI staging VM provisioned in Hyderabad; application not deployed; no public live URL; staging only.**
`app/ui.html` is the real connected staging interface. `reference/synthetic_prototype.html`
is a richer design mockup, not a fully connected application.

## Before Oracle is available

`Application checks` runs API tests on SQLite and disposable PostgreSQL and builds the
container stack with an HTTP proxy smoke check. It uses no cloud credentials or patient data.
No scheduled jobs, paid runners or automatic deployments are configured. Included private
Actions usage is account-wide: keep paid overage disabled in GitHub billing settings.
Do not assume a repository workflow can enforce the account's spending budget.

## When Oracle is available

1. Provision an eligible Always Free host; verify the tenancy's actual free limits and
   capacity. Install Docker Engine + Compose from official Ubuntu instructions.
2. Clone this private repository to `/opt/nims-cmv` using an owner-configured read-only
   deploy key. Keep that private key on the host. No full-account write token is needed.
3. Copy `.env.example` to `.env`; privately set a strong database password and a hostname
   you control. Configure DNS and permit HTTPS/HTTP; restrict SSH to administration.
4. Run `bash ops/deploy.sh FULL_REVIEWED_COMMIT_SHA` from the checkout. The SHA must be
   on `origin/main`. Existing data gets a protected local pre-deployment snapshot.
5. Run `docker compose exec api python bootstrap_admin.py` and choose credentials privately.
6. Check public HTTPS, login, synthetic save/reload, access denial and service restart.
   Configure encrypted offsite backups and prove restoration before clinical go-live.

`/healthz` checks process responsiveness; `/readyz` also checks the database. Compose
checks API readiness, rotates container logs and restarts exited services. An unhealthy
but still running process is flagged; Docker does not restart it just for being unhealthy.
Neither these checks nor restart policies prevent an Oracle host outage or reclamation.
External availability alerting is still to be configured after a public URL exists.

For an application rollback, inspect `.deploy-state/previous-commit` and redeploy that
reviewed SHA with the same script. Database migrations/restoration require a separate
review; code rollback does not reverse a schema or data change. Do not run
`docker compose down -v` on the server: it destroys stored volumes.

**State: a locally tested staging foundation. NOT a live deployment, NOT yet a validated eCRF, NOT approved for identifiable clinical data.**

The user requested an independently hosted custom website for approximately 10–15 nephrology consultants, PGs and trial staff; 12-month CMV trial follow-up; full transplant/infection registry; individual audit logs; clinician-reviewed VGCV renal dosing and encrypted backups to their Google Drive. This package begins the custom build with PostgreSQL, FastAPI, a responsive test interface, Docker Compose, a TLS reverse proxy, deployment instructions, and encrypted Drive backup scripts. No user records or credentials are included.

## Verified reference specifications

- Protocol v5.0 (14 August 2026), NIMS–ICMR CMV RCT, 344 participants; 1:1 variable permuted block randomization by **rATG yes/no** and **living/deceased donor**; 3-month prophylaxis; PCR months **1/2/3/4/6/9/12**. **Production randomization is NOT implemented**.
- VGCV trial arms 450 mg / 900 mg, with renal-dose adjustment by Cockcroft–Gault. **Current calculation is only a dose-preview/testing tool**, with a manually chosen arm; never prescribe automatically.
- `reference/data_dictionary_draft.csv` contains 552 provisional fields (not yet validated or enforced by the starter API), and `reference/synthetic_prototype.html` preserves the previously built full-interface mockup.

## What actually works in this staging starter

- User passwords hashed using Argon2; random server-side session tokens in HttpOnly, SameSite=Strict cookies; CSRF token required for authenticated writes; 12-hour session expiry; explicit user roles. HTTPS cookie is enabled by default (disable **only** for local testing).
- Persisted patients (CR/name/study ID/transplant date), repeated dated records in nine event categories, optimistic revision checks and attributable server-generated audit events.
- PG, consultant, scientist, nurse, lab, pharmacy role write rules at API level; role test coverage for PG.
- Searchable patient list, timeline, clinical entry staging interface, and schedule-derived follow-up worklist.
- Aggregate dashboard, correction form and independent review queue for synthetic staging records. Review decisions bind to an entry revision; later correction returns it to pending. Reviewer cannot verify their own creation or latest edit. This application-level review history is not a validated, immutable clinical audit trail.
- Dose-preview API matching protocol v5.0 renal adjustment thresholds, with automated tests around boundaries.
- ARM64-compatible container definitions, PostgreSQL database, TLS-capable Caddy proxy. Exposed ports: 80/443; SQL DB isolated on private Docker network.
- Opt-in **6-hour encrypted snapshot backup script** (only functions after rclone OAuth and crypt configuration); SHA-256 remote roundtrip verification; separate non-destructive restore-check script.

## Explicitly NOT yet implemented or validated

- A Free Tier E2.1.Micro VM and public subnet exist in OCI Hyderabad, but **no domain, HTTPS live endpoint, Google Drive OAuth, backup timer, external monitoring, or 15-user load test has been configured or verified**. OCI Run Command has not delivered the staging diagnostic; the instance has no deployed application.
- Login lacks rate limiting and MFA, schema migrations, DB-enforced immutable audit, fully typed 552-field forms, document uploads, independent randomization, blinded adjudication, correct clinical-grade medication orders, full unit-based access control, formal data-validation queries and official statistical outputs.
- Clinical use must wait until all items in `ops/GO_LIVE_GATES.md` are signed off. Current database uses its owner account and staging schema creation, so its audit log is not immutable against database administrators.
- The worklist displays due visits but does not message patients, send email reminders or authorize contact.
- Site/website deployment and Google Drive backup remain **unconnected**.

## Read next

1. `ORACLE_DEPLOYMENT_RUNBOOK.md` — precise OCI signup and provisioning steps, shell deployment, validation and contingency plan.
2. `ops/GO_LIVE_GATES.md` — data governance, validation, security and clinical safety blockers.
3. `ops/backup_to_drive.sh` and `ops/restore_check.sh` — secure backup tooling for later configuration.
4. `tests/test_foundation.py` — local unit/API tests.

## Local development (disposable synthetic-only data)

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
export DATABASE_URL=sqlite:///./local_uat.sqlite3
export COOKIE_SECURE=false
python -m ops.bootstrap_admin
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Local browser: `http://127.0.0.1:8000`. Do not make this port publicly accessible or enter real records. Test suite: `python -m pytest -q`. Local PostgreSQL integration and container builds require Docker; see GitHub Actions for remote results.

## Recovery / ownership

All source code, schema definition, reference field dictionary, instructions and tests are supplied as editable files. The source remains under user control and can be moved between hosts. Keep keys, .env, backup encryption passphrases and OAuth refresh tokens **outside source code, ChatGPT messages and Git**.

Oracle documentation: https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
rclone docs: https://rclone.org/crypt/ and https://rclone.org/drive/

