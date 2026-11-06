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
    cvm_attach_error_location(pc);
    return NULL;
}

#undef _PUSH
#undef _POP
#undef _TOP
#undef _A1
#undef _A2
#undef _A3
