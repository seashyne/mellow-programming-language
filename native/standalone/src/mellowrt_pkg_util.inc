/* ── string buffers ──────────────────────────────────────────────────────── */

typedef struct {
    char *ptr;
    size_t len;
    size_t cap;
} PkgBuf;

static int pk_buf_reserve(PkgBuf *b, size_t extra) {
    size_t want;
    char *next;
    if (!b) return 0;
    want = b->len + extra + 1;
    if (want <= b->cap) return 1;
    want = want < 128 ? 128 : want * 2;
    next = (char *)realloc(b->ptr, want);
    if (!next) return 0;
    if (!b->ptr) next[0] = '\0';
    b->ptr = next;
    b->cap = want;
    return 1;
}

static int pk_buf_put(PkgBuf *b, const char *text, size_t len) {
    if (!pk_buf_reserve(b, len)) return 0;
    if (len) memcpy(b->ptr + b->len, text, len);
    b->len += len;
    b->ptr[b->len] = '\0';
    return 1;
}

static int pk_buf_puts(PkgBuf *b, const char *text) {
    return text ? pk_buf_put(b, text, strlen(text)) : 0;
}

static int pk_buf_putc(PkgBuf *b, char c) {
    return pk_buf_put(b, &c, 1);
}

static void pk_buf_free(PkgBuf *b) {
    if (!b) return;
    free(b->ptr);
    b->ptr = NULL;
    b->len = 0;
    b->cap = 0;
}

static char *pk_strdup(const char *text) {
    size_t len;
    char *copy;
    if (!text) return NULL;
    len = strlen(text);
    copy = (char *)malloc(len + 1);
    if (!copy) return NULL;
    memcpy(copy, text, len + 1);
    return copy;
}

static char *pk_trim(char *text) {
    char *end;
    if (!text) return text;
    while (*text == ' ' || *text == '\t' || *text == '\r' || *text == '\n') text++;
    end = text + strlen(text);
    while (end > text) {
        char c = end[-1];
        if (c != ' ' && c != '\t' && c != '\r' && c != '\n') break;
        *--end = '\0';
    }
    return text;
}

static int pk_ieq(const char *a, const char *b) {
    if (!a || !b) return 0;
    while (*a && *b) {
        if (tolower((unsigned char)*a) != tolower((unsigned char)*b)) return 0;
        ++a;
        ++b;
    }
    return *a == '\0' && *b == '\0';
}

/* ── paths ───────────────────────────────────────────────────────────────── */

static void pk_slashes(char *path) {
    char *p;
    for (p = path; p && *p; ++p) {
        if (*p == '\\') *p = '/';
    }
}

static int pk_join(char *out, size_t cap, const char *a, const char *b) {
    size_t n;
    if (!out || cap == 0 || !a || !b) return 0;
    n = strlen(a);
    if (n && (a[n - 1] == '/' || a[n - 1] == '\\'))
        snprintf(out, cap, "%s%s", a, b);
    else
        snprintf(out, cap, "%s/%s", a, b);
    out[cap - 1] = '\0';
    pk_slashes(out);
    return 1;
}

/* Append to a path in place; snprintf must not see the same buffer twice. */
static int pk_join2(char *out, size_t cap, const char *child) {
    char base[PKG_PATH_MAX];
    if (!out || cap == 0) return 0;
    snprintf(base, sizeof base, "%s", out);
    return pk_join(out, cap, base, child);
}

static int pk_basename(const char *path, char *out, size_t cap) {
    const char *end;
    const char *start;
    size_t len;
    if (!path || !out || cap == 0) return 0;
    end = path + strlen(path);
    while (end > path && (end[-1] == '/' || end[-1] == '\\')) --end;
    start = end;
    while (start > path && start[-1] != '/' && start[-1] != '\\') --start;
    len = (size_t)(end - start);
    if (len >= cap) len = cap - 1;
    memcpy(out, start, len);
    out[len] = '\0';
    return len > 0;
}

static int pk_dirname(const char *path, char *out, size_t cap) {
    const char *end;
    size_t len;
    if (!path || !out || cap == 0) return 0;
    end = path + strlen(path);
    while (end > path && (end[-1] == '/' || end[-1] == '\\')) --end;
    while (end > path && end[-1] != '/' && end[-1] != '\\') --end;
    len = (size_t)(end - path);
    while (len > 1 && (path[len - 1] == '/' || path[len - 1] == '\\')) --len;
    if (len >= cap) len = cap - 1;
    memcpy(out, path, len);
    out[len] = '\0';
    if (len == 0) {
        snprintf(out, cap, ".");
    }
    return 1;
}

