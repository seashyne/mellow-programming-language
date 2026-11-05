/* Standard-library fragment 4: std.list (value semantics, returns new lists). */

static int std_numeric_pair(const MValue *a, const MValue *b, double *x, double *y) {
    if ((a->tag == MVAL_I64 || a->tag == MVAL_F64) &&
        (b->tag == MVAL_I64 || b->tag == MVAL_F64)) {
        return ai_number(a, x) && ai_number(b, y);
    }
    return 0;
}

static double std_sort_key(const MValue *value, char **text, size_t *len) {
    double number;
    if ((value->tag == MVAL_I64 || value->tag == MVAL_F64) && ai_number(value, &number)) {
        *text = NULL;
        *len = 0;
        return number;
    }
    *text = std_text(value, len);
    return 0.0;
}

static int std_sort_cmp(const MValue *a, const MValue *b) {
    double x, y;
    char *ta = NULL, *tb = NULL;
    size_t la = 0, lb = 0;
    int result = 0;
    if (std_numeric_pair(a, b, &x, &y)) return x < y ? -1 : (x > y ? 1 : 0);
    std_sort_key(a, &ta, &la);
    std_sort_key(b, &tb, &lb);
    if (ta && tb) {
        size_t n = la < lb ? la : lb;
        result = n ? memcmp(ta, tb, n) : 0;
        if (result == 0) result = la < lb ? -1 : (la > lb ? 1 : 0);
    }
    free(ta); free(tb);
    return result;
}

static int std_list_sort_syscall(const MValue *args, size_t argc, MValue *out, int reverse) {
    MValue copy;
    size_t i, j;
    if (argc < 1 || argc > 2 || args[0].tag != MVAL_LIST) return 0;
    copy = std_clone(&args[0]);
    if (copy.tag != MVAL_LIST) return 0;
    if (argc == 2) reverse = ai_truthy(&args[1]);
    for (i = 1; i < copy.as.list.len; ++i) {
        MValue item = copy.as.list.items[i];
        j = i;
        while (j > 0) {
            int order = std_sort_cmp(&copy.as.list.items[j - 1], &item);
            if (reverse ? order < 0 : order > 0) {
                copy.as.list.items[j] = copy.as.list.items[j - 1];
                --j;
            } else break;
        }
        copy.as.list.items[j] = item;
    }
    *out = copy;
    return 1;
}

static int std_list_push_syscall(const MValue *args, size_t argc, MValue *out) {
    MValue copy;
    if (argc != 2 || args[0].tag != MVAL_LIST) return 0;
    copy = std_clone(&args[0]);
    if (!std_list_append(&copy, std_clone(&args[1]))) { mvalue_free(&copy); return 0; }
    *out = copy;
    return 1;
}

static int std_list_pop_syscall(const MValue *args, size_t argc, MValue *out) {
    const MValue *list;
    if (argc != 1 || args[0].tag != MVAL_LIST) return 0;
    list = &args[0];
    *out = list->as.list.len ? std_clone(&list->as.list.items[list->as.list.len - 1]) : mval_none();
    return 1;
}

static int std_list_insert_syscall(const MValue *args, size_t argc, MValue *out) {
    MValue copy;
    size_t index, i;
    int64_t raw = 0;
    if (argc != 3 || args[0].tag != MVAL_LIST || !ai_integer(&args[1], &raw)) return 0;
    copy = std_clone(&args[0]);
    index = raw < 0 ? 0 : (size_t)raw;
    if (index > copy.as.list.len) index = copy.as.list.len;
    if (!std_list_append(&copy, mval_none())) { mvalue_free(&copy); return 0; }
    for (i = copy.as.list.len - 1; i > index; --i)
        copy.as.list.items[i] = copy.as.list.items[i - 1];
    copy.as.list.items[index] = std_clone(&args[2]);
    *out = copy;
    return 1;
}

