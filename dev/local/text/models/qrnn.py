#AUTOGENERATED! DO NOT EDIT! File to edit: dev/36_text_models_qrnn.ipynb (unless otherwise specified).

__all__ = ['load_cpp', 'dispatch_cuda', 'forget_mult_CPU', 'ForgetMultGPU', 'QRNNLayer', 'QRNN']

#Cell
from ...torch_basics import *
from ...test import *
from ...core import *
from ...layers import *
from ...data.all import *
from ..core import *
from .awdlstm import dropout_mask

#Cell
from torch.utils import cpp_extension
from torch.autograd import Function

#Cell
import local

def load_cpp(name, files, path):
    return cpp_extension.load(name='forget_mult_cuda', sources=[fastai_path/f for f in files], build_directory=Config().model)

if torch.cuda.is_available():
    #fastai_path = Path(fastai.__path__[0])/'text'/'models'
    fastai_path = Path.cwd()/'local'/'text'/'models'
    files = ['forget_mult_cuda.cpp', 'forget_mult_cuda_kernel.cu']
    forget_mult_cuda = load_cpp(name='forget_mult_cuda', files=files, path=fastai_path)
    files = ['bwd_forget_mult_cuda.cpp', 'bwd_forget_mult_cuda_kernel.cu']
    bwd_forget_mult_cuda = load_cpp(name='bwd_forget_mult_cuda', files=files, path=fastai_path)

#Cell
def dispatch_cuda(cuda_class, cpu_func, x):
    "Depending on `x.device` uses `cpu_func` or `cuda_class.apply`"
    return cuda_class.apply if x.device.type == 'cuda' else cpu_func

#Cell
def forget_mult_CPU(x, f, first_h=None, batch_first=True, backward=False):
    "ForgetMult gate applied to `x` and `f` on the CPU."
    result = []
    dim = (1 if batch_first else 0)
    forgets = f.split(1, dim=dim)
    inputs =  x.split(1, dim=dim)
    prev_h = None if first_h is None else first_h.unsqueeze(1 if batch_first else 0)
    idx_range = range(len(inputs)-1,-1,-1) if backward else range(len(inputs))
    for i in idx_range:
        prev_h = inputs[i] * forgets[i] if prev_h is None else inputs[i] * forgets[i] + (1-forgets[i]) * prev_h
        if backward: result.insert(0, prev_h)
        else:        result.append(prev_h)
    return torch.cat(result, dim=dim)

#Cell
class ForgetMultGPU(Function):
    "Wraper around the CUDA kernels for the ForgetMult gate."
    @staticmethod
    def forward(ctx, x, f, first_h=None, batch_first=True, backward=False):
        ind = -1 if backward else 0
        (i,j) = (0,1) if batch_first else (1,0)
        output = x.new_zeros(x.shape[0]+i, x.shape[1]+j, x.shape[2])
        if first_h is not None:
            if batch_first: output[:, ind] = first_h
            else:           output[ind]    = first_h
        else: output.zero_()
        ctx.forget_mult = bwd_forget_mult_cuda if backward else forget_mult_cuda
        output = ctx.forget_mult.forward(x, f, output, batch_first)
        ctx.save_for_backward(x, f, first_h, output)
        ctx.batch_first = batch_first
        if backward: return output[:,:-1] if batch_first else output[:-1]
        else:        return output[:,1:]  if batch_first else output[1:]

    @staticmethod
    def backward(ctx, grad_output):
        x, f, first_h, output = ctx.saved_tensors
        grad_x, grad_f, grad_h = ctx.forget_mult.backward(x, f, output, grad_output, ctx.batch_first)
        return (grad_x, grad_f, (None if first_h is None else grad_h), None, None)

