# Work on NIMS CMV eCRF

This repository is the source of truth. Preserve the simple FastAPI/PostgreSQL/Caddy stack.
Stage with synthetic records only. Never commit patient records, database files, credentials,
SSH keys, screenshots containing patient details, or backup archives.

For changes: inspect relevant code, explain clinical implications, make focused edits,
run `python -m pytest -q` after installing `requirements-dev.txt`, and inspect CI.
Use a branch and PR for later changes. No automatic release solely because a chat says
"fixed": report the commit, checks, and deployment state separately.

The full prototype and field dictionary in reference/ are design inputs; the running UI
is app/ui.html. Do not claim all prototype modules are implemented. Randomization,
blinding, dosing and outcome adjudication require protocol-specific validation.
Never infer a medication order from a preview calculation.

Deployment requires Oracle access and a configured hostname. No paid resources or
services are authorized. No public database port. Keep private code access read-only
on the host. Do not store an Actions SSH key until the owner explicitly configures it.
