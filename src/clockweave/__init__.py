"""Declared-model trace-clock consistency; no timestamp rewriting."""
__version__ = '0.1.0a1'

from .model import InputSource, ClockWeaveError

_EXPORTS = {'load_capture':'ingest','load_contract':'contract','inspect_capture':'extract',
            'analyze':'analysis','verify_report':'replay','render_html':'report'}
__all__ = ['InputSource','ClockWeaveError',*_EXPORTS]

def __getattr__(name):
    if name not in _EXPORTS:raise AttributeError(name)
    from importlib import import_module
    value=getattr(import_module('.'+_EXPORTS[name],__name__),name)
    globals()[name]=value
    return value
