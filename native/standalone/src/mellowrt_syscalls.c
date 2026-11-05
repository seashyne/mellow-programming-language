#ifndef _WIN32
#define _POSIX_C_SOURCE 199309L
#endif

#include "mellowrt_syscalls.h"
#include "mellowrt_scheduler.h"
#include "mellowrt_money.h"
#include "mellowrt_ledger.h"
#include "mellowrt_storage.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#ifdef _WIN32
#include <direct.h>
#include <windows.h>
#else
#include <unistd.h>
#endif

#define MELLOW_NATIVE_CHANNEL_MAGIC 0x4d43484eu
#define MELLOW_NATIVE_CANVAS_MAGIC 0x4d434156u

typedef struct MellowNativeHeader {
    uint32_t magic;
    int marked;
    struct MellowNativeHeader *next;
} MellowNativeHeader;

typedef struct MellowChannel {
    uint32_t magic;
    int marked;
    MellowNativeHeader *next;
    MValue *items;
    size_t len;
    size_t cap;
} MellowChannel;

typedef struct MellowCanvas {
    uint32_t magic;
    int marked;
    MellowNativeHeader *next;
    int width;
    int height;
    unsigned char *pixels;
} MellowCanvas;

static void mark_value(MellowRuntimeContext *ctx, const MValue *value);
static void mark_channel_queue_values(void *user, MVM *vm);

#include "mellowrt_syscalls_part1.inc"
#include "mellowrt_random.inc"
#include "mellowrt_ai.inc"
#include "mellowrt_std.inc"
#include "mellowrt_syscalls_part2.inc"
#include "mellowrt_syscalls_part3.inc"
#include "mellowrt_syscalls_part4.inc"
