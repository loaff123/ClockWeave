"""Strict, integer-preserving supported trace-export readers."""
from __future__ import annotations
import base64
import hashlib
import json
import math
import re
from dataclasses import replace, asdict
from pathlib import Path
from typing import Sequence
from .model import Capture, ClockWeaveError, InputSource, SourceRef, Span
from .limits import DEFAULT_LIMITS,admit
from .decimal import parse_decimal


def invalid(code, message, source=None):
    raise ClockWeaveError('invalid_input', code, message, source)


def obj(value, label):
    if not isinstance(value, dict): invalid('object_required', f'{label} must be an object')
    return value


def array(value, label):
    if not isinstance(value, list): invalid('array_required', f'{label} must be an array')
    return value


def string(value, label):
    if not isinstance(value, str): invalid('string_required', f'{label} must be a string')
    return value


def integer(value, label, maximum=None, signed=False):
    if isinstance(value, bool) or not (isinstance(value, int) or isinstance(value, str) and re.fullmatch(r'-?[0-9]+' if signed else r'[0-9]+', value)):
        invalid('integer_required', f'{label} must be an integer decimal string or integer token')
    n = parse_decimal(value)
    if (not signed and n < 0) or (maximum is not None and n > maximum):
        invalid('integer_range', f'{label} is out of range')
    return n


def unique_object(pairs):
    result = {}
    for k, v in pairs:
        if k in result: invalid('duplicate_key', f'duplicate JSON key {k!r}')
        result[k] = v
    return result


def decode_json(raw):
    try:
        return json.loads(raw, object_pairs_hook=unique_object,
                          parse_constant=lambda x: invalid('nonfinite', f'nonfinite JSON value {x}'))
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError, ValueError) as e:
        if isinstance(e, ClockWeaveError): raise
        invalid('invalid_json', f'Invalid JSON: {e}')


def ident(value, length, label, legacy=False, empty=False):
    if empty and value in ('', '0' * length, None): return None
    if not isinstance(value, str) or not re.fullmatch('[0-9a-fA-F]+', value):
        invalid('invalid_id', f'{label} must be a hex ID')
    if len(value) not in ((16, 32) if legacy and length == 32 else (length,)) or int(value, 16) == 0:
        invalid('invalid_id', f'{label} has invalid length or is zero')
    return value.lower().zfill(length)


def any_value(value):
    value = obj(value, 'AnyValue')
    choices = [k for k in ('stringValue','boolValue','intValue','doubleValue','bytesValue','arrayValue','kvlistValue') if k in value]
    if len(choices) != 1: invalid('invalid_anyvalue', 'AnyValue must have exactly one value alternative')
    key = choices[0]; x = value[key]
    if key == 'stringValue': return string(x, key)
    if key == 'boolValue':
        if type(x) is not bool: invalid('invalid_bool', 'boolValue must be boolean')
        return x
    if key == 'intValue':
        n = integer(x, key, maximum=2**63-1, signed=True)
        if n < -(2**63): invalid('integer_range', 'intValue out of signed 64-bit range')
        return n
    if key == 'doubleValue':
        if type(x) not in (float,int): invalid('invalid_double','doubleValue must be finite numeric metadata')
        try: converted=float(x)
        except (OverflowError,ValueError): invalid('invalid_double','doubleValue is not representable as a finite double')
        if not math.isfinite(converted): invalid('invalid_double','doubleValue must be finite numeric metadata')
        return converted
    if key == 'bytesValue':
        try: base64.b64decode(string(x,key), validate=True)
        except (ValueError, TypeError): invalid('invalid_bytes','bytesValue must be base64')
        return {'__otlp_bytes__':x}
    if key == 'arrayValue': return [any_value(v) for v in array(obj(x,key).get('values',[]),'values')]
    return {'__otlp_kvlist__':attributes(obj(x,key).get('values',[]))}


def attributes(values):
    result = {}
    for entry in array(values, 'attributes'):
        entry = obj(entry, 'attribute'); key = string(entry.get('key'), 'attribute key')
        if key in result: invalid('duplicate_attribute', f'duplicate attribute {key!r}')
        result[key] = any_value(entry.get('value'))
    return result


def endpoint(s, key, issues):
    if key not in s:
        issues.append('missing_start' if key == 'startTimeUnixNano' else 'missing_end')
        return None
    return integer(s[key], key, maximum=2**64-1)


