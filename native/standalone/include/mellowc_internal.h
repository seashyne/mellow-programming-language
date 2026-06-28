#ifndef MELLOWC_INTERNAL_H
#define MELLOWC_INTERNAL_H

#include "mellowrt.h"

#include <stddef.h>
#include <stdint.h>

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
    unsigned char is_i64[256];
    int len;
} Scope;

typedef struct {
    char alias[64];
    char module[32];
} ModuleAlias;

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
    ModuleAlias module_aliases[32];
    int module_alias_count;
    int loop_depth;
    int loop_breaks[32][64];
    int loop_break_count[32];
    int loop_continues[32][64];
    int loop_continue_count[32];
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

void set_error(Compiler *c, const char *message);
char *copy_text(const char *s, size_t n);
int emit(Compiler *c, int op, int a, int b, int d);
int add_const(Compiler *c, MValue value);
MValue owned_string(const char *s, size_t n);

void lex_next(Lexer *l);
int token_is(Token *t, const char *text);
int parse_integer_literal(const Token *token, int64_t *result);

int scope_find(Scope *scope, const char *name, size_t len);
int scope_slot(Scope *scope, const char *name, size_t len, int create);
Function *find_function(Compiler *c, const char *name, size_t len);

int resolve_builtin_id(Compiler *c, const char *name, size_t len);
int parse_import_statement(Compiler *c, const char *text);
int compile_expr(Compiler *c, const char *text);

const char *trim(char *text);
void strip_inline_comment(char *text);
int starts(const char *text, const char *prefix);
int find_assignment(const char *text);

#endif
