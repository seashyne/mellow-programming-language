/* AI runtime fragment 1: value builders, text decoding, and small file helpers. */

static MValue ai_str(const char *text) {
    size_t n = text ? strlen(text) : 0;
    return mval_owned_copy(text ? text : "", n);
}

static MValue ai_strn(const char *text, size_t n) {
    return mval_owned_copy(text ? text : "", n);
}

static int ai_list_new(MValue *out, size_t cap) {
    *out = mval_none();
    out->tag = MVAL_LIST;
    out->as.list.len = 0;
    out->as.list.cap = cap;
    out->as.list.items = cap ? (MValue *)calloc(cap, sizeof(MValue)) : NULL;
    return cap == 0 || out->as.list.items != NULL;
}

static int ai_list_push(MValue *list, MValue item) {
    if (!list || list->tag != MVAL_LIST || list->as.list.len >= list->as.list.cap) return 0;
    list->as.list.items[list->as.list.len++] = item;
    return 1;
}

static int ai_map_new(MValue *out, size_t cap) {
    *out = mval_none();
    out->tag = MVAL_MAP;
    out->as.map.len = 0;
    out->as.map.cap = cap;
    out->as.map.keys = cap ? (MValue *)calloc(cap, sizeof(MValue)) : NULL;
    out->as.map.values = cap ? (MValue *)calloc(cap, sizeof(MValue)) : NULL;
    return cap == 0 || (out->as.map.keys != NULL && out->as.map.values != NULL);
}

static int ai_map_put(MValue *map, const char *key, MValue value) {
    if (!map || map->tag != MVAL_MAP || map->as.map.len >= map->as.map.cap) return 0;
    map->as.map.keys[map->as.map.len] = ai_str(key);
    map->as.map.values[map->as.map.len] = value;
    map->as.map.len++;
    return 1;
}

static int ai_map_put_str(MValue *map, const char *key, const char *text) {
    return ai_map_put(map, key, ai_str(text));
}

static const MValue *ai_map_get(const MValue *map, const char *key) {
    size_t i;
    size_t n = strlen(key);
    if (!map || map->tag != MVAL_MAP) return NULL;
    for (i = 0; i < map->as.map.len; ++i) {
        const MValue *k = &map->as.map.keys[i];
        if (k->tag == MVAL_STR && k->as.str.len == n && k->as.str.ptr &&
            memcmp(k->as.str.ptr, key, n) == 0)
            return &map->as.map.values[i];
    }
    return NULL;
}

static int ai_number(const MValue *value, double *out) {
    if (!value) return 0;
    if (value->tag == MVAL_I64) { *out = (double)value->as.i64; return 1; }
    if (value->tag == MVAL_F64 && isfinite(value->as.f64)) { *out = value->as.f64; return 1; }
    if (value->tag == MVAL_BOOL) { *out = value->as.boolean ? 1.0 : 0.0; return 1; }
    return 0;
}

static int ai_integer(const MValue *value, int64_t *out) {
    if (!value) return 0;
    if (value->tag == MVAL_I64) { *out = value->as.i64; return 1; }
    if (value->tag == MVAL_F64 && isfinite(value->as.f64) &&
        value->as.f64 >= -9.0e18 && value->as.f64 <= 9.0e18) {
        *out = (int64_t)value->as.f64;
        return 1;
    }
    return 0;
}

static double ai_num_or(const MValue *value, double fallback) {
    double d;
    return ai_number(value, &d) ? d : fallback;
}

static int64_t ai_int_or(const MValue *value, int64_t fallback) {
    int64_t i;
    return ai_integer(value, &i) ? i : fallback;
}

static int ai_truthy(const MValue *value) {
    if (!value) return 0;
    switch (value->tag) {
    case MVAL_NONE: return 0;
    case MVAL_BOOL: return value->as.boolean != 0;
    case MVAL_I64: return value->as.i64 != 0;
    case MVAL_F64: return value->as.f64 != 0.0;
    case MVAL_STR: return value->as.str.len != 0;
    case MVAL_LIST: return value->as.list.len != 0;
    case MVAL_MAP: return value->as.map.len != 0;
    default: return 1;
    }
}