#Cell
class QRNNLayer(Module):
    "Apply a single layer Quasi-Recurrent Neural Network (QRNN) to an input sequence."
    def __init__(self, input_size, hidden_size=None, save_prev_x=False, zoneout=0, window=1,
                 output_gate=True, batch_first=True, backward=False):
        assert window in [1, 2], "This QRNN implementation currently only handles convolutional window of size 1 or size 2"
        self.save_prev_x,self.zoneout,self.window = save_prev_x,zoneout,window
        self.output_gate,self.batch_first,self.backward = output_gate,batch_first,backward
        hidden_size = ifnone(hidden_size, input_size)
        #One large matmul with concat is faster than N small matmuls and no concat
        mult = (3 if output_gate else 2)
        self.linear = nn.Linear(window * input_size, mult * hidden_size)
        self.prevX = None

    def reset(self): self.prevX = None

    def forward(self, inp, hid=None):
        y = self.linear(self._get_source(inp))
        if self.output_gate: z_gate,f_gate,o_gate = y.chunk(3, dim=2)
        else:                z_gate,f_gate        = y.chunk(2, dim=2)
        z_gate.tanh_()
        f_gate.sigmoid_()
        if self.zoneout and self.training:
            f_gate = f_gate * dropout_mask(f_gate, f_gate.size(), self.zoneout).requires_grad_(False)
        z_gate,f_gate = z_gate.contiguous(),f_gate.contiguous()
        forget_mult = dispatch_cuda(ForgetMultGPU, partial(forget_mult_CPU), inp)
        c_gate = forget_mult(z_gate, f_gate, hid, self.batch_first, self.backward)
        output = torch.sigmoid(o_gate) * c_gate if self.output_gate else c_gate
        if self.window > 1 and self.save_prev_x:
            if self.backward: self.prevX = (inp[:, :1]  if self.batch_first else inp[:1]) .detach()
            else:             self.prevX = (inp[:, -1:] if self.batch_first else inp[-1:]).detach()
        idx = 0 if self.backward else -1
        return output, (c_gate[:, idx] if self.batch_first else c_gate[idx])

    def _get_source(self, inp):
        if self.window == 1: return inp
        dim = (1 if self.batch_first else 0)
        inp_shift = [torch.zeros_like(inp[:,:1] if self.batch_first else inp[:1]) if self.prevX is None else self.prevX]
        if self.backward: inp_shift.insert(0,inp[:,1:] if self.batch_first else inp[1:])
        else:             inp_shift.append(inp[:,:-1] if self.batch_first else inp[:-1])
        inp_shift = torch.cat(inp_shift, dim)
        return torch.cat([inp, inp_shift], 2)

#Cell
class QRNN(Module):
    "Apply a multiple layer Quasi-Recurrent Neural Network (QRNN) to an input sequence."
    def __init__(self, input_size, hidden_size, n_layers=1, batch_first=True, dropout=0,
                 bidirectional=False, save_prev_x=False, zoneout=0, window=None, output_gate=True):
        assert not (save_prev_x and bidirectional), "Can't save the previous X with bidirectional."
        kwargs = dict(batch_first=batch_first, zoneout=zoneout, output_gate=output_gate)
        self.layers = nn.ModuleList([QRNNLayer(input_size if l == 0 else hidden_size, hidden_size, save_prev_x=save_prev_x,
                                               window=((2 if l ==0 else 1) if window is None else window), **kwargs)
                                     for l in range(n_layers)])
        if bidirectional:
            self.layers_bwd = nn.ModuleList([QRNNLayer(input_size if l == 0 else hidden_size, hidden_size,
                                                       backward=True, window=((2 if l ==0 else 1) if window is None else window),
                                                       **kwargs) for l in range(n_layers)])
        self.n_layers,self.batch_first,self.dropout,self.bidirectional = n_layers,batch_first,dropout,bidirectional

    def reset(self):
        "Reset the hidden state."
        for layer in self.layers: layer.reset()
        if self.bidirectional:
            for layer in self.layers_bwd: layer.reset()

    def forward(self, inp, hid=None):
        new_hid = []
        if self.bidirectional: inp_bwd = inp.clone()
        for i, layer in enumerate(self.layers):
            inp, h = layer(inp, None if hid is None else hid[2*i if self.bidirectional else i])
            new_hid.append(h)
            if self.bidirectional:
                inp_bwd, h_bwd = self.layers_bwd[i](inp_bwd, None if hid is None else hid[2*i+1])
                new_hid.append(h_bwd)
            if self.dropout != 0 and i < len(self.layers) - 1:
                for o in ([inp, inp_bwd] if self.bidirectional else [inp]):
                    o = F.dropout(o, p=self.dropout, training=self.training, inplace=False)
        if self.bidirectional: inp = torch.cat([inp, inp_bwd], dim=2)
        return inp, torch.stack(new_hid, 0)