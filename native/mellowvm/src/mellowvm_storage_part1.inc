static PyObject *sv_cfg(CVM *vm, const char *key) {
    if (!vm->config || !PyDict_Check(vm->config)) return NULL;
    return PyDict_GetItemString(vm->config, key);   /* borrowed */
}

static int sv_cfg_bool(CVM *vm, const char *key) {
    PyObject *v = sv_cfg(vm, key);
    return v ? mellow_truthy(v) : 0;
}

/* Config string with the same trimming the Python VM applies; blank → fallback. */
static PyObject *sv_cfg_path(CVM *vm, const char *key, const char *fallback) {
    PyObject *v = sv_cfg(vm, key);
    if (!v || v == Py_None) return PyUnicode_FromString(fallback);
    PyObject *cleaned = sv_clean(v, 0);
    if (!cleaned) return NULL;
    const char *txt = PyUnicode_AsUTF8(cleaned);
    if (!txt || !*txt) { Py_DECREF(cleaned); return PyUnicode_FromString(fallback); }
    return cleaned;
}

/* Call an os-module function; `fn` may be dotted, e.g. "path.abspath". */
static PyObject *sv_os(const char *fn, PyObject *a, PyObject *b, int exist_ok) {
    PyObject *os_mod = PyImport_ImportModule("os");
    if (!os_mod) return NULL;

    PyObject *owner = os_mod, *owner_new = NULL, *result = NULL;
    const char *leaf = fn;
    const char *dot = strrchr(fn, '.');
    if (dot) {
        size_t head_len = (size_t)(dot - fn);
        char *head = (char *)malloc(head_len + 1);
        if (!head) { Py_DECREF(os_mod); return NULL; }
        memcpy(head, fn, head_len);
        head[head_len] = '\0';
        owner_new = PyObject_GetAttrString(os_mod, head);
        free(head);
        if (!owner_new) { Py_DECREF(os_mod); return NULL; }
        owner = owner_new;
        leaf = dot + 1;
    }

    PyObject *func = PyObject_GetAttrString(owner, leaf);
    if (func) {
        PyObject *args;
        if (b)      args = PyTuple_Pack(2, a, b);
        else if (a) args = PyTuple_Pack(1, a);
        else        args = PyTuple_New(0);
        PyObject *kw = exist_ok ? Py_BuildValue("{s:O}", "exist_ok", Py_True) : NULL;
        if (args) result = PyObject_Call(func, args, kw);
        Py_XDECREF(args);
        Py_XDECREF(kw);
        Py_DECREF(func);
    }
    Py_XDECREF(owner_new);
    Py_DECREF(os_mod);
    return result;
}

/* 1 when `full` is `base` or nested below it, 0 when outside, -1 on error. */
static int sv_within(PyObject *base_abs, PyObject *full_abs) {
    int cmp = PyUnicode_Compare(base_abs, full_abs);
    if (cmp == 0) return 1;
    if (cmp < 0 && PyErr_Occurred()) return -1;

    PyObject *os_mod = PyImport_ImportModule("os");
    if (!os_mod) return -1;
    PyObject *sep = PyObject_GetAttrString(os_mod, "sep");
    Py_DECREF(os_mod);
    if (!sep) return -1;
    const char *sep_utf8 = PyUnicode_AsUTF8(sep);
    PyObject *prefix = PyUnicode_FromFormat("%U%c", base_abs, sep_utf8 ? sep_utf8[0] : '/');
    Py_DECREF(sep);
    if (!prefix) return -1;
    PyObject *hit = PyObject_CallMethod(full_abs, "startswith", "O", prefix);
    Py_DECREF(prefix);
    if (!hit) return -1;
    int ok = PyObject_IsTrue(hit);
    Py_DECREF(hit);
    return ok;
}

/* os.path predicate as a boolean; a failed lookup reads as false. */
static int sv_os_flag(const char *fn, PyObject *path) {
    PyObject *res = sv_os(fn, path, NULL, 0);
    if (!res) { PyErr_Clear(); return 0; }
    int ok = PyObject_IsTrue(res);
    Py_DECREF(res);
    return ok;
}

/* str(value) with whitespace and quotes trimmed, then '/' separators. */
static PyObject *sv_clean(PyObject *value, int lstrip_slash) {
    PyObject *s = (value && value != Py_None) ? mellow_format(value) : PyUnicode_FromString("");
    if (!s) return NULL;
    PyObject *r = PyObject_CallMethod(s, "strip", NULL);                  Py_DECREF(s);
    if (!r) return NULL;
    PyObject *t = PyObject_CallMethod(r, "strip", "s", "\"");             Py_DECREF(r);
    if (!t) return NULL;
    r = PyObject_CallMethod(t, "strip", "s", "'");                        Py_DECREF(t);
    if (!r) return NULL;
    t = PyObject_CallMethod(r, "replace", "ss", "\\", "/");               Py_DECREF(r);
    if (!t || !lstrip_slash) return t;
    r = PyObject_CallMethod(t, "lstrip", "s", "/");                       Py_DECREF(t);
    return r;
}

static int sv_is_blank(const char *txt) {
    return !txt || !*txt || strcmp(txt, ".") == 0;
}

