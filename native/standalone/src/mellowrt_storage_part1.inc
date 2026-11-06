static MValue owned_copy(const char *src, size_t len) {
    char *buf;
    MValue v = mval_none();
    if (!src) return v;
    buf = (char *)calloc(len + 1, 1);
    if (!buf) return v;
    memcpy(buf, src, len);
    buf[len] = '\0';
    v.tag = MVAL_STR;
    v.flags = 1u;
    v.as.str.ptr = buf;
    v.as.str.len = len;
    return v;
}

static MValue owned_text(const char *text) {
    return owned_copy(text, strlen(text));
}

static void set_error(char *error, size_t cap, const char *message) {
    if (error && cap) snprintf(error, cap, "%s", message);
}

static void set_errorf(char *error, size_t cap, const char *fmt, const char *arg) {
    if (!error || !cap) return;
    if (fmt && arg) snprintf(error, cap, fmt, arg);
    else if (fmt) snprintf(error, cap, "%s", fmt);
    else error[0] = '\0';
}

/* ── paths ─────────────────────────────────────────────────────── */

static int is_separator(char c) {
    return c == '/' || c == '\\';
}

static int path_is_absolute(const char *path) {
    if (!path || !*path) return 0;
    if (path[0] == '/' || path[0] == '\\') return 1;
    if (((path[0] >= 'A' && path[0] <= 'Z') || (path[0] >= 'a' && path[0] <= 'z')) && path[1] == ':')
        return 1;
    return 0;
}

static int path_is_unsafe(const char *raw) {
    size_t n;
    if (!raw || !*raw) return 0;
    if (path_is_absolute(raw)) return 1;
    n = strlen(raw);
    if (strcmp(raw, "..") == 0) return 1;
    if (strncmp(raw, "../", 3) == 0 || strncmp(raw, "..\\", 3) == 0) return 1;
    if (strstr(raw, "/../") || strstr(raw, "\\..\\") || strstr(raw, "/..\\") || strstr(raw, "\\../")) return 1;
    if (n >= 3 && (strcmp(raw + n - 3, "/..") == 0 || strcmp(raw + n - 3, "\\..") == 0)) return 1;
    return 0;
}

/* Trim surrounding whitespace and quotes, then use '/' separators. */
static void path_clean(const MValue *value, char *out, size_t cap) {
    const char *src = NULL;
    size_t len = 0, start = 0;
    size_t i, n;

    out[0] = '\0';
    if (!value || value->tag != MVAL_STR) return;
    src = value->as.str.ptr;
    if (!src) return;
    len = value->as.str.len;
    if (len == 0) len = strlen(src);
    while (len && (src[len - 1] == ' ' || src[len - 1] == '\t' ||
                   src[len - 1] == '\r' || src[len - 1] == '\n')) len--;
    while (start < len && (src[start] == ' ' || src[start] == '\t')) start++;
    if (start < len && src[start] == '"' && src[len - 1] == '"') { start++; if (len > start) len--; }
    if (start < len && src[start] == '\'' && src[len - 1] == '\'') { start++; if (len > start) len--; }

    n = len - start;
    if (n >= cap) n = cap - 1;
    for (i = 0; i < n; ++i) {
        char c = src[start + i];
        out[i] = (c == '\\') ? '/' : c;
    }
    out[n] = '\0';
}

static void path_use_separators(const char *raw, char *out, size_t cap) {
    size_t i, n;
    out[0] = '\0';
    if (!raw) return;
    n = strlen(raw);
    if (n >= cap) n = cap - 1;
    for (i = 0; i < n; ++i) out[i] = (raw[i] == '\\') ? '/' : raw[i];
    out[n] = '\0';
}

static int file_exists(const char *path) {
    struct stat info;
    return stat(path, &info) == 0;
}

static void make_dirs(const char *path) {
    char buf[STOR_PATH_MAX];
    size_t i, len;
    snprintf(buf, sizeof buf, "%s", path);
    len = strlen(buf);
    while (len > 1 && is_separator(buf[len - 1])) buf[--len] = '\0';
    for (i = 1; buf[i]; ++i) {
        if (buf[i] == '/') {
            buf[i] = '\0';
            STOR_MAKE_DIR(buf);
            buf[i] = '/';
        }
    }
    STOR_MAKE_DIR(buf);
}

static void parent_dir(const char *path, char *out, size_t cap) {
    const char *slash = strrchr(path, '/');
    size_t len;
    out[0] = '\0';
    if (!slash) return;
    len = (size_t)(slash - path);
    if (len == 0 || len >= cap) return;
    memcpy(out, path, len);
    out[len] = '\0';
}

/* Best-effort absolute form of a path, used only for reporting. */
static void absolute_path(const char *path, char *out, size_t cap) {
    char cwd[STOR_PATH_MAX];
    out[0] = '\0';
    if (!path || !*path) return;
    if (path_is_absolute(path)) { snprintf(out, cap, "%s", path); return; }
    if (STOR_GET_CWD(cwd, sizeof cwd) == NULL) { snprintf(out, cap, "%s", path); return; }
    snprintf(out, cap, "%s/%s", cwd, path);
}

static int join_under_base(char *out, size_t cap, const char *base, const char *rel) {
    if (path_is_unsafe(rel)) return 0;
    if (!rel || !*rel || strcmp(rel, ".") == 0) {
        snprintf(out, cap, "%s", base);
        return 1;
    }
    if (snprintf(out, cap, "%s/%s", base, rel) >= (int)cap) return 0;
    return 1;
}

