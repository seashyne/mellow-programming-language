#include "mellowc_internal.h"

#include <ctype.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void set_error(Compiler *c, const char *message) {
    if (c->error && c->error_cap && !c->error[0])
        snprintf(c->error, c->error_cap, "%s:%d:1: syntax error: %s",
                 c->source_name ? c->source_name : "<memory>", c->current_line, message);
}

char *copy_text(const char *s, size_t n) {
    char *p = (char *)calloc(n + 1, 1);
    if (p && n) memcpy(p, s, n);
    return p;
}

static int reserve(void **ptr, size_t *cap, size_t need, size_t item_size) {
    size_t next;
    void *grown;
    if (*cap >= need) return 1;
    next = *cap ? *cap * 2 : 32;
    while (next < need) next *= 2;
    grown = realloc(*ptr, next * item_size);
    if (!grown) return 0;
    *ptr = grown;
    *cap = next;
    return 1;
}

int emit(Compiler *c, int op, int a, int b, int d) {
    MSourceSpan span;
    if (!reserve((void **)&c->code, &c->code_cap, c->code_len + 1, sizeof(*c->code)) ||
        !reserve((void **)&c->spans, &c->span_cap, c->span_len + 1, sizeof(*c->spans))) {
        set_error(c, "out of memory");
        return -1;
    }
    c->code[c->code_len] = (MInstruction){(uint8_t)op, a, b, d};
    span = (MSourceSpan){(uint32_t)c->current_line, 1, (uint32_t)c->current_line, 1};
    c->spans[c->span_len++] = span;
    return (int)c->code_len++;
}

int add_const(Compiler *c, MValue value) {
    if (!reserve((void **)&c->consts, &c->const_cap, c->const_len + 1, sizeof(*c->consts))) {
        set_error(c, "constant pool allocation failed");
        return -1;
    }
    c->consts[c->const_len] = value;
    return (int)c->const_len++;
}

MValue owned_string(const char *s, size_t n) {
    MValue value = mval_none();
    char *copy = copy_text(s, n);
    if (!copy) return value;
    value.tag = MVAL_STR;
    value.flags = 1u;
    value.as.str.ptr = copy;
    value.as.str.len = n;
    return value;
}

int scope_find(Scope *scope, const char *name, size_t len) {
    int i;
    for (i = 0; i < scope->len; ++i)
        if (strlen(scope->vars[i].name) == len && memcmp(scope->vars[i].name, name, len) == 0)
            return scope->vars[i].slot;
    return -1;
}

int scope_slot(Scope *scope, const char *name, size_t len, int create) {
    int slot = scope_find(scope, name, len);
    if (slot >= 0 || !create || scope->len >= 256) return slot;
    slot = scope->len;
    snprintf(scope->vars[scope->len].name, sizeof(scope->vars[scope->len].name), "%.*s", (int)len, name);
    scope->vars[scope->len].slot = slot;
    scope->is_i64[scope->len] = 0;
    scope->len++;
    return slot;
}

Function *find_function(Compiler *c, const char *name, size_t len) {
    int i;
    for (i = 0; i < c->func_count; ++i)
        if (strlen(c->funcs[i].name) == len && memcmp(c->funcs[i].name, name, len) == 0)
            return &c->funcs[i];
    return NULL;
}

const char *trim(char *text) {
    while (*text && isspace((unsigned char)*text)) text++;
    return text;
}

void strip_inline_comment(char *text) {
    int quote = 0;
    int escaped = 0;
    int depth = 0;
    size_t i;
    for (i = 0; text[i]; ++i) {
        char ch = text[i];
        if (escaped) { escaped = 0; continue; }
        if (quote) {
            if (ch == '\\') escaped = 1;
            else if (ch == quote) quote = 0;
            continue;
        }
        if (ch == '"' || ch == '\'') { quote = ch; continue; }
        if (ch == '(' || ch == '[' || ch == '{') depth++;
        else if ((ch == ')' || ch == ']' || ch == '}') && depth > 0) depth--;
        else if (depth == 0 && ch == '#') { text[i] = '\0'; break; }
        else if (depth == 0 && ch == '/' && text[i + 1] == '/') { text[i] = '\0'; break; }
    }
    while (i > 0 && isspace((unsigned char)text[i - 1])) text[--i] = '\0';
}

