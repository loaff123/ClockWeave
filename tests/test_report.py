import copy
import pytest
from clockweave.report import render_html,validate_report_structure
from clockweave.model import ClockWeaveError
from .test_analysis import report
from .helpers import rpc_doc

def test_report_html_escapes_evidence(tmp_path):
    r=report(tmp_path);r['observations'][0]['name']='<script>alert("unsafe")</script>'
    html=render_html(r)
    assert '<script>' not in html and '&lt;script&gt;' in html
    assert 'Structurally validated report. Independent verification requires the original inputs and contract.' in html
    assert 'qualified subset' in html and 'coupled' in html
    assert 'http://' not in html and 'https://' not in html

def test_render_is_not_independent_verification(tmp_path):
    r=report(tmp_path);r['solution']['ranges'][1]['upper']['value_ns']='999'
    validate_report_structure(r)
    html=render_html(r)
    assert 'Independent verification requires' in html and '999' in html

def test_incompatible_source_links(tmp_path):
    r=report(tmp_path,rpc_doc(240));html=render_html(r)
    assert '-6' in html and 'href="#constraint-' in html and 'Raw observations' in html

@pytest.mark.parametrize('mutate',[lambda r:r.update(schema='unknown'),lambda r:r.pop('coverage'),lambda r:r['constraints'][0].update(weight_ns=3),lambda r:r['solution']['example_ns'].update(v0=True)])
def test_structural_malformed_report_rejected(tmp_path,mutate):
    r=report(tmp_path);mutate(r)
    with pytest.raises(ClockWeaveError):render_html(r)

@pytest.mark.parametrize('mutate',[lambda r:r['solution']['ranges'].__setitem__(0,3),lambda r:r['contract'].pop('sha256'),lambda r:r['inputs'][0].update(bytes=True),lambda r:r['observations'][0].update(parent='bad'),lambda r:r['constraints'][0].update(sources=[3]),lambda r:r['qualification'].update(spans=3)])
def test_malformed_nested_structure_is_explicit_error(tmp_path,mutate):
    r=report(tmp_path);mutate(r)
    with pytest.raises(ClockWeaveError):render_html(r)
