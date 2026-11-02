/* mellowvm_storage.inc — storage, fs and file syscalls for the native VM.
 *
 * Included by mellowvm_module.c before mellowvm_syscalls.inc. Kept separate so
 * the dispatcher in mellowvm_syscalls.inc stays focused on pure stdlib maths.
 * Sandbox semantics mirror src/mellowlang/vm/storage.py.
 */

/* ── storage / fs / file helpers ──────────────────────────────────────
   Path handling mirrors src/mellowlang/vm/storage.py so the native and
   Python engines agree on what a script is allowed to reach.           */

static PyObject *sv_clean(PyObject *value, int lstrip_slash);

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
static PyObject *sv_fs_resolve(CVM *vm, PyObject *path, const char *op) {
    PyObject *raw = sv_clean(path, 0);
    if (!raw) return NULL;
    if (sv_is_blank(PyUnicode_AsUTF8(raw))) {
        Py_DECREF(raw);
        raw = PyUnicode_FromString(".");
        if (!raw) return NULL;
    }
    const char *txt = PyUnicode_AsUTF8(raw);
    if (!txt) { Py_DECREF(raw); return NULL; }

    int project_mode = sv_cfg_bool(vm, "project_mode");
    int unsafe = sv_cfg_bool(vm, "allow_unsafe_fs");

    if (sv_escapes_base(txt) && (project_mode || !unsafe)) {
        Py_DECREF(raw);
        PyErr_SetString(PyExc_RuntimeError, "SANDBOX: fs: \"..\" traversal is blocked");
        return NULL;
    }

    if (sv_os_flag("path.isabs", raw)) {
        if (project_mode) {
            Py_DECREF(raw);
            PyErr_SetString(PyExc_RuntimeError,
                            "SANDBOX: fs: absolute paths are disabled in project mode");
            return NULL;
        }
        if (!unsafe) {
            Py_DECREF(raw);
            PyErr_SetString(PyExc_RuntimeError,
                            "SANDBOX: fs: absolute paths are disabled by default "
                            "(run with --unsafe-fs for dev)");
            return NULL;
        }
        PyObject *res = sv_os("path.abspath", raw, NULL, 0);
        Py_DECREF(raw);
        return res;
    }

    PyObject *root = NULL;
    if (project_mode) {
        PyObject *pr = sv_cfg(vm, "project_root");
        root = (pr && pr != Py_None) ? sv_os("path.abspath", pr, NULL, 0)
                                     : sv_os("getcwd", NULL, NULL, 0);
    } else {
        root = sv_os("getcwd", NULL, NULL, 0);
    }
    PyObject *joined = root ? sv_os("path.join", root, raw, 0) : NULL;
    PyObject *full = joined ? sv_os("path.abspath", joined, NULL, 0) : NULL;
    Py_XDECREF(joined);
    /* The deny hint still needs the caller's text once `raw` is released. */
    char *origin = NULL;
    if (project_mode && txt) {
        size_t txt_len = strlen(txt);
        origin = (char *)malloc(txt_len + 1);
        if (origin) memcpy(origin, txt, txt_len + 1);
    }
    Py_DECREF(raw);
    if (!full) { Py_XDECREF(root); return NULL; }
    if (!project_mode) { Py_DECREF(root); return full; }

    const char *allow_key = strcmp(op, "read") == 0 ? "fs_read_allow" : "fs_write_allow";
    PyObject *allow_cfg = sv_cfg(vm, allow_key);
    PyObject *allow_text = allow_cfg ? PyObject_Str(allow_cfg) : PyUnicode_FromString("");
    if (!allow_text) { Py_DECREF(root); Py_DECREF(full); return NULL; }
    const char *allow_txt = PyUnicode_AsUTF8(allow_text);
    int granted = 0;
    if (allow_txt) {
        const char *cursor = allow_txt;
        while (*cursor && !granted) {
            while (*cursor == ' ' || *cursor == ',') cursor++;
            const char *start = cursor;
            while (*cursor && *cursor != ',') cursor++;
            size_t len = (size_t)(cursor - start);
            while (len > 0 && (start[len - 1] == ' ' || start[len - 1] == '\t')) len--;
            if (len == 0) continue;
            char *entry = (char *)malloc(len + 1);
            if (!entry) break;
            memcpy(entry, start, len);
            entry[len] = '\0';
            for (char *p = entry; *p; p++) if (*p == '\\') *p = '/';
            char *head = entry;
            while (*head == '.' || *head == '/') head++;
            if (sv_allowlist_entry_usable(head)) {
                PyObject *base = root;
                if (*head) {
                    PyObject *rel = PyUnicode_FromString(head);
                    PyObject *joined_base = rel ? sv_os("path.join", root, rel, 0) : NULL;
                    base = joined_base ? sv_os("path.abspath", joined_base, NULL, 0) : NULL;
                    Py_XDECREF(joined_base);
                    Py_XDECREF(rel);
                } else {
                    Py_INCREF(base);
                }
                if (base) {
                    granted = sv_within(base, full) == 1;
                    Py_DECREF(base);
                }
            }
            free(entry);
        }
    }
    Py_DECREF(allow_text);
    if (granted) {
        Py_DECREF(root);
        free(origin);
        return full;
    }

    /* Deny with the same deterministic hint the Python VM produces. */
    const char *source = origin ? origin : "";
    const char *slash = strchr(source, '/');
    size_t need_len = slash ? (size_t)(slash - source) : strlen(source);
    char *need = (char *)malloc(need_len + 1);
    if (!need) {
        Py_DECREF(root);
        Py_DECREF(full);
        free(origin);
        return PyErr_NoMemory();
    }
    memcpy(need, source, need_len);
    need[need_len] = '\0';
    Py_DECREF(root);
    Py_DECREF(full);
    if (!*need) {
        PyErr_Format(PyExc_RuntimeError,
                     "SANDBOX: fs access denied (%s): %s\n"
                     "Hint: add permission in mellow.json: \"fs.%s:.\"", op, source, op);
    } else {
        PyErr_Format(PyExc_RuntimeError,
                     "SANDBOX: fs access denied (%s): %s\n"
                     "Hint: add permission in mellow.json: \"fs.%s:./%s\"", op, source, op, need);
    }
    free(need);
    free(origin);
    return NULL;
}

