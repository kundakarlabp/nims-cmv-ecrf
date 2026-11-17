from pathlib import Path
import subprocess

from app.build_identity import build_fingerprint, digest_entries
from ops.verify_release import expected_fingerprint, is_identity_bootstrap, matches


def test_fingerprint_is_source_only_and_order_independent():
    assert len(build_fingerprint())==64
    assert digest_entries([('b',b'2'),('a',b'1')])==digest_entries([('a',b'1'),('b',b'2')])
    assert digest_entries([('a',b'1')])!=digest_entries([('a',b'changed')])


def test_health_verification_requires_correct_mode_source_and_commit():
    sha='a'*40; fingerprint='b'*64
    data={'ok':True,'service':'staging','app_commit':sha,'build_fingerprint':fingerprint}
    assert matches(data,sha,fingerprint)
    assert not matches(dict(data,app_commit='c'*40),sha,fingerprint,True)
    assert not matches(dict(data,build_fingerprint='d'*64),sha,fingerprint)
    assert matches(dict(data,service='clinical'),sha,fingerprint)
    assert not matches(dict(data,service='unknown'),sha,fingerprint)
    assert not matches(dict(data,ok=False),sha,fingerprint)
    assert not matches(dict(data,app_commit=None),sha,fingerprint)
    assert matches(dict(data,app_commit=None),sha,fingerprint,True)
    assert not matches([],sha,fingerprint)


def test_git_expected_identity_matches_files_and_bootstrap_only_first_commit(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    def git(*args):return subprocess.check_output(['git',*args]).decode().strip()
    git('init','-b','main');git('config','user.name','Test');git('config','user.email','test@example.invalid')
    Path('base').write_text('base');git('add','.');git('commit','-m','base')
    Path('app').mkdir();Path('app/build_identity.py').write_text('# identity\n')
    Path('app/ui.html').write_text('<html>test</html>')
    git('add','.');git('commit','-m','identity')
    first=git('rev-parse','HEAD')
    expected=digest_entries([('build_identity.py',b'# identity\n'),('ui.html',b'<html>test</html>')])
    assert expected_fingerprint(first)==expected
    assert is_identity_bootstrap(first)
    Path('base').write_text('operator change');git('commit','-am','later')
    later=git('rev-parse','HEAD')
    assert expected_fingerprint(later)==expected
    assert not is_identity_bootstrap(later)

