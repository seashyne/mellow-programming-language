#include "mellow_runtime.h"
#include "mellowrt_syscalls.h"

#include <stdlib.h>
#include <string.h>

struct MellowRuntime {
    MellowRuntimeContext ctx;
};

static void refresh_view(MellowCompiledProgram *program) {
    if (!program) return;
    program->view.code = program->native.code;
    program->view.code_len = program->native.code_len;
    program->view.const_pool = program->native.consts;
    program->view.const_len = program->native.const_len;
    program->view.span_map = program->native.spans;
    program->view.span_len = program->native.span_len;
    program->view.source_name = program->native.source_name;
}

MellowRuntime *mellow_runtime_new(void) {
    MellowRuntime *runtime = (MellowRuntime *)calloc(1, sizeof(MellowRuntime));
    return runtime;
}

void mellow_runtime_free(MellowRuntime *runtime) {
    if (!runtime) return;
    mellowrt_collect_garbage(&runtime->ctx);
    free(runtime);
}

void mellow_runtime_set_argv(MellowRuntime *runtime, int argc, char **argv, int script_arg_start) {
    if (!runtime) return;
    runtime->ctx.argc = argc;
    runtime->ctx.argv = argv;
    runtime->ctx.script_arg_start = script_arg_start;
}

int mellow_runtime_compile_source(
    MellowRuntime *runtime,
    const char *source,
    const char *source_name,
    MellowCompiledProgram *out_program,
    char *error,
    size_t error_cap
) {
    (void)runtime;
    if (!out_program) return 0;
    memset(out_program, 0, sizeof(*out_program));
    if (!mellow_compile_source(source, source_name, &out_program->native, error, error_cap)) return 0;
    refresh_view(out_program);
    return 1;
}

int mellow_runtime_compile_file(
    MellowRuntime *runtime,
    const char *path,
    MellowCompiledProgram *out_program,
    char *error,
    size_t error_cap
) {
    (void)runtime;
    if (!out_program) return 0;
    memset(out_program, 0, sizeof(*out_program));
    if (!mellow_compile_file(path, &out_program->native, error, error_cap)) return 0;
    refresh_view(out_program);
    return 1;
}

void mellow_runtime_program_free(MellowCompiledProgram *program) {
    if (!program) return;
    mellow_native_program_free(&program->native);
    memset(program, 0, sizeof(*program));
}

int mellow_runtime_run_program(
    MellowRuntime *runtime,
    const MellowCompiledProgram *program,
    MRunResult *out_result
) {
    MVM vm;
    int ok;
    if (!runtime || !program || !out_result) return 0;
    mvm_init(&vm);
    runtime->ctx.vm = &vm;
    vm.syscall.fn = mellowrt_default_syscall;
    vm.syscall.user = &runtime->ctx;
    ok = mvm_run(&vm, &program->view, out_result);
    mvm_gc_collect(&vm);
    mellowrt_collect_garbage(&runtime->ctx);
    runtime->ctx.vm = NULL;
    mvm_free(&vm);
    mellowrt_collect_garbage(&runtime->ctx);
    return ok && !out_result->failed;
}

MellowRuntimeGCStats mellow_runtime_gc_collect(MellowRuntime *runtime) {
    if (runtime && runtime->ctx.vm) mvm_gc_collect(runtime->ctx.vm);
    if (runtime) mellowrt_collect_garbage(&runtime->ctx);
    return mellow_runtime_gc_stats(runtime);
}

MellowRuntimeGCStats mellow_runtime_gc_stats(const MellowRuntime *runtime) {
    MellowRuntimeGCStats stats;
    memset(&stats, 0, sizeof(stats));
    if (!runtime) return stats;
    stats.collections = runtime->ctx.gc_collections;
    stats.native_allocated = runtime->ctx.native_allocated;
    stats.native_freed = runtime->ctx.native_freed;
    stats.native_live = runtime->ctx.native_live;
    stats.native_last_gc_freed = runtime->ctx.gc_freed;
    if (runtime->ctx.vm) {
        stats.heap_allocated = runtime->ctx.vm->heap_allocated;
        stats.heap_freed = runtime->ctx.vm->heap_freed;
        stats.heap_live = runtime->ctx.vm->heap_live;
        stats.heap_last_gc_freed = runtime->ctx.vm->heap_last_gc_freed;
    }
    return stats;
}
