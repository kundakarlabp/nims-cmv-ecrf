# Oracle Cloud Always Free — Deployment runbook for NIMS CMV registry (12 Nov 2026)

**Do not enter real patient information during staging.** Only synthetic data until security/clinical go-live gates are independently verified.

## 1. Oracle free-tier eligibility and true limits

- OCI Ampere A1 Always Free: **2 OCPUs + 12 GB RAM total**, split across eligible instances. The frequently quoted older 4 OCPU/24 GB allowance is not the applicable official value in the current Always Free documentation. Verify your own tenancy quota in the Oracle console.
- 200 GB total block volume, counting boot volume; five volume backups within home-region allowance. 20 GB of combined Always Free Object/Archive storage under free-only tenancy terms; subject to applicable tiers and limits.
- Initial configuration: one `VM.Standard.A1.Flex`, **2 OCPUs/8 GB RAM**, Ubuntu 24.04 LTS ARM64, 50 GB Always Free boot volume. Remaining Always Free capacity is not a promise of available instance inventory.
- Choose **India South (Hyderabad)** home region (`ap-hyderabad-1`) on signup **if selectable**. Free resources must be created in your home region. The home region cannot be changed later.
- Account signup may require a supported credit/debit card and phone verification; one account per person. Do NOT create duplicate free accounts to evade capacity limits.
- OCI may reclaim an Always Free instance that meets its 7-day idle criteria. Instance provisioning may fail with `out of host capacity` even when you have quota. Free trial's non-free services expire/reclaim according to trial rules. Always Free-only users have community rather than standard paid support.
- Expected compute bill: ₹0 if every resource remains `Always Free`. Domain name, excess storage, third-party messaging, excess provider use, and maintenance may cost extra. Avoid selecting resources without an `Always Free` label.

Reference: https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm ; https://www.oracle.com/in/cloud/free/faq/ ; https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/launchinginstance.htm

## 2. Create the tenancy and compute instance — user action

1. Open https://www.oracle.com/in/cloud/free/ and create/sign into a **single** OCI Free Tier tenancy. Complete verification privately; never send your password, debit card number, SSH private key or OTP in chat.
2. Select **India South (Hyderabad)** as the home region if available; record the region and account tenancy display name. If you already have an account, its home region is already fixed.
3. In the Console, check **Governance & Administration → Limits, Quotas and Usage** for A1 availability and block storage limits.
4. Create an instance named e.g. `nims-cmv-staging`. Select **Always Free** A1 Flex, 2 OCPU, 8GB RAM, Ubuntu ARM64, 50GB boot volume. Check the Always Free label before pressing Create.
5. Generate an SSH key locally and upload the **public** key only; store the private key on your personal machine. Never share private keys in messages.
6. Restrict ingress with a network security group: TCP 22 only from your own administrative IP (or use OCI Bastion); TCP 80/443 for the website when DNS ready. **Do not open 5432/PostgreSQL to the internet.** Enable basic VCN logs/instance monitoring and MFA for the cloud administrator.
7. Create a controlled DNS subdomain for the web application and point the A record to the instance's stable public IP. HTTPS certificate issuance requires working DNS and publicly reachable 80/443. A registered domain may be an additional cost.
8. If OCI returns `out of host capacity`, try another availability domain in the same home region (if available). Do **not** claim that instance is created or relocate identifiable data without assessing region/data governance.

## 3. Install containers after successful SSH connection

SSH from your machine (replace placeholder):

```bash
ssh -i /path/to/private_key ubuntu@YOUR_OCI_PUBLIC_IP
```

On Ubuntu ARM64, follow the official Docker Engine installation instructions for Ubuntu and install Docker's Compose plugin. The official instructions support arm64:
https://docs.docker.com/engine/install/ubuntu/

After installation, verify:

```bash
sudo docker version
sudo docker compose version
sudo docker run --rm hello-world
```

For automated backup service to run as `ubuntu`, that user needs Docker access. Membership in the `docker` group is root-equivalent: assess host security before running `sudo usermod -aG docker ubuntu`, then sign out/in. Alternatively adapt the systemd unit to a locked-down privileged service account.

## 4. Put staging code on server

From local computer:

```bash
scp -i /path/to/private_key NIMS_CMV_Oracle_Starter_v0.3.zip ubuntu@YOUR_OCI_PUBLIC_IP:~/
```

On server:

