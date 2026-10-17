import random
from clockweave.graph import solve_graph
from clockweave.model import Constraint
from clockweave.contract import load_contract
from clockweave.ingest import load_capture
from clockweave.extract import extract
from clockweave.model import InputSource
from .helpers import rpc_doc,contract,write_json

def edge(i,u,v,w):return Constraint(str(i),u,v,w,'start_order','test',('t','c'),('t','s'),(0,w),0,())

def check(variables,edges,anchor,result):
    by={e.id:e for e in edges}
    def assignment(a):
        assert set(a)==set(variables) and int(a[anchor])==0
        assert all(int(a[e.to_id])-int(a[e.from_id])<=e.weight_ns for e in edges)
    if result['contradiction'] is not None:
        es=[by[k] for k in result['contradiction']['constraint_ids']]
        assert es and all(e.to_id==es[(i+1)%len(es)].from_id for i,e in enumerate(es))
        assert sum(e.weight_ns for e in es)==int(result['contradiction']['sum_ns'])<0
        return
    solution=result['solution'];assignment(solution['example_ns'])
    for r in solution['ranges']:
        for side in ('lower','upper'):
            bound=r[side];source,target=(r['variable'],anchor) if side=='lower' else (anchor,r['variable'])
            if bound['value_ns'] is None:
                reachable=set(bound['reachable']);assert source in reachable and target not in reachable
                assert not any(e.from_id in reachable and e.to_id not in reachable for e in edges)
            else:
                assignment(bound['attaining_ns']);assert int(bound['attaining_ns'][r['variable']])==int(bound['value_ns'])
                current=source;total=0
                for eid in bound['path']:
                    e=by[eid];assert e.from_id==current;current=e.to_id;total+=e.weight_ns
                assert current==target and total==(-1 if side=='lower' else 1)*int(bound['value_ns'])

def extracted(tmp_path,last=248,anchor='A'):
    c=contract();c['anchor']['domain']=anchor
    return extract(load_capture([InputSource(write_json(tmp_path/'t.json',rpc_doc(last)))]),load_contract(write_json(tmp_path/'c.json',c)))

def test_three_domain_coupled_ranges(tmp_path):
    e=extracted(tmp_path);variables=[v['id'] for v in e.variables];r=solve_graph(variables,e.constraints,e.anchor);check(variables,e.constraints,e.anchor,r)
    assert [(x['lower']['value_ns'],x['upper']['value_ns']) for x in r['solution']['ranges']]==[('0','0'),('-20','-18'),('-48','-46')]
    e=extracted(tmp_path,240);r=solve_graph(variables,e.constraints,e.anchor);check(variables,e.constraints,e.anchor,r)
    assert r['contradiction']['sum_ns']=='-6'

def test_anchor_c_normalized(tmp_path):
    e=extracted(tmp_path,anchor='C');variables=[v['id'] for v in e.variables];r=solve_graph(variables,e.constraints,e.anchor);check(variables,e.constraints,e.anchor,r)
    assert r['solution']['example_ns'][e.anchor]=='0'
    assert [(x['lower']['value_ns'],x['upper']['value_ns']) for x in r['solution']['ranges']]==[('46','48'),('28','30'),('0','0')]

def test_same_domain_negative_self_loop():
    for weight in (-1,0,10):
        es=[edge(0,'A','A',weight)];r=solve_graph(['A'],es,'A');check(['A'],es,'A',r)
        assert (r['contradiction'] is not None)==(weight<0)

def test_unbounded_cut():
    es=[edge(0,'A','B',5)];r=solve_graph(['A','B'],es,'A');check(['A','B'],es,'A',r)
    b=r['solution']['ranges'][1];assert b['upper']['value_ns']=='5' and b['lower']['value_ns'] is None

def test_zero_cycle_path_terminates():
    es=[edge(0,'A','B',0),edge(1,'B','C',0),edge(2,'C','B',0),edge(3,'C','A',0)]
    r=solve_graph(['A','B','C'],es,'C');check(['A','B','C'],es,'C',r)
    assert all(x['upper']['value_ns']=='0' for x in r['solution']['ranges'])

def test_disconnected_joint_example():
    es=[edge(0,'A','B',1),edge(1,'D','E',-8)]
    r=solve_graph(['A','B','D','E'],es,'B');check(['A','B','D','E'],es,'B',r)
    assert len(r['components'])==2
    for x in r['solution']['ranges'][2:]:assert x['lower']['value_ns'] is None and x['upper']['value_ns'] is None

def test_parallel_edges_all_checked():
    es=[edge(0,'A','B',10),edge(1,'A','B',3),edge(2,'A','B',3)]
    r=solve_graph(['A','B'],es,'A');check(['A','B'],es,'A',r)
    assert r['solution']['ranges'][1]['upper']['value_ns']=='3'

def test_seeded_floyd_warshall_agreement():
    rng=random.Random(91732)
    for case in range(100):
        n=rng.randrange(1,9);vs=[str(x) for x in range(n)];es=[edge(i,rng.choice(vs),rng.choice(vs),rng.randrange(-10,15)) for i in range(rng.randrange(0,n*n+1))]
        d=[[0 if i==j else None for j in range(n)] for i in range(n)]
        for e in es:
            u,v=int(e.from_id),int(e.to_id);d[u][v]=min(d[u][v],e.weight_ns) if d[u][v] is not None else e.weight_ns
        for k in range(n):
            for i in range(n):
                for j in range(n):
                    if d[i][k] is not None and d[k][j] is not None:
                        candidate=d[i][k]+d[k][j]
                        if d[i][j] is None or candidate<d[i][j]:d[i][j]=candidate
        anchor=rng.choice(vs);a=int(anchor);r=solve_graph(vs,es,anchor);check(vs,es,anchor,r)
        assert (r['contradiction'] is not None)==any(d[i][i]<0 for i in range(n))
        if r['solution']:
            for j,x in enumerate(r['solution']['ranges']):
                assert x['upper']['value_ns']==(None if d[a][j] is None else str(d[a][j]))
                assert x['lower']['value_ns']==(None if d[j][a] is None else str(-d[j][a]))
