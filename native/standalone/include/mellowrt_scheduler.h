#ifndef MELLOWRT_SCHEDULER_H
#define MELLOWRT_SCHEDULER_H

#include "mellowrt.h"

#include <stddef.h>
#include <stdint.h>

void mellowrt_task_free_values(MTask *task);
int mellowrt_scheduler_bootstrap(MVM *vm);
void mellowrt_task_save_from_vm(MVM *vm, size_t index, uint32_t pc);
void mellowrt_task_load_into_vm(MVM *vm, size_t index);
size_t mellowrt_scheduler_next_runnable(MVM *vm);
void mellowrt_scheduler_unblock_native_waiters(MVM *vm, void *native_ptr);
uint64_t mellowrt_scheduler_spawn(MVM *vm, MFunctionRef fn);

#endif
