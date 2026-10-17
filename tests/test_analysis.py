import copy
import json
from clockweave.analysis import analyze
from clockweave.model import InputSource
from clockweave.ingest import load_capture
from clockweave.contract import load_contract
from .helpers import contract,rpc_doc,otlp,span,write_json

def report(tmp_path,doc=None,con=None):
    return analyze(load_capture([InputSource(write_json(tmp_path/'t.json',rpc_doc() if doc is None else doc))]),load_contract(write_json(tmp_path/'c.json',contract() if con is None else con)))

def test_complete_compatible_report(tmp_path):
    r=report(tmp_path)
    assert r['schema']=='clockweave.report.v1' and r['status']=='compatible'
    assert r['coverage']['raw_constraint_count']==6
    assert len(r['observations'])==6 and len(r['constraints'])==6
    assert r['observations'][0]['start_ns']=='1800000000000000001'
    assert r['solution'] and r['contradiction'] is None
    assert r['contract']['data']==load_contract(tmp_path/'c.json').data
    assert str(tmp_path) not in json.dumps(r)

def test_compatible_qualified_subset_preserves_coverage(tmp_path):
    d=rpc_doc();d['resourceSpans']+=otlp([span(i=500,trace=500,parent=999)],domain='Z')['resourceSpans']
    r=report(tmp_path,d)
    assert r['status']=='compatible' and r['coverage']['unresolved_pairs']==1
    assert len(r['variables'])==4 and len(r['components'])==2

def test_insufficient_evidence_not_unconstrained_success(tmp_path):
    for d,c,code in [(otlp([]),contract(),'no_constraints'),(rpc_doc(),{**contract(),'anchor':{'domain':'Z','epoch':'driver'}},'missing_anchor')]:
        r=report(tmp_path,d,c)
        assert r['status']=='insufficient_evidence' and r['solution'] is None and r['contradiction'] is None
        assert code in [x['code'] for x in r['reasons']]
    c=contract();c['provenance']['state']='unknown';r=report(tmp_path,con=c)
    assert r['status']=='insufficient_evidence' and len(r['constraints'])==6

def test_incompatible_source_linked_cycle(tmp_path):
    r=report(tmp_path,rpc_doc(240))
    assert r['status']=='incompatible' and r['solution'] is None
    assert r['contradiction']['sum_ns']=='-6'
    assert all(c['sources'] for c in r['constraints'])
    assert all(type(c['weight_ns']) is str for c in r['constraints'])
    assert all(type(n) is str for c in r['constraints'] for n in c['endpoint_values_ns'])
