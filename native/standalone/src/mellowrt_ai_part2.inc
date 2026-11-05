/* AI runtime fragment 2: UTF-8 walking, rounding, and checkpoint paths. */

static int ai_utf8_decode(const char *text, size_t len, size_t *pos, int32_t *cp) {
    size_t i = *pos;
    unsigned char c;
    if (i >= len) return 0;
    c = (unsigned char)text[i];
    if (c < 0x80) { *cp = c; *pos = i + 1; return 1; }
    if ((c & 0xe0) == 0xc0 && i + 1 < len) {
        *cp = ((int32_t)(c & 0x1f) << 6) | ((unsigned char)text[i + 1] & 0x3f);
        *pos = i + 2;
        return 1;
    }
    if ((c & 0xf0) == 0xe0 && i + 2 < len) {
        *cp = ((int32_t)(c & 0x0f) << 12) |
              ((int32_t)((unsigned char)text[i + 1] & 0x3f) << 6) |
              ((unsigned char)text[i + 2] & 0x3f);
        *pos = i + 3;
        return 1;
    }
    if ((c & 0xf8) == 0xf0 && i + 3 < len) {
        *cp = ((int32_t)(c & 0x07) << 18) |
              ((int32_t)((unsigned char)text[i + 1] & 0x3f) << 12) |
              ((int32_t)((unsigned char)text[i + 2] & 0x3f) << 6) |
              ((unsigned char)text[i + 3] & 0x3f);
        *pos = i + 4;
        return 1;
    }
    *cp = c;
    *pos = i + 1;
    return 1;
}

static int ai_utf8_encode(int32_t cp, char out[4]) {
    if (cp < 0x80) { out[0] = (char)cp; return 1; }
    if (cp < 0x800) {
        out[0] = (char)(0xc0 | (cp >> 6));
        out[1] = (char)(0x80 | (cp & 0x3f));
        return 2;
    }
    if (cp < 0x10000) {
        out[0] = (char)(0xe0 | (cp >> 12));
        out[1] = (char)(0x80 | ((cp >> 6) & 0x3f));
        out[2] = (char)(0x80 | (cp & 0x3f));
        return 3;
    }
    out[0] = (char)(0xf0 | (cp >> 18));
    out[1] = (char)(0x80 | ((cp >> 12) & 0x3f));
    out[2] = (char)(0x80 | ((cp >> 6) & 0x3f));
    out[3] = (char)(0x80 | (cp & 0x3f));
    return 4;
}

static size_t ai_utf8_count(const char *text, size_t len) {
    size_t pos = 0, count = 0;
    int32_t cp;
    while (pos < len && ai_utf8_decode(text, len, &pos, &cp)) ++count;
    return count;
}

/* Byte offset of the character index, clamped to len. */
static size_t ai_utf8_offset(const char *text, size_t len, size_t chars) {
    size_t pos = 0;
    int32_t cp;
    while (chars && pos < len && ai_utf8_decode(text, len, &pos, &cp)) --chars;
    return pos;
}

/* First `count` characters of text (Python text[:count]). Caller frees. */
static char *ai_utf8_prefix(const char *text, size_t len, size_t count, size_t *out_len) {
    size_t offset = ai_utf8_offset(text, len, count);
    char *copy = (char *)calloc(offset + 1, 1);
    if (!copy) { if (out_len) *out_len = 0; return NULL; }
    if (offset) memcpy(copy, text, offset);
    if (out_len) *out_len = offset;
    return copy;
}

static double ai_round6(double value) {
    if (!isfinite(value)) return value;
    return round(value * 1000000.0) / 1000000.0;
}

static const char *ai_base_name(const char *path) {
    const char *base = path ? path : "";
    const char *p;
    if (!path) return "";
    for (p = path; *p; ++p)
        if (*p == '/' || *p == '\\') base = p + 1;
    return base;
}

/* Build "mellow_models/<basename><ext>"; creates the folder. Returns 0 on overflow. */
#ifdef _WIN32
#define AI_PATH_SEP "\\"
#else
#define AI_PATH_SEP "/"
#endif
static int ai_model_path(const MValue *name_value, const char *ext, char *out, size_t cap) {
    char raw[512];
    size_t len;
    char *text = ai_value_text(name_value, &len);
    const char *base;
    int written;
    if (!text) return 0;
    while (len > 0 && (text[len - 1] == '/' || text[len - 1] == '\\')) text[--len] = '\0';
    base = ai_base_name(text);
    written = snprintf(raw, sizeof(raw), "%s", base);
    free(text);
    if (written < 0) return 0;
    len = strlen(raw);
    {
        size_t ext_len = strlen(ext);
        if (ext_len < sizeof(raw) - len && (len < ext_len || strcmp(raw + len - ext_len, ext) != 0))
            strncat(raw, ext, sizeof(raw) - len - 1);
    }
    if (strlen(raw) > sizeof(raw) - 16) return 0;
#ifdef _WIN32
    _mkdir("mellow_models");
#else
    mkdir("mellow_models", 0777);
#endif
    written = snprintf(out, cap, "mellow_models%s%s", AI_PATH_SEP, raw);
    return written > 0 && (size_t)written < cap;
}

static char *ai_read_file(const char *path, size_t *out_len) {
    FILE *fp = fopen(path, "rb");
    long size;
    char *buffer;
    size_t read;
    if (!fp) return NULL;
    if (fseek(fp, 0, SEEK_END) != 0) { fclose(fp); return NULL; }
    size = ftell(fp);
    if (size < 0) { fclose(fp); return NULL; }
    rewind(fp);
    buffer = (char *)calloc((size_t)size + 1, 1);
    if (!buffer) { fclose(fp); return NULL; }
    read = fread(buffer, 1, (size_t)size, fp);
    fclose(fp);
    buffer[read] = '\0';
    if (out_len) *out_len = read;
    return buffer;
}

static int ai_write_file(const char *path, const char *text, size_t len) {
    FILE *fp = fopen(path, "wb");
    size_t written;
    if (!fp) return 0;
    written = fwrite(text, 1, len, fp);
    return fclose(fp) == 0 && written == len;
}
