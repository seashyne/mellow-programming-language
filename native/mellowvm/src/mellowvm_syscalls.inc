/* ================================================================
 * cvm_syscall_dispatch — full SYSCALL table
 * sa[0..argc-1] are borrowed refs from the stack
 * Returns new ref to result, or NULL on error.
 * If sn is unknown, sets RuntimeError and returns NULL.
 * ================================================================ */

/* helper: coerce to Python float */
#include "mellowvm_syscalls_part1.inc"
#include "mellowvm_syscalls_part2.inc"
#include "mellowvm_syscalls_part3.inc"
#include "mellowvm_syscalls_part4.inc"
