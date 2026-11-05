/* AI runtime fragment 4: the JSON reader used by model checkpoints. */

typedef struct {
    const char *text;
    size_t len;
    size_t pos;
    int depth;
} AiJsonReader;

static void ai_json_skip_ws(AiJsonReader *r) {
    while (r->pos < r->len) {
        char c = r->text[r->pos];
        if (c == ' ' || c == '\t' || c == '\n' || c == '\r') ++r->pos;
        else break;
    }
}

static int ai_json_hex4(AiJsonReader *r, int32_t *out) {
    int32_t value = 0;
    int i;
    if (r->pos + 4 > r->len) return 0;
    for (i = 0; i < 4; ++i) {
        char c = r->text[r->pos + (size_t)i];
        value <<= 4;
        if (c >= '0' && c <= '9') value |= c - '0';
        else if (c >= 'a' && c <= 'f') value |= c - 'a' + 10;
        else if (c >= 'A' && c <= 'F') value |= c - 'A' + 10;
        else return 0;
    }
    r->pos += 4;
    *out = value;
    return 1;
}

static int ai_json_string(AiJsonReader *r, MValue *out) {
    size_t cap, len = 0;
    char *buf;
    if (r->pos >= r->len || r->text[r->pos] != '"') return 0;
    r->pos++;
    cap = r->len - r->pos + 1;
    buf = (char *)calloc(cap, 1);
    if (!buf) return 0;
    while (r->pos < r->len) {
        unsigned char c = (unsigned char)r->text[r->pos++];
        if (c == '"') {
            buf[len] = '\0';
            out->tag = MVAL_STR;
            out->flags = 1u;
            out->as.str.ptr = buf;
            out->as.str.len = len;
            return 1;
        }
        if (c == '\\') {
            int32_t cp;
            char encoded[4];
            int n;
            if (r->pos >= r->len) break;
            c = (unsigned char)r->text[r->pos++];
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
                if (!ai_json_hex4(r, &cp)) { free(buf); return 0; }
                if (cp >= 0xd800 && cp <= 0xdbff && r->pos + 6 <= r->len &&
                    r->text[r->pos] == '\\' && r->text[r->pos + 1] == 'u') {
                    int32_t low;
                    size_t save = r->pos;
                    r->pos += 2;
                    if (ai_json_hex4(r, &low) && low >= 0xdc00 && low <= 0xdfff) {
                        cp = 0x10000 + ((cp - 0xd800) << 10) + (low - 0xdc00);
                    } else {
                        r->pos = save;
                    }
                }
                n = ai_utf8_encode(cp, encoded);
                if (len + (size_t)n + 1 > cap) { free(buf); return 0; }
                memcpy(buf + len, encoded, (size_t)n);
                len += (size_t)n;
                break;
            default: free(buf); return 0;
            }
        } else {
            if (len + 2 > cap) { free(buf); return 0; }
            buf[len++] = (char)c;
        }
    }
    free(buf);
    return 0;
}

static int ai_json_append(MValue *list, MValue item) {
    if (list->as.list.len == list->as.list.cap) {
        size_t next = list->as.list.cap ? list->as.list.cap * 2 : 8;
        MValue *grown = (MValue *)realloc(list->as.list.items, next * sizeof(MValue));
        if (!grown) return 0;
        list->as.list.items = grown;
        list->as.list.cap = next;
    }
    list->as.list.items[list->as.list.len++] = item;
    return 1;
}

static int ai_json_map_append(MValue *map, MValue key, MValue value) {
    if (map->as.map.len == map->as.map.cap) {
        size_t next = map->as.map.cap ? map->as.map.cap * 2 : 8;
        MValue *keys = (MValue *)realloc(map->as.map.keys, next * sizeof(MValue));
        MValue *values;
        if (!keys) return 0;
        map->as.map.keys = keys;
        values = (MValue *)realloc(map->as.map.values, next * sizeof(MValue));
        if (!values) return 0;
        map->as.map.values = values;
        map->as.map.cap = next;
    }
    map->as.map.keys[map->as.map.len] = key;
    map->as.map.values[map->as.map.len] = value;
    map->as.map.len++;
    return 1;
}

static int ai_json_value(AiJsonReader *r, MValue *out);

