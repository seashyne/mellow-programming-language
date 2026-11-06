/* Standard-library fragment 7: std.json.decode. */

typedef struct {
    const char *ptr;
    size_t len;
    size_t pos;
} StdJson;

static void std_json_skip(StdJson *p) {
    while (p->pos < p->len && std_space(p->ptr[p->pos])) ++p->pos;
}

static int std_json_hex4(StdJson *p, uint32_t *out) {
    uint32_t value = 0;
    int i, digit;
    for (i = 0; i < 4; ++i) {
        if (p->pos >= p->len) return 0;
        digit = hex_digit(p->ptr[p->pos++]);
        if (digit < 0) return 0;
        value = (value << 4) | (uint32_t)digit;
    }
    *out = value;
    return 1;
}

static int std_json_string(StdJson *p, MValue *out) {
    AiTextBuf buf;
    if (p->pos >= p->len || p->ptr[p->pos] != '"') return 0;
    ++p->pos;
    memset(&buf, 0, sizeof(buf));
    while (p->pos < p->len) {
        char c = p->ptr[p->pos++];
        if (c == '"') {
            *out = mval_owned_copy(buf.ptr ? buf.ptr : "", buf.len);
            free(buf.ptr);
            return 1;
        }
        if (c != '\\') {
            if ((unsigned char)c < 0x20) { free(buf.ptr); return 0; }
            if (!ai_text_append(&buf, &c, 1)) { free(buf.ptr); return 0; }
            continue;
        }
        if (p->pos >= p->len) { free(buf.ptr); return 0; }
        c = p->ptr[p->pos++];
        if (c == '"' || c == '\\' || c == '/') ai_text_append(&buf, &c, 1);
        else if (c == 'b') ai_text_append(&buf, "\b", 1);
        else if (c == 'f') ai_text_append(&buf, "\f", 1);
        else if (c == 'n') ai_text_append(&buf, "\n", 1);
        else if (c == 'r') ai_text_append(&buf, "\r", 1);
        else if (c == 't') ai_text_append(&buf, "\t", 1);
        else if (c == 'u') {
            uint32_t cp = 0;
            if (!std_json_hex4(p, &cp)) { free(buf.ptr); return 0; }
            if (cp >= 0xD800 && cp <= 0xDBFF && p->pos + 1 < p->len &&
                p->ptr[p->pos] == '\\' && p->ptr[p->pos + 1] == 'u') {
                uint32_t low = 0;
                size_t save = p->pos;
                p->pos += 2;
                if (std_json_hex4(p, &low) && low >= 0xDC00 && low <= 0xDFFF)
                    cp = 0x10000 + ((cp - 0xD800) << 10) + (low - 0xDC00);
                else
                    p->pos = save;
            }
            {
                char bytes[4];
                int n = ai_utf8_encode((int32_t)cp, bytes);
                if (n > 0) ai_text_append(&buf, bytes, (size_t)n);
            }
        } else { free(buf.ptr); return 0; }
    }
    free(buf.ptr);
    return 0;
}

static int std_json_number(StdJson *p, MValue *out) {
    size_t start = p->pos;
    int is_float = 0;
    if (p->pos < p->len && p->ptr[p->pos] == '-') ++p->pos;
    while (p->pos < p->len && p->ptr[p->pos] >= '0' && p->ptr[p->pos] <= '9') ++p->pos;
    if (p->pos < p->len && p->ptr[p->pos] == '.') {
        is_float = 1;
        ++p->pos;
        while (p->pos < p->len && p->ptr[p->pos] >= '0' && p->ptr[p->pos] <= '9') ++p->pos;
    }
    if (p->pos < p->len && (p->ptr[p->pos] == 'e' || p->ptr[p->pos] == 'E')) {
        is_float = 1;
        ++p->pos;
        if (p->pos < p->len && (p->ptr[p->pos] == '+' || p->ptr[p->pos] == '-')) ++p->pos;
        while (p->pos < p->len && p->ptr[p->pos] >= '0' && p->ptr[p->pos] <= '9') ++p->pos;
    }
    if (p->pos == start) return 0;
    {
        char scratch[64];
        size_t n = p->pos - start;
        char *end = NULL;
        if (n >= sizeof(scratch)) return 0;
        memcpy(scratch, p->ptr + start, n);
        scratch[n] = '\0';
        if (!is_float) {
            long long integer = strtoll(scratch, &end, 10);
            if (end && *end == '\0') {
                *out = mval_i64((int64_t)integer);
                return 1;
            }
        }
        *out = mval_f64(strtod(scratch, &end));
        return end && *end == '\0';
    }
}

