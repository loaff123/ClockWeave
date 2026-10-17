"""Exact difference constraints with independently checkable witnesses.

An edge (u,v,w) means x[v]-x[u] <= w. This is ordinary Bellman-Ford,
not a measurement or a new synchronization algorithm.
"""
from __future__ import annotations
from collections import deque
from typing import Sequence
from .model import Constraint
from .decimal import parse_decimal,decimal_text


def _bellman(variables,edges,source=None):
    d={v:(0 if source is None or v==source else None) for v in variables};pred={}
    for iteration in range(len(variables)):
        changed=None
        for u,v,w,eid in edges:
            if d[u] is not None and (d[v] is None or d[v]>d[u]+w):
                d[v]=d[u]+w;pred[v]=(u,v,w,eid);changed=v
        if changed is None:return d,None
    cursor=changed
    for _ in variables:cursor=pred[cursor][0]
    cycle=[];start=cursor
    while True:
        e=pred[cursor];cycle.append(e);cursor=e[0]
        if cursor==start:break
    cycle.reverse()
    assert sum(e[2] for e in cycle)<0
    return None,cycle


def _assignment(variables,edges,anchor):
    values,cycle=_bellman(variables,edges)
    if cycle is not None:return None,cycle
    zero=values[anchor]
    values={v:values[v]-zero for v in variables}
    assert all(values[v]-values[u]<=w for u,v,w,_ in edges)
    return {v:decimal_text(values[v]) for v in variables},None


def _reachable(start,edges):
    neighbors={}
    for u,v,_,_ in edges:neighbors.setdefault(u,[]).append(v)
    reached={start};queue=[start]
    for u in queue:
        for v in neighbors.get(u,[]):
            if v not in reached:reached.add(v);queue.append(v)
    return sorted(reached)


def _path(start,target,edges,predicate):
    if start==target:return []
    neighbors={}
    for edge in edges:
        if predicate(edge):neighbors.setdefault(edge[0],[]).append(edge)
    pred={start:None};queue=deque([start])
    while queue:
        u=queue.popleft()
        for edge in neighbors.get(u,[]):
            v=edge[1]
            if v in pred:continue
            pred[v]=edge
            if v==target:
                path=[];cursor=v
                while cursor!=start:
                    e=pred[cursor];path.append(e[3]);cursor=e[0]
                return path[::-1]
            queue.append(v)
    raise AssertionError('Finite shortest bound lacks a tight-edge witness path')


def _components(variables,edges,anchor):
    neighbors={v:set() for v in variables}
    for u,v,_,_ in edges:neighbors[u].add(v);neighbors[v].add(u)
    seen=set();result=[]
    for start in variables:
        if start in seen:continue
        component={start};todo=[start];seen.add(start)
        for u in todo:
            for v in sorted(neighbors[u]):
                if v not in seen:seen.add(v);component.add(v);todo.append(v)
        result.append({'variables':sorted(component),'contains_anchor':anchor in component})
    return result


def solve_graph(variables: Sequence[str],constraints: Sequence[Constraint],anchor: str) -> dict:
    variables=list(variables)
    if anchor not in variables or len(set(variables))!=len(variables):raise ValueError('Graph requires a present anchor and unique variables')
    tight={}
    for c in constraints:
        if c.from_id not in variables or c.to_id not in variables:raise ValueError('Constraint references an unknown variable')
        key=(c.from_id,c.to_id);edge=(c.from_id,c.to_id,c.weight_ns,c.id)
        if key not in tight or (c.weight_ns,c.id)<(tight[key][2],tight[key][3]):tight[key]=edge
    edges=[tight[key] for key in sorted(tight)]
    example,cycle=_assignment(variables,edges,anchor)
    result={'solution':None,'contradiction':None,'components':_components(variables,edges,anchor)}
    if cycle is not None:
        result['contradiction']={'constraint_ids':[e[3] for e in cycle],'sum_ns':decimal_text(sum(e[2] for e in cycle))}
        return result
    forward,_=_bellman(variables,edges,anchor)
    reverse,_=_bellman(variables,[(v,u,w,eid) for u,v,w,eid in edges],anchor)
    ranges=[]
    for v in variables:
        row={'variable':v}
        for side in ('lower','upper'):
            distance=reverse[v] if side=='lower' else forward[v]
            if distance is None:
                row[side]={'value_ns':None,'reachable':_reachable(v if side=='lower' else anchor,edges)}
                continue
            value=-distance if side=='lower' else distance
            fixed=[*edges,(anchor,v,value,'__attain_upper'),(v,anchor,-value,'__attain_lower')]
            attaining,bad=_assignment(variables,fixed,anchor)
            assert bad is None and parse_decimal(attaining[v])==value
            assert all(parse_decimal(attaining[c.to_id])-parse_decimal(attaining[c.from_id])<=c.weight_ns for c in constraints)
            if side=='upper':
                path=_path(anchor,v,edges,lambda e:forward[e[0]] is not None and forward[e[1]]==forward[e[0]]+e[2])
            else:
                path=_path(v,anchor,edges,lambda e:reverse[e[1]] is not None and reverse[e[0]]==e[2]+reverse[e[1]])
            row[side]={'value_ns':decimal_text(value),'path':path,'attaining_ns':attaining}
        ranges.append(row)
    assert all(parse_decimal(example[c.to_id])-parse_decimal(example[c.from_id])<=c.weight_ns for c in constraints)
    result['solution']={'example_ns':example,'ranges':ranges}
    return result
