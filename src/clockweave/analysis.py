"""Compose complete evidence and exact declared-model results."""
from dataclasses import asdict
from . import __version__
from .extract import extract,observation
from .graph import solve_graph,_components
from .model import Capture,Contract
from .decimal import decimal_text

INTERPRETATION=(
    'This result concerns only the qualified observations under the displayed domain, epoch and endpoint assumptions. '
    'Compatible ranges are coupled projections, not independently selectable offsets or physical clock measurements. '
    'An incompatible result rejects the joint declared model and evidence; it does not identify causal blame. '
    'Disconnected example offsets choose arbitrary relative translations. Original timestamps are unchanged.'
)


def constraint_record(c):
    return {'id':c.id,'from':c.from_id,'to':c.to_id,'weight_ns':decimal_text(c.weight_ns),'relation':c.relation,
            'boundary_id':c.boundary_id,'client':list(c.client),'server':list(c.server),
            'endpoint_values_ns':[decimal_text(x) for x in c.endpoint_values_ns],'slack_ns':decimal_text(c.slack_ns),
            'sources':[asdict(s) for s in c.sources]}


def analyze(capture: Capture,contract: Contract) -> dict:
    e=extract(capture,contract)
    result={'schema':'clockweave.report.v1','tool_version':__version__,'status':'insufficient_evidence','interpretation':INTERPRETATION,
            'inputs':sorted(capture.inputs,key=lambda i:(i['sha256'],i['file_name'],i['format'])),
            'contract':{'data':contract.data,'sha256':contract.sha256,'canonical_sha256':contract.canonical_sha256},
            'coverage':e.coverage,'observations':[observation(s) for s in capture.spans],
            'qualification':e.qualification,'variables':list(e.variables),'anchor':e.anchor,
            'components':_components([v['id'] for v in e.variables],[(c.from_id,c.to_id,c.weight_ns,c.id) for c in e.constraints],e.anchor),
            'constraints':[constraint_record(c) for c in e.constraints],
            'solution':None,'contradiction':None,'reasons':list(e.reasons)}
    if not e.reasons:
        solved=solve_graph([v['id'] for v in e.variables],e.constraints,e.anchor)
        result.update(solved);result['status']='compatible' if solved['solution'] is not None else 'incompatible'
    return result
