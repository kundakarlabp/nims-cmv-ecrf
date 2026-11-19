# Session and daytime operations

Refreshing the page restores the signed-in workspace from its existing HttpOnly
session cookie. CSRF tokens and clinical UI data remain in memory. No password,
patient data or session token is written to browser storage. A server deadline
expires the session after 30 minutes of inactivity. Only real foreground input
sends an authenticated, CSRF-checked renewal; background reads do not renew it.
Logout, account disablement and access expiry still invalidate access. Account
administration retains its existing permissions.

In the owner-configured shared clinical workspace, any authorised signed-in staff
member can verify source data, including their own entry. The audit record keeps
the person's name, timestamp, revision and reason. This is source verification,
not a substitute for the investigator's clinical eligibility decision.

Routine encrypted offsite Actions backups run at 07:47, 10:47, 13:47 and 16:47
India time. Host snapshot/restore maintenance runs only between 07:30 and 17:00
India time; forced initial cutover/recovery and genuine deployment recovery remain
available. The existing 8-hour backup freshness check remains: writes may pause
overnight until the next successful morning copy. No recovery archives are deleted.

Code changes can use the existing authenticated GitHub connection and the reviewed
release pipeline without a dashboard login. Patient records require a valid staff
session. No anonymous command endpoint or credential bypass is introduced.
