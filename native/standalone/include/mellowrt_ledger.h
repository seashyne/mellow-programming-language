#ifndef MELLOWRT_LEDGER_H
#define MELLOWRT_LEDGER_H

#include <stddef.h>
#include <stdint.h>

#include "mellowrt.h"

int mellowrt_ledger_syscall(
    int32_t id,
    const MValue *args,
    size_t argc,
    MValue *out_result,
    char *error,
    size_t error_cap
);

#endif
