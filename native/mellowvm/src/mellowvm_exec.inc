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

#include "mellowvm_exec_part1.inc"
#include "mellowvm_exec_part2.inc"
#include "mellowvm_exec_part3.inc"
