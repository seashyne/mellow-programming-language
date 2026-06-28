#ifndef _WIN32
#define _POSIX_C_SOURCE 199309L
#endif

#include "mellowrt_syscalls.h"
#include "mellowrt_scheduler.h"

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
#define MELLOW_NATIVE_CANVAS_MAGIC 0x4d434156u

typedef struct MellowNativeHeader {
    uint32_t magic;
    int marked;
    struct MellowNativeHeader *next;
} MellowNativeHeader;

typedef struct MellowChannel {
    uint32_t magic;
    int marked;
    MellowNativeHeader *next;
    MValue *items;
    size_t len;
    size_t cap;
} MellowChannel;

typedef struct MellowCanvas {
    uint32_t magic;
    int marked;
    MellowNativeHeader *next;
    int width;
    int height;
    unsigned char *pixels;
} MellowCanvas;

static void mark_value(MellowRuntimeContext *ctx, const MValue *value);
static void mark_channel_queue_values(void *user, MVM *vm);

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
    default: return 0;
    }
}
