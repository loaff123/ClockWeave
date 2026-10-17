"""Reference raw reader for replay, independent of production ingestion.

This deliberately repeats supported format interpretation using plain dictionaries.
It must not import ingestion, qualification or graph implementation modules.
"""
import base64
import hashlib
import json
import math
from pathlib import Path
from .limits import DEFAULT_LIMITS,admit


def require(ok,message):
    if not ok:raise ValueError(message)


def object_(x):
    require(type(x) is dict,'Expected object');return x


def list_(x):
    require(type(x) is list,'Expected array');return x


def string_(x):
    require(type(x) is str,'Expected string');return x


def number(x,signed=False,maximum=None):
    if type(x) is str:
        digits=x[1:] if signed and x.startswith('-') else x
        require(bool(digits) and digits.isascii() and digits.isdecimal(),'Expected decimal integer')
    else:require(type(x) is int,'Expected integer token')
    if type(x) is int:n=x
    else:
        minus=x.startswith('-');digits=x[1:] if minus else x;digits=digits.lstrip('0') or '0';n=0
        while digits:
            part,digits=digits[:9],digits[9:];n=n*(10**len(part))+int(part)
        if minus:n=-n
    require(signed or n>=0,'Expected nonnegative integer');require(maximum is None or n<=maximum,'Integer exceeds range')
    return n


def ns_text(value):
    negative=value<0;value=abs(value);digits=[]
    while value:
        value,part=divmod(value,10**9);digits.append(part)
    if not digits:return '0'
    return ('-' if negative else '')+str(digits[-1])+''.join(str(p).rjust(9,'0') for p in digits[-2::-1])


def finite_double(value):
    require(type(value) in (int,float),'Expected numeric double')
    try:converted=float(value)
    except (ValueError,OverflowError) as e:raise ValueError('Unrepresentable double') from e
    require(math.isfinite(converted),'Expected finite double');return converted


def _pairs(pairs):
    out={}
    for k,v in pairs:require(k not in out,'Duplicate JSON key');out[k]=v
    return out


def read_json(raw):
    def reject_constant(x):raise ValueError('Nonfinite JSON token '+x)
    return json.loads(raw,object_pairs_hook=_pairs,parse_constant=reject_constant)


def identifier(x,width,legacy=False,parent=False):
    if parent and x in (None,'','0'*width):return None
    string_(x);require(len(x) in ((16,32) if legacy and width==32 else (width,)),'Wrong identifier length')
    require(all(ch in '0123456789abcdefABCDEF' for ch in x) and int(x,16)!=0,'Invalid identifier')
    return x.lower().zfill(width)


def decode_attrs(values):
    result={}
    for pair in list_(values):
        pair=object_(pair);k=string_(pair.get('key'));require(k not in result,'Duplicate attribute');result[k]=decode_value(pair.get('value'))
    return result


def decode_value(value):
    value=object_(value);keys=set(value)&{'stringValue','boolValue','intValue','doubleValue','bytesValue','arrayValue','kvlistValue'}
    require(len(keys)==1,'Ambiguous AnyValue');tag=keys.pop();v=value[tag]
    if tag=='stringValue':return string_(v)
    if tag=='boolValue':require(type(v) is bool,'Expected boolValue');return v
    if tag=='intValue':
        result=number(v,True,2**63-1);require(result>=-2**63,'intValue underflow');return result
    if tag=='doubleValue':return finite_double(v)
    if tag=='bytesValue':base64.b64decode(string_(v),validate=True);return {'__otlp_bytes__':v}
    if tag=='arrayValue':return [decode_value(x) for x in list_(object_(v).get('values',[]))]
    return {'__otlp_kvlist__':decode_attrs(object_(v).get('values',[]))}


def decode_tags(values):
    result={}
    for entry in list_(values):
        entry=object_(entry);key=string_(entry.get('key'));require(key not in result,'Duplicate tag')
        kind=entry.get('type');v=entry.get('value')
        if kind=='string':v=string_(v)
        elif kind in ('int64','int'):v=number(v,True,2**63-1);require(v>=-2**63,'Integer tag underflow')
        elif kind=='bool':require(type(v) is bool,'Expected boolean tag')
        elif kind=='float64':v=finite_double(v)
        elif kind=='binary':v={'__jaeger_bytes__':string_(v)}
        else:raise ValueError('Unsupported tag type')
        result[key]=v
    return result


def _record(key,name,kind,parent,start,end,resource,attributes,scope,version,warnings,source,issues):
    return {'key':list(key),'name':name,'kind':kind,'parent':list(parent) if parent else None,
            'start_ns':None if start is None else ns_text(start),'end_ns':None if end is None else ns_text(end),
            'resource':resource,'attributes':attributes,'scope_name':scope,'scope_version':version,
            'warnings':warnings,'sources':[source],'issues':issues}


