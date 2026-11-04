        case MOP_SYSCALL: {
            MellowRuntimeContext *rt_ctx = (MellowRuntimeContext *)vm->syscall.user;
            if (!vm->syscall.fn){set_error(out,"syscall_bridge_missing");return 0;}
            size_t argc=(size_t)insn->b;
            if (argc>vm->stack_len){set_error(out,"syscall_stack_underflow");return 0;}
            MValue result=mval_none();
            if (insn->a == 23) {
                uint64_t task_id;
                if (argc != 1 || vm->stack[vm->stack_len - 1].tag != MVAL_FUNC) {
                    set_error(out,"spawn_requires_function"); return 0;
                }
                task_id = mellowrt_scheduler_spawn(vm, vm->stack[vm->stack_len - 1].as.func);
                if (!task_id) { set_error(out,"spawn_failed"); return 0; }
                if (rt_ctx) rt_ctx->spawned_tasks++;
                for(size_t i=vm->stack_len-argc;i<vm->stack_len;++i) mvalue_free(&vm->stack[i]);
                vm->stack_len-=argc;
                if (insn->c && !push(vm, mval_i64((int64_t)task_id))) { set_error(out,"spawn_result_push_failed"); return 0; }
                out->syscalls++; pc++; break;
            }
            if (insn->a == 24) {
                if (argc != 0) { set_error(out,"yield_takes_no_args"); return 0; }
                if (rt_ctx) rt_ctx->yielded_tasks++;
                out->syscalls++; pc++;
                mellowrt_task_save_from_vm(vm, vm->current_task, pc);
                next_task = mellowrt_scheduler_next_runnable(vm);
                if (next_task != (size_t)-1) {
                    mellowrt_task_load_into_vm(vm, next_task);
                    pc = vm->tasks[vm->current_task].pc;
                }
                break;
            }
            if (!vm->syscall.fn(vm->syscall.user,insn->a,vm->stack+(vm->stack_len-argc),argc,&result)){
                for(size_t i=vm->stack_len-argc;i<vm->stack_len;++i) mvalue_free(&vm->stack[i]);
                vm->stack_len-=argc;set_error(out,(rt_ctx&&rt_ctx->syscall_error[0])?rt_ctx->syscall_error:"syscall_failed");return 0;
            }
            if (rt_ctx && rt_ctx->recv_would_block) {
                void *waiting = NULL;
                if (argc == 1 && vm->stack[vm->stack_len - 1].tag == MVAL_NATIVE)
                    waiting = vm->stack[vm->stack_len - 1].as.ptr;
                rt_ctx->recv_would_block = 0;
                mvalue_free(&result);
                vm->tasks[vm->current_task].blocked = 1;
                vm->tasks[vm->current_task].waiting_native = waiting;
                vm->scheduler_blocks++;
                mellowrt_task_save_from_vm(vm, vm->current_task, pc);
                next_task = mellowrt_scheduler_next_runnable(vm);
                if (next_task == (size_t)-1) {
                    vm->tasks[vm->current_task].blocked = 0;
                    vm->tasks[vm->current_task].waiting_native = NULL;
                    for(size_t i=vm->stack_len-argc;i<vm->stack_len;++i) mvalue_free(&vm->stack[i]);
                    vm->stack_len-=argc;
                    if (insn->c&&!push(vm,result)){mvalue_free(&result);set_error(out,"syscall_result_push_failed");return 0;}
                    if (!insn->c) mvalue_free(&result);
                    out->syscalls++; pc++;
                    break;
                }
                mellowrt_task_load_into_vm(vm, next_task);
                pc = vm->tasks[vm->current_task].pc;
                out->syscalls++;
                break;
            }
            for(size_t i=vm->stack_len-argc;i<vm->stack_len;++i) mvalue_free(&vm->stack[i]);
            vm->stack_len-=argc;
            if (insn->c&&!push(vm,result)){mvalue_free(&result);set_error(out,"syscall_result_push_failed");return 0;}
            if (!insn->c) mvalue_free(&result);
            if (insn->a == 26) mellowrt_scheduler_unblock_native_waiters(vm, NULL);
            out->syscalls++; pc++; break;
        }

        case MOP_PUSH_FUNC:      /* always lowered to PUSH_CONST by Python compiler */
        case MOP_DEBUG_SNAPSHOT:
            pc++; break;

        default:
            set_error(out,"unsupported_opcode"); return 0;
        }

        snap.pc=pc;
        snap.frame=vm->frame_len?&vm->frames[vm->frame_len-1]:NULL;
        snap.frames=vm->frames; snap.frame_len=vm->frame_len;
        snap.stack=vm->stack;   snap.stack_len=vm->stack_len;
        snap.locals=vm->locals; snap.locals_len=vm->locals_len;
        if (vm->debug.on_after_instruction&&!vm->debug.on_after_instruction(vm->debug.user,&snap)){
            out->halted=1; out->result=vm->stack_len?vm->stack[vm->stack_len-1]:mval_none(); return 1;
        }
        continue;

finish_current_task:
        if (vm->current_task == 0)
            out->result = vm->stack_len ? mvalue_clone(vm, &vm->stack[vm->stack_len-1]) : mval_none();
        else
            vm->tasks[vm->current_task].result = vm->stack_len ? mvalue_clone(vm, &vm->stack[vm->stack_len-1]) : mval_none();
finish_current_task_with_result:
        vm->tasks[vm->current_task].finished = 1;
        mellowrt_task_save_from_vm(vm, vm->current_task, pc);
        next_task = mellowrt_scheduler_next_runnable(vm);
        if (next_task == (size_t)-1) break;
        mellowrt_task_load_into_vm(vm, next_task);
        pc = vm->tasks[vm->current_task].pc;
    }
    out->halted=1;
    return 1;
}
