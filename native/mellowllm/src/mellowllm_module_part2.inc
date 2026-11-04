static PyObject *py_batch(PyObject *self, PyObject *args) {
    (void)self;
    PyObject *ops_obj = NULL;
    if (!PyArg_ParseTuple(args, "O", &ops_obj)) {
        return NULL;
    }
    PyObject *ops = PySequence_Fast(ops_obj, "expected a sequence of operation maps");
    if (!ops) {
        return NULL;
    }
    Py_ssize_t len = PySequence_Fast_GET_SIZE(ops);
    PyObject *out = PyList_New(len);
    if (!out) {
        Py_DECREF(ops);
        return NULL;
    }
    PyObject **items = PySequence_Fast_ITEMS(ops);
    for (Py_ssize_t i = 0; i < len; i++) {
        PyObject *item = items[i];
        PyObject *result = NULL;
        if (!PyMapping_Check(item)) {
            result = Py_BuildValue("{s:n,s:s}", "index", i, "error", "operation must be a map");
            PyList_SET_ITEM(out, i, result);
            continue;
        }
        PyObject *op_obj = PyMapping_GetItemString(item, "op");
        const char *op = op_obj ? PyUnicode_AsUTF8(op_obj) : "";
        if (!op) {
            Py_XDECREF(op_obj);
            Py_DECREF(out);
            Py_DECREF(ops);
            return NULL;
        }
        if (strcmp(op, "softmax") == 0 || strcmp(op, "gelu") == 0) {
            PyObject *values = PyMapping_GetItemString(item, "values");
            PyObject *call_args = PyTuple_Pack(1, values ? values : Py_None);
            result = strcmp(op, "softmax") == 0 ? py_softmax(NULL, call_args) : py_gelu(NULL, call_args);
            Py_XDECREF(values);
            Py_DECREF(call_args);
        } else if (strcmp(op, "matmul") == 0) {
            PyObject *a = PyMapping_GetItemString(item, "a");
            PyObject *b = PyMapping_GetItemString(item, "b");
            PyObject *m = PyMapping_GetItemString(item, "m");
            PyObject *n = PyMapping_GetItemString(item, "n");
            PyObject *k = PyMapping_GetItemString(item, "k");
            PyObject *call_args = PyTuple_Pack(5, a ? a : Py_None, b ? b : Py_None, m ? m : Py_None, n ? n : Py_None, k ? k : Py_None);
            result = py_matmul(NULL, call_args);
            Py_XDECREF(a); Py_XDECREF(b); Py_XDECREF(m); Py_XDECREF(n); Py_XDECREF(k);
            Py_DECREF(call_args);
        } else if (strcmp(op, "layer_norm") == 0) {
            PyObject *values = PyMapping_GetItemString(item, "values");
            PyObject *gamma = PyMapping_GetItemString(item, "gamma");
            PyObject *beta = PyMapping_GetItemString(item, "beta");
            PyObject *eps = PyMapping_GetItemString(item, "eps");
            PyObject *default_eps = NULL;
            PyObject *eps_arg = eps ? eps : (default_eps = PyFloat_FromDouble(1e-5));
            PyObject *call_args = PyTuple_Pack(4, values ? values : Py_None, gamma ? gamma : Py_None, beta ? beta : Py_None, eps_arg);
            result = py_layer_norm(NULL, call_args);
            Py_XDECREF(default_eps);
            Py_XDECREF(values); Py_XDECREF(gamma); Py_XDECREF(beta); Py_XDECREF(eps);
            Py_DECREF(call_args);
        } else {
            result = Py_BuildValue("{s:s}", "error", "unknown tensor op");
        }
        if (!result) {
            Py_DECREF(out);
            Py_DECREF(ops);
            Py_XDECREF(op_obj);
            return NULL;
        }
        PyObject *row = Py_BuildValue("{s:s,s:s,s:O,s:n}", "op", op, "backend", "mellow-native-c", "values", result, "index", i);
        PyObject *error_key = PyUnicode_FromString("error");
        int has_error = error_key && PyDict_Check(result) ? PyDict_Contains(result, error_key) : 0;
        Py_XDECREF(error_key);
        if (has_error > 0) {
            Py_DECREF(row);
            row = result;
            Py_INCREF(row);
            PyObject *idx = PyLong_FromSsize_t(i);
            if (idx) {
                PyDict_SetItemString(row, "index", idx);
                Py_DECREF(idx);
            }
        }
        Py_DECREF(result);
        PyList_SET_ITEM(out, i, row);
        Py_XDECREF(op_obj);
    }
    Py_DECREF(ops);
    return out;
}

static PyMethodDef METHODS[] = {
    {"capabilities", py_capabilities, METH_NOARGS, "Return Mellow native LLM tensor capabilities."},
    {"matmul", py_matmul, METH_VARARGS, "Matrix multiply flattened row-major matrices."},
    {"softmax", py_softmax, METH_VARARGS, "Softmax over a vector."},
    {"gelu", py_gelu, METH_VARARGS, "GELU activation over a vector."},
    {"layer_norm", py_layer_norm, METH_VARARGS, "Layer norm over a vector."},
    {"batch", py_batch, METH_VARARGS, "Run multiple tensor kernels in one native call."},
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
