/* mellowvm_storage.inc — storage, fs and file syscalls for the native VM.
 *
 * Included by mellowvm_module.c before mellowvm_syscalls.inc. Kept separate so
 * the dispatcher in mellowvm_syscalls.inc stays focused on pure stdlib maths.
 * Sandbox semantics mirror src/mellowlang/vm/storage.py.
 */

/* ── storage / fs / file helpers ──────────────────────────────────────
   Path handling mirrors src/mellowlang/vm/storage.py so the native and
   Python engines agree on what a script is allowed to reach.           */

static PyObject *sv_clean(PyObject *value, int lstrip_slash);

#include "mellowvm_storage_part1.inc"
#include "mellowvm_storage_part2.inc"
#include "mellowvm_storage_part3.inc"
