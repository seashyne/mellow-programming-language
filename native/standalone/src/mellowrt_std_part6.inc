/* Standard-library fragment 6: std.json.encode and number rendering. */

/* Shortest decimal text that round-trips, matching Python's repr(float). */
static void std_number_repr(char *out, size_t cap, double value) {
    int precision;
    if (!isfinite(value)) {
        snprintf(out, cap, "%s",
                 isnan(value) ? "NaN" : (value < 0 ? "-Infinity" : "Infinity"));
        return;
    }
    for (precision = 15; precision < 17; ++precision) {
        snprintf(out, cap, "%.*g", precision, value);
        if (strtod(out, NULL) == value) break;
    }
    if (precision >= 17) snprintf(out, cap, "%.17g", value);
    if (!strpbrk(out, ".eE")) {
        size_t len = strlen(out);
        if (len + 2 < cap) { out[len] = '.'; out[len + 1] = '0'; out[len + 2] = '\0'; }
    }
}

static int std_json_quote(AiTextBuf *buf, const char *text, size_t len) {
    size_t i;
    static const char hex[] = "0123456789abcdef";
    if (!ai_text_append(buf, "\"", 1)) return 0;
    for (i = 0; i < len; ++i) {
        unsigned char c = (unsigned char)(text ? text[i] : 0);
        char escape[8];
        if (c == '"') { if (!ai_text_append(buf, "\\\"", 2)) return 0; }
        else if (c == '\\') { if (!ai_text_append(buf, "\\\\", 2)) return 0; }
        else if (c == '\n') { if (!ai_text_append(buf, "\\n", 2)) return 0; }
        else if (c == '\r') { if (!ai_text_append(buf, "\\r", 2)) return 0; }
        else if (c == '\t') { if (!ai_text_append(buf, "\\t", 2)) return 0; }
        else if (c == '\b') { if (!ai_text_append(buf, "\\b", 2)) return 0; }
        else if (c == '\f') { if (!ai_text_append(buf, "\\f", 2)) return 0; }
        else if (c < 0x20) {
            snprintf(escape, sizeof(escape), "\\u00%c%c", hex[c >> 4], hex[c & 15]);
            if (!ai_text_append(buf, escape, 6)) return 0;
        }
        else if (!ai_text_append(buf, (const char *)&c, 1)) return 0;
    }
    return ai_text_append(buf, "\"", 1);
}

static int std_json_encode_value(AiTextBuf *buf, const MValue *value, int depth);

static int std_json_encode_key(AiTextBuf *buf, const MValue *key) {
    char number[64];
    switch (key->tag) {
    case MVAL_STR:
        return std_json_quote(buf, key->as.str.ptr, key->as.str.len);
    case MVAL_BOOL:
        return std_json_quote(buf, key->as.boolean ? "true" : "false", key->as.boolean ? 4 : 5);
    case MVAL_NONE:
        return std_json_quote(buf, "null", 4);
    case MVAL_I64:
        snprintf(number, sizeof(number), "%lld", (long long)key->as.i64);
        return std_json_quote(buf, number, strlen(number));
    case MVAL_F64:
        std_number_repr(number, sizeof(number), key->as.f64);
        return std_json_quote(buf, number, strlen(number));
    default:
        return std_json_quote(buf, "", 0);
    }
}

static int std_json_encode_value(AiTextBuf *buf, const MValue *value, int depth) {
    char number[64];
    size_t i;
    if (!value) return ai_text_append(buf, "null", 4);
    if (depth > 64) return 0;
    switch (value->tag) {
    case MVAL_NONE:
        return ai_text_append(buf, "null", 4);
    case MVAL_BOOL:
        return ai_text_append(buf, value->as.boolean ? "true" : "false",
                              value->as.boolean ? 4 : 5);
    case MVAL_I64:
        snprintf(number, sizeof(number), "%lld", (long long)value->as.i64);
        return ai_text_append(buf, number, strlen(number));
    case MVAL_F64:
        std_number_repr(number, sizeof(number), value->as.f64);
        return ai_text_append(buf, number, strlen(number));
    case MVAL_STR:
        return std_json_quote(buf, value->as.str.ptr, value->as.str.len);
    case MVAL_LIST:
        if (!ai_text_append(buf, "[", 1)) return 0;
        for (i = 0; i < value->as.list.len; ++i) {
            if (i && !ai_text_append(buf, ", ", 2)) return 0;
            if (!std_json_encode_value(buf, &value->as.list.items[i], depth + 1)) return 0;
        }
        return ai_text_append(buf, "]", 1);
    case MVAL_MAP:
        if (!ai_text_append(buf, "{", 1)) return 0;
        for (i = 0; i < value->as.map.len; ++i) {
            if (i && !ai_text_append(buf, ", ", 2)) return 0;
            if (!std_json_encode_key(buf, &value->as.map.keys[i])) return 0;
            if (!ai_text_append(buf, ": ", 2)) return 0;
            if (!std_json_encode_value(buf, &value->as.map.values[i], depth + 1)) return 0;
        }
        return ai_text_append(buf, "}", 1);
    default:
        return 0;
    }
}

static int std_json_syscall(MellowRuntimeContext *ctx, int id, const MValue *args,
                            size_t argc, MValue *out) {
    if (id != 266) return 0;
    if (argc != 1) return 0;
    {
        AiTextBuf buf;
        memset(&buf, 0, sizeof(buf));
        if (!std_json_encode_value(&buf, &args[0], 0)) {
            free(buf.ptr);
            return std_error(ctx, "std.json.encode: unsupported value");
        }
        *out = mval_owned_copy(buf.ptr ? buf.ptr : "", buf.len);
        free(buf.ptr);
        return 1;
    }
}
