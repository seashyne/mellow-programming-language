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
