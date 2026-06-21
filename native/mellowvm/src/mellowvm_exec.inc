/* ================================================================
 * cvm_exec — main dispatch loop (shared between run and call1)
 *
 * Runs from start_pc until HALT/STOP or until RETURN with csp==0.
 * Returns new ref to result (top-of-stack or None), or NULL on error.
 * ================================================================ */

#define _PUSH(v)  do { if(vm->sp>=(int)vm->max_stack){PyErr_SetString(PyExc_RuntimeError,"CVM:stack overflow");goto exec_err;}Py_XINCREF(v);vm->stack[vm->sp++]=(v); } while(0)
#define _POP()    (vm->sp>0 ? vm->stack[--vm->sp] : (Py_INCREF(Py_None),Py_None))
#define _TOP()    (vm->sp>0 ? vm->stack[vm->sp-1] : Py_None)
#define _A1       (ilen>1?PyTuple_GET_ITEM(instr,1):Py_None)
#define _A2       (ilen>2?PyTuple_GET_ITEM(instr,2):Py_None)
#define _A3       (ilen>3?PyTuple_GET_ITEM(instr,3):Py_None)

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

        case OP_BUILD_LIST: {
            long n=ilen>1?(long)PyLong_AsLong(_A1):0;
            PyObject *lst=PyList_New(n); if(!lst)goto exec_err;
            for(long i=n-1;i>=0;i--){ PyObject *v=_POP(); PyList_SET_ITEM(lst,i,v); }
            _PUSH(lst); Py_DECREF(lst); break;
        }

        case OP_BUILD_MAP: {
            long n=ilen>1?(long)PyLong_AsLong(_A1):0;
            PyObject *d=PyDict_New(); if(!d)goto exec_err;
            PyObject **pairs=(PyObject**)alloca((size_t)(n*2)*sizeof(PyObject*));
            for(long i=n*2-1;i>=0;i--) pairs[i]=_POP();
            for(long i=0;i<n;i++){
                PyObject *k=pairs[i*2],*v=pairs[i*2+1];
                PyObject *ks=PyObject_Str(k);
                if(ks){PyDict_SetItem(d,ks,v);Py_DECREF(ks);}
                Py_DECREF(k); Py_DECREF(v);
            }
            _PUSH(d); Py_DECREF(d); break;
        }

        case OP_LIST_HAS: {
            PyObject *item=_POP(),*lst=_POP(); int found=0;
            if(PyList_Check(lst)){
                Py_ssize_t sz=PyList_GET_SIZE(lst);
                for(Py_ssize_t i=0;i<sz;i++){
                    int eq=PyObject_RichCompareBool(PyList_GET_ITEM(lst,i),item,Py_EQ);
                    if(eq>0){found=1;break;} if(eq<0)PyErr_Clear();
                }
            }
            Py_DECREF(item); Py_DECREF(lst);
            _PUSH(found?Py_True:Py_False); break;
        }

        case OP_LIST_PUT: {
            PyObject *lst=_POP(),*item=_POP();
            if(PyList_Check(lst)) PyList_Append(lst,item);
            Py_DECREF(lst); Py_DECREF(item); break;
        }

        /* ── SYSCALL ── */
        case OP_SYSCALL: {
            long argc_c=ilen>1?(long)PyLong_AsLong(_A1):0;
            PyObject **sa=(PyObject**)alloca((size_t)argc_c*sizeof(PyObject*));
            for(long i=argc_c-1;i>=0;i--) sa[i]=_POP();
            PyObject *sc_name=_POP();
            const char *sn=PyUnicode_Check(sc_name)?PyUnicode_AsUTF8(sc_name):"";
            PyObject *sc_result=cvm_syscall_dispatch(sn,sa,argc_c,vm);
            for(long i=0;i<argc_c;i++) Py_DECREF(sa[i]);
            Py_DECREF(sc_name);
            if(!sc_result) goto exec_runtime_err;
            _PUSH(sc_result); Py_DECREF(sc_result); break;
        }

        /* ── TRY / ENDTRY ── */
        case OP_TRY: {
            if(vm->tsp>=vm->max_try){
                PyErr_SetString(PyExc_RuntimeError,"CVM:try stack overflow"); goto exec_err;
            }
            CvmTryFrame *tf=&vm->try_stack[vm->tsp++];
            tf->catch_pc   = ilen>1&&_A1!=Py_None?(int)PyLong_AsLong(_A1):-1;
            tf->finally_pc = ilen>2&&_A2!=Py_None?(int)PyLong_AsLong(_A2):-1;
            tf->err_name   = ilen>3?_A3:NULL;
            tf->stack_len  = vm->sp;
            break;
        }
        case OP_ENDTRY: {
            if(vm->tsp>0) vm->tsp--;
            break;
        }

        /* ── RANDOM / SEED ── */
        case OP_RANDOM: {
            PyObject *hi=_POP(), *lo=_POP();
            long lo_l=to_long(lo), hi_l=to_long(hi);
            Py_DECREF(lo); Py_DECREF(hi);
            long r;
            if(!vm->rng){
                /* use C rand */
                r = lo_l + (hi_l>lo_l ? (long)(rand()%(hi_l-lo_l+1)) : 0);
            } else {
                PyObject *res=PyObject_CallMethod(vm->rng,"randint","ll",lo_l,hi_l);
                if(!res) goto exec_runtime_err;
                r=PyLong_AsLong(res); Py_DECREF(res);
            }
            PyObject *rv=PyLong_FromLong(r); _PUSH(rv); Py_DECREF(rv); break;
        }
        case OP_RANDFLOAT: {
            double r;
            if(!vm->rng){
                r=(double)rand()/(double)RAND_MAX;
            } else {
                PyObject *res=PyObject_CallMethod(vm->rng,"random",NULL);
                if(!res) goto exec_runtime_err;
                r=PyFloat_AS_DOUBLE(res); Py_DECREF(res);
            }
            PyObject *rv=PyFloat_FromDouble(r); _PUSH(rv); Py_DECREF(rv); break;
        }
        case OP_SEED: case OP_GLOBAL_SEED: {
            PyObject *s=_POP();
            long seed=to_long(s); Py_DECREF(s);
            if(!vm->rng){
                PyObject *rand_mod=PyImport_ImportModule("random");
                if(rand_mod){
                    PyObject *rng_cls=PyObject_GetAttrString(rand_mod,"Random");
                    if(rng_cls){vm->rng=PyObject_CallNoArgs(rng_cls);Py_DECREF(rng_cls);}
                    Py_DECREF(rand_mod);
                }
            }
            if(vm->rng){
                PyObject *s_obj=PyLong_FromLong(seed);
                PyObject_CallMethod(vm->rng,"seed","O",s_obj);
                Py_DECREF(s_obj);
            }
            srand((unsigned)seed);
            break;
        }

        /* ── WAIT ── */
        case OP_WAIT: {
            PyObject *sec=_POP();
            if(vm->allow_wait){
                double t=to_double(sec);
                PyObject *tm=PyImport_ImportModule("time");
                if(tm){PyObject_CallMethod(tm,"sleep","d",t);Py_DECREF(tm);}
            }
            Py_DECREF(sec); break;
        }

        /* ── ASK ── */
        case OP_ASK: {
            PyObject *prompt=_POP();
            if(!vm->allow_ask){
                Py_DECREF(prompt);
                PyErr_SetString(PyExc_RuntimeError,"SANDBOX: ask() is disabled");
                goto exec_runtime_err;
            }
            PyObject *ps=mellow_format(prompt); Py_DECREF(prompt);
            PyObject *builtins=PyImport_ImportModule("builtins");
            PyObject *input_fn=builtins?PyObject_GetAttrString(builtins,"input"):NULL;
            Py_XDECREF(builtins);
            PyObject *raw=input_fn?PyObject_CallOneArg(input_fn,ps):PyUnicode_FromString("");
            Py_XDECREF(input_fn); Py_XDECREF(ps);
            if(!raw) raw=PyUnicode_FromString("");
            /* coerce */
            const char *rs=PyUnicode_AsUTF8(raw);
            PyObject *val=raw;
            if(rs){
                if(strcmp(rs,"true")==0){Py_DECREF(raw);val=Py_True;Py_INCREF(val);}
                else if(strcmp(rs,"false")==0){Py_DECREF(raw);val=Py_False;Py_INCREF(val);}
                else {
                    char *end; long li=strtol(rs,&end,10);
                    if(*end=='\0'){Py_DECREF(raw);val=PyLong_FromLong(li);}
                    else {
                        double df=strtod(rs,&end);
                        if(*end=='\0'){Py_DECREF(raw);val=PyFloat_FromDouble(df);}
                    }
                }
            }
            _PUSH(val); Py_DECREF(val); break;
        }

        /* ── SAVE / LOAD_F / SAVE_VAL ── */
        case OP_SAVE_VAL: {
            if (!vm->allow_storage) {
                PyErr_SetString(PyExc_RuntimeError, "SANDBOX: storage is disabled");
                goto exec_err;
            }
            PyObject *value=_POP(), *filename=_POP();
            PyObject *json=PyImport_ImportModule("json");
            if(json){
                PyObject *fs=cvm_storage_path(vm, filename);
                if(!fs || !storage_ensure_base(vm)){
                    Py_XDECREF(fs); Py_DECREF(json); Py_DECREF(value); Py_DECREF(filename); goto exec_err;
                }
                {
                    PyObject *encoded=PyObject_CallMethod(json,"dumps","O",value);
                    if(encoded){
                        const char *fn_s=PyUnicode_AsUTF8(fs);
                        if(fn_s){
                            FILE *f=fopen(fn_s,"w");
                            if(f){fputs(PyUnicode_AsUTF8(encoded),f);fclose(f);}
                        }
                        Py_DECREF(encoded);
                    }
                }
                Py_DECREF(fs);
                if (PyErr_Occurred()) { Py_DECREF(json); Py_DECREF(value); Py_DECREF(filename); goto exec_err; }
                Py_DECREF(json);
            }
            Py_DECREF(value); Py_DECREF(filename); break;
        }
        case OP_SAVE: {
            if (!vm->allow_storage) {
                PyErr_SetString(PyExc_RuntimeError, "SANDBOX: storage is disabled");
                goto exec_err;
            }
            PyObject *filename=_POP();
            PyObject *vname=_A1;
            PyObject *value=scope_get(vm->scopes,vm->ns,vname);
            if(!value) value=Py_None;
            PyObject *json=PyImport_ImportModule("json");
            if(json){
                PyObject *fs=cvm_storage_path(vm, filename);
                if(!fs || !storage_ensure_base(vm)){
                    Py_XDECREF(fs); Py_DECREF(json); Py_DECREF(filename); goto exec_err;
                }
                {
                    PyObject *encoded=PyObject_CallMethod(json,"dumps","O",value);
                    if(encoded){
                        const char *fn_s=PyUnicode_AsUTF8(fs);
                        if(fn_s){FILE *f=fopen(fn_s,"w");if(f){fputs(PyUnicode_AsUTF8(encoded),f);fclose(f);}}
                        Py_DECREF(encoded);
                    }
                }
                Py_DECREF(fs);
                if (PyErr_Occurred()) { Py_DECREF(json); Py_DECREF(filename); goto exec_err; }
                Py_DECREF(json);
            }
            Py_DECREF(filename); break;
        }
        case OP_LOAD_F: {
            if (!vm->allow_storage) {
                PyErr_SetString(PyExc_RuntimeError, "SANDBOX: storage is disabled");
                goto exec_err;
            }
            PyObject *filename=_POP();
            PyObject *vname=_A1;
            PyObject *loaded=Py_None;
            PyObject *fs=cvm_storage_path(vm, filename); Py_DECREF(filename);
            if(fs){
                const char *fn_s=PyUnicode_AsUTF8(fs);
                if(fn_s){
                    FILE *f=fopen(fn_s,"r");
                    if(f){
                        fseek(f,0,SEEK_END); long sz=ftell(f); fseek(f,0,SEEK_SET);
                        char *buf=(char*)malloc(sz+1);
                        if(buf){
                            fread(buf,1,sz,f); buf[sz]=0;
                            PyObject *json=PyImport_ImportModule("json");
                            if(json){
                                PyObject *s=PyUnicode_FromString(buf);
                                if(s){loaded=PyObject_CallMethod(json,"loads","O",s);Py_DECREF(s);}
                                if(!loaded){PyErr_Clear();loaded=Py_None;Py_INCREF(loaded);}
                                Py_DECREF(json);
                            }
                            free(buf);
                        }
                        fclose(f);
                    }
                }
                Py_DECREF(fs);
            } else {
                goto exec_err;
            }
            if(!loaded){loaded=Py_None;Py_INCREF(loaded);}
            PyDict_SetItem(vm->scopes[vm->ns-1],vname,loaded);
            Py_DECREF(loaded); break;
        }

        /* ── IMPORT ── */
        case OP_IMPORT: {
            PyObject *path=_A1, *alias=_A2;
            const char *path_c=PyUnicode_Check(path)?PyUnicode_AsUTF8(path):"";
            const char *alias_c=PyUnicode_Check(alias)?PyUnicode_AsUTF8(alias):"mod";
            /* compile + run via Python API */
            PyObject *comp_mod=PyImport_ImportModule("mellowlang.compiler");
            if(!comp_mod){PyErr_Clear();break;} /* silently skip if can't import */
            PyObject *Compiler=PyObject_GetAttrString(comp_mod,"Compiler");
            Py_DECREF(comp_mod);
            if(!Compiler){PyErr_Clear();break;}
            PyObject *compiler=PyObject_CallNoArgs(Compiler); Py_DECREF(Compiler);
            if(!compiler){PyErr_Clear();break;}

            /* read file */
            FILE *mf=fopen(path_c,"r");
            if(!mf){Py_DECREF(compiler);break;}
            fseek(mf,0,SEEK_END); long msz=ftell(mf); fseek(mf,0,SEEK_SET);
            char *mbuf=(char*)malloc(msz+1);
            if(!mbuf){fclose(mf);Py_DECREF(compiler);break;}
            fread(mbuf,1,msz,mf); mbuf[msz]=0; fclose(mf);

            PyObject *src=PyUnicode_FromString(mbuf); free(mbuf);
            if(!src){Py_DECREF(compiler);break;}
            PyObject *prog=PyObject_CallMethod(compiler,"compile","O",src);
            Py_DECREF(src); Py_DECREF(compiler);
            if(!prog){PyErr_Clear();break;}

            /* Extract bytecode + func_table from program */
            PyObject *mod_bc=PyObject_GetAttrString(prog,"bytecode");
            PyObject *mod_ft=PyObject_GetAttrString(prog,"func_table");
            Py_DECREF(prog);
            if(!mod_bc||!mod_ft){Py_XDECREF(mod_bc);Py_XDECREF(mod_ft);break;}

            Py_ssize_t mod_len=PyList_Check(mod_bc)?PyList_GET_SIZE(mod_bc):0;
            long offset=(long)vm->bc_len;

            /* Append module bytecode with patched addresses */
            if(mod_len>0){
                /* Simple append: patch JUMP/JIF targets */
                PyObject *Op=PyImport_ImportModule("mellowlang.constants");
                for(Py_ssize_t mi=0;mi<mod_len;mi++){
                    PyObject *ins=PyList_GET_ITEM(mod_bc,mi);
                    PyList_Append(vm->bytecode_obj, ins);
                }
                vm->bc_len += mod_len;
                if(Op) Py_DECREF(Op);
            }

            /* Register functions with alias prefix */
            if(PyDict_Check(mod_ft)){
                PyObject *k,*v; Py_ssize_t pos=0;
                while(PyDict_Next(mod_ft,&pos,&k,&v)){
                    PyObject *qualified=PyUnicode_FromFormat("%s.%U",alias_c,k);
                    if(qualified&&PyDict_Check(v)){
                        PyObject *new_meta=PyDict_Copy(v);
                        if(new_meta){
                            PyObject *old_addr=PyDict_GetItemString(v,"address");
                            if(old_addr){
                                long new_addr=PyLong_AsLong(old_addr)+offset;
                                PyObject *na=PyLong_FromLong(new_addr);
                                PyDict_SetItemString(new_meta,"address",na);
                                Py_DECREF(na);
                            }
                            PyDict_SetItem(vm->func_table,qualified,new_meta);
                            Py_DECREF(new_meta);
                        }
                        Py_DECREF(qualified);
                    }
                }
            }

            /* create namespace proxy object (a dict) */
            PyObject *ns_proxy=PyDict_New();
            if(ns_proxy){
                PyDict_SetItem(vm->scopes[vm->ns-1],alias,ns_proxy);
                Py_DECREF(ns_proxy);
            }

            Py_DECREF(mod_bc); Py_DECREF(mod_ft); break;
        }

        default: break; /* unknown op: skip */
        }

        pc++;
        continue;