static int std_list_remove_syscall(const MValue *args, size_t argc, MValue *out) {
    MValue copy;
    size_t i, found = (size_t)-1;
    if (argc != 2 || args[0].tag != MVAL_LIST) return 0;
    copy = std_clone(&args[0]);
    for (i = 0; i < copy.as.list.len; ++i) {
        if (std_values_equal(&copy.as.list.items[i], &args[1])) { found = i; break; }
    }
    if (found != (size_t)-1) {
        mvalue_free(&copy.as.list.items[found]);
        for (i = found; i + 1 < copy.as.list.len; ++i)
            copy.as.list.items[i] = copy.as.list.items[i + 1];
        copy.as.list.items[--copy.as.list.len] = mval_none();
    }
    *out = copy;
    return 1;
}

static int std_list_has_syscall(const MValue *args, size_t argc, MValue *out) {
    size_t i;
    if (argc != 2 || args[0].tag != MVAL_LIST) return 0;
    for (i = 0; i < args[0].as.list.len; ++i)
        if (std_values_equal(&args[0].as.list.items[i], &args[1])) {
            *out = mval_bool(1);
            return 1;
        }
    *out = mval_bool(0);
    return 1;
}

static int std_list_find_syscall(const MValue *args, size_t argc, MValue *out) {
    size_t i;
    if (argc != 2 || args[0].tag != MVAL_LIST) return 0;
    for (i = 0; i < args[0].as.list.len; ++i)
        if (std_values_equal(&args[0].as.list.items[i], &args[1])) {
            *out = mval_i64((int64_t)i);
            return 1;
        }
    *out = mval_i64(-1);
    return 1;
}

static int std_list_count_syscall(const MValue *args, size_t argc, MValue *out) {
    size_t i, count = 0;
    if (argc != 2 || args[0].tag != MVAL_LIST) return 0;
    for (i = 0; i < args[0].as.list.len; ++i)
        if (std_values_equal(&args[0].as.list.items[i], &args[1])) ++count;
    *out = mval_i64((int64_t)count);
    return 1;
}

static int std_list_slice_syscall(const MValue *args, size_t argc, MValue *out) {
    const MValue *list;
    int64_t start = 0, end = 0;
    size_t i;
    if (argc < 2 || argc > 3 || args[0].tag != MVAL_LIST) return 0;
    list = &args[0];
    if (!ai_integer(&args[1], &start)) return 0;
    end = (int64_t)list->as.list.len;
    if (argc == 3 && !ai_integer(&args[2], &end)) return 0;
    if (start < 0) start += (int64_t)list->as.list.len;
    if (end < 0) end += (int64_t)list->as.list.len;
    if (start < 0) start = 0;
    if (start > (int64_t)list->as.list.len) start = (int64_t)list->as.list.len;
    if (end < start) end = start;
    if (end > (int64_t)list->as.list.len) end = (int64_t)list->as.list.len;
    if (!ai_list_new(out, (size_t)(end - start))) return 0;
    for (i = (size_t)start; i < (size_t)end; ++i)
        std_list_append(out, std_clone(&list->as.list.items[i]));
    return 1;
}

static int std_list_reverse_syscall(const MValue *args, size_t argc, MValue *out) {
    const MValue *list;
    size_t i;
    if (argc != 1 || args[0].tag != MVAL_LIST) return 0;
    list = &args[0];
    if (!ai_list_new(out, list->as.list.len)) return 0;
    for (i = list->as.list.len; i > 0; --i)
        std_list_append(out, std_clone(&list->as.list.items[i - 1]));
    return 1;
}

static int std_list_any_syscall(const MValue *args, size_t argc, MValue *out, int want_all) {
    const MValue *list;
    size_t i;
    int result = want_all ? 1 : 0;
    if (argc != 1 || args[0].tag != MVAL_LIST) return 0;
    list = &args[0];
    for (i = 0; i < list->as.list.len; ++i) {
        int truth = ai_truthy(&list->as.list.items[i]);
        if (want_all && !truth) { result = 0; break; }
        if (!want_all && truth) { result = 1; break; }
    }
    *out = mval_bool(result);
    return 1;
}

