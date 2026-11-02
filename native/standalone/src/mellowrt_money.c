#include "mellowrt_money.h"

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static MValue money_owned_string(const char *src, size_t len){
    char *buf=(char*)calloc(len+1,1);
    MValue v=mval_none();
    if(!buf)return v;
    if(src&&len)memcpy(buf,src,len);
    buf[len]='\0';
    v.tag=MVAL_STR;
    v.flags=1u;
    v.as.str.ptr=buf;
    v.as.str.len=len;
    return v;
}

static int str_eq(const MValue *value, const char *text){
    size_t n=strlen(text);
    return value&&value->tag==MVAL_STR&&value->as.str.len==n&&
           value->as.str.ptr&&memcmp(value->as.str.ptr,text,n)==0;
}

static const MValue *map_get_str(const MValue *map, const char *key){
    size_t i;
    if(!map||map->tag!=MVAL_MAP)return NULL;
    for(i=0;i<map->as.map.len;++i)
        if(str_eq(&map->as.map.keys[i],key))return &map->as.map.values[i];
    return NULL;
}

static int is_money_map(const MValue *value){
    const MValue *type=map_get_str(value,"type");
    return type&&str_eq(type,"money");
}

static int currency_from_value(const MValue *value, char out[16]){
    size_t i,n;
    if(!value||value->tag==MVAL_NONE){
        snprintf(out,16,"USD");
        return 1;
    }
    if(value->tag!=MVAL_STR||!value->as.str.ptr)return 0;
    n=value->as.str.len;
    while(n&&value->as.str.ptr[n-1]==' ')n--;
    if(n==0||n>=16)return 0;
    for(i=0;i<n;++i){
        char ch=value->as.str.ptr[i];
        if(ch>='a'&&ch<='z')ch=(char)(ch-'a'+'A');
        if(!((ch>='A'&&ch<='Z')||(ch>='0'&&ch<='9')||ch=='_'))return 0;
        out[i]=ch;
    }
    out[n]='\0';
    return 1;
}

static int parse_cents_string(const char *s, size_t n, int64_t *out){
    int sign=1;
    size_t i=0;
    int64_t units=0;
    int cents=0;
    int frac_digits=0;
    if(!s||!out)return 0;
    while(i<n&&(s[i]==' '||s[i]=='\t'))i++;
    if(i<n&&(s[i]=='-'||s[i]=='+')){if(s[i]=='-')sign=-1;i++;}
    if(i>=n)return 0;
    while(i<n&&s[i]>='0'&&s[i]<='9'){
        if(units>INT64_MAX/10)return 0;
        units=units*10+(int64_t)(s[i]-'0');
        i++;
    }
    if(i<n&&s[i]=='.'){
        i++;
        while(i<n&&s[i]>='0'&&s[i]<='9'){
            int digit=s[i]-'0';
            if(frac_digits<2)cents=cents*10+digit;
            else if(frac_digits==2&&digit>=5)cents++;
            frac_digits++;
            i++;
        }
    }
    while(frac_digits<2){cents*=10;frac_digits++;}
    while(i<n&&(s[i]==' '||s[i]=='\t'))i++;
    if(i!=n)return 0;
    if(cents>=100){units++;cents-=100;}
    if(units>(INT64_MAX-cents)/100)return 0;
    *out=(units*100+(int64_t)cents)*(int64_t)sign;
    return 1;
}

int mellowrt_money_cents(const MValue *value, int64_t *out){
    const MValue *amount;
    if(is_money_map(value)){
        amount=map_get_str(value,"amount");
        return mellowrt_money_cents(amount,out);
    }
    if(!value||!out)return 0;
    if(value->tag==MVAL_STR)return parse_cents_string(value->as.str.ptr,value->as.str.len,out);
    if(value->tag==MVAL_I64){
        if(value->as.i64>INT64_MAX/100||value->as.i64<INT64_MIN/100)return 0;
        *out=value->as.i64*100;
        return 1;
    }
    if(value->tag==MVAL_F64&&isfinite(value->as.f64)&&value->as.f64<(double)(INT64_MAX/100)&&value->as.f64>(double)(INT64_MIN/100)){
        *out=(int64_t)llround(value->as.f64*100.0);
        return 1;
    }
    return 0;
}

void mellowrt_money_format_cents(int64_t cents, char out[64]){
    int negative=cents<0;
    uint64_t abs_cents=negative?(uint64_t)(-(cents+1))+1u:(uint64_t)cents;
    snprintf(out,64,"%s%llu.%02llu",
             negative?"-":"",
             (unsigned long long)(abs_cents/100u),
             (unsigned long long)(abs_cents%100u));
}

