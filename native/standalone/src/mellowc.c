#include "mellowrt.h"

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef enum {
    TK_EOF, TK_NUM, TK_STR, TK_ID, TK_LP, TK_RP, TK_LB, TK_RB, TK_LC, TK_RC,
    TK_COMMA, TK_COLON, TK_PLUS, TK_MINUS, TK_STAR, TK_SLASH, TK_PERCENT,
    TK_EQ, TK_NE, TK_LT, TK_LE, TK_GT, TK_GE
} TokenKind;

typedef struct {
    TokenKind kind;
    const char *start;
    size_t len;
    double number;
    int is_float;
} Token;

typedef struct {
    const char *cur;
    Token token;
    int line;
} Lexer;

typedef struct {
    char *text;
    int indent;
    int number;
} SourceLine;

typedef struct {
    char name[64];
    int slot;
} Variable;

typedef struct {
    Variable vars[256];
    int len;
} Scope;

typedef struct {
    char name[64];
    char params[16][64];
    int arity;
    int address;
    int local_count;
    int const_slot;
    int line_start;
    int line_end;
    int body_indent;
} Function;

typedef struct {
    MInstruction *code;
    size_t code_len, code_cap;
    MSourceSpan *spans;
    size_t span_len, span_cap;
    MValue *consts;
    size_t const_len, const_cap;
    SourceLine *lines;
    int line_count;
    Function funcs[128];
    int func_count;
    Scope globals;
    Scope *scope;
    int current_line;
    const char *source_name;
    char *error;
    size_t error_cap;
} Compiler;

typedef struct {
    Compiler *compiler;
    Lexer lexer;
} Expr;

static void set_error(Compiler *c, const char *message) {
    if (c->error && c->error_cap && !c->error[0])
        snprintf(c->error, c->error_cap, "%s:%d:1: syntax error: %s",
                 c->source_name ? c->source_name : "<memory>", c->current_line, message);
}