int starts(const char *text, const char *prefix) {
    size_t n = strlen(prefix);
    return strncmp(text, prefix, n) == 0;
}

static int ident_len_at(const char *text) {
    int n = 0;
    if (!text || !(isalpha((unsigned char)text[0]) || text[0] == '_')) return 0;
    while (isalnum((unsigned char)text[n]) || text[n] == '_') n++;
    return n;
}

static const char *skip_spaces(const char *text) {
    while (*text && isspace((unsigned char)*text)) text++;
    return text;
}

static int expr_is_i64_literal(const char *expr) {
    char *endp = NULL;
    const char *p = skip_spaces(expr);
    (void)strtoll(p, &endp, 10);
    return endp != p && *skip_spaces(endp) == '\0';
}

static int emit_fast_i64_lt_jump(Compiler *c, const char *condition, int *jump_index) {
    const char *p = skip_spaces(condition);
    int left_len = ident_len_at(p);
    char left[64], right[64];
    int right_len, left_slot, right_slot;
    if (!left_len || left_len >= (int)sizeof(left)) return 0;
    memcpy(left, p, (size_t)left_len); left[left_len] = '\0';
    p = skip_spaces(p + left_len);
    if (*p != '<' || p[1] == '=') return 0;
    p = skip_spaces(p + 1);
    right_len = ident_len_at(p);
    if (!right_len || right_len >= (int)sizeof(right)) return 0;
    memcpy(right, p, (size_t)right_len); right[right_len] = '\0';
    p = skip_spaces(p + right_len);
    if (*p) return 0;
    left_slot = scope_find(c->scope, left, strlen(left));
    right_slot = scope_find(c->scope, right, strlen(right));
    if (left_slot < 0 || right_slot < 0) return 0;
    if (!c->scope->is_i64[left_slot] || !c->scope->is_i64[right_slot]) return 0;
    *jump_index = emit(c, MOP_JUMP_IF_LOCAL_I64_LT_FALSE, left_slot, right_slot, 0);
    return *jump_index >= 0 ? 1 : -1;
}

static int emit_fast_i64_add_assignment(Compiler *c, const char *lhs, const char *expr) {
    const char *p = skip_spaces(expr);
    int left_len = ident_len_at(p);
    char left[64], rhs_name[64];
    int lhs_slot, rhs_slot, rhs_len;
    char *endp = NULL;
    long long delta;
    if (!left_len || left_len >= (int)sizeof(left)) return 0;
    memcpy(left, p, (size_t)left_len); left[left_len] = '\0';
    p = skip_spaces(p + left_len);
    if (*p != '+') return 0;
    p = skip_spaces(p + 1);
    if (strcmp(lhs, left) != 0) return 0;
    lhs_slot = scope_find(c->scope, lhs, strlen(lhs));
    if (lhs_slot < 0) return 0;
    if (!c->scope->is_i64[lhs_slot]) return 0;

    rhs_len = ident_len_at(p);
    if (rhs_len > 0) {
        if (rhs_len >= (int)sizeof(rhs_name)) return 0;
        memcpy(rhs_name, p, (size_t)rhs_len); rhs_name[rhs_len] = '\0';
        p = skip_spaces(p + rhs_len);
        if (*p) return 0;
        rhs_slot = scope_find(c->scope, rhs_name, strlen(rhs_name));
        if (rhs_slot < 0) return 0;
        if (!c->scope->is_i64[rhs_slot]) return 0;
        return emit(c, MOP_I64_ADD_LOCAL_LOCAL, lhs_slot, rhs_slot, 0) >= 0 ? 1 : -1;
    }

    delta = strtoll(p, &endp, 10);
    if (endp == p || *skip_spaces(endp) || delta < INT_MIN || delta > INT_MAX) return 0;
    return emit(c, MOP_I64_ADD_LOCAL_CONST, lhs_slot, (int)delta, 0) >= 0 ? 1 : -1;
}