static int std_json_value(StdJson *p, MValue *out, int depth) {
    if (depth > 64) return 0;
    std_json_skip(p);
    if (p->pos >= p->len) return 0;
    switch (p->ptr[p->pos]) {
    case '{':
        ++p->pos;
        if (!ai_map_new(out, 0)) return 0;
        std_json_skip(p);
        if (p->pos < p->len && p->ptr[p->pos] == '}') { ++p->pos; return 1; }
        while (p->pos < p->len) {
            MValue key = mval_none(), value = mval_none();
            std_json_skip(p);
            if (!std_json_string(p, &key)) return 0;
            std_json_skip(p);
            if (p->pos >= p->len || p->ptr[p->pos] != ':') { mvalue_free(&key); return 0; }
            ++p->pos;
            if (!std_json_value(p, &value, depth + 1)) { mvalue_free(&key); return 0; }
            std_map_set(out, key, value);
            std_json_skip(p);
            if (p->pos < p->len && p->ptr[p->pos] == ',') { ++p->pos; continue; }
            if (p->pos < p->len && p->ptr[p->pos] == '}') { ++p->pos; return 1; }
            return 0;
        }
        return 0;
    case '[':
        ++p->pos;
        if (!ai_list_new(out, 0)) return 0;
        std_json_skip(p);
        if (p->pos < p->len && p->ptr[p->pos] == ']') { ++p->pos; return 1; }
        while (p->pos < p->len) {
            MValue item = mval_none();
            if (!std_json_value(p, &item, depth + 1)) return 0;
            if (!std_list_append(out, item)) return 0;
            std_json_skip(p);
            if (p->pos < p->len && p->ptr[p->pos] == ',') { ++p->pos; continue; }
            if (p->pos < p->len && p->ptr[p->pos] == ']') { ++p->pos; return 1; }
            return 0;
        }
        return 0;
    case '"':
        return std_json_string(p, out);
    case 't':
        if (p->pos + 4 <= p->len && memcmp(p->ptr + p->pos, "true", 4) == 0) {
            p->pos += 4;
            *out = mval_bool(1);
            return 1;
        }
        return 0;
    case 'f':
        if (p->pos + 5 <= p->len && memcmp(p->ptr + p->pos, "false", 5) == 0) {
            p->pos += 5;
            *out = mval_bool(0);
            return 1;
        }
        return 0;
    case 'n':
        if (p->pos + 4 <= p->len && memcmp(p->ptr + p->pos, "null", 4) == 0) {
            p->pos += 4;
            *out = mval_none();
            return 1;
        }
        return 0;
    default:
        return std_json_number(p, out);
    }
}

static int std_json_decode_syscall(MellowRuntimeContext *ctx, const MValue *args,
                                   size_t argc, MValue *out) {
    StdJson p;
    char *text;
    size_t len = 0;
    int ok;
    if (argc != 1) return 0;
    text = std_text(&args[0], &len);
    if (!text) return 0;
    p.ptr = text;
    p.len = len;
    p.pos = 0;
    ok = std_json_value(&p, out, 0);
    std_json_skip(&p);
    if (!ok || p.pos != p.len) {
        mvalue_free(out);
        free(text);
        return std_error(ctx, "std.json.decode: invalid JSON");
    }
    free(text);
    return 1;
}
