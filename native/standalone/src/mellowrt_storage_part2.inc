static void json_encode(Sbuf *b, const MValue *value, int depth) {
    size_t i;
    if (!b->ok || !value || depth > STOR_MAX_DEPTH) { b->ok = 0; return; }
    switch (value->tag) {
    case MVAL_NONE:
        sbuf_add_str(b, "null");
        break;
    case MVAL_BOOL:
        sbuf_add_str(b, value->as.boolean ? "true" : "false");
        break;
    case MVAL_I64:
    case MVAL_F64:
        json_encode_number(b, value);
        break;
    case MVAL_STR:
        sbuf_add_json_string(b, value->as.str.ptr, value->as.str.len);
        break;
    case MVAL_LIST:
        sbuf_add_char(b, '[');
        for (i = 0; i < value->as.list.len; ++i) {
            if (i) sbuf_add_str(b, ", ");
            json_encode(b, &value->as.list.items[i], depth + 1);
        }
        sbuf_add_char(b, ']');
        break;
    case MVAL_MAP:
        sbuf_add_char(b, '{');
        for (i = 0; i < value->as.map.len; ++i) {
            Sbuf key;
            if (i) sbuf_add_str(b, ", ");
            sbuf_init(&key);
            json_encode(&key, &value->as.map.keys[i], depth + 1);
            if (key.ok && key.buf && key.buf[0] == '"') sbuf_add_str(b, key.buf);
            else sbuf_add_json_string(b, key.buf ? key.buf : "", key.len);
            free(key.buf);
            sbuf_add_str(b, ": ");
            json_encode(b, &value->as.map.values[i], depth + 1);
        }
        sbuf_add_char(b, '}');
        break;
    default:
        sbuf_add_str(b, "null");
        break;
    }
}

/* ── json decode ───────────────────────────────────────────────── */

typedef struct {
    const char *text;
    size_t pos;
    size_t len;
    int failed;
} SJson;

typedef struct {
    MValue *items;
    size_t len;
    size_t cap;
} SVec;

static int svec_push(SVec *v, MValue value) {
    if (v->len == v->cap) {
        size_t cap = v->cap ? v->cap * 2 : 8;
        MValue *grown = (MValue *)realloc(v->items, cap * sizeof(MValue));
        if (!grown) return 0;
        v->items = grown;
        v->cap = cap;
    }
    v->items[v->len++] = value;
    return 1;
}

static void json_skip_space(SJson *p) {
    while (p->pos < p->len) {
        char c = p->text[p->pos];
        if (c == ' ' || c == '\t' || c == '\n' || c == '\r') p->pos++;
        else break;
    }
}

static MValue json_parse_value(SJson *p, int depth);

static int json_hex4(SJson *p, unsigned *out) {
    unsigned value = 0;
    int i;
    for (i = 0; i < 4; ++i) {
        char c;
        unsigned digit;
        if (p->pos >= p->len) return 0;
        c = p->text[p->pos++];
        if (c >= '0' && c <= '9') digit = (unsigned)(c - '0');
        else if (c >= 'a' && c <= 'f') digit = (unsigned)(c - 'a' + 10);
        else if (c >= 'A' && c <= 'F') digit = (unsigned)(c - 'A' + 10);
        else return 0;
        value = value * 16u + digit;
    }
    *out = value;
    return 1;
}

static void utf8_append(char *buf, size_t *len, unsigned codepoint) {
    if (codepoint < 0x80u) {
        buf[(*len)++] = (char)codepoint;
    } else if (codepoint < 0x800u) {
        buf[(*len)++] = (char)(0xC0u | (codepoint >> 6));
        buf[(*len)++] = (char)(0x80u | (codepoint & 0x3Fu));
    } else if (codepoint < 0x10000u) {
        buf[(*len)++] = (char)(0xE0u | (codepoint >> 12));
        buf[(*len)++] = (char)(0x80u | ((codepoint >> 6) & 0x3Fu));
        buf[(*len)++] = (char)(0x80u | (codepoint & 0x3Fu));
    } else {
        buf[(*len)++] = (char)(0xF0u | (codepoint >> 18));
        buf[(*len)++] = (char)(0x80u | ((codepoint >> 12) & 0x3Fu));
        buf[(*len)++] = (char)(0x80u | ((codepoint >> 6) & 0x3Fu));
        buf[(*len)++] = (char)(0x80u | (codepoint & 0x3Fu));
    }
}

