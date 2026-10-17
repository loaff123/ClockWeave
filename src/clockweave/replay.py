"""Independently reconstruct raw evidence and check arithmetic/traversal proofs."""
import json
from typing import Mapping,Sequence
from pathlib import Path
from .model import InputSource,ClockWeaveError
from .replay_input import read_capture,require,number
from .replay_contract import read_contract,reconstruct

FIELDS={'schema','tool_version','status','interpretation','inputs','contract','coverage','observations','qualification','variables','anchor','components','constraints','solution','contradiction','reasons'}
INTERPRETATION=('This result concerns only the qualified observations under the displayed domain, epoch and endpoint assumptions. '
               'Compatible ranges are coupled projections, not independently selectable offsets or physical clock measurements. '
               'An incompatible result rejects the joint declared model and evidence; it does not identify causal blame. '
               'Disconnected example offsets choose arbitrary relative translations. Original timestamps are unchanged.')


def same(actual,expected,label):
    require(json.dumps(actual,sort_keys=True,ensure_ascii=False,allow_nan=False)==json.dumps(expected,sort_keys=True,ensure_ascii=False,allow_nan=False),'Reconstructed '+label+' differs from report')


def ns(value):
    require(type(value) is str,'Nanoseconds must be decimal strings');return number(value,signed=True)


def proof(report):
    variables=[v['id'] for v in report['variables']];anchor=report['anchor'];edges={e['id']:e for e in report['constraints']}
    def assignment(values):
        require(type(values) is dict and set(values)==set(variables),'Assignment variable set mismatch')
        parsed={v:ns(x) for v,x in values.items()};require(parsed[anchor]==0,'Assignment is not normalized to anchor')
        for e in edges.values():require(parsed[e['to']]-parsed[e['from']]<=ns(e['weight_ns']),'Assignment violates raw inequality '+e['id'])
        return parsed
    if report['status']=='insufficient_evidence':
        require(bool(report['reasons']),'No reconstructed insufficiency reason');require(report['solution'] is None and report['contradiction'] is None,'Insufficient report asserts a solve');return
    require(not report['reasons'],'Evidence blocker contradicts diagnosis')
    if report['status']=='incompatible':
        require(report['solution'] is None and type(report['contradiction']) is dict,'Invalid incompatible shape');cycle=report['contradiction']
        require(set(cycle)=={'constraint_ids','sum_ns'} and type(cycle['constraint_ids']) is list and bool(cycle['constraint_ids']),'Missing negative cycle')
        selected=[edges[eid] for eid in cycle['constraint_ids']]
        require(all(e['to']==selected[(i+1)%len(selected)]['from'] for i,e in enumerate(selected)),'Cycle is not contiguous and closed')
        summed=sum(ns(e['weight_ns']) for e in selected);require(summed==ns(cycle['sum_ns']) and summed<0,'Cycle sum is not the claimed strict negative value');return
    require(report['status']=='compatible','Unknown status');require(report['contradiction'] is None,'Compatible report contains a contradiction')
    solution=report['solution'];require(type(solution) is dict and set(solution)=={'example_ns','ranges'},'Invalid solution shape');assignment(solution['example_ns'])
    ranges=solution['ranges'];require(type(ranges) is list and len(ranges)==len(variables),'Missing or duplicate ranges')
    require([r['variable'] for r in ranges]==variables,'Range variable ordering/set mismatch')
    for row in ranges:
        require(set(row)=={'variable','lower','upper'},'Invalid range shape');v=row['variable']
        for side in ('lower','upper'):
            bound=row[side];require(type(bound) is dict,'Invalid bound');start,target=(v,anchor) if side=='lower' else (anchor,v)
            if bound.get('value_ns') is None:
                require(set(bound)=={'value_ns','reachable'} and type(bound['reachable']) is list,'Invalid unbounded witness')
                reached=set(bound['reachable']);require(len(reached)==len(bound['reachable']) and reached<=set(variables),'Invalid reachable set')
                require(start in reached and target not in reached,'Unbounded cut endpoints are invalid')
                require(all(e['from'] not in reached or e['to'] in reached for e in edges.values()),'Unbounded cut has an outgoing edge')
            else:
                require(set(bound)=={'value_ns','path','attaining_ns'} and type(bound['path']) is list,'Invalid finite witness')
                value=ns(bound['value_ns']);joint=assignment(bound['attaining_ns']);require(joint[v]==value,'Assignment does not attain bound')
                current=start;weight=0
                for eid in bound['path']:
                    e=edges[eid];require(e['from']==current,'Bound path is discontinuous');current=e['to'];weight+=ns(e['weight_ns'])
                require(current==target and weight==value*(-1 if side=='lower' else 1),'Bound path does not prove claimed endpoint')


def verify_report(report: Mapping,inputs: Sequence[InputSource],contract_path: Path) -> dict:
    result={'schema':'clockweave.verification.v1','valid':False,'status':'failed','checks':[],'errors':[]}
    if not isinstance(report,Mapping) or report.get('schema')!='clockweave.report.v1':
        result['status']='unsupported';result['errors']=[{'code':'unsupported_report_schema','message':'Unsupported report schema'}];return result
    try:
        require(set(report)==FIELDS,'Report fields do not match schema');require(type(report['tool_version']) is str,'Missing tool version')
        same(report['interpretation'],INTERPRETATION,'interpretation')
        observations,metadata,duplicates=read_capture(inputs);contract=read_contract(contract_path)
        same(report['inputs'],metadata,'input files');same(report['contract'],contract,'contract')
        result['checks'].append('original_input_and_contract_hashes')
        same(report['observations'],observations,'observations')
        expected=reconstruct(observations,contract,duplicates)
        for key,value in expected.items():same(report[key],value,key)
        result['checks'].append('independent_observations_qualification_and_constraints')
        proof(report);result['checks'].append('exact_assignment_path_attainment_cut_or_cycle')
        result['valid']=True;result['status']='verified'
    except ClockWeaveError as e:
        result['status']='unsupported' if e.kind in ('limit_exceeded','unsupported') else 'failed'
        result['errors'].append({'code':e.code,'message':e.message})
    except (ValueError,KeyError,TypeError,IndexError,OSError,OverflowError,RecursionError) as e:
        result['errors'].append({'code':'verification_failed','message':str(e) or type(e).__name__})
    return result
