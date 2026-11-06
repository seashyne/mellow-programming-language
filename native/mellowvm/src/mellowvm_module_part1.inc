static PyObject *cvm_call1(CVM *vm, PyObject *fn_ref,
                            PyObject **args, long argc);
static PyObject *cvm_syscall_dispatch(const char *sn,
                                      PyObject **sa, long argc,
                                      CVM *parent_vm);

static void cvm_attach_error_location(int pc)
{
    PyObject *type = NULL, *value = NULL, *traceback = NULL;
    PyObject *pc_value = NULL, *kind_value = NULL, *message_value = NULL;
    const char *message = NULL;

    if (!PyErr_Occurred()) return;
    PyErr_Fetch(&type, &value, &traceback);
    PyErr_NormalizeException(&type, &value, &traceback);
    if (!value) {
        value = PyObject_CallNoArgs(type ? type : PyExc_RuntimeError);
    }
    if (value) {
        pc_value = PyLong_FromLong(pc);
        message_value = PyObject_Str(value);
        message = message_value ? PyUnicode_AsUTF8(message_value) : NULL;
        kind_value = PyUnicode_FromString(
            message && strncmp(message, "SANDBOX:", 8) == 0 ? "SANDBOX" : "RUNTIME"
        );
        if (pc_value && PyObject_SetAttrString(value, "pc", pc_value) < 0) PyErr_Clear();
        if (kind_value && PyObject_SetAttrString(value, "kind", kind_value) < 0) PyErr_Clear();
        if (message_value && PyObject_SetAttrString(value, "msg", message_value) < 0) PyErr_Clear();
    }
    Py_XDECREF(pc_value);
    Py_XDECREF(kind_value);
    Py_XDECREF(message_value);
    PyErr_Restore(type, value, traceback);
}

/* ── String interning for hot comparisons ──────────────────────── */
/* We compare syscall names as C strings — fast enough */

/* ── Helpers ────────────────────────────────────────────────────── */

static int mellow_truthy(PyObject *v) {
    if (!v || v == Py_None || v == Py_False) return 0;
    if (v == Py_True) return 1;
    if (PyLong_CheckExact(v))  return PyLong_AsLong(v) != 0;
    if (PyFloat_CheckExact(v)) return PyFloat_AS_DOUBLE(v) != 0.0;
    if (PyUnicode_Check(v))    return PyUnicode_GET_LENGTH(v) > 0;
    if (PyList_Check(v))       return PyList_GET_SIZE(v) > 0;
    if (PyDict_Check(v))       return PyDict_Size(v) > 0;
    return 1;
}

static PyObject *fmt_list(PyObject *lst);
static PyObject *mellow_format(PyObject *v) {
    if (!v || v == Py_None)    return PyUnicode_FromString("None");
    if (v == Py_True)          return PyUnicode_FromString("True");
    if (v == Py_False)         return PyUnicode_FromString("False");
    if (PyLong_CheckExact(v))  return PyObject_Str(v);
    if (PyFloat_CheckExact(v)) {
        double d = PyFloat_AS_DOUBLE(v), ip;
        if (modf(d, &ip)==0.0 && fabs(d)<1e15) {
            PyObject *li = PyLong_FromDouble(d);
            if (!li) return NULL;
            PyObject *s = PyObject_Str(li); Py_DECREF(li); return s;
        }
        return PyObject_Str(v);
    }
    if (PyUnicode_Check(v)) { Py_INCREF(v); return v; }
    if (PyList_Check(v))    return fmt_list(v);
    if (PyDict_Check(v))    return PyObject_Repr(v);
    return PyObject_Str(v);
}

static int storage_name_unsafe(const char *raw) {
    if (!raw) return 0;
    if (raw[0] == '/' || raw[0] == '\\') return 1;
    if (((raw[0] >= 'A' && raw[0] <= 'Z') || (raw[0] >= 'a' && raw[0] <= 'z')) && raw[1] == ':') return 1;
    if (strcmp(raw, "..") == 0) return 1;
    if (strncmp(raw, "../", 3) == 0 || strncmp(raw, "..\\", 3) == 0) return 1;
    if (strstr(raw, "/../") || strstr(raw, "\\..\\") || strstr(raw, "/..\\") || strstr(raw, "\\../")) return 1;
    size_t n = strlen(raw);
    if (n >= 3 && (strcmp(raw + n - 3, "/..") == 0 || strcmp(raw + n - 3, "\\..") == 0)) return 1;
    return 0;
}

