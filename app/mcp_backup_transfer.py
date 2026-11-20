"""Short-lived ciphertext transfer for an authenticated Drive readback workflow.

The exported archive was encrypted and restored on OCI before this module sees
it.  No database key, allocation key, plaintext dump, arbitrary file or shell
operation is exposed.  A PI/admin may authorize a ten-minute download of only
the newest validated archive, then attest the independently downloaded Drive
copy by exact SHA-256.  Host maintenance still owns the clinical gate receipt.
"""
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .main import AuthContext, audit, db, now, sha
from .oauth_api import origin
from .oauth_models import MCPReceipt

router = APIRouter(tags=["private-encrypted-backup-transfer"])

FOLDER_ID = "1Mnzme95zuQM5WKuHWtsv2-nzhtPUK_EM"
BUNDLE_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$")
FILE_RE = re.compile(r"^clinical-([0-9]{8}T[0-9]{6}Z-[0-9a-f]{12})[.]tar$")
DRIVE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,200}$")
MAX_BUNDLE = 32 * 1024 * 1024


def _operator(u: AuthContext):
    if u.role not in {"admin", "pi"} and not u.pi_authorized:
        raise HTTPException(403, "PI or administrator permission required")


def _root():
    return Path(os.getenv("CLINICAL_BACKUP_EXPORT_DIR", "/run/clinical-backups"))


def _bundle(bundle_id: str | None = None):
    root = _root()
    ids = sorted(path.stem for path in root.glob("*.json")
                 if BUNDLE_RE.fullmatch(path.stem))
    selected = bundle_id or (ids[-1] if ids else None)
    if selected is None or not BUNDLE_RE.fullmatch(selected):
        raise HTTPException(503, "Encrypted restored backup is not available")
    archive = root / (selected + ".tar")
    manifest_path = root / (selected + ".json")
    if (archive.is_symlink() or manifest_path.is_symlink() or
            not archive.is_file() or not manifest_path.is_file() or
            archive.stat().st_size > MAX_BUNDLE):
        raise HTTPException(503, "Encrypted restored backup is not available")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        raise HTTPException(503, "Encrypted backup manifest is invalid")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if (manifest.get("id") != selected or manifest.get("restore_verified") is not True or
            manifest.get("size") != archive.stat().st_size or manifest.get("sha256") != digest):
        raise HTTPException(503, "Encrypted backup validation failed")
    return archive, manifest


def prepare_transfer(u: AuthContext, s: Session):
    _operator(u)
    _, manifest = _bundle()
    raw = secrets.token_urlsafe(48)
    expires = now() + timedelta(minutes=10)
    token_id = sha("backup-transfer:" + raw)
    s.add(MCPReceipt(id=token_id,
        request_digest=sha("backup-transfer:" + u.user_id + ":" + manifest["id"]),
        result={"type": "encrypted_backup_transfer", "user_id": u.user_id,
                "bundle_id": manifest["id"], "sha256": manifest["sha256"],
                "size": manifest["size"], "expires_at": expires.isoformat()}))
    audit(s, u, "backup_transfer_authorize", "encrypted_backup", manifest["id"],
          None, None, {"sha256": manifest["sha256"], "size": manifest["size"],
                       "expires_at": expires},
          "Ten-minute ciphertext-only transfer authorized for verified Drive upload")
    s.commit()
    return {"bundle_id": manifest["id"],
            "file_name": "clinical-" + manifest["id"] + ".tar",
            "size": manifest["size"], "sha256": manifest["sha256"],
            "download_url": origin() + "/api/backup-transfer/" + manifest["id"],
            "authorization_header": "Backup " + raw,
            "expires_at": expires,
            "encryption": "OCI Fernet archive plus owner-SSH age key escrow",
            "destination_folder_id": FOLDER_ID,
            "contains_plaintext_clinical_data": False}


def confirm_readback(bundle_id: str, drive_file_id: str, drive_file_name: str,
                     readback_sha256: str, u: AuthContext, s: Session):
    _operator(u)
    archive, manifest = _bundle(bundle_id)
    expected_name = "clinical-" + bundle_id + ".tar"
    if (not DRIVE_ID_RE.fullmatch(drive_file_id) or drive_file_name != expected_name or
            not FILE_RE.fullmatch(drive_file_name) or
            not re.fullmatch(r"[0-9a-f]{64}", readback_sha256) or
            not secrets.compare_digest(readback_sha256, manifest["sha256"])):
        raise HTTPException(409, "Google Drive readback does not match the restored OCI archive")
    if hashlib.sha256(archive.read_bytes()).hexdigest() != manifest["sha256"]:
        raise HTTPException(409, "OCI archive changed after transfer")
    ack_dir = Path(os.getenv("CLINICAL_BACKUP_ACK_DIR", "/run/backup-ack"))
    ack_dir.mkdir(mode=0o750, parents=True, exist_ok=True)
    payload = {"bundle_id": bundle_id, "sha256": manifest["sha256"],
               "gdrive_folder_id": FOLDER_ID, "gdrive_file_id": drive_file_id,
               "gdrive_file_name": drive_file_name, "confirmed_by": u.user_id,
               "confirmed_at": now().isoformat()}
    temporary = ack_dir / (bundle_id + ".tmp-" + secrets.token_hex(6))
    final = ack_dir / (bundle_id + ".json")
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o640)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(payload, output, separators=(",", ":"))
        os.replace(temporary, final)
    finally:
        temporary.unlink(missing_ok=True)
    audit(s, u, "backup_drive_readback_confirm", "encrypted_backup", bundle_id,
          None, None, {"drive_file_id": drive_file_id,
                       "drive_file_name": drive_file_name,
                       "sha256": manifest["sha256"]},
          "Encrypted Drive object downloaded and exact SHA-256 readback confirmed")
    s.commit()
    return {"acknowledged": True, "bundle_id": bundle_id,
            "drive_file_id": drive_file_id, "sha256": manifest["sha256"],
            "next_step": "OCI maintenance validates the acknowledgment and refreshes the clinical gate receipt"}


@router.get("/api/backup-transfer/{bundle_id}")
def download_backup(bundle_id: str, authorization: str | None = Header(default=None),
                    s: Session = Depends(db)):
    if not authorization or not authorization.startswith("Backup ") or len(authorization) > 512:
        raise HTTPException(401, "Encrypted backup transfer authorization required")
    raw = authorization[7:]
    receipt = s.get(MCPReceipt, sha("backup-transfer:" + raw))
    data = receipt.result if receipt and isinstance(receipt.result, dict) else {}
    try:
        expires = datetime.fromisoformat(data["expires_at"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(401, "Encrypted backup transfer authorization rejected")
    if (data.get("type") != "encrypted_backup_transfer" or
            data.get("bundle_id") != bundle_id or expires <= now()):
        raise HTTPException(401, "Encrypted backup transfer authorization rejected")
    archive, manifest = _bundle(bundle_id)
    if (data.get("sha256") != manifest["sha256"] or data.get("size") != manifest["size"]):
        raise HTTPException(409, "Encrypted backup transfer no longer matches")
    return FileResponse(archive, media_type="application/x-tar",
        filename="clinical-" + bundle_id + ".tar",
        headers={"Cache-Control": "no-store, private", "X-Content-Type-Options": "nosniff",
                 "Referrer-Policy": "no-referrer"})
