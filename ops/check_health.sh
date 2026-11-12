#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose ps
docker compose exec -T api python - <<'PY'
import json, urllib.request
for path in ('/healthz', '/readyz'):
    with urllib.request.urlopen('http://127.0.0.1:8000'+path, timeout=5) as response:
        assert response.status == 200
        assert json.load(response)['ok'] is True
print('API and database readiness passed. Public HTTPS must be checked separately.')
PY
