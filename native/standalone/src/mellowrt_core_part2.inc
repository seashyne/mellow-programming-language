static int push(MVM *vm, MValue v) {
    if (!ensure_stack(vm, vm->stack_len+1)) return 0;
    vm->stack[vm->stack_len++] = v; return 1;
}
static MValue pop(MVM *vm) {
    MValue value;
    if (!vm->stack_len) return mval_none();
    vm->stack_len--;
    value=vm->stack[vm->stack_len];
    vm->stack[vm->stack_len]=mval_none();
    return value;
}
static MValue *local_ptr(MVM *vm, const MFrame *frame, int32_t slot) {
    size_t idx = frame ? frame->local_base + (size_t)slot : (size_t)slot;
    if (idx >= vm->locals_len) return NULL;
    return &vm->locals[idx];
}
static int ensure_local_window(MVM *vm, size_t count) {
    if (!mvm_reserve_locals(vm, count)) return 0;
    if (vm->locals_len < count) {
        for (size_t i = vm->locals_len; i < count; ++i) vm->locals[i] = mval_none();
        vm->locals_len = count;
    }
    return 1;
}

static int numeric_compare(MValue a, MValue b, MCompareOp op, int *out) {
    if ((a.tag!=MVAL_I64&&a.tag!=MVAL_F64)||(b.tag!=MVAL_I64&&b.tag!=MVAL_F64)) return 0;
    double da=(a.tag==MVAL_F64)?a.as.f64:(double)a.as.i64;
    double db=(b.tag==MVAL_F64)?b.as.f64:(double)b.as.i64;
    switch(op){
        case MCMP_EQ: *out=da==db; return 1; case MCMP_NE: *out=da!=db; return 1;
        case MCMP_LT: *out=da<db;  return 1; case MCMP_LE: *out=da<=db; return 1;
        case MCMP_GT: *out=da>db;  return 1; case MCMP_GE: *out=da>=db; return 1;
        default: return 0;
    }
}
static int generic_compare(MValue a, MValue b, MCompareOp op) {
    int result=0;
    if (numeric_compare(a,b,op,&result)) return result;
    if (a.tag==MVAL_STR && b.tag==MVAL_STR) {
        size_t n=a.as.str.len<b.as.str.len?a.as.str.len:b.as.str.len;
        int cmp=(n>0)?memcmp(a.as.str.ptr,b.as.str.ptr,n):0;
        if (cmp==0 && a.as.str.len!=b.as.str.len) cmp=(a.as.str.len<b.as.str.len)?-1:1;
        switch(op){
            case MCMP_EQ: return cmp==0; case MCMP_NE: return cmp!=0;
            case MCMP_LT: return cmp<0;  case MCMP_LE: return cmp<=0;
            case MCMP_GT: return cmp>0;  case MCMP_GE: return cmp>=0;
            default: return 0;
        }
    }
    switch(op){
        case MCMP_EQ: return a.tag==b.tag&&((a.tag==MVAL_BOOL&&a.as.boolean==b.as.boolean)||(a.tag==MVAL_NONE));
        case MCMP_NE: return !generic_compare(a,b,MCMP_EQ);
        default: return 0;
    }
}

static int build_list(MVM *vm, int32_t count) {
    if (count<0||(size_t)count>vm->stack_len) return 0;
    MValue v=mval_none(); v.tag=MVAL_LIST;
    v.as.list.len=v.as.list.cap=(size_t)count;
    v.as.list.items=count?(MValue*)heap_alloc(vm,(size_t)count,sizeof(MValue),MHEAP_LIST_ITEMS):NULL;
    if (count&&!v.as.list.items) return 0;
    /* Move values off the stack (not copy) to avoid double-free of owned strings. */
    for (int32_t i=count-1;i>=0;--i) {
        MValue sv = pop(vm);
        v.as.list.items[(size_t)i] = sv;
    }
    return push(vm,v);
}
static int build_map(MVM *vm, int32_t pair_count) {
    if (pair_count<0||(size_t)(pair_count*2)>vm->stack_len) return 0;
    MValue v=mval_none(); v.tag=MVAL_MAP;
    v.as.map.len=v.as.map.cap=(size_t)pair_count;
    v.as.map.keys  =pair_count?(MValue*)heap_alloc(vm,(size_t)pair_count,sizeof(MValue),MHEAP_MAP_KEYS):NULL;
    v.as.map.values=pair_count?(MValue*)heap_alloc(vm,(size_t)pair_count,sizeof(MValue),MHEAP_MAP_VALUES):NULL;
    if (pair_count&&(!v.as.map.keys||!v.as.map.values)){mvalue_free(&v);return 0;}
    /* Move values off the stack to avoid double-free of owned strings. */
    for (int32_t i=pair_count-1;i>=0;--i){
        v.as.map.values[(size_t)i]=pop(vm);
        v.as.map.keys[(size_t)i]  =pop(vm);
    }
    /* Zero the stack slots we just consumed (they're below stack_len now, but
       a future realloc or mvm_free scan might still read them). */
    return push(vm,v);
}
static int map_get(const MMap *m, const MValue *key, MValue *out) {
    for (size_t i=0;i<m->len;++i) if (generic_compare(m->keys[i],*key,MCMP_EQ)){*out=m->values[i];return 1;}
    return 0;
}
static void set_error(MRunResult *out, const char *msg) { out->failed=1; out->error_message=msg; }

