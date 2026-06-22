#include "mellowrt.h"

#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

static int ensure_stack(MVM *vm, size_t cap) {
    if (vm->stack_cap >= cap) return 1;
    size_t next = vm->stack_cap ? vm->stack_cap * 2 : 64;
    if (next < cap) next = cap;
    MValue *p = (MValue *)realloc(vm->stack, sizeof(MValue) * next);
    if (!p) return 0;
    vm->stack = p; vm->stack_cap = next; return 1;
}
static int ensure_frames(MVM *vm, size_t cap) {
    if (vm->frame_cap >= cap) return 1;
    size_t next = vm->frame_cap ? vm->frame_cap * 2 : 16;
    if (next < cap) next = cap;
    MFrame *p = (MFrame *)realloc(vm->frames, sizeof(MFrame) * next);
    if (!p) return 0;
    vm->frames = p; vm->frame_cap = next; return 1;
}
int mvm_reserve_locals(MVM *vm, size_t cap) {
    if (vm->locals_cap >= cap) return 1;
    size_t next = vm->locals_cap ? vm->locals_cap * 2 : 64;
    if (next < cap) next = cap;
    MValue *p = (MValue *)realloc(vm->locals, sizeof(MValue) * next);
    if (!p) return 0;
    for (size_t i = vm->locals_cap; i < next; ++i) p[i] = mval_none();
    vm->locals = p; vm->locals_cap = next; return 1;
}
void mvm_init(MVM *vm) { memset(vm, 0, sizeof(*vm)); }

static void mlist_free(MList *list) {
    if (!list || !list->items) return;
    for (size_t i = 0; i < list->len; ++i) mvalue_free(&list->items[i]);
    free(list->items); list->items = NULL; list->len = list->cap = 0;
}
static void mmap_free(MMap *map) {
    if (!map) return;
    for (size_t i = 0; i < map->len; ++i) { mvalue_free(&map->keys[i]); mvalue_free(&map->values[i]); }
    free(map->keys); free(map->values); map->keys = map->values = NULL; map->len = map->cap = 0;
}
void mvalue_free(MValue *v) {
    if (!v) return;
    if (v->tag == MVAL_LIST) mlist_free(&v->as.list);
    else if (v->tag == MVAL_MAP) mmap_free(&v->as.map);
    else if (v->tag == MVAL_STR && (v->flags & 1u) && v->as.str.ptr) free((void *)v->as.str.ptr);
    *v = mval_none();
}
void mvm_free(MVM *vm) {
    if (!vm) return;
    for (size_t i = 0; i < vm->stack_len; ++i) mvalue_free(&vm->stack[i]);
    for (size_t i = 0; i < vm->locals_len; ++i) mvalue_free(&vm->locals[i]);
    free(vm->stack); free(vm->frames); free(vm->locals); memset(vm, 0, sizeof(*vm));
}
int mvm_reserve_stack(MVM *vm, size_t cap)  { return ensure_stack(vm, cap); }
int mvm_reserve_frames(MVM *vm, size_t cap) { return ensure_frames(vm, cap); }

MValue mval_none(void)  { MValue v; memset(&v,0,sizeof(v)); v.tag=MVAL_NONE; return v; }
MValue mval_bool(int x) { MValue v=mval_none(); v.tag=MVAL_BOOL; v.as.boolean=!!x; return v; }
MValue mval_i64(int64_t x) { MValue v=mval_none(); v.tag=MVAL_I64; v.as.i64=x; return v; }
MValue mval_f64(double x)  { MValue v=mval_none(); v.tag=MVAL_F64; v.as.f64=x; return v; }
MValue mval_str(const char *ptr, size_t len) { MValue v=mval_none(); v.tag=MVAL_STR; v.as.str.ptr=ptr; v.as.str.len=len; return v; }
MValue mval_func(uint32_t address, uint16_t arity, uint16_t local_count, uint16_t flags) {
    MValue v=mval_none(); v.tag=MVAL_FUNC; v.as.func.address=address; v.as.func.arity=arity;
    v.as.func.local_count=local_count; v.as.func.flags=flags; return v;
}
const char *mvalue_tag_name(MValueTag tag) {
    switch(tag){
        case MVAL_NONE:  return "none";  case MVAL_BOOL:  return "bool";
        case MVAL_I64:   return "i64";   case MVAL_F64:   return "f64";
        case MVAL_STR:   return "str";   case MVAL_BYTES: return "bytes";
        case MVAL_LIST:  return "list";  case MVAL_MAP:   return "map";
        case MVAL_FUNC:  return "func";  case MVAL_NATIVE:return "native";
        case MVAL_ERROR: return "error"; default:         return "unknown";
    }
}

