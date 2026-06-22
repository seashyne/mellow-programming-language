/*
 * mellowvm_module.c — MellowLang C VM v1.5.0
 *
 * Full-system C VM: handles ALL opcodes natively.
 * No Python fallback needed for standard Mellow programs.
 *
 * Architecture:
 *   CVM struct  — shared execution state (stack, scopes, call stack, try stack)
 *   cvm_exec()  — main dispatch loop, reentrant (called recursively for HOF)
 *   cvm_call1() — call a single Mellow function by name, return result
 *   cvm_syscall()— full SYSCALL table (~70 builtins)
 *   mellowvm_run()— Python-facing entry point
 *
 * Build: cd MellowLang_v1_5_0 && python setup.py build_ext --inplace
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <math.h>
#include <string.h>
#include <stdlib.h>
#include <stdint.h>
#include <time.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

/* ── Opcodes ──────────────────────────────────────────────────────── */
#define OP_HALT        0
#define OP_PUSH        1
#define OP_STORE       2
#define OP_LOAD        3
#define OP_ADD         4
#define OP_SUB         5
#define OP_MUL         6
#define OP_DIV         7
#define OP_COMPARE     8
#define OP_PRINT       9
#define OP_JUMP        10
#define OP_JIF         11
#define OP_CALL        12
#define OP_RETURN      13
#define OP_ARG         14
#define OP_SHOW_PREC   15
#define OP_ASK         16
#define OP_RANDOM      17
#define OP_STOP        18
#define OP_WAIT        19
#define OP_SAVE        23
#define OP_LOAD_F      24
#define OP_LIST_HAS    25
#define OP_LIST_PUT    26
#define OP_BOOL_AND    27
#define OP_BOOL_OR     28
#define OP_BOOL_NOT    29
#define OP_SYSCALL     30
#define OP_POP         31
#define OP_SAVE_VAL    32
#define OP_GETITEM     33
#define OP_LEN         34
#define OP_BUILD_LIST  35
#define OP_BUILD_MAP   36
#define OP_TRY         37
#define OP_ENDTRY      38
#define OP_RANDFLOAT   39
#define OP_STORE_KEEP  40
#define OP_STORE_AUTO  41
#define OP_SEED        42
#define OP_GLOBAL_SEED 43
#define OP_PRINTN      44
#define OP_PUSH_FUNC   45
#define OP_CALL_VAL    46
#define OP_SLICE       47
#define OP_IMPORT      49
#define OP_MOD         50
#define OP_POW_OP      51

/* ── CVM State ──────────────────────────────────────────────────── */
#define CVM_MAX_STACK     4096
#define CVM_MAX_SCOPES    512
#define CVM_MAX_CS        512
#define CVM_MAX_TRY       32

/* sub-call limits (for HOF: map/filter/reduce) */
#define CVM_SUB_STACK     512
#define CVM_SUB_SCOPES    64
#define CVM_SUB_CS        64
#define CVM_SUB_TRY       8

typedef struct {
    int catch_pc;
    int finally_pc;
    PyObject *err_name; /* borrowed */
    int stack_len;
} CvmTryFrame;

typedef struct CVM {
    PyObject *bytecode_obj;   /* Python list — borrowed */
    Py_ssize_t bc_len;
    PyObject *func_table;     /* Python dict — borrowed */
    long *steps;              /* shared counter */
    long max_steps;

    PyObject **stack;
    int sp;
    int max_stack;

    PyObject **scopes;        /* array of dict* */
    int ns;                   /* # active scopes */
    int max_scopes;

    int *cs;                  /* call-return PC stack */
    int csp;
    int max_cs;

    CvmTryFrame *try_stack;
    int tsp;
    int max_try;

    /* RNG state (Python random.Random object) */
    PyObject *rng;            /* may be NULL */
    PyObject *host;           /* borrowed for the duration of run() */

    /* config */
    int allow_ask;
    int allow_wait;
    int allow_storage;
    PyObject *storage_dir;    /* owned by top-level VM, borrowed by sub-VMs */

    /* output capture buffer — NULL means write to real stdout */
    PyObject *capture_list;   /* list of strings, or NULL */
} CVM;

/* ── Forward declarations ──────────────────────────────────────── */
static PyObject *cvm_exec(CVM *vm, int start_pc);
static PyObject *cvm_call1(CVM *vm, PyObject *fn_ref,
                            PyObject **args, long argc);
