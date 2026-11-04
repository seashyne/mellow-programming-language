#include "mellowrt.h"
#include "mellowrt_syscalls.h"
#include "mellowrt_scheduler.h"

#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

typedef enum {
    MHEAP_STR = 1,
    MHEAP_LIST_ITEMS = 2,
    MHEAP_MAP_KEYS = 3,
    MHEAP_MAP_VALUES = 4
} MHeapKind;

typedef struct MHeapBlock {
    void *ptr;
    size_t bytes;
    MHeapKind kind;
    int marked;
    MVM *owner;
    struct MHeapBlock *next;
} MHeapBlock;

static MHeapBlock *g_heap_blocks = NULL;

#include "mellowrt_core_part1.inc"
#include "mellowrt_core_part2.inc"
#include "mellowrt_core_part3.inc"
#include "mellowrt_core_part4.inc"