/* ── owned heap string ──────────────────────────────────────────────────── */
static MValue mval_owned_str(const char *src, size_t len) {
    char *buf = (char *)calloc(len + 1, 1);
    MValue v = mval_none();
    if (!buf) return v;
    if (src && len) memcpy(buf, src, len);
    buf[len] = '\0';
    v.tag = MVAL_STR; v.flags = 1u; v.as.str.ptr = buf; v.as.str.len = len;
    return v;
}

/* Deep-copy a value so every allocation is independently owned. */
static MValue mvalue_deep_copy(const MValue *src) {
    if (!src) return mval_none();
    switch (src->tag) {
    case MVAL_STR:
        if (src->as.str.ptr)
            return mval_owned_str(src->as.str.ptr, src->as.str.len);
        return mval_none();
    case MVAL_LIST: {
        MValue v = mval_none(); v.tag = MVAL_LIST;
        v.as.list.len = v.as.list.cap = src->as.list.len;
        v.as.list.items = src->as.list.len ? (MValue*)calloc(src->as.list.len,sizeof(MValue)) : NULL;
        if (src->as.list.len && !v.as.list.items) return mval_none();
        for (size_t i=0;i<src->as.list.len;++i)
            v.as.list.items[i] = mvalue_deep_copy(&src->as.list.items[i]);
        return v;
    }
    case MVAL_MAP: {
        MValue v = mval_none(); v.tag = MVAL_MAP;
        v.as.map.len = v.as.map.cap = src->as.map.len;
        v.as.map.keys   = src->as.map.len ? (MValue*)calloc(src->as.map.len,sizeof(MValue)) : NULL;
        v.as.map.values = src->as.map.len ? (MValue*)calloc(src->as.map.len,sizeof(MValue)) : NULL;
        if (src->as.map.len && (!v.as.map.keys||!v.as.map.values)) {
            free(v.as.map.keys); free(v.as.map.values); return mval_none();
        }
        for (size_t i=0;i<src->as.map.len;++i) {
            v.as.map.keys[i]   = mvalue_deep_copy(&src->as.map.keys[i]);
            v.as.map.values[i] = mvalue_deep_copy(&src->as.map.values[i]);
        }
        return v;
    }
    default: return *src;
    }
}

