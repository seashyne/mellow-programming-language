/* std.data fragment 4: row transforms and syscall dispatch. */

static int std_data_order(const MValue *left, const MValue *right, int *cmp) {
    if ((left->tag == MVAL_I64 || left->tag == MVAL_F64 || left->tag == MVAL_BOOL) &&
        (right->tag == MVAL_I64 || right->tag == MVAL_F64 || right->tag == MVAL_BOOL)) {
        if (left->tag == MVAL_I64 && right->tag == MVAL_I64)
            *cmp = left->as.i64 < right->as.i64 ? -1 : (left->as.i64 > right->as.i64 ? 1 : 0);
        else {
            double a, b;
            if (!ai_number(left, &a) || !ai_number(right, &b)) return 0;
            *cmp = a < b ? -1 : (a > b ? 1 : 0);
        }
        return 1;
    }
    if (left->tag == MVAL_STR && right->tag == MVAL_STR) {
        size_t n = left->as.str.len < right->as.str.len ? left->as.str.len : right->as.str.len;
        int order = n ? memcmp(left->as.str.ptr, right->as.str.ptr, n) : 0;
        if (!order) order = left->as.str.len < right->as.str.len ? -1
                                : (left->as.str.len > right->as.str.len ? 1 : 0);
        *cmp = order < 0 ? -1 : (order > 0 ? 1 : 0);
        return 1;
    }
    if (left->tag == MVAL_LIST && right->tag == MVAL_LIST) {
        size_t i, n = left->as.list.len < right->as.list.len ? left->as.list.len
                                                             : right->as.list.len;
        for (i = 0; i < n; ++i) {
            int part;
            if (!std_data_order(&left->as.list.items[i], &right->as.list.items[i], &part)) return 0;
            if (part) { *cmp = part; return 1; }
        }
        *cmp = left->as.list.len < right->as.list.len ? -1
                  : (left->as.list.len > right->as.list.len ? 1 : 0);
        return 1;
    }
    return 0;
}

static int std_data_contains(const MValue *haystack, const MValue *needle, int *found) {
    size_t i;
    *found = 0;
    if (haystack->tag == MVAL_STR) {
        size_t n;
        if (needle->tag != MVAL_STR) return 0;
        n = needle->as.str.len;
        if (!n) { *found = 1; return 1; }
        if (haystack->as.str.len < n) return 1;
        for (i = 0; i + n <= haystack->as.str.len; ++i) {
            if (memcmp(haystack->as.str.ptr + i, needle->as.str.ptr, n) == 0) {
                *found = 1;
                return 1;
            }
        }
        return 1;
    }
    if (haystack->tag == MVAL_LIST) {
        for (i = 0; i < haystack->as.list.len; ++i)
            if (std_values_equal(&haystack->as.list.items[i], needle)) { *found = 1; return 1; }
        return 1;
    }
    if (haystack->tag == MVAL_MAP) {
        for (i = 0; i < haystack->as.map.len; ++i)
            if (std_values_equal(&haystack->as.map.keys[i], needle)) { *found = 1; return 1; }
        return 1;
    }
    return 1;
}

static int std_data_matches(MellowRuntimeContext *ctx, const MValue *row,
                            const char *key, const char *op, const MValue *expected,
                            int *matched) {
    const MValue *actual;
    MValue missing = mval_none();
    int order = 0, found = 0;
    *matched = 0;
    if (row->tag != MVAL_MAP) return 1;
    actual = ai_map_get(row, key);
    if (!actual) actual = &missing;
    if (!strcmp(op, "==")) *matched = std_values_equal(actual, expected);
    else if (!strcmp(op, "!=")) *matched = !std_values_equal(actual, expected);
    else if (!strcmp(op, ">") || !strcmp(op, ">=") || !strcmp(op, "<") || !strcmp(op, "<=")) {
        if (!std_data_order(actual, expected, &order))
            return std_data_error(ctx, "data.where comparison failed");
        if (!strcmp(op, ">")) *matched = order > 0;
        else if (!strcmp(op, ">=")) *matched = order >= 0;
        else if (!strcmp(op, "<")) *matched = order < 0;
        else *matched = order <= 0;
    } else if (!strcmp(op, "contains")) {
        if (!std_data_contains(actual, expected, &found))
            return std_data_error(ctx, "data.where comparison failed");
        *matched = found;
    } else {
        return std_data_error(ctx, "unsupported data.where operator: %s", op);
    }
    return 1;
}

