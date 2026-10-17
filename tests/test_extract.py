import copy
from clockweave.contract import load_contract
from clockweave.extract import extract, inspect_capture
from clockweave.ingest import load_capture
from clockweave.model import InputSource
from .helpers import contract, rpc_doc, otlp, span, attr, write_json

def run(tmp_path,d=None,c=None):
    cap=load_capture([InputSource(write_json(tmp_path/'t.json',d if d is not None else rpc_doc()))])
    con=load_contract(write_json(tmp_path/'c.json',c if c is not None else contract()))
    return extract(cap,con)

def test_start_only_headers_pair(tmp_path):
    c=contract();c['boundaries'][0]['relations']=c['boundaries'][0]['relations'][:1]
    e=run(tmp_path,c=c)
    assert e.coverage['start_relations']==3 and e.coverage['end_relations']==0
    assert [x.weight_ns for x in e.constraints]==[20,30,48]

def test_no_service_clock_fallback(tmp_path):
    d=rpc_doc()
    for r in d['resourceSpans']:r['resource']['attributes']=[attr('service.name','same-service')]
    e=run(tmp_path,d)
    assert e.coverage['unresolved_spans']==6 and not e.constraints

def test_epoch_splits_variables(tmp_path):
    d=rpc_doc();d['resourceSpans'][-1]['resource']['attributes'][1]=attr('clockweave.clock.epoch','restarted')
    e=run(tmp_path,d)
    assert len(e.variables)==4
    assert {(v['domain'],v['epoch']) for v in e.variables if v['domain']=='C'}=={('C','driver'),('C','restarted')}

def test_identity_ambiguity(tmp_path):
    c=contract();c['identities'].append({**c['identities'][0],'id':'second'})
    e=run(tmp_path,c=c)
    assert not e.constraints and all(s['reason']=='ambiguous_identity' for s in e.qualification['spans'])

def test_slack_is_independent(tmp_path):
    before=run(tmp_path);c=contract();c['boundaries'][0]['relations'][0]['slack_ns']='7'
    after=run(tmp_path,c=c)
    for a,b in zip(before.constraints,after.constraints):
        assert b.weight_ns-a.weight_ns==(7 if a.relation=='start_order' else 0)

def test_arbitrary_anchor(tmp_path):
    c=contract();c['anchor']['domain']='C';e=run(tmp_path,c=c)
    assert next(v for v in e.variables if v['id']==e.anchor)['domain']=='C'

def test_missing_anchor_reason(tmp_path):
    c=contract();c['anchor']['domain']='Z'
    assert 'missing_anchor' in [r['code'] for r in run(tmp_path,c=c).reasons]

def test_ambiguous_boundary(tmp_path):
    c=contract();c['boundaries'].append({**c['boundaries'][0],'id':'other'})
    e=run(tmp_path,c=c)
    assert not e.constraints and e.coverage['unresolved_pairs']==3
    assert all(p['reason']=='ambiguous_boundary' for p in e.qualification['pairs'])

def test_missing_parent(tmp_path):
    d=rpc_doc();d['resourceSpans']=d['resourceSpans'][1:]
    e=run(tmp_path,d)
    assert any(p['reason']=='missing_parent' for p in e.qualification['pairs'])

def test_excluded_async(tmp_path):
    d=rpc_doc();d['resourceSpans']+=otlp([span(100,trace=100,kind=4),span(101,trace=100,kind=5,parent=100)])['resourceSpans']
    e=run(tmp_path,d)
    assert e.coverage['excluded_spans']==2 and e.coverage['selected_pairs']==3
    assert any(p['reason']=='excluded' for p in e.qualification['pairs'])

def test_partial_end_retains_start_relation(tmp_path):
    d=rpc_doc();del d['resourceSpans'][0]['scopeSpans'][0]['spans'][0]['endTimeUnixNano']
    e=run(tmp_path,d)
    assert e.coverage['start_relations']==3 and e.coverage['end_relations']==2
    assert any('missing_endpoint' in p['unqualified_relations'].values() for p in e.qualification['pairs'])

def test_negative_duration_unavailable(tmp_path):
    d=rpc_doc();s=d['resourceSpans'][0]['scopeSpans'][0]['spans'][0];s['endTimeUnixNano']='1'
    e=run(tmp_path,d)
    assert e.coverage['selected_pairs']==2

def test_provenance_reasons(tmp_path):
    for state in ('unknown','adjusted'):
        c=contract();c['provenance']['state']=state
        assert 'provenance_'+state in [r['code'] for r in run(tmp_path,c=c).reasons]
    d=rpc_doc();d['resourceSpans'][0]['resource']['attributes'].append(attr('clockweave.timestamp.state','adjusted'))
    assert 'adjusted_marker' in [r['code'] for r in run(tmp_path,d).reasons]

def test_same_domain_edges_retained(tmp_path):
    d=rpc_doc()
    for r in d['resourceSpans']:r['resource']['attributes'][0]=attr('clockweave.clock.domain','A')
    e=run(tmp_path,d)
    assert len(e.constraints)==6 and all(x.from_id==x.to_id for x in e.constraints)

def test_deterministic_constraint_ids(tmp_path):
    d=rpc_doc();before=run(tmp_path,d);d['resourceSpans'].reverse();after=run(tmp_path,d)
    assert [(e.id,e.from_id,e.to_id,e.weight_ns) for e in before.constraints]==[(e.id,e.from_id,e.to_id,e.weight_ns) for e in after.constraints]

def test_inventory_without_contract(tmp_path):
    cap=load_capture([InputSource(write_json(tmp_path/'t.json',rpc_doc()))])
    i=inspect_capture(cap)
    assert i['schema']=='clockweave.inventory.v1' and i['span_count']==6
    assert 'clockweave.clock.domain' in i['resource_attribute_keys']
