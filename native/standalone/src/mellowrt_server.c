#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
typedef SOCKET mellow_socket_t;
#define MELLOW_INVALID_SOCKET INVALID_SOCKET
#define mellow_close_socket closesocket
#else
#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>
typedef int mellow_socket_t;
#define MELLOW_INVALID_SOCKET (-1)
#define mellow_close_socket close
#endif

#include "mellowrt.h"
#include "mellowrt_server.h"
#include "mellowrt_syscalls.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    char *data;
    size_t len;
    size_t cap;
} SBuf;

static const char *arg_value(int argc, char **argv, const char *name)
{
    int i;
    for(i=0;i<argc-1;++i) if(!strcmp(argv[i],name)) return argv[i+1];
    return NULL;
}

static MValue owned_str(const char *src, size_t len)
{
    MValue v=mval_none();
    char *buf=(char*)calloc(len+1,1);
    if(!buf)return v;
    if(src&&len)memcpy(buf,src,len);
    buf[len]='\0';
    v.tag=MVAL_STR;
    v.flags=1u;
    v.as.str.ptr=buf;
    v.as.str.len=len;
    return v;
}

static int sbuf_add(SBuf *b, const char *s, size_t n)
{
    char *grown;
    size_t next;
    if(!b||!s)return 0;
    if(b->len+n+1>b->cap){
        next=b->cap?b->cap*2u:256u;
        while(b->len+n+1>next)next*=2u;
        grown=(char*)realloc(b->data,next);
        if(!grown)return 0;
        b->data=grown;b->cap=next;
    }
    memcpy(b->data+b->len,s,n);
    b->len+=n;
    b->data[b->len]='\0';
    return 1;
}

static int sbuf_puts(SBuf *b, const char *s){return sbuf_add(b,s,strlen(s));}

static int json_escape(SBuf *b, const char *s, size_t n)
{
    size_t i;
    if(!sbuf_puts(b,"\""))return 0;
    for(i=0;i<n;++i){
        unsigned char c=(unsigned char)s[i];
        char tmp[8];
        if(c=='"'||c=='\\'){tmp[0]='\\';tmp[1]=(char)c;if(!sbuf_add(b,tmp,2))return 0;}
        else if(c=='\n'){if(!sbuf_puts(b,"\\n"))return 0;}
        else if(c=='\r'){if(!sbuf_puts(b,"\\r"))return 0;}
        else if(c=='\t'){if(!sbuf_puts(b,"\\t"))return 0;}
        else if(c<32){snprintf(tmp,sizeof(tmp),"\\u%04x",(unsigned)c);if(!sbuf_puts(b,tmp))return 0;}
        else if(!sbuf_add(b,(const char*)&c,1))return 0;
    }
    return sbuf_puts(b,"\"");
}

static int value_json(SBuf *b, const MValue *v)
{
    char tmp[64];
    size_t i;
    if(!v)return sbuf_puts(b,"null");
    switch(v->tag){
    case MVAL_NONE: return sbuf_puts(b,"null");
    case MVAL_BOOL: return sbuf_puts(b,v->as.boolean?"true":"false");
    case MVAL_I64: snprintf(tmp,sizeof(tmp),"%lld",(long long)v->as.i64); return sbuf_puts(b,tmp);
    case MVAL_F64: snprintf(tmp,sizeof(tmp),"%g",v->as.f64); return sbuf_puts(b,tmp);
    case MVAL_STR: return json_escape(b,v->as.str.ptr?v->as.str.ptr:"",v->as.str.len);
    case MVAL_LIST:
        if(!sbuf_puts(b,"["))return 0;
        for(i=0;i<v->as.list.len;++i){if(i&&!sbuf_puts(b,","))return 0;if(!value_json(b,&v->as.list.items[i]))return 0;}
        return sbuf_puts(b,"]");
    case MVAL_MAP:
        if(!sbuf_puts(b,"{"))return 0;
        for(i=0;i<v->as.map.len;++i){
            if(i&&!sbuf_puts(b,","))return 0;
            if(v->as.map.keys[i].tag==MVAL_STR){
                if(!json_escape(b,v->as.map.keys[i].as.str.ptr?v->as.map.keys[i].as.str.ptr:"",v->as.map.keys[i].as.str.len))return 0;
            } else if(!json_escape(b,"key",3))return 0;
            if(!sbuf_puts(b,":"))return 0;
            if(!value_json(b,&v->as.map.values[i]))return 0;
        }
        return sbuf_puts(b,"}");
    default:
        return json_escape(b,mvalue_tag_name(v->tag),strlen(mvalue_tag_name(v->tag)));
    }
}

