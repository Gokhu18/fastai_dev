#AUTOGENERATED! DO NOT EDIT! File to edit: dev/12_learner.ipynb (unless otherwise specified).

__all__ = ['Callback', 'TrainEvalCallback', 'CancelFitException', 'CancelEpochException', 'CancelTrainException',
           'CancelValidException', 'CancelBatchException', 'event', 'Learner', 'VerboseCallback', 'Metric', 'AvgMetric',
           'AvgLoss', 'AvgSmoothLoss', 'Recorder']

from .imports import *
from .test import *
from .core import *
from .layers import *
from .data.pipeline import *
from .data.source import *
from .data.core import *
from .data.external import *
from .notebook.showdoc import show_doc
from .optimizer import *

@docs
class Callback():
    "Basic class handling tweaks of the training loop by changing a `Learner` in various events"
    order=0
    def __getattr__(self, k): return getattr(self.learn, k)

    @property
    def name(self):
        "Name of the `Callback`, camel-cased and with Callback removed"
        name = re.sub(r'Callback$', '', self.__class__.__name__)
        return camel2snake(name or 'callback')

    def __call__(self, event_name): getattr(self, event_name, noop)()

    _docs=dict(__call__="Call `self.{event_name}` if it's defined",
              __getattr__="Passthrough to get the attributes of `self.learn`",
              )

class TrainEvalCallback(Callback):
    "`Callback` that tracks the number of iterations done and properly sets training/eval mode"
    def begin_fit(self):
        "Set the iter and epoch counters to 0"
        self.learn.train_iter,self.learn.pct_train = 0,0.

    def begin_batch(self):
        "On the first batch, put the model on the right device"
        if self.learn.train_iter == 0: self.model.to(find_device(self.xb))

    def after_batch(self):
        "Update the iter counter (in training mode)"
        if not self.training: return
        self.learn.pct_train += 1./(self.n_iter*self.n_epoch)
        self.learn.train_iter   += 1

    def begin_train(self):
        "Set the model in training mode"
        self.learn.pct_train=self.epoch/self.n_epoch
        self.model.train()
        self.learn.training=True

    def begin_validate(self):
        "Set the model in validation mode"
        self.model.eval()
        self.learn.training=False

class CancelFitException  (Exception): pass
class CancelEpochException(Exception): pass
class CancelTrainException(Exception): pass
class CancelValidException(Exception): pass
class CancelBatchException(Exception): pass

CancelBatchException.__doc__ = "Skip the rest of this batch and go to `after_batch`"
CancelTrainException.__doc__ = "Skip the rest of the training part of the epoch and go to `after_train`"
CancelValidException.__doc__ = "Skip the rest of the validation part of the epoch and go to `after_validate`"
CancelEpochException.__doc__ = "Skip the rest of this epoch and go to `after_epoch`"
CancelFitException  .__doc__ = "Interrupts training and go to `after_fit`"

event = SimpleNamespace(**{o:o for o in {
    'begin_fit', 'begin_epoch', 'begin_train', 'begin_batch', 'after_pred', 'after_loss', 'after_backward',
    'after_step', 'after_cancel_batch', 'after_batch', 'after_cancel_train', 'after_train', 'begin_validate',
    'after_cancel_validate', 'after_validate', 'after_cancel_epoch', 'after_epoch', 'after_cancel_fit',
    'after_fit'
}})

event.__doc__ = "Object containing all possible events as attributes to get tab-completion and typo-proofing"

defaults.callbacks = [TrainEvalCallback]