int find_assignment(const char *text) {
    int depth=0, quote=0, i;
    for(i=0;text[i];++i) {
        char ch=text[i];
        if(quote){if(ch==quote&&text[i-1]!='\\')quote=0;continue;}
        if(ch=='"'||ch=='\''){quote=ch;continue;}
        if(ch=='('||ch=='['||ch=='{')depth++;
        else if(ch==')'||ch==']'||ch=='}')depth--;
        else if(ch=='='&&depth==0&&text[i+1]!='='&&
                (i==0||(text[i-1]!='!'&&text[i-1]!='<'&&text[i-1]!='>')))return i;
    }
    return -1;
}

static int compile_block(Compiler *c, int *position, int end, int indent);

static int compile_statement(Compiler *c, int *position, int end, int indent) {
    SourceLine *line=&c->lines[*position];
    char *text=(char*)trim(line->text);
    int assign;
    c->current_line=line->number;
    strip_inline_comment(text);
    text=(char*)trim(text);
    if (!*text || starts(text,"//") || *text=='#') { (*position)++; return 1; }
    {
        int import_result = parse_import_statement(c, text);
        if (import_result < 0) return 0;
        if (import_result > 0) { (*position)++; return 1; }
    }
    if (starts(text,"def ")) {
        Function *fn=NULL; int i;
        for(i=0;i<c->func_count;++i)if(c->funcs[i].line_start==*position){fn=&c->funcs[i];break;}
        *position=fn?fn->line_end:*position+1;
        return 1;
    }
    if (starts(text,"if ") && text[strlen(text)-1]==':') {
        int jump_false;
        int end_jumps[32];
        int end_count=0;
        text[strlen(text)-1]='\0';
        if(!compile_expr(c,text+3))return 0;
        jump_false=emit(c,MOP_JUMP_IF_FALSE,0,0,0);
        (*position)++;
        if(!compile_block(c,position,end,indent+4))return 0;
        while(*position<end && c->lines[*position].indent==indent){
            char *next=(char*)trim(c->lines[*position].text);
            strip_inline_comment(next);
            next=(char*)trim(next);
            if(starts(next,"elif ") && next[strlen(next)-1]==':'){
                if(end_count<32)end_jumps[end_count++]=emit(c,MOP_JUMP,0,0,0);
                c->code[jump_false].a=(int32_t)c->code_len;
                next[strlen(next)-1]='\0';
                c->current_line=c->lines[*position].number;
                if(!compile_expr(c,next+5))return 0;
                jump_false=emit(c,MOP_JUMP_IF_FALSE,0,0,0);
                (*position)++;
                if(!compile_block(c,position,end,indent+4))return 0;
                continue;
            }
            if(starts(next,"else:")){
                if(end_count<32)end_jumps[end_count++]=emit(c,MOP_JUMP,0,0,0);
                c->code[jump_false].a=(int32_t)c->code_len;
                c->current_line=c->lines[*position].number;
                (*position)++;
                if(!compile_block(c,position,end,indent+4))return 0;
                jump_false=-1;
            }
            break;
        }
        if(jump_false>=0)c->code[jump_false].a=(int32_t)c->code_len;
        for(int j=0;j<end_count;++j)c->code[end_jumps[j]].a=(int32_t)c->code_len;
        return 1;
    }
    if (starts(text,"stop")) {
        emit(c,MOP_STOP,0,0,0);(*position)++;return 1;
    }
    if (starts(text,"show ")) {
        if(!compile_expr(c,trim(text+5)))return 0;
        emit(c,MOP_SYSCALL,1,1,0);
        (*position)++;return 1;
    }
    if (starts(text,"while ") && text[strlen(text)-1]==':') {
        int loop=(int)c->code_len, jf;
        int depth=c->loop_depth++;
        c->loop_break_count[depth]=0;
        c->loop_continue_count[depth]=0;
        text[strlen(text)-1]='\0';
        {
            int fast_condition = emit_fast_i64_lt_jump(c, trim(text+6), &jf);
            if (fast_condition < 0) return 0;
            if (!fast_condition) {
                if(!compile_expr(c,text+6))return 0;
                jf=emit(c,MOP_JUMP_IF_FALSE,0,0,0);
            }
        }
        (*position)++;
        if(!compile_block(c,position,end,indent+4))return 0;
        for(int j=0;j<c->loop_continue_count[depth];++j)c->code[c->loop_continues[depth][j]].a=loop;
        emit(c,MOP_JUMP,loop,0,0);
        if (c->code[jf].opcode == MOP_JUMP_IF_LOCAL_I64_LT_FALSE) c->code[jf].c=(int32_t)c->code_len;
        else c->code[jf].a=(int32_t)c->code_len;
        for(int j=0;j<c->loop_break_count[depth];++j)c->code[c->loop_breaks[depth][j]].a=(int32_t)c->code_len;
        c->loop_depth--;
        return 1;
    }
    if (starts(text,"for ") && text[strlen(text)-1]==':') {
        char name[64], start_expr[256], stop_expr[256];
        int slot, stop_slot, loop, jf;
        int depth=c->loop_depth++;
        c->loop_break_count[depth]=0;
        c->loop_continue_count[depth]=0;
        if(sscanf(text,"for %63s in range(%255[^,],%255[^)]):",name,start_expr,stop_expr)!=3){
            if(sscanf(text,"for %63s in range(%255[^)]):",name,stop_expr)!=2){
                set_error(c,"expected for name in range(start, stop):");return 0;
            }
            snprintf(start_expr,sizeof(start_expr),"0");
        }
        slot=scope_slot(c->scope,name,strlen(name),1);
        snprintf(name,sizeof(name),"__stop_%d",line->number);
        stop_slot=scope_slot(c->scope,name,strlen(name),1);
        if(!compile_expr(c,start_expr)||emit(c,MOP_STORE_LOCAL,slot,0,0)<0||
           !compile_expr(c,stop_expr)||emit(c,MOP_STORE_LOCAL,stop_slot,0,0)<0)return 0;
        loop=(int)c->code_len;
        emit(c,MOP_LOAD_LOCAL,slot,0,0);emit(c,MOP_LOAD_LOCAL,stop_slot,0,0);emit(c,MOP_COMPARE,MCMP_LT,0,0);
        jf=emit(c,MOP_JUMP_IF_FALSE,0,0,0);
        (*position)++;
        if(!compile_block(c,position,end,indent+4))return 0;
        for(int j=0;j<c->loop_continue_count[depth];++j)c->code[c->loop_continues[depth][j]].a=(int32_t)c->code_len;
        emit(c,MOP_LOAD_LOCAL,slot,0,0);
        {int one=add_const(c,mval_i64(1));emit(c,MOP_PUSH_CONST,one,0,0);}
        emit(c,MOP_ADD,0,0,0);emit(c,MOP_STORE_LOCAL,slot,0,0);emit(c,MOP_JUMP,loop,0,0);
        c->code[jf].a=(int32_t)c->code_len;
        for(int j=0;j<c->loop_break_count[depth];++j)c->code[c->loop_breaks[depth][j]].a=(int32_t)c->code_len;
        c->loop_depth--;
        return 1;
    }
    if (starts(text,"break")) {
        int depth=c->loop_depth-1;
        int jump;
        if(depth<0){set_error(c,"break outside loop");return 0;}
        jump=emit(c,MOP_JUMP,0,0,0);
        if(c->loop_break_count[depth]<64)c->loop_breaks[depth][c->loop_break_count[depth]++]=jump;
        (*position)++;return 1;
    }
    if (starts(text,"continue")) {
        int depth=c->loop_depth-1;
        int jump;
        if(depth<0){set_error(c,"continue outside loop");return 0;}
        jump=emit(c,MOP_JUMP,0,0,0);
        if(c->loop_continue_count[depth]<64)c->loop_continues[depth][c->loop_continue_count[depth]++]=jump;
        (*position)++;return 1;
    }
    if (starts(text,"wait ")) {
        char *expr=(char*)trim(text+5);
        char *endp=NULL;
        double seconds=strtod(expr,&endp);
        if(endp&&*trim(endp)=='\0'){
            int ci=add_const(c,mval_i64((int64_t)(seconds*1000.0)));
            if(ci<0||emit(c,MOP_PUSH_CONST,ci,0,0)<0)return 0;
        } else {
            if(!compile_expr(c,expr))return 0;
        }
        emit(c,MOP_SYSCALL,18,1,0);
        (*position)++;return 1;
    }
    if (starts(text,"return")) {
        const char *expr=trim(text+6);
        if(*expr){if(!compile_expr(c,expr))return 0;}
        else {int ci=add_const(c,mval_none());emit(c,MOP_PUSH_CONST,ci,0,0);}
        emit(c,MOP_RETURN,0,0,0);(*position)++;return 1;
    }
    if (starts(text,"print(") && text[strlen(text)-1]==')') {
        if(!compile_expr(c,text))return 0;
        (*position)++;return 1;
    }
    if(starts(text,"let "))text=(char*)trim(text+4);
    else if(starts(text,"var "))text=(char*)trim(text+4);
    else if(starts(text,"keep "))text=(char*)trim(text+5);
    assign=find_assignment(text);
    if(assign>=0){
        char name[64];const char *expr;
        size_t n=(size_t)assign;
        while(n&&isspace((unsigned char)text[n-1]))n--;
        snprintf(name,sizeof(name),"%.*s",(int)n,text);
        expr=trim(text+assign+1);
        {
            int fast_assign = emit_fast_i64_add_assignment(c, name, expr);
            if (fast_assign < 0) return 0;
            if (fast_assign) {
                int slot = scope_find(c->scope, name, strlen(name));
                if (slot >= 0) c->scope->is_i64[slot] = 1;
            } else {
                int slot;
                if(!compile_expr(c,expr))return 0;
                slot=scope_slot(c->scope,name,strlen(name),1);
                if(slot<0||emit(c,MOP_STORE_LOCAL,slot,0,0)<0)return 0;
                c->scope->is_i64[slot] = (unsigned char)expr_is_i64_literal(expr);
            }
        }
        (*position)++;return 1;
    }
    if(!compile_expr(c,text))return 0;
    emit(c,MOP_POP,0,0,0);(*position)++;return 1;
}

