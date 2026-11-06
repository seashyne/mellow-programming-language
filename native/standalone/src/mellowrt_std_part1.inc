/* Standard-library fragment 1: shared value, text, and equality helpers. */

static int std_values_equal(const MValue *a, const MValue *b);
static int std_list_append(MValue *list, MValue item);
static int std_map_set(MValue *map, MValue key, MValue value);

static int std_error(MellowRuntimeContext *ctx, const char *message) {
    if (ctx) snprintf(ctx->syscall_error, sizeof(ctx->syscall_error), "%s", message);
    return 0;
}

/* Deep copy that always owns plain calloc memory, so the result can be freed
 * or grown by host functions without touching the VM heap. */
static MValue std_clone(const MValue *src) {
    MValue out = mval_none();
    size_t i;
    if (!src) return out;
    switch (src->tag) {
    case MVAL_STR:
        return mval_owned_copy(src->as.str.ptr, src->as.str.len);
    case MVAL_BYTES: {
        MValue bytes = mval_owned_copy(src->as.str.ptr, src->as.str.len);
        bytes.tag = MVAL_BYTES;
        return bytes;
    }
    case MVAL_LIST:
        if (!ai_list_new(&out, src->as.list.len)) return mval_none();
        for (i = 0; i < src->as.list.len; ++i)
            if (!std_list_append(&out, std_clone(&src->as.list.items[i]))) return out;
        return out;
    case MVAL_MAP:
        if (!ai_map_new(&out, src->as.map.len)) return mval_none();
        for (i = 0; i < src->as.map.len; ++i) {
            if (!std_map_set(&out, std_clone(&src->as.map.keys[i]),
                             std_clone(&src->as.map.values[i]))) return out;
        }
        return out;
    default:
        return *src;
    }
}

static int std_values_equal(const MValue *a, const MValue *b) {
    size_t i, j;
    if (!a || !b) return a == b;
    if ((a->tag == MVAL_I64 || a->tag == MVAL_F64 || a->tag == MVAL_BOOL) &&
        (b->tag == MVAL_I64 || b->tag == MVAL_F64 || b->tag == MVAL_BOOL)) {
        double x, y;
        if (a->tag == MVAL_I64 && b->tag == MVAL_I64) return a->as.i64 == b->as.i64;
        if (!ai_number(a, &x) || !ai_number(b, &y)) return 0;
        return x == y;
    }
    if (a->tag != b->tag) return 0;
    switch (a->tag) {
    case MVAL_NONE:
        return 1;
    case MVAL_STR:
        return a->as.str.len == b->as.str.len &&
               (!a->as.str.len || (a->as.str.ptr && b->as.str.ptr &&
                                   memcmp(a->as.str.ptr, b->as.str.ptr, a->as.str.len) == 0));
    case MVAL_LIST:
        if (a->as.list.len != b->as.list.len) return 0;
        for (i = 0; i < a->as.list.len; ++i)
            if (!std_values_equal(&a->as.list.items[i], &b->as.list.items[i])) return 0;
        return 1;
    case MVAL_MAP:
        if (a->as.map.len != b->as.map.len) return 0;
        for (i = 0; i < a->as.map.len; ++i) {
            int found = 0;
            for (j = 0; j < b->as.map.len; ++j) {
                if (!std_values_equal(&a->as.map.keys[i], &b->as.map.keys[j])) continue;
                if (!std_values_equal(&a->as.map.values[i], &b->as.map.values[j])) return 0;
                found = 1;
                break;
            }
            if (!found) return 0;
        }
        return 1;
    default:
        return a->as.i64 == b->as.i64;
    }
}

static int std_list_append(MValue *list, MValue item) {
    size_t next;
    MValue *grown;
    if (!list || list->tag != MVAL_LIST) return 0;
    if (list->as.list.len == list->as.list.cap) {
        next = list->as.list.cap ? list->as.list.cap * 2 : 8;
        grown = (MValue *)realloc(list->as.list.items, next * sizeof(MValue));
        if (!grown) return 0;
        memset(grown + list->as.list.cap, 0, (next - list->as.list.cap) * sizeof(MValue));
        list->as.list.items = grown;
        list->as.list.cap = next;
    }
    list->as.list.items[list->as.list.len++] = item;
    return 1;
}

