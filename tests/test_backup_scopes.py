"""Backup/restore script regression checks using disposable mock programs.

No cloud credentials, databases, hospital records, or network requests.
"""
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
FAKE_DOCKER=r'''#!/usr/bin/env python3
import os,sys
from pathlib import Path
args=sys.argv[1:]
with open(os.environ["MOCK_DOCKER_LOG"],"a") as f:f.write(" ".join(args)+"\n")
if "nims_cmv_clinical" in os.environ.get("MOCK_DATABASE",""):
    expected="nims_cmv_clinical"
else:expected="nims_ecrf"
if any("printf" in a for a in args):
    sys.stdout.write(os.environ.get("MOCK_DATABASE",expected))
elif any("pg_dump" in a for a in args):
    sys.stdout.buffer.write(b"FAKE-DATABASE-FOR-UNIT-TEST-ONLY\n")
else:
    sys.stdin.buffer.read()
    if os.environ.get("MOCK_RESTORE_FAIL")=="1":sys.exit(2)
'''
FAKE_RCLONE=r'''#!/usr/bin/env python3
import os,sys
from pathlib import Path
args=sys.argv[1:]
dir=Path(os.environ["MOCK_REMOTE_DIR"])
dir.mkdir(parents=True,exist_ok=True)
if args[:1]==["listremotes"]:
    print("ecrfcrypt:")
elif args[:2]==["config","show"]:
    print("[ecrfcrypt]")
    print("type = "+os.environ.get("MOCK_CRYPT_TYPE","crypt"))
elif args[:1]==["copyto"]:
    a,b=args[1:3]
    if a.startswith("ecrfcrypt:"):
        data=(dir/Path(a).name).read_bytes()
        Path(b).write_bytes(data)
    else:
        (dir/Path(b).name).write_bytes(Path(a).read_bytes())
elif args[:1]==["cat"]:
    sys.stdout.buffer.write((dir/Path(args[1]).name).read_bytes())
else:sys.exit(2)
'''

def harness(tmp_path,scope="staging"):
    bindir=tmp_path/"bin";bindir.mkdir()
    for name,source in (("docker",FAKE_DOCKER),("rclone",FAKE_RCLONE)):
        path=bindir/name
        path.write_text(source)
        path.chmod(0o755)
    config=tmp_path/"rclone.conf"
    config.write_text("[ecrfcrypt]\ntype = crypt\n")
    env=os.environ.copy()
    env.update({
        "PATH":str(bindir)+os.pathsep+os.environ["PATH"],
        "RCLONE_CONFIG":str(config),
        "MOCK_DOCKER_LOG":str(tmp_path/"docker.log"),
        "MOCK_REMOTE_DIR":str(tmp_path/"remote"),
        "BACKUP_SCOPE":scope,
        "BACKUP_REMOTE":"ecrfcrypt:approved-test-only",
        "BACKUP_STATUS_DIR":str(tmp_path/"status"),
        "MOCK_DATABASE":"nims_cmv_clinical" if scope=="clinical" else "nims_ecrf",
    })
    if scope=="clinical":
        private=tmp_path/"private-clinical.env"
        private.write_text("CLINICAL_DB_OWNER_PASSWORD=TEST\n")
        env["CLINICAL_ENV_FILE"]=str(private)
    return env

def run(command,env):
    return subprocess.run(["bash",str(ROOT/"ops"/command)],env=env,
                         cwd=ROOT,capture_output=True,text=True,timeout=20)

def test_encrypted_clinical_backup_writes_readable_receipt_and_uses_clinical_database(tmp_path):
    env=harness(tmp_path,"clinical")
    result=run("backup_to_drive.sh",env)
    assert result.returncode==0,result.stderr
    receipt=Path(env["BACKUP_STATUS_DIR"])/"last_success"
    assert receipt.exists()
    stamp,checksum,remote=receipt.read_text().split()
    assert remote.startswith("ecrfcrypt:approved-test-only/nims-cmv-clinical-")
    assert len(checksum)==64
    assert receipt.stat().st_mode & 0o004
    calls=Path(env["MOCK_DOCKER_LOG"]).read_text()
    assert "compose.clinical.yaml" in calls and "private-clinical.env" in calls
    assert "pg_dump" in calls

def test_backup_refuses_wrong_compose_database(tmp_path):
    env=harness(tmp_path,"clinical")
    env["MOCK_DATABASE"]="nims_ecrf"
    result=run("backup_to_drive.sh",env)
    assert result.returncode!=0
    assert "Database identity mismatch" in result.stderr
    assert not (Path(env["BACKUP_STATUS_DIR"])/"last_success").exists()

def test_backup_refuses_noncrypt_remote(tmp_path):
    env=harness(tmp_path,"clinical")
    env["MOCK_CRYPT_TYPE"]="drive"
    result=run("backup_to_drive.sh",env)
    assert result.returncode!=0
    assert "not an rclone crypt backend" in result.stderr

def test_clinical_restore_targets_separate_project_and_writes_proof_on_success(tmp_path):
    env=harness(tmp_path,"clinical")
    assert run("backup_to_drive.sh",env).returncode==0
    original=(Path(env["BACKUP_STATUS_DIR"])/"last_success").read_text()
    stamp=original.split()[0]
    result=subprocess.run(["bash",str(ROOT/"ops/restore_check.sh"),stamp,
        "nims_restore_trial"],env=env,capture_output=True,text=True,cwd=ROOT,timeout=20)
    assert result.returncode==0,result.stderr
    assert (Path(env["BACKUP_STATUS_DIR"])/"last_restore").exists()
    calls=Path(env["MOCK_DOCKER_LOG"]).read_text()
    assert "compose.clinical.yaml" in calls
    assert "TARGET_DB=nims_restore_trial" in calls

def test_failed_restore_never_creates_success_marker(tmp_path):
    env=harness(tmp_path,"clinical")
    assert run("backup_to_drive.sh",env).returncode==0
    stamp=(Path(env["BACKUP_STATUS_DIR"])/"last_success").read_text().split()[0]
    env["MOCK_RESTORE_FAIL"]="1"
    result=subprocess.run(["bash",str(ROOT/"ops/restore_check.sh"),stamp,
        "nims_restore_trial"],env=env,capture_output=True,text=True,cwd=ROOT,timeout=20)
    assert result.returncode!=0
    assert not (Path(env["BACKUP_STATUS_DIR"])/"last_restore").exists()

def test_restore_cannot_target_live_clinical_database(tmp_path):
    env=harness(tmp_path,"clinical")
    result=subprocess.run(["bash",str(ROOT/"ops/restore_check.sh"),
      "20261117T121212Z","nims_cmv_clinical"],env=env,capture_output=True,text=True)
    assert result.returncode!=0
    assert "Refusing" in result.stderr
