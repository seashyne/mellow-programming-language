#ifndef MELLOWRT_SYSCALLS_H
#define MELLOWRT_SYSCALLS_H

#include "mellowrt.h"

/* MT19937 state, seeded the same way CPython's random.Random(seed) is, so a
 * Mellow program gets the same sequence on the standalone runtime without
 * linking a Python host. */
typedef struct {
    uint32_t state[624];
    int index;
    int gauss_valid;
    double gauss_next;
} MRngState;

typedef struct {
    int argc;
    char **argv;
    int script_arg_start;
    int64_t rng_seed;
    int rng_seed_set;
    int rng_ready;
    MRngState rng;
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
    char storage_dir[512];
    MValue server_request;
    MValue server_response_body;
    int server_response_set;
    int server_response_status;
    char server_response_content_type[64];
    char syscall_error[256];
} MellowRuntimeContext;

int mellowrt_default_syscall(
    void *user,
    int32_t syscall_id,
    const MValue *args,
    size_t argc,
    MValue *out_result
);

/* Resolve a syscall name (behaviour-tree leaves) to its runtime id. */
int mellowrt_builtin_lookup(const char *name, size_t len);

void mellowrt_collect_garbage(MellowRuntimeContext *ctx);

#endif