static int std_list_extend_syscall(const MValue *args, size_t argc, MValue *out) {
    size_t i;
    if (argc != 2 || args[0].tag != MVAL_LIST) return 0;
    *out = std_clone(&args[0]);
    if (args[1].tag == MVAL_LIST) {
        for (i = 0; i < args[1].as.list.len; ++i)
            std_list_append(out, std_clone(&args[1].as.list.items[i]));
    } else if (args[1].tag == MVAL_STR) {
        size_t pos = 0, len = args[1].as.str.len;
        int32_t cp;
        while (pos < len && ai_utf8_decode(args[1].as.str.ptr, len, &pos, &cp)) {
            char bytes[4];
            int n = ai_utf8_encode(cp, bytes);
            std_list_append(out, mval_owned_copy(bytes, (size_t)(n > 0 ? n : 0)));
        }
    }
    return 1;
}

static int std_list_enumerate_syscall(const MValue *args, size_t argc, MValue *out) {
    size_t i;
    if (argc != 1) return 0;
    if (!ai_list_new(out, 8)) return 0;
    if (args[0].tag == MVAL_LIST) {
        for (i = 0; i < args[0].as.list.len; ++i) {
            MValue pair;
            ai_list_new(&pair, 2);
            std_list_append(&pair, mval_i64((int64_t)i));
            std_list_append(&pair, std_clone(&args[0].as.list.items[i]));
            std_list_append(out, pair);
        }
    } else if (args[0].tag == MVAL_STR) {
        size_t pos = 0, len = args[0].as.str.len;
        int32_t cp;
        while (pos < len && ai_utf8_decode(args[0].as.str.ptr, len, &pos, &cp)) {
            MValue pair;
            char bytes[4];
            int n = ai_utf8_encode(cp, bytes);
            ai_list_new(&pair, 2);
            std_list_append(&pair, mval_i64((int64_t)(out->as.list.len)));
            std_list_append(&pair, mval_owned_copy(bytes, (size_t)(n > 0 ? n : 0)));
            std_list_append(out, pair);
        }
    }
    return 1;
}

static int std_list_zip_syscall(const MValue *args, size_t argc, MValue *out) {
    size_t i, j, rows = argc, shortest = (size_t)-1;
    if (argc < 2) return 0;
    for (i = 0; i < rows; ++i) {
        if (args[i].tag != MVAL_LIST) return 0;
        if (args[i].as.list.len < shortest) shortest = args[i].as.list.len;
    }
    if (!ai_list_new(out, shortest)) return 0;
    for (j = 0; j < shortest; ++j) {
        MValue row;
        ai_list_new(&row, rows);
        for (i = 0; i < rows; ++i)
            std_list_append(&row, std_clone(&args[i].as.list.items[j]));
        std_list_append(out, row);
    }
    return 1;
}

static int std_list_syscall(MellowRuntimeContext *ctx, int id, const MValue *args,
                            size_t argc, MValue *out) {
    (void)ctx;
    switch (id) {
    case 220: return std_list_push_syscall(args, argc, out);
    case 221: return std_list_pop_syscall(args, argc, out);
    case 222:
        if (argc != 1 || args[0].tag != MVAL_LIST) return 0;
        *out = mval_i64((int64_t)args[0].as.list.len);
        return 1;
    case 223: return std_list_insert_syscall(args, argc, out);
    case 224: return std_list_remove_syscall(args, argc, out);
    case 225: return std_list_has_syscall(args, argc, out);
    case 226: return std_list_sort_syscall(args, argc, out, 0);
    case 229: return std_list_find_syscall(args, argc, out);
    case 230: return std_list_slice_syscall(args, argc, out);
    case 231: return std_list_reverse_syscall(args, argc, out);
    case 233: return std_list_count_syscall(args, argc, out);
    case 234: return std_list_enumerate_syscall(args, argc, out);
    case 235: return std_list_zip_syscall(args, argc, out);
    case 236: return std_list_sort_syscall(args, argc, out, 0);
    case 237: return std_list_reverse_syscall(args, argc, out);
    case 238: return std_list_any_syscall(args, argc, out, 0);
    case 239: return std_list_any_syscall(args, argc, out, 1);
    case 240: return std_list_extend_syscall(args, argc, out);
    case 241:
        if (argc != 2 || args[0].tag != MVAL_LIST) return 0;
        *out = std_clone(&args[0]);
        std_list_append(out, std_clone(&args[1]));
        return 1;
    default:
        break;
    }
    return 0;
}
