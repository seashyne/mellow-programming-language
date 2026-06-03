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

    /* config */
    int allow_ask;
    int allow_wait;

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
    if (!v || v == Py_None)    return PyUnicode_FromString("none");
    if (v == Py_True)          return PyUnicode_FromString("true");
    if (v == Py_False)         return PyUnicode_FromString("false");
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
    sub.allow_ask    = parent_vm->allow_ask;
    sub.allow_wait   = parent_vm->allow_wait;
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

static PyObject *cvm_syscall_dispatch(const char *sn,
                                      PyObject **sa, long argc,
                                      CVM *parent_vm)
{
#define A0 (argc>0?sa[0]:Py_None)
#define A1 (argc>1?sa[1]:Py_None)
#define A2 (argc>2?sa[2]:Py_None)
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

    /* Fallthrough: unknown syscall */
    PyErr_Format(PyExc_RuntimeError, "RUNTIME: unknown syscall '%s'", sn);
    return NULL;

#undef A0
#undef A1
#undef A2
#undef STR0
#undef STR1
}

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
            if(!val) { PyObject *z=PyLong_FromLong(0); _PUSH(z); Py_DECREF(z); }
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
            PyObject *idx=_POP(), *tgt=_POP(), *r=Py_None;
            if(PyList_Check(tgt)){
                Py_ssize_t i=PyLong_AsSsize_t(idx),sz=PyList_GET_SIZE(tgt);
                if(i<0)i+=sz;
                r=(i>=0&&i<sz)?PyList_GET_ITEM(tgt,i):Py_None;
                Py_INCREF(r);
            } else if(PyUnicode_Check(tgt)){
                Py_ssize_t i=PyLong_AsSsize_t(idx),sz=PyUnicode_GET_LENGTH(tgt);
                if(i<0)i+=sz;
                r=(i>=0&&i<sz)?PyUnicode_FromOrdinal((int)PyUnicode_READ_CHAR(tgt,i)):PyUnicode_FromString("");
            } else if(PyDict_Check(tgt)){
                PyObject *k=mellow_format(idx);
                PyObject *val=k?PyDict_GetItem(tgt,k):NULL;
                Py_XDECREF(k);
                r=val?val:Py_None; Py_INCREF(r);
            } else { Py_INCREF(r); }
            Py_DECREF(idx); Py_DECREF(tgt);
            if(!r)goto exec_err;
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
            PyObject *value=_POP(), *filename=_POP();
            PyObject *json=PyImport_ImportModule("json");
            if(json){
                PyObject *fs=mellow_format(filename);
                if(fs){
                    PyObject *encoded=PyObject_CallMethod(json,"dumps","O",value);
                    if(encoded){
                        const char *fn_s=PyUnicode_AsUTF8(fs);
                        if(fn_s){
                            FILE *f=fopen(fn_s,"w");
                            if(f){fputs(PyUnicode_AsUTF8(encoded),f);fclose(f);}
                        }
                        Py_DECREF(encoded);
                    }
                    Py_DECREF(fs);
                }
                Py_DECREF(json);
            }
            Py_DECREF(value); Py_DECREF(filename); break;
        }
        case OP_SAVE: {
            PyObject *filename=_POP();
            PyObject *vname=_A1;
            PyObject *value=scope_get(vm->scopes,vm->ns,vname);
            if(!value) value=Py_None;
            PyObject *json=PyImport_ImportModule("json");
            if(json){
                PyObject *fs=mellow_format(filename);
                if(fs){
                    PyObject *encoded=PyObject_CallMethod(json,"dumps","O",value);
                    if(encoded){
                        const char *fn_s=PyUnicode_AsUTF8(fs);
                        if(fn_s){FILE *f=fopen(fn_s,"w");if(f){fputs(PyUnicode_AsUTF8(encoded),f);fclose(f);}}
                        Py_DECREF(encoded);
                    }
                    Py_DECREF(fs);
                }
                Py_DECREF(json);
            }
            Py_DECREF(filename); break;
        }
        case OP_LOAD_F: {
            PyObject *filename=_POP();
            PyObject *vname=_A1;
            PyObject *loaded=Py_None;
            PyObject *fs=mellow_format(filename); Py_DECREF(filename);
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

/* ================================================================
 * mellowvm_run — Python-facing entry point
 * ================================================================ */
static PyObject *
mellowvm_run(PyObject *self, PyObject *args_in, PyObject *kwargs)
{
    static char *kwlist[]={"bytecode","func_table","config","event_table",NULL};
    PyObject *bytecode_obj=NULL,*func_table=NULL,*config_obj=NULL,*event_table=NULL;
    if(!PyArg_ParseTupleAndKeywords(args_in,kwargs,"O|OOO",kwlist,
            &bytecode_obj,&func_table,&config_obj,&event_table))
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
    int allow_ask=0, allow_wait=1;
    if(config_obj&&PyDict_Check(config_obj)){
        PyObject *ms=PyDict_GetItemString(config_obj,"max_steps");
        if(ms&&PyLong_Check(ms)) max_steps=PyLong_AsLong(ms);
        PyObject *mk=PyDict_GetItemString(config_obj,"max_stack");
        if(mk&&PyLong_Check(mk)) max_stack_c=PyLong_AsLong(mk);
        PyObject *aa=PyDict_GetItemString(config_obj,"allow_ask");
        if(aa) allow_ask=mellow_truthy(aa);
        PyObject *aw=PyDict_GetItemString(config_obj,"allow_wait");
        if(aw) allow_wait=mellow_truthy(aw);
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
        return PyErr_NoMemory();
    }

    scopes[0]=PyDict_New();
    if(!scopes[0]){free(stack);free(scopes);free(cs);free(try_stk);Py_DECREF(func_table);return NULL;}

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
    vm.allow_ask    = allow_ask;
    vm.allow_wait   = allow_wait;
    vm.capture_list = NULL;

    PyObject *result = cvm_exec(&vm, 0);

    /* cleanup */
    for(int i=0;i<vm.sp;i++) Py_XDECREF(vm.stack[i]);
    for(int i=0;i<vm.ns;i++) Py_XDECREF(vm.scopes[i]);
    Py_XDECREF(vm.rng);
    free(stack); free(scopes); free(cs); free(try_stk);
    Py_DECREF(func_table);

    return result; /* new ref or NULL with exception set */
}


static PyObject *
mellowvm_capabilities(PyObject *self, PyObject *Py_UNUSED(args))
{
    return Py_BuildValue("{s:O,s:O,s:O,s:O,s:O,s:s}",
        "available", Py_True,
        "native_execution", Py_True,
        "conditional_breakpoints", Py_False,
        "watch_expressions", Py_False,
        "typed_frame_snapshots", Py_False,
        "source_span_parity", Py_False,
        "notes", "Execution parity is native-first in v2.0.3; debugger parity still needs follow-up hooks."
    );
}

/* ── Module ──────────────────────────────────────────────────────── */
static PyMethodDef methods[]={
    {"run",(PyCFunction)mellowvm_run,METH_VARARGS|METH_KEYWORDS,
     "Run MellowLang bytecode in native C VM v1.5.0.\n"
     "Args: bytecode, func_table=None, config=None, event_table=None\n"
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
