#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker_cmd=(docker)
if ! docker info >/dev/null 2>&1; then
  sudo -n docker info >/dev/null
  docker_cmd=(sudo -n docker)
fi
compose_args=()
if [[ -f .deploy-state/clinical-active ]]; then
  compose_args=(--env-file "$HOME/.local/share/nims-cmv-clinical/clinical.env" -f compose.clinical.yaml)
fi
"${docker_cmd[@]}" compose "${compose_args[@]}" ps
"${docker_cmd[@]}" compose "${compose_args[@]}" exec -T api python - <<'PY'
import json, urllib.request
for path in ('/healthz', '/readyz'):
    with urllib.request.urlopen('http://127.0.0.1:8000'+path, timeout=5) as response:
        assert response.status == 200
        assert json.load(response)['ok'] is True
print('API and database readiness passed. Public HTTPS must be checked separately.')
PY


