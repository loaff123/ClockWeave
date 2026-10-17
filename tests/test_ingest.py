import copy
import hashlib
import json
import pytest
from clockweave.model import InputSource, ClockWeaveError
from clockweave.ingest import load_capture
from .helpers import otlp, span, jaeger, write_json, attr

def load(tmp_path, doc):
    return load_capture([InputSource(write_json(tmp_path/'trace.json', doc))])

def test_one_ns_above_2_pow_53(tmp_path):
    c = load(tmp_path, otlp([span(), span(2, start=1800000000000000002)]))
    assert c.spans[1].start_ns - c.spans[0].start_ns == 1
    assert c.spans[0].start_ns == 1800000000000000001

def test_jaeger_us_conversion(tmp_path):
    s = load(tmp_path, jaeger()).spans[0]
    assert (s.start_ns,s.end_ns) == (123000,130000)
    assert s.resource['service.name'] == 'demo'
    assert s.kind == 3
    assert s.key == ('00000000000000000000000000000001','0000000000000001')

def test_jsonl_sources(tmp_path):
    p=tmp_path/'trace.jsonl'; p.write_text(json.dumps(otlp([span()]))+'\n\n'+json.dumps(otlp([span(2)]))+'\n')
    c=load_capture([InputSource(p)])
    assert c.spans[1].sources[0].line == 3
    assert c.inputs[0]['document_count'] == 2

def test_empty_is_capture(tmp_path):
    assert load(tmp_path, {'resourceSpans': []}).spans == ()

def test_same_span_id_distinct_traces(tmp_path):
    assert len(load(tmp_path, otlp([span(trace=1),span(trace=2)])).spans)==2

def test_exact_duplicates_preserve_sources(tmp_path):
    p=write_json(tmp_path/'a.json',otlp()); q=write_json(tmp_path/'b.json',otlp())
    c=load_capture([InputSource(p),InputSource(q)])
    assert len(c.spans)==1 and c.duplicate_observations==1
    assert len(c.spans[0].sources)==2

def test_conflicting_duplicates_rejected(tmp_path):
    with pytest.raises(ClockWeaveError,match='conflict'):
        load(tmp_path,otlp([span(),span(end=1800000000000000099)]))

@pytest.mark.parametrize('bad',[True,False,1.5,-1,None,'1.0','1e3','',str(2**64)])
def test_bad_timestamp_invalid(tmp_path,bad):
    s=span();s['startTimeUnixNano']=bad
    with pytest.raises(ClockWeaveError) as e:load(tmp_path,otlp([s]))
    assert e.value.kind=='invalid_input'

def test_integer_token_valid(tmp_path):
    s=span();s['startTimeUnixNano']=1800000000000000001
    assert load(tmp_path,otlp([s])).spans[0].start_ns==1800000000000000001

def test_exponent_token_invalid(tmp_path):
    p=tmp_path/'a.json';p.write_text(json.dumps(otlp()).replace('"1800000000000000001"','1e3'))
    with pytest.raises(ClockWeaveError):load_capture([InputSource(p)])

def test_omitted_defaults_and_endpoints(tmp_path):
    s=span();del s['kind'];del s['endTimeUnixNano']
    a=load(tmp_path,otlp([s])).spans[0]
    assert a.kind==0 and a.end_ns is None and 'missing_end' in a.issues

def test_negative_duration_retained(tmp_path):
    a=load(tmp_path,otlp([span(start=12,end=10)])).spans[0]
    assert a.end_ns==10 and 'negative_raw_duration' in a.issues

@pytest.mark.parametrize('field,value',[('traceId','0'*32),('spanId','0'*16),('spanId','abcd'),('traceId','G'*32)])
def test_invalid_ids(tmp_path,field,value):
    s=span();s[field]=value
    with pytest.raises(ClockWeaveError):load(tmp_path,otlp([s]))

def test_uppercase_ids_and_zero_parent(tmp_path):
    s=span(i=10,trace=15,parent=0);s['traceId']=s['traceId'].upper()
    a=load(tmp_path,otlp([s])).spans[0]
    assert a.parent is None and a.key[0].endswith('f')

@pytest.mark.parametrize('raw',['{"resourceSpans":[],"resourceSpans":[]}','{"resourceSpans":[],"x":NaN}'])
def test_duplicate_json_keys_nonfinite_invalid(tmp_path,raw):
    p=tmp_path/'a.json';p.write_text(raw)
    with pytest.raises(ClockWeaveError):load_capture([InputSource(p)])

def test_duplicate_attributes_invalid(tmp_path):
    d=otlp();d['resourceSpans'][0]['resource']['attributes'].append(attr('clockweave.clock.domain','B'))
    with pytest.raises(ClockWeaveError):load(tmp_path,d)

def test_anyvalue_types_and_unknown_fields(tmp_path):
    s=span();s['futureUnknown']={'anything':1};s['attributes']=[attr('n',3),attr('b',True),{'key':'array','value':{'arrayValue':{'values':[{'stringValue':'x'}]}}}]
    a=load(tmp_path,otlp([s])).spans[0]
    assert a.attributes=={'n':3,'b':True,'array':['x']}

def test_anyvalue_multiple_alternatives_invalid(tmp_path):
    s=span();s['attributes']=[{'key':'x','value':{'stringValue':'s','intValue':'3'}}]
    with pytest.raises(ClockWeaveError):load(tmp_path,otlp([s]))

def test_legacy_scope_alias(tmp_path):
    d=otlp();r=d['resourceSpans'][0];r['instrumentationLibrarySpans']=r.pop('scopeSpans')
    assert len(load(tmp_path,d).spans)==1
    r['scopeSpans']=[]
    with pytest.raises(ClockWeaveError):load(tmp_path,d)

@pytest.mark.parametrize('doc',[[],{'foo':1},{'data':[],'resourceSpans':[]}])
def test_unsupported_shape(tmp_path,doc):
    with pytest.raises(ClockWeaveError) as e:load(tmp_path,doc)
    assert e.value.kind=='unsupported'

def test_symbolic_kind_unsupported(tmp_path):
    with pytest.raises(ClockWeaveError) as e:load(tmp_path,otlp([span(kind='SPAN_KIND_SERVER')]))
    assert e.value.kind=='unsupported'

def test_jaeger_parent_and_follows_from(tmp_path):
    d=jaeger();s=d['data'][0]['spans'][0]
    s['references']=[{'refType':'FOLLOWS_FROM','traceID':s['traceID'],'spanID':'0000000000000002'}]
    assert load(tmp_path,d).spans[0].parent is None
    s['references'][0]['refType']='CHILD_OF'
    assert load(tmp_path,d).spans[0].parent[1]=='0000000000000002'
    s['references'].append({**s['references'][0],'spanID':'0000000000000003'})
    a=load(tmp_path,d).spans[0]
    assert a.parent is None and 'ambiguous_parent' in a.issues

def test_raw_file_unchanged(tmp_path):
    p=write_json(tmp_path/'a.json',otlp());before=p.read_bytes()
    c=load_capture([InputSource(p)])
    assert p.read_bytes()==before and c.inputs[0]['sha256']==hashlib.sha256(before).hexdigest()

def test_duplicate_attribute_type_conflict_rejected(tmp_path):
    a=span(attributes=[attr('typed',True)]);b=span(attributes=[attr('typed',1)])
    with pytest.raises(ClockWeaveError,match='conflict'):load(tmp_path,otlp([a,b]))
