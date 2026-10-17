"""Independent-review findings, pinned before repairs."""
import copy
import hashlib
import json
from pathlib import Path
import pytest
from clockweave import InputSource,ClockWeaveError,load_capture,load_contract,analyze,verify_report,render_html,inspect_capture
from clockweave.model import Capture
from .helpers import otlp,span,attr,jaeger,contract,rpc_doc,write_json

@pytest.mark.parametrize('fmt',['auto','otlp-json','otlp-jsonl'])
def test_empty_otlp_request_is_insufficient(tmp_path,fmt):
    p=write_json(tmp_path/'empty.json',{});c=load_contract(write_json(tmp_path/'c.json',contract()))
    cap=load_capture([InputSource(p,fmt)]);r=analyze(cap,c)
    assert r['status']=='insufficient_evidence' and verify_report(r,[InputSource(p,fmt)],tmp_path/'c.json')['valid']

def test_jaeger_unhashable_process_id_is_structured_invalid(tmp_path):
    d=jaeger();d['data'][0]['spans'][0]['processID']=[]
    with pytest.raises(ClockWeaveError) as e:load_capture([InputSource(write_json(tmp_path/'t.json',d))])
    assert e.value.kind=='invalid_input'

def test_jaeger_binary_span_kind_is_unspecified_metadata(tmp_path):
    d=jaeger();d['data'][0]['spans'][0]['tags']=[{'key':'span.kind','type':'binary','value':'AA=='}]
    s=load_capture([InputSource(write_json(tmp_path/'t.json',d))]).spans[0]
    assert s.kind==0 and isinstance(s.attributes['span.kind'],dict)

@pytest.mark.parametrize('case',['huge_double','huge_timestamp'])
def test_numeric_conversion_failures_are_structured(tmp_path,case):
    d=rpc_doc();c=contract()
    if case=='huge_double':d['resourceSpans'][0]['scopeSpans'][0]['spans'][0]['attributes']=[{'key':'n','value':{'doubleValue':10**400}}]
    elif case=='huge_timestamp':d['resourceSpans'][0]['scopeSpans'][0]['spans'][0]['startTimeUnixNano']='9'*5000
    else:c['boundaries'][0]['relations'][0]['slack_ns']='9'*5000
    p=write_json(tmp_path/'t.json',d);cp=write_json(tmp_path/'c.json',c)
    with pytest.raises(ClockWeaveError):analyze(load_capture([InputSource(p)]),load_contract(cp))

def colliding_values():
    return {'bytesValue':'YQ=='},{'kvlistValue':{'values':[{'key':'__otlp_bytes__','value':{'stringValue':'YQ=='}}]}}

def test_bytes_and_kvlist_are_conflicting_duplicate_types(tmp_path):
    binary,kv=colliding_values()
    d=otlp([span(attributes=[{'key':'payload','value':binary}]),span(attributes=[{'key':'payload','value':kv}])])
    with pytest.raises(ClockWeaveError,match='conflict'):load_capture([InputSource(write_json(tmp_path/'t.json',d))])

def test_rehashed_bytes_to_kvlist_change_rejected(tmp_path):
    binary,kv=colliding_values();d=rpc_doc();d['resourceSpans'][0]['scopeSpans'][0]['spans'][0]['attributes']=[{'key':'payload','value':binary}]
    p=write_json(tmp_path/'t.json',d);cp=write_json(tmp_path/'c.json',contract());r=analyze(load_capture([InputSource(p)]),load_contract(cp));old=r['inputs'][0]['sha256']
    d['resourceSpans'][0]['scopeSpans'][0]['spans'][0]['attributes'][0]['value']=kv;write_json(p,d)
    r=json.loads(json.dumps(r).replace(old,hashlib.sha256(p.read_bytes()).hexdigest()));r['inputs'][0]['bytes']=p.stat().st_size
    assert not verify_report(r,[InputSource(p)],cp)['valid']

def test_duplicate_source_multiset_reordering_replays(tmp_path):
    a=write_json(tmp_path/'a.json',rpc_doc());b=write_json(tmp_path/'b.json',rpc_doc());c=write_json(tmp_path/'c.json',contract())
    sources=[InputSource(a),InputSource(b)];r=analyze(load_capture(sources),load_contract(c))
    assert verify_report(r,sources[::-1],c)['valid']
    other=analyze(load_capture(sources[::-1]),load_contract(c))
    assert r==other

