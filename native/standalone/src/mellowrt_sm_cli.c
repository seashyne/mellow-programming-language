#include "mellowrt_sm_cli.h"
#include "sm_native.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned char *read_binary_file(const char *path, size_t *out_size)
{
    FILE *f;
    long size;
    unsigned char *data;
    if(!path||!out_size)return NULL;
    f=fopen(path,"rb");
    if(!f)return NULL;
    if(fseek(f,0,SEEK_END)!=0){fclose(f);return NULL;}
    size=ftell(f);
    if(size<0){fclose(f);return NULL;}
    if(fseek(f,0,SEEK_SET)!=0){fclose(f);return NULL;}
    data=(unsigned char*)malloc((size_t)size?((size_t)size):1u);
    if(!data){fclose(f);return NULL;}
    if(size&&fread(data,1,(size_t)size,f)!=(size_t)size){free(data);fclose(f);return NULL;}
    fclose(f);
    *out_size=(size_t)size;
    return data;
}

static int write_binary_file(const char *path, const unsigned char *data, size_t size)
{
    FILE *f;
    if(!path||!data)return 0;
    f=fopen(path,"wb");
    if(!f)return 0;
    if(size&&fwrite(data,1,size,f)!=size){fclose(f);return 0;}
    fclose(f);
    return 1;
}

static const char *arg_value(int argc, char **argv, const char *name)
{
    int i;
    for(i=0;i<argc-1;++i)if(!strcmp(argv[i],name))return argv[i+1];
    return NULL;
}

static int has_arg(int argc, char **argv, const char *name)
{
    int i;
    for(i=0;i<argc;++i)if(!strcmp(argv[i],name))return 1;
    return 0;
}

static char *default_sm_pack_output(const char *input)
{
    size_t n=strlen(input);
    char *out=(char*)calloc(n+4,1);
    if(!out)return NULL;
    snprintf(out,n+4,"%s.sm",input);
    return out;
}

static char *default_sm_unpack_output(const char *input)
{
    size_t n=strlen(input);
    char *out;
    if(n>3&&!strcmp(input+n-3,".sm")){
        out=(char*)calloc(n-2,1);
        if(!out)return NULL;
        memcpy(out,input,n-3);
        out[n-3]='\0';
        return out;
    }
    out=(char*)calloc(n+9,1);
    if(!out)return NULL;
    snprintf(out,n+9,"%s.decoded",input);
    return out;
}

static void print_json_string(const char *text)
{
    const unsigned char *p=(const unsigned char *)(text?text:"");
    putchar('"');
    while(*p){
        if(*p=='"'||*p=='\\'){putchar('\\');putchar(*p);}
        else if(*p=='\n')printf("\\n");
        else if(*p=='\r')printf("\\r");
        else if(*p=='\t')printf("\\t");
        else if(*p<0x20)printf("\\u%04x",(unsigned)*p);
        else putchar(*p);
        p++;
    }
    putchar('"');
}

static void print_sm_info_json(const char *path, const SmInfo *info)
{
    printf("{\"path\":");
    print_json_string(path?path:"");
    printf(",\"codec\":");
    print_json_string(info->codec);
    printf(",\"version\":%d,"
           "\"dictionary_entries\":%d,\"original_size\":%u,"
           "\"token_stream_size\":%u,\"payload_size\":%u,"
           "\"compressed_size\":%u,\"checksum_ok\":%s}\n",
           info->version,info->dictionary_entries,
           info->original_size,info->token_stream_size,info->payload_size,
           info->compressed_size,info->checksum_ok?"true":"false");
}

