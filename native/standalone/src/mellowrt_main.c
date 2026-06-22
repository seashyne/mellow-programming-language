/* mellowrt_main.c — v2.3.4 standalone runner
   Loads an MLVI binary image and executes it with mellowrt_core.
   No Python dependency. Build: cmake -S . -B build && cmake --build build
*/
#include "mellowrt.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <time.h>
#include <math.h>

#define MLVI_MAGIC     "MLVI0200"
#define MLVI_MAGIC_LEN 8

/* ── image structures ────────────────────────────────────────────────────── */
typedef struct { uint32_t slot; char *name; } MLoadedGlobal;
typedef struct { char *name; uint32_t address; uint16_t arity; uint16_t local_count; uint16_t flags; } MLoadedFunction;
typedef struct { char *name; uint32_t target; uint32_t flags; } MLoadedEvent;
typedef struct { char *name; uint32_t flags; } MLoadedModule;

typedef struct {
    MValue        *consts;       size_t const_len;
    MInstruction  *code;         size_t code_len;
    MSourceSpan   *spans;        size_t span_len;
    char          *source_name;
    char          *pipeline;
    MLoadedGlobal    *globals;   size_t globals_len;
    MLoadedFunction  *functions; size_t functions_len;
    MLoadedEvent     *events;    size_t events_len;
    MLoadedModule    *modules;   size_t modules_len;
} MLoadedProgram;

/* ── binary readers ──────────────────────────────────────────────────────── */
static uint8_t  read_u8 (FILE *f,int*ok){uint8_t  v=0;if(fread(&v,1,1,f)!=1)*ok=0;return v;}
static uint16_t read_u16(FILE *f,int*ok){uint16_t v=0;if(fread(&v,sizeof(v),1,f)!=1)*ok=0;return v;}
static uint32_t read_u32(FILE *f,int*ok){uint32_t v=0;if(fread(&v,sizeof(v),1,f)!=1)*ok=0;return v;}
static int32_t  read_i32(FILE *f,int*ok){int32_t  v=0;if(fread(&v,sizeof(v),1,f)!=1)*ok=0;return v;}
static int64_t  read_i64(FILE *f,int*ok){int64_t  v=0;if(fread(&v,sizeof(v),1,f)!=1)*ok=0;return v;}
static double   read_f64(FILE *f,int*ok){double   v=0;if(fread(&v,sizeof(v),1,f)!=1)*ok=0;return v;}
static char *read_string(FILE *f,int*ok){
    uint32_t len=read_u32(f,ok); if(!*ok)return NULL;
    char *buf=(char*)calloc((size_t)len+1,1); if(!buf){*ok=0;return NULL;}
    if(len&&fread(buf,1,len,f)!=len){free(buf);*ok=0;return NULL;}
    buf[len]='\0'; return buf;
}

static void free_loaded_program(MLoadedProgram *lp){
    size_t i;
    if(!lp)return;
    if(lp->consts){for(i=0;i<lp->const_len;++i)mvalue_free(&lp->consts[i]);free(lp->consts);}
    free(lp->code); free(lp->spans); free(lp->source_name); free(lp->pipeline);
    if(lp->globals)  {for(i=0;i<lp->globals_len;++i)  free(lp->globals[i].name);   free(lp->globals);}
    if(lp->functions){for(i=0;i<lp->functions_len;++i) free(lp->functions[i].name); free(lp->functions);}
    if(lp->events)   {for(i=0;i<lp->events_len;++i)    free(lp->events[i].name);    free(lp->events);}
    if(lp->modules)  {for(i=0;i<lp->modules_len;++i)   free(lp->modules[i].name);   free(lp->modules);}
    memset(lp,0,sizeof(*lp));
}

