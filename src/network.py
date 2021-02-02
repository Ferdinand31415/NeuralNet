import numpy as np

from functools import partial
import itertools
import warnings

import layer
from activations import softmax
import misc

class Network(list):

    def __init__(self, verbose=True):

        self.layers = {}
        self.epoch = 0
        self.verbose=verbose

        self.append(layer.Layer())  # starting layer, for holding input values to the network
        self.softmax = None  # True if last act fct is softmax

    def __str__(self):
        s = 17*'*' + '\nmodel information:\n'

        number_params = 0
        params = ['w','b','beta','gamma']
        for layer in self:
            s += str(layer) + '\n'
            for param in params:
                if hasattr(layer,param):
                    N = np.multiply.accumulate(getattr(layer,param).shape)[-1]
                    number_params += N

        s += '  number of parameters: %i' % number_params
        return s

    def __call__(self, a):
        return self.forward_step(a)

    def add(self, layer):
        self.append(layer)

    def compile(self, loss, lr, optimizer=None):
        self.batch_norm = False
        for l in self.layers:
            try:
                if l.info == 'batch':
                    self.batch_norm = True
            except AttributeError:
                pass

        self.lr = lr
        self.loss_fct = loss
        self.derivative_loss_fct = partial(self.loss_fct, derivative=True)

        if self[-1].g is softmax:
            self.softmax = True

    def fit(self, x, y, epochs=1, batch_size=128, validation_data=None, gradients_to_check_each_epoch=None, verbose=True):

        ytrain_labels = np.argmax(y, axis=0)
        Ntrain = x.shape[-1]

        if validation_data:
            xtest, ytest = validation_data
            assert xtest.shape[-1] == ytest.shape[-1]
            ytest_labels = np.argmax(ytest, axis=0)
            Ntest = xtest.shape[-1]
        else:
            val_printout = ''

        if not gradients_to_check_each_epoch:
            grad_printout = ''

        for epoch in range(1, epochs):

            losses = []
            self.lr *= 0.993

            minibatches = misc.minibatches(x, y, batch_size=1000)
            for m, minibatch in enumerate(minibatches):

                self.train_on_batch(*minibatch)

                losses.append(self.get_loss(*minibatch))

                # important: do gradient checking before weights are changed!
                if gradients_to_check_each_epoch and m == 1:
                    goodness = self.gradient_checks(*minibatch, eps=10**(-6), checks=3)
                    grad_printout = f'gradcheck: {goodness:.3e}'

                self.update_weights()


            a_train = self(x)
            ytrain_pred = np.argmax(a_train, axis=0)
            train_correct = np.sum(ytrain_pred == ytrain_labels)
            loss = np.mean(losses)

            if validation_data:
                a_test = self(xtest)
                ytest_pred = np.argmax(a_test, axis=0)
                test_correct = np.sum(ytest_pred == ytest_labels)
                val_loss = self.get_loss(xtest, ytest)

                val_printout = f'{val_loss=:.3f}, test:{test_correct}/{Ntest}'

            print(f'{epoch=}, {loss=:.3f}, train: {train_correct}/{Ntrain}, {val_printout}, {grad_printout}')

            self.epoch += 1


    def forward_step(self, a):
        if self.verbose: print('START FORWARD STEP')
        self[0].a = a
        for layer in self:
            a = layer(a)
        return a

    def train_on_batch(self, x, y):
        self.forward_step(x)
        self.backpropagation(x, y)


    def backpropagation(self, x, y, verbose=True):

        error_prev = self._backprop_last_layer(x, y)

        for l in range(len(self)-2, 0, -1):

            a_next = self[l - 1].a
            w_prev = self[l + 1].w

            error_prev = self[l].backward_step(a_next, w_prev, error_prev)


    def _backprop_last_layer(self, x, y):
        '''
        calculates the error for the last layer.
        It is a little bit special as it involves
        the cost function, so do it in its own function.
        '''

        derivative_loss = self.derivative_loss_fct(
            ypred=self[-1].a,
            ytrue=y,
            average_examples=False
        )

        derivative_layer = self[-1].g(
            z=self[-1].z,
            derivative=True
        )

        if self[-1].g is softmax:
            deltaL = np.einsum('in,jin->jn', derivative_loss, derivative_layer)
        else:
            deltaL = derivative_layer * derivative_loss

        batch_size = x.shape[-1]
        self[-1].dw = 1 / batch_size * np.dot(deltaL, self[-2].a.T)
        self[-1].db = 1 / batch_size * np.sum(deltaL, axis=1, keepdims=True)
        return deltaL


    def update_weights(self):
        for layer in self[1:]:
            layer.w -= self.lr * layer.dw
            layer.b -= self.lr * layer.db


    def get_loss(self, x, ytrue, average_examples=True):
        ypred = self(x)
        loss = self.loss_fct(ypred, ytrue, average_examples=average_examples)
        return loss


    def predict(self, x):
        return self(x)


    def complete_gradient_check(self, x, y, eps=10**(-6)):
        self.grads_ = []
        for layer in self[1:]:

            gradient_manual = np.zeros(layer.w.shape)

            ranges = [range(dim) for dim in layer.w.shape]
            for idx in itertools.product(*ranges):

                gradient = self.gradient_check(
                    x=x,
                    ytrue=y,
                    eps=eps,
                    layer_id=layer.layer_id,
                    weight_idx=idx
                )

                gradient_manual[idx] = gradient

            numerator = np.linalg.norm(gradient_manual - layer.dw)
            denominator = np.linalg.norm(gradient_manual) +  np.linalg.norm(layer.dw)

            goodness = numerator / denominator
            self.n= numerator
            self.d=denominator
            self.grads_.append(gradient_manual)
            print(f'backprop err layer {layer.layer_id}: {goodness=}')


    def gradient_checks(self, x, ytrue, checks=15, eps=10**(-6)):
        '''
        Carries out several gradient checks in random places at once
        '''

        grads = np.zeros(checks)
        grads_backprop = np.zeros(checks)

        for check in range(checks):

            layer_id = np.random.randint(1, len(self))
            shape = self[layer_id].w.shape
            weight_idx = tuple(np.random.choice(dim) for dim in shape)
            gradient = self.gradient_check(
                x=x,
                ytrue=ytrue,
                eps=eps,
                layer_id=layer_id,
                weight_idx=weight_idx
            )

            grads[check] = gradient
            grads_backprop[check] = self[layer_id].dw[weight_idx]

        n = np.linalg.norm
        goodness = n(grads - grads_backprop)/(n(grads) + n(grads_backprop))

        return goodness


    def gradient_check(self, x, ytrue, eps, layer_id, weight_idx):
        ''' to test the backprop algorithm, we also manually check the gradient
            for one randomly chosen weight/bias
            do this by using df(x)/dx = (f(x+eps) - f(x-eps)/2/eps'''

        cost = 0
        w_original = self[layer_id].w[weight_idx]

        for sign in [+1, -1]:

            self[layer_id].w[weight_idx] = w_original + sign * eps # change weight
            cost += sign * self.get_loss(x, ytrue, average_examples=True)

        self[layer_id].w[weight_idx] = w_original  # restore weight


        gradient_manual = cost / (2*eps)
        return gradient_manual