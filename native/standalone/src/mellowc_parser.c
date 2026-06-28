#include "mellowc_internal.h"

#include <math.h>
#include <string.h>

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
        int ci;
        MValue value;
        if (token.is_float) {
            if (!isfinite(token.number)) {
                set_error(c, "numeric literal is not finite");
                return 0;
            }
            value = mval_f64(token.number);
        } else {
            int64_t integer;
            if (!parse_integer_literal(&token, &integer)) {
                set_error(c, "integer literal is outside the signed 64-bit range");
                return 0;
            }
            value = mval_i64(integer);
        }
        ci = add_const(c, value);
        lex_next(&e->lexer);
        return ci >= 0 && emit(c, MOP_PUSH_CONST, ci, 0, 0) >= 0;
    }
    if (token.kind == TK_STR) {
        int ci = add_const(c, owned_string(token.start, token.len));
        lex_next(&e->lexer);
        return ci >= 0 && emit(c, MOP_PUSH_CONST, ci, 0, 0) >= 0;
    }
    if (token_is(&token, "true") || token_is(&token, "false") || token_is(&token, "none") || token_is(&token, "null")) {
        MValue v = (token_is(&token, "none") || token_is(&token, "null")) ? mval_none() : mval_bool(token_is(&token, "true"));
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
        if (token_is(&token, "get") || token_is(&token, "call")) {
            Token target = e->lexer.token;
            int argc = 0, id;
            if (target.kind != TK_ID || !memchr(target.start, '.', target.len)) {
                set_error(c, "expected module.function after get");
                return 0;
            }
            id = resolve_builtin_id(c, target.start, target.len);
            if (!id) {
                set_error(c, "unknown native module function");
                return 0;
            }
            lex_next(&e->lexer);
            if (e->lexer.token.kind == TK_LP) {
                lex_next(&e->lexer);
                while (e->lexer.token.kind != TK_RP && e->lexer.token.kind != TK_EOF) {
                    if (!parse_expression(e, 0)) return 0;
                    argc++;
                    if (e->lexer.token.kind != TK_COMMA) break;
                    lex_next(&e->lexer);
                }
                if (!expect(e, TK_RP, "expected ')' after arguments")) return 0;
            }
            return emit(c, MOP_SYSCALL, id, argc, 1) >= 0;
        }
        if (e->lexer.token.kind == TK_LP) {
            int argc = 0, id = resolve_builtin_id(c, token.start, token.len);
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
        if (slot < 0 && c->scope != &c->globals) slot = scope_slot(&c->globals, token.start, token.len, 1);
        if (slot < 0) {
            Function *fn = find_function(c, token.start, token.len);
            if (fn) return emit(c, MOP_PUSH_CONST, fn->const_slot, 0, 0) >= 0;
        }
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

int compile_expr(Compiler *c, const char *text) {
    Expr e;
    e.compiler = c;
    e.lexer.cur = text;
    e.lexer.line = c->current_line;
    lex_next(&e.lexer);
    return parse_expression(&e, 0);
}