static PyObject *cvm_syscall_dispatch(const char *sn,
                                      PyObject **sa, long argc,
                                      CVM *parent_vm);

static void cvm_attach_error_location(int pc)
{
    PyObject *type = NULL, *value = NULL, *traceback = NULL;
    PyObject *pc_value = NULL, *kind_value = NULL, *message_value = NULL;
    const char *message = NULL;

    if (!PyErr_Occurred()) return;
    PyErr_Fetch(&type, &value, &traceback);
    PyErr_NormalizeException(&type, &value, &traceback);
    if (!value) {
        value = PyObject_CallNoArgs(type ? type : PyExc_RuntimeError);
    }
    if (value) {
        pc_value = PyLong_FromLong(pc);
        message_value = PyObject_Str(value);
        message = message_value ? PyUnicode_AsUTF8(message_value) : NULL;
        kind_value = PyUnicode_FromString(
            message && strncmp(message, "SANDBOX:", 8) == 0 ? "SANDBOX" : "RUNTIME"
        );
        if (pc_value && PyObject_SetAttrString(value, "pc", pc_value) < 0) PyErr_Clear();
        if (kind_value && PyObject_SetAttrString(value, "kind", kind_value) < 0) PyErr_Clear();
        if (message_value && PyObject_SetAttrString(value, "msg", message_value) < 0) PyErr_Clear();
    }
    Py_XDECREF(pc_value);
    Py_XDECREF(kind_value);
    Py_XDECREF(message_value);
    PyErr_Restore(type, value, traceback);
}

/* ── String interning for hot comparisons ──────────────────────── */
/* We compare syscall names as C strings — fast enough */

/* ── Helpers ────────────────────────────────────────────────────── */

static int mellow_truthy(PyObject *v) {
    if (!v || v == Py_None || v == Py_False) return 0;
    if (v == Py_True) return 1;
    if (PyLong_CheckExact(v))  return PyLong_AsLong(v) != 0;
    if (PyFloat_CheckExact(v)) return PyFloat_AS_DOUBLE(v) != 0.0;
    if (PyUnicode_Check(v))    return PyUnicode_GET_LENGTH(v) > 0;
    if (PyList_Check(v))       return PyList_GET_SIZE(v) > 0;
    if (PyDict_Check(v))       return PyDict_Size(v) > 0;
    return 1;
}

static PyObject *fmt_list(PyObject *lst);
static PyObject *mellow_format(PyObject *v) {
    if (!v || v == Py_None)    return PyUnicode_FromString("None");
    if (v == Py_True)          return PyUnicode_FromString("True");
    if (v == Py_False)         return PyUnicode_FromString("False");
    if (PyLong_CheckExact(v))  return PyObject_Str(v);
    if (PyFloat_CheckExact(v)) {
        double d = PyFloat_AS_DOUBLE(v), ip;
        if (modf(d, &ip)==0.0 && fabs(d)<1e15) {
            PyObject *li = PyLong_FromDouble(d);
            if (!li) return NULL;
            PyObject *s = PyObject_Str(li); Py_DECREF(li); return s;
        }
        return PyObject_Str(v);
    }
    if (PyUnicode_Check(v)) { Py_INCREF(v); return v; }
    if (PyList_Check(v))    return fmt_list(v);
    if (PyDict_Check(v))    return PyObject_Repr(v);
    return PyObject_Str(v);
}

static int storage_name_unsafe(const char *raw) {
    if (!raw) return 0;
    if (raw[0] == '/' || raw[0] == '\\') return 1;
    if (((raw[0] >= 'A' && raw[0] <= 'Z') || (raw[0] >= 'a' && raw[0] <= 'z')) && raw[1] == ':') return 1;
    if (strcmp(raw, "..") == 0) return 1;
    if (strncmp(raw, "../", 3) == 0 || strncmp(raw, "..\\", 3) == 0) return 1;
    if (strstr(raw, "/../") || strstr(raw, "\\..\\") || strstr(raw, "/..\\") || strstr(raw, "\\../")) return 1;
    size_t n = strlen(raw);
    if (n >= 3 && (strcmp(raw + n - 3, "/..") == 0 || strcmp(raw + n - 3, "\\..") == 0)) return 1;
    return 0;
}

