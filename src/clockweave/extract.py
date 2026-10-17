"""Inventory and explicit qualification of raw endpoint relations."""
from __future__ import annotations
from dataclasses import asdict
from .contract import matches
from .model import Capture, Constraint, Contract, Extraction
from .limits import DEFAULT_LIMITS,admit
from .decimal import parse_decimal,decimal_text


def observation(span):
    d=asdict(span)
    d['key']=list(span.key);d['parent']=list(span.parent) if span.parent else None
    d['start_ns']=decimal_text(span.start_ns) if span.start_ns is not None else None
    d['end_ns']=decimal_text(span.end_ns) if span.end_ns is not None else None
    d['warnings']=list(span.warnings);d['issues']=list(span.issues)
    d['sources']=[asdict(s) for s in span.sources]
    return d


def identity_value(span,rule):
    if 'literal' in rule:value=rule['literal']
    elif 'resource_attribute' in rule:value=span.resource.get(rule['resource_attribute'])
    else:value=span.attributes.get(rule['span_attribute'])
    return value if isinstance(value,str) and value.strip() else None


def extract(capture: Capture, contract: Contract) -> Extraction:
    admit(len(capture.spans)+capture.duplicate_observations,DEFAULT_LIMITS.max_spans,'Observed span records including duplicates')
    admit(sum(i['bytes'] for i in capture.inputs),DEFAULT_LIMITS.max_input_bytes,'Total input bytes')
    data=contract.data;indexed={s.key:s for s in capture.spans};identities={};span_records=[];excluded={};reasons=[]
    for s in capture.spans:
        selected=[r for r in data['identities'] if matches(s,r['select'])]
        reason=None;value=None;rule_id=None
        if not selected:reason='unmatched_identity'
        elif len(selected)>1:reason='ambiguous_identity'
        else:
            r=selected[0];rule_id=r['id'];domain=identity_value(s,r['domain']);epoch=identity_value(s,r['epoch'])
            if domain is None or epoch is None:reason='missing_identity_attribute'
            else:value=(domain,epoch);identities[s.key]=value
        ex=[r['id'] for r in data['exclusions'] if matches(s,r['select'])]
        if ex:excluded[s.key]=ex
        span_records.append({'span':list(s.key),'identity':value,'identity_rule':rule_id,'reason':reason,'exclusions':ex,'issues':list(s.issues)})
    variables=tuple({'id':f'v{i}','domain':v[0],'epoch':v[1]} for i,v in enumerate(sorted(set(identities.values()))))
    admit(len(variables),DEFAULT_LIMITS.max_domain_epochs,'Declared domain/epochs')
    ids={(v['domain'],v['epoch']):v['id'] for v in variables}
    for r in span_records:
        if r['identity'] is not None:r['identity']=ids[r['identity']]
    anchor=ids.get((data['anchor']['domain'],data['anchor']['epoch']))
    if anchor is None:reasons.append({'code':'missing_anchor','message':'The declared anchor domain/epoch was not found.','sources':[]})
    if data['provenance']['state']!='raw':
        state=data['provenance']['state'];reasons.append({'code':'provenance_'+state,'message':f'Input provenance is declared {state}; diagnosis requires declared raw evidence.','sources':[]})
    marked=[s for s in capture.spans if s.attributes.get('clockweave.timestamp.state')=='adjusted' or s.resource.get('clockweave.timestamp.state')=='adjusted']
    if marked:reasons.append({'code':'adjusted_marker','message':'Explicit adjusted timestamp metadata prevents a raw-evidence diagnosis.','sources':[asdict(ref) for s in marked for ref in s.sources]})
    constraints=[];pair_records=[]
    for server in capture.spans:
        if server.parent is None:continue
        client=indexed.get(server.parent)
        record={'client':list(server.parent),'server':list(server.key),'status':'unresolved','reason':None,'boundary_id':None,'selected_relations':[],'unqualified_relations':{}}
        if client is None:record['reason']='missing_parent'
        elif server.key in excluded or client.key in excluded:record.update(status='excluded',reason='excluded')
        else:
            rules=[r for r in data['boundaries'] if matches(client,r['client']) and matches(server,r['server'])]
            if not rules:record['reason']='unmatched_boundary'
            elif len(rules)>1:record['reason']='ambiguous_boundary'
            elif server.key not in identities or client.key not in identities:record['reason']='unqualified_identity'
            elif 'negative_raw_duration' in server.issues or 'negative_raw_duration' in client.issues:record['reason']='negative_raw_duration'
            else:
                rule=rules[0];record['boundary_id']=rule['id']
                cv=ids[identities[client.key]];sv=ids[identities[server.key]]
                for relation in sorted(rule['relations'],key=lambda r:r['kind']):
                    kind=relation['kind'];slack=parse_decimal(relation['slack_ns'])
                    left,right=(client.start_ns,server.start_ns) if kind=='start_order' else (server.end_ns,client.end_ns)
                    if left is None or right is None:record['unqualified_relations'][kind]='missing_endpoint';continue
                    u,v=(sv,cv) if kind=='start_order' else (cv,sv)
                    constraints.append(Constraint('',u,v,right-left+slack,kind,rule['id'],client.key,server.key,(left,right),slack,client.sources+server.sources))
                    record['selected_relations'].append(kind)
                if record['selected_relations']:
                    record['status']='selected';record['reason']='partial_endpoints' if record['unqualified_relations'] else None
                else:record['reason']='missing_endpoint'
        pair_records.append(record)
    from dataclasses import replace
    constraints=tuple(replace(c,id=f'c{i:06d}') for i,c in enumerate(sorted(constraints,key=lambda c:(c.client[0],c.client[1],c.server[1],c.boundary_id,c.relation))))
    if not constraints:reasons.append({'code':'no_constraints','message':'No endpoint relation has sufficient declared qualification and observed endpoints.','sources':[]})
    coverage={'span_count':len(capture.spans),'duplicate_observations':capture.duplicate_observations,
              'identity_qualified_spans':len(identities),'parent_candidates':len(pair_records),
              'selected_pairs':sum(r['status']=='selected' for r in pair_records),
              'start_relations':sum(c.relation=='start_order' for c in constraints),'end_relations':sum(c.relation=='end_enclosure' for c in constraints),
              'excluded_spans':len(excluded),'unresolved_spans':sum(r['reason'] is not None or bool(r['issues']) for r in span_records),
              'unresolved_pairs':sum(r['status']=='unresolved' or bool(r['unqualified_relations']) for r in pair_records),
              'raw_constraint_count':len(constraints),'graph_edge_count':len({(c.from_id,c.to_id) for c in constraints})}
    qualification={'spans':span_records,'pairs':pair_records,'provenance_warnings':[{'span':list(s.key),'warnings':list(s.warnings)} for s in capture.spans if s.warnings]}
    return Extraction(variables,anchor,constraints,coverage,qualification,tuple(reasons))


def inspect_capture(capture: Capture, contract: Contract | None = None) -> dict:
    admit(len(capture.spans)+capture.duplicate_observations,DEFAULT_LIMITS.max_spans,'Observed span records including duplicates')
    admit(sum(i['bytes'] for i in capture.inputs),DEFAULT_LIMITS.max_input_bytes,'Total input bytes')
    result={'schema':'clockweave.inventory.v1','inputs':list(capture.inputs),'span_count':len(capture.spans),
            'duplicate_observations':capture.duplicate_observations,
            'resource_attribute_keys':sorted({k for s in capture.spans for k in s.resource}),
            'span_attribute_keys':sorted({k for s in capture.spans for k in s.attributes}),
            'scopes':sorted({s.scope_name for s in capture.spans}),'observations':[observation(s) for s in capture.spans]}
    if contract is not None:
        e=extract(capture,contract);result.update(variables=list(e.variables),anchor=e.anchor,coverage=e.coverage,qualification=e.qualification,reasons=list(e.reasons))
    return result