/* _save_json: temp file in the target folder, then an atomic replace. */
static int sv_save_json(CVM *vm, PyObject *key, PyObject *value) {
    if (!vm->allow_storage) {
        PyErr_SetString(PyExc_RuntimeError, "SANDBOX: storage is disabled");
        return -1;
    }
    PyObject *path = cvm_storage_path(vm, key);
    if (!path) return -1;
    if (!storage_ensure_base(vm)) { Py_DECREF(path); return -1; }

    PyObject *dirpath = sv_os("path.dirname", path, NULL, 0);
    if (dirpath && PyUnicode_GetLength(dirpath) == 0) {
        Py_DECREF(dirpath);
        dirpath = vm->storage_dir;
        Py_INCREF(dirpath);
    }
    if (!dirpath) { Py_DECREF(path); return -1; }

    PyObject *norm_dir = sv_os("path.normpath", dirpath, NULL, 0);
    PyObject *norm_base = sv_os("path.normpath", vm->storage_dir, NULL, 0);
    int same_root = norm_dir && norm_base && PyUnicode_Compare(norm_dir, norm_base) == 0;
    Py_XDECREF(norm_dir);
    Py_XDECREF(norm_base);
    if (!same_root && !sv_os_flag("path.exists", dirpath)) {
        PyObject *msg = PyUnicode_FromFormat("RUNTIME: Folder not found: %U (create it first)",
                                            dirpath);
        Py_DECREF(dirpath);
        Py_DECREF(path);
        if (msg) { PyErr_SetObject(PyExc_RuntimeError, msg); Py_DECREF(msg); }
        return -1;
    }

    PyObject *json_mod = PyImport_ImportModule("json");
    if (!json_mod) { Py_DECREF(dirpath); Py_DECREF(path); return -1; }
    PyObject *dumps = PyObject_GetAttrString(json_mod, "dumps");
    Py_DECREF(json_mod);
    if (!dumps) { Py_DECREF(dirpath); Py_DECREF(path); return -1; }
    PyObject *dump_args = PyTuple_Pack(1, value);
    PyObject *dump_kw = Py_BuildValue("{s:O}", "ensure_ascii", Py_False);
    PyObject *encoded = dump_args ? PyObject_Call(dumps, dump_args, dump_kw) : NULL;
    Py_XDECREF(dump_args);
    Py_XDECREF(dump_kw);
    Py_DECREF(dumps);
    if (!encoded) { Py_DECREF(dirpath); Py_DECREF(path); return -1; }

    PyObject *tempfile_mod = PyImport_ImportModule("tempfile");
    PyObject *mkstemp = tempfile_mod ? PyObject_GetAttrString(tempfile_mod, "mkstemp") : NULL;
    Py_XDECREF(tempfile_mod);
    if (!mkstemp) { Py_DECREF(encoded); Py_DECREF(dirpath); Py_DECREF(path); return -1; }
    PyObject *temp_kw = Py_BuildValue("{s:s,s:s,s:O}",
                                      "prefix", ".mellow_", "suffix", ".tmp", "dir", dirpath);
    PyObject *empty_args = PyTuple_New(0);
    PyObject *temp_pair = (temp_kw && empty_args)
                        ? PyObject_Call(mkstemp, empty_args, temp_kw) : NULL;
    Py_XDECREF(temp_kw);
    Py_XDECREF(empty_args);
    Py_DECREF(mkstemp);
    if (!temp_pair) { Py_DECREF(encoded); Py_DECREF(dirpath); Py_DECREF(path); return -1; }

    PyObject *fd_obj = PyTuple_GetItem(temp_pair, 0);
    PyObject *temp_name = PyTuple_GetItem(temp_pair, 1);
    int wrote = -1;
    if (fd_obj && temp_name) {
        PyObject *os_mod = PyImport_ImportModule("os");
        PyObject *fdopen = os_mod ? PyObject_GetAttrString(os_mod, "fdopen") : NULL;
        Py_XDECREF(os_mod);
        if (fdopen) {
            PyObject *open_args = Py_BuildValue("(ls)", (long)PyLong_AsLong(fd_obj), "w");
            PyObject *open_kw = Py_BuildValue("{s:s}", "encoding", "utf-8");
            PyObject *handle = open_args ? PyObject_Call(fdopen, open_args, open_kw) : NULL;
            Py_XDECREF(open_args);
            Py_XDECREF(open_kw);
            if (handle) {
                PyObject *res = PyObject_CallMethod(handle, "write", "O", encoded);
                PyObject *closed = PyObject_CallMethod(handle, "close", NULL);
                Py_XDECREF(closed);
                Py_DECREF(handle);
                if (res) {
                    Py_DECREF(res);
                    PyObject *move = sv_os("replace", temp_name, path, 0);
                    if (move) { Py_DECREF(move); wrote = 0; }
                }
            }
            Py_DECREF(fdopen);
        }
        if (sv_os_flag("path.exists", temp_name)) {
            PyObject *gone = sv_os("remove", temp_name, NULL, 0);
            if (!gone) PyErr_Clear();
            Py_XDECREF(gone);
        }
    }
    Py_DECREF(temp_pair);
    Py_DECREF(encoded);
    Py_DECREF(dirpath);
    Py_DECREF(path);
    return wrote;
}

