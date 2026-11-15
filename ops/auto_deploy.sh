#!/usr/bin/env bash
# Poll a CI-approved staging tag using a read-only GitHub deploy key.
set -euo pipefail
cd "$(dirname "$0")/.."
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