/* Replace or insert a map entry with an arbitrary key value. */
static int std_map_set(MValue *map, MValue key, MValue value) {
    size_t i, next;
    MValue *keys, *values;
    if (!map || map->tag != MVAL_MAP) return 0;
    for (i = 0; i < map->as.map.len; ++i) {
        if (!std_values_equal(&map->as.map.keys[i], &key)) continue;
        mvalue_free(&map->as.map.keys[i]);
        mvalue_free(&map->as.map.values[i]);
        map->as.map.keys[i] = key;
        map->as.map.values[i] = value;
        return 1;
    }
    if (map->as.map.len == map->as.map.cap) {
        next = map->as.map.cap ? map->as.map.cap * 2 : 8;
        keys = (MValue *)realloc(map->as.map.keys, next * sizeof(MValue));
        if (!keys) return 0;
        map->as.map.keys = keys;
        values = (MValue *)realloc(map->as.map.values, next * sizeof(MValue));
        if (!values) return 0;
        map->as.map.values = values;
        memset(keys + map->as.map.cap, 0, (next - map->as.map.cap) * sizeof(MValue));
        memset(values + map->as.map.cap, 0, (next - map->as.map.cap) * sizeof(MValue));
        map->as.map.cap = next;
    }
    map->as.map.keys[map->as.map.len] = key;
    map->as.map.values[map->as.map.len] = value;
    map->as.map.len++;
    return 1;
}

/* str(value): a top-level string stays raw, containers use repr spelling. */
static char *std_text(const MValue *value, size_t *out_len) {
    return ai_value_text(value, out_len);
}

static MValue std_own_text(const char *text, size_t len) {
    return mval_owned_copy(text, len);
}

/* to_str()/tostr(): Mellow spelling with lowercase none/true/false. */
static char *std_mellow_text(const MValue *value, size_t *out_len) {
    char scratch[64];
    AiTextBuf buf;
    int written;
    MValue owned;
    if (!value) return ai_value_text(NULL, out_len);
    if (value->tag == MVAL_STR) {
        owned = std_own_text(value->as.str.ptr, value->as.str.len);
        if (out_len) *out_len = value->as.str.len;
        return (char *)owned.as.str.ptr;
    }
    memset(&buf, 0, sizeof(buf));
    switch (value->tag) {
    case MVAL_NONE:
        written = snprintf(scratch, sizeof(scratch), "none");
        break;
    case MVAL_BOOL:
        written = snprintf(scratch, sizeof(scratch), "%s", value->as.boolean ? "true" : "false");
        break;
    case MVAL_F64:
        if (isfinite(value->as.f64) && value->as.f64 == (double)(int64_t)value->as.f64 &&
            value->as.f64 >= -9.0e18 && value->as.f64 <= 9.0e18)
            written = snprintf(scratch, sizeof(scratch), "%lld", (long long)(int64_t)value->as.f64);
        else
            written = snprintf(scratch, sizeof(scratch), "%g", value->as.f64);
        break;
    default:
        return ai_value_text(value, out_len);
    }
    if (written < 0 || !ai_text_append(&buf, scratch, (size_t)written)) {
        free(buf.ptr);
        if (out_len) *out_len = 0;
        return NULL;
    }
    if (out_len) *out_len = buf.len;
    return buf.ptr;
}

static long std_find_sub(const char *hay, size_t hay_len, const char *needle,
                         size_t needle_len, size_t from) {
    size_t i;
    if (!needle_len) return (long)(from <= hay_len ? from : hay_len);
    if (!hay || !needle || needle_len > hay_len || from > hay_len) return -1;
    for (i = from; i + needle_len <= hay_len; ++i)
        if (memcmp(hay + i, needle, needle_len) == 0) return (long)i;
    return -1;
}

static int std_space(char c) {
    return c == ' ' || c == '\t' || c == '\n' || c == '\r' || c == '\f' || c == '\v';
}
