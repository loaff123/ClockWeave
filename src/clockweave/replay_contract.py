"""Reference contract interpretation and extraction, without production helpers."""
import hashlib
import json
from pathlib import Path
from .replay_input import require,object_,list_,string_,number,read_json,ns_text
from .limits import DEFAULT_LIMITS,admit


def _keys(item,needed,allowed=None):
    object_(item);needed=set(needed);allowed=needed if allowed is None else set(allowed)
    require(needed<=set(item)<=allowed,'Contract fields do not match schema')


def _nonblank(x):string_(x);require(bool(x.strip()),'Expected nonblank declaration')


def _assumption(rule):
    _nonblank(rule['assumption']);items=list_(rule['evidence']);require(bool(items),'Evidence references are empty')
    for item in items:_nonblank(item)


def _select_shape(rule):
    _keys(rule,(),('names','kinds','scope_names','resource','attributes'))
    for k,v in rule.items():
        if k in ('resource','attributes'):
            for name,w in object_(v).items():string_(name);require(type(w) in (str,int,bool),'Invalid selector scalar')
        else:
            for w in list_(v):
                if k=='kinds':require(type(w) is int and 0<=w<=5,'Invalid kind selector')
                else:string_(w)


def read_contract(path):
    raw=Path(path).read_bytes();d=read_json(raw)
    _keys(d,('schema','provenance','identities','boundaries','anchor'),('schema','description','provenance','identities','boundaries','exclusions','anchor'))
    require(d['schema']=='clockweave.contract.v1','Unsupported contract schema');string_(d.get('description',''))
    p=d['provenance'];_keys(p,('state','assumption','evidence'));require(p['state'] in ('raw','unknown','adjusted'),'Invalid provenance');_assumption(p)
    _keys(d['anchor'],('domain','epoch'))
    for v in d['anchor'].values():_nonblank(v)
    for section in ('identities','boundaries','exclusions'):
        entries=list_(d.get(section,[]));seen=set()
        for e in entries:
            needed={'identities':('id','select','domain','epoch','assumption','evidence'),'boundaries':('id','client','server','link','relations'),'exclusions':('id','select','reason')}[section]
            _keys(e,needed);_nonblank(e['id']);require(e['id'] not in seen,'Duplicate rule id');seen.add(e['id'])
            if section=='identities':
                _select_shape(e['select']);_assumption(e)
                for k in ('domain','epoch'):
                    source=object_(e[k]);require(len(source)==1 and set(source)<={'resource_attribute','span_attribute','literal'},'Invalid identity source');_nonblank(next(iter(source.values())))
            elif section=='exclusions':_select_shape(e['select']);_nonblank(e['reason'])
            else:
                _select_shape(e['client']);_select_shape(e['server']);require(e['link']=='parent','Unsupported link')
                relations=list_(e['relations']);require(bool(relations),'Empty relations');kinds=set()
                for rel in relations:
                    _keys(rel,('kind','slack_ns','assumption','evidence'));require(rel['kind'] in ('start_order','end_enclosure') and rel['kind'] not in kinds,'Invalid/duplicate relation');kinds.add(rel['kind'])
                    string_(rel['slack_ns']);number(rel['slack_ns']);_assumption(rel)
    d.setdefault('description','');d.setdefault('exclusions',[])
    canonical=json.dumps(d,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
    return {'data':d,'sha256':hashlib.sha256(raw).hexdigest(),'canonical_sha256':hashlib.sha256(canonical).hexdigest()}


def selected(s,rule):
    for k,actual in (('names',s['name']),('kinds',s['kind']),('scope_names',s['scope_name'])):
        if k in rule and actual not in rule[k]:return False
    for section in ('resource','attributes'):
        for name,wanted in rule.get(section,{}).items():
            observed=s[section].get(name)
            if name not in s[section] or type(observed)!=type(wanted) or observed!=wanted:return False
    return True


def _value(s,rule):
    kind,key=next(iter(rule.items()))
    value=key if kind=='literal' else s['resource' if kind=='resource_attribute' else 'attributes'].get(key)
    return value if type(value) is str and value.strip() else None


def components(variables,constraints,anchor):
    undirected={v['id']:set() for v in variables}
    for e in constraints:undirected[e['from']].add(e['to']);undirected[e['to']].add(e['from'])
    visited=set();result=[]
    for variable in variables:
        start=variable['id']
        if start in visited:continue
        group={start};todo=[start];visited.add(start)
        for u in todo:
            for v in sorted(undirected[u]):
                if v not in visited:visited.add(v);group.add(v);todo.append(v)
        result.append({'variables':sorted(group),'contains_anchor':anchor in group})
    return result


def reconstruct(observations,contract,duplicates):
    d=contract['data'];index={tuple(s['key']):s for s in observations};identity={};records=[];excluded={};reasons=[]
    for s in observations:
        key=tuple(s['key']);rules=[r for r in d['identities'] if selected(s,r['select'])];reason=None;rid=None;value=None
        if len(rules)==0:reason='unmatched_identity'
        elif len(rules)>1:reason='ambiguous_identity'
        else:
            r=rules[0];rid=r['id'];a=_value(s,r['domain']);b=_value(s,r['epoch'])
            if a is None or b is None:reason='missing_identity_attribute'
            else:value=(a,b);identity[key]=value
        exclusions=[r['id'] for r in d['exclusions'] if selected(s,r['select'])]
        if exclusions:excluded[key]=exclusions
        records.append({'span':s['key'],'identity':value,'identity_rule':rid,'reason':reason,'exclusions':exclusions,'issues':s['issues']})
    labels=sorted(set(identity.values()));variables=[{'id':'v'+str(i),'domain':domain,'epoch':epoch} for i,(domain,epoch) in enumerate(labels)]
    admit(len(variables),DEFAULT_LIMITS.max_domain_epochs,'Declared domain/epochs')
    ids={label:'v'+str(i) for i,label in enumerate(labels)}
    for r in records:
        if r['identity'] is not None:r['identity']=ids[r['identity']]
    anchor=ids.get((d['anchor']['domain'],d['anchor']['epoch']))
    if anchor is None:reasons.append({'code':'missing_anchor','message':'The declared anchor domain/epoch was not found.','sources':[]})
    state=d['provenance']['state']
    if state!='raw':reasons.append({'code':'provenance_'+state,'message':f'Input provenance is declared {state}; diagnosis requires declared raw evidence.','sources':[]})
    adjusted=[s for s in observations if any(s[section].get('clockweave.timestamp.state')=='adjusted' for section in ('resource','attributes'))]
    if adjusted:reasons.append({'code':'adjusted_marker','message':'Explicit adjusted timestamp metadata prevents a raw-evidence diagnosis.','sources':[ref for s in adjusted for ref in s['sources']]})
    pairs=[];edges=[]
    for server in observations:
        if server['parent'] is None:continue
        parent=tuple(server['parent']);key=tuple(server['key']);client=index.get(parent)
        pair={'client':server['parent'],'server':server['key'],'status':'unresolved','reason':None,'boundary_id':None,'selected_relations':[],'unqualified_relations':{}}
        if client is None:pair['reason']='missing_parent'
        elif parent in excluded or key in excluded:pair['reason']='excluded';pair['status']='excluded'
        else:
            rules=[r for r in d['boundaries'] if selected(client,r['client']) and selected(server,r['server'])]
            if not rules:pair['reason']='unmatched_boundary'
            elif len(rules)>1:pair['reason']='ambiguous_boundary'
            elif parent not in identity or key not in identity:pair['reason']='unqualified_identity'
            elif 'negative_raw_duration' in client['issues']+server['issues']:pair['reason']='negative_raw_duration'
            else:
                r=rules[0];pair['boundary_id']=r['id'];cv=ids[identity[parent]];sv=ids[identity[key]]
                for rel in sorted(r['relations'],key=lambda rel:rel['kind']):
                    kind=rel['kind'];slack=number(rel['slack_ns'])
                    a,b=(client['start_ns'],server['start_ns']) if kind=='start_order' else (server['end_ns'],client['end_ns'])
                    if a is None or b is None:pair['unqualified_relations'][kind]='missing_endpoint';continue
                    left,right=number(a,True),number(b,True);u,v=(sv,cv) if kind=='start_order' else (cv,sv)
                    edges.append({'id':'','from':u,'to':v,'weight_ns':ns_text(right-left+slack),'relation':kind,'boundary_id':r['id'],'client':client['key'],'server':server['key'],'endpoint_values_ns':[ns_text(left),ns_text(right)],'slack_ns':ns_text(slack),'sources':client['sources']+server['sources']})
                    pair['selected_relations'].append(kind)
                if pair['selected_relations']:pair['status']='selected';pair['reason']='partial_endpoints' if pair['unqualified_relations'] else None
                else:pair['reason']='missing_endpoint'
        pairs.append(pair)
    edges.sort(key=lambda e:(e['client'][0],e['client'][1],e['server'][1],e['boundary_id'],e['relation']))
    for i,e in enumerate(edges):e['id']=f'c{i:06d}'
    if not edges:reasons.append({'code':'no_constraints','message':'No endpoint relation has sufficient declared qualification and observed endpoints.','sources':[]})
    coverage={'span_count':len(observations),'duplicate_observations':duplicates,'identity_qualified_spans':len(identity),'parent_candidates':len(pairs),
              'selected_pairs':sum(p['status']=='selected' for p in pairs),'start_relations':sum(e['relation']=='start_order' for e in edges),
              'end_relations':sum(e['relation']=='end_enclosure' for e in edges),'excluded_spans':len(excluded),
              'unresolved_spans':sum(p['reason'] is not None or bool(p['issues']) for p in records),
              'unresolved_pairs':sum(p['status']=='unresolved' or bool(p['unqualified_relations']) for p in pairs),
              'raw_constraint_count':len(edges),'graph_edge_count':len({(e['from'],e['to']) for e in edges})}
    qualification={'spans':records,'pairs':pairs,'provenance_warnings':[{'span':s['key'],'warnings':s['warnings']} for s in observations if s['warnings']]}
    return {'coverage':coverage,'qualification':qualification,'variables':variables,'anchor':anchor,'components':components(variables,edges,anchor),'constraints':edges,'reasons':reasons}