static int value_text(SBuf *b, const MValue *v)
{
    char tmp[64];
    if(!v||v->tag==MVAL_NONE)return 1;
    if(v->tag==MVAL_STR)return sbuf_add(b,v->as.str.ptr?v->as.str.ptr:"",v->as.str.len);
    if(v->tag==MVAL_BOOL)return sbuf_puts(b,v->as.boolean?"true":"false");
    if(v->tag==MVAL_I64){snprintf(tmp,sizeof(tmp),"%lld",(long long)v->as.i64);return sbuf_puts(b,tmp);}
    if(v->tag==MVAL_F64){snprintf(tmp,sizeof(tmp),"%g",v->as.f64);return sbuf_puts(b,tmp);}
    return value_json(b,v);
}

static MValue make_request(const char *method, const char *path, const char *query, const char *body)
{
    MValue req=mval_none();
    req.tag=MVAL_MAP;
    req.as.map.len=req.as.map.cap=4;
    req.as.map.keys=(MValue*)calloc(4,sizeof(MValue));
    req.as.map.values=(MValue*)calloc(4,sizeof(MValue));
    if(!req.as.map.keys||!req.as.map.values){free(req.as.map.keys);free(req.as.map.values);return mval_none();}
    req.as.map.keys[0]=owned_str("method",6); req.as.map.values[0]=owned_str(method,strlen(method));
    req.as.map.keys[1]=owned_str("path",4); req.as.map.values[1]=owned_str(path,strlen(path));
    req.as.map.keys[2]=owned_str("query",5); req.as.map.values[2]=owned_str(query,strlen(query));
    req.as.map.keys[3]=owned_str("body",4); req.as.map.values[3]=owned_str(body,strlen(body));
    return req;
}

static int run_app(const MNativeProgram *native, const MValue *req, SBuf *body, int *status, const char **content_type)
{
    MProgram prog;
    MVM vm;
    MRunResult rr;
    MellowRuntimeContext ctx;
    int ok;
    memset(&ctx,0,sizeof(ctx));
    ctx.server_request=*req;
    ctx.server_response_body=mval_none();
    ctx.server_response_status=204;
    snprintf(ctx.server_response_content_type,sizeof(ctx.server_response_content_type),"%s","text/plain; charset=utf-8");
    prog=(MProgram){native->code,native->code_len,native->consts,native->const_len,native->spans,native->span_len,native->source_name};
    mvm_init(&vm);
    ctx.vm=&vm;
    vm.syscall.fn=mellowrt_default_syscall;
    vm.syscall.user=&ctx;
    memset(&rr,0,sizeof(rr));
    ok=mvm_run(&vm,&prog,&rr);
    if(!ok||rr.failed){
        *status=500;
        *content_type="text/plain; charset=utf-8";
        sbuf_puts(body,rr.error_message?rr.error_message:"runtime error");
    } else if(ctx.server_response_set) {
        *status=ctx.server_response_status;
        *content_type=ctx.server_response_content_type;
        if(strstr(ctx.server_response_content_type,"json")) value_json(body,&ctx.server_response_body);
        else value_text(body,&ctx.server_response_body);
    } else {
        *status=204;
        *content_type="text/plain; charset=utf-8";
    }
    mvalue_free(&ctx.server_response_body);
    mvalue_free(&rr.result);
    ctx.vm=NULL;
    mvm_free(&vm);
    return 1;
}

static void send_response(mellow_socket_t client, int status, const char *content_type, const char *body, size_t body_len)
{
    char head[512];
    int n=snprintf(head,sizeof(head),
        "HTTP/1.1 %d %s\r\nContent-Type: %s\r\nContent-Length: %lu\r\nConnection: close\r\n\r\n",
        status,(status>=200&&status<300)?"OK":(status==404?"Not Found":"Error"),
        content_type,(unsigned long)body_len);
    send(client,head,n,0);
    if(body_len)send(client,body,(int)body_len,0);
}

