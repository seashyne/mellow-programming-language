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