static int storage_ensure_base(CVM *vm) {
    PyObject *os_mod = PyImport_ImportModule("os");
    if (!os_mod) return 0;
    PyObject *makedirs = PyObject_GetAttrString(os_mod, "makedirs");
    Py_DECREF(os_mod);
    if (!makedirs) return 0;
    PyObject *args = PyTuple_Pack(1, vm->storage_dir);
    PyObject *kwargs = Py_BuildValue("{s:O}", "exist_ok", Py_True);
    PyObject *res = (args && kwargs) ? PyObject_Call(makedirs, args, kwargs) : NULL;
    Py_XDECREF(args);
    Py_XDECREF(kwargs);
    Py_DECREF(makedirs);
    if (!res) return 0;
    Py_DECREF(res);
    return 1;
}

static PyObject *cvm_storage_path(CVM *vm, PyObject *filename) {
    PyObject *fs = mellow_format(filename);
    if (!fs) return NULL;
    const char *raw = PyUnicode_AsUTF8(fs);
    if (!raw) {
        Py_DECREF(fs);
        return NULL;
    }
    while (*raw == ' ' || *raw == '\t' || *raw == '"' || *raw == '\'') raw++;
    if (storage_name_unsafe(raw)) {
        Py_DECREF(fs);
        PyErr_SetString(PyExc_RuntimeError, "SANDBOX: invalid storage path (path traversal blocked)");
        return NULL;
    }
    const char *name = (*raw == '\0' || strcmp(raw, ".") == 0) ? "save" : raw;
    int has_json = 0;
    size_t n = strlen(name);
    if (n >= 5 && strcmp(name + n - 5, ".json") == 0) has_json = 1;
    PyObject *path = PyUnicode_FromFormat(has_json ? "%U/%s" : "%U/%s.json", vm->storage_dir, name);
    Py_DECREF(fs);
    return path;
}
static PyObject *fmt_list(PyObject *lst) {
    Py_ssize_t n = PyList_GET_SIZE(lst);
    PyObject *parts = PyList_New(n);
    if (!parts) return NULL;
    for (Py_ssize_t i=0;i<n;i++) {
        PyObject *item = PyList_GET_ITEM(lst,i);
        PyObject *f;
        /* Match Python VM: str(val) — which uses repr for strings in lists */
        if (PyUnicode_Check(item)) {
            f = PyObject_Repr(item);  /* 'hello' not hello */
        } else {
            f = mellow_format(item);
        }
        if (!f){Py_DECREF(parts);return NULL;}
        PyList_SET_ITEM(parts,i,f);
    }
    PyObject *sep = PyUnicode_FromString(", ");
    PyObject *j   = PyUnicode_Join(sep,parts);
    Py_DECREF(sep); Py_DECREF(parts);
    if (!j) return NULL;
    PyObject *r = PyUnicode_FromFormat("[%U]", j);
    Py_DECREF(j); return r;
}

static double to_double(PyObject *v) {
    if (v==Py_True)  return 1.0;
    if (v==Py_False) return 0.0;
    if (PyLong_CheckExact(v)) return (double)PyLong_AsLong(v);
    if (PyFloat_CheckExact(v)) return PyFloat_AS_DOUBLE(v);
    if (PyUnicode_Check(v)) {
        const char *s = PyUnicode_AsUTF8(v);
        if (s) return atof(s);
    }
    return 0.0;
}
static long to_long(PyObject *v) {
    if (v==Py_True)  return 1;
    if (v==Py_False) return 0;
    if (PyLong_CheckExact(v)) return PyLong_AsLong(v);
    if (PyFloat_CheckExact(v)) return (long)PyFloat_AS_DOUBLE(v);
    if (PyUnicode_Check(v)) {
        const char *s = PyUnicode_AsUTF8(v);
        if (s) return atol(s);
    }
    return 0;
}

static PyObject *maybe_int(double d) {
    double ip; if (modf(d,&ip)==0.0 && fabs(d)<9e15) return PyLong_FromDouble(d);
    return PyFloat_FromDouble(d);
}

#define IS_INT(v) ((v) && PyLong_CheckExact(v) && (v)!=Py_True && (v)!=Py_False)

