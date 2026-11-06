static void free_channel(MellowRuntimeContext *ctx, MellowChannel *ch){
    size_t i;
    if(!ch)return;
    for(i=0;i<ch->len;++i)mvalue_free(&ch->items[i]);
    free(ch->items);
    ch->items=NULL;
    ch->len=ch->cap=0;
    ch->magic=0;
    if(ctx){
        ctx->native_freed++;
        if(ctx->native_live>0)ctx->native_live--;
    }
    free(ch);
}

static void free_canvas(MellowRuntimeContext *ctx, MellowCanvas *canvas){
    if(!canvas)return;
    free(canvas->pixels);
    canvas->pixels=NULL;
    canvas->width=0;
    canvas->height=0;
    canvas->magic=0;
    if(ctx){
        ctx->native_freed++;
        if(ctx->native_live>0)ctx->native_live--;
    }
    free(canvas);
}

static void free_native(MellowRuntimeContext *ctx, MellowNativeHeader *node){
    if(!node)return;
    if(node->magic==MELLOW_NATIVE_CHANNEL_MAGIC){
        free_channel(ctx,(MellowChannel*)node);
    }else if(node->magic==MELLOW_NATIVE_CANVAS_MAGIC){
        free_canvas(ctx,(MellowCanvas*)node);
    }else{
        free(node);
    }
}

static uint64_t collect_value_heap(MellowRuntimeContext *ctx){
    if(!ctx||!ctx->vm)return 0;
    return mvm_gc_collect_with_marker(ctx->vm, mark_channel_queue_values, ctx);
}

static int print_value(FILE *out, const MValue *v){
    switch(v->tag){
    case MVAL_NONE: return fprintf(out,"none")>=0;
    case MVAL_BOOL: return fprintf(out,"%s",v->as.boolean?"true":"false")>=0;
    case MVAL_I64:  return fprintf(out,"%lld",(long long)v->as.i64)>=0;
    case MVAL_F64:  return fprintf(out,"%g",v->as.f64)>=0;
    case MVAL_STR:  return fprintf(out,"%.*s",(int)v->as.str.len,v->as.str.ptr?v->as.str.ptr:"")>=0;
    case MVAL_FUNC: return fprintf(out,"<func@%u>",v->as.func.address)>=0;
    case MVAL_LIST:{
        size_t i; if(fprintf(out,"[")<0)return 0;
        for(i=0;i<v->as.list.len;++i){if(i&&fprintf(out,", ")<0)return 0; if(!print_value(out,&v->as.list.items[i]))return 0;}
        return fprintf(out,"]")>=0;}
    case MVAL_MAP:{
        size_t i; if(fprintf(out,"{")<0)return 0;
        for(i=0;i<v->as.map.len;++i){
            if(i&&fprintf(out,", ")<0)return 0;
            if(!print_value(out,&v->as.map.keys[i]))return 0;
            if(fprintf(out,": ")<0)return 0;
            if(!print_value(out,&v->as.map.values[i]))return 0;
        }
        return fprintf(out,"}")>=0;}
    default: return fprintf(out,"<%s>",mvalue_tag_name(v->tag))>=0;
    }
}

static MValue mval_owned_copy(const char *src, size_t len){
    char *buf=(char*)calloc(len+1,1); MValue v=mval_none();
    if(!buf)return v;
    if(src&&len) memcpy(buf,src,len);
    buf[len]='\0';
    v.tag=MVAL_STR; v.flags=1u; v.as.str.ptr=buf; v.as.str.len=len;
    return v;
}

static int numeric_value(const MValue *value, double *out){
    if(value->tag==MVAL_I64){*out=(double)value->as.i64;return 1;}
    if(value->tag==MVAL_F64&&isfinite(value->as.f64)){*out=value->as.f64;return 1;}
    return 0;
}

static MValue clone_value(MellowRuntimeContext *ctx, const MValue *src){
    if(ctx&&ctx->vm)return mvalue_clone(ctx->vm,src);
    if(!src)return mval_none();
    switch(src->tag){
    case MVAL_STR:
        return mval_owned_copy(src->as.str.ptr,src->as.str.len);
    case MVAL_LIST:{
        MValue v=mval_none();
        size_t i;
        v.tag=MVAL_LIST;
        v.as.list.len=v.as.list.cap=src->as.list.len;
        v.as.list.items=src->as.list.len?(MValue*)calloc(src->as.list.len,sizeof(MValue)):NULL;
        if(src->as.list.len&&!v.as.list.items)return mval_none();
        for(i=0;i<src->as.list.len;++i)v.as.list.items[i]=clone_value(ctx,&src->as.list.items[i]);
        return v;
    }
    case MVAL_MAP:{
        MValue v=mval_none();
        size_t i;
        v.tag=MVAL_MAP;
        v.as.map.len=v.as.map.cap=src->as.map.len;
        v.as.map.keys=src->as.map.len?(MValue*)calloc(src->as.map.len,sizeof(MValue)):NULL;
        v.as.map.values=src->as.map.len?(MValue*)calloc(src->as.map.len,sizeof(MValue)):NULL;
        if(src->as.map.len&&(!v.as.map.keys||!v.as.map.values)){
            free(v.as.map.keys);free(v.as.map.values);return mval_none();
        }
        for(i=0;i<src->as.map.len;++i){
            v.as.map.keys[i]=clone_value(ctx,&src->as.map.keys[i]);
            v.as.map.values[i]=clone_value(ctx,&src->as.map.values[i]);
        }
        return v;
    }
    default:
        return *src;
    }
}

static MValue native_ptr(void *ptr){
    MValue v=mval_none();
    v.tag=MVAL_NATIVE;
    v.as.ptr=ptr;
    return v;
}

static MellowChannel *as_channel(const MValue *value){
    MellowChannel *ch;
    if(!value||value->tag!=MVAL_NATIVE||!value->as.ptr)return NULL;
    ch=(MellowChannel*)value->as.ptr;
    return ch->magic==MELLOW_NATIVE_CHANNEL_MAGIC?ch:NULL;
}

static MellowCanvas *as_canvas(const MValue *value){
    MellowCanvas *canvas;
    if(!value||value->tag!=MVAL_NATIVE||!value->as.ptr)return NULL;
    canvas=(MellowCanvas*)value->as.ptr;
    return canvas->magic==MELLOW_NATIVE_CANVAS_MAGIC?canvas:NULL;
}

static void register_native(MellowRuntimeContext *ctx, MellowNativeHeader *node){
    if(!ctx||!node)return;
    node->next=(MellowNativeHeader*)ctx->native_registry;
    ctx->native_registry=node;
    ctx->native_allocated++;
    ctx->native_live++;
}

static void register_channel(MellowRuntimeContext *ctx, MellowChannel *ch){
    if(!ctx||!ch)return;
    register_native(ctx,(MellowNativeHeader*)ch);
}

static void mark_channel(MellowRuntimeContext *ctx, MellowChannel *ch){
    size_t i;
    if(!ctx||!ch||ch->marked)return;
    ch->marked=1;
    for(i=0;i<ch->len;++i)mark_value(ctx,&ch->items[i]);
}

static void mark_canvas(MellowRuntimeContext *ctx, MellowCanvas *canvas){
    (void)ctx;
    if(!canvas||canvas->marked)return;
    canvas->marked=1;
}

static void mark_native(MellowRuntimeContext *ctx, MellowNativeHeader *node){
    if(!node)return;
    if(node->magic==MELLOW_NATIVE_CHANNEL_MAGIC)mark_channel(ctx,(MellowChannel*)node);
    else if(node->magic==MELLOW_NATIVE_CANVAS_MAGIC)mark_canvas(ctx,(MellowCanvas*)node);
}

