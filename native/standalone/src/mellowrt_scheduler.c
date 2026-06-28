#include "mellowrt_scheduler.h"

#include <stdlib.h>
#include <string.h>

#define MELLOWRT_MAX_SCHEDULER_WORKERS 256u

void mellowrt_task_free_values(MTask *task) {
    size_t i;
    if (!task) return;
    for (i = 0; i < task->stack_len; ++i) mvalue_free(&task->stack[i]);
    for (i = 0; i < task->locals_len; ++i) mvalue_free(&task->locals[i]);
    mvalue_free(&task->result);
    free(task->stack);
    free(task->frames);
    free(task->locals);
    memset(task, 0, sizeof(*task));
}

static int ensure_tasks(MVM *vm, size_t cap) {
    MTask *grown;
    size_t next;
    if (vm->task_cap >= cap) return 1;
    next = vm->task_cap ? vm->task_cap * 2 : 8;
    if (next < cap) next = cap;
    grown = (MTask *)realloc(vm->tasks, next * sizeof(MTask));
    if (!grown) return 0;
    memset(grown + vm->task_cap, 0, (next - vm->task_cap) * sizeof(MTask));
    vm->tasks = grown;
    vm->task_cap = next;
    return 1;
}

void mellowrt_task_save_from_vm(MVM *vm, size_t index, uint32_t pc) {
    MTask *task;
    if (!vm || index >= vm->task_len) return;
    task = &vm->tasks[index];
    task->pc = pc;
    task->stack = vm->stack; task->stack_len = vm->stack_len; task->stack_cap = vm->stack_cap;
    task->frames = vm->frames; task->frame_len = vm->frame_len; task->frame_cap = vm->frame_cap;
    task->locals = vm->locals; task->locals_len = vm->locals_len; task->locals_cap = vm->locals_cap;
}

void mellowrt_task_load_into_vm(MVM *vm, size_t index) {
    MTask *task;
    if (!vm || index >= vm->task_len) return;
    task = &vm->tasks[index];
    vm->current_task = index;
    vm->stack = task->stack; vm->stack_len = task->stack_len; vm->stack_cap = task->stack_cap;
    vm->frames = task->frames; vm->frame_len = task->frame_len; vm->frame_cap = task->frame_cap;
    vm->locals = task->locals; vm->locals_len = task->locals_len; vm->locals_cap = task->locals_cap;
}

int mellowrt_scheduler_bootstrap(MVM *vm) {
    MTask *main_task;
    if (vm->tasks) return 1;
    if (!ensure_tasks(vm, 1)) return 0;
    if (!vm->scheduler_workers) vm->scheduler_workers = 1;
    vm->task_len = 1;
    vm->current_task = 0;
    vm->next_task_id = 1;
    main_task = &vm->tasks[0];
    memset(main_task, 0, sizeof(*main_task));
    main_task->id = 0;
    main_task->active = 1;
    main_task->pc = 0;
    main_task->result = mval_none();
    main_task->stack = vm->stack; main_task->stack_len = vm->stack_len; main_task->stack_cap = vm->stack_cap;
    main_task->frames = vm->frames; main_task->frame_len = vm->frame_len; main_task->frame_cap = vm->frame_cap;
    main_task->locals = vm->locals; main_task->locals_len = vm->locals_len; main_task->locals_cap = vm->locals_cap;
    return 1;
}

size_t mellowrt_scheduler_next_runnable(MVM *vm) {
    size_t i;
    if (!vm || !vm->task_len) return (size_t)-1;
    for (i = 1; i <= vm->task_len; ++i) {
        size_t idx = (vm->current_task + i) % vm->task_len;
        MTask *task = &vm->tasks[idx];
        if (task->active && !task->finished && !task->blocked) {
            if (idx != vm->current_task) vm->scheduler_switches++;
            return idx;
        }
    }
    return (size_t)-1;
}

void mellowrt_scheduler_unblock_native_waiters(MVM *vm, void *native_ptr) {
    size_t i;
    if (!vm) return;
    for (i = 0; i < vm->task_len; ++i) {
        MTask *task = &vm->tasks[i];
        if (task->active && task->blocked &&
            (!native_ptr || task->waiting_native == native_ptr)) {
            task->blocked = 0;
            task->waiting_native = NULL;
        }
    }
}

int mellowrt_scheduler_set_workers(MVM *vm, size_t workers) {
    if (!vm || workers == 0 || workers > MELLOWRT_MAX_SCHEDULER_WORKERS) return 0;
    vm->scheduler_workers = workers;
    return 1;
}

size_t mellowrt_scheduler_worker_count(const MVM *vm) {
    if (!vm || !vm->scheduler_workers) return 1;
    return vm->scheduler_workers;
}

size_t mellowrt_scheduler_runnable_count(const MVM *vm) {
    size_t i;
    size_t count = 0;
    if (!vm) return 0;
    for (i = 0; i < vm->task_len; ++i) {
        const MTask *task = &vm->tasks[i];
        if (task->active && !task->finished && !task->blocked) count++;
    }
    return count;
}

const char *mellowrt_scheduler_mode(const MVM *vm) {
    (void)vm;
    return "m:n-cooperative";
}

uint64_t mellowrt_scheduler_spawn(MVM *vm, MFunctionRef fn) {
    MTask *task;
    size_t index;
    size_t local_count;
    if (!vm || !ensure_tasks(vm, vm->task_len + 1)) return 0;
    index = vm->task_len++;
    task = &vm->tasks[index];
    memset(task, 0, sizeof(*task));
    task->id = vm->next_task_id++;
    task->active = 1;
    task->pc = fn.address;
    task->result = mval_none();
    task->frame_cap = 1;
    task->frames = (MFrame *)calloc(1, sizeof(MFrame));
    if (!task->frames) { task->active = 0; return 0; }
    task->frame_len = 1;
    task->frames[0] = (MFrame){
        .frame_id = 0,
        .return_pc = UINT32_MAX,
        .base = 0,
        .local_base = 0,
        .local_count = fn.local_count,
        .function = fn
    };
    local_count = vm->locals_len > fn.local_count ? vm->locals_len : fn.local_count;
    task->locals_cap = local_count ? local_count : 1;
    task->locals = (MValue *)calloc(task->locals_cap, sizeof(MValue));
    if (!task->locals) { mellowrt_task_free_values(task); return 0; }
    task->locals_len = local_count;
    for (size_t i = 0; i < task->locals_len; ++i)
        task->locals[i] = i < vm->locals_len ? mvalue_clone(vm, &vm->locals[i]) : mval_none();
    return task->id;
}