static PyObject *op_add(PyObject *a, PyObject *b) {
    if (PyUnicode_Check(a)||PyUnicode_Check(b)) {
        PyObject *sa=mellow_format(a),*sb=mellow_format(b);
        if(!sa||!sb){Py_XDECREF(sa);Py_XDECREF(sb);return NULL;}
        PyObject *r=PyUnicode_Concat(sa,sb); Py_DECREF(sa);Py_DECREF(sb); return r;
    }
    if (PyList_Check(a)&&PyList_Check(b)) return PySequence_Concat(a,b);
    if (IS_INT(a)&&IS_INT(b)) return PyLong_FromLong(PyLong_AsLong(a)+PyLong_AsLong(b));
    return maybe_int(to_double(a)+to_double(b));
}
static PyObject *op_sub(PyObject *a, PyObject *b) {
    if (IS_INT(a)&&IS_INT(b)) return PyLong_FromLong(PyLong_AsLong(a)-PyLong_AsLong(b));
    return maybe_int(to_double(a)-to_double(b));
}
static PyObject *op_mul(PyObject *a, PyObject *b) {
    if (PyUnicode_Check(a)&&IS_INT(b)) return PySequence_Repeat(a,(Py_ssize_t)PyLong_AsLong(b));
    if (IS_INT(a)&&IS_INT(b)) return PyLong_FromLong(PyLong_AsLong(a)*PyLong_AsLong(b));
    return maybe_int(to_double(a)*to_double(b));
}
static PyObject *op_div(PyObject *a, PyObject *b) {
    double db=to_double(b); if(db==0.0) return PyLong_FromLong(0);
    return maybe_int(to_double(a)/db);
}
static PyObject *op_mod(PyObject *a, PyObject *b) {
    if (IS_INT(a)&&IS_INT(b)) {
        long lb=PyLong_AsLong(b); if(!lb) return PyLong_FromLong(0);
        long r = PyLong_AsLong(a) % lb;
        if (r!=0 && (r<0)!=(lb<0)) r+=lb; /* Python-style sign */
        return PyLong_FromLong(r);
    }
    double db=to_double(b); if(db==0.0) return PyFloat_FromDouble(0.0);
    return maybe_int(fmod(to_double(a),db));
}
static PyObject *op_pow(PyObject *a, PyObject *b) {
    return maybe_int(pow(to_double(a),to_double(b)));
}
static PyObject *op_cmp(PyObject *a, PyObject *b, const char *op) {
    int res=0;
    if (strcmp(op,"==")==0) { int r=PyObject_RichCompareBool(a,b,Py_EQ); if(r<0){PyErr_Clear();r=0;} res=r; }
    else if (strcmp(op,"!=")==0) { int r=PyObject_RichCompareBool(a,b,Py_EQ); if(r<0){PyErr_Clear();r=0;} res=!r; }
    else {
        int cop = strcmp(op,"<")==0?Py_LT:strcmp(op,">")==0?Py_GT:strcmp(op,"<=")==0?Py_LE:Py_GE;
        int r=PyObject_RichCompareBool(a,b,cop); if(r<0){PyErr_Clear();r=0;} res=r;
    }
    return res?(Py_INCREF(Py_True),Py_True):(Py_INCREF(Py_False),Py_False);
}

static PyObject *make_func_ref(PyObject *name) {
    PyObject *tag=PyUnicode_FromString("__func__");
    if(!tag) return NULL;
    PyObject *t=PyTuple_Pack(2,tag,name); Py_DECREF(tag); return t;
}
static int is_func_ref(PyObject *v, PyObject **out) {
    if(!v||!PyTuple_Check(v)||PyTuple_GET_SIZE(v)!=2) return 0;
    PyObject *tag=PyTuple_GET_ITEM(v,0);
    if(!PyUnicode_Check(tag)) return 0;
    const char *s=PyUnicode_AsUTF8(tag);
    if(!s||strcmp(s,"__func__")!=0) return 0;
    if(out) *out=PyTuple_GET_ITEM(v,1);
    return 1;
}

/* scope lookup */
static PyObject *scope_get(PyObject **scopes, int ns, PyObject *name) {
    for (int i=ns-1;i>=0;i--) {
        PyObject *v=PyDict_GetItem(scopes[i],name);
        if (v) return v;
    }
    return NULL;
}

/* print to stdout or capture buffer */
static void cvm_print(CVM *vm, const char *s) {
    PySys_WriteStdout("%s\n", s);
}
static void cvm_printn(CVM *vm, const char **parts, int n) {
    for (int i=0;i<n;i++) {
        if (i>0) PySys_WriteStdout(" ");
        PySys_WriteStdout("%s", parts[i]);
    }
    PySys_WriteStdout("\n");
}

/* ================================================================
 * cvm_call1 — call a single Mellow function with args
 *   fn_ref: ("__func__", name) tuple
 *   args[0..argc-1]: arguments (borrowed refs)
 *   Returns new ref to result, or NULL on error.
 * ================================================================ */
