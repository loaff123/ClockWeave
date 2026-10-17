import copy
import pytest
from clockweave.contract import load_contract, matches
from clockweave.ingest import load_capture
from clockweave.model import InputSource, ClockWeaveError
from .helpers import contract, otlp, span, attr, write_json

def test_contract_defaults_and_hashes(tmp_path):
    c=contract();del c['exclusions']
    a=load_contract(write_json(tmp_path/'c.json',c))
    assert a.data['exclusions']==[] and len(a.sha256)==64 and len(a.canonical_sha256)==64

@pytest.mark.parametrize('mutate',[lambda c:c.update(foo=1),lambda c:c.update(schema='next'),lambda c:c['identities'][0].update(typo=True),lambda c:c['identities'][0].update(domain={'literal':'A','span_attribute':'x'}),lambda c:c['boundaries'][0].update(link='follows_from'),lambda c:c['boundaries'][0]['relations'][0].update(slack_ns='-1'),lambda c:c['boundaries'][0]['relations'][0].update(assumption=''),lambda c:c['boundaries'][0]['client'].update(names='call'),lambda c:c['boundaries'][0]['client'].update(kinds=[True]),lambda c:c['boundaries'][0]['client'].update(resource={'x':1.5}),lambda c:c['boundaries'][0]['relations'].append(c['boundaries'][0]['relations'][0]),lambda c:c['identities'].append(c['identities'][0])])
def test_invalid_contract_rejected(tmp_path,mutate):
    c=contract();mutate(c)
    with pytest.raises(ClockWeaveError):load_contract(write_json(tmp_path/'c.json',c))

def test_matching_typed_equality(tmp_path):
    s=span(attributes=[attr('x',1)])
    a=load_capture([InputSource(write_json(tmp_path/'t.json',otlp([s])))]).spans[0]
    assert matches(a,{'attributes':{'x':1}})
    assert not matches(a,{'attributes':{'x':True}})
    assert not matches(a,{'attributes':{'x':'1'}})
    assert not matches(a,{'names':[]})
    assert matches(a,{})
