"""Synthetic tests only: no patient record, real OAuth token, SSH or Drive access."""
import configparser
import json
from pathlib import Path

import pytest
from ops import repair_drive_backup as repair
from ops import drive_offsite


def valid_remote(folder=None, refresh="SYNTHETIC-REFRESH"):
    token=json.dumps({"access_token":"SYNTHETIC-ACCESS",
                      "refresh_token":refresh,"token_type":"Bearer"})
    return ("[nims_cmv_drive]\ntype = drive\nroot_folder_id = " +
            (folder or drive_offsite.FOLDER_ID) + "\ntoken = " + token + "\n").encode()


def test_only_approved_folder_and_refreshable_single_remote_can_be_imported():
    remote=repair.parse_supplied_remote(valid_remote())
    assert remote["type"]=="drive"
    assert remote["root_folder_id"]==drive_offsite.FOLDER_ID
    with pytest.raises(ValueError):
        repair.parse_supplied_remote(valid_remote("other_folder"))
    with pytest.raises(ValueError):
        repair.parse_supplied_remote(valid_remote(refresh=""))
    with pytest.raises(ValueError):
        repair.parse_supplied_remote(valid_remote() + b"\n[other]\ntype=drive\n")
    with pytest.raises(ValueError):
        repair.parse_supplied_remote(b"not a config")
    with pytest.raises(ValueError):
        repair.parse_supplied_remote(valid_remote() + b"x"*65536)


def test_installer_preserves_unrelated_remote_and_protects_oauth_file(tmp_path,monkeypatch):
    path=tmp_path/"rclone"/"rclone.conf"
    path.parent.mkdir()
    path.write_text("[unrelated]\ntype = local\nnoun = stays\n")
    path.chmod(0o600)
    monkeypatch.setattr(repair.drive_offsite, "connection_ready",
                        lambda: "nims_cmv_drive" in path.read_text())
    monkeypatch.setattr(repair.drive_offsite, "_rclone",lambda *a: b"")
    assert repair.install_remote(valid_remote(),path) is True
    cfg=configparser.ConfigParser(interpolation=None)
    cfg.read(path)
    assert cfg.get("unrelated","noun")=="stays"
    assert cfg.get("nims_cmv_drive","root_folder_id")==drive_offsite.FOLDER_ID
    assert path.stat().st_mode & 0o777==0o600
    assert path.parent.stat().st_mode & 0o777==0o700
    old=path.read_bytes()
    assert repair.install_remote(valid_remote(refresh="OUTDATED-SYNTHETIC"),path) is False
    assert path.read_bytes()==old, "Working OAuth must not be overwritten"


def test_dead_remote_may_be_replaced_only_by_exact_config(tmp_path,monkeypatch):
    path=tmp_path/"rclone.conf"
    path.write_bytes(valid_remote(refresh="OLD-SYNTHETIC"))
    path.chmod(0o600)
    monkeypatch.setattr(repair.drive_offsite, "connection_ready",lambda: True)
    monkeypatch.setattr(repair.drive_offsite, "_rclone",lambda *a: (_ for _ in ()).throw(
        RuntimeError("SYNTHETIC provider failure with hidden credential")))
    assert repair.install_remote(valid_remote(refresh="NEW-SYNTHETIC"),path)
    assert "NEW-SYNTHETIC" in path.read_text()
    assert "OLD-SYNTHETIC" not in path.read_text()


def test_wrong_remote_never_changes_existing_config(tmp_path):
    path=tmp_path/"rclone.conf"
    path.write_text("[unrelated]\ntype = local\n")
    path.chmod(0o600)
    original=path.read_bytes()
    with pytest.raises(ValueError):
        repair.install_remote(valid_remote("wrong-folder"),path)
    assert path.read_bytes()==original


def test_symlinked_rclone_config_rejected(tmp_path):
    actual=tmp_path/"sensitive"
    actual.write_text("[other]\ntype = local\n")
    link=tmp_path/"rclone.conf"
    link.symlink_to(actual)
    with pytest.raises(ValueError,match="symlinked"):
        repair.install_remote(valid_remote(),link)
    assert actual.read_text()=="[other]\ntype = local\n"


def test_workflow_has_no_embeddded_tokens_or_unsafe_ssh_shortcuts():
    source=(Path(__file__).resolve().parents[1] /
            ".github/workflows/repair-oci-drive-backup.yml").read_text()
    assert "StrictHostKeyChecking=yes" in source
    assert "UserKnownHostsFile=" in source
    assert "persist-credentials: false" in source
    assert "secrets.CMV_DRIVE_RCLONE_CONFIG_B64" in source
    assert "secrets.OCI_SSH_KNOWN_HOSTS" in source
    assert "secrets.OCI_SSH_PRIVATE_KEY" in source
    assert "workflow_dispatch:" in source
    assert "clinical-backup" not in source
    assert "ssh-keyscan" not in source
    assert "StrictHostKeyChecking=no" not in source
