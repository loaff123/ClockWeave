"""Original application-owned OpenTelemetry capture with real process restarts.

Optional dependencies: opentelemetry-sdk, opentelemetry-exporter-otlp-proto-http.
Actual loopback I/O; timestamp offsets are deliberate instrumentation injections.
No machine clock or OS settings are changed. No calibration claim is made.
"""
from __future__ import annotations
import argparse
import base64
import faulthandler
import hashlib
import json
import multiprocessing as mp
import os
from pathlib import Path
import threading
import time
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version
from google.protobuf.json_format import MessageToDict
from opentelemetry import trace
from opentelemetry.trace import SpanKind
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.sampling import ALWAYS_ON
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.exporter.otlp.proto.common.trace_encoder import encode_spans
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

PROP=TraceContextTextMapPropagator()

class Collector(SpanExporter):
    def __init__(self):self.spans=[];self.lock=threading.Lock()
    def export(self,spans):
        with self.lock:self.spans.extend(spans)
        return SpanExportResult.SUCCESS

class Clock:
    def __init__(self,domain,epoch,offset):
        self.domain,self.epoch,self.offset=domain,epoch,offset
        self.collector=Collector()
        self.provider=TracerProvider(sampler=ALWAYS_ON,resource=Resource({
            'service.name':'clockweave-loopback-'+domain,'service.instance.id':domain+'-'+epoch,
            'clockweave.clock.domain':domain,'clockweave.clock.epoch':epoch,
            'clockweave.timestamp.state':'raw'}))
        self.provider.add_span_processor(SimpleSpanProcessor(self.collector))
        self.tracer=self.provider.get_tracer('clockweave.loopback','1')
    def start(self,name,kind,context=None):
        return self.tracer.start_span(name,kind=kind,context=context,start_time=time.time_ns()+self.offset)
    def end(self,span):span.end(end_time=time.time_ns()+self.offset)
    def save(self,path):
        self.provider.force_flush();path.write_bytes(encode_spans(self.collector.spans).SerializeToString());self.provider.shutdown()

def request(clock,url,context=None,headers_only=False,downstream=None):
    span=clock.start('client-until-headers' if headers_only else 'fully-consumed-rpc',SpanKind.CLIENT,context)
    headers={};PROP.inject(headers,context=trace.set_span_in_context(span))
    if downstream:headers['X-Clockweave-Downstream']=downstream
    ended=False
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=8) as response:
            if headers_only:clock.end(span);ended=True
            return response.read()
    finally:
        if not ended:clock.end(span)

def service(domain,epoch,offset,connection,output):
    # Preserve a stack trace if startup stalls before the parent readiness deadline.
    faulthandler.dump_traceback_later(10, repeat=False)
    clock=Clock(domain,epoch,offset)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            context=PROP.extract({k.lower():v for k,v in self.headers.items()})
            headers_only=self.path=='/headers';asynchronous=self.path=='/async'
            name='server-through-response-body' if headers_only else 'background-outlives-parent' if asynchronous else 'handler-before-response'
            span=clock.start(name,SpanKind.CONSUMER if asynchronous else SpanKind.SERVER,context)
            if headers_only:
                self.send_response(200);self.send_header('Content-Length','2');self.end_headers();self.wfile.flush()
                time.sleep(.040);self.wfile.write(b'ok');self.wfile.flush();clock.end(span)
                return
            try:
                time.sleep(.020 if asynchronous else .002)
                downstream=self.headers.get('X-Clockweave-Downstream')
                if domain=='B' and downstream:
                    request(clock,downstream,trace.set_span_in_context(span))
            finally:
                # Qualified boundary: span ends before releasing any response bytes.
                clock.end(span)
            self.send_response(200);self.send_header('Content-Length','2');self.end_headers();self.wfile.write(b'ok');self.wfile.flush()
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    def control():
        try:connection.recv()
        except EOFError:pass
        server.shutdown()
    threading.Thread(target=control,daemon=True).start()
    connection.send({'event':'started','domain':domain,'epoch':epoch,'pid':os.getpid(),'port':server.server_port,'observed_time_ns':str(time.time_ns())})
    faulthandler.cancel_dump_traceback_later()
    try:server.serve_forever(poll_interval=.01)
    finally:
        server.server_close();clock.save(Path(output)/('process-'+epoch+'.pb'))
        connection.send({'event':'stopped','domain':domain,'epoch':epoch,'pid':os.getpid(),'observed_time_ns':str(time.time_ns())})
        connection.close()

def hex_ids(value):
    if isinstance(value,list):return [hex_ids(v) for v in value]
    if isinstance(value,dict):return {k:(base64.b64decode(v).hex() if k in ('traceId','spanId','parentSpanId') else hex_ids(v)) for k,v in value.items()}
    return value

def simple_attributes(attrs):
    result={}
    for a in attrs:
        v=a['value']
        if 'stringValue' in v:result[a['key']]=v['stringValue']
        elif 'intValue' in v:result[a['key']]=int(v['intValue'])
        elif 'boolValue' in v:result[a['key']]=v['boolValue']
    return result

