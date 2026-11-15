"""Exercise release selection without a network connection or Docker daemon."""
import shutil
import subprocess
import os
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


def test_failed_container_start_restores_previous_commit(tmp_path):
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    run("git", "init", "--bare", str(origin), cwd=tmp_path)
    run("git", "init", "-b", "main", str(work), cwd=tmp_path)
    run("git", "config", "user.email", "test@example.invalid", cwd=work)
    run("git", "config", "user.name", "Test", cwd=work)
    (work / "ops").mkdir()
    shutil.copy(ROOT / "ops/deploy.sh", work / "ops/deploy.sh")
    (work / "ops/check_health.sh").write_text("#!/bin/bash\nexit 0\n")
    (work / ".gitignore").write_text(".env\n.deploy-state/\nbackups/\n")
    (work / "release-state").write_text("good\n")
    run("git", "add", ".", cwd=work)
    run("git", "commit", "-m", "working version", cwd=work)
    previous = run("git", "rev-parse", "HEAD", cwd=work)
    (work / "release-state").write_text("bad\n")
    run("git", "commit", "-am", "broken version", cwd=work)
    target = run("git", "rev-parse", "HEAD", cwd=work)
    run("git", "remote", "add", "origin", str(origin), cwd=work)
    run("git", "push", "-u", "origin", "main", cwd=work)
    run("git", "checkout", "--detach", previous, cwd=work)
    (work / ".env").write_text("POSTGRES_PASSWORD=testing-only\nSITE_DOMAIN=example.invalid\n")
    docker = bin_dir / "docker"
    docker.write_text(
        '#!/bin/bash\n'
        'if [[ "$1 $2" == "compose up" && $(cat release-state) == bad ]]; then exit 1; fi\n'
        'exit 0\n'
    )
    docker.chmod(0o755)
    result = subprocess.run(["bash", "ops/deploy.sh", target], cwd=work,
                            env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"},
                            text=True, capture_output=True)
    assert result.returncode != 0
    assert run("git", "rev-parse", "HEAD", cwd=work) == previous
    assert (work / ".deploy-state/previous-commit").read_text().strip() == previous
    assert not (work / ".deploy-state/current-commit").exists()

