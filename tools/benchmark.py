"""Original capture generator and measured whole-workflow qualification.

This measures particular workloads; it is not a security/resource guarantee.
Run each --worker case in a fresh process so peak RSS is meaningful.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import resource
import sys
import time
from clockweave import InputSource,load_capture,load_contract,inspect_capture,analyze,verify_report,render_html


def generate(spans,domains,dense,attribute_bytes=0):
    groups=[[] for _ in range(domains)];base=1800000000000000001
    for i in range(spans//2):
        client=i%domains
        server=((i//domains)%(domains-1)+client+1)%domains if dense else (client+1)%domains
        tid=f'{i+1:032x}';first=2*i+1;true=base+i*1000
        for domain,sid,parent,name,kind,start,end in [(client,first,None,'call',3,true,true+10),(server,first+1,first,'serve',2,true+2,true+8)]:
            s={'traceId':tid,'spanId':f'{sid:016x}','name':name,'kind':kind,'startTimeUnixNano':str(start+domain*1000),'endTimeUnixNano':str(end+domain*1000)}
            if attribute_bytes:s['attributes']=[{'key':'application.context','value':{'stringValue':'x'*attribute_bytes}}]
            if parent is not None:s['parentSpanId']=f'{parent:016x}'
            groups[domain].append(s)
    def a(k,v):return {'key':k,'value':{'stringValue':v}}
    doc={'resourceSpans':[{'resource':{'attributes':[a('clockweave.clock.domain',f'D{d:03d}'),a('clockweave.clock.epoch','run')]},'scopeSpans':[{'scope':{'name':'clockweave.benchmark'},'spans':values}]} for d,values in enumerate(groups)]}
    relation=lambda kind:{'kind':kind,'slack_ns':'0','assumption':'Original controlled fixture endpoint ordering','evidence':['tools/benchmark.py']}
    con={'schema':'clockweave.contract.v1','provenance':{'state':'raw','assumption':'Original generated qualification workload','evidence':['tools/benchmark.py']},
         'identities':[{'id':'declared','select':{},'domain':{'resource_attribute':'clockweave.clock.domain'},'epoch':{'resource_attribute':'clockweave.clock.epoch'},'assumption':'Explicit generated constant domain offsets','evidence':['tools/benchmark.py']}],
         'boundaries':[{'id':'rpc','client':{'names':['call'],'kinds':[3]},'server':{'names':['serve'],'kinds':[2]},'link':'parent','relations':[relation('start_order'),relation('end_enclosure')]}],
         'anchor':{'domain':'D000','epoch':'run'}}
    return doc,con


def run(spans,domains,dense,output,attribute_bytes=0):
    out=Path(output);out.mkdir(parents=True,exist_ok=True);doc,con=generate(spans,domains,dense,attribute_bytes)
    path=out/'generated.otlp.json';cp=out/'contract.json';path.write_text(json.dumps(doc));cp.write_text(json.dumps(con));del doc,con
    digest=hashlib.sha256(path.read_bytes()).hexdigest();times={};t=time.perf_counter();cap=load_capture([InputSource(path)]);contract=load_contract(cp);times['load']=time.perf_counter()-t
    t=time.perf_counter();inventory=inspect_capture(cap,contract);assert inventory['span_count']==spans;times['inspect']=time.perf_counter()-t;del inventory
    t=time.perf_counter();report=analyze(cap,contract);times['analyze']=time.perf_counter()-t;assert report['status']=='compatible'
    t=time.perf_counter();verified=verify_report(report,[InputSource(path)],cp);times['verify']=time.perf_counter()-t;assert verified['valid'],verified
    t=time.perf_counter();encoded=json.dumps(report,indent=2);json_size=len(encoded.encode());times['json']=time.perf_counter()-t;del encoded
    t=time.perf_counter();html=render_html(report);html_size=len(html.encode());times['html']=time.perf_counter()-t;del html
    assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
    result={'spans':spans,'domains':domains,'dense':dense,'attribute_bytes_per_span':attribute_bytes,'graph_edges':report['coverage']['graph_edge_count'],'raw_constraints':report['coverage']['raw_constraint_count'],
            'seconds':times,'total_seconds':sum(times.values()),'peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024*1024 if sys.platform=='darwin' else 1024),
            'input_bytes':path.stat().st_size,'json_bytes':json_size,'html_bytes':html_size,'replay_valid':True,
            'environment':{'python':platform.python_version(),'platform':platform.platform(),'machine':platform.machine()},
            'limits':'Measured generated workload only; not a hostile-input or OS resource guarantee.'}
    (out/'measurement.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--spans',type=int,required=True);p.add_argument('--domains',type=int,required=True);p.add_argument('--dense',action='store_true');p.add_argument('--attribute-bytes',type=int,default=0);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.spans<2 or a.spans%2 or a.domains<2:p.error('Use an even span count and at least two domains')
    run(a.spans,a.domains,a.dense,a.output,a.attribute_bytes)
