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
