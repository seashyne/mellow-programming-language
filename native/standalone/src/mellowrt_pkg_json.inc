/* ── minimal JSON tree (manifests, lockfile, aliases) ────────────────────── */

typedef enum { PJ_NULL, PJ_BOOL, PJ_NUMBER, PJ_STRING, PJ_ARRAY, PJ_OBJECT } PjType;

typedef struct PjValue {
    PjType type;
    int boolean;
    double number;
    char *string;
    struct PjValue **items;
    char **keys;
    size_t count;
    size_t cap;
} PjValue;

static PjValue *pj_new(PjType type) {
    PjValue *value = (PjValue *)calloc(1, sizeof(PjValue));
    if (value) value->type = type;
    return value;
}

static void pj_free(PjValue *value) {
    size_t i;
    if (!value) return;
    free(value->string);
    for (i = 0; i < value->count; ++i) {
        if (value->keys) free(value->keys[i]);
        pj_free(value->items[i]);
    }
    free(value->keys);
    free(value->items);
    free(value);
}

static PjValue *pj_new_string(const char *text) {
    PjValue *value = pj_new(PJ_STRING);
    if (!value) return NULL;
    value->string = pk_strdup(text ? text : "");
    if (!value->string) {
        free(value);
        return NULL;
    }
    return value;
}

static PjValue *pj_new_number(double number) {
    PjValue *value = pj_new(PJ_NUMBER);
    if (value) value->number = number;
    return value;
}

static int pj_grow(PjValue *value) {
    size_t cap = value->cap ? value->cap * 2 : 4;
    PjValue **items = (PjValue **)realloc(value->items, sizeof(PjValue *) * cap);
    if (!items) return 0;
    value->items = items;
    if (value->type == PJ_OBJECT) {
        char **keys = (char **)realloc(value->keys, sizeof(char *) * cap);
        if (!keys) return 0;
        value->keys = keys;
    }
    value->cap = cap;
    return 1;
}

static int pj_obj_set(PjValue *object, const char *key, PjValue *child) {
    if (!object || object->type != PJ_OBJECT || !child) return 0;
    if (object->count == object->cap && !pj_grow(object)) return 0;
    object->keys[object->count] = pk_strdup(key ? key : "");
    if (!object->keys[object->count]) return 0;
    object->items[object->count] = child;
    object->count++;
    return 1;
}

static int pj_arr_push(PjValue *array, PjValue *child) {
    if (!array || array->type != PJ_ARRAY || !child) return 0;
    if (array->count == array->cap && !pj_grow(array)) return 0;
    array->items[array->count++] = child;
    return 1;
}

static PjValue *pj_obj_get(const PjValue *object, const char *key) {
    size_t i;
    if (!object || object->type != PJ_OBJECT) return NULL;
    for (i = 0; i < object->count; ++i) {
        if (!strcmp(object->keys[i], key)) return object->items[i];
    }
    return NULL;
}

static const char *pj_str(const PjValue *object, const char *key, const char *fallback) {
    PjValue *value = pj_obj_get(object, key);
    return (value && value->type == PJ_STRING && value->string) ? value->string : fallback;
}

static int pj_bool(const PjValue *object, const char *key, int fallback) {
    PjValue *value = pj_obj_get(object, key);
    return (value && value->type == PJ_BOOL) ? value->boolean : fallback;
}