class Learner():
    "Group together a `model`, some `data` and a `loss_func` to handle training"
    def __init__(self, model, data, loss_func, opt_func=SGD, lr=1e-2, splitter=trainable_params,
                 cbs=None, cb_funcs=None, metrics=None):
        self.model,self.data,self.loss_func = model,data,loss_func
        self.opt_func,self.lr,self.splitter = opt_func,lr,splitter

        self.metrics = [m if isinstance(m, Metric) else AvgMetric(m) for m in L(metrics)]
        self.training,self.logger,self.opt = False,print,None
        self.cbs = L([])
        self.add_cbs(cbf() for cbf in L(defaults.callbacks))
        self.add_cbs(cbs)
        self.add_cbs(cbf() for cbf in L(cb_funcs))

    def add_cbs(self, cbs):
        "Add `cbs` to the list of `Callback` and register `self` as their learner"
        for cb in L(cbs): self.add_cb(cb)

    def add_cb(self, cb):
        "Add `cb` to the list of `Callback` and register `self` as their learner"
        cb.learn = self
        setattr(self, cb.name, cb)
        self.cbs.append(cb)

    def remove_cbs(self, cbs):
        "Remove `cbs` from the list of `Callback` and deregister `self` as their learner"
        for cb in L(cbs): self.remove_cb(cb)

    def remove_cb(self, cb):
        "Add `cb` from the list of `Callback` and deregister `self` as their learner"
        cb.learn = None
        setattr(self, cb.name, None)
        if cb in self.cbs: self.cbs.remove(cb)

    @contextmanager
    def added_cbs(self, cbs):
        self.add_cbs(cbs)
        yield
        self.remove_cbs(cbs)

    def one_batch(self, xb, yb, i=None):
        "Train or evaluate `self.model` on batch `(xb,yb)`"
        try:
            if i is not None: self.iter = i
            self.xb,self.yb = xb,yb;                        self('begin_batch')
            self.pred = self.model(self.xb);                self('after_pred')
            self.loss = self.loss_func(self.pred, self.yb); self('after_loss')
            if not self.training: return
            self.loss.backward();                           self('after_backward')
            self.opt.step();                                self('after_step')
            self.opt.zero_grad()
        except CancelBatchException:                        self('after_cancel_batch')
        finally:                                            self('after_batch')

    def all_batches(self):
        "Train or evaluate `self.model` on all batches of `self.dl`"
        self.n_iter = len(self.dl)
        for i,(xb,yb) in enumerate(self.dl): self.one_batch(xb, yb, i)

    def do_begin_fit(self, n_epoch):
        "Prepare evertyhing for training `epochs` epochs"
        self.n_epoch,self.loss = n_epoch,tensor(0.)
        self('begin_fit')

    def do_epoch_train(self, epoch):
        "Execute the training part of the `epoch`-th epoch"
        self.epoch,self.dl = epoch,self.data.train_dl
        try:
            self('begin_train')
            self.all_batches()
        except CancelTrainException: self('after_cancel_train')
        finally:                     self('after_train')

    def do_epoch_validate(self):
        "Execute the validation part of an epoch"
        try:
            self('begin_validate')
            with torch.no_grad():
                self.dl = self.data.valid_dl
                self.all_batches()
        except CancelValidException: self('after_cancel_validate')
        finally:                     self('after_validate')

    def fit(self, n_epoch, cbs=None, reset_opt=False):
        "Fit `self.model` for `epochs` using `cbs`. Optionally `reset_opt`."
        with self.added_cbs(cbs):
            if reset_opt or not self.opt: self.opt = self.opt_func(self.splitter(self.model), lr=self.lr)

            try:
                self.do_begin_fit(n_epoch)
                for epoch in range(n_epoch):
                    try:
                        self('begin_epoch')
                        self.do_epoch_train(epoch)
                        self.do_epoch_validate()
                    except CancelEpochException: self('after_cancel_epoch')
                    finally:                     self('after_epoch')

            except CancelFitException: self('after_cancel_fit')
            finally:                   self('after_fit')

    def __call__(self, event_name):
        "Call `event_name` (one or a list) for all callbacks"
        for e in L(event_name): self._call_one(e)

    def _call_one(self, event_name):
        assert hasattr(event, event_name)
        [cb(event_name) for cb in self.cbs.sorted("order")]

class VerboseCallback(Callback):
    "Callback that prints the name of each event called"
    def __call__(self, event_name):
        print(event_name)
        super().__call__(event_name)

@docs
class Metric():
    "Blueprint for defining a metric"
    def reset(self):             pass
    def accumulate(self, learn): pass
    @property
    def value(self): raise NotImplementedError

    @property
    def name(self):
        "Name of the `Metric`, camel-cased and with Metric removed"
        name = re.sub(r'Metric$', '', self.__class__.__name__)
        return camel2snake(name or 'metric')

    _docs = {'reset': "Reset inner state to prepare for new computation",
            'accumulate': "Use `learn` to update the state with new results",
            'value': "The value of the metric"
    }

class AvgMetric(Metric):
    "Average the values of `func` taking into account potential different batch sizes"
    def __init__(self, func):  self.func = func
    def reset(self):           self.total,self.count = 0.,0
    def accumulate(self, learn):
        bs = find_bs(learn.yb)
        self.total += to_detach(self.func(learn.pred, learn.yb))*bs
        self.count += bs
    @property
    def value(self): return self.total/self.count
    @property
    def name(self):  return self.func.__name__