static MValue json_parse_string(SJson *p) {
    size_t cap = 64, len = 0;
    char *buf = (char *)malloc(cap);
    MValue out = mval_none();
    if (!buf) { p->failed = 1; return out; }
    p->pos++; /* opening quote */
    while (p->pos < p->len && !p->failed) {
        char c = p->text[p->pos++];
        unsigned codepoint = 0;
        if (c == '"') break;
        if (len + 8 > cap) {
            char *grown;
            cap *= 2;
            grown = (char *)realloc(buf, cap);
            if (!grown) { free(buf); p->failed = 1; return out; }
            buf = grown;
        }
        if (c != '\\') { buf[len++] = c; continue; }
        if (p->pos >= p->len) { p->failed = 1; break; }
        c = p->text[p->pos++];
        switch (c) {
        case '"': buf[len++] = '"'; break;
        case '\\': buf[len++] = '\\'; break;
        case '/': buf[len++] = '/'; break;
        case 'b': buf[len++] = '\b'; break;
        case 'f': buf[len++] = '\f'; break;
        case 'n': buf[len++] = '\n'; break;
        case 'r': buf[len++] = '\r'; break;
        case 't': buf[len++] = '\t'; break;
        case 'u':
            if (!json_hex4(p, &codepoint)) { p->failed = 1; break; }
            if (codepoint >= 0xD800u && codepoint < 0xDC00u &&
                p->pos + 5 < p->len && p->text[p->pos] == '\\' && p->text[p->pos + 1] == 'u') {
                unsigned low = 0;
                p->pos += 2;
                if (json_hex4(p, &low) && low >= 0xDC00u && low < 0xE000u)
                    codepoint = 0x10000u + ((codepoint - 0xD800u) << 10) + (low - 0xDC00u);
            }
            utf8_append(buf, &len, codepoint);
            break;
        default: buf[len++] = c; break;
        }
    }
    if (p->failed) { free(buf); return mval_none(); }
    buf[len] = '\0';
    out = owned_copy(buf, len);
    free(buf);
    return out;
}

static MValue json_parse_number(SJson *p) {
    size_t start = p->pos;
    int is_float = 0;
    char text[64];
    size_t n;
    if (p->pos < p->len && (p->text[p->pos] == '-' || p->text[p->pos] == '+')) p->pos++;
    while (p->pos < p->len) {
        char c = p->text[p->pos];
        if (c >= '0' && c <= '9') { p->pos++; continue; }
        if (c == '.' || c == 'e' || c == 'E' || c == '-' || c == '+') {
            if (c != '-') is_float = 1;
            p->pos++;
            continue;
        }
        break;
    }
    n = p->pos - start;
    if (n == 0 || n >= sizeof text) { p->failed = 1; return mval_none(); }
    memcpy(text, p->text + start, n);
    text[n] = '\0';
    if (is_float || strchr(text, '.') || strchr(text, 'e') || strchr(text, 'E'))
        return mval_f64(strtod(text, NULL));
    return mval_i64((int64_t)strtoll(text, NULL, 10));
}

static MValue empty_list(void) {
    MValue out = mval_none();
    out.tag = MVAL_LIST;
    out.as.list.items = (MValue *)calloc(1, sizeof(MValue));
    if (!out.as.list.items) return mval_none();
    out.as.list.len = out.as.list.cap = 0;
    return out;
}

static MValue empty_map(void) {
    MValue out = mval_none();
    out.tag = MVAL_MAP;
    out.as.map.keys = (MValue *)calloc(1, sizeof(MValue));
    out.as.map.values = (MValue *)calloc(1, sizeof(MValue));
    if (!out.as.map.keys || !out.as.map.values) {
        free(out.as.map.keys);
        free(out.as.map.values);
        return mval_none();
    }
    out.as.map.len = out.as.map.cap = 0;
    return out;
}

static MValue json_parse_array(SJson *p, int depth) {
    SVec items;
    MValue out = mval_none();
    items.items = NULL;
    items.len = items.cap = 0;
    p->pos++;
    json_skip_space(p);
    if (p->pos < p->len && p->text[p->pos] == ']') {
        p->pos++;
        return empty_list();
    }
    while (p->pos < p->len && !p->failed) {
        MValue value = json_parse_value(p, depth + 1);
        if (p->failed) break;
        if (!svec_push(&items, value)) { p->failed = 1; break; }
        json_skip_space(p);
        if (p->pos < p->len && p->text[p->pos] == ',') { p->pos++; json_skip_space(p); continue; }
        if (p->pos < p->len && p->text[p->pos] == ']') { p->pos++; break; }
        p->failed = 1;
    }
    if (p->failed) {
        size_t i;
        for (i = 0; i < items.len; ++i) mvalue_free(&items.items[i]);
        free(items.items);
        return mval_none();
    }
    if (!items.items) return empty_list();
    out.tag = MVAL_LIST;
    out.as.list.items = items.items;
    out.as.list.len = out.as.list.cap = items.len;
    return out;
}

