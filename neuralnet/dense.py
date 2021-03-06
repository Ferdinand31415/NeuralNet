import numpy as np
from functools import wraps

from .layer import Layer
from . import kernel_initializers

class Dense(Layer):
    def __init__(
            self,
            output_dim,
            activation,
            kernel_initializer=kernel_initializers.normal,
            kernel_regularizer=None,
            bias_regularizer=None,
            input_shape=None,
            verbose=False):

        super().__init__()

        self.verbose = verbose
        self.g = activation

        assert isinstance(output_dim, int)
        self.output_dim = (output_dim, )

        self.input_shape = input_shape

        self.kernel_initializer = kernel_initializer

        self.kernel_regularizer = kernel_regularizer(self, 'w') if kernel_regularizer else None
        self.bias_regularizer = bias_regularizer(self, 'b') if bias_regularizer else None


    def prepare_params(self, input_shape=None):
        if input_shape:
            self.shape = self.output_dim + input_shape
        else:
            self.shape = self.output_dim + (self.input_shape, )

        self.w = kernel_initializers.create(self.kernel_initializer, self.shape)
        self.dw = np.zeros(self.w.shape)

        self.b = np.zeros(self.output_dim + (1,) )
        self.db = np.zeros(self.b.shape)
        return self.output_dim


    def forward(self, a):
        self.z = np.dot(self.w, a) + self.b
        self.a = self.g(self.z)
        return self.a


    def backward_step(self, a_next, w_prev, error_prev):
        batch_size = a_next.shape[-1]

        derivative = self.g(self.z, derivative=True)
        error = np.dot(w_prev.T, error_prev) * derivative

        self.dw = 1 / batch_size * np.dot(error, a_next.T)
        self.db = 1 / batch_size * np.sum(error, axis=1, keepdims=True)

        if self.kernel_regularizer:
            self.dw += 1 / batch_size * self.kernel_regularizer.derivative()
            assert np.all(self.kernel_regularizer.param == self.w)


        if self.bias_regularizer:
            self.db += 1 / batch_size * self.bias_regularizer.derivative()

        return error