/* _load_json: parsed document, or None when the slot is empty. */
static PyObject *sv_load_json(CVM *vm, PyObject *key) {
    if (!vm->allow_storage) {
        PyErr_SetString(PyExc_RuntimeError, "SANDBOX: storage is disabled");
        return NULL;
    }
    PyObject *path = cvm_storage_path(vm, key);
    if (!path) return NULL;
    if (!sv_os_flag("path.exists", path)) {
        Py_DECREF(path);
        Py_INCREF(Py_None);
        return Py_None;
    }
    PyObject *text = sv_read_file(path, "r", 0);
    Py_DECREF(path);
    if (!text) return NULL;
    PyObject *json_mod = PyImport_ImportModule("json");
    if (!json_mod) { Py_DECREF(text); return NULL; }
    PyObject *loaded = PyObject_CallMethod(json_mod, "loads", "O", text);
    Py_DECREF(text);
    Py_DECREF(json_mod);
    return loaded;
}

/* storage_dir(): pick the next storage base, always locked in project mode. */
static PyObject *sv_storage_dir(CVM *vm, PyObject *target) {
    PyObject *raw = sv_clean(target, 0);
    if (!raw) return NULL;
    const char *txt = PyUnicode_AsUTF8(raw);
    if (!txt) { Py_DECREF(raw); return NULL; }

    int project_mode = sv_cfg_bool(vm, "project_mode");
    int unsafe = sv_cfg_bool(vm, "allow_unsafe_fs");
    int is_abs = sv_os_flag("path.isabs", raw);
    PyObject *new_dir;

    if (project_mode) {
        if (is_abs) {
            Py_DECREF(raw);
            PyErr_SetString(PyExc_RuntimeError,
                            "SANDBOX: storage_dir: absolute paths are disabled in project mode. "
                            "Tip: use a sandbox slot name, e.g. storage_dir(\"profile_01\").");
            return NULL;
        }
        if (sv_escapes_base(txt)) {
            Py_DECREF(raw);
            PyErr_SetString(PyExc_RuntimeError,
                            "SANDBOX: storage_dir: \"..\" traversal is blocked in project mode.");
            return NULL;
        }
        PyObject *root_cfg = sv_cfg(vm, "project_root");
        PyObject *root = (root_cfg && root_cfg != Py_None)
                       ? sv_os("path.abspath", root_cfg, NULL, 0)
                       : sv_os("getcwd", NULL, NULL, 0);
        PyObject *sandbox = sv_cfg_path(vm, "sandbox_root", "saves");
        PyObject *base = (root && sandbox) ? sv_os("path.join", root, sandbox, 0) : NULL;
        if (sv_is_blank(txt)) {
            new_dir = base;                        /* ownership moves to new_dir */
        } else {
            new_dir = base ? sv_os("path.join", base, raw, 0) : NULL;
            Py_XDECREF(base);
        }
        Py_XDECREF(root);
        Py_XDECREF(sandbox);
        Py_DECREF(raw);
        if (!new_dir) {
            if (!PyErr_Occurred())
                PyErr_SetString(PyExc_RuntimeError, "RUNTIME: storage_dir: unresolved sandbox root");
            return NULL;
        }
    } else {
        if (is_abs && !unsafe) {
            Py_DECREF(raw);
            PyErr_SetString(PyExc_RuntimeError,
                            "SANDBOX: storage_dir: absolute paths are disabled by default. "
                            "Tip: use a relative path (e.g. \"examples\" or \".\") "
                            "or run with --unsafe-fs.");
            return NULL;
        }
        if (sv_escapes_base(txt) && !unsafe) {
            Py_DECREF(raw);
            PyErr_SetString(PyExc_RuntimeError,
                            "SANDBOX: storage_dir: \"..\" traversal is blocked. "
                            "Tip: choose a folder under the project (e.g. \"saves\") "
                            "or run with --unsafe-fs.");
            return NULL;
        }
        new_dir = raw;                             /* keep it alive through the setter */
    }

    sv_set_storage_dir(vm, new_dir);
    Py_DECREF(new_dir);
    Py_INCREF(Py_True);
    return Py_True;
}

