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
        mellowrt_collect_garbage(ctx);
        collect_value_heap(ctx);
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
        if(!channel_push(ctx,ch,&args[1]))return 0;
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
            if(ctx)ctx->recv_would_block=1;
            *out_result=mval_none();
        }
        return 1;
    }
    case 28:{
        MellowCanvas *canvas;
        int width,height;
        size_t bytes;
        if(argc!=2)return 0;
        if(!integer_arg(&args[0],&width)||!integer_arg(&args[1],&height))return 0;
        if(width<=0||height<=0||width>8192||height>8192)return 0;
        if((size_t)width>(SIZE_MAX/3u)/(size_t)height)return 0;
        canvas=(MellowCanvas*)calloc(1,sizeof(MellowCanvas));
        if(!canvas)return 0;
        bytes=(size_t)width*(size_t)height*3u;
        canvas->pixels=(unsigned char*)calloc(bytes,1);
        if(!canvas->pixels){free(canvas);return 0;}
        canvas->magic=MELLOW_NATIVE_CANVAS_MAGIC;
        canvas->width=width;
        canvas->height=height;
        if(ctx)ctx->canvas_count++;
        register_native(ctx,(MellowNativeHeader*)canvas);
        *out_result=native_ptr(canvas);
        return 1;
    }
    case 29:{
        MellowCanvas *canvas;
        unsigned char rgb[3];
        if(argc!=2)return 0;
        canvas=as_canvas(&args[0]);
        if(!canvas||!parse_color(&args[1],rgb))return 0;
        canvas_clear_raw(canvas,rgb);
        *out_result=mval_bool(1);
        return 1;
    }
    case 30:{
        MellowCanvas *canvas;
        unsigned char rgb[3];
        int x,y;
        if(argc!=4)return 0;
        canvas=as_canvas(&args[0]);
        if(!canvas||!integer_arg(&args[1],&x)||!integer_arg(&args[2],&y)||!parse_color(&args[3],rgb))return 0;
        canvas_pixel_raw(canvas,x,y,rgb);
        *out_result=mval_bool(1);
        return 1;
    }
    case 31:{
        MellowCanvas *canvas;
        unsigned char rgb[3];
        int x0,y0,x1,y1;
        if(argc!=6)return 0;
        canvas=as_canvas(&args[0]);
        if(!canvas||!integer_arg(&args[1],&x0)||!integer_arg(&args[2],&y0)||
           !integer_arg(&args[3],&x1)||!integer_arg(&args[4],&y1)||!parse_color(&args[5],rgb))return 0;
        canvas_line_raw(canvas,x0,y0,x1,y1,rgb);
        *out_result=mval_bool(1);
        return 1;
    }
    case 32:{
        MellowCanvas *canvas;
        unsigned char rgb[3];
        int x,y,w,h;
        if(argc!=6)return 0;
        canvas=as_canvas(&args[0]);
        if(!canvas||!integer_arg(&args[1],&x)||!integer_arg(&args[2],&y)||
           !integer_arg(&args[3],&w)||!integer_arg(&args[4],&h)||!parse_color(&args[5],rgb))return 0;
        canvas_rect_raw(canvas,x,y,w,h,rgb);
        *out_result=mval_bool(1);
        return 1;
    }
    case 33:{
        MellowCanvas *canvas;
        unsigned char rgb[3];
        int cx,cy,radius;
        if(argc!=5)return 0;
        canvas=as_canvas(&args[0]);
        if(!canvas||!integer_arg(&args[1],&cx)||!integer_arg(&args[2],&cy)||
           !integer_arg(&args[3],&radius)||!parse_color(&args[4],rgb))return 0;
        canvas_circle_raw(canvas,cx,cy,radius,rgb);
        *out_result=mval_bool(1);
        return 1;
    }
    case 34:{
        MellowCanvas *canvas;
        if(argc!=2)return 0;
        canvas=as_canvas(&args[0]);
        if(!canvas)return 0;
        *out_result=mval_bool(canvas_save_ppm(canvas,&args[1]));
        return 1;
    }
    case 35:{
        int workers;
        if(argc!=1||!ctx||!ctx->vm)return 0;
        if(!integer_arg(&args[0],&workers)||workers<=0)return 0;
        if(!mellowrt_scheduler_set_workers(ctx->vm,(size_t)workers))return 0;
        ctx->scheduler_worker_changes++;
        *out_result=mval_i64((int64_t)mellowrt_scheduler_worker_count(ctx->vm));
        return 1;
    }
    case 36:
        if(argc!=0)return 0;
        *out_result=mval_i64((ctx&&ctx->vm)?(int64_t)mellowrt_scheduler_worker_count(ctx->vm):1);
        return 1;
    case 37:{
        const char *mode=(ctx&&ctx->vm)?mellowrt_scheduler_mode(ctx->vm):"m:n-cooperative";
        if(argc!=0)return 0;
        *out_result=mval_owned_copy(mode,strlen(mode));
        return 1;
    }
    case 38:
    case 39:
    case 40:
    case 41:
    case 42:
    case 43:
    case 44:
    case 45:
    case 46:
    case 47:
    case 48:
    case 49:
        return mellowrt_money_syscall(id,args,argc,out_result);
    case 56:
    case 57:
    case 58:
    case 59:
    case 60:
        return mellowrt_ledger_syscall(id,args,argc,out_result,
                                       ctx?ctx->syscall_error:NULL,
                                       ctx?sizeof(ctx->syscall_error):0);
    case 52:
        if(argc!=0)return 0;
        if(ctx&&ctx->server_request.tag!=MVAL_NONE) *out_result=clone_value(ctx,&ctx->server_request);
        else {
            MValue req=mval_none();
            req.tag=MVAL_MAP;
            req.as.map.len=req.as.map.cap=4;
            req.as.map.keys=(MValue*)calloc(4,sizeof(MValue));
            req.as.map.values=(MValue*)calloc(4,sizeof(MValue));
            if(!req.as.map.keys||!req.as.map.values){free(req.as.map.keys);free(req.as.map.values);return 0;}
            req.as.map.keys[0]=mval_owned_copy("method",6); req.as.map.values[0]=mval_owned_copy("GET",3);
            req.as.map.keys[1]=mval_owned_copy("path",4); req.as.map.values[1]=mval_owned_copy("/",1);
            req.as.map.keys[2]=mval_owned_copy("query",5); req.as.map.values[2]=mval_owned_copy("",0);
            req.as.map.keys[3]=mval_owned_copy("body",4); req.as.map.values[3]=mval_owned_copy("",0);
            *out_result=req;
        }
        return 1;
    case 53:
    case 54:{
        const char *ct=(id==53)?"application/json":"text/plain; charset=utf-8";
        if(argc!=1||!ctx)return 0;
        mvalue_free(&ctx->server_response_body);
        ctx->server_response_body=clone_value(ctx,&args[0]);
        ctx->server_response_set=1;
        ctx->server_response_status=200;
        snprintf(ctx->server_response_content_type,sizeof(ctx->server_response_content_type),"%s",ct);
        return 1;
    }
    case 55:{
        const char *ct;
        if(argc!=2||!ctx||args[0].tag!=MVAL_I64)return 0;
        ct=(args[1].tag==MVAL_MAP||args[1].tag==MVAL_LIST)?"application/json":"text/plain; charset=utf-8";
        mvalue_free(&ctx->server_response_body);
        ctx->server_response_body=clone_value(ctx,&args[1]);
        ctx->server_response_set=1;
        ctx->server_response_status=(int)args[0].as.i64;
        snprintf(ctx->server_response_content_type,sizeof(ctx->server_response_content_type),"%s",ct);
        return 1;
    }
    case 50:{
        double value, low, high, out;
        if(argc!=3)return 0;
        if(!numeric_value(&args[0],&value)||!numeric_value(&args[1],&low)||!numeric_value(&args[2],&high))return 0;
        out=value<low?low:(value>high?high:value);
        if(args[0].tag==MVAL_I64&&args[1].tag==MVAL_I64&&args[2].tag==MVAL_I64)*out_result=mval_i64((int64_t)out);
        else *out_result=mval_f64(out);
        return 1;
    }
    case 51:{
        double a,b,t,out;
        if(argc!=3)return 0;
        if(!numeric_value(&args[0],&a)||!numeric_value(&args[1],&b)||!numeric_value(&args[2],&t))return 0;
        out=a+(b-a)*t;
        if(args[0].tag==MVAL_I64&&args[1].tag==MVAL_I64&&args[2].tag==MVAL_I64)*out_result=mval_i64((int64_t)out);
        else *out_result=mval_f64(out);
        return 1;
    }
    case 61:
    case 62:
