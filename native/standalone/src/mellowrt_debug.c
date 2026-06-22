#include "mellowrt.h"

#include <stdio.h>

int mellowrt_debug_log_snapshot(void *user, const MDebugSnapshot *snapshot) {
    (void)user;
    if (!snapshot || !snapshot->insn) return 1;
    fprintf(stderr,
            "[mellowrt] pc=%u opcode=%u stack=%llu locals=%llu frames=%llu\n",
            snapshot->pc,
            (unsigned)snapshot->insn->opcode,
            (unsigned long long)snapshot->stack_len,
            (unsigned long long)snapshot->locals_len,
            (unsigned long long)snapshot->frame_len);
    return 1;
}