static int parse_loaded_program(const char *path, MLoadedProgram *out){
    FILE *f=fopen(path,"rb");
    char magic[MLVI_MAGIC_LEN];
    uint32_t version=0,flags_hdr=0,counts[7]={0};
    int ok=1; size_t i;
    if(!f)return 0;
    memset(out,0,sizeof(*out));
    if(fread(magic,1,MLVI_MAGIC_LEN,f)!=MLVI_MAGIC_LEN||memcmp(magic,MLVI_MAGIC,MLVI_MAGIC_LEN)){fclose(f);return 0;}
    version   =read_u32(f,&ok);
    flags_hdr =read_u32(f,&ok);
    (void)version;(void)flags_hdr;
    out->source_name=read_string(f,&ok);
    out->pipeline   =read_string(f,&ok);
    for(i=0;i<7;++i) counts[i]=read_u32(f,&ok);
    if(!ok)goto fail;

    /* globals */
    out->globals_len=counts[3];
    out->globals=(MLoadedGlobal*)calloc(out->globals_len?out->globals_len:1,sizeof(MLoadedGlobal));
    for(i=0;i<out->globals_len;++i){
        out->globals[i].slot=read_u32(f,&ok);
        out->globals[i].name=read_string(f,&ok);
    }
    /* functions */
    out->functions_len=counts[4];
    out->functions=(MLoadedFunction*)calloc(out->functions_len?out->functions_len:1,sizeof(MLoadedFunction));
    for(i=0;i<out->functions_len;++i){
        out->functions[i].name      =read_string(f,&ok);
        out->functions[i].address   =read_u32(f,&ok);
        out->functions[i].arity     =read_u16(f,&ok);
        out->functions[i].local_count=read_u16(f,&ok);
        out->functions[i].flags     =read_u16(f,&ok);
    }
    /* events */
    out->events_len=counts[5];
    out->events=(MLoadedEvent*)calloc(out->events_len?out->events_len:1,sizeof(MLoadedEvent));
    for(i=0;i<out->events_len;++i){
        out->events[i].name  =read_string(f,&ok);
        out->events[i].target=read_u32(f,&ok);
        out->events[i].flags =read_u32(f,&ok);
    }
    /* modules */
    out->modules_len=counts[6];
    out->modules=(MLoadedModule*)calloc(out->modules_len?out->modules_len:1,sizeof(MLoadedModule));
    for(i=0;i<out->modules_len;++i){
        out->modules[i].name =read_string(f,&ok);
        out->modules[i].flags=read_u32(f,&ok);
    }
    /* consts */
    out->const_len=counts[0];
    out->consts=(MValue*)calloc(out->const_len?out->const_len:1,sizeof(MValue));
    for(i=0;i<out->const_len;++i){
        out->consts[i]=mval_none();
        uint8_t tag=read_u8(f,&ok);
        switch(tag){
        case 0: out->consts[i]=mval_none(); break;
        case 1:{uint8_t b=read_u8(f,&ok); out->consts[i]=mval_bool((int)b); break;}
        case 2: out->consts[i]=mval_i64(read_i64(f,&ok)); break;
        case 3: out->consts[i]=mval_f64(read_f64(f,&ok)); break;
        case 4:{uint32_t slen=read_u32(f,&ok); char *sbuf=(char*)calloc((size_t)slen+1,1);
                if(!sbuf){ok=0;break;} if(slen&&fread(sbuf,1,slen,f)!=slen){free(sbuf);ok=0;break;}
                sbuf[slen]='\0'; out->consts[i].tag=MVAL_STR; out->consts[i].flags=1u;
                out->consts[i].as.str.ptr=sbuf; out->consts[i].as.str.len=slen; break;}
        case 8:{uint32_t addr=read_u32(f,&ok); uint16_t arity=read_u16(f,&ok);
                uint16_t lc=read_u16(f,&ok); uint16_t fl=read_u16(f,&ok);
                out->consts[i]=mval_func(addr,arity,lc,fl); break;}
        default: ok=0; break;
        }
    }
    /* code */
    out->code_len=counts[1];
    out->code=(MInstruction*)calloc(out->code_len?out->code_len:1,sizeof(MInstruction));
    for(i=0;i<out->code_len;++i){
        out->code[i].opcode=(uint8_t)read_u8(f,&ok);
        out->code[i].a=read_i32(f,&ok);
        out->code[i].b=read_i32(f,&ok);
        out->code[i].c=read_i32(f,&ok);
    }
    /* spans */
    out->span_len=counts[2];
    out->spans=(MSourceSpan*)calloc(out->span_len?out->span_len:1,sizeof(MSourceSpan));
    for(i=0;i<out->span_len;++i){
        out->spans[i].start_line=read_u32(f,&ok);
        out->spans[i].start_col =read_u32(f,&ok);
        out->spans[i].end_line  =read_u32(f,&ok);
        out->spans[i].end_col   =read_u32(f,&ok);
    }
    if(!ok)goto fail;
    fclose(f); return 1;
fail:
    fclose(f); free_loaded_program(out); return 0;
}