static int compile_block(Compiler *c, int *position, int end, int indent) {
    while(*position<end){
        SourceLine *line=&c->lines[*position];
        char *text=(char*)trim(line->text);
        strip_inline_comment(text);
        text=(char*)trim(text);
        if(!*text||starts(text,"//")||*text=='#'){(*position)++;continue;}
        if(line->indent<indent)return 1;
        if(line->indent>indent){set_error(c,"unexpected indentation");return 0;}
        if(!compile_statement(c,position,end,indent))return 0;
    }
    return 1;
}

static int split_lines(Compiler *c, const char *source) {
    const char *p=source,*start=source;
    int number=1;
    while(1){
        if(*p=='\n'||!*p){
            size_t n=(size_t)(p-start),cap=c->line_count+1;
            int indent=0;
            SourceLine *grown=(SourceLine*)realloc(c->lines,sizeof(*grown)*(size_t)cap);
            char *line;
            if(!grown)return 0;
            c->lines=grown;
            if(n&&start[n-1]=='\r')n--;
            line=copy_text(start,n);if(!line)return 0;
            while(line[indent]==' ')indent++;
            c->lines[c->line_count++]=(SourceLine){line,indent,number++};
            if(!*p)break;
            start=++p;continue;
        }
        p++;
    }
    return 1;
}