def otlp_spans(doc, ref):
    for ri, resource_span in enumerate(array(doc.get('resourceSpans', []), 'resourceSpans')):
        resource_span = obj(resource_span, 'ResourceSpans')
        resource = attributes(obj(resource_span.get('resource',{}),'resource').get('attributes',[]))
        if 'scopeSpans' in resource_span and 'instrumentationLibrarySpans' in resource_span:
            invalid('ambiguous_scope','scopeSpans and instrumentationLibrarySpans cannot both appear')
        scope_key = 'instrumentationLibrarySpans' if 'instrumentationLibrarySpans' in resource_span else 'scopeSpans'
        for si, scope_span in enumerate(array(resource_span.get(scope_key,[]),scope_key)):
            scope_span=obj(scope_span,scope_key)
            scope=obj(scope_span.get('scope',scope_span.get('instrumentationLibrary',{})),'scope')
            name=string(scope.get('name',''),'scope.name');version=string(scope.get('version',''),'scope.version')
            for pi, s in enumerate(array(scope_span.get('spans',[]),'spans')):
                s=obj(s,'Span'); source=replace(ref,json_pointer=f'/resourceSpans/{ri}/{scope_key}/{si}/spans/{pi}')
                try:
                    tid=ident(s.get('traceId'),32,'traceId'); sid=ident(s.get('spanId'),16,'spanId')
                    pid=ident(s.get('parentSpanId',''),16,'parentSpanId',empty=True)
                    kind=s.get('kind',0)
                    if isinstance(kind,str): raise ClockWeaveError('unsupported','symbolic_kind','OTLP kind must use integer enum encoding')
                    if type(kind) is not int or kind not in range(6): invalid('invalid_kind','OTLP kind must be an integer from 0 through 5')
                    issues=[];start=endpoint(s,'startTimeUnixNano',issues);end=endpoint(s,'endTimeUnixNano',issues)
                    if start is not None and end is not None and end<start:issues.append('negative_raw_duration')
                    yield Span((tid,sid),string(s.get('name',''),'span.name'),kind,(tid,pid) if pid else None,
                               start,end,resource,attributes(s.get('attributes',[])),name,version,(),(source,),tuple(issues))
                except ClockWeaveError as e:
                    if e.source is None:e.source=source
                    raise


def tags(values):
    result={}
    for tag in array(values,'tags'):
        tag=obj(tag,'tag');key=string(tag.get('key'),'tag.key');kind=tag.get('type');value=tag.get('value')
        if key in result:invalid('duplicate_attribute',f'duplicate tag {key!r}')
        if kind=='string':value=string(value,'string tag')
        elif kind in ('int64','int'):
            value=integer(value,'integer tag',maximum=2**63-1,signed=True)
            if value < -(2**63):invalid('integer_range','Integer tag out of signed 64-bit range')
        elif kind=='bool':
            if type(value) is not bool:invalid('invalid_bool','boolean tag requires boolean value')
        elif kind=='float64':
            if type(value) not in (int,float):invalid('invalid_double','float tag requires finite number')
            try:value=float(value)
            except (OverflowError,ValueError):invalid('invalid_double','Float tag is not representable as a finite double')
            if not math.isfinite(value):invalid('invalid_double','float tag requires finite number')
        elif kind=='binary': value={'__jaeger_bytes__':string(value,'binary tag')}
        else:raise ClockWeaveError('unsupported','tag_type',f'Unsupported Jaeger tag type {kind!r}')
        result[key]=value
    return result


def jaeger_spans(doc,ref):
    for ti,trace in enumerate(array(doc.get('data',[]),'data')):
        trace=obj(trace,'trace');processes=obj(trace.get('processes',{}),'processes')
        trace_id=ident(trace.get('traceID'),32,'traceID',legacy=True)
        for si,s in enumerate(array(trace.get('spans',[]),'spans')):
            s=obj(s,'span');source=replace(ref,json_pointer=f'/data/{ti}/spans/{si}')
            try:
                tid=ident(s.get('traceID',trace_id),32,'span.traceID',legacy=True)
                if tid!=trace_id:invalid('trace_mismatch','Jaeger span traceID conflicts with containing trace')
                sid=ident(s.get('spanID'),16,'spanID');issues=[]
                process_id=s.get('processID')
                if 'processID' in s:string(process_id,'processID')
                process=obj(processes.get(process_id,{}),'process')
                if process_id not in processes:issues.append('missing_process')
                resource=tags(process.get('tags',[]))
                if 'serviceName' in process:resource['service.name']=string(process['serviceName'],'serviceName')
                attrs=tags(s.get('tags',[]));kind_value=attrs.get('span.kind');kind={'internal':1,'server':2,'client':3,'producer':4,'consumer':5}.get(kind_value,0) if isinstance(kind_value,str) else 0
                if 'startTime' not in s: start=None;issues.append('missing_start')
                else:start=1000*integer(s['startTime'],'startTime')
                if 'duration' not in s: end=None;issues.append('missing_end')
                else:
                    duration=1000*integer(s['duration'],'duration');end=None if start is None else start+duration
                parents=[]
                for r in array(s.get('references',[]),'references'):
                    r=obj(r,'reference')
                    if r.get('refType')=='CHILD_OF':
                        rt=ident(r.get('traceID'),32,'reference.traceID',legacy=True);rs=ident(r.get('spanID'),16,'reference.spanID')
                        parents.append((rt,rs))
                parent=None
                if len(parents)>1:issues.append('ambiguous_parent')
                elif parents:
                    if parents[0][0]!=tid:issues.append('cross_trace_parent')
                    else:parent=parents[0]
                warnings=s.get('warnings',[])
                if warnings is None:warnings=[]
                if not isinstance(warnings,list):invalid('warnings_type','Jaeger warnings must be an array')
                warnings=tuple(string(w,'warning') for w in warnings)
                yield Span((tid,sid),string(s.get('operationName',''),'operationName'),kind,parent,start,end,resource,attrs,'','',warnings,(source,),tuple(issues))
            except ClockWeaveError as e:
                if e.source is None:e.source=source
                raise


