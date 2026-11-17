"""CI-only disposable key mount check. Never uses an existing clinical key."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ops.prepare_clinical import prepare


def main():
    with tempfile.TemporaryDirectory(prefix='nims-disposable-key-') as scratch:
        private=Path(scratch)/'private'
        prepare(private)
        key=private/'allocation.key'
        gid=str(key.stat().st_gid)
        config=json.loads(subprocess.check_output(['docker','compose','--env-file',
            str(private/'clinical.env'),'-f','compose.clinical.yaml','config','--format','json']))
        assert list(map(str,config['services']['api']['group_add']))==[gid]
        image=subprocess.check_output(['docker','compose','images','-q','api']).decode().strip()
        assert image and '\n' not in image
        primary='65533' if gid=='65534' else '65534'
        base=['docker','run','--rm','--network','none','--read-only','--user','10001:'+primary,
              '-v',str(key)+':/run/key:ro']
        program=['python','-c',"from pathlib import Path; assert len(Path('/run/key').read_bytes().strip())==44"]
        denied=subprocess.run(base+[image]+program,stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,timeout=30)
        assert denied.returncode!=0,'Key unexpectedly readable without its intended group'
        subprocess.run(base+['--group-add',gid,image]+program,check=True,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30)
    print('Disposable key mount verified: UID 10001 requires the intended supplemental group.')


if __name__=='__main__':main()
