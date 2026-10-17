import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from .helpers import rpc_doc,contract,otlp,write_json

def cli(*args):return subprocess.run([sys.executable,'-m','clockweave',*map(str,args)],capture_output=True,text=True,timeout=20)

def inputs(tmp_path,last=248):return write_json(tmp_path/'trace.json',rpc_doc(last)),write_json(tmp_path/'contract.json',contract())

def test_cli_roundtrip(tmp_path):
    p,c=inputs(tmp_path);j=tmp_path/'report.json';h=tmp_path/'report.html'
    r=cli('analyze',p,'--contract',c,'--json',j,'--html',h)
    assert r.returncode==0,r.stderr
    assert json.loads(j.read_text())['status']=='compatible' and h.exists()
    r=cli('verify',j,p,'--contract',c,'--json','-')
    assert r.returncode==0 and json.loads(r.stdout)['valid']
    r=cli('inspect',p,'--contract',c,'--json','-')
    assert r.returncode==0 and json.loads(r.stdout)['coverage']['selected_pairs']==3
    other=tmp_path/'render.html';r=cli('render',j,'--html',other)
    assert r.returncode==0 and 'Independent verification requires' in other.read_text()

def test_exit_codes(tmp_path):
    p,c=inputs(tmp_path,240)
    r=cli('analyze',p,'--contract',c,'--json','-');assert r.returncode==1 and json.loads(r.stdout)['status']=='incompatible'
    write_json(p,otlp([]));r=cli('analyze',p,'--contract',c,'--json','-');assert r.returncode==3
    p.write_text('{');assert cli('inspect',p,'--json','-').returncode==2
    write_json(p,{'unrecognized':True});assert cli('inspect',p,'--json','-').returncode==4

def test_false_certificate_verify_exit(tmp_path):
    p,c=inputs(tmp_path);j=tmp_path/'report.json';assert cli('analyze',p,'--contract',c,'--json',j).returncode==0
    r=json.loads(j.read_text());r['solution']['example_ns']['v0']='5';write_json(j,r)
    v=cli('verify',j,p,'--contract',c,'--json','-');assert v.returncode==5 and not json.loads(v.stdout)['valid']

@pytest.mark.parametrize('target_kind',['trace','contract','report'])
@pytest.mark.parametrize('alias_kind',['same','symlink','hardlink'])
def test_input_output_alias_rejected_even_force(tmp_path,target_kind,alias_kind):
    p,c=inputs(tmp_path);j=tmp_path/'report.json';assert cli('analyze',p,'--contract',c,'--json',j).returncode==0
    target={'trace':p,'contract':c,'report':j}[target_kind];alias=tmp_path/'alias'
    if alias_kind=='same':alias=target
    elif alias_kind=='hardlink':os.link(target,alias)
    else:
        try:alias.symlink_to(target)
        except OSError:pytest.skip('symlinks unavailable on this platform')
    original=target.read_bytes()
    args=['render',j,'--html',alias,'--force'] if target_kind=='report' else ['analyze',p,'--contract',c,'--json',alias,'--force']
    r=cli(*args)
    assert r.returncode==2,r.stderr
    assert target.read_bytes()==original

def test_output_alias_each_other_rejected(tmp_path):
    p,c=inputs(tmp_path);out=tmp_path/'same-output'
    r=cli('analyze',p,'--contract',c,'--json',out,'--html',out,'--force')
    assert r.returncode==2 and not out.exists()

def test_existing_output_requires_force(tmp_path):
    p,c=inputs(tmp_path);out=tmp_path/'report.json';out.write_text('preserve')
    assert cli('analyze',p,'--contract',c,'--json',out).returncode==2
    assert out.read_text()=='preserve'
    assert cli('analyze',p,'--contract',c,'--json',out,'--force').returncode==0