static int sv_escapes_base(const char *txt) {
    return txt && (strcmp(txt, "..") == 0 || strncmp(txt, "../", 3) == 0 ||
                   strncmp(txt, "..\\", 3) == 0);
}

/* io.open(path, mode) — text modes decode UTF-8 like the Python VM does. */
static PyObject *sv_open(PyObject *path, const char *mode, int binary) {
    PyObject *io_mod = PyImport_ImportModule("io");
    if (!io_mod) return NULL;
    PyObject *open_fn = PyObject_GetAttrString(io_mod, "open");
    Py_DECREF(io_mod);
    if (!open_fn) return NULL;
    PyObject *args = Py_BuildValue("(Os)", path, mode);
    PyObject *kw = binary ? NULL : Py_BuildValue("{s:s}", "encoding", "utf-8");
    PyObject *handle = args ? PyObject_Call(open_fn, args, kw) : NULL;
    Py_XDECREF(args);
    Py_XDECREF(kw);
    Py_DECREF(open_fn);
    return handle;
}

static PyObject *sv_read_file(PyObject *path, const char *mode, int binary) {
    PyObject *handle = sv_open(path, mode, binary);
    if (!handle) return NULL;
    PyObject *data = PyObject_CallMethod(handle, "read", NULL);
    PyObject *closed = PyObject_CallMethod(handle, "close", NULL);
    Py_XDECREF(closed);
    Py_DECREF(handle);
    return data;
}

static int sv_write_file(PyObject *path, PyObject *value, const char *mode, int binary) {
    PyObject *payload;
    if (binary && (PyBytes_Check(value) || PyByteArray_Check(value))) {
        Py_INCREF(value);
        payload = value;
    } else if (!binary && PyUnicode_Check(value)) {
        Py_INCREF(value);
        payload = value;
    } else {
        PyObject *text = PyObject_Str(value);
        if (!text) return -1;
        payload = binary ? PyUnicode_AsUTF8String(text) : text;
        if (binary) Py_DECREF(text);
        if (!payload) return -1;
    }
    PyObject *handle = sv_open(path, mode, binary);
    if (!handle) { Py_DECREF(payload); return -1; }
    PyObject *written = PyObject_CallMethod(handle, "write", "O", payload);
    Py_DECREF(payload);
    PyObject *closed = PyObject_CallMethod(handle, "close", NULL);
    Py_XDECREF(closed);
    Py_DECREF(handle);
    if (!written) return -1;
    Py_DECREF(written);
    return 0;
}

/* One of the two modes an api understands; anything else takes the text mode. */
static void sv_pick_mode(PyObject *value, const char *text_mode, const char *binary_mode,
                         const char **out_mode, int *out_binary)
{
    const char *raw = (value && PyUnicode_Check(value)) ? PyUnicode_AsUTF8(value) : NULL;
    *out_mode = (raw && strcmp(raw, binary_mode) == 0) ? binary_mode : text_mode;
    *out_binary = strcmp(*out_mode, binary_mode) == 0;
}

/* Move the run's storage base; the Python VM writes the same key back to config. */
static void sv_set_storage_dir(CVM *vm, PyObject *new_dir) {
    Py_INCREF(new_dir);
    vm->storage_dir = new_dir;   /* run() keeps the original reference alive */
    if (vm->config && PyDict_Check(vm->config))
        PyDict_SetItemString(vm->config, "storage_dir", new_dir);
}

/* _safe_fs_path: join under the storage base without forcing a .json suffix. */
static PyObject *sv_fs_path(CVM *vm, PyObject *sub) {
    PyObject *raw = sv_clean(sub, 0);
    if (!raw) return NULL;
    const char *txt = PyUnicode_AsUTF8(raw);
    if (!txt) { Py_DECREF(raw); return NULL; }
    if (storage_name_unsafe(txt) || sv_escapes_base(txt)) {
        Py_DECREF(raw);
        PyErr_SetString(PyExc_RuntimeError, "SANDBOX: invalid file path (path traversal blocked)");
        return NULL;
    }
    PyObject *full;
    if (sv_is_blank(txt)) {
        full = sv_os("path.normpath", vm->storage_dir, NULL, 0);
    } else {
        PyObject *joined = sv_os("path.join", vm->storage_dir, raw, 0);
        full = joined ? sv_os("path.normpath", joined, NULL, 0) : NULL;
        Py_XDECREF(joined);
    }
    Py_DECREF(raw);
    if (!full) return NULL;

    PyObject *base_abs = sv_os("path.abspath", vm->storage_dir, NULL, 0);
    PyObject *full_abs = sv_os("path.abspath", full, NULL, 0);
    int inside = (base_abs && full_abs) ? sv_within(base_abs, full_abs) : -1;
    Py_XDECREF(base_abs);
    Py_XDECREF(full_abs);
    if (inside != 1) {
        Py_DECREF(full);
        PyErr_SetString(PyExc_RuntimeError, "SANDBOX: invalid file path (path traversal blocked)");
        return NULL;
    }
    return full;
}

/* One allowlist entry: '/' separators, absolute roots ignored, './' prefix dropped. */
static int sv_allowlist_entry_usable(const char *entry) {
    return entry[0] != '/' && !(entry[0] && entry[1] == ':');
}

/* _fs_resolve: host path, deny-by-default allowlist while in project mode. */