def _otlp(doc,source):
    for ri,r in enumerate(list_(doc.get('resourceSpans',[]))):
        r=object_(r);resource=decode_attrs(object_(r.get('resource',{})).get('attributes',[]))
        require(not ('scopeSpans' in r and 'instrumentationLibrarySpans' in r),'Ambiguous scope containers')
        field='instrumentationLibrarySpans' if 'instrumentationLibrarySpans' in r else 'scopeSpans'
        for qi,q in enumerate(list_(r.get(field,[]))):
            q=object_(q);scope=object_(q.get('scope',q.get('instrumentationLibrary',{})))
            sn=string_(scope.get('name',''));sv=string_(scope.get('version',''))
            for si,s in enumerate(list_(q.get('spans',[]))):
                s=object_(s);tid=identifier(s.get('traceId'),32);sid=identifier(s.get('spanId'),16)
                parent=identifier(s.get('parentSpanId',''),16,parent=True);kind=s.get('kind',0)
                require(type(kind) is int and 0<=kind<=5,'Unsupported or invalid kind')
                issues=[];ends=[]
                for key,missing in [('startTimeUnixNano','missing_start'),('endTimeUnixNano','missing_end')]:
                    if key in s:ends.append(number(s[key],maximum=2**64-1))
                    else:ends.append(None);issues.append(missing)
                if ends[0] is not None and ends[1] is not None and ends[1]<ends[0]:issues.append('negative_raw_duration')
                pointer=f'/resourceSpans/{ri}/{field}/{qi}/spans/{si}'
                yield _record((tid,sid),string_(s.get('name','')),kind,(tid,parent) if parent else None,*ends,resource,
                              decode_attrs(s.get('attributes',[])),sn,sv,[],dict(source,json_pointer=pointer),issues)


def _jaeger(doc,source):
    for ti,t in enumerate(list_(doc.get('data',[]))):
        t=object_(t);tid=identifier(t.get('traceID'),32,True);processes=object_(t.get('processes',{}))
        for si,s in enumerate(list_(t.get('spans',[]))):
            s=object_(s);st=identifier(s.get('traceID',tid),32,True);require(st==tid,'Containing trace conflict');sid=identifier(s.get('spanID'),16)
            pid=s.get('processID')
            if 'processID' in s:string_(pid)
            p=object_(processes.get(pid,{}));issues=[] if pid in processes else ['missing_process']
            resource=decode_tags(p.get('tags',[]))
            if 'serviceName' in p:resource['service.name']=string_(p['serviceName'])
            attrs=decode_tags(s.get('tags',[]));tag_kind=attrs.get('span.kind');kind={'internal':1,'server':2,'client':3,'producer':4,'consumer':5}.get(tag_kind,0) if type(tag_kind) is str else 0
            start=None;end=None
            if 'startTime' in s:start=number(s['startTime'])*1000
            else:issues.append('missing_start')
            if 'duration' in s:
                duration=number(s['duration'])*1000
                if start is not None:end=start+duration
            else:issues.append('missing_end')
            parents=[]
            for ref in list_(s.get('references',[])):
                ref=object_(ref)
                if ref.get('refType')=='CHILD_OF':parents.append((identifier(ref.get('traceID'),32,True),identifier(ref.get('spanID'),16)))
            parent=None
            if len(parents)>1:issues.append('ambiguous_parent')
            elif parents:
                if parents[0][0]==tid:parent=parents[0]
                else:issues.append('cross_trace_parent')
            raw_warnings=s.get('warnings',[]);warnings=[string_(x) for x in list_([] if raw_warnings is None else raw_warnings)]
            yield _record((tid,sid),string_(s.get('operationName','')),kind,parent,start,end,resource,attrs,'','',warnings,dict(source,json_pointer=f'/data/{ti}/spans/{si}'),issues)


def read_capture(inputs):
    observations={};metadata=[];duplicates=0;total_bytes=0;records=0
    for item in inputs:
        path=Path(item.path);admit(total_bytes+path.stat().st_size,DEFAULT_LIMITS.max_input_bytes,'Total input bytes');raw=path.read_bytes();total_bytes+=len(raw);admit(total_bytes,DEFAULT_LIMITS.max_input_bytes,'Total input bytes');sha=hashlib.sha256(raw).hexdigest();fmt=item.format
        require(fmt in ('auto','otlp-json','otlp-jsonl','jaeger-json'),'Unsupported format')
        if fmt=='auto' and path.suffix.lower() in ('.jsonl','.ndjson'):fmt='otlp-jsonl'
        text=raw.decode('utf-8')
        docs=[(line_no,read_json(line)) for line_no,line in enumerate(text.splitlines(),1) if line.strip()] if fmt=='otlp-jsonl' else [(None,read_json(text))]
        for di,(line,doc) in enumerate(docs):
            object_(doc);require(not ('resourceSpans' in doc and 'data' in doc),'Conflicting formats')
            if fmt=='auto':
                if 'resourceSpans' in doc or not doc:fmt='otlp-json'
                elif 'data' in doc:fmt='jaeger-json'
                else:raise ValueError('Unsupported export shape')
            require('data' in doc if fmt=='jaeger-json' else 'data' not in doc,'Format does not match contents')
            source={'file_sha256':sha,'file_name':path.name,'document_index':di,'line':line,'json_pointer':''}
            for span in (_jaeger(doc,source) if fmt=='jaeger-json' else _otlp(doc,source)):
                records+=1;admit(records,DEFAULT_LIMITS.max_spans,'Observed span records including duplicates')
                key=tuple(span['key'])
                if key in observations:
                    prior=observations[key]
                    old={k:v for k,v in prior.items() if k!='sources'};new={k:v for k,v in span.items() if k!='sources'}
                    require(json.dumps(old,sort_keys=True)==json.dumps(new,sort_keys=True),'Conflicting duplicate spans')
                    prior['sources']+=span['sources'];duplicates+=1
                else:observations[key]=span
        metadata.append({'file_name':path.name,'sha256':sha,'format':fmt,'bytes':len(raw),'document_count':len(docs)})
    for span in observations.values():
        span['sources'].sort(key=lambda ref:(ref['file_sha256'],ref['file_name'],ref['document_index'],-1 if ref['line'] is None else ref['line'],ref['json_pointer']))
    return [observations[k] for k in sorted(observations)],sorted(metadata,key=lambda i:(i['sha256'],i['file_name'],i['format'])),duplicates
