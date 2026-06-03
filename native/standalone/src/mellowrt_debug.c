#include "mellowrt.h"

#include <stdio.h>

int mellowrt_debug_log_snapshot(void *user, const MDebugSnapshot *snapshot) {
    (void)user;
    if (!snapshot || !snapshot->insn) return 1;
    fprintf(stderr,
            "[mellowrt] pc=%u opcode=%u stack=%zu locals=%zu frames=%zu\n",
            snapshot->pc,
            (unsigned)snapshot->insn->opcode,
            snapshot->stack_len,
            snapshot->locals_len,
            snapshot->frame_len);
    return 1;
}
