"""A real process/HTTP/SDK workflow, independent of solver implementation."""
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
import pytest
from clockweave.model import InputSource
from clockweave.ingest import load_capture
from clockweave.contract import load_contract
from clockweave.extract import extract

ROOT=Path(__file__).resolve().parents[1]

def test_real_restart_reusable_capture(tmp_path):
    pytest.importorskip('opentelemetry.sdk.trace')
    script=ROOT/'examples'/'loopback'/'capture.py'
    contract_path=script.with_name('contract.json')
    # The workflow must exist and run before graph construction can add value.
    assert script.exists(), 'real loopback capture workflow is not implemented'
    contract_hash=hashlib.sha256(contract_path.read_bytes()).hexdigest()
    keysets=[]
    for run in range(2):
        out=tmp_path/f'capture{run}'
        result=subprocess.run([sys.executable,str(script),'--output',str(out)],capture_output=True,text=True,timeout=30)
        assert result.returncode==0,result.stderr
        meta=json.loads((out/'capture-metadata.json').read_text())
        lifecycle=meta['lifecycle']
        starts=[x for x in lifecycle if x['event']=='started' and x['domain']=='C']
        assert len(starts)==2 and starts[0]['pid']!=starts[1]['pid'] and starts[0]['epoch']!=starts[1]['epoch']
        assert all(any(stop['event']=='stopped' and stop['pid']==x['pid'] for stop in lifecycle) for x in starts)
        capture=load_capture([InputSource(out/'original.otlp.json')])
        e=extract(capture,load_contract(contract_path))
        known={(r['domain'],r['epoch']):-int(r['injected_offset_ns']) for r in meta['clocks']}
        values={v['id']:known[(v['domain'],v['epoch'])] for v in e.variables}
        assert all(values[c.to_id]-values[c.from_id]<=c.weight_ns for c in e.constraints)
        assert e.coverage['selected_pairs']>=6 and e.coverage['start_relations']==e.coverage['end_relations']+1
        assert e.coverage['excluded_spans']==2
        assert meta['per_capture_manual_annotations']==0
        assert meta['physical_host_count']==1 and meta['system_clock_modified'] is False
        assert (out/'original.pb').stat().st_size>0
        assert len(load_capture([InputSource(out/'original.otlp.jsonl')]).spans)==len(capture.spans)
        legacy=load_capture([InputSource(out/'comparison.jaeger.json')])
        assert len(legacy.spans)==len(capture.spans)
        for raw,converted in zip(capture.spans,legacy.spans):
            assert raw.key==converted.key and converted.start_ns==raw.start_ns//1000*1000
        keysets.append({s.key for s in capture.spans})
    assert keysets[0].isdisjoint(keysets[1])
    assert hashlib.sha256(contract_path.read_bytes()).hexdigest()==contract_hash
