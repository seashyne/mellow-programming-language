#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#endif

#include "mellowrt_storage.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>

#ifdef _WIN32
#include <direct.h>
#define STOR_MAKE_DIR(path) _mkdir(path)
#define STOR_GET_CWD(buf, cap) _getcwd((buf), (int)(cap))
#else
#include <unistd.h>
#define STOR_MAKE_DIR(path) mkdir((path), 0777)
#define STOR_GET_CWD(buf, cap) getcwd((buf), (cap))
#endif

#define STOR_PATH_MAX 512
#define STOR_DEFAULT_BASE "mellow_saves"
#define STOR_MAX_DEPTH 24

#define ERR_STORAGE_TRAVERSAL "SANDBOX: invalid storage path (path traversal blocked)"
#define ERR_FILE_TRAVERSAL "SANDBOX: invalid file path (path traversal blocked)"
#define ERR_FS_TRAVERSAL "SANDBOX: fs: \"..\" traversal is blocked"
#define ERR_FS_ABSOLUTE "SANDBOX: fs: absolute paths are disabled by default"
#define ERR_DIR_ABSOLUTE "SANDBOX: storage_dir: absolute paths are disabled by default"
#define ERR_DIR_TRAVERSAL "SANDBOX: storage_dir: \"..\" traversal is blocked"
#define ERR_NOT_JSON "RUNTIME: value is not storable as JSON"
#define ERR_WRITE "RUNTIME: could not write the file"
#define ERR_READ "RUNTIME: could not read the file"
#define ERR_CORRUPT "RUNTIME: invalid JSON in save document"

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

static MValue json_parse_object(SJson *p, int depth) {
    SVec keys, values;
    MValue out = mval_none();
    keys.items = NULL;
    keys.len = keys.cap = 0;
    values.items = NULL;
    values.len = values.cap = 0;
    p->pos++;
    json_skip_space(p);
    if (p->pos < p->len && p->text[p->pos] == '}') {
        p->pos++;
        return empty_map();
    }
    while (p->pos < p->len && !p->failed) {
        MValue key;
        MValue value;
        json_skip_space(p);
        if (p->pos >= p->len || p->text[p->pos] != '"') { p->failed = 1; break; }
        key = json_parse_string(p);
        if (p->failed) break;
        json_skip_space(p);
        if (p->pos >= p->len || p->text[p->pos] != ':') { p->failed = 1; break; }
        p->pos++;
        json_skip_space(p);
        value = json_parse_value(p, depth + 1);
        if (p->failed) { mvalue_free(&key); break; }
        if (!svec_push(&keys, key) || !svec_push(&values, value)) {
            mvalue_free(&key);
            mvalue_free(&value);
            p->failed = 1;
            break;
        }
        json_skip_space(p);
        if (p->pos < p->len && p->text[p->pos] == ',') { p->pos++; continue; }
        if (p->pos < p->len && p->text[p->pos] == '}') { p->pos++; break; }
        p->failed = 1;
    }
    if (p->failed) {
        size_t i;
        for (i = 0; i < keys.len; ++i) { mvalue_free(&keys.items[i]); mvalue_free(&values.items[i]); }
        free(keys.items);
        free(values.items);
        return mval_none();
    }
    if (!keys.items || !values.items) return empty_map();
    out.tag = MVAL_MAP;
    out.as.map.keys = keys.items;
    out.as.map.values = values.items;
    out.as.map.len = out.as.map.cap = keys.len;
    return out;
}

static MValue json_parse_value(SJson *p, int depth) {
    char c;
    json_skip_space(p);
    if (depth > STOR_MAX_DEPTH || p->pos >= p->len) { p->failed = 1; return mval_none(); }
    c = p->text[p->pos];
    if (c == '{') return json_parse_object(p, depth);
    if (c == '[') return json_parse_array(p, depth);
    if (c == '"') return json_parse_string(p);
    if (c == 't' && p->pos + 4 <= p->len && memcmp(p->text + p->pos, "true", 4) == 0) {
        p->pos += 4;
        return mval_bool(1);
    }
    if (c == 'f' && p->pos + 5 <= p->len && memcmp(p->text + p->pos, "false", 5) == 0) {
        p->pos += 5;
        return mval_bool(0);
    }
    if (c == 'n' && p->pos + 4 <= p->len && memcmp(p->text + p->pos, "null", 4) == 0) {
        p->pos += 4;
        return mval_none();
    }
    if (c == '-' || (c >= '0' && c <= '9')) return json_parse_number(p);
    p->failed = 1;
    return mval_none();
}

