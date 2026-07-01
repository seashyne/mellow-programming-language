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
    scope->i64_list_len[scope->len] = 0;
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

static uint16_t expr_i64_list_literal_len(const char *expr) {
    const char *p = skip_spaces(expr);
    uint16_t count = 0;
    if (*p != '[') return 0;
    p = skip_spaces(p + 1);
    if (*p == ']') return 0;
    while (*p) {
        char *endp = NULL;
        (void)strtoll(p, &endp, 10);
        if (endp == p) return 0;
        if (count == UINT16_MAX) return 0;
        count++;
        p = skip_spaces(endp);
        if (*p == ',') {
            p = skip_spaces(p + 1);
            continue;
        }
        if (*p == ']') {
            p = skip_spaces(p + 1);
            return *p == '\0' ? count : 0;
        }
        return 0;
    }
    return 0;
}

static int parse_i64_lt_condition(Compiler *c, const char *condition, int *left_slot_out, int *right_slot_out) {
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
    *left_slot_out = left_slot;
    *right_slot_out = right_slot;
    return 1;
}

static int emit_fast_i64_lt_jump(Compiler *c, const char *condition, int *jump_index) {
    int left_slot, right_slot;
    if (!parse_i64_lt_condition(c, condition, &left_slot, &right_slot)) return 0;
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

static char *normalized_line_copy(SourceLine *line) {
    char *copy = copy_text(line->text, strlen(line->text));
    char *trimmed;
    if (!copy) return NULL;
    strip_inline_comment(copy);
    trimmed = (char *)trim(copy);
    if (trimmed != copy) memmove(copy, trimmed, strlen(trimmed) + 1);
    return copy;
}

static int parse_assignment_parts(const char *text, char *lhs, size_t lhs_cap, const char **expr_out) {
    int assign = find_assignment(text);
    size_t n;
    if (assign < 0) return 0;
    n = (size_t)assign;
    while (n && isspace((unsigned char)text[n-1])) n--;
    if (!n || n >= lhs_cap) return 0;
    memcpy(lhs, text, n);
    lhs[n] = '\0';
    *expr_out = trim((char *)text + assign + 1);
    return 1;
}

static int parse_self_plus_ident(const char *lhs, const char *expr, char *rhs, size_t rhs_cap) {
    const char *p = skip_spaces(expr);
    int left_len = ident_len_at(p), rhs_len;
    if (!left_len || strlen(lhs) != (size_t)left_len || memcmp(lhs, p, (size_t)left_len) != 0) return 0;
    p = skip_spaces(p + left_len);
    if (*p != '+') return 0;
    p = skip_spaces(p + 1);
    rhs_len = ident_len_at(p);
    if (!rhs_len || rhs_len >= (int)rhs_cap) return 0;
    memcpy(rhs, p, (size_t)rhs_len);
    rhs[rhs_len] = '\0';
    p = skip_spaces(p + rhs_len);
    return *p == '\0';
}

static int parse_self_plus_list_mod(
    Compiler *c,
    const char *lhs,
    const char *expr,
    int expected_idx_slot,
    int *list_slot_out,
    int *mod_out
) {
    const char *p = skip_spaces(expr);
    int left_len = ident_len_at(p), list_len, idx_len;
    char list_name[64], idx_name[64];
    int list_slot, idx_slot;
    char *endp = NULL;
    long long mod_value;
    if (!left_len || strlen(lhs) != (size_t)left_len || memcmp(lhs, p, (size_t)left_len) != 0) return 0;
    p = skip_spaces(p + left_len);
    if (*p != '+') return 0;
    p = skip_spaces(p + 1);
    list_len = ident_len_at(p);
    if (!list_len || list_len >= (int)sizeof(list_name)) return 0;
    memcpy(list_name, p, (size_t)list_len); list_name[list_len] = '\0';
    list_slot = scope_find(c->scope, list_name, strlen(list_name));
    if (list_slot < 0) return 0;
    p = skip_spaces(p + list_len);
    if (*p != '[') return 0;
    p = skip_spaces(p + 1);
    idx_len = ident_len_at(p);
    if (!idx_len || idx_len >= (int)sizeof(idx_name)) return 0;
    memcpy(idx_name, p, (size_t)idx_len); idx_name[idx_len] = '\0';
    idx_slot = scope_find(c->scope, idx_name, strlen(idx_name));
    if (idx_slot != expected_idx_slot) return 0;
    p = skip_spaces(p + idx_len);
    if (*p != '%') return 0;
    p = skip_spaces(p + 1);
    mod_value = strtoll(p, &endp, 10);
    if (endp == p || mod_value <= 0 || mod_value > 65535) return 0;
    p = skip_spaces(endp);
    if (*p != ']') return 0;
    p = skip_spaces(p + 1);
    if (*p != '\0') return 0;
    *list_slot_out = list_slot;
    *mod_out = (int)mod_value;
    return 1;
}

static int parse_self_plus_one(const char *lhs, const char *expr) {
    const char *p = skip_spaces(expr);
    int left_len = ident_len_at(p);
    char *endp = NULL;
    long long delta;
    if (!left_len || strlen(lhs) != (size_t)left_len || memcmp(lhs, p, (size_t)left_len) != 0) return 0;
    p = skip_spaces(p + left_len);
    if (*p != '+') return 0;
    p = skip_spaces(p + 1);
    delta = strtoll(p, &endp, 10);
    return endp != p && *skip_spaces(endp) == '\0' && delta == 1;
}

static int parse_self_plus_const(const char *lhs, const char *expr, long long expected) {
    const char *p = skip_spaces(expr);
    int left_len = ident_len_at(p);
    char *endp = NULL;
    long long delta;
    if (!left_len || strlen(lhs) != (size_t)left_len || memcmp(lhs, p, (size_t)left_len) != 0) return 0;
    p = skip_spaces(p + left_len);
    if (*p != '+') return 0;
    p = skip_spaces(p + 1);
    delta = strtoll(p, &endp, 10);
    return endp != p && *skip_spaces(endp) == '\0' && delta == expected;
}

static int parse_call_two_idents(
    const char *expr,
    char *fn_name,
    size_t fn_cap,
    char *arg0,
    size_t arg0_cap,
    char *arg1,
    size_t arg1_cap
) {
    const char *p = skip_spaces(expr);
    int fn_len = ident_len_at(p);
    int arg0_len, arg1_len;
    if (!fn_len || fn_len >= (int)fn_cap) return 0;
    memcpy(fn_name, p, (size_t)fn_len); fn_name[fn_len] = '\0';
    p = skip_spaces(p + fn_len);
    if (*p != '(') return 0;
    p = skip_spaces(p + 1);
    arg0_len = ident_len_at(p);
    if (!arg0_len || arg0_len >= (int)arg0_cap) return 0;
    memcpy(arg0, p, (size_t)arg0_len); arg0[arg0_len] = '\0';
    p = skip_spaces(p + arg0_len);
    if (*p != ',') return 0;
    p = skip_spaces(p + 1);
    arg1_len = ident_len_at(p);
    if (!arg1_len || arg1_len >= (int)arg1_cap) return 0;
    memcpy(arg1, p, (size_t)arg1_len); arg1[arg1_len] = '\0';
    p = skip_spaces(p + arg1_len);
    if (*p != ')') return 0;
    p = skip_spaces(p + 1);
    return *p == '\0';
}

static int function_returns_param_sum(Compiler *c, Function *fn) {
    int count = 0;
    char *body = NULL;
    const char *expr;
    const char *p;
    int left_len, right_len;
    if (!fn || fn->arity != 2) return 0;
    for (int i = fn->line_start + 1; i < fn->line_end; ++i) {
        char *copy;
        copy = normalized_line_copy(&c->lines[i]);
        if (!copy) return 0;
        if (*copy) {
            if (c->lines[i].indent != fn->body_indent) { free(copy); free(body); return 0; }
            if (count++) { free(copy); free(body); return 0; }
            body = copy;
        } else {
            free(copy);
        }
    }
    if (!body || !starts(body, "return ")) { free(body); return 0; }
    expr = skip_spaces(body + 7);
    p = skip_spaces(expr);
    left_len = ident_len_at(p);
    if (!left_len || strlen(fn->params[0]) != (size_t)left_len || memcmp(p, fn->params[0], (size_t)left_len) != 0) { free(body); return 0; }
    p = skip_spaces(p + left_len);
    if (*p != '+') { free(body); return 0; }
    p = skip_spaces(p + 1);
    right_len = ident_len_at(p);
    if (!right_len || strlen(fn->params[1]) != (size_t)right_len || memcmp(p, fn->params[1], (size_t)right_len) != 0) { free(body); return 0; }
    p = skip_spaces(p + right_len);
    if (*p) { free(body); return 0; }
    free(body);
    return 1;
}

static int parse_self_plus_string_literal(Compiler *c, const char *lhs, const char *expr, int *const_slot_out) {
    const char *p = skip_spaces(expr);
    int left_len = ident_len_at(p);
    char quote;
    const char *start;
    size_t len;
    int ci;
    if (!left_len || strlen(lhs) != (size_t)left_len || memcmp(lhs, p, (size_t)left_len) != 0) return 0;
    p = skip_spaces(p + left_len);
    if (*p != '+') return 0;
    p = skip_spaces(p + 1);
    if (*p != '"' && *p != '\'') return 0;
    quote = *p++;
    start = p;
    while (*p && *p != quote) {
        if (*p == '\\') return 0;
        p++;
    }
    if (*p != quote) return 0;
    len = (size_t)(p - start);
    p = skip_spaces(p + 1);
    if (*p) return 0;
    ci = add_const(c, owned_string(start, len));
    if (ci < 0 || ci > 65535) return -1;
    *const_slot_out = ci;
    return 1;
}

static int parse_mod2_eq_zero_condition(Compiler *c, const char *condition, int expected_idx_slot) {
    const char *p = skip_spaces(condition);
    int idx_len = ident_len_at(p), idx_slot;
    char idx[64];
    char *endp = NULL;
    long long mod_value, eq_value;
    if (!idx_len || idx_len >= (int)sizeof(idx)) return 0;
    memcpy(idx, p, (size_t)idx_len); idx[idx_len] = '\0';
    idx_slot = scope_find(c->scope, idx, strlen(idx));
    if (idx_slot != expected_idx_slot) return 0;
    p = skip_spaces(p + idx_len);
    if (*p != '%') return 0;
    p = skip_spaces(p + 1);
    mod_value = strtoll(p, &endp, 10);
    if (endp == p || mod_value != 2) return 0;
    p = skip_spaces(endp);
    if (p[0] != '=' || p[1] != '=') return 0;
    p = skip_spaces(p + 2);
    eq_value = strtoll(p, &endp, 10);
    return endp != p && eq_value == 0 && *skip_spaces(endp) == '\0';
}

static int emit_fast_i64_sum_loop(Compiler *c, int *position, int end, int indent, const char *condition) {
    int idx_slot, limit_slot, body_start, body_end, count = 0;
    int body_indices[2];
    char *line0 = NULL, *line1 = NULL;
    char lhs0[64], lhs1[64], rhs0[64];
    const char *expr0, *expr1;
    int acc_slot;

    if (!parse_i64_lt_condition(c, condition, &idx_slot, &limit_slot)) return 0;
    body_start = *position + 1;
    body_end = body_start;
    while (body_end < end && c->lines[body_end].indent > indent) body_end++;
    for (int i = body_start; i < body_end; ++i) {
        char *copy;
        if (c->lines[i].indent != indent + 4) return 0;
        copy = normalized_line_copy(&c->lines[i]);
        if (!copy) return -1;
        if (*copy) {
            if (count >= 2) { free(copy); return 0; }
            body_indices[count++] = i;
        }
        free(copy);
    }
    if (count != 2) return 0;

    line0 = normalized_line_copy(&c->lines[body_indices[0]]);
    line1 = normalized_line_copy(&c->lines[body_indices[1]]);
    if (!line0 || !line1) { free(line0); free(line1); return -1; }
    if (!parse_assignment_parts(line0, lhs0, sizeof(lhs0), &expr0) ||
        !parse_assignment_parts(line1, lhs1, sizeof(lhs1), &expr1) ||
        !parse_self_plus_ident(lhs0, expr0, rhs0, sizeof(rhs0)) ||
        !parse_self_plus_one(lhs1, expr1)) {
        free(line0); free(line1); return 0;
    }
    if (scope_find(c->scope, lhs1, strlen(lhs1)) != idx_slot ||
        scope_find(c->scope, rhs0, strlen(rhs0)) != idx_slot) {
        free(line0); free(line1); return 0;
    }
    acc_slot = scope_find(c->scope, lhs0, strlen(lhs0));
    if (acc_slot < 0 || !c->scope->is_i64[acc_slot]) {
        free(line0); free(line1); return 0;
    }
    free(line0); free(line1);
    if (emit(c, MOP_I64_SUM_RANGE_STEP1, acc_slot, idx_slot, limit_slot) < 0) return -1;
    *position = body_end;
    return 1;
}

static int emit_fast_i64_branch_mod2_loop(Compiler *c, int *position, int end, int indent, const char *condition) {
    int idx_slot, limit_slot, body_start, body_end, count = 0;
    int body_indices[5];
    char *lines[5] = {0};
    char lhs_true[64], lhs_false[64], lhs_inc[64];
    const char *expr_true, *expr_false, *expr_inc;
    int acc_slot, ok = 0;

    if (!parse_i64_lt_condition(c, condition, &idx_slot, &limit_slot)) return 0;
    body_start = *position + 1;
    body_end = body_start;
    while (body_end < end && c->lines[body_end].indent > indent) body_end++;
    for (int i = body_start; i < body_end; ++i) {
        char *copy;
        if (c->lines[i].indent != indent + 4 && c->lines[i].indent != indent + 8) return 0;
        copy = normalized_line_copy(&c->lines[i]);
        if (!copy) return -1;
        if (*copy) {
            if (count >= 5) { free(copy); return 0; }
            body_indices[count] = i;
            lines[count++] = copy;
        } else {
            free(copy);
        }
    }
    if (count != 5) goto done;
    if (c->lines[body_indices[0]].indent != indent + 4 ||
        c->lines[body_indices[1]].indent != indent + 8 ||
        c->lines[body_indices[2]].indent != indent + 4 ||
        c->lines[body_indices[3]].indent != indent + 8 ||
        c->lines[body_indices[4]].indent != indent + 4) goto done;
    if (!starts(lines[0], "if ") || lines[0][strlen(lines[0])-1] != ':' ||
        strcmp(lines[2], "else:") != 0) goto done;
    lines[0][strlen(lines[0])-1] = '\0';
    if (!parse_mod2_eq_zero_condition(c, trim(lines[0] + 3), idx_slot)) goto done;
    if (!parse_assignment_parts(lines[1], lhs_true, sizeof(lhs_true), &expr_true) ||
        !parse_assignment_parts(lines[3], lhs_false, sizeof(lhs_false), &expr_false) ||
        !parse_assignment_parts(lines[4], lhs_inc, sizeof(lhs_inc), &expr_inc)) goto done;
    if (strcmp(lhs_true, lhs_false) != 0) goto done;
    acc_slot = scope_find(c->scope, lhs_true, strlen(lhs_true));
    if (acc_slot < 0 || !c->scope->is_i64[acc_slot]) goto done;
    if (!parse_self_plus_const(lhs_true, expr_true, 3) ||
        !parse_self_plus_const(lhs_false, expr_false, 1) ||
        scope_find(c->scope, lhs_inc, strlen(lhs_inc)) != idx_slot ||
        !parse_self_plus_one(lhs_inc, expr_inc)) goto done;
    if (emit(c, MOP_I64_BRANCH_MOD2_ACCUM_STEP1, acc_slot, idx_slot, limit_slot) < 0) { ok = -1; goto done; }
    *position = body_end;
    ok = 1;

done:
    for (int i = 0; i < count; ++i) free(lines[i]);
    return ok;
}

static int emit_fast_i64_list_mod_loop(Compiler *c, int *position, int end, int indent, const char *condition) {
    int idx_slot, limit_slot, body_start, body_end, count = 0;
    int body_indices[2];
    char *line0 = NULL, *line1 = NULL;
    char lhs0[64], lhs1[64];
    const char *expr0, *expr1;
    int acc_slot, list_slot, mod_value;
    int packed;

    if (!parse_i64_lt_condition(c, condition, &idx_slot, &limit_slot)) return 0;
    body_start = *position + 1;
    body_end = body_start;
    while (body_end < end && c->lines[body_end].indent > indent) body_end++;
    for (int i = body_start; i < body_end; ++i) {
        char *copy;
        if (c->lines[i].indent != indent + 4) return 0;
        copy = normalized_line_copy(&c->lines[i]);
        if (!copy) return -1;
        if (*copy) {
            if (count >= 2) { free(copy); return 0; }
            body_indices[count++] = i;
        }
        free(copy);
    }
    if (count != 2) return 0;

    line0 = normalized_line_copy(&c->lines[body_indices[0]]);
    line1 = normalized_line_copy(&c->lines[body_indices[1]]);
    if (!line0 || !line1) { free(line0); free(line1); return -1; }
    if (!parse_assignment_parts(line0, lhs0, sizeof(lhs0), &expr0) ||
        !parse_assignment_parts(line1, lhs1, sizeof(lhs1), &expr1) ||
        !parse_self_plus_list_mod(c, lhs0, expr0, idx_slot, &list_slot, &mod_value) ||
        scope_find(c->scope, lhs1, strlen(lhs1)) != idx_slot ||
        !parse_self_plus_one(lhs1, expr1)) {
        free(line0); free(line1); return 0;
    }
    acc_slot = scope_find(c->scope, lhs0, strlen(lhs0));
    if (acc_slot < 0 || !c->scope->is_i64[acc_slot]) {
        free(line0); free(line1); return 0;
    }
    if (c->scope->i64_list_len[list_slot] != (uint16_t)mod_value) {
        free(line0); free(line1); return 0;
    }
    if (limit_slot < 0 || limit_slot > 65535 || list_slot < 0 || list_slot > 65535 || mod_value <= 0) {
        free(line0); free(line1); return 0;
    }
    /* The runtime validates the list value and item tags. */
    packed = ((limit_slot & 0xffff) << 16) | (list_slot & 0xffff);
    free(line0); free(line1);
    if (emit(c, MOP_I64_LIST_MOD_ACCUM_STEP1, acc_slot, idx_slot, packed) < 0) return -1;
    *position = body_end;
    return 1;
}

static int emit_fast_i64_add_func_loop(Compiler *c, int *position, int end, int indent, const char *condition) {
    int idx_slot, limit_slot, body_start, body_end, count = 0;
    int body_indices[2];
    char *line0 = NULL, *line1 = NULL;
    char lhs0[64], lhs1[64], fn_name[64], arg0[64], arg1[64];
    const char *expr0, *expr1;
    int acc_slot, arg0_slot, arg1_slot;
    Function *fn;

    if (!parse_i64_lt_condition(c, condition, &idx_slot, &limit_slot)) return 0;
    body_start = *position + 1;
    body_end = body_start;
    while (body_end < end && c->lines[body_end].indent > indent) body_end++;
    for (int i = body_start; i < body_end; ++i) {
        char *copy;
        if (c->lines[i].indent != indent + 4) return 0;
        copy = normalized_line_copy(&c->lines[i]);
        if (!copy) return -1;
        if (*copy) {
            if (count >= 2) { free(copy); return 0; }
            body_indices[count++] = i;
        }
        free(copy);
    }
    if (count != 2) return 0;

    line0 = normalized_line_copy(&c->lines[body_indices[0]]);
    line1 = normalized_line_copy(&c->lines[body_indices[1]]);
    if (!line0 || !line1) { free(line0); free(line1); return -1; }
    if (!parse_assignment_parts(line0, lhs0, sizeof(lhs0), &expr0) ||
        !parse_assignment_parts(line1, lhs1, sizeof(lhs1), &expr1) ||
        !parse_call_two_idents(expr0, fn_name, sizeof(fn_name), arg0, sizeof(arg0), arg1, sizeof(arg1)) ||
        scope_find(c->scope, lhs1, strlen(lhs1)) != idx_slot ||
        !parse_self_plus_one(lhs1, expr1)) {
        free(line0); free(line1); return 0;
    }
    acc_slot = scope_find(c->scope, lhs0, strlen(lhs0));
    arg0_slot = scope_find(c->scope, arg0, strlen(arg0));
    arg1_slot = scope_find(c->scope, arg1, strlen(arg1));
    if (acc_slot < 0 || arg0_slot != acc_slot || arg1_slot != idx_slot ||
        !c->scope->is_i64[acc_slot] || !c->scope->is_i64[idx_slot]) {
        free(line0); free(line1); return 0;
    }
    fn = find_function(c, fn_name, strlen(fn_name));
    if (!function_returns_param_sum(c, fn)) {
        free(line0); free(line1); return 0;
    }
    free(line0); free(line1);
    if (emit(c, MOP_I64_ADD_FUNC_ACCUM_STEP1, acc_slot, idx_slot, limit_slot) < 0) return -1;
    *position = body_end;
    return 1;
}

static int emit_fast_string_append_loop(Compiler *c, int *position, int end, int indent, const char *condition) {
    int idx_slot, limit_slot, body_start, body_end, count = 0;
    int body_indices[2];
    char *line0 = NULL, *line1 = NULL;
    char lhs0[64], lhs1[64];
    const char *expr0, *expr1;
    int text_slot, const_slot, packed;

    if (!parse_i64_lt_condition(c, condition, &idx_slot, &limit_slot)) return 0;
    body_start = *position + 1;
    body_end = body_start;
    while (body_end < end && c->lines[body_end].indent > indent) body_end++;
    for (int i = body_start; i < body_end; ++i) {
        char *copy;
        if (c->lines[i].indent != indent + 4) return 0;
        copy = normalized_line_copy(&c->lines[i]);
        if (!copy) return -1;
        if (*copy) {
            if (count >= 2) { free(copy); return 0; }
            body_indices[count++] = i;
        }
        free(copy);
    }
    if (count != 2) return 0;

    line0 = normalized_line_copy(&c->lines[body_indices[0]]);
    line1 = normalized_line_copy(&c->lines[body_indices[1]]);
    if (!line0 || !line1) { free(line0); free(line1); return -1; }
    if (!parse_assignment_parts(line0, lhs0, sizeof(lhs0), &expr0) ||
        !parse_assignment_parts(line1, lhs1, sizeof(lhs1), &expr1) ||
        scope_find(c->scope, lhs1, strlen(lhs1)) != idx_slot ||
        !parse_self_plus_one(lhs1, expr1)) {
        free(line0); free(line1); return 0;
    }
    text_slot = scope_find(c->scope, lhs0, strlen(lhs0));
    if (text_slot < 0 || limit_slot < 0 || limit_slot > 65535) {
        free(line0); free(line1); return 0;
    }
    {
        int parsed = parse_self_plus_string_literal(c, lhs0, expr0, &const_slot);
        if (parsed <= 0) {
            free(line0); free(line1);
            return parsed;
        }
    }
    packed = ((limit_slot & 0xffff) << 16) | (const_slot & 0xffff);
    free(line0); free(line1);
    if (emit(c, MOP_STR_APPEND_REPEAT_STEP1, text_slot, idx_slot, packed) < 0) return -1;
    *position = body_end;
    return 1;
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
        int loop, jf, depth, fast_loop;
        text[strlen(text)-1]='\0';
        fast_loop = emit_fast_i64_branch_mod2_loop(c, position, end, indent, trim(text+6));
        if (fast_loop < 0) return 0;
        if (fast_loop) return 1;
        fast_loop = emit_fast_i64_list_mod_loop(c, position, end, indent, trim(text+6));
        if (fast_loop < 0) return 0;
        if (fast_loop) return 1;
        fast_loop = emit_fast_i64_add_func_loop(c, position, end, indent, trim(text+6));
        if (fast_loop < 0) return 0;
        if (fast_loop) return 1;
        fast_loop = emit_fast_string_append_loop(c, position, end, indent, trim(text+6));
        if (fast_loop < 0) return 0;
        if (fast_loop) return 1;
        fast_loop = emit_fast_i64_sum_loop(c, position, end, indent, trim(text+6));
        if (fast_loop < 0) return 0;
        if (fast_loop) return 1;
        loop=(int)c->code_len;
        depth=c->loop_depth++;
        c->loop_break_count[depth]=0;
        c->loop_continue_count[depth]=0;
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
                c->scope->i64_list_len[slot] = expr_i64_list_literal_len(expr);
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

static int line_module_is_builtin(const char *module) {
    return strcmp(module, "io") == 0 || strcmp(module, "sys") == 0 ||
           strcmp(module, "math") == 0 || strcmp(module, "time") == 0 ||
           strcmp(module, "gc") == 0 || strcmp(module, "thread") == 0 ||
           strcmp(module, "chan") == 0 || strcmp(module, "canvas") == 0 ||
           strcmp(module, "money") == 0 || strcmp(module, "server") == 0;
}

static int parse_import_module_name(const char *line, char *module, size_t module_cap) {
    char tmp[512];
    char *rest = NULL;
    char *as_pos = NULL;
    size_t module_len;
    if (!line || !module || module_cap == 0) return 0;
    snprintf(tmp, sizeof(tmp), "%s", line);
    strip_inline_comment(tmp);
    rest = (char *)trim(tmp);
    if (starts(rest, "import ")) rest = (char *)trim(rest + 7);
    else if (starts(rest, "use ")) rest = (char *)trim(rest + 4);
    else if (starts(rest, "need ")) rest = (char *)trim(rest + 5);
    else return 0;
    as_pos = strstr(rest, " as ");
    if (!as_pos) return 0;
    module_len = (size_t)(as_pos - rest);
    while (module_len && isspace((unsigned char)rest[module_len - 1])) module_len--;
    if (module_len >= module_cap) module_len = module_cap - 1;
    memcpy(module, rest, module_len);
    module[module_len] = '\0';
    if (module[0] && (module[0] == '"' || module[0] == '\'') && module[strlen(module) - 1] == module[0]) {
        size_t n = strlen(module);
        memmove(module, module + 1, n - 2);
        module[n - 2] = '\0';
    }
    if (strncmp(module, "pkg:", 4) == 0) memmove(module, module + 4, strlen(module + 4) + 1);
    return *module != '\0';
}

static char *read_text_file(const char *path) {
    FILE *f;
    long size;
    char *source;
    if (!path) return NULL;
    f = fopen(path, "rb");
    if (!f) return NULL;
    if (fseek(f, 0, SEEK_END) != 0) { fclose(f); return NULL; }
    size = ftell(f);
    if (size < 0) { fclose(f); return NULL; }
    if (fseek(f, 0, SEEK_SET) != 0) { fclose(f); return NULL; }
    source = (char *)calloc((size_t)size + 1u, 1u);
    if (!source) { fclose(f); return NULL; }
    if (fread(source, 1, (size_t)size, f) != (size_t)size) {
        free(source);
        fclose(f);
        return NULL;
    }
    fclose(f);
    return source;
}

static int path_already_imported(char imported[][1024], int imported_count, const char *path) {
    int i;
    for (i = 0; i < imported_count; ++i)
        if (strcmp(imported[i], path) == 0) return 1;
    return 0;
}

static int append_text(char **out, size_t *len, size_t *cap, const char *text) {
    size_t n = strlen(text);
    char *grown;
    if (*len + n + 2u > *cap) {
        size_t next = *cap ? *cap * 2u : 4096u;
        while (*len + n + 2u > next) next *= 2u;
        grown = (char *)realloc(*out, next);
        if (!grown) return 0;
        *out = grown;
        *cap = next;
    }
    memcpy(*out + *len, text, n);
    *len += n;
    if (*len == 0 || (*out)[*len - 1] != '\n') (*out)[(*len)++] = '\n';
    (*out)[*len] = '\0';
    return 1;
}

static int expand_package_imports_into(
    const char *source,
    const char *source_name,
    int depth,
    char imported[][1024],
    int *imported_count,
    char **out,
    size_t *out_len,
    size_t *out_cap
) {
    const char *p = source;
    const char *start = source;
    if (depth > 8) return 1;
    while (1) {
        if (*p == '\n' || *p == '\0') {
            size_t n = (size_t)(p - start);
            char line[512];
            char module[128];
            if (n >= sizeof(line)) n = sizeof(line) - 1;
            memcpy(line, start, n);
            line[n] = '\0';
            if (parse_import_module_name(line, module, sizeof(module)) && !line_module_is_builtin(module)) {
                char resolved[1024];
                if (mellowrt_resolve_package_entry(source_name, module, resolved, sizeof(resolved)) &&
                    !path_already_imported(imported, *imported_count, resolved) &&
                    *imported_count < 32) {
                    char *pkg_source;
                    snprintf(imported[*imported_count], 1024, "%s", resolved);
                    (*imported_count)++;
                    pkg_source = read_text_file(resolved);
                    if (pkg_source) {
                        if (!expand_package_imports_into(pkg_source, resolved, depth + 1, imported, imported_count, out, out_len, out_cap)) {
                            free(pkg_source);
                            return 0;
                        }
                        free(pkg_source);
                    }
                }
            }
            if (*p == '\0') break;
            start = p + 1;
        }
        p++;
    }
    return append_text(out, out_len, out_cap, source);
}

static char *expand_package_imports(const char *source, const char *source_name) {
    char imported[32][1024];
    int imported_count = 0;
    char *out = NULL;
    size_t out_len = 0, out_cap = 0;
    memset(imported, 0, sizeof(imported));
    if (!expand_package_imports_into(source, source_name, 0, imported, &imported_count, &out, &out_len, &out_cap)) {
        free(out);
        return NULL;
    }
    return out;
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
    char *expanded_source = NULL;
    memset(&c,0,sizeof(c));memset(out,0,sizeof(*out));
    c.error=error;c.error_cap=error_cap;c.scope=&c.globals;c.current_line=1;c.source_name=source_name;
    if(error&&error_cap)error[0]='\0';
    expanded_source = expand_package_imports(source, source_name ? source_name : "<memory>");
    if(!expanded_source){set_error(&c,"package import expansion failed");goto fail;}
    if(!split_lines(&c,expanded_source)||!scan_functions(&c))goto fail;
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
    free(expanded_source);
    return 1;
fail:
    for(i=0;i<c.line_count;++i)free(c.lines[i].text);
    free(c.lines);
    for(i=0;i<(int)c.const_len;++i)mvalue_free(&c.consts[i]);
    free(c.consts);free(c.code);free(c.spans);
    free(expanded_source);
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
