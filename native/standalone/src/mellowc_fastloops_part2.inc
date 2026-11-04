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

