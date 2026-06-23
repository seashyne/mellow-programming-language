/*
 * Experimental Mellow Runtime embedding ABI.
 *
 * The standalone C runtime remains the release-authoritative execution path.
 * This header is a provisional host-facing wrapper that will be hardened over
 * later releases before being treated as stable ABI.
 */
#ifndef MELLOW_RUNTIME_H
#define MELLOW_RUNTIME_H

#include "mellowrt.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct MellowRuntime MellowRuntime;

typedef struct {
    uint64_t collections;
    uint64_t heap_allocated;
    uint64_t heap_freed;
    uint64_t heap_live;
    uint64_t heap_last_gc_freed;
    uint64_t native_allocated;
    uint64_t native_freed;
    uint64_t native_live;
    uint64_t native_last_gc_freed;
} MellowRuntimeGCStats;

typedef struct {
    MNativeProgram native;
    MProgram view;
} MellowCompiledProgram;

MellowRuntime *mellow_runtime_new(void);
void mellow_runtime_free(MellowRuntime *runtime);

void mellow_runtime_set_argv(MellowRuntime *runtime, int argc, char **argv, int script_arg_start);

int mellow_runtime_compile_source(
    MellowRuntime *runtime,
    const char *source,
    const char *source_name,
    MellowCompiledProgram *out_program,
    char *error,
    size_t error_cap
);

int mellow_runtime_compile_file(
    MellowRuntime *runtime,
    const char *path,
    MellowCompiledProgram *out_program,
    char *error,
    size_t error_cap
);

void mellow_runtime_program_free(MellowCompiledProgram *program);

int mellow_runtime_run_program(
    MellowRuntime *runtime,
    const MellowCompiledProgram *program,
    MRunResult *out_result
);

MellowRuntimeGCStats mellow_runtime_gc_collect(MellowRuntime *runtime);
MellowRuntimeGCStats mellow_runtime_gc_stats(const MellowRuntime *runtime);

#ifdef __cplusplus
}
#endif

#endif
