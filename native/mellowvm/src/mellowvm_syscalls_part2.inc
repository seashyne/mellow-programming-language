    /* ── std.list ── */
    if (strncmp(sn,"std.list.",9)==0) {
        const char *op = sn+9;

        if (strcmp(op,"push")==0 && argc>=2) {
            /* returns list after append */
            if (PyList_Check(A0)) PyList_Append(A0, A1);
            Py_INCREF(A0); return A0;
        }
        if (strcmp(op,"pop")==0 && argc>=1) {
            if (PyList_Check(A0) && PyList_GET_SIZE(A0)>0) {
                Py_ssize_t last = PyList_GET_SIZE(A0)-1;
                PyObject *r = PyList_GET_ITEM(A0, last);
                Py_INCREF(r);
                PyList_SetSlice(A0, last, last+1, NULL);
                return r;
            }
            Py_INCREF(Py_None); return Py_None;
        }
        if (strcmp(op,"len")==0 && argc>=1) {
            Py_ssize_t n = PyList_Check(A0)?PyList_GET_SIZE(A0):0;
            return PyLong_FromSsize_t(n);
        }
        if (strcmp(op,"has")==0 && argc>=2) {
            int found = 0;
            if (PyList_Check(A0)) {
                Py_ssize_t n=PyList_GET_SIZE(A0);
                for(Py_ssize_t i=0;i<n;i++) {
                    int eq=PyObject_RichCompareBool(PyList_GET_ITEM(A0,i),A1,Py_EQ);
                    if(eq>0){found=1;break;} if(eq<0)PyErr_Clear();
                }
            }
            return found?(Py_INCREF(Py_True),Py_True):(Py_INCREF(Py_False),Py_False);
        }
        if (strcmp(op,"insert")==0 && argc>=3) {
            if (PyList_Check(A0)) {
                Py_ssize_t idx = to_long(A1);
                Py_ssize_t n = PyList_GET_SIZE(A0);
                if (idx<0) idx+=n; if(idx<0)idx=0; if(idx>n)idx=n;
                PyList_Insert(A0, idx, A2);
            }
            Py_INCREF(A0); return A0;
        }
        if (strcmp(op,"remove")==0 && argc>=2) {
            if (PyList_Check(A0)) {
                Py_ssize_t n=PyList_GET_SIZE(A0);
                for(Py_ssize_t i=0;i<n;i++) {
                    int eq=PyObject_RichCompareBool(PyList_GET_ITEM(A0,i),A1,Py_EQ);
                    if(eq>0){PyList_SetSlice(A0,i,i+1,NULL);break;}
                    if(eq<0)PyErr_Clear();
                }
            }
            Py_INCREF(A0); return A0;
        }
        if (strcmp(op,"count")==0 && argc>=2) {
            long cnt=0;
            if (PyList_Check(A0)) {
                Py_ssize_t n=PyList_GET_SIZE(A0);
                for(Py_ssize_t i=0;i<n;i++){
                    int eq=PyObject_RichCompareBool(PyList_GET_ITEM(A0,i),A1,Py_EQ);
                    if(eq>0)cnt++; if(eq<0)PyErr_Clear();
                }
            }
            return PyLong_FromLong(cnt);
        }
        if (strcmp(op,"find")==0 && argc>=2) {
            long idx=-1;
            if (PyList_Check(A0)) {
                Py_ssize_t n=PyList_GET_SIZE(A0);
                for(Py_ssize_t i=0;i<n;i++){
                    int eq=PyObject_RichCompareBool(PyList_GET_ITEM(A0,i),A1,Py_EQ);
                    if(eq>0){idx=(long)i;break;} if(eq<0)PyErr_Clear();
                }
            }
            return PyLong_FromLong(idx);
        }
        if (strcmp(op,"slice")==0 && argc>=2) {
            if (!PyList_Check(A0)) { Py_INCREF(Py_None); return Py_None; }
            Py_ssize_t n=PyList_GET_SIZE(A0);
            Py_ssize_t start=to_long(A1);
            Py_ssize_t stop = argc>=3&&A2!=Py_None ? to_long(A2) : n;
            if(start<0)start+=n; if(stop<0)stop+=n;
            if(start<0)start=0; if(stop>n)stop=n;
            PyObject *r=PyList_New(stop>start?stop-start:0);
            if(!r) return NULL;
            for(Py_ssize_t i=start;i<stop;i++){
                Py_INCREF(PyList_GET_ITEM(A0,i));
                PyList_SET_ITEM(r,i-start,PyList_GET_ITEM(A0,i));
            }
            return r;
        }
        if (strcmp(op,"reverse")==0 && argc>=1) {
            if (!PyList_Check(A0)) { Py_INCREF(A0); return A0; }
            Py_ssize_t n=PyList_GET_SIZE(A0);
            PyObject *r=PyList_New(n);
            if(!r) return NULL;
            for(Py_ssize_t i=0;i<n;i++){
                Py_INCREF(PyList_GET_ITEM(A0,n-1-i));
                PyList_SET_ITEM(r,i,PyList_GET_ITEM(A0,n-1-i));
            }
            return r;
        }
        if (strcmp(op,"reversed")==0 && argc>=1) {
            if (!PyList_Check(A0)) { Py_INCREF(A0); return A0; }
            Py_ssize_t n=PyList_GET_SIZE(A0);
            PyObject *r=PyList_New(n);
            if(!r) return NULL;
            for(Py_ssize_t i=0;i<n;i++){
                Py_INCREF(PyList_GET_ITEM(A0,n-1-i));
                PyList_SET_ITEM(r,i,PyList_GET_ITEM(A0,n-1-i));
            }
            return r;
        }
        if (strcmp(op,"sort")==0 && argc>=1) {
            if (!PyList_Check(A0)) { Py_INCREF(A0); return A0; }
            /* Sort a copy */
            PyObject *copy = PyList_GetSlice(A0, 0, PyList_GET_SIZE(A0));
            if (!copy) return NULL;
            if (PyList_Sort(copy)<0) { Py_DECREF(copy); return NULL; }
            return copy;
        }
        if (strcmp(op,"sorted")==0 && argc>=1) {
            if (!PyList_Check(A0)) { Py_INCREF(A0); return A0; }
            PyObject *copy = PyList_GetSlice(A0, 0, PyList_GET_SIZE(A0));
            if (!copy) return NULL;
            if (PyList_Sort(copy)<0) { Py_DECREF(copy); return NULL; }
            return copy;
        }
        if (strcmp(op,"any")==0 && argc>=1) {
            int found=0;
            if (PyList_Check(A0)) {
                Py_ssize_t n=PyList_GET_SIZE(A0);
                for(Py_ssize_t i=0;i<n;i++) if(mellow_truthy(PyList_GET_ITEM(A0,i))){found=1;break;}
            }
            return found?(Py_INCREF(Py_True),Py_True):(Py_INCREF(Py_False),Py_False);
        }
        if (strcmp(op,"all")==0 && argc>=1) {
            int all=1;
            if (PyList_Check(A0)) {
                Py_ssize_t n=PyList_GET_SIZE(A0);
                for(Py_ssize_t i=0;i<n;i++) if(!mellow_truthy(PyList_GET_ITEM(A0,i))){all=0;break;}
            }
            return all?(Py_INCREF(Py_True),Py_True):(Py_INCREF(Py_False),Py_False);
        }
        if (strcmp(op,"enumerate")==0 && argc>=1) {
            if (!PyList_Check(A0)) {
                PyObject *r=PyList_New(0); if(!r) return NULL; return r;
            }
            Py_ssize_t n=PyList_GET_SIZE(A0);
            PyObject *r=PyList_New(n); if(!r) return NULL;
            for(Py_ssize_t i=0;i<n;i++){
                PyObject *pair=PyList_New(2); if(!pair){Py_DECREF(r);return NULL;}
                PyObject *idx=PyLong_FromSsize_t(i);
                Py_INCREF(PyList_GET_ITEM(A0,i));
                PyList_SET_ITEM(pair,0,idx);
                PyList_SET_ITEM(pair,1,PyList_GET_ITEM(A0,i));
                PyList_SET_ITEM(r,i,pair);
            }
            return r;
        }
        if (strcmp(op,"zip")==0 && argc>=2) {
            Py_ssize_t n=PyList_Check(A0)?PyList_GET_SIZE(A0):0;
            for(long k=1;k<argc;k++) {
                Py_ssize_t m=PyList_Check(sa[k])?PyList_GET_SIZE(sa[k]):0;
                if(m<n)n=m;
            }
            PyObject *r=PyList_New(n); if(!r) return NULL;
            for(Py_ssize_t i=0;i<n;i++){
                PyObject *row=PyList_New(argc); if(!row){Py_DECREF(r);return NULL;}
                for(long k=0;k<argc;k++){
                    PyObject *item=PyList_Check(sa[k])&&i<PyList_GET_SIZE(sa[k])?PyList_GET_ITEM(sa[k],i):Py_None;
                    Py_INCREF(item); PyList_SET_ITEM(row,k,item);
                }
                PyList_SET_ITEM(r,i,row);
            }
            return r;
        }
        /* HOF: map, filter, reduce, map_fn, filter_fn */
        if ((strcmp(op,"map")==0||strcmp(op,"map_fn")==0) && argc>=2 && parent_vm) {
            if (!PyList_Check(A0)) { PyObject *r=PyList_New(0); if(!r)return NULL; return r; }
            PyObject *fn = A1;
            Py_ssize_t n=PyList_GET_SIZE(A0);
            PyObject *result=PyList_New(n); if(!result) return NULL;
            for(Py_ssize_t i=0;i<n;i++){
                PyObject *item=PyList_GET_ITEM(A0,i);
                PyObject *r=cvm_call1(parent_vm, fn, &item, 1);
                if(!r){Py_DECREF(result);return NULL;}
                PyList_SET_ITEM(result,i,r);
            }
            return result;
        }
        if ((strcmp(op,"filter")==0||strcmp(op,"filter_fn")==0) && argc>=2 && parent_vm) {
            if (!PyList_Check(A0)) { PyObject *r=PyList_New(0); if(!r)return NULL; return r; }
            PyObject *fn = A1;
            Py_ssize_t n=PyList_GET_SIZE(A0);
            PyObject *result=PyList_New(0); if(!result) return NULL;
            for(Py_ssize_t i=0;i<n;i++){
                PyObject *item=PyList_GET_ITEM(A0,i);
                PyObject *r=cvm_call1(parent_vm, fn, &item, 1);
                if(!r){Py_DECREF(result);return NULL;}
                if(mellow_truthy(r)){
                    Py_INCREF(item); PyList_Append(result, item);
                }
                Py_DECREF(r);
            }
            return result;
        }
        if (strcmp(op,"reduce")==0 && argc>=2 && parent_vm) {
            if (!PyList_Check(A0)||PyList_GET_SIZE(A0)==0) {
                PyObject *init = argc>=3?A2:Py_None;
                Py_INCREF(init); return init;
            }
            PyObject *fn = A1;
            Py_ssize_t n=PyList_GET_SIZE(A0);
            PyObject *acc = argc>=3&&A2!=Py_None ? A2 : PyList_GET_ITEM(A0,0);
            Py_INCREF(acc);
            Py_ssize_t start = argc>=3&&A2!=Py_None ? 0 : 1;
            for(Py_ssize_t i=start;i<n;i++){
                PyObject *item=PyList_GET_ITEM(A0,i);
                PyObject *call_args[2]={acc, item};
                PyObject *r=cvm_call1(parent_vm, fn, call_args, 2);
                Py_DECREF(acc);
                if(!r) return NULL;
                acc=r;
            }
            return acc;
        }
        /* spread helpers */
        if (strcmp(op,"_append_to_top")==0 && argc>=2) {
            PyObject *base=PyList_Check(A0)?A0:NULL;
            Py_ssize_t bsz=base?PyList_GET_SIZE(base):0;
            PyObject *r=PyList_New(bsz+1); if(!r) return NULL;
            for(Py_ssize_t i=0;i<bsz;i++){Py_INCREF(PyList_GET_ITEM(base,i));PyList_SET_ITEM(r,i,PyList_GET_ITEM(base,i));}
            Py_INCREF(A1); PyList_SET_ITEM(r,bsz,A1);
            return r;
        }
        if (strcmp(op,"_extend")==0 && argc>=2) {
            PyObject *base=PyList_Check(A0)?A0:NULL;
            Py_ssize_t bsz=base?PyList_GET_SIZE(base):0;
            Py_ssize_t esz=PyList_Check(A1)?PyList_GET_SIZE(A1):(PyUnicode_Check(A1)?PyUnicode_GET_LENGTH(A1):0);
            PyObject *r=PyList_New(bsz+esz); if(!r) return NULL;
            for(Py_ssize_t i=0;i<bsz;i++){Py_INCREF(PyList_GET_ITEM(base,i));PyList_SET_ITEM(r,i,PyList_GET_ITEM(base,i));}
            if(PyList_Check(A1)){
                for(Py_ssize_t i=0;i<esz;i++){Py_INCREF(PyList_GET_ITEM(A1,i));PyList_SET_ITEM(r,bsz+i,PyList_GET_ITEM(A1,i));}
            } else if(PyUnicode_Check(A1)){
                for(Py_ssize_t i=0;i<esz;i++){
                    PyObject *ch=PyUnicode_FromOrdinal((int)PyUnicode_READ_CHAR(A1,i));
                    if(!ch){Py_DECREF(r);return NULL;}
                    PyList_SET_ITEM(r,bsz+i,ch);
                }
            }
            return r;
        }
    } /* std.list */

