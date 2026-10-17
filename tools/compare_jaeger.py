"""Execute pinned Jaeger 2.22.0 itself on an exact shared export view.

Requires an operator-supplied official binary whose checksum was checked.
No Jaeger code is copied or reimplemented. Local transient in-memory service only.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import urllib.request


def port():
    with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]


def query(binary,doc,out,mode):
    query_port,ingest_port,grpc_port=port(),port(),port()
    config=f'''service:
  extensions: [jaeger_storage, jaeger_query]
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [jaeger_storage_exporter]
  telemetry:
    logs:
      level: warn
    metrics:
      level: none
extensions:
  jaeger_storage:
    backends:
      memory_store:
        memory:
          max_traces: 10000
  jaeger_query:
    storage:
      traces: memory_store
    http:
      endpoint: 127.0.0.1:{query_port}
    grpc:
      endpoint: 127.0.0.1:{grpc_port}
    max_clock_skew_adjust: {'0s' if mode=='raw' else '1s'}
receivers:
  otlp:
    protocols:
      http:
        endpoint: 127.0.0.1:{ingest_port}
exporters:
  jaeger_storage_exporter:
    trace_storage: memory_store
'''
    config_path=out/(mode+'.yaml');config_path.write_text(config)
    trace_ids=sorted({s['traceId'] for r in doc['resourceSpans'] for sc in r['scopeSpans'] for s in sc['spans']})
    log=(out/(mode+'.log')).open('w');command=[str(binary),'--config',str(config_path)]
    environment=dict(os.environ)
    # Isolate only this benchmark child from ambient self-telemetry exporters.
    environment.update(OTEL_TRACES_EXPORTER="none",OTEL_METRICS_EXPORTER="none",OTEL_LOGS_EXPORTER="none")
    proc=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,env=environment)
    try:
        deadline=time.monotonic()+20
        while True:
            if proc.poll() is not None:raise RuntimeError('Jaeger exited: '+(out/(mode+'.log')).read_text()[-4000:])
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{query_port}/api/v3/services',timeout=1) as r:r.read()
                break
            except (OSError,TimeoutError):
                if time.monotonic()>deadline:raise RuntimeError('Jaeger startup timed out')
                time.sleep(.05)
        payload=json.dumps(doc).encode()
        request=urllib.request.Request(f'http://127.0.0.1:{ingest_port}/v1/traces',data=payload,headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(request,timeout=10) as r:response=r.read()
        result={'data':[]}
        for tid in trace_ids:
            deadline=time.monotonic()+10
            while True:
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{query_port}/api/traces/{tid}',timeout=5) as r:one=json.load(r)
                    if one.get('data'):result['data'].extend(one['data']);break
                except OSError:pass
                if time.monotonic()>deadline:raise RuntimeError('Trace did not become queryable: '+tid)
                time.sleep(.05)
        (out/(mode+'.jaeger.json')).write_text(json.dumps(result,indent=2)+'\n')
        return result,command,response.decode()
    finally:
        proc.terminate()
        try:proc.wait(timeout=10)
        except subprocess.TimeoutExpired:proc.kill();proc.wait()
        log.close()


def compare_jaeger(binary: Path,capture_path: Path,output_dir: Path) -> dict:
    binary=Path(binary).resolve();capture_path=Path(capture_path);out=Path(output_dir);out.mkdir(parents=True,exist_ok=False)
    original=capture_path.read_bytes();doc=json.loads(original);rounded=copy.deepcopy(doc);expected={}
    for r in rounded['resourceSpans']:
        for sc in r['scopeSpans']:
            for s in sc['spans']:
                for key in ('startTimeUnixNano','endTimeUnixNano'):s[key]=str(int(s[key])//1000*1000)
                expected[(s['traceId'],s['spanId'])]=(int(s['startTimeUnixNano'])//1000,int(s['endTimeUnixNano'])//1000)
    (out/'shared-rounded.otlp.json').write_text(json.dumps(rounded,indent=2)+'\n')
    before,raw_cmd,raw_response=query(binary,rounded,out,'raw');after,adj_cmd,adj_response=query(binary,rounded,out,'adjusted')
    def index(result):return {(s['traceID'].zfill(32),s['spanID']):s for t in result['data'] for s in t['spans']}
    raw,adjusted=index(before),index(after)
    exact=set(raw)==set(expected) and all((s['startTime'],s['startTime']+s['duration'])==expected[key] for key,s in raw.items())
    if not exact:raise AssertionError('Jaeger disabled-adjustment endpoint roundtrip is not exact')
    differences=[]
    for key,s in sorted(raw.items()):
        a=adjusted[key]
        differences.append({'trace_id':key[0],'span_id':key[1],'name':s['operationName'],'raw_start_us':str(s['startTime']),
            'adjusted_start_us':str(a['startTime']),'delta_us':str(a['startTime']-s['startTime']),
            'duration_us':str(s['duration']),'raw_warnings':s.get('warnings') or [],'adjusted_warnings':a.get('warnings') or []})
    result={'upstream':'Jaeger official runtime','upstream_version':'2.22.0','source':'https://github.com/jaegertracing/jaeger/releases/tag/v2.22.0',
        'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'original_otlp_sha256':hashlib.sha256(original).hexdigest(),
        'precision':'Both endpoints floored to microseconds before ingestion; raw queried Jaeger JSON is the exact shared analysis input.',
        'raw_endpoint_roundtrip_exact':exact,'span_count':len(raw),'changed_span_count':sum(d['delta_us']!='0' for d in differences),
        'child_telemetry_exporters':'none (benchmark child only; no system settings changed)','commands':[raw_cmd,adj_cmd],'ingest_responses':[raw_response,adj_response],'differences':differences,
        'comparison_limit':'Jaeger performs recursive per-trace display correction with warnings. ClockWeave tests a global explicitly qualified constant-domain/epoch model. Different intended outputs are not baseline failures.'}
    (out/'comparison.json').write_text(json.dumps(result,indent=2)+'\n')
    assert capture_path.read_bytes()==original
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--binary',type=Path,required=True);p.add_argument('--capture',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=compare_jaeger(a.binary,a.capture,a.output);print(json.dumps({k:r[k] for k in ('upstream_version','span_count','changed_span_count','raw_endpoint_roundtrip_exact')}))
