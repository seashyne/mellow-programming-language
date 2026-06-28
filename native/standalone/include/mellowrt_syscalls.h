#ifndef MELLOWRT_SYSCALLS_H
#define MELLOWRT_SYSCALLS_H

#include "mellowrt.h"

typedef struct {
    int argc;
    char **argv;
    int script_arg_start;
    MVM *vm;
    uint64_t gc_collections;
    uint64_t gc_freed;
    uint64_t native_live;
    uint64_t native_allocated;
    uint64_t native_freed;
    uint64_t spawned_tasks;
    uint64_t yielded_tasks;
    uint64_t channel_count;
    uint64_t canvas_count;
    uint64_t scheduler_worker_changes;
    int recv_would_block;
    void *native_registry;
} MellowRuntimeContext;

int mellowrt_default_syscall(
    void *user,
    int32_t syscall_id,
    const MValue *args,
    size_t argc,
    MValue *out_result
);

void mellowrt_collect_garbage(MellowRuntimeContext *ctx);

#endif
