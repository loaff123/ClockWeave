"""Small explicit qualification language; no inferred clock semantics."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
from typing import Mapping
from .ingest import decode_json
from .model import ClockWeaveError, Contract, Span


def fail(message, code='invalid_contract'):
    raise ClockWeaveError('invalid_contract',code,message)


def fields(value, required, optional=(), label='object'):
    if not isinstance(value,dict):fail(f'{label} must be an object')
    unknown=set(value)-set(required)-set(optional);missing=set(required)-set(value)
    if unknown or missing:fail(f'{label}: unknown fields {sorted(unknown)}; missing fields {sorted(missing)}')


def text(value,label,nonempty=False):
    if not isinstance(value,str) or (nonempty and not value.strip()):fail(f'{label} must be a {"nonblank " if nonempty else ""}string')


def sequence(value,label):
    if not isinstance(value,list):fail(f'{label} must be an array')


def evidence(value):
    text(value['assumption'],'assumption',True);sequence(value['evidence'],'evidence')
    if not value['evidence']:fail('evidence references must not be empty')
    for entry in value['evidence']:text(entry,'evidence reference',True)


def selector(value):
    fields(value,(),('names','kinds','scope_names','resource','attributes'),'selector')
    for key in ('names','scope_names','kinds'):
        if key not in value:continue
        sequence(value[key],key)
        for x in value[key]:
            if key=='kinds':
                if type(x) is not int or x not in range(6):fail('selector kinds require integer enums 0..5')
            else:text(x,key)
    for key in ('resource','attributes'):
        if key not in value:continue
        if not isinstance(value[key],dict):fail(f'{key} selector must be an object')
        for name,x in value[key].items():
            text(name,'attribute key')
            if type(x) not in (str,bool,int):fail('selector values must be string, boolean or integer scalars')


def value_source(value):
    if not isinstance(value,dict) or len(value)!=1 or next(iter(value)) not in ('resource_attribute','span_attribute','literal'):
        fail('identity value source must be exactly one resource_attribute, span_attribute or literal')
    text(next(iter(value.values())),'identity source',True)


def validate_contract(data):
    fields(data,('schema','provenance','identities','boundaries','anchor'),('description','exclusions'),'contract')
    if data['schema']!='clockweave.contract.v1':raise ClockWeaveError('unsupported','contract_schema','Unsupported contract schema')
    text(data.get('description',''),'description')
    fields(data['provenance'],('state','assumption','evidence'),label='provenance')
    if data['provenance']['state'] not in ('raw','unknown','adjusted'):fail('provenance.state must be raw, unknown or adjusted')
    evidence(data['provenance'])
    fields(data['anchor'],('domain','epoch'),label='anchor')
    for x in data['anchor'].values():text(x,'anchor identity',True)
    for group in ('identities','boundaries','exclusions'):
        values=data.get(group,[]);sequence(values,group);seen=set()
        for value in values:
            required={'identities':('id','select','domain','epoch','assumption','evidence'),
                      'boundaries':('id','client','server','link','relations'),
                      'exclusions':('id','select','reason')}[group]
            fields(value,required,label=group+' rule');text(value['id'],'rule id',True)
            if value['id'] in seen:fail(f'duplicate {group} rule id {value["id"]!r}')
            seen.add(value['id'])
            if group=='identities':
                selector(value['select']);value_source(value['domain']);value_source(value['epoch']);evidence(value)
            elif group=='exclusions':selector(value['select']);text(value['reason'],'exclusion reason',True)
            else:
                selector(value['client']);selector(value['server'])
                if value['link']!='parent':raise ClockWeaveError('unsupported','boundary_link','Only parent boundary matching is supported')
                sequence(value['relations'],'relations')
                if not value['relations']:fail('relations cannot be empty')
                kinds=set()
                for relation in value['relations']:
                    fields(relation,('kind','slack_ns','assumption','evidence'),label='relation')
                    if relation['kind'] not in ('start_order','end_enclosure'):fail('Unknown endpoint relation')
                    if relation['kind'] in kinds:fail('duplicate endpoint relation')
                    kinds.add(relation['kind']);slack=relation['slack_ns']
                    if not isinstance(slack,str) or re.fullmatch('[0-9]+',slack) is None:fail('slack_ns must be a nonnegative decimal string')
                    evidence(relation)
    normalized=dict(data);normalized.setdefault('description','');normalized.setdefault('exclusions',[])
    return normalized


def load_contract(path: Path) -> Contract:
    path=Path(path)
    try:raw=path.read_bytes()
    except OSError as e:raise ClockWeaveError('io_error','contract_read',f'Cannot read {path.name}: {e}') from e
    try:data=validate_contract(decode_json(raw))
    except ClockWeaveError as e:
        if e.kind=='invalid_input':e.kind='invalid_contract'
        raise
    canonical=json.dumps(data,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
    return Contract(data,hashlib.sha256(raw).hexdigest(),hashlib.sha256(canonical).hexdigest())


def matches(span: Span, select: Mapping) -> bool:
    for field,actual in (('names',span.name),('kinds',span.kind),('scope_names',span.scope_name)):
        if field in select and actual not in select[field]:return False
    for field,actual in (('resource',span.resource),('attributes',span.attributes)):
        for key,value in select.get(field,{}).items():
            if key not in actual or type(actual[key]) is not type(value) or actual[key]!=value:return False
    return True