static int truthy(MValue v) {
    switch(v.tag){
        case MVAL_NONE: return 0; case MVAL_BOOL: return v.as.boolean != 0;
        case MVAL_I64:  return v.as.i64 != 0; case MVAL_F64: return v.as.f64 != 0.0;
        case MVAL_STR:  return v.as.str.len != 0; case MVAL_LIST: return v.as.list.len != 0;
        case MVAL_MAP:  return v.as.map.len != 0; default: return 1;
    }
}
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
    v.as.list.items=count?(MValue*)calloc((size_t)count,sizeof(MValue)):NULL;
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
    v.as.map.keys  =pair_count?(MValue*)calloc((size_t)pair_count,sizeof(MValue)):NULL;
    v.as.map.values=pair_count?(MValue*)calloc((size_t)pair_count,sizeof(MValue)):NULL;
    if (pair_count&&(!v.as.map.keys||!v.as.map.values)){free(v.as.map.keys);free(v.as.map.values);return 0;}
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
    if (!vm||!program||!out) return 0;
    memset(out,0,sizeof(*out));
    uint32_t pc=0;
    out->result=mval_none();
    if (!ensure_frames(vm,1)){set_error(out,"frame_alloc_failed");return 0;}
    vm->frame_len=1;
    vm->frames[0]=(MFrame){.frame_id=0,.return_pc=(uint32_t)program->code_len,.base=0,.local_base=0,.local_count=0,.function={0,0,0,0}};

    while (pc<program->code_len) {
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
            out->halted=1; out->result=vm->stack_len?vm->stack[vm->stack_len-1]:mval_none(); return 1;

        /* stack */
        case MOP_PUSH_CONST: {
            if ((size_t)insn->a >= program->const_len) { set_error(out,"push_const_oob"); return 0; }
            MValue cv = mvalue_deep_copy(&program->const_pool[insn->a]);
            if (!push(vm, cv)) { set_error(out,"push_const_failed"); return 0; }
            pc++; break;
        }
        case MOP_POP: { MValue discarded=pop(vm); mvalue_free(&discarded); pc++; break; }
        case MOP_DUP:
            if (!vm->stack_len||!push(vm,vm->stack[vm->stack_len-1])){set_error(out,"dup_failed");return 0;}
            pc++; break;

        /* locals */
        case MOP_LOAD_LOCAL: {
            MValue *slot=local_ptr(vm,frame,insn->a);
            if (!slot){set_error(out,"load_local_failed");return 0;}
            /* Full deep-copy (strings, lists, maps) so mvm_free never
               double-frees a value that lives in both stack and locals. */
            MValue cv = mvalue_deep_copy(slot);
            if (!push(vm, cv)){set_error(out,"load_local_failed");return 0;}
            pc++; break;
        }
        case MOP_STORE_LOCAL: {
            size_t base=frame?frame->local_base:0, idx=base+(size_t)insn->a;
            if (!ensure_local_window(vm,idx+1)){set_error(out,"store_local_alloc_failed");return 0;}
            if (frame&&frame->local_count<(uint32_t)(insn->a+1)) frame->local_count=(uint32_t)(insn->a+1);
            /* Free any existing value in this local slot before overwriting. */
            mvalue_free(&vm->locals[idx]);
            /* Move (not copy) from stack — pop zeros the stack_len, value ownership
               transfers to locals so mvm_free won't double-free. */
            vm->locals[idx] = pop(vm);
            /* Zero the now-consumed stack slot for safety. */
            memset(&vm->stack[vm->stack_len], 0, sizeof(MValue));
            pc++; break;
        }

        /* arithmetic */
        case MOP_ADD: case MOP_SUB: case MOP_MUL: case MOP_DIV: {
            MValue b=pop(vm), a=pop(vm);
            if (insn->opcode==MOP_ADD&&(a.tag==MVAL_STR||b.tag==MVAL_STR)){
                char abuf[64],bbuf[64]; const char *ap=NULL,*bp=NULL; size_t alen=0,blen=0;
                if (!coerce_str(a,abuf,sizeof(abuf),&ap,&alen)||!coerce_str(b,bbuf,sizeof(bbuf),&bp,&blen)){
                    mvalue_free(&a);mvalue_free(&b);set_error(out,"string_concat_unsupported_type");return 0;
                }
                MValue sv=mval_owned_str(NULL,alen+blen);
                if (!sv.as.str.ptr){mvalue_free(&a);mvalue_free(&b);set_error(out,"string_concat_alloc_failed");return 0;}
                memcpy((char*)sv.as.str.ptr,ap,alen); memcpy((char*)sv.as.str.ptr+alen,bp,blen);
                mvalue_free(&a);mvalue_free(&b);
                if (!push(vm,sv)){mvalue_free(&sv);set_error(out,"string_concat_push_failed");return 0;}
                pc++; break;
            }
            if ((a.tag!=MVAL_I64&&a.tag!=MVAL_F64)||(b.tag!=MVAL_I64&&b.tag!=MVAL_F64)){mvalue_free(&a);mvalue_free(&b);set_error(out,"numeric_op_requires_numbers");return 0;}
            int use_f=(a.tag==MVAL_F64||b.tag==MVAL_F64||insn->opcode==MOP_DIV);
            double da=(a.tag==MVAL_F64)?a.as.f64:(double)a.as.i64;
            double db=(b.tag==MVAL_F64)?b.as.f64:(double)b.as.i64;
            if (insn->opcode==MOP_DIV&&db==0.0){mvalue_free(&a);mvalue_free(&b);set_error(out,"division_by_zero");return 0;}
            double res=(insn->opcode==MOP_ADD)?da+db:(insn->opcode==MOP_SUB)?da-db:(insn->opcode==MOP_MUL)?da*db:da/db;
            mvalue_free(&a);mvalue_free(&b);
            if (!push(vm,use_f?mval_f64(res):mval_i64((int64_t)res))){set_error(out,"numeric_push_failed");return 0;}
            pc++; break;
        }

        /* v2.3.4: modulo */
        case MOP_MOD: {
            MValue b=pop(vm), a=pop(vm);
            if (a.tag==MVAL_I64&&b.tag==MVAL_I64){
                if (b.as.i64==0){mvalue_free(&a);mvalue_free(&b);set_error(out,"modulo_by_zero");return 0;}
                int64_t r=a.as.i64%b.as.i64;
                if (r!=0&&((r<0)!=(b.as.i64<0))) r+=b.as.i64; /* Python-style sign */
                if (!push(vm,mval_i64(r))){set_error(out,"mod_push_failed");return 0;}
            } else {
                double da=(a.tag==MVAL_F64)?a.as.f64:(double)a.as.i64;
                double db=(b.tag==MVAL_F64)?b.as.f64:(double)b.as.i64;
                if (db==0.0){mvalue_free(&a);mvalue_free(&b);set_error(out,"modulo_by_zero");return 0;}
                if (!push(vm,mval_f64(fmod(da,db)))){set_error(out,"mod_push_failed");return 0;}
            }
            mvalue_free(&a);mvalue_free(&b);
            pc++; break;
        }

        /* v2.3.4: power */
        case MOP_POW: {
            MValue b=pop(vm), a=pop(vm);
            if (a.tag==MVAL_I64&&b.tag==MVAL_I64&&b.as.i64>=0&&b.as.i64<=62){
                int64_t acc=1, bv=a.as.i64, n=b.as.i64;
                while(n>0){if(n&1)acc*=bv; bv*=bv; n>>=1;}
                if (!push(vm,mval_i64(acc))){set_error(out,"pow_push_failed");return 0;}
            } else {
                double base=(a.tag==MVAL_F64)?a.as.f64:(double)a.as.i64;
                double exp_v=(b.tag==MVAL_F64)?b.as.f64:(double)b.as.i64;
                if (!push(vm,mval_f64(pow(base,exp_v)))){set_error(out,"pow_push_failed");return 0;}
            }
            mvalue_free(&a);mvalue_free(&b);
            pc++; break;
        }

        /* v2.3.4: boolean ops */
        case MOP_BOOL_AND: { MValue b=pop(vm),a=pop(vm); int r=truthy(a)&&truthy(b); mvalue_free(&a);mvalue_free(&b); if(!push(vm,mval_bool(r))){set_error(out,"bool_and_failed");return 0;} pc++; break; }
        case MOP_BOOL_OR:  { MValue b=pop(vm),a=pop(vm); int r=truthy(a)||truthy(b); mvalue_free(&a);mvalue_free(&b); if(!push(vm,mval_bool(r))){set_error(out,"bool_or_failed"); return 0;} pc++; break; }
        case MOP_BOOL_NOT: { MValue a=pop(vm); int r=!truthy(a); mvalue_free(&a); if(!push(vm,mval_bool(r))){set_error(out,"bool_not_failed");return 0;} pc++; break; }

        /* compare + jumps */
        case MOP_COMPARE: { MValue b=pop(vm),a=pop(vm); int r=generic_compare(a,b,(MCompareOp)insn->a); mvalue_free(&a);mvalue_free(&b); if(!push(vm,mval_bool(r))){set_error(out,"compare_failed");return 0;} pc++; break; }
        case MOP_JUMP: pc=(uint32_t)insn->a; break;
        case MOP_JUMP_IF_FALSE: { MValue c=pop(vm); int r=truthy(c); mvalue_free(&c); pc=r?pc+1:(uint32_t)insn->a; break; }

        /* functions */
        case MOP_CALL: {
            /* standalone lowering emits: PUSH arg0..argN-1, PUSH func_ref, CALL N
               so func_ref is at TOP = stack[top-1]; args are below it. */
            if (vm->stack_len < (size_t)insn->a + 1) { set_error(out,"call_stack_underflow"); return 0; }
            MValue callee = vm->stack[vm->stack_len - 1];  /* func_ref at top */
            if (callee.tag != MVAL_FUNC) { set_error(out,"call_non_function"); return 0; }
            if (!ensure_frames(vm, vm->frame_len+1)) { set_error(out,"call_frame_alloc_failed"); return 0; }
            size_t argc = (size_t)insn->a;
            size_t args_base = vm->stack_len - 1 - argc;   /* args start below func_ref */
            if (!ensure_local_window(vm, vm->locals_len + callee.as.func.local_count)) { set_error(out,"call_local_alloc_failed"); return 0; }
            size_t lb = vm->locals_len;
            for (size_t i = 0; i < argc; ++i) vm->locals[lb+i] = vm->stack[args_base+i];
            for (size_t i = argc; i < callee.as.func.local_count; ++i) vm->locals[lb+i] = mval_none();
            vm->locals_len += callee.as.func.local_count;
            vm->stack_len = args_base;   /* pop args + func_ref */
            vm->frames[vm->frame_len++] = (MFrame){
                .frame_id=(uint32_t)vm->frame_len, .return_pc=pc+1,
                .base=(uint32_t)vm->stack_len, .local_base=(uint32_t)lb,
                .local_count=callee.as.func.local_count, .function=callee.as.func
            };
            pc = callee.as.func.address; break;
        }

        /* v2.3.4: CALL_VAL — first-class function value on stack */
        case MOP_CALL_VAL: {
            size_t argc=(size_t)insn->a;
            if (vm->stack_len<=argc){set_error(out,"call_val_stack_underflow");return 0;}
            MValue callee=vm->stack[vm->stack_len-1-argc];
            if (callee.tag!=MVAL_FUNC){set_error(out,"call_val_non_function");return 0;}
            if (!ensure_frames(vm,vm->frame_len+1)){set_error(out,"call_val_frame_alloc_failed");return 0;}
            size_t args_base=vm->stack_len-argc;
            if (!ensure_local_window(vm,vm->locals_len+callee.as.func.local_count)){set_error(out,"call_val_local_alloc_failed");return 0;}
            size_t lb=vm->locals_len;
            for(size_t i=0;i<argc;++i) vm->locals[lb+i]=vm->stack[args_base+i];
            for(size_t i=argc;i<callee.as.func.local_count;++i) vm->locals[lb+i]=mval_none();
            vm->locals_len+=callee.as.func.local_count;
            vm->stack_len=args_base-1;
            vm->frames[vm->frame_len++]=(MFrame){.frame_id=(uint32_t)vm->frame_len,.return_pc=pc+1,.base=(uint32_t)vm->stack_len,.local_base=(uint32_t)lb,.local_count=callee.as.func.local_count,.function=callee.as.func};
            pc=callee.as.func.address; break;
        }

        case MOP_RETURN: {
            MValue ret=vm->stack_len?pop(vm):mval_none();
            if (vm->frame_len<=1){out->halted=1;out->result=ret;return 1;}
            MFrame ended=vm->frames[--vm->frame_len];
            for(size_t i=ended.local_base;i<vm->locals_len;++i) mvalue_free(&vm->locals[i]);
            vm->locals_len=ended.local_base; vm->stack_len=ended.base;
            if (!push(vm,ret)){set_error(out,"return_push_failed");return 0;}
            pc=ended.return_pc; break;
        }

        /* collections */
        case MOP_BUILD_LIST:
            if (!build_list(vm,insn->a)){set_error(out,"build_list_failed");return 0;}
            out->allocations++; pc++; break;
        case MOP_BUILD_MAP:
            if (!build_map(vm,insn->a)){set_error(out,"build_map_failed");return 0;}
            out->allocations++; pc++; break;

        /* v2.3.4: GETITEM — list[i], map[key], str[i] */
        case MOP_GETITEM: {
            MValue idx=pop(vm), cont=pop(vm);
            MValue selected=mval_none();
            if (cont.tag==MVAL_LIST){
                int64_t i=(idx.tag==MVAL_I64)?idx.as.i64:(idx.tag==MVAL_F64)?(int64_t)idx.as.f64:-1;
                if (i<0) i+=(int64_t)cont.as.list.len;
                if (i<0||(size_t)i>=cont.as.list.len){mvalue_free(&idx);mvalue_free(&cont);set_error(out,"getitem_index_out_of_range");return 0;}
                selected=mvalue_deep_copy(&cont.as.list.items[(size_t)i]);
            } else if (cont.tag==MVAL_MAP){
                MValue val=mval_none();
                if (!map_get(&cont.as.map,&idx,&val)){mvalue_free(&idx);mvalue_free(&cont);set_error(out,"getitem_key_not_found");return 0;}
                selected=mvalue_deep_copy(&val);
            } else if (cont.tag==MVAL_STR){
                int64_t i=(idx.tag==MVAL_I64)?idx.as.i64:(idx.tag==MVAL_F64)?(int64_t)idx.as.f64:-1;
                if (i<0) i+=(int64_t)cont.as.str.len;
                if (i<0||(size_t)i>=cont.as.str.len){mvalue_free(&idx);mvalue_free(&cont);set_error(out,"getitem_index_out_of_range");return 0;}
                char ch[1]; ch[0]=cont.as.str.ptr[(size_t)i];
                selected=mval_owned_str(ch,1);
            } else { mvalue_free(&idx);mvalue_free(&cont);set_error(out,"getitem_unsupported_type"); return 0; }
            mvalue_free(&idx);mvalue_free(&cont);
            if (!push(vm,selected)){mvalue_free(&selected);set_error(out,"getitem_push_failed");return 0;}
            pc++; break;
        }

        /* v2.3.4: LEN */
        case MOP_LEN: {
            MValue v=pop(vm); int64_t n=0;
            if      (v.tag==MVAL_LIST) n=(int64_t)v.as.list.len;
            else if (v.tag==MVAL_STR)  n=(int64_t)v.as.str.len;
            else if (v.tag==MVAL_MAP)  n=(int64_t)v.as.map.len;
            else {mvalue_free(&v);set_error(out,"len_unsupported_type");return 0;}
            mvalue_free(&v);
            if (!push(vm,mval_i64(n))){set_error(out,"len_push_failed");return 0;}
            pc++; break;
        }

        /* module / syscall */
        case MOP_IMPORT: pc++; break; /* metadata in image; no-op at runtime */

        case MOP_SYSCALL: {
            if (!vm->syscall.fn){set_error(out,"syscall_bridge_missing");return 0;}
            size_t argc=(size_t)insn->b;
            if (argc>vm->stack_len){set_error(out,"syscall_stack_underflow");return 0;}
            MValue result=mval_none();
            if (!vm->syscall.fn(vm->syscall.user,insn->a,vm->stack+(vm->stack_len-argc),argc,&result)){
                for(size_t i=vm->stack_len-argc;i<vm->stack_len;++i) mvalue_free(&vm->stack[i]);
                vm->stack_len-=argc;set_error(out,"syscall_failed");return 0;
            }
            for(size_t i=vm->stack_len-argc;i<vm->stack_len;++i) mvalue_free(&vm->stack[i]);
            vm->stack_len-=argc;
            if (insn->c&&!push(vm,result)){mvalue_free(&result);set_error(out,"syscall_result_push_failed");return 0;}
            if (!insn->c) mvalue_free(&result);
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
    }
    out->halted=1; out->result=vm->stack_len?vm->stack[vm->stack_len-1]:mval_none(); return 1;
}
