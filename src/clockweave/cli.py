"""Local-only CLI with ordinary overwrite and alias protection.

Path checks protect ordinary use; they are not hostile concurrent-race defenses.
"""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
import tempfile
from . import __version__
from .model import ClockWeaveError,InputSource


def parser():
    p=argparse.ArgumentParser(prog='clockweave',description='Exact trace-clock consistency under explicit assumptions; no timestamp rewriting.')
    p.add_argument('--version',action='version',version=__version__);commands=p.add_subparsers(dest='command',required=True)
    for name in ('inspect','analyze','verify','render'):
        s=commands.add_parser(name);s.add_argument('--force',action='store_true',help='replace existing outputs; never overwrite an input alias')
        if name in ('verify','render'):s.add_argument('report',type=Path)
        if name!='render':
            s.add_argument('inputs',nargs='+',type=Path);s.add_argument('--format',choices=['auto','otlp-json','otlp-jsonl','jaeger-json'],default='auto')
            s.add_argument('--contract',type=Path,required=name in ('analyze','verify'))
            s.add_argument('--json',required=name=='analyze',default='-' if name in ('inspect','verify') else None)
        if name in ('analyze','render'):s.add_argument('--html',required=name=='render')
    return p


def protect_paths(inputs,outputs,force):
    paths=[Path(p) for p in inputs];destinations=[Path(p) for p in outputs if p is not None and p!='-']
    def aliases(a,b):
        if a.resolve()==b.resolve():return True
        return a.exists() and b.exists() and a.samefile(b)
    for i,out in enumerate(destinations):
        if any(aliases(out,source) for source in paths) or any(aliases(out,other) for other in destinations[:i]):
            raise ClockWeaveError('invalid_input','output_alias','An output aliases an input, contract, report, or another output; refused even with --force.')
        if out.exists() and not force:raise ClockWeaveError('io_error','output_exists',f'Output {out.name} already exists; use --force to replace an ordinary output.')
        if not out.parent.is_dir():raise ClockWeaveError('io_error','output_directory',f'Output parent directory does not exist: {out.parent}')


def write_output(destination,text):
    if destination=='-':sys.stdout.write(text);return
    path=Path(destination);fd,name=tempfile.mkstemp(prefix='.'+path.name+'.',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as file:file.write(text)
        os.replace(name,path)
    finally:
        try:os.unlink(name)
        except FileNotFoundError:pass


def main(argv=None):
    args=parser().parse_args(argv)
    try:
        from .ingest import load_capture,decode_json
        from .contract import load_contract
        from .extract import inspect_capture
        from .analysis import analyze
        from .replay import verify_report
        from .report import render_html
        source_paths=list(getattr(args,'inputs',[]))
        if getattr(args,'contract',None):source_paths.append(args.contract)
        if getattr(args,'report',None):source_paths.append(args.report)
        if getattr(args,'html',None)=='-':raise ClockWeaveError('invalid_input','html_stdout','Only --json supports output "-".')
        outputs=[getattr(args,'json',None),getattr(args,'html',None)]
        protect_paths(source_paths,outputs,args.force)
        if args.command=='render':
            report=decode_json(args.report.read_bytes());write_output(args.html,render_html(report));print('Rendered a structurally validated report; raw evidence was not replayed.',file=sys.stderr);return 0
        inputs=[InputSource(p,args.format) for p in args.inputs]
        if args.command=='verify':
            result=verify_report(decode_json(args.report.read_bytes()),inputs,args.contract)
            code=0 if result['valid'] else 4 if result['status']=='unsupported' else 5
            summary='Independent replay verified.' if result['valid'] else 'Independent replay did not verify this report.'
        else:
            capture=load_capture(inputs);contract=load_contract(args.contract) if args.contract else None
            if args.command=='inspect':result=inspect_capture(capture,contract);code=0;summary=f'Inspected {len(capture.spans)} spans; no clock facts inferred.'
            else:
                result=analyze(capture,contract);code={'compatible':0,'incompatible':1,'insufficient_evidence':3}[result['status']]
                summary=result['status'].replace('_',' ')+'; '+str(result['coverage']['selected_pairs'])+' qualified pairs; '+str(result['coverage']['unresolved_pairs'])+' unresolved pairs.'
        # Render everything before writing either artifact so structural failure cannot leave a misleading partial output.
        rendered=render_html(result) if getattr(args,'html',None) else None
        serialized=json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+'\n'
        if args.json is not None:write_output(args.json,serialized)
        if rendered is not None:write_output(args.html,rendered)
        print(summary,file=sys.stderr);return code
    except ClockWeaveError as e:
        error={'schema':'clockweave.error.v1','kind':e.kind,'code':e.code,'message':e.message,'source':asdict(e.source) if e.source else None}
        print(json.dumps(error,ensure_ascii=False),file=sys.stderr);return 4 if e.kind in ('unsupported','limit_exceeded') else 2
    except BrokenPipeError:return 2
    except OSError as e:
        print(json.dumps({'schema':'clockweave.error.v1','kind':'io_error','code':'io_error','message':str(e),'source':None}),file=sys.stderr);return 2
