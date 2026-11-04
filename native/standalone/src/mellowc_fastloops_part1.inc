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

