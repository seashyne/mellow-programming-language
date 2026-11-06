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
