/* ── tree copy and removal ───────────────────────────────────────────────── */

static int pk_is_abs(const char *path) {
    if (!path || !*path) return 0;
#if defined(_WIN32)
    if (path[0] == '/' || path[0] == '\\') return 1;
    return isalpha((unsigned char)path[0]) && path[1] == ':';
#else
    return path[0] == '/';
#endif
}

/* Absolute, separator-normalized path with "." and ".." segments resolved. */
static void pk_resolve_path(const char *base, const char *path, char *out, size_t cap) {
    char raw[PKG_PATH_MAX];
    size_t o = 0;
    size_t i = 0;
    if (!out || cap == 0) return;
    if (pk_is_abs(path)) snprintf(raw, sizeof raw, "%s", path);
    else pk_join(raw, sizeof raw, base && *base ? base : ".", path ? path : ".");
    pk_slashes(raw);
    i = (isalpha((unsigned char)raw[0]) && raw[1] == ':') ? 2 : 0;
    if (i == 2) {
        out[o++] = raw[0];
        out[o++] = ':';
    }
    if (raw[i] == '/') out[o++] = '/';
    while (raw[i] && o + 1 < cap) {
        size_t start;
        size_t len;
        while (raw[i] == '/') ++i;
        start = i;
        while (raw[i] && raw[i] != '/') ++i;
        len = i - start;
        if (!len) break;
        if (len == 1 && raw[start] == '.') continue;
        if (len == 2 && raw[start] == '.' && raw[start + 1] == '.') {
            while (o > 0 && out[o - 1] != '/' && out[o - 1] != ':') --o;
            while (o > 1 && out[o - 1] == '/') --o;
            continue;
        }
        if (o > 0 && out[o - 1] != '/') out[o++] = '/';
        if (len > cap - 1 - o) len = cap - 1 - o;
        memcpy(out + o, raw + start, len);
        o += len;
    }
    if (!o) out[o++] = '.';
    out[o] = '\0';
}

static int pk_iprefix(const char *path, const char *prefix) {
    size_t n;
    size_t i;
    if (!path || !prefix) return 0;
    n = strlen(prefix);
    if (strlen(path) < n) return 0;
    for (i = 0; i < n; ++i) {
        if (tolower((unsigned char)path[i]) != tolower((unsigned char)prefix[i])) return 0;
    }
    return path[n] == '\0' || path[n] == '/';
}

static int pk_copy_file(const char *src, const char *dst) {
    PkgBuf data = {0};
    int ok;
    if (!pk_read_file(src, &data)) return 0;
    ok = pk_write_file(dst, data.ptr ? data.ptr : "", data.len);
    pk_buf_free(&data);
    return ok;
}

static int pk_copy_tree(const char *src, const char *dst, int depth, const char *skip) {
    PkgList dirs = {0};
    PkgList files = {0};
    char from[PKG_PATH_MAX];
    char to[PKG_PATH_MAX];
    int i;
    int ok = 1;
    if (depth > PKG_MAX_DEPTH || !pk_isdir(src)) return 0;
    if (!pk_mkdirs(dst)) return 0;
    pk_list_dir(src, 0, &files);
    pk_list_dir(src, 1, &dirs);
    for (i = 0; i < files.count && ok; ++i) {
        pk_join(from, sizeof from, src, files.items[i]);
        pk_join(to, sizeof to, dst, files.items[i]);
        ok = pk_copy_file(from, to);
    }
    for (i = 0; i < dirs.count && ok; ++i) {
        pk_join(from, sizeof from, src, dirs.items[i]);
        if (skip && pk_iprefix(from, skip)) continue;
        pk_join(to, sizeof to, dst, dirs.items[i]);
        ok = pk_copy_tree(from, to, depth + 1, skip);
    }
    pk_list_free(&files);
    pk_list_free(&dirs);
    return ok;
}

static int pk_remove_tree(const char *path) {
    PkgList dirs = {0};
    PkgList files = {0};
    char full[PKG_PATH_MAX];
    int i;
    int ok = 1;
    if (!pk_exists(path)) return 1;
    if (!pk_isdir(path)) return remove(path) == 0;
    pk_list_dir(path, 0, &files);
    pk_list_dir(path, 1, &dirs);
    for (i = 0; i < files.count && ok; ++i) {
        pk_join(full, sizeof full, path, files.items[i]);
        ok = remove(full) == 0;
    }
    for (i = 0; i < dirs.count && ok; ++i) {
        pk_join(full, sizeof full, path, dirs.items[i]);
        ok = pk_remove_tree(full);
    }
    pk_list_free(&files);
    pk_list_free(&dirs);
    if (!ok) return 0;
    return PKG_RMDIR(path) == 0 || !pk_exists(path);
}

/* ── names and versions ──────────────────────────────────────────────────── */

static void pk_normalize_name(const char *name, char *out, size_t cap) {
    size_t i = 0, j = 0;
    if (!out || cap == 0) return;
    for (i = 0; name && name[i] && j + 1 < cap; ++i) {
        unsigned char c = (unsigned char)name[i];
        if (isalnum(c) || c == '-' || c == '_' || c == '/' || c == '@' || c == '.')
            out[j++] = (char)tolower(c);
        else
            out[j++] = '-';
    }
    while (j > 0 && out[j - 1] == '-') j--;
    out[j] = '\0';
    if (j == 0) snprintf(out, cap, "pkg");
}

