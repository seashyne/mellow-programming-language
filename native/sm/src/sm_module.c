#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include "sm_native.h"

#include <stdlib.h>

static PyObject *info_to_dict(const SmInfo *info) {
    PyObject *d = PyDict_New();
    if (!d) return NULL;
    PyDict_SetItemString(d, "ok", info->ok ? Py_True : Py_False);
    PyDict_SetItemString(d, "native", Py_True);
    PyDict_SetItemString(d, "codec", PyUnicode_FromString(info->codec));
    PyDict_SetItemString(d, "version", PyLong_FromLong(info->version));
    PyDict_SetItemString(d, "dictionary_entries", PyLong_FromLong(info->dictionary_entries));
    PyDict_SetItemString(d, "original_size", PyLong_FromUnsignedLong(info->original_size));
    PyDict_SetItemString(d, "token_stream_size", PyLong_FromUnsignedLong(info->token_stream_size));
    PyDict_SetItemString(d, "payload_size", PyLong_FromUnsignedLong(info->payload_size));
    PyDict_SetItemString(d, "compressed_size", PyLong_FromUnsignedLong(info->compressed_size));
    PyDict_SetItemString(d, "checksum_ok", info->checksum_ok ? Py_True : Py_False);
    if (info->error[0]) {
        PyDict_SetItemString(d, "error", PyUnicode_FromString(info->error));
    }
    return d;
}

static PyObject *py_pack_bytes(PyObject *self, PyObject *args) {
    const unsigned char *input;
    Py_ssize_t input_size;
    unsigned char *out = NULL;
    size_t out_size = 0;
    SmInfo info;
    (void)self;
    if (!PyArg_ParseTuple(args, "y#", &input, &input_size)) return NULL;
    if (!sm_native_pack_text(input, (size_t)input_size, &out, &out_size, &info)) {
        PyErr_SetString(PyExc_ValueError, info.error[0] ? info.error : "SM native pack failed");
        return NULL;
    }
    PyObject *bytes = PyBytes_FromStringAndSize((const char *)out, (Py_ssize_t)out_size);
    free(out);
    return bytes;
}

static PyObject *py_unpack_bytes(PyObject *self, PyObject *args) {
    const unsigned char *input;
    Py_ssize_t input_size;
    unsigned char *out = NULL;
    size_t out_size = 0;
    SmInfo info;
    (void)self;
    if (!PyArg_ParseTuple(args, "y#", &input, &input_size)) return NULL;
    if (!sm_native_unpack_bytes(input, (size_t)input_size, &out, &out_size, &info)) {
        PyErr_SetString(PyExc_ValueError, info.error[0] ? info.error : "SM native unpack failed");
        return NULL;
    }
    PyObject *bytes = PyBytes_FromStringAndSize((const char *)out, (Py_ssize_t)out_size);
    free(out);
    return bytes;
}

static PyObject *py_inspect_bytes(PyObject *self, PyObject *args) {
    const unsigned char *input;
    Py_ssize_t input_size;
    SmInfo info;
    (void)self;
    if (!PyArg_ParseTuple(args, "y#", &input, &input_size)) return NULL;
    if (!sm_native_inspect_bytes(input, (size_t)input_size, &info)) {
        PyErr_SetString(PyExc_ValueError, info.error[0] ? info.error : "SM native inspect failed");
        return NULL;
    }
    return info_to_dict(&info);
}

static PyMethodDef SmMethods[] = {
    {"pack_bytes", py_pack_bytes, METH_VARARGS, "Pack UTF-8/text-like bytes into native SM3."},
    {"unpack_bytes", py_unpack_bytes, METH_VARARGS, "Unpack native SM3 bytes."},
    {"inspect_bytes", py_inspect_bytes, METH_VARARGS, "Inspect native SM3 bytes."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef module = {
    PyModuleDef_HEAD_INIT,
    "_smnative",
    "Native Smallless SM codec.",
    -1,
    SmMethods,
    NULL,
    NULL,
    NULL,
    NULL
};

PyMODINIT_FUNC PyInit__smnative(void) {
    return PyModule_Create(&module);
}