static char *copy_text(const char *s, size_t n) {
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

static int emit(Compiler *c, int op, int a, int b, int d) {
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

static int add_const(Compiler *c, MValue value) {
    if (!reserve((void **)&c->consts, &c->const_cap, c->const_len + 1, sizeof(*c->consts))) {
        set_error(c, "constant pool allocation failed");
        return -1;
    }
    c->consts[c->const_len] = value;
    return (int)c->const_len++;
}

static MValue owned_string(const char *s, size_t n) {
    MValue value = mval_none();
    char *copy = copy_text(s, n);
    if (!copy) return value;
    value.tag = MVAL_STR;
    value.flags = 1u;
    value.as.str.ptr = copy;
    value.as.str.len = n;
    return value;
}

static void lex_next(Lexer *l) {
    const char *start;
    while (*l->cur == ' ' || *l->cur == '\t') l->cur++;
    start = l->cur;
    l->token = (Token){TK_EOF, start, 0, 0, 0};
    if (!*start || *start == '#') return;
    if (isdigit((unsigned char)*start)) {
        char *end;
        l->token.number = strtod(start, &end);
        l->token.kind = TK_NUM;
        l->token.start = start;
        l->token.len = (size_t)(end - start);
        l->token.is_float = memchr(start, '.', l->token.len) != NULL;
        l->cur = end;
        return;
    }
    if (isalpha((unsigned char)*start) || *start == '_') {
        l->cur++;
        while (isalnum((unsigned char)*l->cur) || *l->cur == '_' || *l->cur == '.') l->cur++;
        l->token = (Token){TK_ID, start, (size_t)(l->cur - start), 0, 0};
        return;
    }
    if (*start == '"' || *start == '\'') {
        char quote = *start++;
        l->cur = start;
        while (*l->cur && *l->cur != quote) {
            if (*l->cur == '\\' && l->cur[1]) l->cur += 2;
            else l->cur++;
        }
        l->token = (Token){TK_STR, start, (size_t)(l->cur - start), 0, 0};
        if (*l->cur == quote) l->cur++;
        return;
    }
#define ONE(ch, token_kind) case ch: l->cur++; l->token.kind=token_kind; l->token.len=1; return
    switch (*start) {
        ONE('(', TK_LP); ONE(')', TK_RP); ONE('[', TK_LB); ONE(']', TK_RB);
        ONE('{', TK_LC); ONE('}', TK_RC); ONE(',', TK_COMMA); ONE(':', TK_COLON);
        ONE('+', TK_PLUS); ONE('-', TK_MINUS); ONE('*', TK_STAR);
        ONE('/', TK_SLASH); ONE('%', TK_PERCENT);
        case '=': l->cur++; l->token.kind = (*l->cur == '=') ? (l->cur++, TK_EQ) : TK_EOF; l->token.len=(size_t)(l->cur-start); return;
        case '!': l->cur++; l->token.kind = (*l->cur == '=') ? (l->cur++, TK_NE) : TK_EOF; l->token.len=(size_t)(l->cur-start); return;
        case '<': l->cur++; l->token.kind = (*l->cur == '=') ? (l->cur++, TK_LE) : TK_LT; l->token.len=(size_t)(l->cur-start); return;
        case '>': l->cur++; l->token.kind = (*l->cur == '=') ? (l->cur++, TK_GE) : TK_GT; l->token.len=(size_t)(l->cur-start); return;
        default: l->cur++; return;
    }
#undef ONE
}

static int token_is(Token *t, const char *text) {
    size_t n = strlen(text);
    return t->kind == TK_ID && t->len == n && memcmp(t->start, text, n) == 0;
}

static int scope_find(Scope *scope, const char *name, size_t len) {
    int i;
    for (i = 0; i < scope->len; ++i)
        if (strlen(scope->vars[i].name) == len && memcmp(scope->vars[i].name, name, len) == 0)
            return scope->vars[i].slot;
    return -1;
}

static int scope_slot(Scope *scope, const char *name, size_t len, int create) {
    int slot = scope_find(scope, name, len);
    if (slot >= 0 || !create || scope->len >= 256) return slot;
    slot = scope->len;
    snprintf(scope->vars[scope->len].name, sizeof(scope->vars[scope->len].name), "%.*s", (int)len, name);
    scope->vars[scope->len].slot = slot;
    scope->len++;
    return slot;
}

static Function *find_function(Compiler *c, const char *name, size_t len) {
    int i;
    for (i = 0; i < c->func_count; ++i)
        if (strlen(c->funcs[i].name) == len && memcmp(c->funcs[i].name, name, len) == 0)
            return &c->funcs[i];
    return NULL;
}

static int builtin_id(const char *name, size_t len) {
    static const struct { const char *name; int id; } builtins[] = {
        {"print",1},{"len",2},{"clock_ms",3},{"getenv",4},{"str",5},{"type",6},
        {"abs",7},{"floor",8},{"ceil",9},{"sqrt",10},{"min",11},{"max",12},{"range",20}
    };
    size_t i;
    for (i=0;i<sizeof(builtins)/sizeof(builtins[0]);++i)
        if (strlen(builtins[i].name)==len && memcmp(name,builtins[i].name,len)==0) return builtins[i].id;
    return 0;
}

static int parse_expression(Expr *e, int min_prec);

static int expect(Expr *e, TokenKind kind, const char *message) {
    if (e->lexer.token.kind != kind) {
        set_error(e->compiler, message);
        return 0;
    }
    lex_next(&e->lexer);
    return 1;
}

static int parse_primary(Expr *e) {
    Compiler *c = e->compiler;
    Token token = e->lexer.token;
    int slot;
    if (token.kind == TK_NUM) {
        int ci = add_const(c, token.is_float ? mval_f64(token.number) : mval_i64((int64_t)token.number));
        lex_next(&e->lexer);
        return ci >= 0 && emit(c, MOP_PUSH_CONST, ci, 0, 0) >= 0;
    }
    if (token.kind == TK_STR) {
        int ci = add_const(c, owned_string(token.start, token.len));
        lex_next(&e->lexer);
        return ci >= 0 && emit(c, MOP_PUSH_CONST, ci, 0, 0) >= 0;
    }
    if (token_is(&token, "true") || token_is(&token, "false") || token_is(&token, "none")) {
        MValue v = token_is(&token, "none") ? mval_none() : mval_bool(token_is(&token, "true"));
        int ci = add_const(c, v);
        lex_next(&e->lexer);
        return ci >= 0 && emit(c, MOP_PUSH_CONST, ci, 0, 0) >= 0;
    }
    if (token.kind == TK_MINUS || token_is(&token, "not")) {
        int is_not = token_is(&token, "not");
        lex_next(&e->lexer);
        if (is_not) return parse_primary(e) && emit(c, MOP_BOOL_NOT, 0, 0, 0) >= 0;
        {
            int zero = add_const(c, mval_i64(0));
            if (emit(c, MOP_PUSH_CONST, zero, 0, 0) < 0 || !parse_primary(e)) return 0;
            return emit(c, MOP_SUB, 0, 0, 0) >= 0;
        }
    }
    if (token.kind == TK_LP) {
        lex_next(&e->lexer);
        if (!parse_expression(e, 0)) return 0;
        return expect(e, TK_RP, "expected ')'");
    }
    if (token.kind == TK_LB) {
        int count = 0;
        lex_next(&e->lexer);
        while (e->lexer.token.kind != TK_RB && e->lexer.token.kind != TK_EOF) {
            if (!parse_expression(e, 0)) return 0;
            count++;
            if (e->lexer.token.kind != TK_COMMA) break;
            lex_next(&e->lexer);
        }
        if (!expect(e, TK_RB, "expected ']'")) return 0;
        return emit(c, MOP_BUILD_LIST, count, 0, 0) >= 0;
    }
    if (token.kind == TK_LC) {
        int count = 0;
        lex_next(&e->lexer);
        while (e->lexer.token.kind != TK_RC && e->lexer.token.kind != TK_EOF) {
            if (!parse_expression(e, 0) || !expect(e, TK_COLON, "expected ':' in map") ||
                !parse_expression(e, 0)) return 0;
            count++;
            if (e->lexer.token.kind != TK_COMMA) break;
            lex_next(&e->lexer);
        }
        if (!expect(e, TK_RC, "expected '}'")) return 0;
        return emit(c, MOP_BUILD_MAP, count, 0, 0) >= 0;
    }
    if (token.kind == TK_ID) {
        lex_next(&e->lexer);
        if (e->lexer.token.kind == TK_LP) {
            int argc = 0, id = builtin_id(token.start, token.len);
            Function *fn = find_function(c, token.start, token.len);
            lex_next(&e->lexer);
            while (e->lexer.token.kind != TK_RP && e->lexer.token.kind != TK_EOF) {
                if (!parse_expression(e, 0)) return 0;
                argc++;
                if (e->lexer.token.kind != TK_COMMA) break;
                lex_next(&e->lexer);
            }
            if (!expect(e, TK_RP, "expected ')' after arguments")) return 0;
            if (id) return emit(c, MOP_SYSCALL, id, argc, id == 1 ? 0 : 1) >= 0;
            if (!fn) { set_error(c, "unknown function"); return 0; }
            if (emit(c, MOP_PUSH_CONST, fn->const_slot, 0, 0) < 0) return 0;
            return emit(c, MOP_CALL, argc, 0, 0) >= 0;
        }
        slot = scope_find(c->scope, token.start, token.len);
        if (slot < 0 && c->scope != &c->globals) slot = scope_find(&c->globals, token.start, token.len);
        if (slot < 0) { set_error(c, "unknown variable"); return 0; }
        if (emit(c, MOP_LOAD_LOCAL, slot, 0, 0) < 0) return 0;
        while (e->lexer.token.kind == TK_LB) {
            lex_next(&e->lexer);
            if (!parse_expression(e, 0) || !expect(e, TK_RB, "expected ']' after index")) return 0;
            if (emit(c, MOP_GETITEM, 0, 0, 0) < 0) return 0;
        }
        return 1;
    }
    set_error(c, "expected expression");
    return 0;
}

static int precedence(Token *t) {
    if (token_is(t, "or")) return 1;
    if (token_is(t, "and")) return 2;
    if (t->kind==TK_EQ||t->kind==TK_NE||t->kind==TK_LT||t->kind==TK_LE||t->kind==TK_GT||t->kind==TK_GE) return 3;
    if (t->kind==TK_PLUS||t->kind==TK_MINUS) return 4;
    if (t->kind==TK_STAR||t->kind==TK_SLASH||t->kind==TK_PERCENT) return 5;
    return -1;
}

static int parse_expression(Expr *e, int min_prec) {
    Compiler *c = e->compiler;
    if (!parse_primary(e)) return 0;
    for (;;) {
        Token op = e->lexer.token;
        int prec = precedence(&op), opcode = -1, cmp = 0;
        if (prec < min_prec) break;
        lex_next(&e->lexer);
        if (!parse_expression(e, prec + 1)) return 0;
        if (op.kind==TK_PLUS) opcode=MOP_ADD; else if(op.kind==TK_MINUS) opcode=MOP_SUB;
        else if(op.kind==TK_STAR) opcode=MOP_MUL; else if(op.kind==TK_SLASH) opcode=MOP_DIV;
        else if(op.kind==TK_PERCENT) opcode=MOP_MOD; else if(token_is(&op,"and")) opcode=MOP_BOOL_AND;
        else if(token_is(&op,"or")) opcode=MOP_BOOL_OR;
        else {
            opcode=MOP_COMPARE;
            if(op.kind==TK_EQ)cmp=MCMP_EQ; else if(op.kind==TK_NE)cmp=MCMP_NE;
            else if(op.kind==TK_LT)cmp=MCMP_LT; else if(op.kind==TK_LE)cmp=MCMP_LE;
            else if(op.kind==TK_GT)cmp=MCMP_GT; else cmp=MCMP_GE;
        }
        if (emit(c, opcode, cmp, 0, 0) < 0) return 0;
    }
    return 1;
}

static int compile_expr(Compiler *c, const char *text) {
    Expr e;
    e.compiler = c;
    e.lexer.cur = text;
    e.lexer.line = c->current_line;
    lex_next(&e.lexer);
    return parse_expression(&e, 0);
}

static const char *trim(char *text) {
    while (*text && isspace((unsigned char)*text)) text++;
    return text;
}

static int starts(const char *text, const char *prefix) {
    size_t n = strlen(prefix);
    return strncmp(text, prefix, n) == 0;
}

static int find_assignment(const char *text) {
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
    if (!*text || starts(text,"//") || *text=='#') { (*position)++; return 1; }
    if (starts(text,"def ")) {
        Function *fn=NULL; int i;
        for(i=0;i<c->func_count;++i)if(c->funcs[i].line_start==*position){fn=&c->funcs[i];break;}
        *position=fn?fn->line_end:*position+1;
        return 1;
    }
    if (starts(text,"if ") && text[strlen(text)-1]==':') {
        int jump_false, jump_end=-1;
        text[strlen(text)-1]='\0';
        if(!compile_expr(c,text+3))return 0;
        jump_false=emit(c,MOP_JUMP_IF_FALSE,0,0,0);
        (*position)++;
        if(!compile_block(c,position,end,indent+4))return 0;
        if(*position<end && c->lines[*position].indent==indent && starts(trim(c->lines[*position].text),"else:")){
            jump_end=emit(c,MOP_JUMP,0,0,0);
            c->code[jump_false].a=(int32_t)c->code_len;
            (*position)++;
            if(!compile_block(c,position,end,indent+4))return 0;
            c->code[jump_end].a=(int32_t)c->code_len;
        } else c->code[jump_false].a=(int32_t)c->code_len;
        return 1;
    }
    if (starts(text,"while ") && text[strlen(text)-1]==':') {
        int loop=(int)c->code_len, jf;
        text[strlen(text)-1]='\0';
        if(!compile_expr(c,text+6))return 0;
        jf=emit(c,MOP_JUMP_IF_FALSE,0,0,0);
        (*position)++;
        if(!compile_block(c,position,end,indent+4))return 0;
        emit(c,MOP_JUMP,loop,0,0);
        c->code[jf].a=(int32_t)c->code_len;
        return 1;
    }
    if (starts(text,"for ") && text[strlen(text)-1]==':') {
        char name[64], start_expr[256], stop_expr[256];
        int slot, stop_slot, loop, jf;
        if(sscanf(text,"for %63s in range(%255[^,],%255[^)]):",name,start_expr,stop_expr)!=3){
            set_error(c,"expected for name in range(start, stop):");return 0;
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
        emit(c,MOP_LOAD_LOCAL,slot,0,0);
        {int one=add_const(c,mval_i64(1));emit(c,MOP_PUSH_CONST,one,0,0);}
        emit(c,MOP_ADD,0,0,0);emit(c,MOP_STORE_LOCAL,slot,0,0);emit(c,MOP_JUMP,loop,0,0);
        c->code[jf].a=(int32_t)c->code_len;
        return 1;
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
    else if(starts(text,"keep "))text=(char*)trim(text+5);
    assign=find_assignment(text);
    if(assign>=0){
        char name[64];const char *expr;
        size_t n=(size_t)assign;
        while(n&&isspace((unsigned char)text[n-1]))n--;
        snprintf(name,sizeof(name),"%.*s",(int)n,text);
        expr=trim(text+assign+1);
        if(!compile_expr(c,expr))return 0;
        {
            int slot=scope_slot(c->scope,name,strlen(name),1);
            if(slot<0||emit(c,MOP_STORE_LOCAL,slot,0,0)<0)return 0;
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
