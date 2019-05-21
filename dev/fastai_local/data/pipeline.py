#AUTOGENERATED! DO NOT EDIT! File to edit: dev/02_data_pipeline.ipynb (unless otherwise specified).

__all__ = ['Transform', 'add_docs', 'docs']

from ..imports import *
from ..test import *
from ..core import *


class Transform():
    "A function that `encodes` if `filt` matches, and optionally `decodes`, with an optional `setup`"
    order,filt = 0,None

    def __init__(self, encodes=None, **kwargs):
        if encodes is not None: self.encodes=encodes
        for k,v in kwargs.items(): setattr(self, k, v)

    @classmethod
    def create(cls, f, filt=None):
        "classmethod: Turn `f` into a `Transform` unless it already is one"
        return f if hasattr(f,'decode') or isinstance(f,Transform) else cls(f)

    def __call__(self, o, filt=None, **kwargs):
        "Call `self.encodes` unless `filt` is passed and it doesn't match `self.filt`"
        if self.filt is not None and self.filt!=filt: return o
        return self.encodes(o, **kwargs)

    def decode(self, o, filt=None, **kwargs):
        "Call `self.decodes` unless `filt` is passed and it doesn't match `self.filt`"
        if self.filt is not None and self.filt!=filt: return o
        return self.decodes(o, **kwargs)

    def __repr__(self): return str(self.encodes) if self.__class__==Transform else str(self.__class__)
    def decodes(self, o, *args, **kwargs): return o

def add_docs(cls, **docs):
    "Copy values from `docs` to `cls` docstrings, and confirm all public methods are documented"
    for k,v in docs.items(): getattr(cls,k).__doc__ = v
    # List of public callables without docstring
    nodoc = [c for n,c in cls.__dict__.items() if isinstance(c,Callable)
             and not n.startswith('_') and c.__doc__ is None]
    assert not nodoc, f"Missing docs: {nodoc}"
    assert cls.__doc__ is not None, f"Missing class docs: {cls}"

def docs(cls):
    "Decorator version of `add_docs"
    add_docs(cls, **cls._doc)
    return cls