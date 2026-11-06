static PyObject *cvm_call1(CVM *parent_vm, PyObject *fn_ref,
                            PyObject **args, long argc)
{
    PyObject *fn_name = NULL;
    if (!is_func_ref(fn_ref, &fn_name)) {
        PyErr_SetString(PyExc_TypeError, "cvm_call1: not a func ref");
        return NULL;
    }
    PyObject *fn_meta = fn_name ? PyDict_GetItem(parent_vm->func_table, fn_name) : NULL;
    if (!fn_meta) {
        PyErr_Format(PyExc_RuntimeError, "cvm_call1: unknown function '%s'",
                     fn_name ? PyUnicode_AsUTF8(fn_name) : "?");
        return NULL;
    }
    PyObject *addr_obj = PyDict_GetItemString(fn_meta, "address");
    if (!addr_obj) { PyErr_SetString(PyExc_RuntimeError,"cvm_call1: no address"); return NULL; }
    int fn_addr = (int)PyLong_AsLong(addr_obj);

    /* param count + defaults */
    long pcount = 0;
    PyObject *pco = PyDict_GetItemString(fn_meta, "param_count");
    if (pco) pcount = PyLong_AsLong(pco);

    /* Build sub-CVM */
    PyObject *sub_stack_arr[CVM_SUB_STACK];
    PyObject *sub_scopes_arr[CVM_SUB_SCOPES];
    int       sub_cs_arr[CVM_SUB_CS];
    CvmTryFrame sub_try_arr[CVM_SUB_TRY];

    memset(sub_stack_arr, 0, sizeof(sub_stack_arr));
    memset(sub_scopes_arr, 0, sizeof(sub_scopes_arr));

    CVM sub;
    memset(&sub, 0, sizeof(sub));
    sub.bytecode_obj = parent_vm->bytecode_obj;
    sub.bc_len       = parent_vm->bc_len;
    sub.func_table   = parent_vm->func_table;
    sub.steps        = parent_vm->steps;
    sub.max_steps    = parent_vm->max_steps;
    sub.stack        = sub_stack_arr;
    sub.sp           = 0;
    sub.max_stack    = CVM_SUB_STACK;
    sub.scopes       = sub_scopes_arr;
    sub.ns           = 0;
    sub.max_scopes   = CVM_SUB_SCOPES;
    sub.cs           = sub_cs_arr;
    sub.csp          = 0;
    sub.max_cs       = CVM_SUB_CS;
    sub.try_stack    = sub_try_arr;
    sub.tsp          = 0;
    sub.max_try      = CVM_SUB_TRY;
    sub.rng          = parent_vm->rng;
    sub.host         = parent_vm->host;
    sub.allow_ask    = parent_vm->allow_ask;
    sub.allow_wait   = parent_vm->allow_wait;
    sub.allow_storage = parent_vm->allow_storage;
    sub.storage_dir = parent_vm->storage_dir;
    sub.config = parent_vm->config;
    sub.capture_list = parent_vm->capture_list;

    /* new scope for the function */
    sub.scopes[0] = PyDict_New();
    if (!sub.scopes[0]) return NULL;
    sub.ns = 1;

    /* push args (pad with None if fewer than pcount) */
    for (long i=0; i<pcount; i++) {
        PyObject *v = (i < argc) ? args[i] : Py_None;
        Py_INCREF(v);
        sub.stack[sub.sp++] = v;
    }

    /* sentinel return: csp=0 means top-level, RETURN will exit loop */
    /* we set start_pc to fn_addr, loop runs until RETURN with csp==0 */
    PyObject *result = cvm_exec(&sub, fn_addr);

    /* cleanup sub scope */
    for (int i=0; i<sub.ns; i++) Py_XDECREF(sub.scopes[i]);
    /* cleanup sub stack */
    for (int i=0; i<sub.sp; i++) Py_XDECREF(sub.stack[i]);

    return result; /* new ref or NULL */
}

/* Storage, fs and file syscalls live in their own include unit. */
#include "mellowvm_storage.inc"

/* Syscall implementation is isolated from the VM dispatch loop. */
#include "mellowvm_syscalls.inc"


/* Opcode execution is isolated from the Python module binding. */
#include "mellowvm_exec.inc"


/* ================================================================
 * mellowvm_run — Python-facing entry point
 * ================================================================ */
