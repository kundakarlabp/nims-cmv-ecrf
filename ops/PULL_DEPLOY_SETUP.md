# Phone-independent staging releases

The live OCI VM currently runs a transferred bundle at `/home/ubuntu/nims-cmv`.
The steps below turn it into a read-only Git checkout and enable the VM to pull
explicitly released, CI-checked commits. This is for **synthetic staging only**.
Do not paste the private key, database password or patient records into chat.

## One-time VM and GitHub connection

1. On the VM as `ubuntu`, generate a dedicated repository key:

   ```bash
   install -d -m 700 ~/.ssh
   ssh-keygen -t ed25519 -f ~/.ssh/nims_cmv_repo_readonly -N '' -C 'nims-cmv-staging-readonly'
   chmod 600 ~/.ssh/nims_cmv_repo_readonly
   cat ~/.ssh/nims_cmv_repo_readonly.pub
   ```

2. In the private repository's **Settings → Deploy keys**, add that **public** key
   with **Allow write access unchecked**. Verify `github.com`'s SSH host key
   against GitHub's published fingerprints before adding it to `known_hosts`.
   Then verify repository read access:

   ```bash
   GIT_SSH_COMMAND="ssh -i $HOME/.ssh/nims_cmv_repo_readonly -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes" \
     git ls-remote git@github.com:kundakarlabp/nims-cmv-ecrf.git HEAD
   ```

3. Take a separate protected database snapshot before changing the checkout.
   Preserve the current `.env` and `.initial-admin`. The `nims-cmv` Compose
   project name keeps the existing named database and Caddy volumes when the
   source directory changes. Do not use `docker compose down -v`.

   ```bash
   cd /home/ubuntu/nims-cmv
   umask 077
   mkdir -p backups
   sudo docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-acl' \
     > "backups/pre-git-$(date -u +%Y%m%dT%H%M%SZ).dump"
   cd /home/ubuntu
   mv nims-cmv "nims-cmv-bundle-$(date -u +%Y%m%dT%H%M%SZ)"
   GIT_SSH_COMMAND="ssh -i $HOME/.ssh/nims_cmv_repo_readonly -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes" \
     git clone git@github.com:kundakarlabp/nims-cmv-ecrf.git nims-cmv
   cp nims-cmv-bundle-*/.env nims-cmv/.env
   cp nims-cmv-bundle-*/.initial-admin nims-cmv/.initial-admin
   chmod 600 nims-cmv/.env nims-cmv/.initial-admin
   cd nims-cmv
   git config core.sshCommand "ssh -i $HOME/.ssh/nims_cmv_repo_readonly -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes"
   ```

   If more than one old bundle folder exists, select the most recent one
   explicitly instead of using the `*` glob. Keep the old folder until the
   first release and restore drill succeed.

4. Deploy the reviewed commit once, confirm `/readyz`, sign in and inspect the
   dashboard. Only then install and enable the timer:

   ```bash
   bash ops/deploy.sh FULL_REVIEWED_MAIN_SHA
   sudo cp ops/nims-cmv-auto-deploy.{service,timer} /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now nims-cmv-auto-deploy.timer
   systemctl list-timers nims-cmv-auto-deploy.timer
   ```

## Each later change from ChatGPT chat

1. Inspect the source, change it on a branch and open a PR. Run and inspect CI.
2. Merge the reviewed PR. Record its full main commit SHA.
3. In a **separate** commit on main, create or update `ops/staging-release.txt`
   with only that full 40-character SHA and a newline. CI tests the intent
   commit; the release workflow checks that it is the current main commit and
   that the target is an ancestor before publishing a timestamped tag.
4. The VM timer fetches tags every five minutes and deploys the newest valid
   release, taking a local backup and checking health. Inspect
   `journalctl -u nims-cmv-auto-deploy.service -n 100 --no-pager`, then verify
   public HTTPS and sign-in. A failed app update attempts to restore the
   previous application commit; schema/data rollback is separate.

ChatGPT chat needs GitHub repository access for code and release-intent commits.
No laptop browser session, inbound VM SSH from GitHub Actions, or write-capable
GitHub token on the VM is needed after one-time setup. Do not release an API or
schema change without reviewing migration and rollback effects.
