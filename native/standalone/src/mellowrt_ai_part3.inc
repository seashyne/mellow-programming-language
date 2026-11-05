/* AI runtime fragment 3: the JSON writer used by model checkpoints. */

static int ai_json_write_value(FILE *fp, const MValue *value, int depth);

static int ai_json_write_string(FILE *fp, const char *text, size_t len) {
    size_t i;
    if (fputc('"', fp) == EOF) return 0;
    for (i = 0; i < len; ++i) {
        unsigned char c = (unsigned char)text[i];
        switch (c) {
        case '"': if (fputs("\\\"", fp) == EOF) return 0; break;
        case '\\': if (fputs("\\\\", fp) == EOF) return 0; break;
        case '\b': if (fputs("\\b", fp) == EOF) return 0; break;
        case '\f': if (fputs("\\f", fp) == EOF) return 0; break;
        case '\n': if (fputs("\\n", fp) == EOF) return 0; break;
        case '\r': if (fputs("\\r", fp) == EOF) return 0; break;
        case '\t': if (fputs("\\t", fp) == EOF) return 0; break;
        default:
            if (c < 0x20) { if (fprintf(fp, "\\u%04x", c) < 0) return 0; }
            else if (fputc(c, fp) == EOF) return 0;
            break;
        }
    }
    return fputc('"', fp) != EOF;
}

static int ai_json_write_value(FILE *fp, const MValue *value, int depth) {
    size_t i;
    char buf[64];
    if (!value) return fputs("null", fp) >= 0;
    if (depth > 64) return 0;
    switch (value->tag) {
    case MVAL_NONE: return fputs("null", fp) >= 0;
    case MVAL_BOOL: return fputs(value->as.boolean ? "true" : "false", fp) >= 0;
    case MVAL_I64:
        return fprintf(fp, "%lld", (long long)value->as.i64) >= 0;
    case MVAL_F64: {
        int written;
        if (!isfinite(value->as.f64)) return fputs("null", fp) >= 0;
        written = snprintf(buf, sizeof(buf), "%.17g", value->as.f64);
        if (written <= 0) return 0;
        if (!strpbrk(buf, ".eEnN")) {
            if ((size_t)written + 2 >= sizeof(buf)) return 0;
            buf[written++] = '.';
            buf[written++] = '0';
            buf[written] = '\0';
        }
        return fputs(buf, fp) >= 0;
    }
    case MVAL_STR:
        return ai_json_write_string(fp, value->as.str.ptr ? value->as.str.ptr : "", value->as.str.len);
    case MVAL_LIST:
        if (fputc('[', fp) == EOF) return 0;
        for (i = 0; i < value->as.list.len; ++i) {
            if (i && fputc(',', fp) == EOF) return 0;
            if (!ai_json_write_value(fp, &value->as.list.items[i], depth + 1)) return 0;
        }
        return fputc(']', fp) != EOF;
    case MVAL_MAP:
        if (fputc('{', fp) == EOF) return 0;
        for (i = 0; i < value->as.map.len; ++i) {
            const MValue *key = &value->as.map.keys[i];
            if (i && fputc(',', fp) == EOF) return 0;
            if (key->tag == MVAL_STR) {
                if (!ai_json_write_string(fp, key->as.str.ptr ? key->as.str.ptr : "", key->as.str.len))
                    return 0;
            } else {
                char *text = ai_value_text(key, NULL);
                int ok = text ? ai_json_write_string(fp, text, strlen(text)) : 0;
                free(text);
                if (!ok) return 0;
            }
            if (fputc(':', fp) == EOF) return 0;
            if (!ai_json_write_value(fp, &value->as.map.values[i], depth + 1)) return 0;
        }
        return fputc('}', fp) != EOF;
    default:
        return fputs("null", fp) >= 0;
    }
}
