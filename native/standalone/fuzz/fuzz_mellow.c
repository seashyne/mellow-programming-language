#include "mellowrt.h"

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define MELLOW_FUZZ_MAX_SOURCE (64u * 1024u)

static int fuzz_syscall(
    void *user,
    int32_t syscall_id,
    const MValue *args,
    size_t argc,
    MValue *out_result
) {
    (void)user;
    (void)syscall_id;
    (void)args;
    (void)argc;
    *out_result = mval_none();
    return 1;
}

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size)
{
    char *source;
    char error[512] = {0};
    MNativeProgram native;

    if (size > MELLOW_FUZZ_MAX_SOURCE) return 0;
    source = (char *)malloc(size + 1);
    if (!source) return 0;
    if (size) memcpy(source, data, size);
    source[size] = '\0';

    memset(&native, 0, sizeof(native));
    if (mellow_compile_source(source, "<fuzz>", &native, error, sizeof(error))) {
        MProgram program = {
            native.code,
            native.code_len,
            native.consts,
            native.const_len,
            native.spans,
            native.span_len,
            native.source_name,
        };
        MRunResult result;
        MVM vm;
        memset(&result, 0, sizeof(result));
        mvm_init(&vm);
        vm.syscall.fn = fuzz_syscall;
        (void)mvm_run(&vm, &program, &result);
        mvm_free(&vm);
        mellow_native_program_free(&native);
    }
    free(source);
    return 0;
}