MValue mellowrt_money_make(int64_t cents, const char *currency){
    MValue v=mval_none();
    char amount[64];
    v.tag=MVAL_MAP;
    v.as.map.len=v.as.map.cap=3;
    v.as.map.keys=(MValue*)calloc(3,sizeof(MValue));
    v.as.map.values=(MValue*)calloc(3,sizeof(MValue));
    if(!v.as.map.keys||!v.as.map.values){
        free(v.as.map.keys);free(v.as.map.values);return mval_none();
    }
    mellowrt_money_format_cents(cents,amount);
    v.as.map.keys[0]=money_owned_string("type",4);
    v.as.map.values[0]=money_owned_string("money",5);
    v.as.map.keys[1]=money_owned_string("currency",8);
    v.as.map.values[1]=money_owned_string(currency?currency:"USD",strlen(currency?currency:"USD"));
    v.as.map.keys[2]=money_owned_string("amount",6);
    v.as.map.values[2]=money_owned_string(amount,strlen(amount));
    return v;
}

static int money_parts(const MValue *value, int64_t *cents, char currency[16]){
    const MValue *cur;
    if(is_money_map(value)){
        cur=map_get_str(value,"currency");
        if(!currency_from_value(cur,currency))return 0;
        return mellowrt_money_cents(value,cents);
    }
    snprintf(currency,16,"USD");
    return mellowrt_money_cents(value,cents);
}

static int scalar_value(const MValue *value, double *out){
    if(!value||!out)return 0;
    if(value->tag==MVAL_I64){*out=(double)value->as.i64;return 1;}
    if(value->tag==MVAL_F64&&isfinite(value->as.f64)){*out=value->as.f64;return 1;}
    if(value->tag==MVAL_STR){
        char tmp[64];
        char *endp=NULL;
        size_t n=value->as.str.len<sizeof(tmp)-1?value->as.str.len:sizeof(tmp)-1;
        memcpy(tmp,value->as.str.ptr,n);
        tmp[n]='\0';
        *out=strtod(tmp,&endp);
        return endp&&*endp=='\0';
    }
    return 0;
}

static int same_currency(const char *a, const char *b){
    return strcmp(a? a:"USD",b? b:"USD")==0;
}

int mellowrt_money_syscall(int32_t id, const MValue *args, size_t argc, MValue *out_result){
    int64_t a,b;
    char cur_a[16],cur_b[16];
    if(!out_result)return 0;
    switch(id){
    case 38:
        if(argc!=1&&argc!=2)return 0;
        if(!mellowrt_money_cents(&args[0],&a))return 0;
        if(argc==2){if(!currency_from_value(&args[1],cur_a))return 0;}
        else snprintf(cur_a,16,"USD");
        *out_result=mellowrt_money_make(a,cur_a);
        return out_result->tag==MVAL_MAP;
    case 39:
    case 40:
        if(argc!=2)return 0;
        if(!money_parts(&args[0],&a,cur_a)||!money_parts(&args[1],&b,cur_b)||!same_currency(cur_a,cur_b))return 0;
        *out_result=mellowrt_money_make(id==39?a+b:a-b,cur_a);
        return out_result->tag==MVAL_MAP;
    case 41:{
        double factor;
        if(argc!=2)return 0;
        if(!money_parts(&args[0],&a,cur_a)||!scalar_value(&args[1],&factor))return 0;
        *out_result=mellowrt_money_make((int64_t)llround((double)a*factor),cur_a);
        return out_result->tag==MVAL_MAP;
    }
    case 42:{
        double divisor;
        if(argc!=2)return 0;
        if(!money_parts(&args[0],&a,cur_a)||!scalar_value(&args[1],&divisor)||divisor==0.0)return 0;
        *out_result=mellowrt_money_make((int64_t)llround((double)a/divisor),cur_a);
        return out_result->tag==MVAL_MAP;
    }
    case 43:
        if(argc!=1&&argc!=2)return 0;
        if(!money_parts(&args[0],&a,cur_a))return 0;
        /* Native money currently stores cents, so quantize keeps 2 decimal places. */
        *out_result=mellowrt_money_make(a,cur_a);
        return out_result->tag==MVAL_MAP;
    case 44:{
        char amount[64],buf[96];
        if(argc!=1||!money_parts(&args[0],&a,cur_a))return 0;
        mellowrt_money_format_cents(a,amount);
        snprintf(buf,sizeof(buf),"%s %s",cur_a,amount);
        *out_result=money_owned_string(buf,strlen(buf));
        return 1;
    }
    case 45:{
        char amount[64];
        if(argc!=1||!money_parts(&args[0],&a,cur_a))return 0;
        (void)cur_a;
        mellowrt_money_format_cents(a,amount);
        *out_result=money_owned_string(amount,strlen(amount));
        return 1;
    }
    case 46:
        if(argc!=1||!money_parts(&args[0],&a,cur_a))return 0;
        (void)a;
        *out_result=money_owned_string(cur_a,strlen(cur_a));
        return 1;
    case 47:
    case 48:
    case 49:
        if(argc!=2)return 0;
        if(!money_parts(&args[0],&a,cur_a)||!money_parts(&args[1],&b,cur_b)||!same_currency(cur_a,cur_b))return 0;
        if(id==47)*out_result=mval_bool(a==b);
        else if(id==48)*out_result=mval_bool(a<b);
        else *out_result=mval_bool(a>b);
        return 1;
    default:
        return 0;
    }
}
