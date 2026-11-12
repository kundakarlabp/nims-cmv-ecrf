#!/usr/bin/env bash
# Deploy a reviewed commit. No credentials or patient records belong in Git.
set -euo pipefail
cd "$(dirname "$0")/.."
target=${1:?Usage: bash ops/deploy.sh FULL_COMMIT_SHA}
[[ "$target" =~ ^[0-9a-f]{40}$ ]] || { echo 'Use a full reviewed commit SHA.' >&2; exit 2; }
command -v flock >/dev/null
mkdir -p .deploy-state
exec 9>.deploy-state/deploy.lock
flock -n 9 || { echo 'Another deployment is running.' >&2; exit 2; }
test -z "$(git status --porcelain)" || { echo 'Commit or save local changes first.' >&2; exit 2; }
test -f .env || { echo 'Configure .env privately first.' >&2; exit 2; }
if grep -Eq 'REPLACE_WITH|YOUR_OWN_DOMAIN' .env; then
  echo 'Replace example settings privately before deploying.' >&2; exit 2
fi
chmod 600 .env
git fetch origin main
git merge-base --is-ancestor "$target" origin/main
previous=$(git rev-parse HEAD)
git checkout --detach "$target"
docker compose config --quiet
docker compose build --pull api
# Snapshot before a change; retain locally until encrypted offsite backup is configured.
if docker compose ps --status running --services | grep -qx db; then
  umask 077
  mkdir -p backups
  dump="backups/predeploy-$(date -u +%Y%m%dT%H%M%SZ).dump"
  docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-acl' > "$dump"
  test -s "$dump"
fi
printf '%s\n' "$previous" > .deploy-state/previous-commit
if ! docker compose up -d --wait --wait-timeout 180; then
  echo 'Deployment did not become healthy. Inspect docker compose logs --tail=100.' >&2
  echo 'Previous commit is in .deploy-state/previous-commit. No database restore was attempted.' >&2
  exit 1
fi
bash ops/check_health.sh
printf '%s\n' "$target" > .deploy-state/current-commit
echo 'Containers ready. Verify public HTTPS/login before accepting deployment.'
