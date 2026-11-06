static PyObject *cvm_exec(CVM *vm, int start_pc)
{
    int pc = start_pc;
    PyObject *exec_result = NULL;

    while (pc < (int)vm->bc_len) {
        if (++(*vm->steps) > vm->max_steps) {
            PyErr_SetString(PyExc_RuntimeError, "RUNTIME: step limit exceeded");
            goto exec_err;
        }

        PyObject *instr = PyList_GET_ITEM(vm->bytecode_obj, pc);
        if (!PyTuple_Check(instr)||PyTuple_GET_SIZE(instr)==0){pc++;continue;}

        int op = (int)PyLong_AsLong(PyTuple_GET_ITEM(instr,0));
        Py_ssize_t ilen = PyTuple_GET_SIZE(instr);

        switch(op) {

        case OP_HALT: case OP_STOP: goto exec_done;

        case OP_PUSH: {
            PyObject *v = _A1;
            /* normalise string literals: "true"→True, "1.5"→1.5 etc. */
            if (PyUnicode_Check(v)) {
                const char *s = PyUnicode_AsUTF8(v);
                if (s) {
                    if (strcmp(s,"true")==0||strcmp(s,"True")==0) { _PUSH(Py_True); break; }
                    if (strcmp(s,"false")==0||strcmp(s,"False")==0) { _PUSH(Py_False); break; }
                    if (strcmp(s,"none")==0||strcmp(s,"null")==0||strcmp(s,"None")==0) { _PUSH(Py_None); break; }
                    /* try numeric */
                    char *end;
                    long li = strtol(s,&end,10);
                    if (*end=='\0') { PyObject *n=PyLong_FromLong(li); _PUSH(n); Py_DECREF(n); break; }
                    double df = strtod(s,&end);
                    if (*end=='\0') { PyObject *n=PyFloat_FromDouble(df); _PUSH(n); Py_DECREF(n); break; }
                }
            }
            _PUSH(v); break;
        }

        case OP_STORE: case OP_STORE_KEEP: case OP_STORE_AUTO: {
            PyObject *v=_POP();
            PyDict_SetItem(vm->scopes[vm->ns-1],_A1,v);
            Py_DECREF(v); break;
        }

        case OP_LOAD: {
            PyObject *nm=_A1, *val=scope_get(vm->scopes,vm->ns,nm);
            if(!val) val=PyDict_GetItem(vm->func_table,nm)?make_func_ref(nm):NULL;
            if(!val) {
                PyErr_Format(PyExc_RuntimeError, "RUNTIME: undefined name: %s",
                             PyUnicode_Check(nm)?PyUnicode_AsUTF8(nm):"<unknown>");
                goto exec_runtime_err;
            }
            else if(val==(PyObject*)1) { goto exec_err; } /* make_func_ref error */
            else { _PUSH(val); if(PyErr_Occurred()) goto exec_err; }
            break;
        }

        case OP_ARG: {
            PyObject *v=_POP();
            PyDict_SetItem(vm->scopes[vm->ns-1],_A1,v);
            Py_DECREF(v); break;
        }

        case OP_ADD: { PyObject *b=_POP(),*a=_POP(),*r=op_add(a,b); Py_DECREF(a);Py_DECREF(b); if(!r)goto exec_err; _PUSH(r);Py_DECREF(r); break; }
        case OP_SUB: { PyObject *b=_POP(),*a=_POP(),*r=op_sub(a,b); Py_DECREF(a);Py_DECREF(b); if(!r)goto exec_err; _PUSH(r);Py_DECREF(r); break; }
        case OP_MUL: { PyObject *b=_POP(),*a=_POP(),*r=op_mul(a,b); Py_DECREF(a);Py_DECREF(b); if(!r)goto exec_err; _PUSH(r);Py_DECREF(r); break; }
        case OP_DIV: {
            PyObject *b=_POP(),*a=_POP();
            double db=to_double(b);
            if (db==0.0) {
                Py_DECREF(a); Py_DECREF(b);
                PyErr_SetString(PyExc_ZeroDivisionError, "division by zero");
                goto exec_runtime_err;
            }
            PyObject *r=maybe_int(to_double(a)/db); Py_DECREF(a);Py_DECREF(b);
            if(!r)goto exec_err; _PUSH(r);Py_DECREF(r); break;
        }
        case OP_MOD: { PyObject *b=_POP(),*a=_POP(),*r=op_mod(a,b); Py_DECREF(a);Py_DECREF(b); if(!r)goto exec_err; _PUSH(r);Py_DECREF(r); break; }
        case OP_POW_OP: { PyObject *b=_POP(),*a=_POP(),*r=op_pow(a,b); Py_DECREF(a);Py_DECREF(b); if(!r)goto exec_err; _PUSH(r);Py_DECREF(r); break; }

        case OP_COMPARE: {
            PyObject *b=_POP(),*a=_POP();
            const char *os=PyUnicode_Check(_A1)?PyUnicode_AsUTF8(_A1):"==";
            PyObject *r=op_cmp(a,b,os); Py_DECREF(a);Py_DECREF(b);
            if(!r)goto exec_err; _PUSH(r);Py_DECREF(r); break;
        }
        case OP_BOOL_AND: { PyObject *b=_POP(),*a=_POP(); int r=mellow_truthy(a)&&mellow_truthy(b); Py_DECREF(a);Py_DECREF(b); _PUSH(r?Py_True:Py_False); break; }
        case OP_BOOL_OR:  { PyObject *b=_POP(),*a=_POP(); int r=mellow_truthy(a)||mellow_truthy(b); Py_DECREF(a);Py_DECREF(b); _PUSH(r?Py_True:Py_False); break; }
        case OP_BOOL_NOT: { PyObject *a=_POP(); int r=!mellow_truthy(a); Py_DECREF(a); _PUSH(r?Py_True:Py_False); break; }

        case OP_JUMP: pc=(int)PyLong_AsLong(_A1); continue;
        case OP_JIF: {
            PyObject *c=_POP(); int t=mellow_truthy(c); Py_DECREF(c);
            if(!t){pc=(int)PyLong_AsLong(_A1);continue;}
            break;
        }

        case OP_CALL: {
            PyObject *fname=_A1;
            long argc_c=ilen>2?PyLong_AsLong(_A2):0;
            const char *fname_c=PyUnicode_Check(fname)?PyUnicode_AsUTF8(fname):"";
            if(fname_c && strcmp(fname_c,"range")==0) {
                PyObject **args=(PyObject**)alloca((size_t)argc_c*sizeof(PyObject*));
                for(long i=argc_c-1;i>=0;i--) args[i]=_POP();
                long start=0, stop=0, step=1;
                if(argc_c==1) {
                    stop=to_long(args[0]);
                } else if(argc_c>=2) {
                    start=to_long(args[0]);
                    stop=to_long(args[1]);
                    if(argc_c>=3) step=to_long(args[2]);
                }
                if(step==0) step=1;
                PyObject *lst=PyList_New(0);
                if(!lst) {
                    for(long i=0;i<argc_c;i++) Py_DECREF(args[i]);
                    goto exec_err;
                }
                if(step>0) {
                    for(long v=start; v<stop; v+=step) {
                        PyObject *item=PyLong_FromLong(v);
                        if(!item || PyList_Append(lst,item)<0) {
                            Py_XDECREF(item);
                            Py_DECREF(lst);
                            for(long i=0;i<argc_c;i++) Py_DECREF(args[i]);
                            goto exec_err;
                        }
                        Py_DECREF(item);
                    }
                } else {
                    for(long v=start; v>stop; v+=step) {
                        PyObject *item=PyLong_FromLong(v);
                        if(!item || PyList_Append(lst,item)<0) {
                            Py_XDECREF(item);
                            Py_DECREF(lst);
                            for(long i=0;i<argc_c;i++) Py_DECREF(args[i]);
                            goto exec_err;
                        }
                        Py_DECREF(item);
                    }
                }
                for(long i=0;i<argc_c;i++) Py_DECREF(args[i]);
                _PUSH(lst);
                Py_DECREF(lst);
                break;
            }
            /* resolve variable → func ref */
            PyObject *fvar=scope_get(vm->scopes,vm->ns,fname);
            PyObject *aname=fname;
            if(fvar){PyObject *rn=NULL; if(is_func_ref(fvar,&rn)) aname=rn;}
            PyObject *fn_meta=PyDict_GetItem(vm->func_table,aname);
            if(!fn_meta){
                PyErr_Format(PyExc_RuntimeError,"RUNTIME: undefined function '%s'",
                             PyUnicode_AsUTF8(aname));
                goto exec_runtime_err;
            }
            long pc_cnt=0; PyObject *pco=PyDict_GetItemString(fn_meta,"param_count");
            if(pco) pc_cnt=PyLong_AsLong(pco);
            /* pad missing args with defaults */
            PyObject *defaults=PyDict_GetItemString(fn_meta,"defaults");
            PyObject *params_list=PyDict_GetItemString(fn_meta,"params");
            while(argc_c<pc_cnt){
                PyObject *def_val=Py_None;
                if(defaults&&params_list&&PyList_Check(params_list)){
                    long pidx=argc_c;
                    if(pidx<PyList_GET_SIZE(params_list)){
                        PyObject *pn=PyList_GET_ITEM(params_list,pidx);
                        if(pn&&PyUnicode_Check(pn)){
                            PyObject *dv=PyDict_GetItem(defaults,pn);
                            if(dv) def_val=dv;
                        }
                    }
                }
                _PUSH(def_val); argc_c++;
            }
            if(vm->csp>=vm->max_cs){PyErr_SetString(PyExc_RuntimeError,"CVM:callstack overflow");goto exec_err;}
            if(vm->ns>=vm->max_scopes){PyErr_SetString(PyExc_RuntimeError,"CVM:scope overflow");goto exec_err;}
            vm->cs[vm->csp++]=pc+1;
            vm->scopes[vm->ns]=PyDict_New(); if(!vm->scopes[vm->ns])goto exec_err; vm->ns++;
            PyObject *addr=PyDict_GetItemString(fn_meta,"address");
            pc=(int)PyLong_AsLong(addr); continue;
        }

        case OP_CALL_VAL: {
            long argc_c=ilen>1?PyLong_AsLong(_A1):0;
            PyObject **ca=(PyObject**)alloca((size_t)argc_c*sizeof(PyObject*));
            for(long i=argc_c-1;i>=0;i--) ca[i]=_POP();
            PyObject *fref=_POP(), *fn_name=NULL;
            if(!is_func_ref(fref,&fn_name)){Py_DECREF(fref);for(long i=0;i<argc_c;i++)Py_DECREF(ca[i]);_PUSH(Py_None);break;}
            PyObject *fn_meta=PyDict_GetItem(vm->func_table,fn_name);
            if(!fn_meta){Py_DECREF(fref);for(long i=0;i<argc_c;i++)Py_DECREF(ca[i]);_PUSH(Py_None);break;}
            long pc_cnt=0; PyObject *pco=PyDict_GetItemString(fn_meta,"param_count");
            if(pco) pc_cnt=PyLong_AsLong(pco);
            for(long i=0;i<argc_c;i++){_PUSH(ca[i]);Py_DECREF(ca[i]);}
            while(argc_c<pc_cnt){_PUSH(Py_None);argc_c++;}
            if(vm->csp>=vm->max_cs||vm->ns>=vm->max_scopes){Py_DECREF(fref);PyErr_SetString(PyExc_RuntimeError,"CVM:overflow");goto exec_err;}
            vm->cs[vm->csp++]=pc+1;
            vm->scopes[vm->ns]=PyDict_New(); if(!vm->scopes[vm->ns]){Py_DECREF(fref);goto exec_err;} vm->ns++;
            PyObject *addr=PyDict_GetItemString(fn_meta,"address");
            pc=(int)PyLong_AsLong(addr); Py_DECREF(fref); continue;
        }

        case OP_RETURN: {
            PyObject *rv=_POP();
            Py_DECREF(vm->scopes[--vm->ns]);
            vm->scopes[vm->ns]=NULL;
            if(vm->csp==0){exec_result=rv;goto exec_done;}
            pc=vm->cs[--vm->csp]; _PUSH(rv); Py_DECREF(rv); continue;
        }

        case OP_PUSH_FUNC: {
            PyObject *ref=make_func_ref(_A1);
            if(!ref) goto exec_err;
            _PUSH(ref); Py_DECREF(ref); break;
        }

        case OP_PRINT: {
            PyObject *v=_POP(), *s=mellow_format(v); Py_DECREF(v);
            if(!s) goto exec_err;
            cvm_print(vm, PyUnicode_AsUTF8(s)); Py_DECREF(s); break;
        }
        case OP_PRINTN: {
            long n=ilen>1?(long)PyLong_AsLong(_A1):1;
            PyObject **vs=(PyObject**)alloca((size_t)n*sizeof(PyObject*));
            for(long i=n-1;i>=0;i--) vs[i]=_POP();
            for(long i=0;i<n;i++){
                PyObject *s=mellow_format(vs[i]);
                if(s){if(i>0)PySys_WriteStdout(" ");PySys_WriteStdout("%s",PyUnicode_AsUTF8(s));Py_DECREF(s);}
                Py_DECREF(vs[i]);
            }
            PySys_WriteStdout("\n"); break;
        }
        case OP_SHOW_PREC: { PyObject *v=_POP(); Py_DECREF(v); break; }

        case OP_POP: if(vm->sp>0){Py_XDECREF(vm->stack[--vm->sp]);} break;

        case OP_LEN: {
            PyObject *v=_POP(); Py_ssize_t n=-1;
            if(PyUnicode_Check(v))n=PyUnicode_GET_LENGTH(v);
            else if(PyList_Check(v))n=PyList_GET_SIZE(v);
            else if(PyDict_Check(v))n=PyDict_Size(v);
            Py_DECREF(v);
            PyObject *r=PyLong_FromSsize_t(n<0?0:n); _PUSH(r); Py_DECREF(r); break;
        }

        case OP_GETITEM: {
            PyObject *idx=_POP(), *tgt=_POP(), *r=NULL;
            if(PyList_Check(tgt)){
                Py_ssize_t i=PyLong_AsSsize_t(idx),sz=PyList_GET_SIZE(tgt);
                if(PyErr_Occurred()){Py_DECREF(idx);Py_DECREF(tgt);goto exec_runtime_err;}
                if(i<0)i+=sz;
                if(i<0||i>=sz){PyErr_SetString(PyExc_IndexError,"index out of range");}
                else {r=PyList_GET_ITEM(tgt,i);Py_INCREF(r);}
            } else if(PyUnicode_Check(tgt)){
                Py_ssize_t i=PyLong_AsSsize_t(idx),sz=PyUnicode_GET_LENGTH(tgt);
                if(PyErr_Occurred()){Py_DECREF(idx);Py_DECREF(tgt);goto exec_runtime_err;}
                if(i<0)i+=sz;
                if(i<0||i>=sz){PyErr_SetString(PyExc_IndexError,"index out of range");}
                else r=PyUnicode_FromOrdinal((int)PyUnicode_READ_CHAR(tgt,i));
            } else if(PyDict_Check(tgt)){
                PyObject *k=mellow_format(idx);
                PyObject *val=k?PyDict_GetItem(tgt,k):NULL;
                Py_XDECREF(k);
                if(!val) PyErr_SetString(PyExc_KeyError,"missing map key");
                else {r=val;Py_INCREF(r);}
            } else {
                PyErr_SetString(PyExc_TypeError,"value is not indexable");
            }
            Py_DECREF(idx); Py_DECREF(tgt);
            if(!r)goto exec_runtime_err;
            _PUSH(r); Py_DECREF(r); break;
        }

        case OP_SLICE: {
            PyObject *stop=_POP(),*start=_POP(),*tgt=_POP();
            PyObject *sl=PySlice_New(start==Py_None?Py_None:start,stop==Py_None?Py_None:stop,Py_None);
            Py_DECREF(start); Py_DECREF(stop);
            PyObject *r=NULL;
            if(sl){r=PyObject_GetItem(tgt,sl);Py_DECREF(sl);}
            Py_DECREF(tgt);
            if(!r){PyErr_Clear();r=Py_None;Py_INCREF(r);}
            _PUSH(r); Py_DECREF(r); break;
        }

