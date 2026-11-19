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
