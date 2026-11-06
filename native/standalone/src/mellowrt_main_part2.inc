int main(int argc, char **argv){
    int check_only=0;
    int path_index=1;
    MellowRuntimeContext ctx;
    memset(&ctx,0,sizeof(ctx));
    ctx.argc=argc;
    ctx.argv=argv;
    ctx.script_arg_start=2;
    /* --seed N / --seed=N and the data switches may appear anywhere; strip
     * them before command dispatch so script arguments never see the flags. */
    {
        int i, out=1;
        for(i=1;i<argc;++i){
            if(!strcmp(argv[i],"--seed")&&i+1<argc){
                ctx.rng_seed=(int64_t)strtoll(argv[++i],NULL,10);
                ctx.rng_seed_set=1;
                continue;
            }
            if(!strncmp(argv[i],"--seed=",7)){
                ctx.rng_seed=(int64_t)strtoll(argv[i]+7,NULL,10);
                ctx.rng_seed_set=1;
                continue;
            }
            if(!strcmp(argv[i],"--data-write")){
                ctx.allow_data_write=1;
                continue;
            }
            if(!strcmp(argv[i],"--data-max-rows")&&i+1<argc){
                ctx.data_max_query_rows=strtoll(argv[++i],NULL,10);
                continue;
            }
            if(!strncmp(argv[i],"--data-max-rows=",16)){
                ctx.data_max_query_rows=strtoll(argv[i]+16,NULL,10);
                continue;
            }
            argv[out++]=argv[i];
        }
        argc=out;
        ctx.argc=argc;
    }
    if(argc<2){usage(argv[0]);return 0;}
    if(!strcmp(argv[1],"--help")||!strcmp(argv[1],"-h")||!strcmp(argv[1],"help")){
        usage(argv[0]);
        return 0;
    }
    if(!strcmp(argv[1],"--version")||!strcmp(argv[1],"-V")||!strcmp(argv[1],"version")){
        puts("Mellow Programming Language 2.9.9 (Full Native C)");
        return 0;
    }
    if(!strcmp(argv[1],"doctor")||!strcmp(argv[1],"status")){
        native_doctor(argv[0]);
        return 0;
    }
    if(!strcmp(argv[1],"sm")){
        return mellowrt_sm_cli(argc,argv);
    }
    if(!strcmp(argv[1],"server")){
        return mellowrt_server_cli(argc,argv);
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
        path_index=2;
    } else if(!strcmp(argv[1],"run")||!strcmp(argv[1],"r")){
        if(argc<3){usage(argv[0]);return 1;}
        path_index=2;
    }
    {
        const char *path=argv[path_index];
        ctx.script_arg_start=path_index+1;
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
            mvm_init(&vm);ctx.vm=&vm;vm.syscall.fn=mellowrt_default_syscall;vm.syscall.user=&ctx;memset(&rr,0,sizeof(rr));
            if(!mvm_run(&vm,&prog,&rr)||rr.failed){
                print_runtime_error(prog.source_name,&rr);
                free_run_result(&rr);mellowrt_collect_garbage(&ctx);ctx.vm=NULL;mvm_free(&vm);mellowrt_collect_garbage(&ctx);mellow_native_program_free(&native);mellowrt_data_release(&ctx);return 1;
            }
            free_run_result(&rr);mellowrt_collect_garbage(&ctx);ctx.vm=NULL;mvm_free(&vm);mellowrt_collect_garbage(&ctx);mellow_native_program_free(&native);mellowrt_data_release(&ctx);return 0;
        }
    }
    MLoadedProgram lp;
    if(!parse_loaded_program(argv[path_index],&lp)){
        fprintf(stderr,"failed to load standalone image: %s\n",argv[path_index]);
        return 1;
    }
    MProgram prog={lp.code,lp.code_len,lp.consts,lp.const_len,lp.spans,lp.span_len,lp.source_name};
    MVM vm; mvm_init(&vm);
    ctx.vm=&vm;
    vm.syscall.fn=mellowrt_default_syscall; vm.syscall.user=&ctx;
    MRunResult rr; memset(&rr,0,sizeof(rr));
    int ok=mvm_run(&vm,&prog,&rr);
    if(!ok||rr.failed){
        print_runtime_error(prog.source_name,&rr);
        free_run_result(&rr);mellowrt_collect_garbage(&ctx);ctx.vm=NULL;mvm_free(&vm);mellowrt_collect_garbage(&ctx); free_loaded_program(&lp); mellowrt_data_release(&ctx); return 1;
    }
    free_run_result(&rr);mellowrt_collect_garbage(&ctx);ctx.vm=NULL;mvm_free(&vm);mellowrt_collect_garbage(&ctx); free_loaded_program(&lp); mellowrt_data_release(&ctx);
    return 0;
}