@pytest.mark.parametrize('mutate',[
 lambda r:r.update(interpretation='Independent verification against the original raw inputs and contract succeeded.'),
 lambda r:r.update(coverage={}),
 lambda r:r['qualification'].update(spans=[False]),
 lambda r:r['qualification'].update(pairs=[123]),
 lambda r:r['observations'][0].update(scope_name=9),
 lambda r:r['observations'][0].update(warnings=[False]),
 lambda r:r['observations'][0].update(issues=[123]),
 lambda r:r['reasons'].append({'code':False,'message':3,'sources':False}),
])
def test_renderer_rejects_forged_trusted_text_and_nested_schema(tmp_path,mutate):
    p=write_json(tmp_path/'t.json',rpc_doc());c=write_json(tmp_path/'c.json',contract());r=analyze(load_capture([InputSource(p)]),load_contract(c));mutate(r)
    with pytest.raises(ClockWeaveError):render_html(r)

def test_inspect_direct_capture_obeys_observed_limit(tmp_path):
    cap=load_capture([InputSource(write_json(tmp_path/'t.json',otlp()))])
    oversized=Capture(cap.spans,cap.inputs,10000)
    with pytest.raises(ClockWeaveError) as e:inspect_capture(oversized)
    assert e.value.kind=='limit_exceeded'


def test_very_large_slack_remains_exact_and_replayable(tmp_path):
    c=contract();c['boundaries'][0]['relations'][0]['slack_ns']='9'*5000
    p=write_json(tmp_path/'t.json',rpc_doc());cp=write_json(tmp_path/'c.json',c)
    r=analyze(load_capture([InputSource(p)]),load_contract(cp))
    assert r['status']=='compatible' and verify_report(r,[InputSource(p)],cp)['valid']
    assert max(len(e['weight_ns']) for e in r['constraints'])>=5000

@pytest.mark.parametrize('bad',[{},0,'',False])
def test_falsy_malformed_jaeger_warnings_rejected(tmp_path,bad):
    d=jaeger();d['data'][0]['spans'][0]['warnings']=bad
    with pytest.raises(ClockWeaveError):load_capture([InputSource(write_json(tmp_path/'t.json',d))])

def test_cli_malformed_metadata_never_mimics_incompatible(tmp_path):
    import subprocess,sys
    d=jaeger();d['data'][0]['spans'][0]['processID']=[];p=write_json(tmp_path/'t.json',d)
    result=subprocess.run([sys.executable,'-m','clockweave','inspect',str(p),'--json','-'],capture_output=True,text=True)
    assert result.returncode==2 and 'Traceback' not in result.stderr
    assert json.loads(result.stderr)['kind']=='invalid_input'

def test_cli_very_large_slack_exact(tmp_path):
    import subprocess,sys
    c=contract();c['boundaries'][0]['relations'][0]['slack_ns']='9'*5000;p=write_json(tmp_path/'t.json',rpc_doc());cp=write_json(tmp_path/'c.json',c)
    result=subprocess.run([sys.executable,'-m','clockweave','analyze',str(p),'--contract',str(cp),'--json','-'],capture_output=True,text=True)
    assert result.returncode==0 and 'Traceback' not in result.stderr
    assert json.loads(result.stdout)['status']=='compatible'

def test_repeat_source_occurrences_preserved_under_ordering(tmp_path):
    a=write_json(tmp_path/'a.json',rpc_doc());b=write_json(tmp_path/'b.json',rpc_doc());c=write_json(tmp_path/'c.json',contract())
    r=analyze(load_capture([InputSource(a),InputSource(b),InputSource(a)]),load_contract(c))
    assert r['coverage']['duplicate_observations']==12 and len(r['observations'][0]['sources'])==3
    assert verify_report(r,[InputSource(b),InputSource(a),InputSource(a)],c)['valid']

def test_nested_complex_attribute_types_replay(tmp_path):
    binary,kv=colliding_values();d=rpc_doc();d['resourceSpans'][0]['scopeSpans'][0]['spans'][0]['attributes']=[{'key':'nested','value':{'arrayValue':{'values':[binary,kv]}}}]
    p=write_json(tmp_path/'t.json',d);c=write_json(tmp_path/'c.json',contract());r=analyze(load_capture([InputSource(p)]),load_contract(c))
    values=r['observations'][0]['attributes']['nested'];assert values[0]!=values[1]
    assert verify_report(r,[InputSource(p)],c)['valid']

def test_analyze_direct_capture_obeys_total_bytes(tmp_path):
    cap=load_capture([InputSource(write_json(tmp_path/'t.json',rpc_doc()))]);records=copy.deepcopy(cap.inputs);records[0]['bytes']=8388609
    oversized=Capture(cap.spans,records,cap.duplicate_observations);c=load_contract(write_json(tmp_path/'c.json',contract()))
    with pytest.raises(ClockWeaveError) as e:analyze(oversized,c)
    assert e.value.kind=='limit_exceeded'