static void handle_client(mellow_socket_t client, const MNativeProgram *native)
{
    char buf[65536];
    int got=(int)recv(client,buf,sizeof(buf)-1,0);
    char method[16]="GET", target[1024]="/", path[1024]="/", query[1024]="";
    char *sp1,*sp2,*q,*body_start;
    MValue req;
    SBuf out={0};
    int status=500;
    const char *content_type="text/plain; charset=utf-8";
    if(got<=0){mellow_close_socket(client);return;}
    buf[got]='\0';
    sp1=strchr(buf,' ');
    if(sp1){
        size_t n=(size_t)(sp1-buf); if(n>=sizeof(method))n=sizeof(method)-1; memcpy(method,buf,n); method[n]='\0';
        sp2=strchr(sp1+1,' ');
        if(sp2){n=(size_t)(sp2-(sp1+1)); if(n>=sizeof(target))n=sizeof(target)-1; memcpy(target,sp1+1,n); target[n]='\0';}
    }
    snprintf(path,sizeof(path),"%s",target);
    q=strchr(path,'?');
    if(q){*q='\0';snprintf(query,sizeof(query),"%s",q+1);}
    body_start=strstr(buf,"\r\n\r\n");
    req=make_request(method,path,query,body_start?body_start+4:"");
    run_app(native,&req,&out,&status,&content_type);
    send_response(client,status,content_type,out.data?out.data:"",out.len);
    free(out.data);
    mvalue_free(&req);
    mellow_close_socket(client);
}

int mellowrt_server_cli(int argc, char **argv)
{
    const char *cmd=argc>=3?argv[2]:NULL;
    const char *file=argc>=4?argv[3]:NULL;
    const char *host=arg_value(argc,argv,"--host");
    const char *port_s=arg_value(argc,argv,"--port");
    int port=port_s?atoi(port_s):8787;
    MNativeProgram native;
    char error[512]={0};
    mellow_socket_t server_fd;
    struct sockaddr_in addr;
#ifdef _WIN32
    WSADATA wsa;
    if(WSAStartup(MAKEWORD(2,2),&wsa)!=0){fprintf(stderr,"server: WSAStartup failed\n");return 1;}
#endif
    if(!cmd||strcmp(cmd,"serve")||!file){fprintf(stderr,"usage: %s server serve <file.mellow> [--host 127.0.0.1] [--port 8787]\n",argv[0]);return 2;}
    if(!host)host="127.0.0.1";
    if(!mellow_compile_file(file,&native,error,sizeof(error))){
        fprintf(stderr,"%s\n",error[0]?error:"server: compile failed");
        return 1;
    }
    server_fd=socket(AF_INET,SOCK_STREAM,0);
    if(server_fd==MELLOW_INVALID_SOCKET){fprintf(stderr,"server: socket failed\n");mellow_native_program_free(&native);return 1;}
    memset(&addr,0,sizeof(addr));
    addr.sin_family=AF_INET;
    addr.sin_port=htons((unsigned short)port);
    addr.sin_addr.s_addr=inet_addr(host);
    if(bind(server_fd,(struct sockaddr*)&addr,sizeof(addr))<0){fprintf(stderr,"server: bind failed\n");mellow_close_socket(server_fd);mellow_native_program_free(&native);return 1;}
    if(listen(server_fd,16)<0){fprintf(stderr,"server: listen failed\n");mellow_close_socket(server_fd);mellow_native_program_free(&native);return 1;}
    printf("Mellow native server running: http://%s:%d\n",host,port);
    fflush(stdout);
    while(1){
        mellow_socket_t client=accept(server_fd,NULL,NULL);
        if(client==MELLOW_INVALID_SOCKET)break;
        handle_client(client,&native);
    }
    mellow_close_socket(server_fd);
    mellow_native_program_free(&native);
#ifdef _WIN32
    WSACleanup();
#endif
    return 0;
}
