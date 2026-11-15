"""Exercise release selection without a network connection or Docker daemon."""
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(*args, cwd):
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=True).stdout.strip()


def test_approved_release_is_idempotent_and_rejects_mismatched_tag(tmp_path):
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    run("git", "init", "--bare", str(origin), cwd=tmp_path)
    run("git", "init", "-b", "main", str(work), cwd=tmp_path)
    run("git", "config", "user.email", "test@example.invalid", cwd=work)
    run("git", "config", "user.name", "Test", cwd=work)
    (work / "ops").mkdir()
    shutil.copy(ROOT / "ops/auto_deploy.sh", work / "ops/auto_deploy.sh")
    (work / "ops/deploy.sh").write_text(
        '#!/bin/bash\nmkdir -p .deploy-state\nprintf "%s\\n" "$1" >> executions.log\n'
        'printf "%s\\n" "$1" > .deploy-state/current-commit\n'
    )
    run("git", "add", "ops", cwd=work)
    run("git", "commit", "-m", "test release", cwd=work)
    sha = run("git", "rev-parse", "HEAD", cwd=work)
    run("git", "remote", "add", "origin", str(origin), cwd=work)
    run("git", "push", "-u", "origin", "main", cwd=work)

    run("bash", "ops/auto_deploy.sh", cwd=work)
    assert not (work / "executions.log").exists()

    run("git", "tag", "-a", f"cmv-staging-20261116T010000Z-{sha}", sha,
        "-m", "approved", cwd=work)
    run("git", "push", "origin", f"refs/tags/cmv-staging-20261116T010000Z-{sha}", cwd=work)
    run("git", "tag", "-d", f"cmv-staging-20261116T010000Z-{sha}", cwd=work)
    run("bash", "ops/auto_deploy.sh", cwd=work)
    run("bash", "ops/auto_deploy.sh", cwd=work)
    assert (work / "executions.log").read_text().splitlines() == [sha]

    wrong_sha = "0" * 40
    run("git", "tag", "-a", f"cmv-staging-20261116T020000Z-{wrong_sha}", sha,
        "-m", "mismatch", cwd=work)
    run("git", "push", "origin", f"refs/tags/cmv-staging-20261116T020000Z-{wrong_sha}", cwd=work)
    run("git", "tag", "-d", f"cmv-staging-20261116T020000Z-{wrong_sha}", cwd=work)
    result = subprocess.run(["bash", "ops/auto_deploy.sh"], cwd=work,
                            text=True, capture_output=True)
    assert result.returncode != 0
    assert "mismatch" in result.stderr
    assert (work / "executions.log").read_text().splitlines() == [sha]