static int scan_functions(Compiler *c) {
    int i;
    for(i=0;i<c->line_count;++i){
        char *text=(char*)trim(c->lines[i].text);
        if(c->lines[i].indent==0&&starts(text,"def ")){
            Function *fn;
            char *lp=strchr(text,'('),*rp=strrchr(text,')'),*cursor;
            int j=i+1;
            if(!lp||!rp||rp<lp||c->func_count>=128){c->current_line=c->lines[i].number;set_error(c,"invalid function declaration");return 0;}
            fn=&c->funcs[c->func_count++];memset(fn,0,sizeof(*fn));
            snprintf(fn->name,sizeof(fn->name),"%.*s",(int)(lp-(text+4)),text+4);
            cursor=lp+1;
            while(cursor<rp){
                char *comma=strchr(cursor,',');char *stop=comma&&comma<rp?comma:rp;
                while(cursor<stop&&isspace((unsigned char)*cursor))cursor++;
                while(stop>cursor&&isspace((unsigned char)stop[-1]))stop--;
                if(stop>cursor){
                    if(fn->arity>=16){c->current_line=c->lines[i].number;set_error(c,"function has more than 16 parameters");return 0;}
                    snprintf(fn->params[fn->arity++],64,"%.*s",(int)(stop-cursor),cursor);
                }
                cursor=comma&&comma<rp?comma+1:rp;
            }
            while(j<c->line_count&&(c->lines[j].indent>0||!*trim(c->lines[j].text)))j++;
            fn->line_start=i;fn->line_end=j;fn->body_indent=4;
            fn->const_slot=add_const(c,mval_func(0,(uint16_t)fn->arity,0,0));
        }
    }
    return 1;
}

