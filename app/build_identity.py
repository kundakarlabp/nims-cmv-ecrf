"""Public identity of application source only: no configuration or records."""
import hashlib
import json
from pathlib import Path
from functools import lru_cache

SOURCE_SUFFIXES={'.py','.js','.html'}


def digest_entries(entries):
    manifest=sorted((name,hashlib.sha256(content).hexdigest()) for name,content in entries)
    return hashlib.sha256(json.dumps(manifest,separators=(',',':')).encode()).hexdigest()


@lru_cache(maxsize=1)
def build_fingerprint():
    root=Path(__file__).resolve().parent
    return digest_entries((path.relative_to(root).as_posix(),path.read_bytes())
        for path in root.rglob('*') if path.is_file() and path.suffix in SOURCE_SUFFIXES)