static MValue parse_document(const char *text, size_t len, int *ok) {
    SJson parser;
    MValue value;
    parser.text = text;
    parser.pos = 0;
    parser.len = len;
    parser.failed = 0;
    value = json_parse_value(&parser, 0);
    if (!parser.failed) json_skip_space(&parser);
    *ok = !parser.failed && parser.pos == parser.len;
    if (!*ok) mvalue_free(&value);
    return value;
}

/* ── syscall implementations ───────────────────────────────────── */

static MValue arg_at(const MValue *args, size_t argc, size_t index) {
    if (args && index < argc) return args[index];
    return mval_none();
}

static const MValue *arg_ptr(const MValue *args, size_t argc, size_t index) {
    return (args && index < argc) ? &args[index] : NULL;
}

static int storage_move(char *dir, size_t cap, const MValue *target, char *error, size_t error_cap) {
    char clean[STOR_PATH_MAX];
    path_clean(target, clean, sizeof clean);
    /* "" and "." both mean "the current working directory", as in the Python VM. */
    if (!*clean || strcmp(clean, ".") == 0) {
        snprintf(dir, cap, ".");
        return 1;
    }
    if (path_is_absolute(clean)) {
        set_error(error, error_cap, ERR_DIR_ABSOLUTE);
        return 0;
    }
    if (path_is_unsafe(clean)) {
        set_error(error, error_cap, ERR_DIR_TRAVERSAL);
        return 0;
    }
    snprintf(dir, cap, "%s", clean);
    return 1;
}

/* Mirrors _save_json: the base is created on demand, sub-folders are not. */
static int storage_write_slot(const char *base, const MValue *key, const MValue *value,
                             char *error, size_t error_cap) {
    char path[STOR_PATH_MAX];
    char parent[STOR_PATH_MAX];
    Sbuf document;
    int moved;
    if (!slot_path(path, sizeof path, base, key)) {
        set_error(error, error_cap, ERR_STORAGE_TRAVERSAL);
        return 0;
    }
    sbuf_init(&document);
    json_encode(&document, value, 0);
    if (!document.ok || !document.buf) {
        free(document.buf);
        set_error(error, error_cap, ERR_NOT_JSON);
        return 0;
    }
    if (!file_exists(base)) make_dirs(base);
    parent_dir(path, parent, sizeof parent);
    if (*parent && strcmp(parent, base) != 0) {
        if (!file_exists(parent)) {
            free(document.buf);
            set_errorf(error, error_cap, "RUNTIME: Folder not found: %s (create it first)", parent);
            return 0;
        }
    }
    moved = write_atomic(path, document.buf, document.len);
    free(document.buf);
    if (!moved) set_error(error, error_cap, "RUNTIME: could not write the save document");
    return moved;
}

static int storage_read_slot(const char *base, const MValue *key, MValue *out_value,
                            char *error, size_t error_cap) {
    char path[STOR_PATH_MAX];
    char *text = NULL;
    size_t len = 0;
    int ok = 0;
    MValue value;
    if (!slot_path(path, sizeof path, base, key)) {
        set_error(error, error_cap, ERR_STORAGE_TRAVERSAL);
        return 0;
    }
    *out_value = mval_none();
    if (!file_exists(path)) return 1;
    if (!read_whole_file(path, &text, &len)) {
        set_error(error, error_cap, "RUNTIME: could not read the save document");
        return 0;
    }
    value = parse_document(text, len, &ok);
    free(text);
    if (!ok) {
        set_error(error, error_cap, ERR_CORRUPT);
        return 0;
    }
    *out_value = value;
    return 1;
}

