import json
import pytest
from clockweave.limits import DEFAULT_LIMITS
from clockweave.model import ClockWeaveError,InputSource
from clockweave.ingest import load_capture
from clockweave.contract import load_contract
from clockweave.extract import extract
from .helpers import otlp,span,contract,write_json

def test_limits_are_measured_defaults():
    assert (DEFAULT_LIMITS.max_input_bytes,DEFAULT_LIMITS.max_spans,DEFAULT_LIMITS.max_domain_epochs)==(8*1024*1024,10000,64)

def test_input_byte_boundary(tmp_path):
    p=tmp_path/'trace.json';start=json.dumps(otlp([])).encode();p.write_bytes(start+b' '*(DEFAULT_LIMITS.max_input_bytes-len(start)))
    assert not load_capture([InputSource(p)]).spans
    p.write_bytes(p.read_bytes()+b' ')
    with pytest.raises(ClockWeaveError) as e:load_capture([InputSource(p)])
    assert e.value.kind=='limit_exceeded'

def test_span_record_boundary_counts_duplicates(tmp_path):
    p=write_json(tmp_path/'trace.json',otlp([span(i=i+1,trace=i+1) for i in range(10000)]))
    assert len(load_capture([InputSource(p)]).spans)==10000
    d=json.loads(p.read_text());d['resourceSpans'][0]['scopeSpans'][0]['spans'].append(d['resourceSpans'][0]['scopeSpans'][0]['spans'][0]);write_json(p,d)
    with pytest.raises(ClockWeaveError) as e:load_capture([InputSource(p)])
    assert e.value.kind=='limit_exceeded'

def test_domain_epoch_boundary(tmp_path):
    resources=[]
    for i in range(65):resources+=otlp([span(i=i+1,trace=i+1)],domain='A' if i==0 else str(i))['resourceSpans']
    c=load_contract(write_json(tmp_path/'c.json',contract()))
    cap=load_capture([InputSource(write_json(tmp_path/'trace.json',{'resourceSpans':resources[:64]}))]);assert len(extract(cap,c).variables)==64
    cap=load_capture([InputSource(write_json(tmp_path/'trace.json',{'resourceSpans':resources}))])
    with pytest.raises(ClockWeaveError) as e:extract(cap,c)
    assert e.value.kind=='limit_exceeded'

def test_combined_input_bytes_and_cli_refusals(tmp_path):
    import subprocess,sys
    from clockweave import analyze,verify_report
    files=[]
    for name in ('a.json','b.json'):
        p=tmp_path/name;p.write_text('{}');files.append(p)
    c=write_json(tmp_path/'c.json',contract());sources=[InputSource(p) for p in files]
    report=analyze(load_capture(sources),load_contract(c))
    for p in files:p.write_bytes(b'{}'+b' '*(DEFAULT_LIMITS.max_input_bytes//2-1))
    assert all(p.stat().st_size<DEFAULT_LIMITS.max_input_bytes for p in files)
    with pytest.raises(ClockWeaveError) as e:load_capture(sources)
    assert e.value.kind=='limit_exceeded'
    assert verify_report(report,sources,c)['status']=='unsupported'
    for command in ('inspect','analyze'):
        result=subprocess.run([sys.executable,'-m','clockweave',command,*map(str,files),'--contract',str(c),'--json','-'],capture_output=True,text=True)
        assert result.returncode==4 and result.stdout=='' and json.loads(result.stderr)['kind']=='limit_exceeded'

def test_renderer_default_domain_and_observation_limits(tmp_path):
    from clockweave import analyze,render_html
    from .helpers import rpc_doc
    p=write_json(tmp_path/'t.json',rpc_doc());c=write_json(tmp_path/'c.json',contract());r=analyze(load_capture([InputSource(p)]),load_contract(c))
    r['variables']=[{'id':'v'+str(i),'domain':str(i),'epoch':'e'} for i in range(65)]
    with pytest.raises(ClockWeaveError) as e:render_html(r)
    assert e.value.kind=='limit_exceeded'
    r=analyze(load_capture([InputSource(p)]),load_contract(c));r['coverage']['duplicate_observations']=10000
    with pytest.raises(ClockWeaveError) as e:render_html(r)
    assert e.value.kind=='limit_exceeded'
