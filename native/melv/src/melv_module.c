#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include "melv_native.h"

static PyObject *info_to_dict(const MelvInfo *info) {
    PyObject *d = PyDict_New();
    PyObject *errors = PyList_New(0);
    PyObject *warnings = PyList_New(0);
    if (!d || !errors || !warnings) {
        Py_XDECREF(d);
        Py_XDECREF(errors);
        Py_XDECREF(warnings);
        return NULL;
    }
    if (info->error[0]) PyList_Append(errors, PyUnicode_FromString(info->error));
    if (info->warning[0]) PyList_Append(warnings, PyUnicode_FromString(info->warning));
    PyDict_SetItemString(d, "ok", info->ok ? Py_True : Py_False);
    PyDict_SetItemString(d, "native", Py_True);
    PyDict_SetItemString(d, "native_supported", info->native_supported ? Py_True : Py_False);
    PyDict_SetItemString(d, "errors", errors);
    PyDict_SetItemString(d, "warnings", warnings);
    PyDict_SetItemString(d, "codec", PyUnicode_FromString(info->codec));
    PyDict_SetItemString(d, "fps", PyFloat_FromDouble(info->fps));
    PyDict_SetItemString(d, "width", PyLong_FromLong(info->width));
    PyDict_SetItemString(d, "height", PyLong_FromLong(info->height));
    PyDict_SetItemString(d, "frames", PyLong_FromLong(info->frames));
    PyDict_SetItemString(d, "expected_frames", PyLong_FromLong(info->expected_frames));
    PyDict_SetItemString(d, "bytes", PyLong_FromLongLong(info->bytes));
    Py_DECREF(errors);
    Py_DECREF(warnings);
    return d;
}

static PyObject *py_inspect(PyObject *self, PyObject *args) {
    const char *path;
    MelvInfo info;
    (void)self;
    if (!PyArg_ParseTuple(args, "s", &path)) return NULL;
    melv_native_inspect_file(path, &info);
    return info_to_dict(&info);
}

static PyObject *py_pack_frames(PyObject *self, PyObject *args, PyObject *kwargs) {
    PyObject *frames_obj;
    const char *output_path;
    double fps = 24.0;
    PyObject *seq;
    Py_ssize_t count;
    const char **frames;
    MelvInfo info;
    static char *kwlist[] = {"frames", "output", "fps", NULL};
    (void)self;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "Os|d", kwlist, &frames_obj, &output_path, &fps)) {
        return NULL;
    }
    seq = PySequence_Fast(frames_obj, "frames must be a sequence of paths");
    if (!seq) {
        return NULL;
    }
    count = PySequence_Fast_GET_SIZE(seq);
    frames = (const char **)PyMem_Calloc((size_t)count, sizeof(char *));
    if (!frames) {
        Py_DECREF(seq);
        return PyErr_NoMemory();
    }
    for (Py_ssize_t i = 0; i < count; i++) {
        PyObject *item = PySequence_Fast_GET_ITEM(seq, i);
        frames[i] = PyUnicode_AsUTF8(item);
        if (!frames[i]) {
            PyMem_Free(frames);
            Py_DECREF(seq);
            return NULL;
        }
    }
    melv_native_pack_ppm_sequence(frames, (size_t)count, output_path, fps, &info);
    PyMem_Free(frames);
    Py_DECREF(seq);
    return info_to_dict(&info);
}

static PyObject *py_extract_native(PyObject *self, PyObject *args) {
    const char *input_path;
    const char *out_dir;
    MelvInfo info;
    (void)self;
    if (!PyArg_ParseTuple(args, "ss", &input_path, &out_dir)) return NULL;
    melv_native_extract_ppm_frames(input_path, out_dir, &info);
    return info_to_dict(&info);
}

static PyMethodDef MelvMethods[] = {
    {"inspect", py_inspect, METH_VARARGS, "Inspect and validate a MELV container using the native C reader."},
    {"validate", py_inspect, METH_VARARGS, "Validate a MELV container using the native C reader."},
    {"pack_frames", (PyCFunction)(void (*)(void))py_pack_frames, METH_VARARGS | METH_KEYWORDS, "Pack PPM P6 frames into native MELV2 using the C backend."},
    {"extract_native", py_extract_native, METH_VARARGS, "Extract native MELV2 frames into PPM P6 files using the C backend."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef module = {
    PyModuleDef_HEAD_INIT,
    "_melv",
    "Native MELV container reader.",
    -1,
    MelvMethods,
    NULL,
    NULL,
    NULL,
    NULL
};

PyMODINIT_FUNC PyInit__melv(void) {
    return PyModule_Create(&module);
}
