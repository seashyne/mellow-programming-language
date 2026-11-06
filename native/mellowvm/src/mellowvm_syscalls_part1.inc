static PyObject *pyfloat(PyObject *v) {
    double d = to_double(v);
    return PyFloat_FromDouble(d);
}
/* helper: coerce to Python int */
static PyObject *pylong(PyObject *v) {
    long l = to_long(v);
    return PyLong_FromLong(l);
}

static int data_compare(PyObject *actual, const char *op, PyObject *expected) {
    int cmp_op = -1;
    if (strcmp(op, "==") == 0) cmp_op = Py_EQ;
    else if (strcmp(op, "!=") == 0) cmp_op = Py_NE;
    else if (strcmp(op, ">") == 0) cmp_op = Py_GT;
    else if (strcmp(op, ">=") == 0) cmp_op = Py_GE;
    else if (strcmp(op, "<") == 0) cmp_op = Py_LT;
    else if (strcmp(op, "<=") == 0) cmp_op = Py_LE;
    if (cmp_op >= 0) return PyObject_RichCompareBool(actual, expected, cmp_op);
    if (strcmp(op, "contains") == 0) {
        if (!PyUnicode_Check(actual) && !PyList_Check(actual) && !PyDict_Check(actual))
            return 0;
        return PySequence_Contains(actual, expected);
    }
    PyErr_Format(PyExc_RuntimeError, "RUNTIME: unsupported data.where operator: %s", op);
    return -1;
}

static PyObject *cvm_syscall_dispatch(const char *sn,
                                      PyObject **sa, long argc,
                                      CVM *parent_vm)
{
#define A0 (argc>0?sa[0]:Py_None)
#define A1 (argc>1?sa[1]:Py_None)
#define A2 (argc>2?sa[2]:Py_None)
#define A3 (argc>3?sa[3]:Py_None)
#define STR0 (PyUnicode_Check(A0)?PyUnicode_AsUTF8(A0):"")
#define STR1 (PyUnicode_Check(A1)?PyUnicode_AsUTF8(A1):"")