/* Storage slot path: always a .json document under the sandbox base. */
static int slot_path(char *out, size_t cap, const char *base, const MValue *key) {
    char clean[STOR_PATH_MAX];
    size_t len;
    path_clean(key, clean, sizeof clean);
    if (!*clean || strcmp(clean, ".") == 0 || strcmp(clean, "..") == 0)
        snprintf(clean, sizeof clean, "save");
    if (path_is_unsafe(clean)) return 0;
    len = strlen(clean);
    if (len < 5 || strcmp(clean + len - 5, ".json") != 0) {
        if (snprintf(out, cap, "%s/%s.json", base, clean) >= (int)cap) return 0;
        return 1;
    }
    return join_under_base(out, cap, base, clean);
}

/* ── file io ───────────────────────────────────────────────────── */

static int read_whole_file(const char *path, char **out, size_t *out_len) {
    FILE *stream;
    long size;
    size_t got;
    char *buf;
    *out = NULL;
    *out_len = 0;
    stream = fopen(path, "rb");
    if (!stream) return 0;
    if (fseek(stream, 0, SEEK_END) != 0) { fclose(stream); return 0; }
    size = ftell(stream);
    if (size < 0) { fclose(stream); return 0; }
    if (fseek(stream, 0, SEEK_SET) != 0) { fclose(stream); return 0; }
    buf = (char *)malloc((size_t)size + 1);
    if (!buf) { fclose(stream); return 0; }
    got = size ? fread(buf, 1, (size_t)size, stream) : 0;
    fclose(stream);
    buf[got] = '\0';
    *out = buf;
    *out_len = got;
    return 1;
}

static int write_whole_file(const char *path, const char *data, size_t len, int append) {
    FILE *stream = fopen(path, append ? "ab" : "wb");
    size_t wrote;
    if (!stream) return 0;
    wrote = len ? fwrite(data, 1, len, stream) : 0;
    fclose(stream);
    return wrote == len;
}

/* Write a temp document, then swap it in so a crash cannot truncate a save. */
static int write_atomic(const char *path, const char *data, size_t len) {
    char temp[STOR_PATH_MAX];
    if (snprintf(temp, sizeof temp, "%s.tmp", path) >= (int)sizeof temp) return 0;
    if (!write_whole_file(temp, data, len, 0)) return 0;
    if (file_exists(path) && remove(path) != 0) { remove(temp); return 0; }
    if (rename(temp, path) != 0) { remove(temp); return 0; }
    return 1;
}

/* ── json encode ───────────────────────────────────────────────── */

typedef struct {
    char *buf;
    size_t len;
    size_t cap;
    int ok;
} Sbuf;

static void sbuf_init(Sbuf *b) {
    b->buf = NULL;
    b->len = 0;
    b->cap = 0;
    b->ok = 1;
}

static void sbuf_add(Sbuf *b, const char *text, size_t len) {
    size_t need = b->len + len + 1;
    size_t cap = b->cap ? b->cap : 128;
    char *grown;
    if (!b->ok) return;
    while (cap < need) cap *= 2;
    if (cap > b->cap) {
        grown = (char *)realloc(b->buf, cap);
        if (!grown) { b->ok = 0; return; }
        b->buf = grown;
        b->cap = cap;
    }
    memcpy(b->buf + b->len, text, len);
    b->len += len;
    b->buf[b->len] = '\0';
}

static void sbuf_add_str(Sbuf *b, const char *text) { sbuf_add(b, text, strlen(text)); }
static void sbuf_add_char(Sbuf *b, char c) { sbuf_add(b, &c, 1); }

static void sbuf_add_json_string(Sbuf *b, const char *text, size_t len) {
    size_t i;
    sbuf_add_char(b, '"');
    if (text) {
        for (i = 0; i < len; ++i) {
            unsigned char c = (unsigned char)text[i];
            char escape[8];
            switch (c) {
            case '"':  sbuf_add_str(b, "\\\""); break;
            case '\\': sbuf_add_str(b, "\\\\"); break;
            case '\b': sbuf_add_str(b, "\\b"); break;
            case '\f': sbuf_add_str(b, "\\f"); break;
            case '\n': sbuf_add_str(b, "\\n"); break;
            case '\r': sbuf_add_str(b, "\\r"); break;
            case '\t': sbuf_add_str(b, "\\t"); break;
            default:
                if (c < 0x20) {
                    snprintf(escape, sizeof escape, "\\u%04x", c);
                    sbuf_add_str(b, escape);
                } else {
                    sbuf_add_char(b, (char)c);
                }
            }
        }
    }
    sbuf_add_char(b, '"');
}

static void json_encode(Sbuf *b, const MValue *value, int depth);

static void json_encode_number(Sbuf *b, const MValue *value) {
    char text[64];
    double number = value->as.f64;
    if (value->tag == MVAL_I64) {
        snprintf(text, sizeof text, "%lld", (long long)value->as.i64);
        sbuf_add_str(b, text);
        return;
    }
    /* JSON has no literal for nan/inf; python's json.dump emits one, so keep it readable. */
    if (number != number || number > 1.7976931348623157e308 || number < -1.7976931348623157e308) {
        sbuf_add_str(b, "null");
        return;
    }
    snprintf(text, sizeof text, "%.15g", number);
    if (!strchr(text, '.') && !strchr(text, 'e'))
        strncat(text, ".0", sizeof text - strlen(text) - 1);
    sbuf_add_str(b, text);
}