/* ── string-concat helper (used by ADD) ─────────────────────────────────── */
static int coerce_str(MValue v, char *buf, size_t bufsz, const char **out_ptr, size_t *out_len) {
    if (v.tag==MVAL_STR)  { *out_ptr=v.as.str.ptr?v.as.str.ptr:""; *out_len=v.as.str.len; return 1; }
    if (v.tag==MVAL_I64)  { int n=snprintf(buf,bufsz,"%lld",(long long)v.as.i64); *out_ptr=buf; *out_len=(size_t)(n>0?n:0); return 1; }
    if (v.tag==MVAL_F64)  { int n=snprintf(buf,bufsz,"%g",v.as.f64); *out_ptr=buf; *out_len=(size_t)(n>0?n:0); return 1; }
    if (v.tag==MVAL_BOOL) { *out_ptr=v.as.boolean?"true":"false"; *out_len=strlen(*out_ptr); return 1; }
    if (v.tag==MVAL_NONE) { *out_ptr="none"; *out_len=4; return 1; }
    return 0;
}

int mvm_run(MVM *vm, const MProgram *program, MRunResult *out) {
    size_t next_task;
    if (!vm||!program||!out) return 0;
    memset(out,0,sizeof(*out));
    uint32_t pc=0;
    out->result=mval_none();
    if (!ensure_frames(vm,1)){set_error(out,"frame_alloc_failed");return 0;}
    vm->frame_len=1;
    vm->frames[0]=(MFrame){.frame_id=0,.return_pc=(uint32_t)program->code_len,.base=0,.local_base=0,.local_count=0,.function={0,0,0,0}};
    if (!mellowrt_scheduler_bootstrap(vm)){set_error(out,"scheduler_alloc_failed");return 0;}
    mellowrt_task_save_from_vm(vm, 0, 0);
    mellowrt_task_load_into_vm(vm, 0);
    pc = vm->tasks[vm->current_task].pc;

    while (1) {
        if (pc >= program->code_len) goto finish_current_task;
        if (vm->current_task >= vm->task_len) { set_error(out,"scheduler_current_task_oob"); return 0; }
        const MInstruction *insn=&program->code[pc];
        const MSourceSpan  *span=(program->span_map&&pc<program->span_len)?&program->span_map[pc]:NULL;
        out->error_pc=pc;
        out->has_error_span=span!=NULL;
        if(span) out->error_span=*span;
        MFrame *frame=vm->frame_len?&vm->frames[vm->frame_len-1]:NULL;
        MDebugSnapshot snap={pc,insn,span,frame,vm->frames,vm->frame_len,vm->stack,vm->stack_len,vm->locals,vm->locals_len};
        if (vm->debug.on_before_instruction&&!vm->debug.on_before_instruction(vm->debug.user,&snap)){
            out->halted=1; out->result=vm->stack_len?vm->stack[vm->stack_len-1]:mval_none(); return 1;
        }
        out->executed_instructions++;

        switch((MOpcode)insn->opcode){

        /* control */
        case MOP_HALT:
        case MOP_STOP:
            goto finish_current_task;

        /* stack */
        case MOP_PUSH_CONST: {
            if ((size_t)insn->a >= program->const_len) { set_error(out,"push_const_oob"); return 0; }
            MValue cv = mvalue_clone(vm, &program->const_pool[insn->a]);
            if (!push(vm, cv)) { set_error(out,"push_const_failed"); return 0; }
            pc++; break;
        }
        case MOP_POP: { MValue discarded=pop(vm); mvalue_release_temp(&discarded); pc++; break; }
        case MOP_DUP:
            if (!vm->stack_len||!push(vm,vm->stack[vm->stack_len-1])){set_error(out,"dup_failed");return 0;}
            pc++; break;

        /* locals */
        case MOP_LOAD_LOCAL: {
            MValue *slot=local_ptr(vm,frame,insn->a);
            if (!slot){set_error(out,"load_local_failed");return 0;}
            /* Scalars are immutable/unowned in the VM, so hot loops can copy
               them directly. Containers/strings still need ownership isolation. */
            MValue cv = mvalue_is_scalar(*slot) ? *slot : mvalue_clone(vm, slot);
            if (!push(vm, cv)){set_error(out,"load_local_failed");return 0;}
            pc++; break;
        }
        case MOP_STORE_LOCAL: {
            size_t base=frame?frame->local_base:0, idx=base+(size_t)insn->a;
            if (!ensure_local_window(vm,idx+1)){set_error(out,"store_local_alloc_failed");return 0;}
            if (frame&&frame->local_count<(uint32_t)(insn->a+1)) frame->local_count=(uint32_t)(insn->a+1);
            /* Release owned values before overwrite; scalar locals are unowned. */
            mvalue_release_temp(&vm->locals[idx]);
            /* Move (not copy) from stack — pop zeros the stack_len, value ownership
               transfers to locals so mvm_free won't double-free. */
            vm->locals[idx] = pop(vm);
            pc++; break;
        }
        case MOP_I64_ADD_LOCAL_CONST: {
            MValue *slot=local_ptr(vm,frame,insn->a);
            if (!slot || slot->tag!=MVAL_I64){set_error(out,"i64_add_local_const_requires_i64");return 0;}
            slot->as.i64 += (int64_t)insn->b;
            pc++; break;
        }
        case MOP_I64_ADD_LOCAL_LOCAL: {
            MValue *slot=local_ptr(vm,frame,insn->a);
            MValue *rhs=local_ptr(vm,frame,insn->b);
            if (!slot || !rhs || slot->tag!=MVAL_I64 || rhs->tag!=MVAL_I64){set_error(out,"i64_add_local_local_requires_i64");return 0;}
            slot->as.i64 += rhs->as.i64;
            pc++; break;
        }
        case MOP_I64_SUM_RANGE_STEP1: {
            MValue *acc=local_ptr(vm,frame,insn->a);
            MValue *idx=local_ptr(vm,frame,insn->b);
            MValue *limit=local_ptr(vm,frame,insn->c);
            int64_t total, i, n;
            if (!acc || !idx || !limit || acc->tag!=MVAL_I64 || idx->tag!=MVAL_I64 || limit->tag!=MVAL_I64){set_error(out,"i64_sum_range_step1_requires_i64");return 0;}
            total=acc->as.i64; i=idx->as.i64; n=limit->as.i64;
            while (i < n) {
                total += i;
                i += 1;
            }
            acc->as.i64=total;
            idx->as.i64=i;
            pc++; break;
        }
        case MOP_I64_BRANCH_MOD2_ACCUM_STEP1: {
            MValue *acc=local_ptr(vm,frame,insn->a);
            MValue *idx=local_ptr(vm,frame,insn->b);
            MValue *limit=local_ptr(vm,frame,insn->c);
            int64_t total, i, n;
            if (!acc || !idx || !limit || acc->tag!=MVAL_I64 || idx->tag!=MVAL_I64 || limit->tag!=MVAL_I64){set_error(out,"i64_branch_mod2_accum_step1_requires_i64");return 0;}
            total=acc->as.i64; i=idx->as.i64; n=limit->as.i64;
            while (i < n) {
                total += (i % 2 == 0) ? 3 : 1;
                i += 1;
            }
            acc->as.i64=total;
            idx->as.i64=i;
            pc++; break;
        }
        case MOP_I64_LIST_MOD_ACCUM_STEP1: {
            int32_t list_slot=insn->c&0xffff;
            int32_t limit_slot=(insn->c>>16)&0xffff;
            MValue *acc=local_ptr(vm,frame,insn->a);
            MValue *idx=local_ptr(vm,frame,insn->b);
            MValue *values=local_ptr(vm,frame,list_slot);
            MValue *limit=local_ptr(vm,frame,limit_slot);
            int64_t total, i, n;
            size_t len;
            if (!acc || !idx || !values || !limit || acc->tag!=MVAL_I64 || idx->tag!=MVAL_I64 || values->tag!=MVAL_LIST || limit->tag!=MVAL_I64){set_error(out,"i64_list_mod_accum_step1_requires_i64_list");return 0;}
            len=values->as.list.len;
            if (len==0){set_error(out,"i64_list_mod_accum_empty_list");return 0;}
            for (size_t item=0; item<len; ++item)
                if (values->as.list.items[item].tag!=MVAL_I64){set_error(out,"i64_list_mod_accum_requires_i64_items");return 0;}
            total=acc->as.i64; i=idx->as.i64; n=limit->as.i64;
            while (i < n) {
                int64_t mod=i%(int64_t)len;
                if (mod<0) mod+=(int64_t)len;
                total += values->as.list.items[(size_t)mod].as.i64;
                i += 1;
            }
            acc->as.i64=total;
            idx->as.i64=i;
            pc++; break;
        }
        case MOP_I64_ADD_FUNC_ACCUM_STEP1: {
            MValue *acc=local_ptr(vm,frame,insn->a);
            MValue *idx=local_ptr(vm,frame,insn->b);
            MValue *limit=local_ptr(vm,frame,insn->c);
            int64_t total, i, n;
            if (!acc || !idx || !limit || acc->tag!=MVAL_I64 || idx->tag!=MVAL_I64 || limit->tag!=MVAL_I64){set_error(out,"i64_add_func_accum_step1_requires_i64");return 0;}
            total=acc->as.i64; i=idx->as.i64; n=limit->as.i64;
            while (i < n) {
                total += i;
                i += 1;
            }
            acc->as.i64=total;
            idx->as.i64=i;
            pc++; break;
        }