/* Return NULL with `*handled` set when the name belongs to this layer. */
static PyObject *cvm_storage_syscall(const char *sn, PyObject **sa, long argc,
                                     CVM *vm, int *handled)
{
#define A0 (argc>0?sa[0]:Py_None)
#define A1 (argc>1?sa[1]:Py_None)
#define A2 (argc>2?sa[2]:Py_None)
#define A3 (argc>3?sa[3]:Py_None)

    *handled = 0;

    /* ── std.storage ── */
    if (strncmp(sn,"std.storage.",12)==0) {
        const char *op = sn+12;
        *handled = 1;

        if (strcmp(op,"dir")==0)
            return sv_storage_dir(vm, argc>0?A0:Py_None);

        if (strcmp(op,"pwd")==0) {
            Py_INCREF(vm->storage_dir);
            return vm->storage_dir;
        }

        if (strcmp(op,"info")==0) {
            PyObject *abs = sv_os("path.abspath", vm->storage_dir, NULL, 0);
            if (!abs) {
                PyErr_Clear();
                abs = vm->storage_dir;
                Py_INCREF(abs);
            }
            PyObject *info = PyDict_New();
            if (!info) { Py_DECREF(abs); return NULL; }
            if (PyDict_SetItemString(info,"storage_dir",vm->storage_dir)<0 ||
                PyDict_SetItemString(info,"storage_abs",abs)<0) {
                Py_DECREF(info); Py_DECREF(abs); return NULL;
            }
            Py_DECREF(abs);
            return info;
        }

        if (strcmp(op,"save")==0) {
            if (argc<2) {
                PyErr_SetString(PyExc_RuntimeError, "RUNTIME: save_data expects 2 args");
                return NULL;
            }
            PyObject *key=A0, *value=A1;
            /* save_data accepts (key, value) or (value, key), like the Python VM */
            if (!PyUnicode_Check(key) && PyUnicode_Check(value)) {
                PyObject *swap=key; key=value; value=swap;
            }
            if (sv_save_json(vm, key, value)!=0) return NULL;
            Py_INCREF(Py_True); return Py_True;
        }

        if (strcmp(op,"load")==0) {
            if (argc<1) {
                PyErr_SetString(PyExc_RuntimeError, "RUNTIME: load_data expects 1 arg");
                return NULL;
            }
            return sv_load_json(vm, A0);
        }

        if (strcmp(op,"mkdir")==0) {
            PyObject *full = sv_fs_path(vm, argc>0?A0:Py_None);
            if (!full) return NULL;
            PyObject *made = sv_os("makedirs", full, NULL, 1);
            Py_DECREF(full);
            if (!made) return NULL;
            Py_DECREF(made);
            Py_INCREF(Py_True); return Py_True;
        }
        *handled = 0;
    }

    /* ── std.fs: host filesystem, allowlisted in project mode ── */
    if (strncmp(sn,"std.fs.",7)==0) {
        const char *op = sn+7;
        *handled = 1;

        if (strcmp(op,"pwd")==0) {
            if (sv_cfg_bool(vm,"project_mode")) {
                PyObject *pr = sv_cfg(vm, "project_root");
                if (pr && pr != Py_None) return PyObject_Str(pr);
            }
            return sv_os("getcwd", NULL, NULL, 0);
        }

        int read_op = (strcmp(op,"read")==0 || strcmp(op,"exists")==0);
        PyObject *full = sv_fs_resolve(vm, argc>0?A0:Py_None, read_op?"read":"write");
        if (!full) return NULL;

        if (strcmp(op,"mkdir")==0) {
            PyObject *made = sv_os("makedirs", full, NULL, 1);
            Py_DECREF(full);
            if (!made) return NULL;
            Py_DECREF(made);
            Py_INCREF(Py_True); return Py_True;
        }
        if (strcmp(op,"exists")==0) {
            PyObject *res = PyBool_FromLong(sv_os_flag("path.exists", full));
            Py_DECREF(full);
            return res;
        }
        if (strcmp(op,"delete")==0) {
            int existed = sv_os_flag("path.exists", full);
            PyObject *res = NULL;
            if (existed) {
                PyObject *gone = sv_os("remove", full, NULL, 0);
                if (gone) { Py_DECREF(gone); res = PyBool_FromLong(1); }
            } else {
                res = PyBool_FromLong(0);
            }
            Py_DECREF(full);
            return res;
        }
        if (strcmp(op,"read")==0) {
            const char *mode = (argc>1 && PyUnicode_Check(A1)) ? PyUnicode_AsUTF8(A1) : NULL;
            if (!mode || !*mode) mode = "r";
            PyObject *data = sv_read_file(full, mode, strchr(mode,'b')!=NULL);
            Py_DECREF(full);
            return data;
        }
        if (strcmp(op,"write")==0 || strcmp(op,"append")==0) {
            int is_append = (op[0]=='a');
            const char *mode = (argc>2 && PyUnicode_Check(A2)) ? PyUnicode_AsUTF8(A2) : NULL;
            if (!mode || !*mode) mode = is_append ? "a" : "w";
            int binary = strchr(mode,'b')!=NULL;
            if (is_append && !strchr(mode,'a')) {
                mode = binary ? "ab" : "a";
                binary = 0;
            }
            /* Write targets are created on demand, matching the Python VM. */
            PyObject *parent_dir = sv_os("path.dirname", full, NULL, 0);
            if (parent_dir && PyUnicode_GetLength(parent_dir)>0 &&
                !sv_os_flag("path.exists", parent_dir)) {
                PyObject *made = sv_os("makedirs", parent_dir, NULL, 1);
                Py_XDECREF(made);
            }
            Py_XDECREF(parent_dir);
            PyObject *blank = PyUnicode_FromString("");
            int rc = sv_write_file(full, argc>1?A1:blank, mode, binary);
            Py_DECREF(blank);
            Py_DECREF(full);
            if (rc!=0) return NULL;
            Py_INCREF(Py_True); return Py_True;
        }
        Py_DECREF(full);
        *handled = 0;
    }

    /* ── std.file: sandboxed file api under the storage base ── */
    if (strncmp(sn,"std.file.",9)==0) {
        const char *op = sn+9;
        *handled = 1;
        PyObject *full = sv_fs_path(vm, argc>0?A0:Py_None);
        if (!full) return NULL;

        if (strcmp(op,"exists")==0) {
            PyObject *res = PyBool_FromLong(sv_os_flag("path.exists", full));
            Py_DECREF(full);
            return res;
        }
        if (strcmp(op,"delete")==0) {
            PyObject *res = NULL;
            if (sv_os_flag("path.exists", full)) {
                PyObject *gone = sv_os("remove", full, NULL, 0);
                if (gone) { Py_DECREF(gone); res = PyBool_FromLong(1); }
            } else {
                res = PyBool_FromLong(0);
            }
            Py_DECREF(full);
            return res;
        }
        if (strcmp(op,"read")==0) {
            const char *mode; int binary;
            sv_pick_mode(argc>1?A1:Py_None, "r", "rb", &mode, &binary);
            PyObject *data = sv_read_file(full, mode, binary);
            Py_DECREF(full);
            return data;
        }

        int is_append = (strcmp(op,"append")==0);
        if (strcmp(op,"write")==0 || is_append) {
            PyObject *base_dir = sv_os("path.normpath", vm->storage_dir, NULL, 0);
            if (base_dir && !sv_os_flag("path.isdir", base_dir)) {
                PyObject *made = sv_os("makedirs", base_dir, NULL, 1);
                Py_XDECREF(made);
            }
            Py_XDECREF(base_dir);
            const char *mode; int binary;
            sv_pick_mode(argc>2?A2:Py_None, is_append?"a":"w", is_append?"ab":"wb", &mode, &binary);
            PyObject *blank = PyUnicode_FromString("");
            int rc = sv_write_file(full, argc>1?A1:blank, mode, binary);
            Py_DECREF(blank);
            Py_DECREF(full);
            if (rc!=0) return NULL;
            Py_INCREF(Py_True); return Py_True;
        }
        Py_DECREF(full);
        *handled = 0;
    }

    return NULL;
}

#undef A0
#undef A1
#undef A2
#undef A3