static int pk_exists(const char *path) {
    struct stat info;
    return path && stat(path, &info) == 0;
}

static int pk_isdir(const char *path) {
#ifdef _WIN32
    DWORD attrs;
    if (!path) return 0;
    attrs = GetFileAttributesA(path);
    return attrs != INVALID_FILE_ATTRIBUTES && (attrs & FILE_ATTRIBUTE_DIRECTORY) != 0;
#else
    DIR *dir;
    if (!path) return 0;
    dir = opendir(path);
    if (!dir) return 0;
    closedir(dir);
    return 1;
#endif
}

static int pk_read_file(const char *path, PkgBuf *out) {
    FILE *fp;
    char chunk[4096];
    size_t got;
    if (!path || !out) return 0;
    fp = fopen(path, "rb");
    if (!fp) return 0;
    while ((got = fread(chunk, 1, sizeof chunk, fp)) > 0) {
        if (!pk_buf_put(out, chunk, got)) {
            fclose(fp);
            return 0;
        }
    }
    fclose(fp);
    if (!out->ptr && !pk_buf_reserve(out, 0)) return 0;
    return 1;
}

static int pk_write_file(const char *path, const char *data, size_t len) {
    FILE *fp;
    if (!path) return 0;
    fp = fopen(path, "wb");
    if (!fp) return 0;
    if (len && fwrite(data, 1, len, fp) != len) {
        fclose(fp);
        return 0;
    }
    return fclose(fp) == 0;
}

static int pk_mkdirs(const char *path) {
    char buf[PKG_PATH_MAX];
    size_t i;
    if (!path || strlen(path) >= sizeof buf) return 0;
    snprintf(buf, sizeof buf, "%s", path);
    for (i = 1; buf[i]; ++i) {
        if (buf[i] == '/' || buf[i] == '\\') {
            char saved = buf[i];
            buf[i] = '\0';
            PKG_MKDIR(buf);
            buf[i] = saved;
        }
    }
    if (pk_isdir(buf)) return 1;
    PKG_MKDIR(buf);
    return pk_isdir(buf);
}

/* ── directory listings ──────────────────────────────────────────────────── */

typedef struct {
    char **items;
    int count;
    int cap;
} PkgList;

static void pk_list_free(PkgList *list) {
    int i;
    if (!list) return;
    for (i = 0; i < list->count; ++i) free(list->items[i]);
    free(list->items);
    list->items = NULL;
    list->count = 0;
    list->cap = 0;
}

static int pk_list_push(PkgList *list, const char *name) {
    char **next;
    if (list->count == list->cap) {
        int cap = list->cap ? list->cap * 2 : 8;
        next = (char **)realloc(list->items, sizeof(char *) * (size_t)cap);
        if (!next) return 0;
        list->items = next;
        list->cap = cap;
    }
    list->items[list->count] = pk_strdup(name);
    if (!list->items[list->count]) return 0;
    list->count++;
    return 1;
}

static int pk_list_cmp(const void *a, const void *b) {
    return strcmp(*(char *const *)a, *(char *const *)b);
}

static int pk_list_dir(const char *dir, int want_dirs, PkgList *out) {
    if (!dir || !out || !pk_isdir(dir)) return 0;
#ifdef _WIN32
    {
        char pattern[PKG_PATH_MAX];
        WIN32_FIND_DATAA entry;
        HANDLE handle;
        snprintf(pattern, sizeof pattern, "%s/*", dir);
        handle = FindFirstFileA(pattern, &entry);
        if (handle == INVALID_HANDLE_VALUE) return 1;
        do {
            int is_dir = (entry.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) != 0;
            if (!strcmp(entry.cFileName, ".") || !strcmp(entry.cFileName, "..")) continue;
            if (is_dir != want_dirs) continue;
            pk_list_push(out, entry.cFileName);
        } while (FindNextFileA(handle, &entry));
        FindClose(handle);
    }
#else
    {
        DIR *dp = opendir(dir);
        struct dirent *entry;
        char full[PKG_PATH_MAX];
        if (!dp) return 0;
        while ((entry = readdir(dp)) != NULL) {
            if (!strcmp(entry->d_name, ".") || !strcmp(entry->d_name, "..")) continue;
            pk_join(full, sizeof full, dir, entry->d_name);
            if (pk_isdir(full) != want_dirs) continue;
            pk_list_push(out, entry->d_name);
        }
        closedir(dp);
    }
#endif
    if (out->count > 1) qsort(out->items, (size_t)out->count, sizeof(char *), pk_list_cmp);
    return 1;
}

#include "mellowrt_pkg_util_part1.inc"