/* ── syscall table (v2.3.4) ─────────────────────────────────────────────── */
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

static int runtime_syscall(void *user, int32_t id, const MValue *args, size_t argc, MValue *out_result){
    (void)user;
    *out_result=mval_none();
    switch(id){
    /* 1 — print(args...) */
    case 1:{
        size_t i; for(i=0;i<argc;++i){if(i)fputc(' ',stdout);print_value(stdout,&args[i]);}
        fputc('\n',stdout); return 1;
    }
    /* 2 — len(container) -> i64 */
    case 2:
        if(argc!=1)return 0;
        if(args[0].tag==MVAL_STR)  {*out_result=mval_i64((int64_t)args[0].as.str.len);  return 1;}
        if(args[0].tag==MVAL_LIST) {*out_result=mval_i64((int64_t)args[0].as.list.len); return 1;}
        if(args[0].tag==MVAL_MAP)  {*out_result=mval_i64((int64_t)args[0].as.map.len);  return 1;}
        return 0;
    /* 3 — clock_ms() -> i64 */
    case 3:{
        long long ms=(long long)((double)clock()*1000.0/(double)CLOCKS_PER_SEC);
        *out_result=mval_i64((int64_t)ms); return 1;
    }
    /* 4 — getenv(name) -> str | none */
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
    /* 5 — str(val) -> str */
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
    /* 6 — type(val) -> str */
    case 6:
        if(argc!=1)return 0;
        {const char *tn=mvalue_tag_name(args[0].tag); *out_result=mval_owned_copy(tn,strlen(tn)); return 1;}

    /* 7 — abs(n) -> number */
    case 7:
        if(argc!=1)return 0;
        if(args[0].tag==MVAL_I64){if(args[0].as.i64==INT64_MIN)return 0;*out_result=mval_i64(args[0].as.i64<0?-args[0].as.i64:args[0].as.i64);return 1;}
        if(args[0].tag==MVAL_F64){*out_result=mval_f64(fabs(args[0].as.f64));return 1;}
        return 0;

    /* 8 — floor(n) -> i64 */
    case 8:
        if(argc!=1)return 0;
        if(args[0].tag==MVAL_I64){*out_result=args[0];return 1;}
        if(args[0].tag==MVAL_F64&&isfinite(args[0].as.f64)&&args[0].as.f64>=(double)INT64_MIN&&args[0].as.f64<(double)INT64_MAX){*out_result=mval_i64((int64_t)floor(args[0].as.f64));return 1;}
        return 0;

    /* 9 — ceil(n) -> i64 */
    case 9:
        if(argc!=1)return 0;
        if(args[0].tag==MVAL_I64){*out_result=args[0];return 1;}
        if(args[0].tag==MVAL_F64&&isfinite(args[0].as.f64)&&args[0].as.f64>=(double)INT64_MIN&&args[0].as.f64<(double)INT64_MAX){*out_result=mval_i64((int64_t)ceil(args[0].as.f64));return 1;}
        return 0;

    /* 10 — sqrt(n) -> f64 */
    case 10:
        if(argc!=1)return 0;
        {double v;if(!numeric_value(&args[0],&v)||v<0.0)return 0;
         *out_result=mval_f64(sqrt(v));return 1;}

    /* 11 — min(a,b) */
    case 11:
        if(argc!=2)return 0;
        {double a,b;if(!numeric_value(&args[0],&a)||!numeric_value(&args[1],&b))return 0;
         if(args[0].tag==MVAL_I64&&args[1].tag==MVAL_I64)
             *out_result=mval_i64(args[0].as.i64<args[1].as.i64?args[0].as.i64:args[1].as.i64);
         else *out_result=mval_f64(a<b?a:b);
         return 1;}

    /* 12 — max(a,b) */
    case 12:
        if(argc!=2)return 0;
        {double a,b;if(!numeric_value(&args[0],&a)||!numeric_value(&args[1],&b))return 0;
         if(args[0].tag==MVAL_I64&&args[1].tag==MVAL_I64)
             *out_result=mval_i64(args[0].as.i64>args[1].as.i64?args[0].as.i64:args[1].as.i64);
         else *out_result=mval_f64(a>b?a:b);
         return 1;}

    /* 13 — print_n(n_args, v0, v1, ...) — PRINTN syscall (argc == actual values) */
    case 13:{
        size_t i; for(i=0;i<argc;++i){if(i)fputc(' ',stdout);print_value(stdout,&args[i]);}
        fputc('\n',stdout); return 1;
    }

    /* 20 — range(start, stop) -> list of i64 */
    case 20: {
        uint64_t count;
        if (argc != 2) return 0;
        if ((args[0].tag != MVAL_I64 && args[0].tag != MVAL_F64) ||
            (args[1].tag != MVAL_I64 && args[1].tag != MVAL_F64)) return 0;
        if ((args[0].tag == MVAL_F64 && (!isfinite(args[0].as.f64) || args[0].as.f64 < (double)INT64_MIN || args[0].as.f64 >= (double)INT64_MAX)) ||
            (args[1].tag == MVAL_F64 && (!isfinite(args[1].as.f64) || args[1].as.f64 < (double)INT64_MIN || args[1].as.f64 >= (double)INT64_MAX))) return 0;
        int64_t start = (args[0].tag == MVAL_I64) ? args[0].as.i64 : (int64_t)args[0].as.f64;
        int64_t stop  = (args[1].tag == MVAL_I64) ? args[1].as.i64 : (int64_t)args[1].as.f64;
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

    default: return 0;
    }
}

static const char *friendly_runtime_error(const char *code)
{
    if(!code) return "unknown runtime error";
    if(!strcmp(code,"division_by_zero")) return "division by zero";
    if(!strcmp(code,"modulo_by_zero")) return "modulo by zero";
    if(!strcmp(code,"getitem_index_out_of_range")) return "index out of range";
    if(!strcmp(code,"getitem_key_not_found")) return "missing map key";
    if(!strcmp(code,"getitem_unsupported_type")) return "value is not indexable";
    if(!strcmp(code,"numeric_op_requires_numbers")) return "arithmetic requires numbers";
    if(!strcmp(code,"len_unsupported_type")) return "len() requires a string, list, or map";
    if(!strcmp(code,"call_non_function")||!strcmp(code,"call_val_non_function")) return "value is not callable";
    if(!strcmp(code,"syscall_failed")) return "built-in call failed (check argument count and types)";
    if(!strcmp(code,"unsupported_opcode")) return "unsupported native opcode";
    return code;
}

static void print_runtime_error(const char *source_name, const MRunResult *result)
{
    const char *name=source_name&&*source_name?source_name:"<memory>";
    const char *message=friendly_runtime_error(result->error_message);
    if(result->has_error_span){
        fprintf(stderr,"%s:%u:%u: runtime error: %s\n",
                name,result->error_span.start_line,result->error_span.start_col,message);
    } else {
        fprintf(stderr,"%s: runtime error at instruction %u: %s\n",
                name,result->error_pc,message);
    }
}

/* ── entry point ─────────────────────────────────────────────────────────── */
static void usage(const char *argv0){
    fprintf(stderr,
        "Mellow Programming Language 2.9.4 (Full Native C)\n"
        "Usage: %s <program.mellow|program.mvi>\n"
        "       %s check <program.mellow>\n"
        "       %s --runtime-info\n"
        "       %s --version\n",argv0,argv0,argv0,argv0);
}

int main(int argc, char **argv){
    int check_only=0;
    if(argc<2){usage(argv[0]);return 1;}
    if(!strcmp(argv[1],"--version")||!strcmp(argv[1],"-V")){
        puts("Mellow Programming Language 2.9.4 (Full Native C)");
        return 0;
    }
    if(!strcmp(argv[1],"--runtime-info")){
        MRuntimePlatform platform=mellow_runtime_platform();
        printf("{\"runtime\":\"mellow-c\",\"architecture\":\"%s\","
               "\"backend\":\"%s\",\"pointer_bits\":%u,"
               "\"little_endian\":%s,\"arm_neon_available\":%s,"
               "\"optimized_kernels\":%s}\n",
               platform.architecture,platform.backend,platform.pointer_bits,
               platform.little_endian?"true":"false",
               platform.arm_neon_available?"true":"false",
               platform.optimized_kernels?"true":"false");
        return 0;
    }
    if(!strcmp(argv[1],"check")){
        if(argc<3){usage(argv[0]);return 1;}
        check_only=1;
    }
    {
        const char *path=argv[check_only?2:1];
        size_t path_len=strlen(path);
        int is_image=path_len>=4&&!strcmp(path+path_len-4,".mvi");
        if(!is_image){
            MNativeProgram native;
            MProgram prog;
            MVM vm;
            MRunResult rr;
            char error[512]={0};
            if(!mellow_compile_file(path,&native,error,sizeof(error))){
                fprintf(stderr,"%s\n",error[0]?error:"<unknown>:1:1: compile error");
                return 1;
            }
            if(check_only){
                printf("OK %s (native-c, %lu instructions)\n",path,(unsigned long)native.code_len);
                mellow_native_program_free(&native);
                return 0;
            }
            prog=(MProgram){native.code,native.code_len,native.consts,native.const_len,native.spans,native.span_len,native.source_name};
            mvm_init(&vm);vm.syscall.fn=runtime_syscall;vm.syscall.user=NULL;memset(&rr,0,sizeof(rr));
            if(!mvm_run(&vm,&prog,&rr)||rr.failed){
                print_runtime_error(prog.source_name,&rr);
                mvm_free(&vm);mellow_native_program_free(&native);return 1;
            }
            mvm_free(&vm);mellow_native_program_free(&native);return 0;
        }
    }
    MLoadedProgram lp;
    if(!parse_loaded_program(argv[1],&lp)){
        fprintf(stderr,"failed to load standalone image: %s\n",argv[1]);
        return 1;
    }
    MProgram prog={lp.code,lp.code_len,lp.consts,lp.const_len,lp.spans,lp.span_len,lp.source_name};
    MVM vm; mvm_init(&vm);
    vm.syscall.fn=runtime_syscall; vm.syscall.user=NULL;
    MRunResult rr; memset(&rr,0,sizeof(rr));
    int ok=mvm_run(&vm,&prog,&rr);
    if(!ok||rr.failed){
        print_runtime_error(prog.source_name,&rr);
        mvm_free(&vm); free_loaded_program(&lp); return 1;
    }
    mvm_free(&vm); free_loaded_program(&lp);
    return 0;
}