def load_capture(inputs: Sequence[InputSource]) -> Capture:
    indexed={};files=[];duplicate_count=0;total_bytes=0;observed_records=0
    for source in inputs:
        path=Path(source.path)
        try:
            admit(total_bytes+path.stat().st_size,DEFAULT_LIMITS.max_input_bytes,'Total input bytes')
            raw=path.read_bytes()
        except OSError as e:raise ClockWeaveError('io_error','read_failed',f'Cannot read {path.name}: {e}') from e
        total_bytes+=len(raw);admit(total_bytes,DEFAULT_LIMITS.max_input_bytes,'Total input bytes')
        digest=hashlib.sha256(raw).hexdigest();fmt=source.format
        if fmt not in ('auto','otlp-json','otlp-jsonl','jaeger-json'):
            raise ClockWeaveError('unsupported','input_format',f'Unsupported input format {fmt!r}')
        if fmt=='auto' and path.suffix.lower() in ('.jsonl','.ndjson'):fmt='otlp-jsonl'
        try: text=raw.decode('utf-8')
        except UnicodeDecodeError as e:
            if raw.startswith(b'\x1f\x8b'):raise ClockWeaveError('unsupported','compressed_input','Compressed input is unsupported') from e
            invalid('invalid_utf8',f'{path.name} is not UTF-8 JSON')
        docs=[(i+1,decode_json(line)) for i,line in enumerate(text.splitlines()) if line.strip()] if fmt=='otlp-jsonl' else [(None,decode_json(text))]
        for di,(line,doc) in enumerate(docs):
            if not isinstance(doc,dict):raise ClockWeaveError('unsupported','input_shape','Expected an OTLP object or legacy Jaeger envelope')
            signatures=('resourceSpans' in doc,'data' in doc)
            if signatures==(True,True):raise ClockWeaveError('unsupported','ambiguous_format','Both OTLP and Jaeger signatures appear')
            if fmt=='auto':
                if signatures==(True,False) or not doc:fmt='otlp-json'
                elif signatures==(False,True):fmt='jaeger-json'
                else:raise ClockWeaveError('unsupported','input_shape','No supported trace-export signature found')
            expected='data' if fmt=='jaeger-json' else 'resourceSpans'
            if expected not in doc and (fmt=='jaeger-json' or 'data' in doc):raise ClockWeaveError('unsupported','input_shape',f'{fmt} requires {expected}')
            ref=SourceRef(digest,path.name,di,line,'')
            for span in (jaeger_spans(doc,ref) if fmt=='jaeger-json' else otlp_spans(doc,ref)):
                observed_records+=1;admit(observed_records,DEFAULT_LIMITS.max_spans,'Observed span records including duplicates')
                old=indexed.get(span.key)
                if old is not None:
                    if json.dumps(asdict(replace(old,sources=())),sort_keys=True)!=json.dumps(asdict(replace(span,sources=())),sort_keys=True):
                        invalid('conflicting_duplicate',f'conflicting duplicate span {span.key}; first source {old.sources[0].file_name}{old.sources[0].json_pointer}',span.sources[0])
                    duplicate_count+=1;span=replace(old,sources=old.sources+span.sources)
                indexed[span.key]=span
        files.append({'file_name':path.name,'sha256':digest,'format':fmt,'bytes':len(raw),'document_count':len(docs)})
    def source_order(ref):return (ref.file_sha256,ref.file_name,ref.document_index,-1 if ref.line is None else ref.line,ref.json_pointer)
    spans=tuple(replace(indexed[k],sources=tuple(sorted(indexed[k].sources,key=source_order))) for k in sorted(indexed))
    return Capture(spans,tuple(files),duplicate_count)