exec_runtime_err:
        /* Runtime error — check try stack */
        if (vm->tsp > 0) {
            CvmTryFrame *tf = &vm->try_stack[--vm->tsp];
            /* restore stack */
            while (vm->sp > tf->stack_len && vm->sp > 0) Py_XDECREF(vm->stack[--vm->sp]);
            /* bind error name */
            if (tf->err_name && tf->err_name != Py_None && PyErr_Occurred()) {
                PyObject *etype,*eval,*etb;
                PyErr_Fetch(&etype,&eval,&etb);
                PyObject *emsg=eval?PyObject_Str(eval):PyUnicode_FromString("error");
                if(emsg){
                    PyDict_SetItem(vm->scopes[vm->ns-1], tf->err_name, emsg);
                    Py_DECREF(emsg);
                }
                Py_XDECREF(etype); Py_XDECREF(eval); Py_XDECREF(etb);
                PyErr_Clear();
            } else {
                PyErr_Clear();
            }
            if (tf->catch_pc >= 0) { pc = tf->catch_pc; continue; }
        }
        goto exec_err;
    }

exec_done:
    if(!exec_result){exec_result=vm->sp>0?vm->stack[vm->sp-1]:Py_None;Py_INCREF(exec_result);}
    return exec_result;

exec_err:
    return NULL;
}

#undef _PUSH
#undef _POP
#undef _TOP
#undef _A1
#undef _A2
#undef _A3
