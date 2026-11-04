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
    PyObject *config;         /* run config dict — borrowed, sandbox policy reads */

    /* output capture buffer — NULL means write to real stdout */
    PyObject *capture_list;   /* list of strings, or NULL */
} CVM;

/* ── Forward declarations ──────────────────────────────────────── */
static PyObject *cvm_exec(CVM *vm, int start_pc);
#include "mellowvm_module_part1.inc"
#include "mellowvm_module_part2.inc"
