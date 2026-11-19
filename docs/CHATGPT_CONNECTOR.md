# Authenticated assistant workflow and future ChatGPT connection

The NIMS CMV eCRF now has an **authenticated, same-origin** assistant
adapter at `/api/assistant`. It is intentionally **not a public ChatGPT
connector**: it accepts the existing staff session only and uses existing CSRF
checks and trial role permissions. There are no integration tokens or server
commands.

| Path | Purpose | Existing clinical enforcement |
| --- | --- | --- |
| `GET /api/assistant/capabilities` | Discover safe operations and connection status | Named login |
| `GET /api/assistant/subjects?q=NCMV001` | Search, max 10; query length >= 3 | Existing masked study search |
| `GET /api/assistant/subjects/{id}/crf` | Read recorded CRF sections | Existing CRF read permissions |
| `PUT /api/assistant/subjects/{id}/drafts/{section}` | Save partial section | Study-ID match, CRF schema, per-user draft, revision |
| `POST /api/assistant/subjects/{id}/entries` | Submit one completed CRF | Explicit confirmation, study-ID match, existing submit + audit |
| `PUT /api/assistant/entries/{entry_id}` | Correct submitted CRF | Explicit confirmation, study-ID match, expected revision, correction reason, existing audit |

Changes through this adapter remain attributable to the **signed-in staff
account**, not a shared API service identity. The adapter cannot create a
patient, bypass eligibility, randomly assign an arm, prescribe, dispense,
approve consent or skip existing security gates. Existing eCRF endpoints
already support those controlled workflows where separately authorized.

## Immediate practical use

Use **ChatGPT Work's cloud browser**, sign into the actual dashboard using a
named authorized account, search by patient/CR/study ID, and enter a user-approved
clinical record in the existing form. Confirm the persisted record after save.
Do not paste credentials into chat. Existing 30-minute idle expiry applies.

## Direct ChatGPT chat integration (not connected)

For ordinary ChatGPT chat to invoke these actions without browser navigation,
build and connect a **private MCP server using OAuth 2.1 with PKCE**. It must:

1. Bind authorization to the *individual* existing user and approved staff
   roles, not GitHub, Supabase or a generic relay account. Support refresh
   revocation and least-privilege read/write scopes.
2. Reuse these exact validated FastAPI service methods and existing database;
   never permit SQL, arbitrary HTTP proxying, server shell, batch trial
   allocation, credential access or PHI-bearing logs.
3. Recheck authorization, patient identity, consent, expected revision,
   occurrence-key uniqueness, backup/restore freshness and user-confirmed
   intent on every write. Require idempotency keys for retried submissions.
4. Preserve complete actor attribution and independently verify that the
   target record was committed and read back.
5. Prove no PHI reaches the NIFTY Supabase project, GitHub issues, Action
   logs, third-party application telemetry or unsecured storage.
6. Complete institutional data-sharing approval and independent synthetic
   security/UAT before enabling any identifiable record through external AI.

**This code does not grant ChatGPT patient access**. It prepares an auditable
application-side workflow without weakening clinical security.


## Simplified single-patient workflow (staff session, no extra service)

The adapter now supports registry search, registration, correction and one-step
exact-match entry:

- `GET /api/assistant/patients?q=TEST-...` and
  `GET /api/assistant/patients/{patient_id}`: reuse the current registry.
- `POST /api/assistant/patients`: register using existing PatientIn checks,
  including staging synthetic restrictions and automatic trial Study ID.
- `PUT /api/assistant/patients/{patient_id}`: correct name/CR using the known
  old CR and expected revision, with a reason and existing audit log.
- `POST /api/assistant/patient-entry`: `{identifier,kind,occurred_on,payload}`
  where identifier is the **exact** CR number, patient name or study ID.
  Duplicated patient names are rejected, rather than guessed; the resulting
  event is saved using the original permission and audit path.
- `PUT /api/assistant/registry-entries/{entry_id}`: correct a registry event
  using existing expected revision and reason.
