"""Original small evidence builders; no third-party trace data."""
import json
from pathlib import Path

def attr(key, value):
    kind = 'boolValue' if isinstance(value, bool) else 'intValue' if isinstance(value, int) else 'stringValue'
    return {'key': key, 'value': {kind: str(value) if kind == 'intValue' else value}}

def span(i=1, trace=1, start=1800000000000000001, end=1800000000000000011, parent=None, **kwargs):
    s = {'traceId': f'{trace:032x}', 'spanId': f'{i:016x}', 'name': 'operation', 'kind': 3,
         'startTimeUnixNano': str(start), 'endTimeUnixNano': str(end)}
    if parent is not None: s['parentSpanId'] = f'{parent:016x}'
    s.update(kwargs)
    return s

def otlp(spans=None, domain='A', epoch='driver'):
    return {'resourceSpans': [{'resource': {'attributes': [attr('clockweave.clock.domain', domain), attr('clockweave.clock.epoch', epoch)]},
                              'scopeSpans': [{'scope': {'name': 'clockweave.loopback'}, 'spans': spans if spans is not None else [span()]}]}]}

def write_json(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2) + '\n', encoding='utf-8')
    return Path(path)

def jaeger():
    return {'data': [{'traceID': '0000000000000001', 'processes': {'p1': {'serviceName': 'demo', 'tags': []}}, 'spans': [
        {'traceID': '0000000000000001', 'spanID': '0000000000000001', 'operationName': 'call', 'processID': 'p1',
         'startTime': 123, 'duration': 7, 'references': [], 'tags': [{'key':'span.kind','type':'string','value':'client'}]}]}]}

def contract():
    return {'schema':'clockweave.contract.v1','provenance':{'state':'raw','assumption':'Direct original fixture','evidence':['test fixture']},
        'identities':[{'id':'explicit','select':{},'domain':{'resource_attribute':'clockweave.clock.domain'},'epoch':{'resource_attribute':'clockweave.clock.epoch'},'assumption':'Declared clocks and epochs','evidence':['test fixture']}],
        'boundaries':[{'id':'rpc','client':{'names':['call'],'kinds':[3]},'server':{'names':['serve'],'kinds':[2]},'link':'parent','relations':[
            {'kind':'start_order','slack_ns':'0','assumption':'Starts before send and after receive','evidence':['test fixture']},
            {'kind':'end_enclosure','slack_ns':'0','assumption':'Ends before response release and after consumption','evidence':['test fixture']}]}],
        'exclusions':[{'id':'async','select':{'kinds':[4,5]},'reason':'No qualified async semantics'}],
        'anchor':{'domain':'A','epoch':'driver'}}

def rpc_doc(last_start=248):
    base=1800000000000000001;resources=[]
    for i,(a,b,cs,ce,ss,se) in enumerate([('A','B',0,10,20,28),('B','C',100,110,130,138),('A','C',200,210,last_start,last_start+8)],1):
        for domain,s in [(a,span(2*i,trace=i,start=base+cs,end=base+ce,name='call',kind=3)),
                         (b,span(2*i+1,trace=i,start=base+ss,end=base+se,parent=2*i,name='serve',kind=2))]:
            resources.extend(otlp([s],domain=domain)['resourceSpans'])
    return {'resourceSpans':resources}
