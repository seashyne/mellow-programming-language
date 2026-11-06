static int parse_color(const MValue *value, unsigned char rgb[3]){
    const char *s;
    size_t n;
    int r1,r2,g1,g2,b1,b2;
    if(!value||value->tag!=MVAL_STR||!value->as.str.ptr)return 0;
    s=value->as.str.ptr;
    n=value->as.str.len;
    if(n==7&&s[0]=='#'){
        r1=hex_digit(s[1]);r2=hex_digit(s[2]);
        g1=hex_digit(s[3]);g2=hex_digit(s[4]);
        b1=hex_digit(s[5]);b2=hex_digit(s[6]);
        if(r1<0||r2<0||g1<0||g2<0||b1<0||b2<0)return 0;
        rgb[0]=(unsigned char)((r1<<4)|r2);
        rgb[1]=(unsigned char)((g1<<4)|g2);
        rgb[2]=(unsigned char)((b1<<4)|b2);
        return 1;
    }
    if(n==5&&memcmp(s,"white",5)==0){rgb[0]=255;rgb[1]=255;rgb[2]=255;return 1;}
    if(n==5&&memcmp(s,"black",5)==0){rgb[0]=0;rgb[1]=0;rgb[2]=0;return 1;}
    if(n==3&&memcmp(s,"red",3)==0){rgb[0]=255;rgb[1]=0;rgb[2]=0;return 1;}
    if(n==5&&memcmp(s,"green",5)==0){rgb[0]=0;rgb[1]=180;rgb[2]=0;return 1;}
    if(n==4&&memcmp(s,"blue",4)==0){rgb[0]=0;rgb[1]=96;rgb[2]=255;return 1;}
    if(n==6&&memcmp(s,"yellow",6)==0){rgb[0]=255;rgb[1]=220;rgb[2]=0;return 1;}
    if(n==4&&memcmp(s,"cyan",4)==0){rgb[0]=0;rgb[1]=220;rgb[2]=255;return 1;}
    if(n==7&&memcmp(s,"magenta",7)==0){rgb[0]=255;rgb[1]=0;rgb[2]=220;return 1;}
    return 0;
}

static void canvas_pixel_raw(MellowCanvas *canvas,int x,int y,const unsigned char rgb[3]){
    size_t off;
    if(!canvas||!canvas->pixels)return;
    if(x<0||y<0||x>=canvas->width||y>=canvas->height)return;
    off=((size_t)y*(size_t)canvas->width+(size_t)x)*3u;
    canvas->pixels[off]=rgb[0];
    canvas->pixels[off+1]=rgb[1];
    canvas->pixels[off+2]=rgb[2];
}

static void canvas_clear_raw(MellowCanvas *canvas,const unsigned char rgb[3]){
    int x,y;
    if(!canvas||!canvas->pixels)return;
    for(y=0;y<canvas->height;++y)
        for(x=0;x<canvas->width;++x)
            canvas_pixel_raw(canvas,x,y,rgb);
}

static void canvas_line_raw(MellowCanvas *canvas,int x0,int y0,int x1,int y1,const unsigned char rgb[3]){
    int dx=abs(x1-x0), sx=x0<x1?1:-1;
    int dy=-abs(y1-y0), sy=y0<y1?1:-1;
    int err=dx+dy;
    while(1){
        int e2;
        canvas_pixel_raw(canvas,x0,y0,rgb);
        if(x0==x1&&y0==y1)break;
        e2=2*err;
        if(e2>=dy){err+=dy;x0+=sx;}
        if(e2<=dx){err+=dx;y0+=sy;}
    }
}

static void canvas_rect_raw(MellowCanvas *canvas,int x,int y,int w,int h,const unsigned char rgb[3]){
    int px,py;
    if(w<0){x+=w;w=-w;}
    if(h<0){y+=h;h=-h;}
    for(py=y;py<y+h;++py)
        for(px=x;px<x+w;++px)
            canvas_pixel_raw(canvas,px,py,rgb);
}

static void canvas_circle_raw(MellowCanvas *canvas,int cx,int cy,int radius,const unsigned char rgb[3]){
    int x,y,r2;
    if(radius<0)return;
    r2=radius*radius;
    for(y=-radius;y<=radius;++y)
        for(x=-radius;x<=radius;++x)
            if(x*x+y*y<=r2)canvas_pixel_raw(canvas,cx+x,cy+y,rgb);
}

