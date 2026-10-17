"""Structural validation and escaped, offline HTML views.

Rendering is not independent replay against original raw inputs.
"""
import html
import json
import math
import re
from typing import Mapping
from .model import ClockWeaveError
from .limits import DEFAULT_LIMITS,admit
from .analysis import INTERPRETATION

BANNER='Structurally validated report. Independent verification requires the original inputs and contract.'
FIELDS={'schema','tool_version','status','interpretation','inputs','contract','coverage','observations','qualification','variables','anchor','components','constraints','solution','contradiction','reasons'}


def check(ok,message):
    if not ok:raise ClockWeaveError('invalid_input','invalid_report_structure',message)


def decimal(value,nullable=False):
    if nullable and value is None:return
    check(type(value) is str and re.fullmatch('-?[0-9]+',value) is not None,'Report nanoseconds must be decimal strings')


def json_types(value):
    if isinstance(value,dict):
        check(all(type(k) is str for k in value),'JSON keys must be strings')
        for v in value.values():json_types(v)
    elif isinstance(value,list):
        for v in value:json_types(v)
    else:check(value is None or type(value) in (str,bool,int) or type(value) is float and math.isfinite(value),'Report contains unsupported JSON values')


def _validate_report_structure(report: Mapping) -> None:
    if not isinstance(report,Mapping) or report.get('schema')!='clockweave.report.v1':
        raise ClockWeaveError('unsupported','report_schema','Unsupported report schema')
    check(set(report)==FIELDS,'Report top-level fields do not match schema');json_types(report)
    check(type(report['tool_version']) is str and report['interpretation']==INTERPRETATION,'Report must carry the fixed limitation text')
    check(report['status'] in ('compatible','incompatible','insufficient_evidence'),'Unknown report status')
    for key in ('inputs','observations','variables','components','constraints','reasons'):check(type(report[key]) is list,key+' must be an array')
    for key in ('contract','coverage','qualification'):check(type(report[key]) is dict,key+' must be an object')
    coverage_fields={'span_count','duplicate_observations','identity_qualified_spans','parent_candidates','selected_pairs','start_relations','end_relations','excluded_spans','unresolved_spans','unresolved_pairs','raw_constraint_count','graph_edge_count'}
    check(set(report['coverage'])==coverage_fields,'Required coverage fields are missing or unknown')
    check(all(type(x) is int and x>=0 for x in report['coverage'].values()),'Coverage counts must be nonnegative integers')
    check(set(report['contract'])=={'data','sha256','canonical_sha256'},'Invalid contract record')
    from .contract import validate_contract
    validate_contract(report['contract']['data'])
    for key in ('sha256','canonical_sha256'):
        check(type(report['contract'][key]) is str and re.fullmatch('[0-9a-f]{64}',report['contract'][key]) is not None,'Invalid contract hash')
    for item in report['inputs']:
        check(type(item) is dict and set(item)=={'file_name','sha256','format','bytes','document_count'},'Invalid input record')
        check(type(item['file_name']) is str and type(item['sha256']) is str and re.fullmatch('[0-9a-f]{64}',item['sha256']) is not None,'Invalid input label/hash')
        check(item['format'] in ('otlp-json','otlp-jsonl','jaeger-json'),'Invalid input format')
        check(all(type(item[k]) is int and item[k]>=0 for k in ('bytes','document_count')),'Invalid input counts')
    check(set(report['qualification'])=={'spans','pairs','provenance_warnings'} and all(type(v) is list for v in report['qualification'].values()),'Invalid qualification lists')
    def source(ref):
        check(type(ref) is dict and set(ref)=={'file_sha256','file_name','document_index','line','json_pointer'},'Invalid source reference')
        check(type(ref['file_sha256']) is str and re.fullmatch('[0-9a-f]{64}',ref['file_sha256']) is not None,'Invalid source hash')
        check(type(ref['file_name']) is str and type(ref['json_pointer']) is str,'Invalid source text')
        check(type(ref['document_index']) is int and ref['document_index']>=0,'Invalid document index')
        check(ref['line'] is None or type(ref['line']) is int and ref['line']>=1,'Invalid source line')
    def span_key(value):
        check(type(value) is list and len(value)==2 and all(type(x) is str for x in value),'Invalid span reference')

    check(report['coverage']['span_count']==len(report['observations']),'Observation coverage count differs')
    admit(len(report['observations'])+report['coverage']['duplicate_observations'],DEFAULT_LIMITS.max_spans,'Report observed span records including duplicates')
    admit(len(report['variables']),DEFAULT_LIMITS.max_domain_epochs,'Report domain/epochs')
    for variable in report['variables']:
        check(type(variable) is dict and set(variable)=={'id','domain','epoch'} and all(type(v) is str for v in variable.values()),'Invalid variable')
    ids=[v['id'] for v in report['variables']];check(len(ids)==len(set(ids)),'Duplicate variable ids')
    check(report['anchor'] is None or report['anchor'] in ids,'Invalid anchor reference')
    for s in report['observations']:
        check(type(s) is dict and {'key','name','kind','parent','start_ns','end_ns','resource','attributes','scope_name','scope_version','warnings','sources','issues'}==set(s),'Invalid observation structure')
        check(type(s['key']) is list and len(s['key'])==2 and all(type(k) is str for k in s['key']),'Invalid span key')
        check(type(s['name']) is str and type(s['kind']) is int and s['kind'] in range(6),'Invalid observation name/kind')
        check(type(s['scope_name']) is str and type(s['scope_version']) is str,'Invalid observation scope metadata')
        check(type(s['warnings']) is list and all(type(w) is str for w in s['warnings']),'Invalid observation warnings')
        check(type(s['issues']) is list and all(type(w) is str for w in s['issues']),'Invalid observation issues')
        decimal(s['start_ns'],True);decimal(s['end_ns'],True)
        if s['parent'] is not None:span_key(s['parent'])
        for ref in s['sources']:source(ref)
        for key in ('resource','attributes'):check(type(s[key]) is dict,'Invalid observation metadata')
        for key in ('warnings','sources','issues'):check(type(s[key]) is list,'Invalid observation list')
    observed_keys={tuple(s['key']) for s in report['observations']}
    check(len(observed_keys)==len(report['observations']),'Duplicate canonical observations')
    identity_rules={r['id'] for r in report['contract']['data']['identities']}
    boundary_rules={r['id'] for r in report['contract']['data']['boundaries']}
    exclusion_rules={r['id'] for r in report['contract']['data'].get('exclusions',[])}
    qualified=report['qualification'];span_records=qualified['spans'];pair_records=qualified['pairs']
    check(len(span_records)==len(observed_keys),'Missing qualification span records')
    seen_spans=set()
    for entry in span_records:
        check(type(entry) is dict and set(entry)=={'span','identity','identity_rule','reason','exclusions','issues'},'Invalid span qualification record')
        span_key(entry['span']);key=tuple(entry['span']);check(key in observed_keys and key not in seen_spans,'Unknown or duplicate qualification span');seen_spans.add(key)
        check(entry['identity'] is None or entry['identity'] in ids,'Invalid qualified identity')
        check(entry['identity_rule'] is None or type(entry['identity_rule']) is str and entry['identity_rule'] in identity_rules,'Invalid identity rule reference')
        check(entry['reason'] in (None,'unmatched_identity','ambiguous_identity','missing_identity_attribute'),'Invalid span qualification reason')
        check(type(entry['exclusions']) is list and all(type(x) is str and x in exclusion_rules for x in entry['exclusions']),'Invalid exclusion references')
        check(type(entry['issues']) is list and all(type(x) is str for x in entry['issues']),'Invalid qualification issues')
    check(len(pair_records)==report['coverage']['parent_candidates'],'Parent candidate count differs')
    seen_servers=set();relation_kinds={'start_order','end_enclosure'}
    for entry in pair_records:
        check(type(entry) is dict and set(entry)=={'client','server','status','reason','boundary_id','selected_relations','unqualified_relations'},'Invalid pair qualification record')
        span_key(entry['client']);span_key(entry['server']);key=tuple(entry['server'])
        check(key in observed_keys and key not in seen_servers,'Unknown or duplicate candidate server');seen_servers.add(key)
        check(entry['status'] in ('selected','excluded','unresolved'),'Invalid pair status')
        check(entry['reason'] in (None,'missing_parent','excluded','unmatched_boundary','ambiguous_boundary','unqualified_identity','negative_raw_duration','partial_endpoints','missing_endpoint'),'Invalid pair reason')
        check(entry['boundary_id'] is None or type(entry['boundary_id']) is str and entry['boundary_id'] in boundary_rules,'Invalid boundary reference')
        check(type(entry['selected_relations']) is list and all(type(x) is str and x in relation_kinds for x in entry['selected_relations']),'Invalid selected relations')
        check(len(set(entry['selected_relations']))==len(entry['selected_relations']),'Duplicate selected relation')
        check(type(entry['unqualified_relations']) is dict and set(entry['unqualified_relations'])<=relation_kinds and all(v=='missing_endpoint' for v in entry['unqualified_relations'].values()),'Invalid unqualified relations')
    for entry in qualified['provenance_warnings']:
        check(type(entry) is dict and set(entry)=={'span','warnings'},'Invalid provenance warning record');span_key(entry['span'])
        check(tuple(entry['span']) in observed_keys and type(entry['warnings']) is list and all(type(w) is str for w in entry['warnings']),'Invalid provenance warning types')
    expected={'id','from','to','weight_ns','relation','boundary_id','client','server','endpoint_values_ns','slack_ns','sources'}
    constraint_ids=[]
    for e in report['constraints']:
        check(type(e) is dict and set(e)==expected,'Invalid constraint structure')
        check(type(e['id']) is str and e['from'] in ids and e['to'] in ids,'Invalid constraint reference')
        check(e['relation'] in ('start_order','end_enclosure'),'Invalid relation')
        decimal(e['weight_ns']);decimal(e['slack_ns']);check(not e['slack_ns'].startswith('-'),'Negative slack')
        check(type(e['endpoint_values_ns']) is list and len(e['endpoint_values_ns'])==2,'Missing endpoints')
        for v in e['endpoint_values_ns']:decimal(v)
        check(type(e['sources']) is list and type(e['boundary_id']) is str,'Invalid constraint metadata');constraint_ids.append(e['id'])
        span_key(e['client']);span_key(e['server'])
        for ref in e['sources']:source(ref)
    check(len(constraint_ids)==len(set(constraint_ids)),'Duplicate constraint ids')
    check(len(constraint_ids)==report['coverage']['raw_constraint_count'],'Raw constraint count differs')
    for component in report['components']:
        check(type(component) is dict and set(component)=={'variables','contains_anchor'},'Invalid component')
        check(type(component['variables']) is list and all(v in ids for v in component['variables']) and type(component['contains_anchor']) is bool,'Invalid component variables')
    for reason in report['reasons']:
        check(type(reason) is dict and set(reason)=={'code','message','sources'},'Invalid evidence reason')
        check(type(reason['code']) is str and type(reason['message']) is str and type(reason['sources']) is list,'Invalid evidence reason field types')
        for ref in reason['sources']:source(ref)
    check(bool(report['reasons'])==(report['status']=='insufficient_evidence'),'Evidence blocker/status mismatch')
    def assignment(a):
        check(type(a) is dict and set(a)==set(ids),'Assignment variable set is invalid')
        for v in a.values():decimal(v)
    if report['status']=='compatible':
        check(report['contradiction'] is None and type(report['solution']) is dict,'Invalid compatible result')
        s=report['solution'];check(set(s)=={'example_ns','ranges'},'Invalid solution fields');assignment(s['example_ns'])
        check(type(s['ranges']) is list and len(s['ranges'])==len(ids),'Missing ranges')
        check(all(type(r) is dict for r in s['ranges']),'Range records must be objects')
        check([r.get('variable') for r in s['ranges']]==ids,'Range variable set/order is invalid')
        for row in s['ranges']:
            check(set(row)=={'variable','lower','upper'},'Invalid range fields')
            for side in ('lower','upper'):
                bound=row[side];check(type(bound) is dict and 'value_ns' in bound,'Invalid bound')
                if bound['value_ns'] is None:
                    check(set(bound)=={'value_ns','reachable'} and type(bound['reachable']) is list and all(v in ids for v in bound['reachable']),'Invalid unbounded witness structure')
                else:
                    check(set(bound)=={'value_ns','path','attaining_ns'} and type(bound['path']) is list and all(x in constraint_ids for x in bound['path']),'Invalid finite witness structure')
                    decimal(bound['value_ns']);assignment(bound['attaining_ns'])
    elif report['status']=='incompatible':
        c=report['contradiction'];check(report['solution'] is None and type(c) is dict and set(c)=={'constraint_ids','sum_ns'},'Invalid incompatible result')
        check(type(c['constraint_ids']) is list and bool(c['constraint_ids']) and all(x in constraint_ids for x in c['constraint_ids']),'Invalid cycle references');decimal(c['sum_ns'])
    else:check(report['solution'] is None and report['contradiction'] is None,'Insufficient evidence cannot assert a solve')


def validate_report_structure(report: Mapping) -> None:
    try:
        _validate_report_structure(report)
    except (KeyError,TypeError,AttributeError,OverflowError,RecursionError) as error:
        raise ClockWeaveError('invalid_input','invalid_report_structure','Malformed nested report structure: '+str(error)) from error


def render_html(report: Mapping) -> str:
    validate_report_structure(report)
    esc=lambda x:html.escape(str(x),quote=True)
    pretty=lambda x:'<pre>'+esc(json.dumps(x,indent=2,ensure_ascii=False))+'</pre>'
    def table(headers,rows):
        return '<div class="scroll"><table><thead><tr>'+''.join('<th scope="col">'+esc(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+str(c)+'</td>' for c in row)+'</tr>' for row in rows)+'</tbody></table></div>'
    status=report['status'];title={'compatible':'Compatible qualified subset','incompatible':'Incompatible qualified subset','insufficient_evidence':'Insufficient evidence'}[status]
    sections=['<header><p class="eyebrow">CLOCKWEAVE · DECLARED-MODEL DIAGNOSIS</p><h1>'+title+'</h1><p>'+esc(report['interpretation'])+'</p></header>',
              '<aside class="verification">'+BANNER+'</aside>',
              '<section><h2>Coverage and exclusions</h2>'+table(['Observation','Count'],[(esc(k.replace('_',' ')),esc(v)) for k,v in report['coverage'].items()])+'</section>']
    if report['reasons']:sections.append('<section><h2>Evidence blockers</h2>'+pretty(report['reasons'])+'</section>')
    sections.append('<section><h2>Declared domain and epoch assumptions</h2><p>Each domain/epoch is a separate constant correction. Assumptions are operator declarations, not certified physical facts.</p>'+table(['Variable','Domain','Epoch','Anchor'],[(esc(v['id']),esc(v['domain']),esc(v['epoch']),'0 ns' if v['id']==report['anchor'] else '') for v in report['variables']])+'<details><summary>Complete reusable qualification contract</summary>'+pretty(report['contract'])+'</details></section>')
    if report['solution']:
        rows=[]
        for row in report['solution']['ranges']:
            rows.append((esc(row['variable']),esc(row['lower']['value_ns']) if row['lower']['value_ns'] is not None else 'unbounded',esc(row['upper']['value_ns']) if row['upper']['value_ns'] is not None else 'unbounded',esc(report['solution']['example_ns'][row['variable']])))
        sections.append('<section><h2>Coupled relative correction ranges</h2><p>All values are integer nanoseconds. These coupled ranges cannot be selected independently. The example is jointly feasible; disconnected translations are arbitrary.</p>'+table(['Variable','Lower ns','Upper ns','Joint example ns'],rows)+'<details><summary>Paths, attaining assignments and unbounded cuts</summary>'+pretty(report['solution']['ranges'])+'</details></section>')
    if report['contradiction']:
        c=report['contradiction'];links=' → '.join('<a href="#constraint-'+esc(x)+'">'+esc(x)+'</a>' for x in c['constraint_ids'])
        sections.append('<section><h2>Exact contradiction</h2><p>Cycle sum: <strong>'+esc(c['sum_ns'])+' ns</strong>. This rejects the joint selected observations and declared model. It does not assign blame.</p><p>'+links+'</p></section>')
    sections.append('<section><h2>Selected raw endpoint inequalities</h2><p>An edge u → v with weight w means x[v] − x[u] ≤ w. Each slack independently relaxes its own inequality.</p>')
    for c in report['constraints']:
        sections.append('<details id="constraint-'+esc(c['id'])+'"><summary>'+esc(c['id'])+' · '+esc(c['from'])+' → '+esc(c['to'])+' ≤ '+esc(c['weight_ns'])+' ns · '+esc(c['relation'])+'</summary>'+pretty(c)+'</details>')
    sections.append('</section><section><h2>Raw observations</h2><p>These timestamps are unchanged. Source hashes and pointers identify the original inputs.</p>')
    for s in report['observations']:
        sections.append('<details><summary>'+esc(s['name'])+' · '+esc('/'.join(s['key']))+' · '+esc(s['start_ns'])+' → '+esc(s['end_ns'])+' ns</summary>'+pretty(s)+'</details>')
    sections.append('</section><section><h2>Unresolved, excluded and selected evidence</h2>'+pretty(report['qualification'])+'</section><section><h2>Input provenance</h2>'+pretty(report['inputs'])+'<details><summary>Disconnected components</summary>'+pretty(report['components'])+'</details></section>')
    css='''*{box-sizing:border-box}body{margin:0;background:#f4f5f8;color:#172434;font:16px/1.55 system-ui,sans-serif}main{max-width:1100px;margin:auto;padding:36px 22px 80px}header{padding:32px;border-radius:18px;background:#152a3a;color:#f7fafc}h1{font-size:36px;line-height:1.15;margin:12px 0}h2{font-size:23px;line-height:1.3}.eyebrow{letter-spacing:.14em;font-size:12px;color:#9dd7d9}section{background:white;margin-top:22px;padding:24px;border-radius:14px;box-shadow:0 2px 8px #17243409}.verification{margin:22px 0;padding:16px 20px;background:#fff3d4;border-left:5px solid #d99b15;border-radius:5px}table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:9px 12px;border-bottom:1px solid #e3e8ee;vertical-align:top}th{font-size:13px;color:#50627a}td{font-variant-numeric:tabular-nums}pre{font:12px/1.6 ui-monospace,monospace;white-space:pre-wrap;overflow-wrap:anywhere;background:#f6f8fa;padding:14px;border-radius:6px}details{border:1px solid #e1e7ef;border-radius:6px;margin:10px 0;padding:12px}summary{cursor:pointer;overflow-wrap:anywhere}a{color:#17698b}.scroll{overflow:auto}@media(max-width:650px){main{padding:16px 10px}header,section{padding:18px}h1{font-size:28px}}'''
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ClockWeave · '+esc(title)+'</title><style>'+css+'</style></head><body><main>'+''.join(sections)+'<footer><p>ClockWeave '+esc(report['tool_version'])+' · Local report view · No remote assets</p></footer></main></body></html>'
