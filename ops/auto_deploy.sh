#!/usr/bin/env bash
# Poll a CI-approved staging tag using a read-only GitHub deploy key.
set -euo pipefail
cd "$(dirname "$0")/.."
status_publisher=$(mktemp)
cp ops/operations_status.py "$status_publisher"
# Keep this reviewed publisher available even if checkout/rollback removes or
# changes its source path. It accepts only a result enum and this fixed root.
publisher=(python3 "$status_publisher" --root "$PWD")
publish_completed_attempt() {
  code=$?
  trap - EXIT
  result=success
  (( code == 0 )) || result=failed
  "${publisher[@]}" --attempt-result "$result" || echo 'Host status report unavailable' >&2
  rm -f "$status_publisher"
  exit "$code"
}
trap publish_completed_attempt EXIT
# Refresh a small allowlisted report even when no release is pending. Do not
# include logs, environment values, database contents, or credential files.
"${publisher[@]}" --attempt-result running || echo 'Host status report unavailable' >&2
git fetch --quiet origin main --tags
tag=$(git tag --list 'cmv-staging-*' --sort=-refname | head -n 1)
[[ -n "$tag" ]] || { echo 'No approved staging release yet.'; exit 0; }
[[ "$tag" =~ ^cmv-staging-[0-9]{8}T[0-9]{6}Z-([0-9a-f]{40})$ ]] || {
  echo 'Invalid staging release tag.' >&2; exit 1;
}
target=${BASH_REMATCH[1]}
[[ "$(git rev-parse "$tag^{commit}")" == "$target" ]] || {
  echo 'Staging tag and commit mismatch.' >&2; exit 1;
}
git merge-base --is-ancestor "$target" origin/main
current=$(cat .deploy-state/current-commit 2>/dev/null || true)
[[ "$current" != "$target" ]] || { echo "Already deployed: $target"; exit 0; }
echo "Deploying approved staging commit: $target"
bash ops/deploy.sh "$target"

