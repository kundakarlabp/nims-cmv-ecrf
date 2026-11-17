# Maintain the application without a connected laptop

The existing read-only VM Git checkout, CI release tags and five-minute
`nims-cmv-auto-deploy.timer` are the control path. No SSH private key, OCI API
key, GitHub write token, Docker socket, public terminal or self-hosted Actions
runner is added to the app.

1. Make a branch/PR, run Application checks, review and merge.
2. In a separate release-intent commit, set ops/staging-release.txt to the
   full reviewed commit SHA. Successful main CI publishes the release tag.
3. The VM fetches the tag using its existing read-only key. Deployment takes
   a local database snapshot and attempts application rollback on failure.
4. Sign in as the system administrator and open `/operations`. Confirm the
   deployed commit, fresh host report, active timer and reachable database.
   An application merge or release tag alone is NOT deployment evidence.

The operations endpoint returns only allowlisted status fields. It cannot
execute a supplied command, return a file, read credentials, return patient
records, grant access or enable clinical mode. API/page access is admin-only
and no-store. Other named staff cannot inspect it.

ops/operations_status.py runs fixed read-only systemctl/resource checks on
each timer cycle. It atomically publishes an ignored status file under
ops/public-status; only that directory is mounted read-only inside the API.
Reports older than 15 minutes, future timestamps, invalid and missing reports
are never marked current. The application image accepts an APP_COMMIT build
argument for releases made with the updated deploy script. The very first
upgrade using the old script can show an unknown image commit: verify the
host's completed-deployment SHA and the new page, then later releases stamp
the image directly.

Clinical deficiencies shown on this page describe the running container's
configuration, not an unseen clinical deployment. No synthetic-to-clinical
conversion or clinical activation occurs through this release. Reviewed
host configuration/provisioning changes remain explicit versioned operator
work, and private release/backup/allocation material stays on the VM.

If the VM never pulls this release, the timer/read-only checkout is not a
working control path. One initial OCI Run Command or Cloud Shell setup is
then unavoidable; authentication in mobile Chrome cannot be transferred to
ChatGPT. Do not report this bridge as live without checking the actual host.
