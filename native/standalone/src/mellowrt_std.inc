/* The data standard library: one translation unit of numbered fragments.
 *
 * Included by mellowrt_syscalls.c after mellowrt_ai.inc so the shared value
 * and text helpers are already defined. Every fragment stays under the
 * 300-line ceiling; the router lives in the last one and is called from the
 * default syscall branch before the AI fallback. */

#ifndef MELLOWRT_STD_INC
#define MELLOWRT_STD_INC

#include "mellowrt_std_part1.inc"
#include "mellowrt_std_part2.inc"
#include "mellowrt_std_part3.inc"
#include "mellowrt_std_part4.inc"
#include "mellowrt_std_part5.inc"
#include "mellowrt_std_part6.inc"
#include "mellowrt_std_part7.inc"
#include "mellowrt_std_part8.inc"
#include "mellowrt_std_part9.inc"

#endif /* MELLOWRT_STD_INC */