static int storage_ensure_base(CVM *vm) {
    PyObject *os_mod = PyImport_ImportModule("os");
    if (!os_mod) return 0;
    PyObject *makedirs = PyObject_GetAttrString(os_mod, "makedirs");
    Py_DECREF(os_mod);
    if (!makedirs) return 0;
    PyObject *args = PyTuple_Pack(1, vm->storage_dir);
    PyObject *kwargs = Py_BuildValue("{s:O}", "exist_ok", Py_True);
    PyObject *res = (args && kwargs) ? PyObject_Call(makedirs, args, kwargs) : NULL;
    Py_XDECREF(args);
    Py_XDECREF(kwargs);
    Py_DECREF(makedirs);
    if (!res) return 0;
    Py_DECREF(res);
    return 1;
}

static PyObject *cvm_storage_path(CVM *vm, PyObject *filename) {
    PyObject *fs = mellow_format(filename);
    if (!fs) return NULL;
    const char *raw = PyUnicode_AsUTF8(fs);
    if (!raw) {
        Py_DECREF(fs);
        return NULL;
    }
    while (*raw == ' ' || *raw == '\t' || *raw == '"' || *raw == '\'') raw++;
    if (storage_name_unsafe(raw)) {
        Py_DECREF(fs);
        PyErr_SetString(PyExc_RuntimeError, "SANDBOX: invalid storage path (path traversal blocked)");
        return NULL;
    }
    const char *name = (*raw == '\0' || strcmp(raw, ".") == 0) ? "save" : raw;
    int has_json = 0;
    size_t n = strlen(name);
    if (n >= 5 && strcmp(name + n - 5, ".json") == 0) has_json = 1;
    PyObject *path = PyUnicode_FromFormat(has_json ? "%U/%s" : "%U/%s.json", vm->storage_dir, name);
    Py_DECREF(fs);
    return path;
}
static PyObject *fmt_list(PyObject *lst) {
    Py_ssize_t n = PyList_GET_SIZE(lst);
    PyObject *parts = PyList_New(n);
    if (!parts) return NULL;
    for (Py_ssize_t i=0;i<n;i++) {
        PyObject *item = PyList_GET_ITEM(lst,i);
        PyObject *f;
        /* Match Python VM: str(val) — which uses repr for strings in lists */
        if (PyUnicode_Check(item)) {
            f = PyObject_Repr(item);  /* 'hello' not hello */
        } else {
            f = mellow_format(item);
        }
        if (!f){Py_DECREF(parts);return NULL;}
        PyList_SET_ITEM(parts,i,f);
    }
    PyObject *sep = PyUnicode_FromString(", ");
    PyObject *j   = PyUnicode_Join(sep,parts);
    Py_DECREF(sep); Py_DECREF(parts);
    if (!j) return NULL;
    PyObject *r = PyUnicode_FromFormat("[%U]", j);
    Py_DECREF(j); return r;
}

static double to_double(PyObject *v) {
    if (v==Py_True)  return 1.0;
    if (v==Py_False) return 0.0;
    if (PyLong_CheckExact(v)) return (double)PyLong_AsLong(v);
    if (PyFloat_CheckExact(v)) return PyFloat_AS_DOUBLE(v);
    if (PyUnicode_Check(v)) {
        const char *s = PyUnicode_AsUTF8(v);
        if (s) return atof(s);
    }
    return 0.0;
}
static long to_long(PyObject *v) {
    if (v==Py_True)  return 1;
    if (v==Py_False) return 0;
    if (PyLong_CheckExact(v)) return PyLong_AsLong(v);
    if (PyFloat_CheckExact(v)) return (long)PyFloat_AS_DOUBLE(v);
    if (PyUnicode_Check(v)) {
        const char *s = PyUnicode_AsUTF8(v);
        if (s) return atol(s);
    }
    return 0;
}

static PyObject *maybe_int(double d) {
    double ip; if (modf(d,&ip)==0.0 && fabs(d)<9e15) return PyLong_FromDouble(d);
    return PyFloat_FromDouble(d);
}

#define IS_INT(v) ((v) && PyLong_CheckExact(v) && (v)!=Py_True && (v)!=Py_False)

