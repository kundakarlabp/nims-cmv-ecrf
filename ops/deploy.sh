#!/usr/bin/env bash
# Deploy a reviewed commit. No credentials or patient records belong in Git.
set -euo pipefail
cd "$(dirname "$0")/.."
target=${1:?Usage: bash ops/deploy.sh FULL_COMMIT_SHA}
[[ "$target" =~ ^[0-9a-f]{40}$ ]] || { echo 'Use a full reviewed commit SHA.' >&2; exit 2; }
command -v flock >/dev/null
docker_cmd=(docker)
if ! docker info >/dev/null 2>&1; then
  sudo -n docker info >/dev/null
  docker_cmd=(sudo -n docker)
fi
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
# Snapshot before a change; retain locally until encrypted offsite backup is configured.
if "${docker_cmd[@]}" compose ps --status running --services | grep -qx db; then
  umask 077
  mkdir -p backups
  dump="backups/predeploy-$(date -u +%Y%m%dT%H%M%SZ).dump"
  "${docker_cmd[@]}" compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-acl' > "$dump"
  test -s "$dump"
fi
printf '%s\n' "$previous" > .deploy-state/previous-commit
switched=0
rollback() {
  code=$?
  trap - ERR
  if (( switched )); then
    echo 'Deployment failed. Restoring the previous application commit.' >&2
    # Preserve explicit failure evidence even when the previous revision
    # predates the publisher and the operations page.
    if [[ -f ops/operations_status.py ]]; then
      python3 ops/operations_status.py --attempt-result failed || echo 'Host status report unavailable' >&2
    fi
    export APP_COMMIT="$previous"
    git checkout --detach "$previous" || true
    "${docker_cmd[@]}" compose build api &&
      "${docker_cmd[@]}" compose up -d --wait --wait-timeout 180 &&
      "${docker_cmd[@]}" compose up -d --force-recreate --no-deps caddy || true
  fi
  echo 'Inspect the containers and backup before retrying. No database restore was attempted.' >&2
  exit "$code"
}
trap rollback ERR
git checkout --detach "$target"
switched=1
export APP_COMMIT="$target"
# Fixed read-only host checks, published separately from private configuration.
python3 ops/operations_status.py || echo 'Host status report unavailable' >&2
"${docker_cmd[@]}" compose config --quiet
"${docker_cmd[@]}" compose build --pull api
"${docker_cmd[@]}" compose up -d --wait --wait-timeout 180
"${docker_cmd[@]}" compose up -d --force-recreate --no-deps caddy
bash ops/check_health.sh
trap - ERR
printf '%s\n' "$target" > .deploy-state/current-commit
python3 ops/operations_status.py --attempt-result success || echo 'Host status report unavailable' >&2
echo 'Containers ready. Verify public HTTPS/login before accepting deployment.'


