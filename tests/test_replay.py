import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
import pytest
from clockweave.analysis import analyze
from clockweave.replay import verify_report
from clockweave.ingest import load_capture
from clockweave.contract import load_contract
from clockweave.model import InputSource
from .helpers import contract,rpc_doc,otlp,span,jaeger,attr,write_json

def case(tmp_path,doc=None,con=None):
    p=write_json(tmp_path/'trace.json',rpc_doc() if doc is None else doc);cp=write_json(tmp_path/'contract.json',contract() if con is None else con)
    return analyze(load_capture([InputSource(p)]),load_contract(cp)),p,cp

def test_valid_replay(tmp_path):
    for start in (248,240):
        r,p,c=case(tmp_path,rpc_doc(start));assert verify_report(r,[InputSource(p)],c)['valid']

def test_disconnected_one_sided_and_anchor(tmp_path):
    con=contract();con['anchor']['domain']='C';con['boundaries'][0]['relations']=con['boundaries'][0]['relations'][:1]
    d=rpc_doc();d['resourceSpans']+=otlp([span(99,trace=99)],domain='Z')['resourceSpans']
    r,p,c=case(tmp_path,d,con);assert verify_report(r,[InputSource(p)],c)['valid']

def test_same_domain_and_insufficient(tmp_path):
    con=contract();con['identities'][0]['domain']={'literal':'A'}
    r,p,c=case(tmp_path,con=con);assert verify_report(r,[InputSource(p)],c)['valid']
    r,p,c=case(tmp_path,otlp([]));assert verify_report(r,[InputSource(p)],c)['valid']
    con=contract();con['provenance']['state']='adjusted';r,p,c=case(tmp_path,con=con);assert verify_report(r,[InputSource(p)],c)['valid']

def test_jaeger_and_jsonl_replay(tmp_path):
    d=jaeger();d['data'][0]['processes']['p1']['tags']=[{'key':'clockweave.clock.domain','type':'string','value':'A'},{'key':'clockweave.clock.epoch','type':'string','value':'driver'}]
    r,p,c=case(tmp_path,d);assert verify_report(r,[InputSource(p)],c)['valid']
    p=tmp_path/'lines.jsonl';p.write_text('\n\n'.join(json.dumps({'resourceSpans':[r]}) for r in rpc_doc()['resourceSpans']))
    r=analyze(load_capture([InputSource(p)]),load_contract(c));assert verify_report(r,[InputSource(p)],c)['valid']

@pytest.mark.parametrize('mutation',[
    lambda r:r['constraints'].pop(),
    lambda r:r['observations'].pop(),
    lambda r:r['coverage'].update(selected_pairs=99),
    lambda r:r['coverage'].update(graph_edge_count=True),
    lambda r:r['constraints'][0].update(weight_ns='999'),
    lambda r:r['variables'][0].update(epoch='forged'),
    lambda r:r['qualification']['pairs'].pop(),
    lambda r:r['solution']['example_ns'].update(v0='1'),
    lambda r:r['solution']['example_ns'].pop('v2'),
    lambda r:r['solution']['ranges'][1]['upper'].update(value_ns='999'),
    lambda r:r['solution']['ranges'][1]['lower']['attaining_ns'].update(v1='999'),
    lambda r:r['solution']['ranges'][1]['upper'].update(path=[]),
    lambda r:r.update(components=[]),
    lambda r:r.update(reasons=[{'code':'forged','message':'forged','sources':[]}]),
])
def test_report_mutations_rejected(tmp_path,mutation):
    r,p,c=case(tmp_path);mutation(r)
    assert not verify_report(r,[InputSource(p)],c)['valid']

def test_false_cycles_rejected(tmp_path):
    r,p,c=case(tmp_path,rpc_doc(240));r['contradiction']['sum_ns']='-7'
    assert not verify_report(r,[InputSource(p)],c)['valid']
    r,p,c=case(tmp_path,rpc_doc(240));r['contradiction']['constraint_ids']=r['contradiction']['constraint_ids'][:1]
    assert not verify_report(r,[InputSource(p)],c)['valid']

def test_false_unbounded_cut_rejected(tmp_path):
    con=contract();con['boundaries'][0]['relations']=con['boundaries'][0]['relations'][:1]
    r,p,c=case(tmp_path,con=con)
    for row in r['solution']['ranges']:
        for side in ('lower','upper'):
            if row[side]['value_ns'] is None:row[side]['reachable']=[]
    assert not verify_report(r,[InputSource(p)],c)['valid']

def test_changed_endpoint_even_with_forged_hash_rejected(tmp_path):
    r,p,c=case(tmp_path);old=r['inputs'][0]['sha256'];d=json.loads(p.read_text());d['resourceSpans'][0]['scopeSpans'][0]['spans'][0]['startTimeUnixNano']='1800000000000000002';write_json(p,d);new=hashlib.sha256(p.read_bytes()).hexdigest()
    r=json.loads(json.dumps(r).replace(old,new));r['inputs'][0]['bytes']=p.stat().st_size
    assert not verify_report(r,[InputSource(p)],c)['valid']

def test_changed_mapping_even_with_forged_hash_rejected(tmp_path):
    r,p,c=case(tmp_path);con=json.loads(c.read_text());con['identities'][0]['domain']={'literal':'A'};write_json(c,con)
    loaded=load_contract(c);r['contract']={'data':loaded.data,'sha256':loaded.sha256,'canonical_sha256':loaded.canonical_sha256}
    assert not verify_report(r,[InputSource(p)],c)['valid']

def test_reference_does_not_import_production_semantics(tmp_path):
    r,p,c=case(tmp_path);rp=write_json(tmp_path/'report.json',r)
    script='''import sys,importlib.abc,json
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname in {'clockweave.ingest','clockweave.contract','clockweave.extract','clockweave.graph','clockweave.analysis'}:raise RuntimeError('Production semantics imported: '+fullname)
sys.meta_path.insert(0,Block())
from clockweave.replay import verify_report
from clockweave.model import InputSource
from pathlib import Path
result=verify_report(json.loads(Path(sys.argv[1]).read_text()),[InputSource(Path(sys.argv[2]))],Path(sys.argv[3]))
assert result['valid'],result
'''
    result=subprocess.run([sys.executable,'-c',script,str(rp),str(p),str(c)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr

def test_reference_reader_differential_valid_shapes(tmp_path):
    from clockweave.replay_input import read_capture
    from clockweave.extract import observation
    docs=[rpc_doc(),otlp([]),otlp([span(attributes=[attr('integer',17),attr('bool',True),{'key':'float','value':{'doubleValue':1}}, {'key':'nested','value':{'kvlistValue':{'values':[attr('inner','x')]}}}, {'key':'bytes','value':{'bytesValue':'YQ=='}}])]),jaeger()]
    for i,doc in enumerate(docs):
        p=write_json(tmp_path/f'{i}.json',doc);sources=[InputSource(p)]
        actual=load_capture(sources);observations,files,duplicates=read_capture(sources)
        assert json.dumps(observations,sort_keys=True)==json.dumps([observation(s) for s in actual.spans],sort_keys=True)
        assert files==list(actual.inputs) and duplicates==actual.duplicate_observations