static int canvas_save_ppm(MellowCanvas *canvas,const MValue *path_value){
    char *path;
    FILE *fp;
    size_t bytes;
    if(!canvas||!canvas->pixels||!path_value||path_value->tag!=MVAL_STR||!path_value->as.str.ptr)return 0;
    path=(char*)calloc(path_value->as.str.len+1,1);
    if(!path)return 0;
    memcpy(path,path_value->as.str.ptr,path_value->as.str.len);
    fp=fopen(path,"wb");
    free(path);
    if(!fp)return 0;
    if(fprintf(fp,"P6\n%d %d\n255\n",canvas->width,canvas->height)<0){fclose(fp);return 0;}
    bytes=(size_t)canvas->width*(size_t)canvas->height*3u;
    if(fwrite(canvas->pixels,1,bytes,fp)!=bytes){fclose(fp);return 0;}
    return fclose(fp)==0;
}

static MValue stats_map(const MellowRuntimeContext *ctx){
    MValue v=mval_none();
    v.tag=MVAL_MAP;
    v.as.map.len=v.as.map.cap=25;
    v.as.map.keys=(MValue*)calloc(25,sizeof(MValue));
    v.as.map.values=(MValue*)calloc(25,sizeof(MValue));
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
    v.as.map.keys[13]=mval_owned_copy("heap_bytes",10);
    v.as.map.values[13]=mval_i64((ctx&&ctx->vm)?(int64_t)ctx->vm->heap_bytes:0);
    v.as.map.keys[14]=mval_owned_copy("heap_blocks",11);
    v.as.map.values[14]=mval_i64((ctx&&ctx->vm)?(int64_t)ctx->vm->heap_blocks:0);
    v.as.map.keys[15]=mval_owned_copy("last_freed_blocks",17);
    v.as.map.values[15]=mval_i64((ctx&&ctx->vm)?(int64_t)ctx->vm->heap_last_gc_freed:0);
    v.as.map.keys[16]=mval_owned_copy("last_freed_bytes",16);
    v.as.map.values[16]=mval_i64((ctx&&ctx->vm)?(int64_t)ctx->vm->heap_last_gc_freed_bytes:0);
    v.as.map.keys[17]=mval_owned_copy("canvases",8);
    v.as.map.values[17]=mval_i64(ctx?(int64_t)ctx->canvas_count:0);
    v.as.map.keys[18]=mval_owned_copy("scheduler_mode",14);
    v.as.map.values[18]=mval_owned_copy(
        (ctx&&ctx->vm)?mellowrt_scheduler_mode(ctx->vm):"m:n-cooperative",
        strlen((ctx&&ctx->vm)?mellowrt_scheduler_mode(ctx->vm):"m:n-cooperative"));
    v.as.map.keys[19]=mval_owned_copy("workers",7);
    v.as.map.values[19]=mval_i64((ctx&&ctx->vm)?(int64_t)mellowrt_scheduler_worker_count(ctx->vm):1);
    v.as.map.keys[20]=mval_owned_copy("tasks",5);
    v.as.map.values[20]=mval_i64((ctx&&ctx->vm)?(int64_t)ctx->vm->task_len:0);
    v.as.map.keys[21]=mval_owned_copy("runnable",8);
    v.as.map.values[21]=mval_i64((ctx&&ctx->vm)?(int64_t)mellowrt_scheduler_runnable_count(ctx->vm):0);
    v.as.map.keys[22]=mval_owned_copy("switches",8);
    v.as.map.values[22]=mval_i64((ctx&&ctx->vm)?(int64_t)ctx->vm->scheduler_switches:0);
    v.as.map.keys[23]=mval_owned_copy("blocked",7);
    v.as.map.values[23]=mval_i64((ctx&&ctx->vm)?(int64_t)ctx->vm->scheduler_blocks:0);
    v.as.map.keys[24]=mval_owned_copy("worker_changes",14);
    v.as.map.values[24]=mval_i64(ctx?(int64_t)ctx->scheduler_worker_changes:0);
    return v;
}

int mellowrt_default_syscall(void *user, int32_t id, const MValue *args, size_t argc, MValue *out_result){
    MellowRuntimeContext *ctx=(MellowRuntimeContext*)user;
    *out_result=mval_none();
    if (ctx) ctx->syscall_error[0]='\0';
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
