#ifndef _WIN32
#define _POSIX_C_SOURCE 199309L
#endif

#include "mellowrt_syscalls.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#ifdef _WIN32
#include <direct.h>
#include <windows.h>
#else
#include <unistd.h>
#endif

#define MELLOW_NATIVE_CHANNEL_MAGIC 0x4d43484eu

typedef struct MellowChannel {
    uint32_t magic;
    int marked;
    struct MellowChannel *next;
    MValue *items;
    size_t len;
    size_t cap;
} MellowChannel;

static void mark_value(MellowRuntimeContext *ctx, const MValue *value);

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

static uint64_t collect_value_heap(MellowRuntimeContext *ctx){
    if(!ctx||!ctx->vm)return 0;
    return mvm_gc_collect(ctx->vm);
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

static MValue clone_value(const MValue *src){
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
        for(i=0;i<src->as.list.len;++i)v.as.list.items[i]=clone_value(&src->as.list.items[i]);
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
            v.as.map.keys[i]=clone_value(&src->as.map.keys[i]);
            v.as.map.values[i]=clone_value(&src->as.map.values[i]);
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

static void register_channel(MellowRuntimeContext *ctx, MellowChannel *ch){
    if(!ctx||!ch)return;
    ch->next=(MellowChannel*)ctx->native_registry;
    ctx->native_registry=ch;
    ctx->native_allocated++;
    ctx->native_live++;
}

static void mark_channel(MellowRuntimeContext *ctx, MellowChannel *ch){
    size_t i;
    if(!ctx||!ch||ch->marked)return;
    ch->marked=1;
    for(i=0;i<ch->len;++i)mark_value(ctx,&ch->items[i]);
}

static void mark_value(MellowRuntimeContext *ctx, const MValue *value){
    size_t i;
    MellowChannel *ch;
    if(!ctx||!value)return;
    switch(value->tag){
    case MVAL_NATIVE:
        ch=as_channel(value);
        if(ch)mark_channel(ctx,ch);
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
    MellowChannel *ch;
    MellowChannel *prev=NULL;
    MellowChannel *next;
    uint64_t freed=0;
    size_t i;
    if(!ctx)return;
    for(ch=(MellowChannel*)ctx->native_registry;ch;ch=ch->next)ch->marked=0;
    if(ctx->vm){
        for(i=0;i<ctx->vm->stack_len;++i)mark_value(ctx,&ctx->vm->stack[i]);
        for(i=0;i<ctx->vm->locals_len;++i)mark_value(ctx,&ctx->vm->locals[i]);
    }
    ch=(MellowChannel*)ctx->native_registry;
    while(ch){
        next=ch->next;
        if(!ch->marked){
            if(prev)prev->next=next;
            else ctx->native_registry=next;
            free_channel(ctx,ch);
            freed++;
        }else{
            prev=ch;
        }
        ch=next;
    }
    ctx->gc_collections++;
    ctx->gc_freed+=freed;
}

static int channel_push(MellowChannel *ch,const MValue *value){
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
    ch->items[ch->len++]=clone_value(value);
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

static MValue stats_map(const MellowRuntimeContext *ctx){
    MValue v=mval_none();
    v.tag=MVAL_MAP;
    v.as.map.len=v.as.map.cap=13;
    v.as.map.keys=(MValue*)calloc(13,sizeof(MValue));
    v.as.map.values=(MValue*)calloc(13,sizeof(MValue));
    if(!v.as.map.keys||!v.as.map.values){
        free(v.as.map.keys);free(v.as.map.values);return mval_none();
    }
    v.as.map.keys[0]=mval_owned_copy("collections",11);
    v.as.map.values[0]=mval_i64(ctx?(int64_t)ctx->gc_collections:0);
    v.as.map.keys[1]=mval_owned_copy("spawned",7);
    v.as.map.values[1]=mval_i64(ctx?(int64_t)ctx->spawned_tasks:0);
    v.as.map.keys[2]=mval_owned_copy("yielded",7);
    v.as.map.values[2]=mval_i64(ctx?(int64_t)ctx->yielded_tasks:0);
    v.as.map.keys[3]=mval_owned_copy("channels",8);
    v.as.map.values[3]=mval_i64(ctx?(int64_t)ctx->channel_count:0);
    v.as.map.keys[4]=mval_owned_copy("mode",4);
    v.as.map.values[4]=mval_owned_copy("mark-sweep-native-handles",25);
    v.as.map.keys[5]=mval_owned_copy("gc_freed",8);
    v.as.map.values[5]=mval_i64(ctx?(int64_t)ctx->gc_freed:0);
    v.as.map.keys[6]=mval_owned_copy("native_live",11);
    v.as.map.values[6]=mval_i64(ctx?(int64_t)ctx->native_live:0);
    v.as.map.keys[7]=mval_owned_copy("native_allocated",16);
    v.as.map.values[7]=mval_i64(ctx?(int64_t)ctx->native_allocated:0);
    v.as.map.keys[8]=mval_owned_copy("native_freed",12);
    v.as.map.values[8]=mval_i64(ctx?(int64_t)ctx->native_freed:0);
    v.as.map.keys[9]=mval_owned_copy("heap_live",9);
    v.as.map.values[9]=mval_i64((ctx&&ctx->vm)?(int64_t)ctx->vm->heap_live:0);
    v.as.map.keys[10]=mval_owned_copy("heap_allocated",14);
    v.as.map.values[10]=mval_i64((ctx&&ctx->vm)?(int64_t)ctx->vm->heap_allocated:0);
    v.as.map.keys[11]=mval_owned_copy("heap_freed",10);
    v.as.map.values[11]=mval_i64((ctx&&ctx->vm)?(int64_t)ctx->vm->heap_freed:0);
    v.as.map.keys[12]=mval_owned_copy("heap_last_gc_freed",18);
    v.as.map.values[12]=mval_i64((ctx&&ctx->vm)?(int64_t)ctx->vm->heap_last_gc_freed:0);
    return v;
}

int mellowrt_default_syscall(void *user, int32_t id, const MValue *args, size_t argc, MValue *out_result){
    MellowRuntimeContext *ctx=(MellowRuntimeContext*)user;
    *out_result=mval_none();
    switch(id){
    case 1:{
        size_t i; for(i=0;i<argc;++i){if(i)fputc(' ',stdout);print_value(stdout,&args[i]);}
        fputc('\n',stdout); return 1;
    }
    case 2:
        if(argc!=1)return 0;
        if(args[0].tag==MVAL_STR)  {*out_result=mval_i64((int64_t)args[0].as.str.len);  return 1;}
        if(args[0].tag==MVAL_LIST) {*out_result=mval_i64((int64_t)args[0].as.list.len); return 1;}
        if(args[0].tag==MVAL_MAP)  {*out_result=mval_i64((int64_t)args[0].as.map.len);  return 1;}
        return 0;
    case 3:{
        long long ms=(long long)((double)clock()*1000.0/(double)CLOCKS_PER_SEC);
        *out_result=mval_i64((int64_t)ms); return 1;
    }
    case 4:{
        if(argc!=1||args[0].tag!=MVAL_STR)return 0;
        char *key=(char*)calloc(args[0].as.str.len+1,1); const char *v;
        if(!key)return 0;
        memcpy(key,args[0].as.str.ptr,args[0].as.str.len);
        v=getenv(key); free(key);
        if(!v)*out_result=mval_none();
        else  *out_result=mval_owned_copy(v,strlen(v));
        return 1;
    }
    case 5:{
        if(argc!=1)return 0;
        char buf[64];
        switch(args[0].tag){
        case MVAL_NONE: *out_result=mval_owned_copy("none",4); break;
        case MVAL_BOOL: *out_result=mval_owned_copy(args[0].as.boolean?"true":"false",args[0].as.boolean?4:5); break;
        case MVAL_I64:{ int n=snprintf(buf,sizeof(buf),"%lld",(long long)args[0].as.i64); *out_result=mval_owned_copy(buf,(size_t)(n>0?n:0)); break;}
        case MVAL_F64:{ int n=snprintf(buf,sizeof(buf),"%g",args[0].as.f64); *out_result=mval_owned_copy(buf,(size_t)(n>0?n:0)); break;}
        case MVAL_STR: *out_result=mval_owned_copy(args[0].as.str.ptr,args[0].as.str.len); break;
        default:{ const char *tn=mvalue_tag_name(args[0].tag); *out_result=mval_owned_copy(tn,strlen(tn)); break;}
        }
        return 1;
    }
    case 6:
        if(argc!=1)return 0;
        {const char *tn=mvalue_tag_name(args[0].tag); *out_result=mval_owned_copy(tn,strlen(tn)); return 1;}
    case 7:
        if(argc!=1)return 0;
        if(args[0].tag==MVAL_I64){if(args[0].as.i64==INT64_MIN)return 0;*out_result=mval_i64(args[0].as.i64<0?-args[0].as.i64:args[0].as.i64);return 1;}
        if(args[0].tag==MVAL_F64){*out_result=mval_f64(fabs(args[0].as.f64));return 1;}
        return 0;
    case 8:
        if(argc!=1)return 0;
        if(args[0].tag==MVAL_I64){*out_result=args[0];return 1;}
        if(args[0].tag==MVAL_F64&&isfinite(args[0].as.f64)&&args[0].as.f64>=(double)INT64_MIN&&args[0].as.f64<(double)INT64_MAX){*out_result=mval_i64((int64_t)floor(args[0].as.f64));return 1;}
        return 0;
    case 9:
        if(argc!=1)return 0;
        if(args[0].tag==MVAL_I64){*out_result=args[0];return 1;}
        if(args[0].tag==MVAL_F64&&isfinite(args[0].as.f64)&&args[0].as.f64>=(double)INT64_MIN&&args[0].as.f64<(double)INT64_MAX){*out_result=mval_i64((int64_t)ceil(args[0].as.f64));return 1;}
        return 0;
    case 10:
        if(argc!=1)return 0;
        {double v;if(!numeric_value(&args[0],&v)||v<0.0)return 0; *out_result=mval_f64(sqrt(v));return 1;}
    case 11:
        if(argc!=2)return 0;
        {double a,b;if(!numeric_value(&args[0],&a)||!numeric_value(&args[1],&b))return 0;
         if(args[0].tag==MVAL_I64&&args[1].tag==MVAL_I64)*out_result=mval_i64(args[0].as.i64<args[1].as.i64?args[0].as.i64:args[1].as.i64);
         else *out_result=mval_f64(a<b?a:b);
         return 1;}
    case 12:
        if(argc!=2)return 0;
        {double a,b;if(!numeric_value(&args[0],&a)||!numeric_value(&args[1],&b))return 0;
         if(args[0].tag==MVAL_I64&&args[1].tag==MVAL_I64)*out_result=mval_i64(args[0].as.i64>args[1].as.i64?args[0].as.i64:args[1].as.i64);
         else *out_result=mval_f64(a>b?a:b);
         return 1;}
    case 13:{
        size_t i; for(i=0;i<argc;++i){if(i)fputc(' ',stdout);print_value(stdout,&args[i]);}
        fputc('\n',stdout); return 1;
    }
    case 14:{
        size_t i; for(i=0;i<argc;++i){if(i)fputc(' ',stdout);print_value(stdout,&args[i]);}
        fflush(stdout); return 1;
    }
    case 15:{
        char buf[4096];
        size_t len;
        if(argc>1)return 0;
        if(argc==1){print_value(stdout,&args[0]);fflush(stdout);}
        if(!fgets(buf,sizeof(buf),stdin)){*out_result=mval_owned_copy("",0);return 1;}
        len=strlen(buf);
        while(len>0 && (buf[len-1]=='\n' || buf[len-1]=='\r')) buf[--len]='\0';
        *out_result=mval_owned_copy(buf,len);
        return 1;
    }
    case 16:{
        int start=ctx?ctx->script_arg_start:0;
        int total=ctx?ctx->argc:0;
        size_t count=(total>start)?(size_t)(total-start):0;
        size_t i;
        MValue v=mval_none();
        if(argc!=0)return 0;
        v.tag=MVAL_LIST;
        v.as.list.len=v.as.list.cap=count;
        v.as.list.items=count?(MValue*)calloc(count,sizeof(MValue)):NULL;
        if(count&&!v.as.list.items)return 0;
        for(i=0;i<count;++i){
            const char *s=ctx->argv[start+(int)i]?ctx->argv[start+(int)i]:"";
            v.as.list.items[i]=mval_owned_copy(s,strlen(s));
        }
        *out_result=v;
        return 1;
    }
    case 17:{
        char buf[4096];
        if(argc!=0)return 0;
#ifdef _WIN32
        if(!_getcwd(buf,sizeof(buf)))return 0;
#else
        if(!getcwd(buf,sizeof(buf)))return 0;
#endif
        *out_result=mval_owned_copy(buf,strlen(buf));
        return 1;
    }
    case 18:{
        int64_t ms;
        if(argc!=1||args[0].tag!=MVAL_I64)return 0;
        ms=args[0].as.i64;
        if(ms<0)return 0;
#ifdef _WIN32
        Sleep((DWORD)ms);
#else
        {
            struct timespec ts;
            ts.tv_sec=(time_t)(ms/1000);
            ts.tv_nsec=(long)((ms%1000)*1000000);
            nanosleep(&ts,NULL);
        }
#endif
        return 1;
    }
    case 19:{
        int code=0;
        if(argc>1)return 0;
        if(argc==1){if(args[0].tag!=MVAL_I64)return 0; code=(int)args[0].as.i64;}
        fflush(stdout);
        fflush(stderr);
        exit(code);
    }
    case 20: {
        uint64_t count;
        int64_t start = 0;
        int64_t stop = 0;
        if (argc != 1 && argc != 2) return 0;
        if ((args[0].tag != MVAL_I64 && args[0].tag != MVAL_F64) ||
            (argc == 2 && args[1].tag != MVAL_I64 && args[1].tag != MVAL_F64)) return 0;
        if ((args[0].tag == MVAL_F64 && (!isfinite(args[0].as.f64) || args[0].as.f64 < (double)INT64_MIN || args[0].as.f64 >= (double)INT64_MAX)) ||
            (argc == 2 && args[1].tag == MVAL_F64 && (!isfinite(args[1].as.f64) || args[1].as.f64 < (double)INT64_MIN || args[1].as.f64 >= (double)INT64_MAX))) return 0;
        if (argc == 1) {
            stop = (args[0].tag == MVAL_I64) ? args[0].as.i64 : (int64_t)args[0].as.f64;
        } else {
            start = (args[0].tag == MVAL_I64) ? args[0].as.i64 : (int64_t)args[0].as.f64;
            stop  = (args[1].tag == MVAL_I64) ? args[1].as.i64 : (int64_t)args[1].as.f64;
        }
        count = stop > start ? (uint64_t)stop - (uint64_t)start : 0;
        if (count > 1000000u) return 0;
        MValue v = mval_none();
        v.tag = MVAL_LIST;
        v.as.list.len = v.as.list.cap = (size_t)count;
        v.as.list.items = count ? (MValue *)calloc((size_t)count, sizeof(MValue)) : NULL;
        if (count && !v.as.list.items) return 0;
        for (uint64_t i = 0; i < count; ++i) v.as.list.items[(size_t)i] = mval_i64(start + (int64_t)i);
        *out_result = v;
        return 1;
    }
    case 21:
        if(argc!=0)return 0;
        collect_value_heap(ctx);
        mellowrt_collect_garbage(ctx);
        *out_result=mval_i64(0);
        return 1;
    case 22:
        if(argc!=0)return 0;
        *out_result=stats_map(ctx);
        return 1;
    case 23:
        if(argc!=1)return 0;
        if(args[0].tag!=MVAL_FUNC)return 0;
        if(ctx)ctx->spawned_tasks++;
        *out_result=mval_i64(ctx?(int64_t)ctx->spawned_tasks:1);
        return 1;
    case 24:
        if(argc!=0)return 0;
        if(ctx)ctx->yielded_tasks++;
        return 1;
    case 25:{
        MellowChannel *ch;
        if(argc!=0)return 0;
        ch=(MellowChannel*)calloc(1,sizeof(MellowChannel));
        if(!ch)return 0;
        ch->magic=MELLOW_NATIVE_CHANNEL_MAGIC;
        if(ctx)ctx->channel_count++;
        register_channel(ctx,ch);
        *out_result=native_ptr(ch);
        return 1;
    }
    case 26:{
        MellowChannel *ch;
        if(argc!=2)return 0;
        ch=as_channel(&args[0]);
        if(!ch)return 0;
        if(!channel_push(ch,&args[1]))return 0;
        *out_result=mval_bool(1);
        return 1;
    }
    case 27:{
        MellowChannel *ch;
        int ok=0;
        if(argc!=1)return 0;
        ch=as_channel(&args[0]);
        if(!ch)return 0;
        *out_result=channel_pop(ch,&ok);
        if(!ok){
            if(ctx)ctx->yielded_tasks++;
            *out_result=mval_none();
        }
        return 1;
    }
    default: return 0;
    }
}
