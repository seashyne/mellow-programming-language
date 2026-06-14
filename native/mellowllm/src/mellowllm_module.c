#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include "mellowllm.h"

static int list_to_double_array(PyObject *obj, double **out, Py_ssize_t *len) {
    PyObject *seq = PySequence_Fast(obj, "expected a sequence");
    if (!seq) {
        return 0;
    }
    Py_ssize_t n = PySequence_Fast_GET_SIZE(seq);
    double *values = PyMem_Calloc((size_t)n, sizeof(double));
    if (!values) {
        Py_DECREF(seq);
        PyErr_NoMemory();
        return 0;
    }
    PyObject **items = PySequence_Fast_ITEMS(seq);
    for (Py_ssize_t i = 0; i < n; i++) {
        values[i] = PyFloat_AsDouble(items[i]);
        if (PyErr_Occurred()) {
            PyMem_Free(values);
            Py_DECREF(seq);
            return 0;
        }
    }
    Py_DECREF(seq);
    *out = values;
    *len = n;
    return 1;
}

static PyObject *double_array_to_list(const double *values, Py_ssize_t len) {
    PyObject *list = PyList_New(len);
    if (!list) {
        return NULL;
    }
    for (Py_ssize_t i = 0; i < len; i++) {
        PyObject *value = PyFloat_FromDouble(values[i]);
        if (!value) {
            Py_DECREF(list);
            return NULL;
        }
        PyList_SET_ITEM(list, i, value);
    }
    return list;
}

static PyObject *py_capabilities(PyObject *self, PyObject *args) {
    (void)self;
    (void)args;
    return Py_BuildValue(
        "{s:s,s:[s,s,s,s],s:[s],s:s}",
        "backend", "mellow-native-c",
        "kernels", "matmul", "softmax", "gelu", "layer_norm",
        "devices", "cpu",
        "dtype", "float64"
    );
}

static PyObject *py_matmul(PyObject *self, PyObject *args) {
    (void)self;
    PyObject *a_obj = NULL;
    PyObject *b_obj = NULL;
    Py_ssize_t m = 0, n = 0, k = 0;
    if (!PyArg_ParseTuple(args, "OOnnn", &a_obj, &b_obj, &m, &n, &k)) {
        return NULL;
    }
    if (m < 0 || n < 0 || k < 0) {
        PyErr_SetString(PyExc_ValueError, "matrix dimensions must be non-negative");
        return NULL;
    }
    double *a = NULL;
    double *b = NULL;
    Py_ssize_t a_len = 0;
    Py_ssize_t b_len = 0;
    if (!list_to_double_array(a_obj, &a, &a_len) || !list_to_double_array(b_obj, &b, &b_len)) {
        PyMem_Free(a);
        return NULL;
    }
    if (a_len != m * k || b_len != k * n) {
        PyMem_Free(a);
        PyMem_Free(b);
        PyErr_SetString(PyExc_ValueError, "matrix data length does not match dimensions");
        return NULL;
    }
    Py_ssize_t out_len = m * n;
    double *out = PyMem_Calloc((size_t)out_len, sizeof(double));
    if (!out) {
        PyMem_Free(a);
        PyMem_Free(b);
        PyErr_NoMemory();
        return NULL;
    }
    mellowllm_matmul(a, b, out, (size_t)m, (size_t)n, (size_t)k);
    PyObject *result = double_array_to_list(out, out_len);
    PyMem_Free(a);
    PyMem_Free(b);
    PyMem_Free(out);
    return result;
}

static PyObject *py_softmax(PyObject *self, PyObject *args) {
    (void)self;
    PyObject *values_obj = NULL;
    if (!PyArg_ParseTuple(args, "O", &values_obj)) {
        return NULL;
    }
    double *values = NULL;
    Py_ssize_t len = 0;
    if (!list_to_double_array(values_obj, &values, &len)) {
        return NULL;
    }
    double *out = PyMem_Calloc((size_t)len, sizeof(double));
    if (!out) {
        PyMem_Free(values);
        PyErr_NoMemory();
        return NULL;
    }
    mellowllm_softmax(values, out, (size_t)len);
    PyObject *result = double_array_to_list(out, len);
    PyMem_Free(values);
    PyMem_Free(out);
    return result;
}

static PyObject *py_gelu(PyObject *self, PyObject *args) {
    (void)self;
    PyObject *values_obj = NULL;
    if (!PyArg_ParseTuple(args, "O", &values_obj)) {
        return NULL;
    }
    double *values = NULL;
    Py_ssize_t len = 0;
    if (!list_to_double_array(values_obj, &values, &len)) {
        return NULL;
    }
    double *out = PyMem_Calloc((size_t)len, sizeof(double));
    if (!out) {
        PyMem_Free(values);
        PyErr_NoMemory();
        return NULL;
    }
    mellowllm_gelu(values, out, (size_t)len);
    PyObject *result = double_array_to_list(out, len);
    PyMem_Free(values);
    PyMem_Free(out);
    return result;
}

static PyObject *py_layer_norm(PyObject *self, PyObject *args) {
    (void)self;
    PyObject *values_obj = NULL;
    PyObject *gamma_obj = NULL;
    PyObject *beta_obj = NULL;
    double eps = 1e-5;
    if (!PyArg_ParseTuple(args, "OOOd", &values_obj, &gamma_obj, &beta_obj, &eps)) {
        return NULL;
    }
    double *values = NULL;
    double *gamma = NULL;
    double *beta = NULL;
    Py_ssize_t len = 0;
    Py_ssize_t gamma_len = 0;
    Py_ssize_t beta_len = 0;
    if (!list_to_double_array(values_obj, &values, &len) ||
        !list_to_double_array(gamma_obj, &gamma, &gamma_len) ||
        !list_to_double_array(beta_obj, &beta, &beta_len)) {
        PyMem_Free(values);
        PyMem_Free(gamma);
        return NULL;
    }
    if (gamma_len != len || beta_len != len) {
        PyMem_Free(values);
        PyMem_Free(gamma);
        PyMem_Free(beta);
        PyErr_SetString(PyExc_ValueError, "gamma and beta must match value length");
        return NULL;
    }
    double *out = PyMem_Calloc((size_t)len, sizeof(double));
    if (!out) {
        PyMem_Free(values);
        PyMem_Free(gamma);
        PyMem_Free(beta);
        PyErr_NoMemory();
        return NULL;
    }
    mellowllm_layer_norm(values, gamma, beta, out, (size_t)len, eps);
    PyObject *result = double_array_to_list(out, len);
    PyMem_Free(values);
    PyMem_Free(gamma);
    PyMem_Free(beta);
    PyMem_Free(out);
    return result;
}

static PyMethodDef METHODS[] = {
    {"capabilities", py_capabilities, METH_NOARGS, "Return Mellow native LLM tensor capabilities."},
    {"matmul", py_matmul, METH_VARARGS, "Matrix multiply flattened row-major matrices."},
    {"softmax", py_softmax, METH_VARARGS, "Softmax over a vector."},
    {"gelu", py_gelu, METH_VARARGS, "GELU activation over a vector."},
    {"layer_norm", py_layer_norm, METH_VARARGS, "Layer norm over a vector."},
    {NULL, NULL, 0, NULL},
};

static struct PyModuleDef MODULE = {
    PyModuleDef_HEAD_INIT,
    "mellowlang._mellowllm",
    "Mellow native LLM tensor kernels.",
    -1,
    METHODS,
};

PyMODINIT_FUNC PyInit__mellowllm(void) {
    return PyModule_Create(&MODULE);
}
