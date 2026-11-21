"""Synthetic-only OCI Google Drive backup tests. No cloud login or patients."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import pytest

from app.clinical_gate import backup_fresh, restore_verified
from ops import drive_offsite as drive


def fixture(tmp_path, monkeypatch):
    path = tmp_path / "rclone.conf"
    path.write_text(
        "[nims_cmv_drive]\n"
        "type = drive\n"
        "root_folder_id = " + drive.FOLDER_ID + "\n"
        'token = {"access_token":"SYNTHETIC-NOT-VALID"}\n')
    path.chmod(0o600)
    monkeypatch.setenv("RCLONE_CONFIG", str(path))
    root = tmp_path / "private"
    export = root / "export"
    export.mkdir(parents=True)
    bundle_id = "20261119T110000Z-abcdef123456"
    bundle = export / (bundle_id + ".tar")
    raw = b"sealed, synthetic, nonpatient archive test"
    bundle.write_bytes(raw)
    stamp = "20261119T110000Z"
    manifest = {
        "id": bundle_id, "sha256": hashlib.sha256(raw).hexdigest(),
        "size": len(raw), "stamp": stamp, "restore_verified": True,
        "created_at": "2026-11-19T11:00:00+00:00",
    }
    (export / (bundle_id + ".json")).write_text(json.dumps(manifest))
    return root, path, manifest, raw


def test_direct_drive_exact_readback_and_same_bundle_is_idempotent(tmp_path, monkeypatch):
    root, config, manifest, raw = fixture(tmp_path, monkeypatch)
    assert drive.connection_ready(config)
    remote = {}
    uploads = []

    def mock_rclone(action, *args):
        if action == "copyto":
            dest = args[1]
            assert dest.startswith("nims_cmv_drive:clinical-")
            remote[dest] = Path(args[0]).read_bytes()
            uploads.append(dest)
            return b""
        if action == "cat":
            return remote[args[0]]
        if action == "lsjson":
            return json.dumps([{"Name": x.split(":", 1)[1]} for x in remote]).encode()
        raise AssertionError((action, args))

    monkeypatch.setattr(drive, "_rclone", mock_rclone)
    assert drive.sync_latest(root) is True
    assert drive.sync_latest(root) is True
    assert len(uploads) == 1
    env = {
        "CLINICAL_BACKUP_RECEIPT_PATH": str(root / "backup-state/last_success"),
        "CLINICAL_RESTORE_RECEIPT_PATH": str(root / "backup-state/last_restore"),
    }
    at = datetime(2026, 11, 19, 11, 5, tzinfo=timezone.utc)
    assert backup_fresh(env, at) and restore_verified(env, at)
    receipt = (root / "backup-state/last_success").read_text()
    assert receipt.endswith("gdrive:" + drive.FOLDER_ID
                            + ":clinical-" + manifest["id"] + ".tar\n")
    assert not backup_fresh(env, datetime(2026, 11, 19, 20, 0, tzinfo=timezone.utc))


def test_corrupt_google_drive_readback_is_not_accepted(tmp_path, monkeypatch):
    root, _, _, _ = fixture(tmp_path, monkeypatch)
    def corrupted(action, *args):
        if action == "copyto":
            return b""
        if action == "cat":
            return b"unverified wrong remote bytes"
        if action == "lsjson":
            return b"[]"
        raise AssertionError(action)
    monkeypatch.setattr(drive, "_rclone", corrupted)
    with pytest.raises(RuntimeError, match="readback size/hash mismatch"):
        drive.sync_latest(root)
    assert not (root / "backup-state/last_success").exists()
    assert not (root / "backup-state/last_restore").exists()


def test_drive_access_requires_specific_private_folder_and_protected_config(tmp_path, monkeypatch):
    root, config, _, _ = fixture(tmp_path, monkeypatch)
    config.chmod(0o644)
    assert not drive.connection_ready(config)
    config.chmod(0o600)
    config.write_text(config.read_text().replace(drive.FOLDER_ID, "unrelated-folder"))
    assert not drive.connection_ready(config)
    assert drive.sync_latest(root) is False
    assert not (root / "backup-state/last_success").exists()


def test_pruning_never_removes_unrelated_drive_objects(monkeypatch):
    removed = []
    names = [
        "clinical-20261119T%06dZ-abcdef012345.tar" % index
        for index in range(drive.KEEP_LATEST + 3)
    ]
    names += ["randomization-private.txt", "other-project-backup.tar"]
    def mock(action, *args):
        if action == "lsjson":
            return json.dumps([{"Name": name} for name in names]).encode()
        if action == "deletefile":
            removed.append(args[0])
            return b""
        raise AssertionError(action)
    monkeypatch.setattr(drive, "_rclone", mock)
    drive._prune_remote()
    assert len(removed) == 3
    assert all("clinical-" in name for name in removed)
    assert not any("randomization" in x or "other-project" in x for x in removed)


def test_existing_exact_remote_file_is_reused_and_read_back(tmp_path, monkeypatch):
    root, _, manifest, raw = fixture(tmp_path, monkeypatch)
    target = "nims_cmv_drive:clinical-" + manifest["id"] + ".tar"
    calls = []
    def existing(action, *args):
        calls.append(action)
        if action == "lsjson":
            return json.dumps([{"Name": target.split(":", 1)[1]}]).encode()
        if action == "cat":
            assert args[0] == target
            return raw
        raise AssertionError("Already existing archive must not be overwritten")
    monkeypatch.setattr(drive, "_rclone", existing)
    assert drive.sync_latest(root)
    assert "copyto" not in calls
    assert "cat" in calls


def test_existing_corrupt_remote_does_not_get_overwritten_or_receipted(tmp_path, monkeypatch):
    root, _, manifest, _ = fixture(tmp_path, monkeypatch)
    name = "clinical-" + manifest["id"] + ".tar"
    def corrupt_existing(action, *args):
        if action == "lsjson":
            return json.dumps([{"Name": name}]).encode()
        if action == "cat":
            return b"wrong remote content"
        raise AssertionError("Corrupt existing archive must not be overwritten")
    monkeypatch.setattr(drive, "_rclone", corrupt_existing)
    with pytest.raises(RuntimeError, match="readback size/hash mismatch"):
        drive.sync_latest(root)
    assert not (root / "backup-state/last_success").exists()


def test_existing_local_receipt_cannot_skip_remote_readback(tmp_path, monkeypatch):
    root, _, manifest, raw = fixture(tmp_path, monkeypatch)
    folder = root / "backup-state"
    folder.mkdir()
    (folder / "last_success").write_text(
        manifest["stamp"] + " " + manifest["sha256"] +
        " gdrive:" + drive.FOLDER_ID + ":clinical-" + manifest["id"] + ".tar\n"
    )
    remote = {}
    calls = []
    def missing_remote(action, *args):
        calls.append(action)
        if action == "lsjson":
            return json.dumps([{"Name": key.split(":", 1)[1]} for key in remote]).encode()
        if action == "copyto":
            remote[args[1]] = Path(args[0]).read_bytes()
            return b""
        if action == "cat":
            return remote[args[0]]
        raise AssertionError(action)
    monkeypatch.setattr(drive, "_rclone", missing_remote)
    assert drive.sync_latest(root)
    assert calls.count("copyto") == 1
    assert calls.count("cat") == 1


def test_ambiguous_duplicate_drive_names_rejected(tmp_path, monkeypatch):
    root, _, manifest, _ = fixture(tmp_path, monkeypatch)
    name = "clinical-" + manifest["id"] + ".tar"
    def duplicate(action, *args):
        if action == "lsjson":
            return json.dumps([{"Name": name}, {"Name": name}]).encode()
        raise AssertionError("No remote archive should be read or overwritten")
    monkeypatch.setattr(drive, "_rclone", duplicate)
    with pytest.raises(RuntimeError, match="Ambiguous duplicate"):
        drive.sync_latest(root)



def test_drive_downloaded_restore_is_proved_once_per_verified_bundle(tmp_path, monkeypatch):
    root, _, manifest, raw = fixture(tmp_path, monkeypatch)
    name = "clinical-" + manifest["id"] + ".tar"
    calls = []
    def existing(action, *args):
        if action == "lsjson":
            return json.dumps([{"Name": name}]).encode()
        if action == "cat":
            calls.append("download")
            return raw
        raise AssertionError("Existing Drive archive must not be overwritten")
    monkeypatch.setattr(drive, "_rclone", existing)
    restored = []
    def verify(data):
        restored.append(data)
        return True
    assert drive.sync_latest(root, verify_restore=verify)
    assert drive.sync_latest(root, verify_restore=verify)
    assert restored == [raw]
    assert calls == ["download", "download"]
    state = root / "backup-state"
    assert (state / "last_offsite_restore").read_bytes() == (
        state / "last_oci_direct").read_bytes() == (
        state / "last_success").read_bytes()


def test_drive_restore_failure_never_advances_receipt(tmp_path, monkeypatch):
    root, _, manifest, raw = fixture(tmp_path, monkeypatch)
    name = "clinical-" + manifest["id"] + ".tar"
    def existing(action, *args):
        if action == "lsjson":
            return json.dumps([{"Name": name}]).encode()
        if action == "cat":
            return raw
        raise AssertionError(action)
    monkeypatch.setattr(drive, "_rclone", existing)
    def failed_restore(_):
        raise RuntimeError("synthetic disposable PostgreSQL restore failure")
    with pytest.raises(RuntimeError, match="synthetic disposable"):
        drive.sync_latest(root, verify_restore=failed_restore)
    state=root / "backup-state"
    assert not (state / "last_success").exists()
    assert not (state / "last_offsite_restore").exists()
    assert not (state / "last_oci_direct").exists()
