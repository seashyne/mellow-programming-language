    /* ── std.time ── */
    if (strncmp(sn,"std.time.",9)==0) {
        const char *op=sn+9;
        PyObject *time_mod=PyImport_ImportModule("time");
        if(!time_mod){PyErr_Clear(); return PyFloat_FromDouble(0.0);}
        PyObject *r=NULL;
        if (strcmp(op,"unix")==0||strcmp(op,"ms")==0) {
            PyObject *t=PyObject_CallMethod(time_mod,"time",NULL);
            if(!t){Py_DECREF(time_mod);return PyFloat_FromDouble(0.0);}
            if(strcmp(op,"ms")==0){r=PyLong_FromDouble(PyFloat_AS_DOUBLE(t)*1000.0);}
            else{r=t;t=NULL;}
            Py_XDECREF(t);
        } else if (strcmp(op,"now")==0) {
            PyObject *t=PyObject_CallMethod(time_mod,"perf_counter",NULL);
            r=t?t:PyFloat_FromDouble(0.0);
        } else {
            r=PyFloat_FromDouble(0.0);
        }
        Py_DECREF(time_mod); return r;
    } /* std.time */

    /* ── std.assert ── */
    if (strncmp(sn,"std.assert.",11)==0) {
        const char *op=sn+11;
        if (strcmp(op,"check")==0 && argc>=1) {
            if(!mellow_truthy(A0)){
                const char *msg=argc>=2&&PyUnicode_Check(A1)?PyUnicode_AsUTF8(A1):"assertion failed";
                PyErr_SetString(PyExc_AssertionError, msg);
                return NULL;
            }
            Py_INCREF(Py_True); return Py_True;
        }
        if (strcmp(op,"eq")==0 && argc>=2) {
            int eq=PyObject_RichCompareBool(A0,A1,Py_EQ); if(eq<0){PyErr_Clear();eq=0;}
            if(!eq){
                const char *msg=argc>=3&&PyUnicode_Check(A2)?PyUnicode_AsUTF8(A2):"assert.eq failed";
                PyErr_SetString(PyExc_AssertionError, msg);
                return NULL;
            }
            Py_INCREF(Py_True); return Py_True;
        }
        if (strcmp(op,"ne")==0 && argc>=2) {
            int eq=PyObject_RichCompareBool(A0,A1,Py_EQ); if(eq<0){PyErr_Clear();eq=0;}
            if(eq){
                const char *msg=argc>=3&&PyUnicode_Check(A2)?PyUnicode_AsUTF8(A2):"assert.ne failed";
                PyErr_SetString(PyExc_AssertionError, msg);
                return NULL;
            }
            Py_INCREF(Py_True); return Py_True;
        }
    }

    /* ── misc ── */
    if (strcmp(sn,"std.len")==0 && argc>=1) {
        Py_ssize_t n;
        if(PyList_Check(A0))n=PyList_GET_SIZE(A0);
        else if(PyDict_Check(A0))n=PyDict_Size(A0);
        else if(PyUnicode_Check(A0))n=PyUnicode_GET_LENGTH(A0);
        else n=0;
        return PyLong_FromSsize_t(n);
    }
    if (strcmp(sn,"sys.get")==0 && argc>=1) { Py_INCREF(Py_None); return Py_None; }
    if (strcmp(sn,"std.event.emit")==0)      { Py_INCREF(Py_None); return Py_None; }

    /* std.json */
    if (strcmp(sn,"std.json.encode")==0 && argc>=1) {
        PyObject *json=PyImport_ImportModule("json"); if(!json) return NULL;
        PyObject *r=PyObject_CallMethod(json,"dumps","O",A0); Py_DECREF(json); return r;
    }
    if (strcmp(sn,"std.json.decode")==0 && argc>=1) {
        PyObject *json=PyImport_ImportModule("json"); if(!json) return NULL;
        PyObject *s=mellow_format(A0); if(!s){Py_DECREF(json);return NULL;}
        PyObject *r=PyObject_CallMethod(json,"loads","O",s); Py_DECREF(s); Py_DECREF(json); return r;
    }

    /* std.data bounded in-memory transforms */
    if (strcmp(sn,"std.data.project")==0 && argc>=2) {
        if (!PyList_Check(A0) || !PyList_Check(A1)) {
            PyErr_SetString(PyExc_RuntimeError, "RUNTIME: data.project expects rows and field-name list");
            return NULL;
        }
        Py_ssize_t row_count=PyList_GET_SIZE(A0), field_count=PyList_GET_SIZE(A1);
        PyObject *names=PyList_New(field_count);
        if(!names) return NULL;
        for(Py_ssize_t j=0;j<field_count;j++) {
            PyObject *name=PyObject_Str(PyList_GET_ITEM(A1,j));
            if(!name){Py_DECREF(names);return NULL;}
            PyList_SET_ITEM(names,j,name);
        }
        PyObject *result=PyList_New(0);
        if(!result){Py_DECREF(names);return NULL;}
        for(Py_ssize_t i=0;i<row_count;i++) {
            PyObject *row=PyList_GET_ITEM(A0,i);
            if(!PyDict_Check(row)) continue;
            PyObject *projected=PyDict_New();
            if(!projected){Py_DECREF(names);Py_DECREF(result);return NULL;}
            for(Py_ssize_t j=0;j<field_count;j++) {
                PyObject *name=PyList_GET_ITEM(names,j);
                PyObject *value=PyDict_GetItemWithError(row,name);
                if(!value && PyErr_Occurred()){Py_DECREF(projected);Py_DECREF(names);Py_DECREF(result);return NULL;}
                if(!value) value=Py_None;
                if(PyDict_SetItem(projected,name,value)<0){Py_DECREF(projected);Py_DECREF(names);Py_DECREF(result);return NULL;}
            }
            if(PyList_Append(result,projected)<0){Py_DECREF(projected);Py_DECREF(names);Py_DECREF(result);return NULL;}
            Py_DECREF(projected);
        }
        Py_DECREF(names);
        return result;
    }
    if (strcmp(sn,"std.data.where")==0 && argc>=4) {
        if (!PyList_Check(A0)) {
            PyErr_SetString(PyExc_RuntimeError, "RUNTIME: data.where expects a row list");
            return NULL;
        }
        PyObject *key=PyObject_Str(A1), *op_obj=PyObject_Str(A2);
        if(!key||!op_obj){Py_XDECREF(key);Py_XDECREF(op_obj);return NULL;}
        const char *op=PyUnicode_AsUTF8(op_obj);
        if(!op){Py_DECREF(key);Py_DECREF(op_obj);return NULL;}
        PyObject *result=PyList_New(0);
        if(!result){Py_DECREF(key);Py_DECREF(op_obj);return NULL;}
        Py_ssize_t row_count=PyList_GET_SIZE(A0);
        for(Py_ssize_t i=0;i<row_count;i++) {
            PyObject *row=PyList_GET_ITEM(A0,i);
            if(!PyDict_Check(row)) continue;
            PyObject *actual=PyDict_GetItemWithError(row,key);
            if(!actual && PyErr_Occurred()){Py_DECREF(result);Py_DECREF(key);Py_DECREF(op_obj);return NULL;}
            if(!actual) actual=Py_None;
            int matched=data_compare(actual,op,A3);
            if(matched<0){Py_DECREF(result);Py_DECREF(key);Py_DECREF(op_obj);return NULL;}
            if(matched && PyList_Append(result,row)<0){Py_DECREF(result);Py_DECREF(key);Py_DECREF(op_obj);return NULL;}
        }
        Py_DECREF(key); Py_DECREF(op_obj);
        return result;
    }
    if (strcmp(sn,"std.data.sum")==0 && argc>=2) {
        if (!PyList_Check(A0)) {
            PyErr_SetString(PyExc_RuntimeError, "RUNTIME: data.sum expects a row list");
            return NULL;
        }
        PyObject *key=PyObject_Str(A1);
        PyObject *total=PyLong_FromLong(0);
        if(!key||!total){Py_XDECREF(key);Py_XDECREF(total);return NULL;}
        Py_ssize_t row_count=PyList_GET_SIZE(A0);
        for(Py_ssize_t i=0;i<row_count;i++) {
            PyObject *row=PyList_GET_ITEM(A0,i);
            if(!PyDict_Check(row)) continue;
            PyObject *value=PyDict_GetItemWithError(row,key);
            if(!value && PyErr_Occurred()){Py_DECREF(key);Py_DECREF(total);return NULL;}
            if(!value) continue;
            PyObject *next=PyNumber_Add(total,value);
            if(!next){Py_DECREF(key);Py_DECREF(total);return NULL;}
            Py_DECREF(total);
            total=next;
        }
        Py_DECREF(key);
        return total;
    }

    /* Storage, fs and file live in their own unit; see mellowvm_storage.inc. */
    {
        int storage_handled = 0;
        PyObject *storage_result = cvm_storage_syscall(sn, sa, argc, parent_vm, &storage_handled);
        if (storage_handled) return storage_result;
    }

    /* Stateful/optional stdlib services are delegated to the per-run host. */
    if (parent_vm->host && parent_vm->host != Py_None) {
        PyObject *arg_list = PyList_New(argc);
        if (!arg_list) return NULL;
        for (long i=0; i<argc; i++) {
            Py_INCREF(sa[i]);
            PyList_SET_ITEM(arg_list, i, sa[i]);
        }
        PyObject *result = PyObject_CallMethod(parent_vm->host, "call", "sO", sn, arg_list);
        Py_DECREF(arg_list);
        return result;
    }

    /* Fallthrough: unknown syscall */
    PyErr_Format(PyExc_RuntimeError, "RUNTIME: unknown syscall '%s'", sn);
    return NULL;

#undef A0
#undef A1
#undef A2
#undef A3
#undef STR0
#undef STR1
}
