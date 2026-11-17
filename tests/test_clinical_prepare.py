import base64
import json
import pytest
from pathlib import Path

from ops.prepare_clinical import prepare


def test_prepare_is_private_idempotent_and_does_not_activate_clinical_mode(tmp_path):
    private=tmp_path/'private'
    result=prepare(private)
    assert result == {'configuration_prepared':True,'allocation_key_prepared':True}
    config=private/'clinical.env'
    key=private/'allocation.key'
    original=config.read_bytes(),key.read_bytes()
    assert len(base64.urlsafe_b64decode(key.read_bytes().strip()))==32
    assert config.stat().st_mode & 0o777 == 0o600
    assert key.stat().st_mode & 0o777 == 0o640
    assert private.stat().st_mode & 0o777 == 0o700
    lines=dict(line.split('=',1) for line in config.read_text().splitlines())
    assert lines['CLINICAL_DB_OWNER_PASSWORD']!=lines['CLINICAL_DB_APP_PASSWORD']
    assert lines['CLINICAL_INSTITUTIONAL_APPROVAL']=='unverified'
    assert lines['CLINICAL_UAT_APPROVED']=='unverified'
    assert lines['CLINICAL_KEY_READER_GID']==str(key.stat().st_gid)
    assert 'CLINICAL_DATA_ENABLED' not in lines
    assert prepare(private)==result
    assert (config.read_bytes(),key.read_bytes())==original
    assert lines['CLINICAL_DB_OWNER_PASSWORD'] not in json.dumps(result)


def test_existing_configuration_and_key_are_never_rotated(tmp_path):
    private=tmp_path/'private';private.mkdir()
    (private/'clinical.env').write_text('OWNER_CONFIG=preserve\n')
    key=base64.urlsafe_b64encode(b'k'*32)
    (private/'allocation.key').write_bytes(key)
    with pytest.raises(RuntimeError,match='nothing was rotated'):
        prepare(private)
    assert (private/'clinical.env').read_text()=='OWNER_CONFIG=preserve\n'
    assert (private/'allocation.key').read_bytes()==key
