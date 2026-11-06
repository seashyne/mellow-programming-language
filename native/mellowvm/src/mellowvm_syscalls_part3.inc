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

