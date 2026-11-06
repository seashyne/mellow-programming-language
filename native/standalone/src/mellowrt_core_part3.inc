        case MOP_STR_APPEND_REPEAT_STEP1: {
            int32_t limit_slot=(insn->c>>16)&0xffff;
            int32_t const_slot=insn->c&0xffff;
            MValue *text=local_ptr(vm,frame,insn->a);
            MValue *idx=local_ptr(vm,frame,insn->b);
            MValue *limit=local_ptr(vm,frame,limit_slot);
            const MValue *suffix;
            int64_t i, n, repeats_i64;
            size_t repeats, old_len, suffix_len, new_len;
            MValue next;
            char *dst;
            if (!text || !idx || !limit || idx->tag!=MVAL_I64 || limit->tag!=MVAL_I64 || text->tag!=MVAL_STR){set_error(out,"str_append_repeat_step1_requires_str_i64");return 0;}
            if (const_slot < 0 || (size_t)const_slot >= program->const_len){set_error(out,"str_append_repeat_const_oob");return 0;}
            suffix=&program->const_pool[const_slot];
            if (suffix->tag!=MVAL_STR){set_error(out,"str_append_repeat_suffix_requires_str");return 0;}
            i=idx->as.i64; n=limit->as.i64;
            if (i >= n){pc++; break;}
            repeats_i64=n-i;
            if (repeats_i64 < 0){pc++; break;}
            repeats=(size_t)repeats_i64;
            old_len=text->as.str.len;
            suffix_len=suffix->as.str.len;
            if (suffix_len && repeats > ((size_t)-1 - old_len) / suffix_len){set_error(out,"str_append_repeat_overflow");return 0;}
            new_len=old_len + repeats * suffix_len;
            next=mval_owned_str(vm,NULL,new_len);
            if (!next.as.str.ptr){set_error(out,"str_append_repeat_alloc_failed");return 0;}
            dst=(char*)next.as.str.ptr;
            if (old_len) memcpy(dst,text->as.str.ptr,old_len);
            dst += old_len;
            for (size_t r=0; r<repeats; ++r) {
                if (suffix_len) memcpy(dst, suffix->as.str.ptr, suffix_len);
                dst += suffix_len;
            }
            mvalue_release_temp(text);
            *text=next;
            idx->as.i64=n;
            pc++; break;
        }

        /* arithmetic */
        case MOP_ADD: case MOP_SUB: case MOP_MUL: case MOP_DIV: {
            MValue b=pop(vm), a=pop(vm);
            if (a.tag==MVAL_I64 && b.tag==MVAL_I64 && insn->opcode!=MOP_DIV) {
                int64_t r = (insn->opcode==MOP_ADD) ? (a.as.i64 + b.as.i64)
                          : (insn->opcode==MOP_SUB) ? (a.as.i64 - b.as.i64)
                          : (a.as.i64 * b.as.i64);
                if (!push(vm,mval_i64(r))){set_error(out,"numeric_push_failed");return 0;}
                pc++; break;
            }
            if (insn->opcode==MOP_ADD&&(a.tag==MVAL_STR||b.tag==MVAL_STR)){
                char abuf[64],bbuf[64]; const char *ap=NULL,*bp=NULL; size_t alen=0,blen=0;
                if (!coerce_str(a,abuf,sizeof(abuf),&ap,&alen)||!coerce_str(b,bbuf,sizeof(bbuf),&bp,&blen)){
                    mvalue_release_temp(&a);mvalue_release_temp(&b);set_error(out,"string_concat_unsupported_type");return 0;
                }
                MValue sv=mval_owned_str(vm,NULL,alen+blen);
                if (!sv.as.str.ptr){mvalue_release_temp(&a);mvalue_release_temp(&b);set_error(out,"string_concat_alloc_failed");return 0;}
                memcpy((char*)sv.as.str.ptr,ap,alen); memcpy((char*)sv.as.str.ptr+alen,bp,blen);
                mvalue_release_temp(&a);mvalue_release_temp(&b);
                if (!push(vm,sv)){mvalue_free(&sv);set_error(out,"string_concat_push_failed");return 0;}
                pc++; break;
            }
            if ((a.tag!=MVAL_I64&&a.tag!=MVAL_F64)||(b.tag!=MVAL_I64&&b.tag!=MVAL_F64)){mvalue_release_temp(&a);mvalue_release_temp(&b);set_error(out,"numeric_op_requires_numbers");return 0;}
            int use_f=(a.tag==MVAL_F64||b.tag==MVAL_F64||insn->opcode==MOP_DIV);
            double da=(a.tag==MVAL_F64)?a.as.f64:(double)a.as.i64;
            double db=(b.tag==MVAL_F64)?b.as.f64:(double)b.as.i64;
            if (insn->opcode==MOP_DIV&&db==0.0){mvalue_release_temp(&a);mvalue_release_temp(&b);set_error(out,"division_by_zero");return 0;}
            double res=(insn->opcode==MOP_ADD)?da+db:(insn->opcode==MOP_SUB)?da-db:(insn->opcode==MOP_MUL)?da*db:da/db;
            mvalue_release_temp(&a);mvalue_release_temp(&b);
            if (!push(vm,use_f?mval_f64(res):mval_i64((int64_t)res))){set_error(out,"numeric_push_failed");return 0;}
            pc++; break;
        }

        /* v2.3.4: modulo */
        case MOP_MOD: {
            MValue b=pop(vm), a=pop(vm);
            if (a.tag==MVAL_I64&&b.tag==MVAL_I64){
                if (b.as.i64==0){set_error(out,"modulo_by_zero");return 0;}
                int64_t r=a.as.i64%b.as.i64;
                if (r!=0&&((r<0)!=(b.as.i64<0))) r+=b.as.i64; /* Python-style sign */
                if (!push(vm,mval_i64(r))){set_error(out,"mod_push_failed");return 0;}
            } else {
                double da=(a.tag==MVAL_F64)?a.as.f64:(double)a.as.i64;
                double db=(b.tag==MVAL_F64)?b.as.f64:(double)b.as.i64;
                if (db==0.0){mvalue_release_temp(&a);mvalue_release_temp(&b);set_error(out,"modulo_by_zero");return 0;}
                if (!push(vm,mval_f64(fmod(da,db)))){set_error(out,"mod_push_failed");return 0;}
            }
            mvalue_release_temp(&a);mvalue_release_temp(&b);
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
            mvalue_release_temp(&a);mvalue_release_temp(&b);
            pc++; break;
        }

        /* v2.3.4: boolean ops */
        case MOP_BOOL_AND: { MValue b=pop(vm),a=pop(vm); int r=truthy(a)&&truthy(b); mvalue_release_temp(&a);mvalue_release_temp(&b); if(!push(vm,mval_bool(r))){set_error(out,"bool_and_failed");return 0;} pc++; break; }
        case MOP_BOOL_OR:  { MValue b=pop(vm),a=pop(vm); int r=truthy(a)||truthy(b); mvalue_release_temp(&a);mvalue_release_temp(&b); if(!push(vm,mval_bool(r))){set_error(out,"bool_or_failed"); return 0;} pc++; break; }
        case MOP_BOOL_NOT: { MValue a=pop(vm); int r=!truthy(a); mvalue_release_temp(&a); if(!push(vm,mval_bool(r))){set_error(out,"bool_not_failed");return 0;} pc++; break; }

        /* compare + jumps */
        case MOP_COMPARE: {
            MValue b=pop(vm),a=pop(vm);
            int r=0;
            if (a.tag==MVAL_I64 && b.tag==MVAL_I64) {
                switch((MCompareOp)insn->a){
                    case MCMP_EQ: r=a.as.i64==b.as.i64; break;
                    case MCMP_NE: r=a.as.i64!=b.as.i64; break;
                    case MCMP_LT: r=a.as.i64<b.as.i64; break;
                    case MCMP_LE: r=a.as.i64<=b.as.i64; break;
                    case MCMP_GT: r=a.as.i64>b.as.i64; break;
                    case MCMP_GE: r=a.as.i64>=b.as.i64; break;
                    default: r=0; break;
                }
            } else {
                r=generic_compare(a,b,(MCompareOp)insn->a);
                mvalue_release_temp(&a);mvalue_release_temp(&b);
            }
            if(!push(vm,mval_bool(r))){set_error(out,"compare_failed");return 0;} pc++; break;
        }
        case MOP_JUMP: pc=(uint32_t)insn->a; break;
        case MOP_JUMP_IF_FALSE: { MValue c=pop(vm); int r=truthy(c); mvalue_release_temp(&c); pc=r?pc+1:(uint32_t)insn->a; break; }
        case MOP_JUMP_IF_LOCAL_I64_LT_FALSE: {
            MValue *left=local_ptr(vm,frame,insn->a);
            MValue *right=local_ptr(vm,frame,insn->b);
            if (!left || !right || left->tag!=MVAL_I64 || right->tag!=MVAL_I64){set_error(out,"i64_lt_local_jump_requires_i64");return 0;}
            pc = (left->as.i64 < right->as.i64) ? pc+1 : (uint32_t)insn->c;
            break;
        }

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
            size_t local_count = callee.as.func.local_count > argc ? callee.as.func.local_count : argc;
            size_t lb = frame ? (size_t)frame->local_base + (size_t)frame->local_count : vm->locals_len;
            if (!ensure_local_window(vm, lb + local_count)) { set_error(out,"call_local_alloc_failed"); return 0; }
            for (size_t i = 0; i < argc; ++i) vm->locals[lb+i] = vm->stack[args_base+i];
            for (size_t i = argc; i < local_count; ++i) vm->locals[lb+i] = mval_none();
            vm->locals_len = lb + local_count;
            vm->stack_len = args_base;   /* pop args + func_ref */
            vm->frames[vm->frame_len++] = (MFrame){
                .frame_id=(uint32_t)vm->frame_len, .return_pc=pc+1,
                .base=(uint32_t)vm->stack_len, .local_base=(uint32_t)lb,
                .local_count=(uint32_t)local_count, .function=callee.as.func
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
            size_t local_count=callee.as.func.local_count>argc?callee.as.func.local_count:argc;
            size_t lb=frame?(size_t)frame->local_base+(size_t)frame->local_count:vm->locals_len;
            if (!ensure_local_window(vm,lb+local_count)){set_error(out,"call_val_local_alloc_failed");return 0;}
            for(size_t i=0;i<argc;++i) vm->locals[lb+i]=vm->stack[args_base+i];
            for(size_t i=argc;i<local_count;++i) vm->locals[lb+i]=mval_none();
            vm->locals_len=lb+local_count;
            vm->stack_len=args_base-1;
            vm->frames[vm->frame_len++]=(MFrame){.frame_id=(uint32_t)vm->frame_len,.return_pc=pc+1,.base=(uint32_t)vm->stack_len,.local_base=(uint32_t)lb,.local_count=(uint32_t)local_count,.function=callee.as.func};
            pc=callee.as.func.address; break;
        }

        case MOP_RETURN: {
            MValue ret=vm->stack_len?pop(vm):mval_none();
            if (vm->frame_len<=1){
                if (vm->current_task == 0) out->result = ret;
                else vm->tasks[vm->current_task].result = ret;
                goto finish_current_task_with_result;
            }
            MFrame ended=vm->frames[--vm->frame_len];
            {
                size_t local_end=(size_t)ended.local_base+(size_t)ended.local_count;
                if (local_end>vm->locals_len) local_end=vm->locals_len;
                for(size_t i=ended.local_base;i<local_end;++i) mvalue_release_temp(&vm->locals[i]);
                vm->locals_len=ended.local_base;
            }
            vm->stack_len=ended.base;
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
                selected=mvalue_clone(vm, &cont.as.list.items[(size_t)i]);
            } else if (cont.tag==MVAL_MAP){
                MValue val=mval_none();
                if (!map_get(&cont.as.map,&idx,&val)){mvalue_free(&idx);mvalue_free(&cont);set_error(out,"getitem_key_not_found");return 0;}
                selected=mvalue_clone(vm, &val);
            } else if (cont.tag==MVAL_STR){
                int64_t i=(idx.tag==MVAL_I64)?idx.as.i64:(idx.tag==MVAL_F64)?(int64_t)idx.as.f64:-1;
                if (i<0) i+=(int64_t)cont.as.str.len;
                if (i<0||(size_t)i>=cont.as.str.len){mvalue_free(&idx);mvalue_free(&cont);set_error(out,"getitem_index_out_of_range");return 0;}
                char ch[1]; ch[0]=cont.as.str.ptr[(size_t)i];
                selected=mval_owned_str(vm,ch,1);
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

