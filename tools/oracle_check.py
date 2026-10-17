"""Development-only differential checks; SciPy is never a runtime dependency."""
import argparse
import itertools
import json
import random
from pathlib import Path
from clockweave.graph import solve_graph
from clockweave.model import Constraint


def constraint(i,u,v,w):return Constraint(str(i),str(u),str(v),w,'start_order','oracle',('t','c'),('t','s'),(0,w),0,())

def floyd(n,edges):
    d=[[0 if i==j else None for j in range(n)] for i in range(n)]
    for u,v,w in edges:d[u][v]=w if d[u][v] is None else min(d[u][v],w)
    for k in range(n):
        for i in range(n):
            for j in range(n):
                if d[i][k] is not None and d[k][j] is not None:
                    value=d[i][k]+d[k][j]
                    if d[i][j] is None or d[i][j]>value:d[i][j]=value
    return d


def check_proofs(n,edges,anchor,result):
    def check_assignment(a):
        assert set(a)=={str(i) for i in range(n)} and int(a[str(anchor)])==0
        assert all(int(a[str(v)])-int(a[str(u)])<=w for u,v,w in edges)
    if result['contradiction']:
        cycle=[edges[int(k)] for k in result['contradiction']['constraint_ids']]
        assert cycle and all(e[1]==cycle[(i+1)%len(cycle)][0] for i,e in enumerate(cycle))
        assert sum(e[2] for e in cycle)==int(result['contradiction']['sum_ns'])<0
        return
    check_assignment(result['solution']['example_ns'])
    for row in result['solution']['ranges']:
        v=int(row['variable'])
        for side in ('lower','upper'):
            b=row[side];start,end=(v,anchor) if side=='lower' else (anchor,v)
            if b['value_ns'] is None:
                seen={int(x) for x in b['reachable']};assert start in seen and end not in seen
                assert all(u not in seen or v in seen for u,v,_ in edges)
            else:
                check_assignment(b['attaining_ns']);assert b['attaining_ns'][str(v)]==b['value_ns']
                current=start;weight=0
                for k in b['path']:
                    u,vv,w=edges[int(k)];assert u==current;current=vv;weight+=w
                assert current==end and weight==int(b['value_ns'])*(1 if side=='upper' else -1)


def run(cases,seed):
    import numpy as np
    from scipy.optimize import linprog
    rng=random.Random(seed);counts={'cases':cases,'feasible':0,'infeasible':0,'floyd_endpoints':0,'lp_endpoints':0,'exhaustive_cases':0}
    for case in range(cases):
        n=rng.randrange(1,9);anchor=rng.randrange(n);truth=[rng.randrange(-30,31) for _ in range(n)];edges=[]
        for _ in range(rng.randrange(0,n*n+1)):
            u,v=rng.randrange(n),rng.randrange(n)
            w=truth[v]-truth[u]+rng.randrange(0,15) if case%2==0 else rng.randrange(-20,21)
            edges.append((u,v,w))
        d=floyd(n,edges);bad=any(d[i][i]<0 for i in range(n));r=solve_graph([str(i) for i in range(n)],[constraint(i,*e) for i,e in enumerate(edges)],str(anchor))
        check_proofs(n,edges,anchor,r);assert (r['contradiction'] is not None)==bad
        a=np.zeros((len(edges),n));b=np.zeros(len(edges))
        for i,(u,v,w) in enumerate(edges):a[i,v]+=1;a[i,u]-=1;b[i]=w
        bounds=[(0,0) if i==anchor else (None,None) for i in range(n)]
        def lp(c):return linprog(c,A_ub=a if edges else None,b_ub=b if edges else None,bounds=bounds,method='highs')
        baseline=lp(np.zeros(n));assert baseline.status==(2 if bad else 0)
        counts['infeasible' if bad else 'feasible']+=1
        if bad:continue
        for j,row in enumerate(r['solution']['ranges']):
            for side in ('lower','upper'):
                expected=d[j][anchor] if side=='lower' else d[anchor][j]
                expected=None if expected is None else (-expected if side=='lower' else expected)
                assert row[side]['value_ns']==(None if expected is None else str(expected));counts['floyd_endpoints']+=1
                objective=np.zeros(n);objective[j]=1 if side=='lower' else -1;optimum=lp(objective)
                if expected is None:assert optimum.status==3
                else:assert optimum.status==0 and abs(optimum.fun-objective[j]*expected)<1e-7;counts['lp_endpoints']+=1
    for case in range(20):
        edges=[(0,j,5) for j in (1,2)]+[(j,0,5) for j in (1,2)]
        edges += [(u,v,rng.randrange(-4,6)) for u,v in (rng.sample(range(3),2) for _ in range(6))]
        valid=[(0,*p) for p in itertools.product(range(-5,6),repeat=2) if all((0,*p)[v]-(0,*p)[u]<=w for u,v,w in edges)]
        r=solve_graph(['0','1','2'],[constraint(i,*e) for i,e in enumerate(edges)],'0');check_proofs(3,edges,0,r)
        assert bool(valid)==(r['solution'] is not None)
        if valid:
            for j,row in enumerate(r['solution']['ranges']):assert (int(row['lower']['value_ns']),int(row['upper']['value_ns']))==(min(p[j] for p in valid),max(p[j] for p in valid))
        counts['exhaustive_cases']+=1
    return {**counts,'seed':seed,'all_assertions_passed':True,'oracle':'independent integer Floyd-Warshall; SciPy/HiGHS feasibility and optimization; bounded exhaustive enumeration'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--cases',type=int,default=1000);p.add_argument('--seed',type=int,default=20261008);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=run(a.cases,a.seed);a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