static const char *pj_skip(const char *p, const char *end) {
    while (p < end && (*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n')) ++p;
    return p;
}

static void pj_utf8(PkgBuf *out, unsigned long code) {
    if (code < 0x80) {
        pk_buf_putc(out, (char)code);
    } else if (code < 0x800) {
        pk_buf_putc(out, (char)(0xC0 | (code >> 6)));
        pk_buf_putc(out, (char)(0x80 | (code & 0x3F)));
    } else {
        pk_buf_putc(out, (char)(0xE0 | (code >> 12)));
        pk_buf_putc(out, (char)(0x80 | ((code >> 6) & 0x3F)));
        pk_buf_putc(out, (char)(0x80 | (code & 0x3F)));
    }
}

static const char *pj_parse_string(const char *p, const char *end, char **out) {
    PkgBuf buf = {0};
    if (p >= end || *p != '"') return NULL;
    ++p;
    while (p < end && *p != '"') {
        if (*p == '\\' && p + 1 < end) {
            ++p;
            switch (*p) {
            case 'n': pk_buf_putc(&buf, '\n'); break;
            case 't': pk_buf_putc(&buf, '\t'); break;
            case 'r': pk_buf_putc(&buf, '\r'); break;
            case 'b': pk_buf_putc(&buf, '\b'); break;
            case 'f': pk_buf_putc(&buf, '\f'); break;
            case 'u': {
                unsigned long code = 0;
                int i;
                if (end - p < 5) { pk_buf_free(&buf); return NULL; }
                for (i = 1; i <= 4; ++i) {
                    char c = p[i];
                    code <<= 4;
                    if (c >= '0' && c <= '9') code |= (unsigned long)(c - '0');
                    else if (c >= 'a' && c <= 'f') code |= (unsigned long)(c - 'a' + 10);
                    else if (c >= 'A' && c <= 'F') code |= (unsigned long)(c - 'A' + 10);
                    else { pk_buf_free(&buf); return NULL; }
                }
                pj_utf8(&buf, code);
                p += 4;
                break;
            }
            default: pk_buf_putc(&buf, *p); break;
            }
            ++p;
        } else {
            pk_buf_putc(&buf, *p++);
        }
    }
    if (p >= end) {
        pk_buf_free(&buf);
        return NULL;
    }
    *out = buf.ptr ? buf.ptr : pk_strdup("");
    return p + 1;
}
static const char *pj_parse_value(const char *p, const char *end, PjValue **out, int depth);
static const char *pj_parse_array(const char *p, const char *end, PjValue **out, int depth) {
    PjValue *array = pj_new(PJ_ARRAY);
    if (!array) return NULL;
    ++p;
    p = pj_skip(p, end);
    if (p < end && *p == ']') {
        *out = array;
        return p + 1;
    }
    for (;;) {
        PjValue *child = NULL;
        p = pj_parse_value(p, end, &child, depth + 1);
        if (!p || !pj_arr_push(array, child)) {
            pj_free(child);
            pj_free(array);
            return NULL;
        }
        p = pj_skip(p, end);
        if (p < end && *p == ',') { p = pj_skip(p + 1, end); continue; }
        if (p < end && *p == ']') {
            *out = array;
            return p + 1;
        }
        pj_free(array);
        return NULL;
    }
}

static const char *pj_parse_object(const char *p, const char *end, PjValue **out, int depth) {
    PjValue *object = pj_new(PJ_OBJECT);
    if (!object) return NULL;
    ++p;
    p = pj_skip(p, end);
    if (p < end && *p == '}') {
        *out = object;
        return p + 1;
    }
    for (;;) {
        char *key = NULL;
        PjValue *child = NULL;
        p = pj_skip(p, end);
        p = pj_parse_string(p, end, &key);
        if (!p) {
            pj_free(object);
            return NULL;
        }
        p = pj_skip(p, end);
        if (p >= end || *p != ':') {
            free(key);
            pj_free(object);
            return NULL;
        }
        p = pj_skip(p + 1, end);
        p = pj_parse_value(p, end, &child, depth + 1);
        if (!p) {
            free(key);
            pj_free(object);
            return NULL;
        }
        if (!pj_obj_set(object, key, child)) {
            free(key);
            pj_free(child);
            pj_free(object);
            return NULL;
        }
        free(key);
        p = pj_skip(p, end);
        if (p < end && *p == ',') { p = pj_skip(p + 1, end); continue; }
        if (p < end && *p == '}') {
            *out = object;
            return p + 1;
        }
        pj_free(object);
        return NULL;
    }
}

static const char *pj_parse_value(const char *p, const char *end, PjValue **out, int depth) {
    PjValue *value = NULL;
    if (!p || depth > 64) return NULL;
    p = pj_skip(p, end);
    if (p >= end) return NULL;
    if (*p == '{') return pj_parse_object(p, end, out, depth);
    if (*p == '[') return pj_parse_array(p, end, out, depth);
    if (*p == '"') {
        char *text = NULL;
        const char *next = pj_parse_string(p, end, &text);
        if (next && (value = pj_new_string(text))) {
            free(text);
            *out = value;
        } else {
            free(text);
        }
        return value ? next : NULL;
    }
    if (end - p >= 4 && !strncmp(p, "true", 4)) {
        value = pj_new(PJ_BOOL);
        if (value) value->boolean = 1;
        *out = value;
        return value ? p + 4 : NULL;
    }
    if (end - p >= 5 && !strncmp(p, "false", 5)) {
        value = pj_new(PJ_BOOL);
        *out = value;
        return value ? p + 5 : NULL;
    }
    if (end - p >= 4 && !strncmp(p, "null", 4)) {
        *out = pj_new(PJ_NULL);
        return *out ? p + 4 : NULL;
    }
    {
        char *stop = NULL;
        double number = strtod(p, &stop);
        if (stop == p) return NULL;
        value = pj_new_number(number);
        if (!value) return NULL;
        *out = value;
        return stop;
    }
}

static PjValue *pj_parse(const char *text, size_t len) {
    PjValue *value = NULL;
    const char *end = text + len;
    const char *next = pj_parse_value(text, end, &value, 0);
    if (!next) {
        pj_free(value);
        return NULL;
    }
    next = pj_skip(next, end);
    if (next != end) {
        pj_free(value);
        return NULL;
    }
    return value;
}
#include "mellowrt_pkg_json_part1.inc"