static PyObject *
mellowvm_run(PyObject *self, PyObject *args_in, PyObject *kwargs)
{
    static char *kwlist[]={"bytecode","func_table","config","event_table","host",NULL};
    PyObject *bytecode_obj=NULL,*func_table=NULL,*config_obj=NULL,*event_table=NULL,*host_obj=Py_None;
    if(!PyArg_ParseTupleAndKeywords(args_in,kwargs,"O|OOOO",kwlist,
            &bytecode_obj,&func_table,&config_obj,&event_table,&host_obj))
        return NULL;
    if(!PyList_Check(bytecode_obj)){
        PyErr_SetString(PyExc_TypeError,"bytecode must be a list"); return NULL;
    }

    /* func_table */
    int own_ft=0;
    if(!func_table||func_table==Py_None){func_table=PyDict_New();own_ft=1;}
    else Py_INCREF(func_table);

    /* config */
    long max_steps=5000000, max_stack_c=CVM_MAX_STACK;
    int allow_ask=0, allow_wait=1, allow_storage=1;
    PyObject *storage_dir = PyUnicode_FromString("mellow_saves");
    if (!storage_dir) return NULL;
    if(config_obj&&PyDict_Check(config_obj)){
        PyObject *ms=PyDict_GetItemString(config_obj,"max_steps");
        if(ms&&PyLong_Check(ms)) max_steps=PyLong_AsLong(ms);
        PyObject *mk=PyDict_GetItemString(config_obj,"max_stack");
        if(mk&&PyLong_Check(mk)) max_stack_c=PyLong_AsLong(mk);
        PyObject *aa=PyDict_GetItemString(config_obj,"allow_ask");
        if(aa) allow_ask=mellow_truthy(aa);
        PyObject *aw=PyDict_GetItemString(config_obj,"allow_wait");
        if(aw) allow_wait=mellow_truthy(aw);
        PyObject *as=PyDict_GetItemString(config_obj,"allow_storage");
        if(as) allow_storage=mellow_truthy(as);
        PyObject *sd=PyDict_GetItemString(config_obj,"storage_dir");
        if(sd){
            PyObject *sd_str=PyObject_Str(sd);
            if(sd_str){ Py_DECREF(storage_dir); storage_dir=sd_str; }
        }
    }
    if(max_stack_c>CVM_MAX_STACK) max_stack_c=CVM_MAX_STACK;

    /* Allocate CVM */
    PyObject **stack=(PyObject**)calloc((size_t)max_stack_c,sizeof(PyObject*));
    PyObject **scopes=(PyObject**)calloc(CVM_MAX_SCOPES,sizeof(PyObject*));
    int *cs=(int*)calloc(CVM_MAX_CS,sizeof(int));
    CvmTryFrame *try_stk=(CvmTryFrame*)calloc(CVM_MAX_TRY,sizeof(CvmTryFrame));
    if(!stack||!scopes||!cs||!try_stk){
        free(stack);free(scopes);free(cs);free(try_stk);
        Py_DECREF(func_table);
        Py_DECREF(storage_dir);
        return PyErr_NoMemory();
    }

    scopes[0]=PyDict_New();
    if(!scopes[0]){free(stack);free(scopes);free(cs);free(try_stk);Py_DECREF(func_table);Py_DECREF(storage_dir);return NULL;}

    /* seed C rng */
    srand((unsigned)time(NULL));

    long steps=0;
    CVM vm;
    memset(&vm,0,sizeof(vm));
    vm.bytecode_obj = bytecode_obj;
    vm.bc_len       = PyList_GET_SIZE(bytecode_obj);
    vm.func_table   = func_table;
    vm.steps        = &steps;
    vm.max_steps    = max_steps;
    vm.stack        = stack;
    vm.sp           = 0;
    vm.max_stack    = (int)max_stack_c;
    vm.scopes       = scopes;
    vm.ns           = 1;
    vm.max_scopes   = CVM_MAX_SCOPES;
    vm.cs           = cs;
    vm.csp          = 0;
    vm.max_cs       = CVM_MAX_CS;
    vm.try_stack    = try_stk;
    vm.tsp          = 0;
    vm.max_try      = CVM_MAX_TRY;
    vm.rng          = NULL;
    vm.host         = host_obj;
    vm.allow_ask    = allow_ask;
    vm.allow_wait   = allow_wait;
    vm.allow_storage = allow_storage;
    vm.storage_dir = storage_dir;
    vm.config = config_obj;
    vm.capture_list = NULL;

    PyObject *result = cvm_exec(&vm, 0);

    /* cleanup */
    for(int i=0;i<vm.sp;i++) Py_XDECREF(vm.stack[i]);
    for(int i=0;i<vm.ns;i++) Py_XDECREF(vm.scopes[i]);
    Py_XDECREF(vm.rng);
    Py_DECREF(storage_dir);
    free(stack); free(scopes); free(cs); free(try_stk);
    Py_DECREF(func_table);

    return result; /* new ref or NULL with exception set */
}


static PyObject *
mellowvm_capabilities(PyObject *self, PyObject *Py_UNUSED(args))
{
    return Py_BuildValue("{s:O,s:O,s:O,s:O,s:O,s:O,s:O,s:O,s:s,s:s}",
        "available", Py_True,
        "native_execution", Py_True,
        "native_stdlib_parity", Py_True,
        "native_data_transforms", Py_True,
        "conditional_breakpoints", Py_False,
        "watch_expressions", Py_False,
        "typed_frame_snapshots", Py_False,
        "source_span_parity", Py_True,
        "native_parity_level", "core-complete+money+data+ledger",
        "notes", "Native C execution has complete Mellow Core Profile and source-span parity plus money, data, and ledger stdlib services; debugger, event, and replay hooks still route through Python."
    );
}

/* ── Module ──────────────────────────────────────────────────────── */
static PyMethodDef methods[]={
    {"run",(PyCFunction)mellowvm_run,METH_VARARGS|METH_KEYWORDS,
     "Run MellowLang bytecode in native C VM v1.5.0.\n"
     "Args: bytecode, func_table=None, config=None, event_table=None, host=None\n"
     "Handles all standard opcodes and ~70 builtin syscalls natively.\n"
     "No Python fallback needed for pure Mellow programs."},
    {"capabilities",(PyCFunction)mellowvm_capabilities,METH_NOARGS,
     "Return native execution/debug parity metadata for the loaded extension."},
    {NULL,NULL,0,NULL}
};
static struct PyModuleDef mod={
    PyModuleDef_HEAD_INIT,"_mellowvm",
    "MellowLang C VM v1.5.0 — full system native execution",
    -1,methods
};
PyMODINIT_FUNC PyInit__mellowvm(void){return PyModule_Create(&mod);}
