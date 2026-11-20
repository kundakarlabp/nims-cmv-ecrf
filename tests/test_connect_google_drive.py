"""Synthetic-only checks for the OCI owner setup helper. No cloud or patient access."""
import os
from pathlib import Path
from types import SimpleNamespace

from ops import connect_google_drive as setup


def export_dir(tmp_path):
    private = tmp_path / "clinical"
    (private / "export").mkdir(parents=True)
    return private


def prepare(monkeypatch):
    monkeypatch.setattr(setup.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(setup.shutil, "which", lambda command: "/usr/bin/rclone")


def test_not_configured_cannot_bootstrap_in_headless_actions(tmp_path, monkeypatch, capsys):
    prepare(monkeypatch)
    monkeypatch.setattr(setup.drive_offsite, "connection_ready", lambda: False)
    monkeypatch.setattr(setup.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("No OAuth interaction permitted in GitHub Actions")))
    assert setup.setup(export_dir(tmp_path), interactive=False) == 2
    assert "interactive" in capsys.readouterr().out


def test_preconfigured_remote_reads_back_without_wizard(tmp_path, monkeypatch, capsys):
    prepare(monkeypatch)
    root = export_dir(tmp_path)
    monkeypatch.setattr(setup.drive_offsite, "connection_ready", lambda: True)
    commands = []
    monkeypatch.setattr(setup.drive_offsite, "_rclone", lambda *args: commands.append(args) or b"")
    monkeypatch.setattr(setup.drive_offsite, "sync_latest", lambda path: path == root)
    monkeypatch.setattr(setup.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("Authorized remote should not need wizard")))
    assert setup.setup(root, interactive=False) == 0
    assert commands == [("lsf", "nims_cmv_drive:")]
    assert "readback verified" in capsys.readouterr().out


def test_interactive_bootstrap_uses_target_folder_and_protects_config(tmp_path, monkeypatch):
    prepare(monkeypatch)
    root = export_dir(tmp_path)
    config = tmp_path / "config" / "rclone.conf"
    monkeypatch.setattr(setup.drive_offsite, "config_path", lambda: config)
    observed = []
    def fake_wizard(args, **kwargs):
        assert args == ["rclone", "--config", str(config), "config"]
        config.write_text("[nims_cmv_drive]\ntype = drive\nroot_folder_id = " +
                          setup.drive_offsite.FOLDER_ID +
                          '\ntoken = {"access_token":"SYNTHETIC"}\n')
        observed.append("wizard")
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(setup.subprocess, "run", fake_wizard)
    monkeypatch.setattr(setup.drive_offsite, "_rclone", lambda *args: b"")
    monkeypatch.setattr(setup.drive_offsite, "sync_latest", lambda path: path == root)
    assert setup.setup(root, interactive=True) == 0
    assert observed == ["wizard"]
    assert config.stat().st_mode & 0o777 == 0o600


def test_remote_errors_never_print_credentials(tmp_path, monkeypatch, capsys):
    prepare(monkeypatch)
    monkeypatch.setattr(setup.drive_offsite, "connection_ready", lambda: True)
    monkeypatch.setattr(setup.drive_offsite, "_rclone", lambda *args: (_ for _ in ()).throw(
        RuntimeError("Bearer SECRET-DO-NOT-PRINT")))
    assert setup.setup(export_dir(tmp_path), interactive=False) == 6
    assert "SECRET-DO-NOT-PRINT" not in capsys.readouterr().out


def test_local_export_is_required_before_oauth(tmp_path, monkeypatch):
    prepare(monkeypatch)
    assert setup.setup(tmp_path / "missing", interactive=False) == 3