int mellow_compile_source(const char *source,const char *source_name,MNativeProgram *out,char *error,size_t error_cap){
    Compiler c;int i,pos,jump_main;
    memset(&c,0,sizeof(c));memset(out,0,sizeof(*out));
    c.error=error;c.error_cap=error_cap;c.scope=&c.globals;c.current_line=1;c.source_name=source_name;
    if(error&&error_cap)error[0]='\0';
    if(!split_lines(&c,source)||!scan_functions(&c))goto fail;
    jump_main=emit(&c,MOP_JUMP,0,0,0);
    for(i=0;i<c.func_count;++i){
        Scope local;Function *fn=&c.funcs[i];memset(&local,0,sizeof(local));
        for(int p=0;p<fn->arity;++p)scope_slot(&local,fn->params[p],strlen(fn->params[p]),1);
        c.scope=&local;fn->address=(int)c.code_len;pos=fn->line_start+1;
        if(!compile_block(&c,&pos,fn->line_end,fn->body_indent))goto fail;
        if(!c.code_len||c.code[c.code_len-1].opcode!=MOP_RETURN){
            int none=add_const(&c,mval_none());emit(&c,MOP_PUSH_CONST,none,0,0);emit(&c,MOP_RETURN,0,0,0);
        }
        fn->local_count=local.len;
        c.consts[fn->const_slot]=mval_func((uint32_t)fn->address,(uint16_t)fn->arity,(uint16_t)fn->local_count,0);
    }
    c.scope=&c.globals;c.code[jump_main].a=(int32_t)c.code_len;pos=0;
    if(!compile_block(&c,&pos,c.line_count,0))goto fail;
    emit(&c,MOP_HALT,0,0,0);
    out->code=c.code;out->code_len=c.code_len;out->consts=c.consts;out->const_len=c.const_len;
    out->spans=c.spans;out->span_len=c.span_len;out->source_name=copy_text(source_name?source_name:"<memory>",strlen(source_name?source_name:"<memory>"));
    for(i=0;i<c.line_count;++i)free(c.lines[i].text);
    free(c.lines);
    return 1;
fail:
    for(i=0;i<c.line_count;++i)free(c.lines[i].text);
    free(c.lines);
    for(i=0;i<(int)c.const_len;++i)mvalue_free(&c.consts[i]);
    free(c.consts);free(c.code);free(c.spans);
    return 0;
}

int mellow_compile_file(const char *path,MNativeProgram *out,char *error,size_t error_cap){
    FILE *f=fopen(path,"rb");long size;char *source;int ok;
    if(!f){if(error&&error_cap)snprintf(error,error_cap,"cannot open %s",path);return 0;}
    fseek(f,0,SEEK_END);size=ftell(f);fseek(f,0,SEEK_SET);
    source=(char*)calloc((size_t)size+1,1);
    if(!source||fread(source,1,(size_t)size,f)!=(size_t)size){free(source);fclose(f);return 0;}
    fclose(f);ok=mellow_compile_source(source,path,out,error,error_cap);free(source);return ok;
}

void mellow_native_program_free(MNativeProgram *program){
    size_t i;if(!program)return;
    for(i=0;i<program->const_len;++i)mvalue_free(&program->consts[i]);
    free(program->consts);free(program->code);free(program->spans);free(program->source_name);
    memset(program,0,sizeof(*program));
}
