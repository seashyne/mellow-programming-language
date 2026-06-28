#include "mellowc_internal.h"

#include <ctype.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

void lex_next(Lexer *l) {
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
        l->token.is_float = memchr(start, '.', l->token.len) != NULL ||
                            memchr(start, 'e', l->token.len) != NULL ||
                            memchr(start, 'E', l->token.len) != NULL;
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

int token_is(Token *t, const char *text) {
    size_t n = strlen(text);
    return t->kind == TK_ID && t->len == n && memcmp(t->start, text, n) == 0;
}

int parse_integer_literal(const Token *token, int64_t *result) {
    uint64_t value = 0;
    const uint64_t limit = (uint64_t)INT64_MAX;
    size_t i;
    for (i = 0; i < token->len; ++i) {
        uint64_t digit = (uint64_t)(token->start[i] - '0');
        if (value > (limit - digit) / 10u) return 0;
        value = value * 10u + digit;
    }
    *result = (int64_t)value;
    return 1;
}