static int storage_read_text(const char *path, MValue *out_result, char *error, size_t error_cap) {
    char *text = NULL;
    size_t len = 0;
    if (!read_whole_file(path, &text, &len)) {
        set_error(error, error_cap, ERR_READ);
        return 0;
    }
    *out_result = owned_copy(text, len);
    free(text);
    return 1;
}

static int storage_write_text(const char *path, const MValue *data, int append,
                             int make_parents, char *error, size_t error_cap) {
    char parent[STOR_PATH_MAX];
    const char *text = NULL;
    size_t len = 0;
    char scratch[64];
    int wrote;

    if (data) {
        if (data->tag == MVAL_STR) {
            text = data->as.str.ptr;
            len = data->as.str.len;
        } else if (data->tag == MVAL_I64 || data->tag == MVAL_F64) {
            Sbuf number;
            sbuf_init(&number);
            json_encode_number(&number, data);
            snprintf(scratch, sizeof scratch, "%s", number.buf ? number.buf : "");
            free(number.buf);
            text = scratch;
            len = strlen(scratch);
        } else if (data->tag == MVAL_BOOL) {
            text = data->as.boolean ? "true" : "false";
            len = strlen(text);
        } else if (data->tag != MVAL_NONE) {
            Sbuf document;
            sbuf_init(&document);
            json_encode(&document, data, 0);
            if (!document.ok) {
                free(document.buf);
                set_error(error, error_cap, ERR_NOT_JSON);
                return 0;
            }
            wrote = write_whole_file(path, document.buf ? document.buf : "", document.len, append);
            free(document.buf);
            if (!wrote) set_error(error, error_cap, ERR_WRITE);
            return wrote;
        }
    }
    if (!text) { text = ""; len = 0; }
    if (make_parents) {
        parent_dir(path, parent, sizeof parent);
        if (*parent && !file_exists(parent)) make_dirs(parent);
    }
    wrote = write_whole_file(path, text, len, append);
    if (!wrote) set_error(error, error_cap, ERR_WRITE);
    return wrote;
}

/* fs_* walks the host tree like _fs_resolve does in dev mode: no traversal, no absolutes. */
static int fs_host_path(const MValue *target, char *out, size_t cap, char *error, size_t error_cap) {
    char clean[STOR_PATH_MAX];
    path_clean(target, clean, sizeof clean);
    if (!*clean) snprintf(clean, sizeof clean, ".");
    if (path_is_absolute(clean)) {
        set_error(error, error_cap, ERR_FS_ABSOLUTE);
        return 0;
    }
    if (path_is_unsafe(clean)) {
        set_error(error, error_cap, ERR_FS_TRAVERSAL);
        return 0;
    }
    snprintf(out, cap, "%s", clean);
    return 1;
}