static int std_data_project_syscall(MellowRuntimeContext *ctx, const MValue *args,
                                    size_t argc, MValue *out) {
    const MValue *rows, *fields;
    MValue result = mval_none();
    size_t i, j;
    if (argc < 2) return std_data_error(ctx, "data.project expects rows and field-name list");
    rows = &args[0];
    fields = &args[1];
    if (rows->tag != MVAL_LIST || fields->tag != MVAL_LIST)
        return std_data_error(ctx, "data.project expects rows and field-name list");
    if (!ai_list_new(&result, rows->as.list.len)) return 0;
    for (i = 0; i < rows->as.list.len; ++i) {
        const MValue *row = &rows->as.list.items[i];
        MValue projected = mval_none();
        if (row->tag != MVAL_MAP) continue;
        if (!ai_map_new(&projected, fields->as.list.len)) { mvalue_free(&result); return 0; }
        for (j = 0; j < fields->as.list.len; ++j) {
            char *name = std_text(&fields->as.list.items[j], NULL);
            const MValue *value;
            if (!name) { mvalue_free(&projected); mvalue_free(&result); return 0; }
            value = ai_map_get(row, name);
            if (!std_map_set(&projected, ai_str(name),
                             value ? std_clone(value) : mval_none())) {
                free(name);
                mvalue_free(&projected);
                mvalue_free(&result);
                return 0;
            }
            free(name);
        }
        std_list_append(&result, projected);
    }
    *out = result;
    return 1;
}

static int std_data_where_syscall(MellowRuntimeContext *ctx, const MValue *args,
                                  size_t argc, MValue *out) {
    const MValue *rows;
    MValue result = mval_none();
    char *key, *op;
    size_t i;
    if (argc < 4) return std_data_error(ctx, "data.where expects a row list");
    rows = &args[0];
    if (rows->tag != MVAL_LIST) return std_data_error(ctx, "data.where expects a row list");
    key = std_text(&args[1], NULL);
    op = std_text(&args[2], NULL);
    if (!key || !op) { free(key); free(op); return 0; }
    if (!ai_list_new(&result, rows->as.list.len)) { free(key); free(op); return 0; }
    for (i = 0; i < rows->as.list.len; ++i) {
        int matched = 0;
        if (!std_data_matches(ctx, &rows->as.list.items[i], key, op, &args[3], &matched)) {
            free(key);
            free(op);
            mvalue_free(&result);
            return 0;
        }
        if (matched) std_list_append(&result, std_clone(&rows->as.list.items[i]));
    }
    free(key);
    free(op);
    *out = result;
    return 1;
}

static int std_data_sum_syscall(MellowRuntimeContext *ctx, const MValue *args,
                                size_t argc, MValue *out) {
    const MValue *rows;
    char *key;
    int64_t total_int = 0;
    double total_float = 0.0;
    int is_float = 0;
    size_t i;
    if (argc < 2) return std_data_error(ctx, "data.sum expects a row list");
    rows = &args[0];
    if (rows->tag != MVAL_LIST) return std_data_error(ctx, "data.sum expects a row list");
    key = std_text(&args[1], NULL);
    if (!key) return 0;
    for (i = 0; i < rows->as.list.len; ++i) {
        const MValue *row = &rows->as.list.items[i];
        const MValue *value;
        if (row->tag != MVAL_MAP) continue;
        value = ai_map_get(row, key);
        if (!value) continue;
        if (value->tag == MVAL_I64 || value->tag == MVAL_BOOL) {
            int64_t part = value->tag == MVAL_BOOL ? (value->as.boolean ? 1 : 0) : value->as.i64;
            if (is_float) total_float += (double)part;
            else total_int += part;
        } else if (value->tag == MVAL_F64) {
            if (!is_float) { total_float = (double)total_int; is_float = 1; }
            total_float += value->as.f64;
        } else {
            free(key);
            return std_data_error(ctx, "data.sum expects numeric values");
        }
    }
    free(key);
    *out = is_float ? mval_f64(total_float) : mval_i64(total_int);
    return 1;
}

static int std_data_syscall(MellowRuntimeContext *ctx, int id, const MValue *args,
                            size_t argc, MValue *out) {
    switch (id) {
    case 360: return std_data_open_syscall(ctx, args, argc, DATA_KIND_JSONL, out);
    case 361: return std_data_open_syscall(ctx, args, argc, DATA_KIND_CSV, out);
    case 362: return std_data_next_syscall(ctx, args, argc, out);
    case 363:
    case 364: return std_data_close_syscall(ctx, args, argc, out);
    case 365: return std_data_info_syscall(ctx, args, argc, out);
    case 366: return std_data_project_syscall(ctx, args, argc, out);
    case 367: return std_data_where_syscall(ctx, args, argc, out);
    case 368: return std_data_sum_syscall(ctx, args, argc, out);
    default: return 0;
    }
}