class AvgLoss(Metric):
    "Average the losses taking into account potential different batch sizes"
    def reset(self):           self.total,self.count = 0.,0
    def accumulate(self, learn):
        bs = find_bs(learn.yb)
        self.total += to_detach(learn.loss)*bs
        self.count += bs
    @property
    def value(self): return self.total/self.count
    @property
    def name(self):  return "loss"

class AvgSmoothLoss(Metric):
    "Smooth average of the losses (exponentially weighted with `beta`)"
    def __init__(self, beta=0.98): self.beta = beta
    def reset(self):               self.count,self.val = 0,tensor(0.)
    def accumulate(self, learn):
        self.count += 1
        self.val = torch.lerp(to_detach(learn.loss), self.val, self.beta)
    @property
    def value(self): return self.val/(1-self.beta**self.count)

from fastprogress.fastprogress import format_time

class Recorder(Callback):
    order = 20
    "Callback that registers statistics (lr, loss and metrics) during training"
    def __init__(self, add_time=True, train_metrics=False, beta=0.98):
        self.add_time,self.train_metrics = add_time,train_metrics
        self.loss,self.smooth_loss = AvgLoss(),AvgSmoothLoss(beta=beta)

    def begin_fit(self):
        "Prepare state for training"
        self.lrs,self.losses,self.values = [],[],[]
        names = [m.name for m in self._valid_mets]
        if self.train_metrics: names = [f'train_{n}' for n in names] + [f'valid_{n}' for n in names]
        else:                  names = ['train_loss', 'valid_loss'] + names[1:]
        if self.add_time: names.append('time')
        self.metric_names = names
        self.smooth_loss.reset()

    def after_batch(self):
        "Update all metrics and records lr and smooth loss in training"
        mets = [self.smooth_loss] + self._train_mets if self.training else self._valid_mets
        for met in mets: met.accumulate(self.learn)
        if not self.training: return
        self.lrs.append(self.opt.hypers[-1]['lr'])
        self.losses.append(self.smooth_loss.value)
        self.learn.smooth_loss = self.smooth_loss.value

    def begin_epoch(self):
        "Set timer if `self.add_time=True`"
        if self.add_time: self.start_epoch = time.time()
        self.log = []

    def begin_train   (self): [m.reset() for m in self._train_mets]
    def after_train   (self): self.log += [m.value for m in self._train_mets]
    def begin_validate(self): [m.reset() for m in self._valid_mets]
    def after_validate(self): self.log += [m.value for m in self._valid_mets]

    def after_epoch(self):
        "Store and log the loss/metric values"
        self.values.append(self.log.copy())
        if self.add_time: self.log.append(format_time(time.time() - self.start_epoch))
        self.logger(self.log)

    @property
    def _train_mets(self): return [self.loss] + (self.metrics if self.train_metrics else [])
    @property
    def _valid_mets(self): return [self.loss] + self.metrics

    def plot_lr  (self): plt.plot(self.lrs)
    def plot_loss(self): plt.plot(self.losses)

    def plot(self, skip_last=0):
        "Plot losses vs learning rates with a log scale, optionally `skip_last` values"
        losses = [o.item() for o in self.losses]
        n = len(losses)-skip_last
        plt.xscale('log')
        plt.plot(self.lrs[:n], losses[:n])

    _docs = {"begin_train": "Reset loss and metrics state",
             "after_validate": "Log loss and metric values on the training set (if `self.training_metrics=True`)",
             "begin_validate": "Reset loss and metrics state",
             "after_validate": "Log loss and metric values on the validation set",
             "plot_lr": "Plot the learning rates",
             "plot_loss": "Plot the losses"}

defaults.callbacks = [TrainEvalCallback, Recorder]

@contextmanager
def _learner_no_logging(self):
    "Context manager to temporarily remove `logger`"
    old_logger = self.logger
    self.logger = noop
    yield
    self.logger = old_logger

Learner.no_logging = _learner_no_logging

def _learn_validate(self, dl=None, cbs=None, metrics=None):
    "Validate on `dl` with potential new `cbs` and `metrics`."
    self.dl = dl or self.data.valid_dl
    metrics = metrics or self.metrics
    with self.added_cbs(cbs), self.no_logging():
        self(['begin_fit', 'begin_epoch', 'begin_validate'])
        self.all_batches()
        self(['after_validate', 'after_epoch', 'after_fit'])
    return self.recorder.values[-1]

Learner.validate = _learn_validate