/* Split "@scope/name@1.2.3" into the registry name and an optional version. */
static void pk_split_ref(const char *ref, char *name, size_t name_cap, char *version, size_t version_cap) {
    const char *at;
    size_t len;
    if (version && version_cap) version[0] = '\0';
    if (!ref) {
        if (name && name_cap) name[0] = '\0';
        return;
    }
    at = strrchr(ref, '@');
    if (at && at != ref) {
        const char *v = at + 1;
        int valid = *v != '\0';
        const char *p;
        for (p = v; *p; ++p) {
            if (!(isalnum((unsigned char)*p) || *p == '.' || *p == '+' || *p == '-')) {
                valid = 0;
                break;
            }
        }
        if (valid && version && version_cap) {
            snprintf(version, version_cap, "%s", v);
            len = (size_t)(at - ref);
            if (len >= name_cap) len = name_cap - 1;
            if (name && name_cap) {
                memcpy(name, ref, len);
                name[len] = '\0';
                pk_normalize_name(name, name, name_cap);
            }
            return;
        }
    }
    if (name && name_cap) pk_normalize_name(ref, name, name_cap);
}

typedef struct {
    int parts[3];
} PkgVersionKey;

static void pk_version_key(const char *version, PkgVersionKey *key) {
    const char *p = version;
    int index = 0;
    memset(key, 0, sizeof *key);
    while (p && *p && index < 3) {
        if (isdigit((unsigned char)*p)) {
            long value = strtol(p, (char **)&p, 10);
            key->parts[index++] = (int)value;
        } else {
            ++p;
        }
    }
}

static int pk_key_cmp(const PkgVersionKey *a, const PkgVersionKey *b) {
    int i;
    for (i = 0; i < 3; ++i) {
        if (a->parts[i] != b->parts[i]) return a->parts[i] < b->parts[i] ? -1 : 1;
    }
    return 0;
}

static int pk_key_satisfies(const PkgVersionKey *value, const char *part) {
    PkgVersionKey bound;
    char op[3] = {0};
    const char *rest = part;
    if (!part || !*part) return 1;
    if (!strcmp(part, "*") || pk_ieq(part, "latest")) return 1;
    if (!strncmp(part, ">=", 2) || !strncmp(part, "<=", 2)) {
        op[0] = part[0];
        op[1] = part[1];
        rest = part + 2;
    } else if (*part == '>' || *part == '<') {
        op[0] = part[0];
        rest = part + 1;
    }
    pk_version_key(rest, &bound);
    if (op[0] == '>') return op[1] == '=' ? pk_key_cmp(value, &bound) >= 0 : pk_key_cmp(value, &bound) > 0;
    if (op[0] == '<') return op[1] == '=' ? pk_key_cmp(value, &bound) <= 0 : pk_key_cmp(value, &bound) < 0;
    return pk_key_cmp(value, &bound) == 0;
}

static int pk_version_satisfies(const char *version, const char *spec) {
    char copy[256];
    char *token;
    PkgVersionKey value;
    if (!spec || !*spec || !strcmp(spec, "*") || pk_ieq(spec, "latest")) return 1;
    if (pk_ieq(spec, "host") || pk_ieq(spec, "builtin") || pk_ieq(spec, "built-in") || pk_ieq(spec, "internal"))
        return 1;
    snprintf(copy, sizeof copy, "%s", spec);
    token = strtok(copy, ", ");
    pk_version_key(version, &value);
    while (token) {
        token = pk_trim(token);
        if (token[0] == '^') {
            PkgVersionKey base;
            pk_version_key(token + 1, &base);
            if (value.parts[0] != base.parts[0] || pk_key_cmp(&value, &base) < 0) return 0;
        } else if (token[0] == '~') {
            PkgVersionKey base;
            pk_version_key(token + 1, &base);
            if (value.parts[0] != base.parts[0] || value.parts[1] != base.parts[1] ||
                pk_key_cmp(&value, &base) < 0)
                return 0;
        } else if (!pk_key_satisfies(&value, token)) {
            return 0;
        }
        token = strtok(NULL, ", ");
    }
    return 1;
}

/* Highest version matching spec; falls back to highest when spec is open. */
static int pk_choose_version(const PkgList *versions, const char *spec, char *out, size_t cap) {
    int i;
    int found = -1;
    PkgVersionKey best = {{0, 0, 0}};
    int open = !spec || !*spec || !strcmp(spec, "*") || pk_ieq(spec, "latest");
    for (i = 0; i < versions->count; ++i) {
        PkgVersionKey key;
        if (!pk_version_satisfies(versions->items[i], spec)) continue;
        pk_version_key(versions->items[i], &key);
        if (found < 0 || pk_key_cmp(&key, &best) > 0) {
            best = key;
            found = i;
        }
    }
    if (found < 0 && open && versions->count) found = versions->count - 1;
    if (found < 0) return 0;
    snprintf(out, cap, "%s", versions->items[found]);
    return 1;
}
