#ifndef MELLOWRT_STORAGE_H
#define MELLOWRT_STORAGE_H

#include <stddef.h>
#include <stdint.h>

#include "mellowrt.h"

/* Storage, save and file syscalls. `storage_dir` is the mutable sandbox base
   the script may move with storage_dir(); it always stays relative to the
   working directory, matching the default the Python VM uses. */
int mellowrt_storage_syscall(
    int32_t id,
    const MValue *args,
    size_t argc,
    MValue *out_result,
    char *storage_dir,
    size_t storage_dir_cap,
    char *error,
    size_t error_cap
);

#endif