/* Text view of a scalar argument, as str(value) would print it. Caller frees. */
typedef struct {
    char *ptr;
    size_t len;
    size_t cap;
} AiTextBuf;

static int ai_text_reserve(AiTextBuf *buf, size_t extra) {
    size_t need = buf->len + extra + 1;
    size_t next;
    char *grown;
    if (need <= buf->cap) return 1;
    next = buf->cap ? buf->cap : 32;
    while (next < need) next *= 2;
    grown = (char *)realloc(buf->ptr, next);
    if (!grown) return 0;
    buf->ptr = grown;
    buf->cap = next;
    return 1;
}

static int ai_text_append(AiTextBuf *buf, const char *text, size_t n) {
    if (!ai_text_reserve(buf, n)) return 0;
    if (n && text) memcpy(buf->ptr + buf->len, text, n);
    buf->len += n;
    buf->ptr[buf->len] = '\0';
    return 1;
}

/* Quote a string the way Python's repr() does, so str(list) agrees across engines. */
static int ai_text_quote(AiTextBuf *buf, const MValue *value) {
    size_t i;
    if (!ai_text_append(buf, "'", 1)) return 0;
    for (i = 0; i < value->as.str.len; ++i) {
        char c = value->as.str.ptr[i];
        const char *escape = NULL;
        if (c == '\\') escape = "\\\\";
        else if (c == '\'') escape = "\\'";
        else if (c == '\n') escape = "\\n";
        else if (c == '\r') escape = "\\r";
        else if (c == '\t') escape = "\\t";
        if (escape) { if (!ai_text_append(buf, escape, 2)) return 0; }
        else if (!ai_text_append(buf, &c, 1)) return 0;
    }
    return ai_text_append(buf, "'", 1);
}

static int ai_render_value(AiTextBuf *buf, const MValue *value, int depth, int nested) {
    char scratch[64];
    size_t i;
    int written;
    if (!value) return 1;
    if (value->tag == MVAL_STR)
        return nested ? ai_text_quote(buf, value)
                      : ai_text_append(buf, value->as.str.ptr ? value->as.str.ptr : "", value->as.str.len);
    switch (value->tag) {
    case MVAL_NONE:
        return ai_text_append(buf, "None", 4);
    case MVAL_BOOL:
        return ai_text_append(buf, value->as.boolean ? "True" : "False", value->as.boolean ? 4 : 5);
    case MVAL_I64:
        written = snprintf(scratch, sizeof(scratch), "%lld", (long long)value->as.i64);
        break;
    case MVAL_F64:
        written = snprintf(scratch, sizeof(scratch), "%g", value->as.f64);
        break;
    case MVAL_LIST:
        if (depth > 8) return ai_text_append(buf, "...", 3);
        if (!ai_text_append(buf, "[", 1)) return 0;
        for (i = 0; i < value->as.list.len; ++i) {
            if (i && !ai_text_append(buf, ", ", 2)) return 0;
            if (!ai_render_value(buf, &value->as.list.items[i], depth + 1, 1)) return 0;
        }
        return ai_text_append(buf, "]", 1);
    case MVAL_MAP:
        if (depth > 8) return ai_text_append(buf, "...", 3);
        if (!ai_text_append(buf, "{", 1)) return 0;
        for (i = 0; i < value->as.map.len; ++i) {
            if (i && !ai_text_append(buf, ", ", 2)) return 0;
            if (!ai_render_value(buf, &value->as.map.keys[i], depth + 1, 1)) return 0;
            if (!ai_text_append(buf, ": ", 2)) return 0;
            if (!ai_render_value(buf, &value->as.map.values[i], depth + 1, 1)) return 0;
        }
        return ai_text_append(buf, "}", 1);
    default:
        written = snprintf(scratch, sizeof(scratch), "<%s>", mvalue_tag_name(value->tag));
        break;
    }
    return written > 0 && ai_text_append(buf, scratch, (size_t)written);
}

static char *ai_value_text(const MValue *value, size_t *out_len) {
    AiTextBuf buf;
    memset(&buf, 0, sizeof(buf));
    if (!ai_render_value(&buf, value, 0, 0) || !buf.ptr) {
        free(buf.ptr);
        if (out_len) *out_len = 0;
        return NULL;
    }
    if (out_len) *out_len = buf.len;
    return buf.ptr;
}
