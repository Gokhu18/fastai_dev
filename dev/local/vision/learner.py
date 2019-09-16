#AUTOGENERATED! DO NOT EDIT! File to edit: dev/22_vision_learner.ipynb (unless otherwise specified).

__all__ = ['has_pool_type', 'create_body', 'in_channels', 'num_features_model', 'create_head', 'create_cnn_model',
           'model_meta', 'cnn_learner']

#Cell
from ..torch_basics import *
from ..test import *
from ..core import *
from ..layers import *
from ..data.all import *
from ..optimizer import *
from ..learner import *
from ..metrics import *
from ..callback.all import *
from .core import *
from .augment import *
from . import models

#Cell
def _is_pool_type(l): return re.search(r'Pool[123]d$', l.__class__.__name__)

#Cell
def has_pool_type(m):
    "Return `True` if `m` is a pooling layer or has one in its children"
    if _is_pool_type(m): return True
    for l in m.children():
        if has_pool_type(l): return True
    return False

#Cell
def create_body(arch, pretrained=True, cut=None):
    "Cut off the body of a typically pretrained `arch` as determined by `cut`"
    model = arch(pretrained)
    #cut = ifnone(cut, cnn_config(arch)['cut'])
    if cut is None:
        ll = list(enumerate(model.children()))
        cut = next(i for i,o in reversed(ll) if has_pool_type(o))
    if   isinstance(cut, int):      return nn.Sequential(*list(model.children())[:cut])
    elif isinstance(cut, Callable): return cut(model)
    else:                           raise NamedError("cut must be either integer or a function")

#Cell
def in_channels(m):
    "Return the shape of the first weight layer in `m`."
    for l in flatten_model(m):
        if hasattr(l, 'weight'): return l.weight.shape[1]
    raise Exception('No weight layer')

#Cell
def num_features_model(m):
    "Return the number of output features for `m`."
    sz = 32
    ch_in = in_channels(m)
    while True:
        #Trying for a few sizes in case the model requires a big input size.
        try:
            with hook_output(m) as hook:
                _ = m.eval()(one_param(m).new(1, ch_in, sz, sz).requires_grad_(False).uniform_(-1.,1.))
                return hook.stored.shape[1]
        except Exception as e:
            sz *= 2
            if sz > 2048: raise

#Cell
def create_head(nf, nc, lin_ftrs=None, ps=0.5, concat_pool=True, bn_final=False):
    "Model head that takes `nf` features, runs through `lin_ftrs`, and out `nc` classes."
    lin_ftrs = [nf, 512, nc] if lin_ftrs is None else [nf] + lin_ftrs + [nc]
    ps = L(ps)
    if len(ps) == 1: ps = [ps[0]/2] * (len(lin_ftrs)-2) + ps
    actns = [nn.ReLU(inplace=True)] * (len(lin_ftrs)-2) + [None]
    pool = AdaptiveConcatPool2d() if concat_pool else nn.AdaptiveAvgPool2d(1)
    layers = [pool, Flatten()]
    for ni,no,p,actn in zip(lin_ftrs[:-1], lin_ftrs[1:], ps, actns):
        layers += BnDropLin(ni, no, True, p, actn)
    if bn_final: layers.append(nn.BatchNorm1d(lin_ftrs[-1], momentum=0.01))
    return nn.Sequential(*layers)

#Cell
def create_cnn_model(arch, nc, cut, pretrained=True, lin_ftrs=None, ps=0.5, custom_head=None,
                     bn_final=False, concat_pool=True):
    "Create custom convnet architecture using `base_arch`"
    body = create_body(arch, pretrained, cut)
    if custom_head is None:
        nf = num_features_model(nn.Sequential(*body.children())) * (2 if concat_pool else 1)
        head = create_head(nf, nc, lin_ftrs, ps=ps, concat_pool=concat_pool, bn_final=bn_final)
    else: head = custom_head
    return nn.Sequential(body, head)

#Cell
def _get_c(dbunch):
    for t in dbunch.train_ds.tls[1].tfms.fs:
        if hasattr(t, 'vocab'): return len(t.vocab)

#Cell
def _default_split(m:nn.Module): return L(m[0], m[1]).mapped(trainable_params)
def _resnet_split(m): return L(m[0][:6], m[0][6:], m[1]).mapped(trainable_params)
def _squeezenet_split(m:nn.Module): return L(m[0][0][:5], m[0][0][5:], m[1]).mapped(trainable_params)
def _densenet_split(m:nn.Module): return L(m[0][0][:7],m[0][0][7:], m[1]).mapped(trainable_params)
def _vgg_split(m:nn.Module): return L(m[0][0][:22], m[0][0][22:], m[1]).mapped(trainable_params)
def _alexnet_split(m:nn.Module): return L(m[0][0][:6], m[0][0][6:], m[1]).mapped(trainable_params)

_default_meta    = {'cut':None, 'split':_default_split}
_resnet_meta     = {'cut':-2, 'split':_resnet_split }
_squeezenet_meta = {'cut':-1, 'split': _squeezenet_split}
_densenet_meta   = {'cut':-1, 'split':_densenet_split}
_vgg_meta        = {'cut':-2, 'split':_vgg_split}
_alexnet_meta    = {'cut':-2, 'split':_alexnet_split}

#Cell
model_meta = {
    models.resnet18 :{**_resnet_meta}, models.resnet34: {**_resnet_meta},
    models.resnet50 :{**_resnet_meta}, models.resnet101:{**_resnet_meta},
    models.resnet152:{**_resnet_meta},

    models.squeezenet1_0:{**_squeezenet_meta},
    models.squeezenet1_1:{**_squeezenet_meta},

    models.densenet121:{**_densenet_meta}, models.densenet169:{**_densenet_meta},
    models.densenet201:{**_densenet_meta}, models.densenet161:{**_densenet_meta},
    models.vgg11_bn:{**_vgg_meta}, models.vgg13_bn:{**_vgg_meta}, models.vgg16_bn:{**_vgg_meta}, models.vgg19_bn:{**_vgg_meta},
    models.alexnet:{**_alexnet_meta}}

#Cell
@delegates(Learner.__init__)
def cnn_learner(dbunch, arch, cut=None, pretrained=True, lin_ftrs=None, ps=0.5, custom_head=None, splitter=trainable_params, bn_final=False,
                init=nn.init.kaiming_normal_, concat_pool=True, **kwargs):
    "Build convnet style learner."
    meta = model_meta.get(arch)
    model = create_cnn_model(arch, _get_c(dbunch), ifnone(cut, meta['cut']), pretrained, lin_ftrs, ps=ps, custom_head=custom_head,
        bn_final=bn_final, concat_pool=concat_pool)
    learn = Learner(model, dbunch, splitter=ifnone(splitter, meta['split']), **kwargs)
    if pretrained: learn.freeze()
    if init: apply_init(model[1], init)
    return learn