```bash
sudo mkdir -p /opt/nims-cmv
sudo chown ubuntu:ubuntu /opt/nims-cmv
unzip NIMS_CMV_Oracle_Starter_v0.3.zip
cp -a NIMS_CMV_Oracle_Starter_v0.3/. /opt/nims-cmv/
cd /opt/nims-cmv
cp .env.example .env
chmod 600 .env
# Edit .env privately: SITE_DOMAIN=your.real.subdomain and a long random POSTGRES_PASSWORD
# Example secure password generator: openssl rand -hex 32
# Do NOT send .env or secret strings to ChatGPT.
docker compose config --quiet
docker compose up -d --build
docker compose ps
# Create the first administrator; choose private, unique credentials:
docker compose exec api python bootstrap_admin.py
```

Visit `https://YOUR_OWN_DOMAIN/`. Before DNS/TLS, do not disable security settings to expose patient data. `healthz` returns only a staging health signal.

**Production changes are mandatory** before identifiable-data use: see `ops/GO_LIVE_GATES.md`. At this stage no actual randomization is enabled; the generic record payload is a transitional staging form.

## 5. Configure Google Drive encryption — not yet connected

The intended backup destination is `kundakarlabp@gmail.com`, subject to NIMS approval for identifiable trial backups. Use dedicated Drive folder with no public sharing and a dedicated OAuth client, read/write authorization to that folder only if possible. Do not grant broad Drive permissions unnecessarily.

- Install `rclone` (https://rclone.org/install/) and configure one **Google Drive** remote (e.g. `drive:`) using its documented OAuth flow (https://rclone.org/drive/). The default shared OAuth client may be retired during 2026; use an account-controlled OAuth client as recommended by rclone. Do not paste tokens into ChatGPT.
- Configure a `crypt` remote named `ecrfcrypt:` pointing to a dedicated path in `drive:` (https://rclone.org/crypt/). Generate a long unique secret and salt and store both in an offline password manager; encrypt/protect the rclone config file and keep a recoverable key escrow separate from the server.
- Test with a **synthetic** backup and a separate restoration test before scheduling; check that Drive only contains encrypted file names/content. rclone's `crypt` config password field is only lightly obscured unless the config itself is secured.
- Export `RCLONE_CONFIG=/home/ubuntu/.config/rclone/rclone.conf`; adapt if configured elsewhere. Run `RCLONE_CONFIG=... ops/backup_to_drive.sh` after PostgreSQL is running. This creates a PostgreSQL custom-format snapshot, uploads to `ecrfcrypt:oracle-nims-backups`, and checks a decrypted remote SHA256 roundtrip. The script fails closed when no crypt remote exists.
- Copy `.service` / `.timer` from `ops/` to `/etc/systemd/system`, then `sudo systemctl daemon-reload && sudo systemctl enable --now nims-ecrf-backup.timer`. Only do this after a successful manual test. Read timer logs and configure failure notifications.
- Run `ops/restore_check.sh TIMESTAMP unique_test_db` to restore to a **non-production** database. Then compare expected patient/entry/audit counts and destroy the test copy according to SOP.
- The offered timer is **every six hours**. This is not an immediate Drive sync after each edit; immediate saving and audit happen in PostgreSQL. Tighter offsite recovery objectives require WAL/PITR replication in addition to six-hour snapshots. Backups do not yet include imaging or attachment files (not implemented in this starter).
- Maintain an independent second recovery copy rather than relying only on the same tenancy or personal Google Drive.

## 6. Operational acceptance / release decisions

- **Financial gate:** instance labeled Always Free, no billable cloud resource selected, cost monitoring and account activity enabled.
- **Service gate:** real availability-domain provisioning confirmed; HTTPS, login, on-host service restart, persistence verified; stress-test at least 15 concurrent users.
- **Audit gate:** 2-user same-record edit conflict, change reason, immutable off-host audit, role access tests, staff onboarding/revocation.
- **Clinical gate:** trial's consent, eligibility, stratification, blinded adjudication, protocol v5.0 dosing, noninferiority endpoint and independent DSMB paths validated. Ensure pharmacist/clinician confirmation for actual medication order.
- **Backup gate:** Google Drive connected, encrypted content verified, scheduled timer logs observed, independent restore from Drive on a *different* system verified.
- **Data governance gate:** explicit institution authorization for cloud region, NIMS-controlled or personal account backups, named patients and imaging, retention, access and incident response.

## 7. Fallback if A1 unavailable

Keep the source code and encrypted backups independent of the free hosting provider. If Oracle A1 has no capacity or is reclaimed, restore the PostgreSQL backup and launch the same Compose stack on another ARM64 or AMD64 VPS. Do not repeatedly recreate accounts in breach of Oracle's terms, or rely on public hosting before production approval.
