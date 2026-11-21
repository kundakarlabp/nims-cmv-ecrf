"""Synthetic only: restore the actual offsite tar into a disposable DB."""
import hashlib
import io
import json
import re
import tarfile

import pytest
from cryptography.fernet import Fernet
from ops import clinical_maintenance as maintenance
from ops import operations_status


def sealed_archive(tmp_path):
    key = Fernet.generate_key()
    (tmp_path / "backup.key").write_bytes(key + b"\n")
    encrypted = Fernet(key).encrypt(b"PGDMP synthetic-only fixture")
    manifest = json.dumps({
        "database": "nims_cmv_clinical",
        "schema_fingerprint": "ci-test-fingerprint",
        "encrypted_dump_sha256": hashlib.sha256(encrypted).hexdigest(),
        "restore_verified": True,
    }).encode()
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as tar:
        for name, data in (
            ("database.dump.fernet", encrypted),
            ("recovery-keys.age", b"age-encryption.org/v1\nsynthetic-escrow-only"),
            ("manifest.json", manifest),
        ):
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            tar.addfile(entry, io.BytesIO(data))
    return output.getvalue()


def test_downloaded_bundle_restores_disposable_database_and_cleans_up(tmp_path, monkeypatch):
    archive = sealed_archive(tmp_path)
    monkeypatch.setattr(maintenance, "PRIVATE", tmp_path)
    monkeypatch.setattr(maintenance, "clinical", lambda dc: ["docker", "compose"])
    commands = []
    def sql(dc, statement, database="nims_cmv_clinical", stage=False):
        commands.append((statement, database))
        if "SELECT fingerprint FROM clinical_schema_baseline" in statement:
            return b"ci-test-fingerprint\n"
        return b""
    def run(cmd, *, data=None, check=True):
        commands.append((cmd, data))
        assert "pg_restore" in cmd
        assert data == b"PGDMP synthetic-only fixture"
        return b""
    monkeypatch.setattr(maintenance, "sql", sql)
    monkeypatch.setattr(maintenance, "run", run)
    assert maintenance.verify_drive_downloaded_restore(["docker"], archive) is True
    created=[s for s,d in commands if isinstance(s,str) and s.startswith("CREATE DATABASE")]
    dropped=[s for s,d in commands if isinstance(s,str) and s.startswith("DROP DATABASE")]
    assert len(created) == len(dropped) == 1
    target=created[0][len("CREATE DATABASE "):-1]
    assert re.fullmatch(r"nims_restore_[0-9a-f]{16}",target)
    assert dropped[0] == f"DROP DATABASE {target};"
    assert target not in {"nims_ecrf", "nims_cmv_clinical"}


def test_failed_restore_always_drops_disposable_database(tmp_path, monkeypatch):
    archive = sealed_archive(tmp_path)
    monkeypatch.setattr(maintenance, "PRIVATE", tmp_path)
    monkeypatch.setattr(maintenance, "clinical", lambda dc: ["docker", "compose"])
    statements=[]
    def fake_sql(dc, statement, database="nims_cmv_clinical", stage=False):
        statements.append(statement)
        if "SELECT fingerprint FROM clinical_schema_baseline" in statement:
            return b"ci-test-fingerprint\n"
        return b""
    monkeypatch.setattr(maintenance, "sql", fake_sql)
    def fake_run(cmd, *, data=None, check=True):
        raise RuntimeError("Synthetic restore failure")
    monkeypatch.setattr(maintenance, "run", fake_run)
    with pytest.raises(RuntimeError, match="Synthetic restore"):
        maintenance.verify_drive_downloaded_restore(["docker"], archive)
    assert sum(s.startswith("CREATE DATABASE") for s in statements)==1
    assert sum(s.startswith("DROP DATABASE") for s in statements)==1


def test_invalid_downloaded_archive_refused_before_sql(tmp_path, monkeypatch):
    archive = sealed_archive(tmp_path)
    monkeypatch.setattr(maintenance, "PRIVATE", tmp_path)
    monkeypatch.setattr(maintenance, "sql", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("No SQL before archive validation")))
    with pytest.raises((tarfile.TarError, RuntimeError, OSError)):
        maintenance.verify_drive_downloaded_restore(["docker"], b"malformed archive")
    assert archive != b"malformed archive"


def test_sanitized_oci_proof_must_match_latest_receipt(tmp_path):
    state=tmp_path/".local/share/nims-cmv-clinical/backup-state"
    state.mkdir(parents=True)
    value=("20261121T100000Z "+("e"*64)+
           " gdrive:1Mnzme95zuQM5WKuHWtsv2-nzhtPUK_EM:"
           "clinical-20261121T100000Z-abcdef123456.tar\n").encode()
    (state/"last_success").write_bytes(value)
    assert operations_status.drive_receipt_proof_matches(tmp_path,"last_oci_direct") is False
    (state/"last_oci_direct").write_bytes(value)
    assert operations_status.drive_receipt_proof_matches(tmp_path,"last_oci_direct") is True
    (state/"last_offsite_restore").write_bytes(b"unverified old receipt")
    assert operations_status.drive_receipt_proof_matches(tmp_path,"last_offsite_restore") is False
