#!/usr/bin/env python3
"""Verify only public health/build identity; never authenticate or fetch records."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.build_identity import digest_entries, SOURCE_SUFFIXES


def git(*args):
    return subprocess.check_output(['git',*args],stderr=subprocess.DEVNULL)


def expected_fingerprint(target):
    if not re.fullmatch('[0-9a-f]{40}',target): raise ValueError('Full target SHA required')
    names=git('ls-tree','-r','--name-only',target,'app/').decode().splitlines()
    entries=[(name[4:],git('show',target+':'+name)) for name in names
             if Path(name).suffix in SOURCE_SUFFIXES]
    if not entries: raise ValueError('Target contains no application source')
    return digest_entries(entries)


def is_identity_bootstrap(target):
    # A source-only match is permitted ONLY for the commit that introduces
    # build identity. Subsequent ops-only releases must match their commit.
    try:
        git('cat-file','-e',target+'^:app/build_identity.py')
        return False
    except subprocess.CalledProcessError:
        return True


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None


def fetch_status(url):
    request=urllib.request.Request(url,headers={'Accept':'application/json','Cache-Control':'no-cache'})
    with urllib.request.build_opener(NoRedirect).open(request,timeout=8) as response:
        return json.loads(response.read(8193))


def matches(data,target,fingerprint,bootstrap=False):
    if not isinstance(data,dict) or data.get('ok') is not True or data.get('service') not in {'staging','clinical'}:return False
    if data.get('build_fingerprint')!=fingerprint:return False
    return data.get('app_commit')==target or (bootstrap and data.get('app_commit') is None)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--target',required=True)
    parser.add_argument('--url',required=True)
    parser.add_argument('--timeout',type=int,default=540)
    args=parser.parse_args()
    url=urlparse(args.url)
    if url.scheme!='https' or not url.hostname or url.path not in ('','/') or url.username or url.password or url.query or url.fragment:
        parser.error('Use a plain HTTPS application origin')
    expected=expected_fingerprint(args.target)
    bootstrap=is_identity_bootstrap(args.target)
    deadline=time.monotonic()+min(max(args.timeout,1),540)
    endpoint=args.url.rstrip('/')+'/readyz'
    while True:
        try:
            data=fetch_status(endpoint)
            if matches(data,args.target,expected,bootstrap):
                scope='source-only bootstrap; image commit not stamped' if data.get('app_commit') is None else 'exact image commit and source'
                print('Verified public database readiness and '+scope+'.')
                print('Target: '+args.target+'; application source SHA256: '+expected)
                return 0
        except (OSError,ValueError,urllib.error.HTTPError):
            pass  # Never print response bodies, headers, cookies or configuration.
        if time.monotonic()>=deadline:
            print('Deployment verification timed out; published release is not confirmed live.',file=sys.stderr)
            return 1
        time.sleep(min(15,max(0,deadline-time.monotonic())))


if __name__=='__main__':raise SystemExit(main())