static PyObject *op_add(PyObject *a, PyObject *b) {
    if (PyUnicode_Check(a)||PyUnicode_Check(b)) {
        PyObject *sa=mellow_format(a),*sb=mellow_format(b);
        if(!sa||!sb){Py_XDECREF(sa);Py_XDECREF(sb);return NULL;}
        PyObject *r=PyUnicode_Concat(sa,sb); Py_DECREF(sa);Py_DECREF(sb); return r;
    }
    if (PyList_Check(a)&&PyList_Check(b)) return PySequence_Concat(a,b);
    if (IS_INT(a)&&IS_INT(b)) return PyLong_FromLong(PyLong_AsLong(a)+PyLong_AsLong(b));
    return maybe_int(to_double(a)+to_double(b));
}
static PyObject *op_sub(PyObject *a, PyObject *b) {
    if (IS_INT(a)&&IS_INT(b)) return PyLong_FromLong(PyLong_AsLong(a)-PyLong_AsLong(b));
    return maybe_int(to_double(a)-to_double(b));
}
static PyObject *op_mul(PyObject *a, PyObject *b) {
    if (PyUnicode_Check(a)&&IS_INT(b)) return PySequence_Repeat(a,(Py_ssize_t)PyLong_AsLong(b));
    if (IS_INT(a)&&IS_INT(b)) return PyLong_FromLong(PyLong_AsLong(a)*PyLong_AsLong(b));
    return maybe_int(to_double(a)*to_double(b));
}
static PyObject *op_div(PyObject *a, PyObject *b) {
    double db=to_double(b); if(db==0.0) return PyLong_FromLong(0);
    return maybe_int(to_double(a)/db);
}
static PyObject *op_mod(PyObject *a, PyObject *b) {
    if (IS_INT(a)&&IS_INT(b)) {
        long lb=PyLong_AsLong(b); if(!lb) return PyLong_FromLong(0);
        long r = PyLong_AsLong(a) % lb;
        if (r!=0 && (r<0)!=(lb<0)) r+=lb; /* Python-style sign */
        return PyLong_FromLong(r);
    }
    double db=to_double(b); if(db==0.0) return PyFloat_FromDouble(0.0);
    return maybe_int(fmod(to_double(a),db));
}
static PyObject *op_pow(PyObject *a, PyObject *b) {
    return maybe_int(pow(to_double(a),to_double(b)));
}
static PyObject *op_cmp(PyObject *a, PyObject *b, const char *op) {
    int res=0;
    if (strcmp(op,"==")==0) { int r=PyObject_RichCompareBool(a,b,Py_EQ); if(r<0){PyErr_Clear();r=0;} res=r; }
    else if (strcmp(op,"!=")==0) { int r=PyObject_RichCompareBool(a,b,Py_EQ); if(r<0){PyErr_Clear();r=0;} res=!r; }
    else {
        int cop = strcmp(op,"<")==0?Py_LT:strcmp(op,">")==0?Py_GT:strcmp(op,"<=")==0?Py_LE:Py_GE;
        int r=PyObject_RichCompareBool(a,b,cop); if(r<0){PyErr_Clear();r=0;} res=r;
    }
    return res?(Py_INCREF(Py_True),Py_True):(Py_INCREF(Py_False),Py_False);
}

static PyObject *make_func_ref(PyObject *name) {
    PyObject *tag=PyUnicode_FromString("__func__");
    if(!tag) return NULL;
    PyObject *t=PyTuple_Pack(2,tag,name); Py_DECREF(tag); return t;
}
static int is_func_ref(PyObject *v, PyObject **out) {
    if(!v||!PyTuple_Check(v)||PyTuple_GET_SIZE(v)!=2) return 0;
    PyObject *tag=PyTuple_GET_ITEM(v,0);
    if(!PyUnicode_Check(tag)) return 0;
    const char *s=PyUnicode_AsUTF8(tag);
    if(!s||strcmp(s,"__func__")!=0) return 0;
    if(out) *out=PyTuple_GET_ITEM(v,1);
    return 1;
}

/* scope lookup */
static PyObject *scope_get(PyObject **scopes, int ns, PyObject *name) {
    for (int i=ns-1;i>=0;i--) {
        PyObject *v=PyDict_GetItem(scopes[i],name);
        if (v) return v;
    }
    return NULL;
}

/* print to stdout or capture buffer */
static void cvm_print(CVM *vm, const char *s) {
    PySys_WriteStdout("%s\n", s);
}
static void cvm_printn(CVM *vm, const char **parts, int n) {
    for (int i=0;i<n;i++) {
        if (i>0) PySys_WriteStdout(" ");
        PySys_WriteStdout("%s", parts[i]);
    }
    PySys_WriteStdout("\n");
}

/* ================================================================
 * cvm_call1 — call a single Mellow function with args
 *   fn_ref: ("__func__", name) tuple
 *   args[0..argc-1]: arguments (borrowed refs)
 *   Returns new ref to result, or NULL on error.
 * ================================================================ */
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