int mellowrt_sm_cli(int argc, char **argv)
{
    const char *cmd;
    const char *input;
    const char *out_arg;
    char *out_default=NULL;
    const char *out_path;
    int json;
    unsigned char *data=NULL;
    unsigned char *out=NULL;
    size_t data_size=0,out_size=0;
    SmInfo info;
    if(argc<3){
        fprintf(stderr,"usage: %s sm <pack|inspect|unpack> <input> [-o output] [--json]\n",argv[0]);
        return 1;
    }
    cmd=argv[2];
    input=argc>=4?argv[3]:NULL;
    out_arg=arg_value(argc,argv,"-o");
    if(!out_arg)out_arg=arg_value(argc,argv,"--out");
    json=has_arg(argc,argv,"--json");
    if(!input||input[0]=='-'){
        fprintf(stderr,"sm %s requires an input path\n",cmd);
        return 1;
    }
    data=read_binary_file(input,&data_size);
    if(!data){
        fprintf(stderr,"cannot read %s\n",input);
        return 1;
    }
    if(!strcmp(cmd,"pack")){
        out_default=out_arg?NULL:default_sm_pack_output(input);
        out_path=out_arg?out_arg:out_default;
        if(!out_path){free(data);fprintf(stderr,"out of memory\n");return 1;}
        if(!sm_native_pack_text(data,data_size,&out,&out_size,&info)){
            fprintf(stderr,"%s\n",info.error[0]?info.error:"SM pack failed");
            free(data);free(out_default);return 1;
        }
        if(!write_binary_file(out_path,out,out_size)){
            fprintf(stderr,"cannot write %s\n",out_path);
            free(data);free(out);free(out_default);return 1;
        }
        if(json){
            printf("{\"input\":");
            print_json_string(input);
            printf(",\"output\":");
            print_json_string(out_path);
            printf(",\"input_bytes\":%u,\"output_bytes\":%u,"
                   "\"ratio\":%.4f,\"saved_bytes\":%d,\"codec\":",
                   info.original_size,info.compressed_size,
                   info.original_size?((double)info.compressed_size/(double)info.original_size):0.0,
                   (int)info.original_size-(int)info.compressed_size);
            print_json_string(info.codec);
            printf("}\n");
        }else{
            printf("packed %s -> %s (%.2f%%, %s)\n",
                   input,out_path,
                   info.original_size?100.0*((double)info.compressed_size/(double)info.original_size):0.0,
                   info.codec);
        }
        free(data);free(out);free(out_default);return 0;
    }
    if(!strcmp(cmd,"inspect")){
        if(!sm_native_inspect_bytes(data,data_size,&info)){
            fprintf(stderr,"%s\n",info.error[0]?info.error:"SM inspect failed");
            free(data);return 1;
        }
        if(json)print_sm_info_json(input,&info);
        else{
            printf(".sm codec: %s\n",info.codec);
            printf("version: %d\n",info.version);
            printf("dictionary entries: %d\n",info.dictionary_entries);
            printf("original size: %u\n",info.original_size);
            printf("compressed size: %u\n",info.compressed_size);
            printf("checksum ok: %s\n",info.checksum_ok?"true":"false");
        }
        free(data);return 0;
    }
    if(!strcmp(cmd,"unpack")){
        out_default=out_arg?NULL:default_sm_unpack_output(input);
        out_path=out_arg?out_arg:out_default;
        if(!out_path){free(data);fprintf(stderr,"out of memory\n");return 1;}
        if(!sm_native_unpack_bytes(data,data_size,&out,&out_size,&info)){
            fprintf(stderr,"%s\n",info.error[0]?info.error:"SM unpack failed");
            free(data);free(out_default);return 1;
        }
        if(!write_binary_file(out_path,out,out_size)){
            fprintf(stderr,"cannot write %s\n",out_path);
            free(data);free(out);free(out_default);return 1;
        }
        if(json){
            printf("{\"input\":");
            print_json_string(input);
            printf(",\"output\":");
            print_json_string(out_path);
            printf(",\"decoded_bytes\":%u,\"codec\":",(unsigned)out_size);
            print_json_string(info.codec);
            printf("}\n");
        }
        else printf("unpacked %s -> %s\n",input,out_path);
        free(data);free(out);free(out_default);return 0;
    }
    fprintf(stderr,"unknown sm command: %s\n",cmd);
    free(data);
    return 1;
}
