from email.message import Message
import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError
import pytest
from ops import transfer_clinical_backup as transfer
from ops.clinical_maintenance import offsite_reference

def test_private_release_upload_requires_readback_and_is_idempotent(tmp_path,monkeypatch):
    root=tmp_path/'encrypted';root.mkdir();readback=tmp_path/'readback'
    raw=b'CI ENCRYPTED ARCHIVE FIXTURE ONLY';digest=hashlib.sha256(raw).hexdigest()
    metadata={'id':'20261117T120000Z-abcdef012345','created_at':'2026-11-17T12:00:00+00:00','sha256':digest}
    (root/'metadata.json').write_text(json.dumps(metadata));(root/'bundle.tar').write_bytes(raw)
    actual_path=Path
    def mapped_path(value):
        return actual_path(str(value).replace('/tmp/nims-encrypted',str(root)).replace('/tmp/nims-readback',str(readback)))
    monkeypatch.setattr(transfer,'Path',mapped_path)
    release={'id':91,'tag_name':'cmv-encrypted-recovery-2026-11','draft':True}
    assets=[];uploads=[]
    def github(path,data=None):
        if path=='':return {'id':1455709378,'private':True}
        if path.startswith('/releases?'):return [release]
        if '/assets?' in path:return assets
        raise AssertionError(path)
    monkeypatch.setattr(transfer,'github_json',github)
    monkeypatch.setattr(transfer,'find_private_release',lambda tag:release)
    monkeypatch.setenv('GITHUB_TOKEN','CI-FAKE-TOKEN')
    def read(url,headers=None,data=None,**kw):
        assert url.startswith('https://uploads.github.com/repos/'+transfer.REPO+'/releases/91/assets?name=clinical-')
        assert data==raw
        uploads.append(url)
        asset={'id':93,'size':len(raw),'state':'uploaded','name':'clinical-'+metadata['id']+'.tar'}
        assets.append(asset);return json.dumps(asset).encode()
    monkeypatch.setattr(transfer,'read',read)
    monkeypatch.setattr(transfer,'download_release_asset',lambda ident:raw)
    transfer.store_release()
    assert (readback/'bundle.tar').read_bytes()==raw
    assert json.loads((root/'remote.json').read_text())=={'release_id':91,'asset_id':93}
    transfer.store_release();assert len(uploads)==1
    monkeypatch.setattr(transfer,'download_release_asset',lambda ident:b'corrupted ciphertext')
    with pytest.raises(SystemExit,match='readback hash mismatch'):transfer.store_release()

def test_release_download_strips_token_before_cdn_redirect(monkeypatch):
    monkeypatch.setenv('GITHUB_TOKEN','CI-FAKE-TOKEN')
    def read(url,headers=None,**kwargs):
        if url.startswith(transfer.API):
            assert headers['Authorization']=='Bearer CI-FAKE-TOKEN'
            h=Message();h['Location']='https://release-assets.githubusercontent.com/fixture?temporary=signature'
            raise HTTPError(url,302,'redirect',h,None)
        assert url.startswith('https://release-assets.githubusercontent.com/')
        assert 'Authorization' not in headers
        return b'CI CIPHERTEXT'
    monkeypatch.setattr(transfer,'read',read)
    assert transfer.download_release_asset(93)==b'CI CIPHERTEXT'

@pytest.mark.parametrize('url',['http://release-assets.githubusercontent.com/test',
    'https://example.org/test','https://127.0.0.1/private','file:///etc/passwd'])
def test_release_download_rejects_unexpected_redirects(monkeypatch,url):
    monkeypatch.setenv('GITHUB_TOKEN','CI-FAKE-TOKEN')
    def read(*args,**kw):
        h=Message();h['Location']=url
        raise HTTPError(transfer.API,302,'redirect',h,None)
    monkeypatch.setattr(transfer,'read',read)
    with pytest.raises(SystemExit,match='redirect rejected'):transfer.download_release_asset(93)

def test_remote_receipts_describe_the_actual_storage_kind():
    assert offsite_reference({'release_id':91,'asset_id':93})=='github-release:1455709378:91:93'
    assert offsite_reference({'artifact_id':94})=='github-artifact:1455709378:94'
    for invalid in ({'release_id':91},{'asset_id':93},{'release_id':True,'asset_id':93},
                    {'release_id':91,'asset_id':-1},{'release_id':91,'asset_id':93,'artifact_id':94}):
        assert offsite_reference(invalid) is None

def test_release_discovery_paginates_metadata_without_embedded_assets(monkeypatch):
    monkeypatch.setenv('GITHUB_TOKEN','CI-FAKE-TOKEN');seen=[]
    def read(url,headers=None,data=None,limit=None):
        assert url=='https://api.github.com/graphql' and limit==262144
        request=json.loads(data);assert 'releaseAssets' not in request['query']
        cursor=request['variables']['cursor'];seen.append(cursor)
        if cursor is None:
            value={'nodes':[{'databaseId':10,'tagName':'unrelated','isDraft':False}],
                   'pageInfo':{'hasNextPage':True,'endCursor':'next-page'}}
        else:
            value={'nodes':[{'databaseId':91,'tagName':'cmv-encrypted-recovery-2026-11','isDraft':True}],
                   'pageInfo':{'hasNextPage':False,'endCursor':'final'}}
        return json.dumps({'data':{'repository':{'releases':value}}}).encode()
    monkeypatch.setattr(transfer,'read',read)
    assert transfer.find_private_release('cmv-encrypted-recovery-2026-11')['id']==91
    assert seen==[None,'next-page']
