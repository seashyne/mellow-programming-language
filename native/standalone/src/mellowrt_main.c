/* mellowrt_main.c — v2.3.4 standalone runner
   Loads an MLVI binary image and executes it with mellowrt_core.
   No Python dependency. Build: cmake -S . -B build && cmake --build build
*/
#include "mellowrt.h"
#include "mellowrt_pkg.h"
#include "mellowrt_syscalls.h"
#include "mellowrt_sm_cli.h"
#include "mellowrt_server.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

#define MLVI_MAGIC     "MLVI0200"
#define MLVI_MAGIC_LEN 8

/* ── image structures ────────────────────────────────────────────────────── */
typedef struct { uint32_t slot; char *name; } MLoadedGlobal;
typedef struct { char *name; uint32_t address; uint16_t arity; uint16_t local_count; uint16_t flags; } MLoadedFunction;
typedef struct { char *name; uint32_t target; uint32_t flags; } MLoadedEvent;
typedef struct { char *name; uint32_t flags; } MLoadedModule;

typedef struct {
    MValue        *consts;       size_t const_len;
    MInstruction  *code;         size_t code_len;
    MSourceSpan   *spans;        size_t span_len;
    char          *source_name;
    char          *pipeline;
    MLoadedGlobal    *globals;   size_t globals_len;
    MLoadedFunction  *functions; size_t functions_len;
    MLoadedEvent     *events;    size_t events_len;
    MLoadedModule    *modules;   size_t modules_len;
} MLoadedProgram;

/* ── binary readers ──────────────────────────────────────────────────────── */
#include "mellowrt_main_part1.inc"
#include "mellowrt_main_part2.inc"
