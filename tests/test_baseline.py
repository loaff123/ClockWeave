"""Optional upstream runtime integration, explicitly enabled by a pinned binary."""
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from clockweave.ingest import load_capture
from clockweave.model import InputSource

ROOT=Path(__file__).resolve().parents[1]

def test_official_jaeger_runtime(tmp_path):
    binary=os.environ.get('CLOCKWEAVE_JAEGER_BINARY');capture=os.environ.get('CLOCKWEAVE_BASELINE_CAPTURE')
    if not binary or not capture:pytest.skip('requires pinned external Jaeger binary and original capture')
    script=ROOT/'tools'/'compare_jaeger.py'
    assert script.exists(),'official runtime comparison is not implemented'
    result=subprocess.run([sys.executable,str(script),'--binary',binary,'--capture',capture,'--output',str(tmp_path/'baseline')],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr
    m=json.loads((tmp_path/'baseline'/'comparison.json').read_text())
    assert m['upstream_version']=='2.22.0' and m['raw_endpoint_roundtrip_exact'] is True
    assert m['span_count']>=16 and m['changed_span_count']>0
    raw=load_capture([InputSource(tmp_path/'baseline'/'raw.jaeger.json')]);adjusted=load_capture([InputSource(tmp_path/'baseline'/'adjusted.jaeger.json')])
    assert len(raw.spans)==len(adjusted.spans)==m['span_count']
