/* The AI and random runtime: one translation unit of numbered fragments.
 *
 * Included by mellowrt_syscalls.c after the value helpers it builds on.
 * Every fragment stays under the 300-line ceiling; the dispatcher lives in
 * the last one and is called from the default syscall branch. */

#ifndef MELLOWRT_AI_INC
#define MELLOWRT_AI_INC

#include <ctype.h>
#include <errno.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#ifdef _WIN32
#include <direct.h>
#include <windows.h>
#else
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#endif

#include "mellowrt_ai_part1.inc"
#include "mellowrt_ai_part2.inc"
#include "mellowrt_ai_part3.inc"
#include "mellowrt_ai_part4.inc"
#include "mellowrt_ai_part5.inc"
#include "mellowrt_ai_part6.inc"
#include "mellowrt_ai_part7.inc"
#include "mellowrt_ai_part8.inc"
#include "mellowrt_ai_part9.inc"
#include "mellowrt_ai_part10.inc"
#include "mellowrt_ai_part11.inc"
#include "mellowrt_ai_part12.inc"
#include "mellowrt_ai_part13.inc"
#include "mellowrt_ai_part14.inc"
#include "mellowrt_ai_part15.inc"
#include "mellowrt_ai_part16.inc"
#include "mellowrt_ai_part17.inc"
#include "mellowrt_ai_part18.inc"
#include "mellowrt_ai_part19.inc"
#include "mellowrt_ai_part20.inc"

#endif /* MELLOWRT_AI_INC */