- `PUT /api/assistant/crf-draft-by-identifier`: save a typed partial CRF
  draft by exact CR number, name or study ID; no manual subject-ID lookup.

No second identity provider, API password, relay service or new database.
The staff login, 30-minute idle session, existing permissions and server-side
revision checks are unchanged. All endpoints remain unavailable to ChatGPT
until the owner connects an authenticated browser (Work) or separately
configures a custom MCP OAuth connection. **This is not equivalent to enabling
direct chat access.**

Use the existing HTTPS dashboard to do clinical work immediately; do not
copy a password or identifiable clinical source text into GitHub issues.

## Implemented MCP/OAuth adapter — 19 November 2026

The same FastAPI process now exposes **`/mcp`**, a stateless Streamable HTTP
JSON-RPC endpoint. Existing `/api/assistant` routes continue to use dashboard
cookies and CSRF; MCP uses independently issued user-bound OAuth bearer tokens.
The adapter calls the same validated service functions and existing database.

- Discovery: `/.well-known/oauth-protected-resource` and
  `/.well-known/oauth-authorization-server`.
- OAuth: `/oauth/register`, `/oauth/authorize`, `/oauth/token`, `/oauth/revoke`.
  ChatGPT-only exact redirect URIs, S256 PKCE, five-minute single-use codes,
  15-minute access tokens, rotating 30-day refresh tokens, 90-day grant ceiling.
  Refresh reuse revokes the entire connection. Tokens and codes are stored only
  as SHA256 digests. The resource is the exact configured HTTPS origin + `/mcp`.
- User authorizes read access and optionally write access through the existing
  dashboard password/MFA flow. This does not change staff roles or dashboard MFA.
  Account disablement, staff expiry and password changes invalidate access.
- Every call reuses account authorization and clinical backup/restore checks.
  Tools cannot randomize, prescribe, verify consent, issue SQL or run commands.
- Writes require explicit confirmation and an idempotency key. The key is bound
  to actor policy, tool and input. A crash with an uncertain save is rejected
  for manual dashboard readback; an uncertain write is never blindly repeated.
- Successful writes return committed readback and the named actor ID. Existing
  service audit remains authoritative; drafts remain drafts.
- Dashboard **ChatGPT connections** opens `/oauth/connections`, where the user
  can revoke a connection with their existing CSRF-protected dashboard session.

### Release and migration

The reviewed additive migration `ops/migrations/20261119_assistant_oauth.sql`
creates five OAuth/receipt tables in the existing database without changing any
clinical table or its baseline fingerprint. The existing deployment preparation
runs it as the database owner before starting the new API. It is idempotent,
keeps schema-creation privileges away from the application role, and survives
application rollback (new tables may remain unused). Token state is covered by
existing database backups. A restored historical backup requires revoking old
OAuth grants before reconnecting external clients.

The canonical origin comes from `MCP_PUBLIC_ORIGIN` or the existing `SITE_DOMAIN`.
Never derive issuer/resource identifiers from request Host or forwarded headers.
No separate identity-provider subscription, API billing or new VM is needed.

### Connect and acceptance checks

After the exact release SHA is verified live, connect the HTTPS `/mcp` URL in
ChatGPT using **OAuth** and dynamic client registration (no static secret).
Approve the dashboard-account link in the authorization page. Attach the actual
connection to the existing private NIMS CMV plugin; do not invent an App ID.

Use synthetic data for acceptance: initialize/list tools; link read-only and
check writes fail; link read/write; register `TEST-MCP-...` with a `Synthetic ...`
name; save one event; compare returned actor/readback against dashboard and
existing database audit; refresh; revoke; verify access and refresh rejection.
Do not claim regular-chat execution merely because endpoint tests or CI pass.

Tests: `python -m pytest -q tests/test_mcp_oauth.py`; full `python -m pytest -q`.
CI additionally exercises migration twice on real disposable PostgreSQL and
checks that the clinical baseline and restricted-role permissions remain intact.

Official contracts:
https://developers.openai.com/plugins/build/auth
https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
