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

static void free_run_result(MRunResult *result)
{
    if(!result)return;
    mvalue_free(&result->result);
}

/* ── entry point ─────────────────────────────────────────────────────────── */
static void usage(const char *argv0){
    printf(
        "Mellow Programming Language 2.9.10 (Full Native C)\n"
        "\n"
        "Common:\n"
        "  %s run <file>             Run a .mellow script\n"
        "  %s check <file>           Compile/syntax check a .mellow script\n"
        "  %s doctor                 Show native runtime status\n"
        "  %s status                 Show native runtime status\n"
        "  %s pkg <cmd>              Native package manager (init/publish/install/list/...)\n"
        "  %s install <name>         Install a package from the local registry\n"
        "  %s sm pack <in> -o <out>  Pack text-like assets into native SM3\n"
        "  %s server serve <file>    Run a native C HTTP server from Mellow source\n"
        "  %s sm inspect <file.sm>   Inspect a native SM3 file\n"
        "  %s sm unpack <in> -o <out> Unpack a native SM3 file\n"
        "  %s help                   Show this help\n"
        "\n"
        "Direct native forms:\n"
        "  %s <program.mellow|program.mvi>\n"
        "  %s --runtime-info\n"
        "  %s --version\n",
        argv0,argv0,argv0,argv0,argv0,argv0,argv0,argv0,argv0,argv0,argv0,argv0,
        argv0,argv0);
}

static void native_doctor(const char *argv0){
    MRuntimePlatform platform=mellow_runtime_platform();
    printf("MellowLang 2.9.10 (Full Native C)\n\n");
    printf("Environment\n");
    printf("  Executable    : %s\n",argv0);
    printf("  Runtime       : mellow-c standalone\n");
    printf("  Python        : not required\n");
    printf("  Architecture  : %s\n",platform.architecture);
    printf("  Backend       : %s\n",platform.backend);
    printf("  Pointer bits  : %u\n",platform.pointer_bits);
    printf("  Little endian : %s\n",platform.little_endian?"true":"false");
    printf("\nChecks\n");
    printf("  [OK] native_cli: standalone C launcher is running\n");
    printf("  [OK] native_compiler: .mellow source compiler is built in\n");
    printf("  [OK] native_runtime: bytecode VM and native built-ins are built in\n");
    printf("  [OK] python_free: this command did not require Python\n");
}