def jaeger_view(raw):
    traces={}
    def tags(attrs):
        return [{'key':k,'type':'bool' if type(v) is bool else 'int64' if type(v) is int else 'string','value':v} for k,v in attrs.items()]
    kinds={1:'internal',2:'server',3:'client',4:'producer',5:'consumer'}
    for ri,r in enumerate(raw['resourceSpans']):
        attrs=simple_attributes(r.get('resource',{}).get('attributes',[]));pid='p'+str(ri)
        for scope in r['scopeSpans']:
            for s in scope['spans']:
                tid=s['traceId'];t=traces.setdefault(tid,{'traceID':tid,'spans':[],'processes':{}})
                t['processes'][pid]={'serviceName':attrs.get('service.name',''),'tags':tags(attrs)}
                start=int(s['startTimeUnixNano'])//1000;end=int(s['endTimeUnixNano'])//1000
                a=simple_attributes(s.get('attributes',[]));a['span.kind']=kinds.get(s.get('kind',0),'unspecified')
                t['spans'].append({'traceID':tid,'spanID':s['spanId'],'operationName':s.get('name',''),'processID':pid,
                    'startTime':start,'duration':end-start,'tags':tags(a),'logs':[],
                    'references':[{'refType':'CHILD_OF','traceID':tid,'spanID':s['parentSpanId']}] if s.get('parentSpanId') else []})
    return {'data':[traces[k] for k in sorted(traces)]}

def capture(output_dir: Path) -> dict:
    output_dir=Path(output_dir);output_dir.mkdir(parents=True,exist_ok=False)
    ctx=mp.get_context('spawn');active=[];lifecycle=[];clocks=[{'domain':'A','epoch':'driver','injected_offset_ns':'0'}]
    driver=Clock('A','driver',0)
    def launch(domain,offset):
        epoch=uuid.uuid4().hex;parent,child=ctx.Pipe();p=ctx.Process(target=service,args=(domain,epoch,offset,child,str(output_dir)))
        p.start();child.close()
        if not parent.poll(15):p.terminate();p.join();raise RuntimeError('Service startup timed out')
        started=parent.recv();lifecycle.append(started);item=(p,parent,started);active.append(item)
        clocks.append({'domain':domain,'epoch':epoch,'injected_offset_ns':str(offset)})
        return item,'http://127.0.0.1:'+str(started['port'])
    def stop(item):
        p,connection,started=item;connection.send('stop')
        if not connection.poll(10):p.terminate();p.join();raise RuntimeError('Service stop acknowledgment timed out')
        lifecycle.append(connection.recv());p.join(10)
        if p.is_alive():p.terminate();p.join();raise RuntimeError('Service did not exit')
        if p.exitcode!=0:raise RuntimeError('Service failed: '+str(p.exitcode))
        connection.close();active.remove(item)
    try:
        c1,curl=launch('C',-10_000_000);b,burl=launch('B',20_000_000)
        request(driver,burl+'/full',downstream=curl+'/full');request(driver,curl+'/full')
        request(driver,curl+'/headers',headers_only=True)
        producer=driver.start('enqueue-background',SpanKind.PRODUCER);headers={};PROP.inject(headers,context=trace.set_span_in_context(producer));driver.end(producer)
        with urllib.request.urlopen(urllib.request.Request(curl+'/async',headers=headers),timeout=8) as response:response.read()
        stop(c1)
        c2,curl=launch('C',400_000_000)
        request(driver,burl+'/full',downstream=curl+'/full');request(driver,curl+'/full')
        stop(c2);stop(b)
    finally:
        for item in list(active):
            try:stop(item)
            except Exception:
                if item[0].is_alive():item[0].terminate();item[0].join()
        driver.save(output_dir/'driver.pb')
    request_message=ExportTraceServiceRequest()
    for p in sorted(output_dir.glob('*.pb')):
        part=ExportTraceServiceRequest();part.ParseFromString(p.read_bytes());request_message.MergeFrom(part)
    protobuf=request_message.SerializeToString();(output_dir/'original.pb').write_bytes(protobuf)
    raw=hex_ids(MessageToDict(request_message,use_integers_for_enums=True))
    (output_dir/'original.otlp.json').write_text(json.dumps(raw,indent=2)+'\n')
    (output_dir/'original.otlp.jsonl').write_text(''.join(json.dumps({'resourceSpans':[r]})+'\n' for r in raw['resourceSpans']))
    (output_dir/'comparison.jaeger.json').write_text(json.dumps(jaeger_view(raw),indent=2)+'\n')
    metadata={'workflow':'application-owned Python OpenTelemetry loopback HTTP','sdk_version':version('opentelemetry-sdk'),
        'protobuf_version':version('protobuf'),'physical_host_count':1,'system_clock_modified':False,
        'per_capture_manual_annotations':0,'lifecycle':lifecycle,'clocks':clocks,
        'conversion':'Official OTLP protobuf encoder -> protobuf JSON dictionary with hex IDs and integer enums; comparison view floors both endpoints to integer microseconds.',
        'claim_limit':'Injected instrumentation offsets, actual separate processes/restart and loopback HTTP; not physical clock measurement.',
        'sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output_dir.glob('*') if p.is_file()}}
    (output_dir/'capture-metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    return metadata

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=capture(args.output)
    print(json.dumps({'output':str(args.output),'process_starts':sum(e['event']=='started' for e in result['lifecycle']),'manual_annotations':0}))
