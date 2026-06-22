/* ================================================================
 * cvm_syscall_dispatch — full SYSCALL table
 * sa[0..argc-1] are borrowed refs from the stack
 * Returns new ref to result, or NULL on error.
 * If sn is unknown, sets RuntimeError and returns NULL.
 * ================================================================ */

/* helper: coerce to Python float */
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

    /* ── std.string ── */
    if (strncmp(sn,"std.string.",11)==0) {
        const char *op=sn+11;
        if (strcmp(op,"tostr")==0   && argc>=1) return mellow_format(A0);
        if (strcmp(op,"len")==0     && argc>=1) {
            Py_ssize_t n=PyUnicode_Check(A0)?PyUnicode_GET_LENGTH(A0):0;
            return PyLong_FromSsize_t(n);
        }
        if (strcmp(op,"lower")==0   && argc>=1) { PyObject *s=mellow_format(A0); if(!s)return NULL; PyObject *r=PyObject_CallMethod(s,"lower",NULL); Py_DECREF(s); return r; }
        if (strcmp(op,"upper")==0   && argc>=1) { PyObject *s=mellow_format(A0); if(!s)return NULL; PyObject *r=PyObject_CallMethod(s,"upper",NULL); Py_DECREF(s); return r; }
        if (strcmp(op,"trim")==0    && argc>=1) { PyObject *s=mellow_format(A0); if(!s)return NULL; PyObject *r=PyObject_CallMethod(s,"strip",NULL); Py_DECREF(s); return r; }
        if (strcmp(op,"replace")==0 && argc>=3) {
            PyObject *s=mellow_format(A0); if(!s) return NULL;
            PyObject *f=mellow_format(A1); if(!f){Py_DECREF(s);return NULL;}
            PyObject *t=mellow_format(A2); if(!t){Py_DECREF(s);Py_DECREF(f);return NULL;}
            PyObject *r=PyUnicode_Replace(s,f,t,-1);
            Py_DECREF(s); Py_DECREF(f); Py_DECREF(t); return r;
        }
        if (strcmp(op,"find")==0 && argc>=2) {
            PyObject *s=mellow_format(A0); if(!s) return NULL;
            PyObject *sub=mellow_format(A1); if(!sub){Py_DECREF(s);return NULL;}
            Py_ssize_t idx=PyUnicode_Find(s,sub,0,PyUnicode_GET_LENGTH(s),1);
            Py_DECREF(s); Py_DECREF(sub);
            return PyLong_FromSsize_t(idx);
        }
        if (strcmp(op,"contains")==0 && argc>=2) {
            PyObject *s=mellow_format(A0); if(!s) return NULL;
            PyObject *sub=mellow_format(A1); if(!sub){Py_DECREF(s);return NULL;}
            Py_ssize_t idx=PyUnicode_Find(s,sub,0,PyUnicode_GET_LENGTH(s),1);
            Py_DECREF(s); Py_DECREF(sub);
            return idx>=0?(Py_INCREF(Py_True),Py_True):(Py_INCREF(Py_False),Py_False);
        }
        if (strcmp(op,"starts_with")==0 && argc>=2) {
            PyObject *s=mellow_format(A0); if(!s) return NULL;
            PyObject *sub=mellow_format(A1); if(!sub){Py_DECREF(s);return NULL;}
            Py_ssize_t sl=PyUnicode_GET_LENGTH(s), ql=PyUnicode_GET_LENGTH(sub);
            int r = sl>=ql && PyUnicode_Find(s,sub,0,ql,1)==0;
            Py_DECREF(s); Py_DECREF(sub);
            return r?(Py_INCREF(Py_True),Py_True):(Py_INCREF(Py_False),Py_False);
        }
        if (strcmp(op,"ends_with")==0 && argc>=2) {
            PyObject *s=mellow_format(A0); if(!s) return NULL;
            PyObject *sub=mellow_format(A1); if(!sub){Py_DECREF(s);return NULL;}
            Py_ssize_t sl=PyUnicode_GET_LENGTH(s), ql=PyUnicode_GET_LENGTH(sub);
            int r = sl>=ql && PyUnicode_Find(s,sub,sl-ql,sl,1)==sl-ql;
            Py_DECREF(s); Py_DECREF(sub);
            return r?(Py_INCREF(Py_True),Py_True):(Py_INCREF(Py_False),Py_False);
        }
        if (strcmp(op,"repeat")==0 && argc>=2) {
            PyObject *s=mellow_format(A0); if(!s) return NULL;
            Py_ssize_t n=(Py_ssize_t)to_long(A1);
            PyObject *r=PySequence_Repeat(s,n>0?n:0); Py_DECREF(s); return r;
        }
        if (strcmp(op,"split")==0 && argc>=1) {
            PyObject *s=mellow_format(A0); if(!s) return NULL;
            PyObject *sep=argc>=2&&A1!=Py_None?mellow_format(A1):NULL;
            PyObject *r;
            if (sep) {
                r=PyUnicode_Split(s,sep,-1);
                Py_DECREF(sep);
            } else {
                r=PyUnicode_Split(s,NULL,-1);
            }
            Py_DECREF(s); return r;
        }
        if (strcmp(op,"join")==0 && argc>=1) {
            PyObject *sep=mellow_format(A0); if(!sep) return NULL;
            if (argc>=2 && PyList_Check(A1)) {
                Py_ssize_t n=PyList_GET_SIZE(A1);
                PyObject *parts=PyList_New(n);
                if(!parts){Py_DECREF(sep);return NULL;}
                for(Py_ssize_t i=0;i<n;i++){
                    PyObject *f=mellow_format(PyList_GET_ITEM(A1,i));
                    if(!f){Py_DECREF(parts);Py_DECREF(sep);return NULL;}
                    PyList_SET_ITEM(parts,i,f);
                }
                PyObject *r=PyUnicode_Join(sep,parts);
                Py_DECREF(sep); Py_DECREF(parts); return r;
            }
            /* join with no list: just return sep */
            return sep;
        }
        if (strcmp(op,"pad_left")==0 && argc>=2) {
            PyObject *s=mellow_format(A0); if(!s) return NULL;
            Py_ssize_t width=(Py_ssize_t)to_long(A1);
            Py_ssize_t cur=PyUnicode_GET_LENGTH(s);
            if(cur>=width){return s;}
            const char *pad_s=" ";
            if(argc>=3&&PyUnicode_Check(A2)&&PyUnicode_GET_LENGTH(A2)>0)
                pad_s=PyUnicode_AsUTF8(A2);
            PyObject *pad=PyUnicode_FromString(pad_s);
            PyObject *r=PyUnicode_FromFormat("%.*s%U",(int)(width-cur),
                /* pad repeated */ pad_s,s);
            /* simpler: build pad string */
            PyObject *padded=PySequence_Repeat(pad,width-cur);
            Py_DECREF(pad);
            if(!padded){Py_DECREF(s);return NULL;}
            PyObject *res=PyUnicode_Concat(padded,s);
            Py_DECREF(padded); Py_DECREF(s);
            Py_XDECREF(r);
            return res;
        }
        if (strcmp(op,"pad_right")==0 && argc>=2) {
            PyObject *s=mellow_format(A0); if(!s) return NULL;
            Py_ssize_t width=(Py_ssize_t)to_long(A1);
            Py_ssize_t cur=PyUnicode_GET_LENGTH(s);
            if(cur>=width){return s;}
            const char *pad_s=" ";
            if(argc>=3&&PyUnicode_Check(A2)&&PyUnicode_GET_LENGTH(A2)>0)
                pad_s=PyUnicode_AsUTF8(A2);
            PyObject *pad=PyUnicode_FromString(pad_s);
            PyObject *padded=PySequence_Repeat(pad,width-cur);
            Py_DECREF(pad);
            if(!padded){Py_DECREF(s);return NULL;}
            PyObject *res=PyUnicode_Concat(s,padded);
            Py_DECREF(padded); Py_DECREF(s);
            return res;
        }
        if (strcmp(op,"chr")==0 && argc>=1) {
            long code=to_long(A0);
            if(code<0||code>0x10FFFF) code=63;
            return PyUnicode_FromOrdinal((int)code);
        }
        if (strcmp(op,"ord")==0 && argc>=1) {
            PyObject *s=mellow_format(A0); if(!s) return NULL;
            long r=PyUnicode_GET_LENGTH(s)>0?(long)PyUnicode_READ_CHAR(s,0):0;
            Py_DECREF(s); return PyLong_FromLong(r);
        }
        if (strcmp(op,"format")==0 && argc>=1) {
            /* simple: just tostr the first arg */
            return mellow_format(A0);
        }
    } /* std.string */

    /* ── std.math ── */
    if (strncmp(sn,"std.math.",9)==0) {
        const char *op=sn+9;
        double a0=argc>0?to_double(A0):0.0;
        double a1=argc>1?to_double(A1):0.0;
        double a2=argc>2?to_double(A2):0.0;
        if (strcmp(op,"abs")==0)         return maybe_int(fabs(a0));
        if (strcmp(op,"floor")==0)       return PyLong_FromDouble(floor(a0));
        if (strcmp(op,"ceil")==0)        return PyLong_FromDouble(ceil(a0));
        if (strcmp(op,"round")==0)       return PyLong_FromDouble(round(a0));
        if (strcmp(op,"sqrt")==0)        return PyFloat_FromDouble(sqrt(a0));
        if (strcmp(op,"pow")==0)         return maybe_int(pow(a0,a1));
        if (strcmp(op,"sin")==0)         return PyFloat_FromDouble(sin(a0));
        if (strcmp(op,"cos")==0)         return PyFloat_FromDouble(cos(a0));
        if (strcmp(op,"tan")==0)         return PyFloat_FromDouble(tan(a0));
        if (strcmp(op,"atan2")==0)       return PyFloat_FromDouble(atan2(a0,a1));
        if (strcmp(op,"pi")==0)          return PyFloat_FromDouble(M_PI);
        if (strcmp(op,"min")==0)         return maybe_int(a0<a1?a0:a1);
        if (strcmp(op,"max")==0)         return maybe_int(a0>a1?a0:a1);
        if (strcmp(op,"sign")==0)        return PyLong_FromLong(a0>0?1:a0<0?-1:0);
        if (strcmp(op,"fmod")==0)        return maybe_int(fmod(a0,a1));
        if (strcmp(op,"deg_to_rad")==0)  return PyFloat_FromDouble(a0*M_PI/180.0);
        if (strcmp(op,"rad_to_deg")==0)  return PyFloat_FromDouble(a0*180.0/M_PI);
        if (strcmp(op,"clamp")==0) {
            double lo=a1,hi=a2; if(a0<lo)a0=lo; if(a0>hi)a0=hi;
            return maybe_int(a0);
        }
        if (strcmp(op,"lerp")==0)        return PyFloat_FromDouble(a0+(a1-a0)*a2);
        if (strcmp(op,"sum")==0 && argc>=1 && PyList_Check(A0)) {
            double s=0.0;
            Py_ssize_t n=PyList_GET_SIZE(A0);
            for(Py_ssize_t i=0;i<n;i++) s+=to_double(PyList_GET_ITEM(A0,i));
            return maybe_int(s);
        }
        if (strcmp(op,"distance")==0 && argc>=2 && PyList_Check(A0) && PyList_Check(A1)) {
            double d=0.0;
            Py_ssize_t n=PyList_GET_SIZE(A0)<PyList_GET_SIZE(A1)?PyList_GET_SIZE(A0):PyList_GET_SIZE(A1);
            for(Py_ssize_t i=0;i<n;i++){
                double diff=to_double(PyList_GET_ITEM(A0,i))-to_double(PyList_GET_ITEM(A1,i));
                d+=diff*diff;
            }
            return PyFloat_FromDouble(sqrt(d));
        }
        if (strcmp(op,"angle_between")==0 && argc>=2 && PyList_Check(A0) && PyList_Check(A1)) {
            double ax=PyList_GET_SIZE(A0)>0?to_double(PyList_GET_ITEM(A0,0)):0.0;
            double ay=PyList_GET_SIZE(A0)>1?to_double(PyList_GET_ITEM(A0,1)):0.0;
            double bx=PyList_GET_SIZE(A1)>0?to_double(PyList_GET_ITEM(A1,0)):0.0;
            double by=PyList_GET_SIZE(A1)>1?to_double(PyList_GET_ITEM(A1,1)):0.0;
            return PyFloat_FromDouble(atan2(by-ay,bx-ax));
        }
        /* vector ops — delegate to Python for simplicity */
    } /* std.math */

    /* ── std.map ── */
    if (strncmp(sn,"std.map.",8)==0) {
        const char *op=sn+8;
        if (strcmp(op,"get")==0 && argc>=2) {
            if (!PyDict_Check(A0)) { Py_INCREF(argc>=3?A2:Py_None); return argc>=3?A2:Py_None; }
            PyObject *k=mellow_format(A1); if(!k)return NULL;
            PyObject *v=PyDict_GetItem(A0,k); Py_DECREF(k);
            if(!v) v=argc>=3?A2:Py_None;
            Py_INCREF(v); return v;
        }
        if (strcmp(op,"set")==0 && argc>=3) {
            if (PyDict_Check(A0)){
                PyObject *k=mellow_format(A1); if(!k)return NULL;
                PyDict_SetItem(A0,k,A2); Py_DECREF(k);
            }
            Py_INCREF(A0); return A0;
        }
        if (strcmp(op,"keys")==0 && argc>=1) {
            if (!PyDict_Check(A0)) { PyObject *r=PyList_New(0); return r; }
            return PyList_New(0); /* build key list */
            /* Actually do it properly: */
        }
        if (strcmp(op,"values")==0 && argc>=1) {
            if (!PyDict_Check(A0)) { PyObject *r=PyList_New(0); return r; }
            PyObject *vals_view=PyDict_Values(A0);
            if(!vals_view) return NULL;
            return vals_view;
        }
        if (strcmp(op,"has")==0 && argc>=2) {
            if (!PyDict_Check(A0)) { Py_INCREF(Py_False); return Py_False; }
            PyObject *k=mellow_format(A1); if(!k) return NULL;
            int r=PyDict_Contains(A0,k); Py_DECREF(k);
            if(r<0){PyErr_Clear();r=0;}
            return r?(Py_INCREF(Py_True),Py_True):(Py_INCREF(Py_False),Py_False);
        }
        /* fix keys */
        if (strcmp(op,"keys")==0 && argc>=1) {
            if (!PyDict_Check(A0)) { return PyList_New(0); }
            PyObject *kv=PyDict_Keys(A0); return kv;
        }
    } /* std.map — fallthrough for keys */

    /* std.map.keys re-entry (fix above duplicate) */
    if (strcmp(sn,"std.map.keys")==0 && argc>=1) {
        if (!PyDict_Check(A0)) return PyList_New(0);
        return PyDict_Keys(A0);
    }

    /* ── std.type ── */
    if (strncmp(sn,"std.type.",9)==0) {
        const char *op=sn+9;
        int is_n = A0&&(PyLong_CheckExact(A0)||PyFloat_CheckExact(A0))&&A0!=Py_True&&A0!=Py_False;
        if (strcmp(op,"is_number")==0) return is_n?(Py_INCREF(Py_True),Py_True):(Py_INCREF(Py_False),Py_False);
        if (strcmp(op,"is_string")==0) { int r=PyUnicode_Check(A0); return r?(Py_INCREF(Py_True),Py_True):(Py_INCREF(Py_False),Py_False); }
        if (strcmp(op,"is_bool")==0)   { int r=(A0==Py_True||A0==Py_False); return r?(Py_INCREF(Py_True),Py_True):(Py_INCREF(Py_False),Py_False); }
        if (strcmp(op,"is_list")==0)   { int r=PyList_Check(A0); return r?(Py_INCREF(Py_True),Py_True):(Py_INCREF(Py_False),Py_False); }
        if (strcmp(op,"is_map")==0)    { int r=PyDict_Check(A0); return r?(Py_INCREF(Py_True),Py_True):(Py_INCREF(Py_False),Py_False); }
        if (strcmp(op,"is_none")==0)   { int r=(A0==Py_None); return r?(Py_INCREF(Py_True),Py_True):(Py_INCREF(Py_False),Py_False); }
        if (strcmp(op,"of")==0) {
            const char *tn="none";
            if(A0==Py_True||A0==Py_False) tn="bool";
            else if(is_n) tn="number";
            else if(PyUnicode_Check(A0)) tn="string";
            else if(PyList_Check(A0))    tn="list";
            else if(PyDict_Check(A0))    tn="map";
            return PyUnicode_FromString(tn);
        }
        if (strcmp(op,"to_int")==0)   return pylong(A0);
        if (strcmp(op,"to_float")==0) return pyfloat(A0);
        if (strcmp(op,"to_str")==0)   return mellow_format(A0);
        if (strcmp(op,"to_bool")==0)  return mellow_truthy(A0)?(Py_INCREF(Py_True),Py_True):(Py_INCREF(Py_False),Py_False);
        if (strcmp(op,"to_list")==0) {
            if(PyList_Check(A0)){Py_INCREF(A0);return A0;}
            if(PyUnicode_Check(A0)){
                Py_ssize_t n=PyUnicode_GET_LENGTH(A0);
                PyObject *r=PyList_New(n); if(!r) return NULL;
                for(Py_ssize_t i=0;i<n;i++){
                    PyObject *ch=PyUnicode_FromOrdinal((int)PyUnicode_READ_CHAR(A0,i));
                    if(!ch){Py_DECREF(r);return NULL;}
                    PyList_SET_ITEM(r,i,ch);
                }
                return r;
            }
            PyObject *r=PyList_New(1); if(!r) return NULL;
            Py_INCREF(A0); PyList_SET_ITEM(r,0,A0); return r;
        }
    } /* std.type */

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