static void mark_value(MellowRuntimeContext *ctx, const MValue *value){
    size_t i;
    if(!ctx||!value)return;
    switch(value->tag){
    case MVAL_NATIVE:
        mark_native(ctx,(MellowNativeHeader*)value->as.ptr);
        break;
    case MVAL_LIST:
        for(i=0;i<value->as.list.len;++i)mark_value(ctx,&value->as.list.items[i]);
        break;
    case MVAL_MAP:
        for(i=0;i<value->as.map.len;++i){
            mark_value(ctx,&value->as.map.keys[i]);
            mark_value(ctx,&value->as.map.values[i]);
        }
        break;
    default:
        break;
    }
}

void mellowrt_collect_garbage(MellowRuntimeContext *ctx){
    MellowNativeHeader *node;
    MellowNativeHeader *prev=NULL;
    MellowNativeHeader *next;
    uint64_t freed=0;
    size_t i;
    if(!ctx)return;
    for(node=(MellowNativeHeader*)ctx->native_registry;node;node=node->next)node->marked=0;
    if(ctx->vm){
        for(i=0;i<ctx->vm->stack_len;++i)mark_value(ctx,&ctx->vm->stack[i]);
        for(i=0;i<ctx->vm->locals_len;++i)mark_value(ctx,&ctx->vm->locals[i]);
    }
    node=(MellowNativeHeader*)ctx->native_registry;
    while(node){
        next=node->next;
        if(!node->marked){
            if(prev)prev->next=next;
            else ctx->native_registry=next;
            free_native(ctx,node);
            freed++;
        }else{
            prev=node;
        }
        node=next;
    }
    ctx->gc_collections++;
    ctx->gc_freed+=freed;
}

static void mark_channel_queue_values(void *user, MVM *vm){
    MellowRuntimeContext *ctx=(MellowRuntimeContext*)user;
    MellowNativeHeader *node;
    MellowChannel *ch;
    size_t i;
    (void)vm;
    if(!ctx)return;
    for(node=(MellowNativeHeader*)ctx->native_registry;node;node=node->next){
        if(node->magic!=MELLOW_NATIVE_CHANNEL_MAGIC)continue;
        ch=(MellowChannel*)node;
        for(i=0;i<ch->len;++i)mvm_gc_mark_value(ctx->vm,&ch->items[i]);
    }
}

static int channel_push(MellowRuntimeContext *ctx,MellowChannel *ch,const MValue *value){
    MValue *grown;
    size_t next;
    if(!ch)return 0;
    if(ch->len>=ch->cap){
        next=ch->cap?ch->cap*2:8;
        grown=(MValue*)realloc(ch->items,next*sizeof(MValue));
        if(!grown)return 0;
        ch->items=grown;
        ch->cap=next;
    }
    ch->items[ch->len++]=clone_value(ctx,value);
    return 1;
}

static MValue channel_pop(MellowChannel *ch,int *ok){
    MValue value=mval_none();
    if(ok)*ok=0;
    if(!ch||ch->len==0)return value;
    value=ch->items[0];
    if(ch->len>1)memmove(ch->items,ch->items+1,(ch->len-1)*sizeof(MValue));
    ch->len--;
    if(ok)*ok=1;
    return value;
}

static int integer_arg(const MValue *value, int *out){
    if(value->tag==MVAL_I64){
        if(value->as.i64<(int64_t)INT32_MIN||value->as.i64>(int64_t)INT32_MAX)return 0;
        *out=(int)value->as.i64;
        return 1;
    }
    if(value->tag==MVAL_F64&&isfinite(value->as.f64)&&value->as.f64>=(double)INT32_MIN&&value->as.f64<=(double)INT32_MAX){
        *out=(int)value->as.f64;
        return 1;
    }
    return 0;
}

static int hex_digit(char c){
    if(c>='0'&&c<='9')return c-'0';
    if(c>='a'&&c<='f')return 10+c-'a';
    if(c>='A'&&c<='F')return 10+c-'A';
    return -1;
}

