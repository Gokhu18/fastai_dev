#AUTOGENERATED! DO NOT EDIT! File to edit: dev/05_data_source.ipynb (unless otherwise specified).

__all__ = ['coll_repr', 'DataSource']

from ..imports import *
from ..test import *
from ..core import *
from .core import *
from .pipeline import *

def coll_repr(c, max=1000):
    "String repr of up to `max` items of (possibly lazy) collection `c`"
    return f'({len(c)} items) [' + ','.join(itertools.islice(map(str,c), 10)) + ('...'
            if len(c)>10 else '') + ']'

class DataSource(Pipeline):
    "Applies a `Pipeline` of `tfms` to filtered subsets of `items`"
    def __init__(self, items, tfms=None, filts=None):
        if filts is None: filts = [range_of(items)]
        self.filts = listify(mask2idxs(filt) for filt in filts)
        self.items = ListContainer(items)
        super().__init__(tfms)

    def __len__(self): return len(self.filts)
    def len(self, filt=0): return len(self.filts[filt])
    def __getitem__(self, i): return _DsrcSubset(self, i)
    def __iter__(self): return (self[i] for i in range_of(self))

    def get(self, idx, filt=0):
        "Value(s) at `idx` from filtered subset `filt`"
        its = self.items[self.filts[filt][idx]]
        return (ListContainer(self(o,filt=filt) for o in its)
                if isinstance(its,ListContainer) else self(its,filt=filt))

    def decode_at(self, idx, filt=0): return self.decode(self.get(idx,filt), filt=filt)
    def show_at(self, idx, filt=0): return self.show(self.decode_at(idx,filt))
    def __eq__(self,b): return all_equal(b if isinstance(b,DataSource) else DataSource(b),self)

    def __repr__(self):
        res = f'{self.__class__.__name__}\n'
        return res + '\n'.join(f'{i}: {coll_repr(o)}' for i,o in enumerate(self))

    def decode_batch(self, b):
        "Decode a batch of `x,y` (i.e. from a `DataLoader`)"
        d = map(self.decode, zip(*b))
        return list(zip(*d))

DataSource.train,DataSource.valid = property(lambda x: x[0]),property(lambda x: x[1])

add_docs(
    DataSource,
    __len__="Number of filtered subsets",
    len="`len` of subset `filt`",
    __getitem__="Filtered subset `i`",
    decode_at="Decoded version of `get`",
    show_at="Call `tfm.show` for item `idx`/`filt`"
)

class _DsrcSubset:
    def __init__(self, dsrc, filt): self.dsrc,self.filt = dsrc,filt
    def __getitem__(self,i): return self.dsrc.get(i,self.filt)
    def decode(self, o): return self.dsrc.decode(o, self.filt)
    def __len__(self): return self.dsrc.len(self.filt)
    def __eq__(self,b): return all_equal(b,self)
    def __iter__(self): return (self[i] for i in range_of(self))
    def __repr__(self): return coll_repr(self)
    def show_at(self, i, **kwargs): return self.dsrc.show_at(i, self.filt, **kwargs)