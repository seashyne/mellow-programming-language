/* Mellow standalone compiler: loop-shape recognizers and their fast emitters.
 *
 * Included by mellowc.c between the shared scanner helpers and the statement
 * dispatcher. Each emit_fast_*_loop() inspects one while-loop body shape and,
 * when it matches, emits a single fused bytecode instruction instead of the
 * generic sequence. Adding a shape here means adding a MOP_* opcode and a
 * matching executor in mellowrt_core.c; nothing outside mellowc.c needs to
 * know these functions exist, so the file is included, not compiled.
 */

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