static int ai_json_array(AiJsonReader *r, MValue *out) {
    r->pos++;
    *out = mval_none();
    out->tag = MVAL_LIST;
    ai_json_skip_ws(r);
    if (r->pos < r->len && r->text[r->pos] == ']') { r->pos++; return 1; }
    for (;;) {
        MValue item;
        if (!ai_json_value(r, &item)) return 0;
        if (!ai_json_append(out, item)) return 0;
        ai_json_skip_ws(r);
        if (r->pos < r->len && r->text[r->pos] == ',') { r->pos++; continue; }
        if (r->pos < r->len && r->text[r->pos] == ']') { r->pos++; return 1; }
        return 0;
    }
}

static int ai_json_object(AiJsonReader *r, MValue *out) {
    r->pos++;
    *out = mval_none();
    out->tag = MVAL_MAP;
    ai_json_skip_ws(r);
    if (r->pos < r->len && r->text[r->pos] == '}') { r->pos++; return 1; }
    for (;;) {
        MValue key, value;
        if (!ai_json_string(r, &key)) return 0;
        ai_json_skip_ws(r);
        if (r->pos >= r->len || r->text[r->pos] != ':') { mvalue_free(&key); return 0; }
        r->pos++;
        if (!ai_json_value(r, &value)) { mvalue_free(&key); return 0; }
        if (!ai_json_map_append(out, key, value)) return 0;
        ai_json_skip_ws(r);
        if (r->pos < r->len && r->text[r->pos] == ',') { r->pos++; ai_json_skip_ws(r); continue; }
        if (r->pos < r->len && r->text[r->pos] == '}') { r->pos++; return 1; }
        return 0;
    }
}

static int ai_json_value(AiJsonReader *r, MValue *out) {
    char token[128];
    size_t start, n;
    ai_json_skip_ws(r);
    if (r->pos >= r->len || ++r->depth > 64) return 0;
    if (r->text[r->pos] == '"') { int ok = ai_json_string(r, out); r->depth--; return ok; }
    if (r->text[r->pos] == '[') { int ok = ai_json_array(r, out); r->depth--; return ok; }
    if (r->text[r->pos] == '{') { int ok = ai_json_object(r, out); r->depth--; return ok; }
    if (r->len - r->pos >= 4 && memcmp(r->text + r->pos, "true", 4) == 0) {
        r->pos += 4; *out = mval_bool(1); r->depth--; return 1;
    }
    if (r->len - r->pos >= 5 && memcmp(r->text + r->pos, "false", 5) == 0) {
        r->pos += 5; *out = mval_bool(0); r->depth--; return 1;
    }
    if (r->len - r->pos >= 4 && memcmp(r->text + r->pos, "null", 4) == 0) {
        r->pos += 4; *out = mval_none(); r->depth--; return 1;
    }
    start = r->pos;
    while (r->pos < r->len && strchr("+-.0123456789eE", r->text[r->pos])) r->pos++;
    n = r->pos - start;
    if (n == 0 || n >= sizeof(token)) { r->depth--; return 0; }
    memcpy(token, r->text + start, n);
    token[n] = '\0';
    if (strpbrk(token, ".eE")) {
        *out = mval_f64(strtod(token, NULL));
    } else {
        char *end = NULL;
        long long number;
        errno = 0;
        number = strtoll(token, &end, 10);
        if (errno == ERANGE) *out = mval_f64(strtod(token, NULL));
        else *out = mval_i64((int64_t)number);
    }
    r->depth--;
    return 1;
}

static int ai_json_parse(const char *text, size_t len, MValue *out) {
    AiJsonReader r;
    int ok;
    r.text = text;
    r.len = len;
    r.pos = 0;
    r.depth = 0;
    *out = mval_none();
    ok = ai_json_value(&r, out);
    if (!ok) { mvalue_free(out); return 0; }
    ai_json_skip_ws(&r);
    return 1;
}

/* Write an MValue tree as compact JSON into a freshly allocated string. */
static char *ai_json_dump(const MValue *value, size_t *out_len) {
    FILE *fp;
    long size;
    char *buffer;
    fp = tmpfile();
    if (!fp) return NULL;
    if (!ai_json_write_value(fp, value, 0)) { fclose(fp); return NULL; }
    fflush(fp);
    if (fseek(fp, 0, SEEK_END) != 0) { fclose(fp); return NULL; }
    size = ftell(fp);
    if (size < 0) { fclose(fp); return NULL; }
    rewind(fp);
    buffer = (char *)calloc((size_t)size + 1, 1);
    if (!buffer) { fclose(fp); return NULL; }
    if (fread(buffer, 1, (size_t)size, fp) != (size_t)size) {
        free(buffer);
        fclose(fp);
        return NULL;
    }
    fclose(fp);
    if (out_len) *out_len = (size_t)size;
    return buffer;
}