int mellowrt_storage_syscall(int32_t id, const MValue *args, size_t argc, MValue *out_result,
                             char *storage_dir, size_t storage_dir_cap,
                             char *error, size_t error_cap) {
    char base[STOR_PATH_MAX];
    char path[STOR_PATH_MAX];
    char clean[STOR_PATH_MAX];
    MValue none = mval_none();

    if (error && error_cap) error[0] = '\0';
    if (!out_result) return 0;
    *out_result = none;
    if (storage_dir && *storage_dir) path_use_separators(storage_dir, base, sizeof base);
    else snprintf(base, sizeof base, "%s", STOR_DEFAULT_BASE);

    switch (id) {
    case 61: /* storage_dir */
        if (argc > 1 || !storage_dir || !storage_dir_cap) return 0;
        if (!storage_move(storage_dir, storage_dir_cap, arg_ptr(args, argc, 0), error, error_cap)) return 0;
        *out_result = mval_bool(1);
        return 1;
    case 62: /* storage_pwd */
        if (argc != 0) return 0;
        *out_result = owned_text(base);
        return 1;
    case 63: { /* storage_info */
        MValue info = mval_none();
        if (argc != 0) return 0;
        info.tag = MVAL_MAP;
        info.as.map.keys = (MValue *)calloc(2, sizeof(MValue));
        info.as.map.values = (MValue *)calloc(2, sizeof(MValue));
        if (!info.as.map.keys || !info.as.map.values) {
            free(info.as.map.keys);
            free(info.as.map.values);
            return 0;
        }
        info.as.map.len = info.as.map.cap = 2;
        absolute_path(base, path, sizeof path);
        info.as.map.keys[0] = owned_text("storage_dir");
        info.as.map.values[0] = owned_text(base);
        info.as.map.keys[1] = owned_text("storage_abs");
        info.as.map.values[1] = owned_text(path);
        *out_result = info;
        return 1;
    }
    case 64: { /* save_data */
        MValue key = arg_at(args, argc, 0);
        MValue value = arg_at(args, argc, 1);
        MValue swap;
        if (argc < 2) return 0;
        /* save_data accepts (key, value) or (value, key), like the Python VM */
        if (key.tag != MVAL_STR && value.tag == MVAL_STR) { swap = key; key = value; value = swap; }
        if (!storage_write_slot(base, &key, &value, error, error_cap)) return 0;
        *out_result = mval_bool(1);
        return 1;
    }
    case 65: /* load_data */
        if (argc < 1) return 0;
        if (!storage_read_slot(base, arg_ptr(args, argc, 0), out_result, error, error_cap)) return 0;
        return 1;
    case 66: { /* storage.mkdir under the storage base */
        path_clean(arg_ptr(args, argc, 0), clean, sizeof clean);
        if (argc > 1) return 0;
        if (!join_under_base(path, sizeof path, base, clean)) {
            set_error(error, error_cap, ERR_FILE_TRAVERSAL);
            return 0;
        }
        make_dirs(path);
        *out_result = mval_bool(file_exists(path));
        return 1;
    }
    default:
        break;
    }

    if (id >= 67 && id <= 73) {
        if (id == 73) { /* fs_pwd */
            char cwd[STOR_PATH_MAX];
            if (argc != 0) return 0;
            if (STOR_GET_CWD(cwd, sizeof cwd) == NULL) return 0;
            *out_result = owned_text(cwd);
            return 1;
        }
        if (!fs_host_path(arg_ptr(args, argc, 0), path, sizeof path, error, error_cap)) return 0;
        switch (id) {
        case 67: /* fs_read */
            if (!storage_read_text(path, out_result, error, error_cap)) return 0;
            return 1;
        case 68: /* fs_write */
        case 69: /* fs_append */
            if (!storage_write_text(path, arg_ptr(args, argc, 1), id == 69, 1, error, error_cap)) return 0;
            *out_result = mval_bool(1);
            return 1;
        case 70: /* fs_exists */
            *out_result = mval_bool(file_exists(path));
            return 1;
        case 71: /* fs_delete */
            if (!file_exists(path)) { *out_result = mval_bool(0); return 1; }
            *out_result = mval_bool(remove(path) == 0);
            return 1;
        default: /* 72: fs_mkdir */
            make_dirs(path);
            *out_result = mval_bool(file_exists(path));
            return 1;
        }
    }

    if (id >= 74 && id <= 78) {
        /* file_* stays under the storage base, like the Python sandbox does. */
        path_clean(arg_ptr(args, argc, 0), clean, sizeof clean);
        if (!join_under_base(path, sizeof path, base, clean)) {
            set_error(error, error_cap, ERR_FILE_TRAVERSAL);
            return 0;
        }
        switch (id) {
        case 74: /* file_read */
            if (!storage_read_text(path, out_result, error, error_cap)) return 0;
            return 1;
        case 75: /* file_write */
        case 76: /* file_append */
            if (!file_exists(base)) make_dirs(base);
            if (!storage_write_text(path, arg_ptr(args, argc, 1), id == 76, 0, error, error_cap)) return 0;
            *out_result = mval_bool(1);
            return 1;
        case 77: /* file_exists */
            *out_result = mval_bool(file_exists(path));
            return 1;
        default: /* 78: file_delete */
            if (!file_exists(path)) { *out_result = mval_bool(0); return 1; }
            *out_result = mval_bool(remove(path) == 0);
            return 1;
        }
    }

    return 0;
}
