/* Mellow standalone compiler: loop-shape recognizers and their fast emitters.
 *
 * Included by mellowc.c between the shared scanner helpers and the statement
 * dispatcher. Each emit_fast_*_loop() inspects one while-loop body shape and,
 * when it matches, emits a single fused bytecode instruction instead of the
 * generic sequence. Adding a shape here means adding a MOP_* opcode and a
 * matching executor in mellowrt_core.c; nothing outside mellowc.c needs to
 * know these functions exist, so the file is included, not compiled.
 */

#include "mellowc_fastloops_part1.inc"
#include "mellowc_fastloops_part2.inc"
#include "mellowc_fastloops_part3.inc"
