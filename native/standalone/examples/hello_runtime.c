#include "mellow_runtime.h"

#include <stdio.h>

int main(void) {
    const char *source = "print(\"Hello from embedded Mellow Runtime\")\n";
    char error[512] = {0};
    MellowCompiledProgram program;
    MRunResult result;
    MellowRuntime *runtime = mellow_runtime_new();
    if (!runtime) return 1;

    if (!mellow_runtime_compile_source(runtime, source, "<embed>", &program, error, sizeof(error))) {
        fprintf(stderr, "%s\n", error[0] ? error : "compile failed");
        mellow_runtime_free(runtime);
        return 1;
    }

    if (!mellow_runtime_run_program(runtime, &program, &result)) {
        fprintf(stderr, "runtime error: %s\n", result.error_message ? result.error_message : "unknown");
        mellow_runtime_program_free(&program);
        mellow_runtime_free(runtime);
        return 1;
    }

    mellow_runtime_program_free(&program);
    mellow_runtime_free(runtime);
    return 0;
}
