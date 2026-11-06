/* ── registry configuration and JSON requests ───────────────────────────── */

static int pk_config_file(char *out, size_t cap) {
    const char *dir = getenv("MELLOW_CONFIG_DIR");
    if (dir && *dir) return pk_join(out, cap, dir, "config.json");
#ifdef _WIN32
    dir = getenv("USERPROFILE");
#else
    dir = getenv("HOME");
#endif
    if (!dir || !*dir) return 0;
    snprintf(out, cap, "%s/.mellow/config.json", dir);
    pk_slashes(out);
    return 1;
}

static const char *pk_registry_url(const char *explicit_url) {
    static char resolved[PKG_PATH_MAX];
    const char *env_url = getenv("MELLOW_REGISTRY_URL");
    char path[PKG_PATH_MAX];
    size_t len;
    resolved[0] = '\0';
    if (explicit_url && *explicit_url)
        snprintf(resolved, sizeof resolved, "%s", explicit_url);
    else if (env_url && *env_url)
        snprintf(resolved, sizeof resolved, "%s", env_url);
    if (!resolved[0] && pk_config_file(path, sizeof path)) {
        PkgBuf data = {0};
        if (pk_read_file(path, &data) && data.ptr) {
            PjValue *root = pj_parse(data.ptr, data.len);
            const char *value = pj_str(root, "registry", NULL);
            if (value) snprintf(resolved, sizeof resolved, "%s", value);
            pj_free(root);
        }
        pk_buf_free(&data);
    }
    if (!resolved[0]) snprintf(resolved, sizeof resolved, "%s", PKG_DEFAULT_REGISTRY);
    len = strlen(resolved);
    while (len > 8 && resolved[len - 1] == '/') resolved[--len] = '\0';
    return resolved;
}

static const char *pk_registry_token(const char *registry) {
    static char token[1024];
    const char *env_token = getenv("MELLOW_PUBLISH_TOKEN");
    char path[PKG_PATH_MAX];
    token[0] = '\0';
    if (!env_token || !*env_token) env_token = getenv("MELLOW_REGISTRY_TOKEN");
    if (env_token && *env_token) snprintf(token, sizeof token, "%s", env_token);
    if (!token[0] && registry && *registry && pk_config_file(path, sizeof path)) {
        PkgBuf data = {0};
        if (pk_read_file(path, &data) && data.ptr) {
            PjValue *root = pj_parse(data.ptr, data.len);
            const char *value = pj_str(pj_obj_get(root, "auth"), registry, NULL);
            if (value) snprintf(token, sizeof token, "%s", value);
            pj_free(root);
        }
        pk_buf_free(&data);
    }
    return token[0] ? token : NULL;
}

static void pk_url_encode(const char *text, PkgBuf *out) {
    const unsigned char *p = (const unsigned char *)(text ? text : "");
    for (; *p; ++p) {
        if (isalnum(*p) || *p == '-' || *p == '_' || *p == '.' || *p == '~') {
            pk_buf_putc(out, (char)*p);
        } else {
            char escape[4];
            snprintf(escape, sizeof escape, "%%%02X", (unsigned)*p);
            pk_buf_puts(out, escape);
        }
    }
}

/* Registry names may keep `@`, `/`, `-`, `_` and `.` unescaped. */
static void pk_url_quote_path(const char *text, PkgBuf *out) {
    const unsigned char *p = (const unsigned char *)(text ? text : "");
    for (; *p; ++p) {
        if (isalnum(*p) || *p == '@' || *p == '/' || *p == '-' || *p == '_' || *p == '.') {
            pk_buf_putc(out, (char)*p);
        } else {
            char escape[4];
            snprintf(escape, sizeof escape, "%%%02X", (unsigned)*p);
            pk_buf_puts(out, escape);
        }
    }
}

static void pk_join_string_array(const PjValue *array, char *out, size_t cap, const char *sep) {
    size_t used = 0;
    size_t i;
    if (!out || !cap) return;
    out[0] = '\0';
    if (!array || array->type != PJ_ARRAY) return;
    for (i = 0; i < array->count; ++i) {
        const PjValue *item = array->items[i];
        const char *text = item && item->type == PJ_STRING ? item->string : NULL;
        int wrote;
        if (!text || !*text) continue;
        wrote = snprintf(out + used, cap - used, "%s%s", used ? sep : "", text);
        if (wrote < 0 || (size_t)wrote >= cap - used) break;
        used += (size_t)wrote;
    }
}

static PjValue *pk_remote_json(const char *registry, const char *path, const char *token,
                               char *err, size_t cap) {
    char url[PKG_PATH_MAX * 2];
    PkgBuf body = {0};
    PjValue *root;
    int status = 0;
    if (strlen(registry) + strlen(path) >= sizeof url) {
        snprintf(err, cap, "registry url is too long");
        return NULL;
    }
    snprintf(url, sizeof url, "%s%s", registry, path);
    if (!pk_net_get(url, token, &body, &status, err, cap)) {
        pk_buf_free(&body);
        return NULL;
    }
    if (status < 200 || status >= 300) {
        snprintf(err, cap, "registry returned http %d", status);
        pk_buf_free(&body);
        return NULL;
    }
    root = pj_parse(body.ptr ? body.ptr : "", body.len);
    pk_buf_free(&body);
    if (!root) {
        snprintf(err, cap, "registry returned invalid json");
        return NULL;
    }
    if (!pj_bool(root, "ok", 1)) {
        snprintf(err, cap, "%s", pj_str(root, "error", "registry request failed"));
        pj_free(root);
        return NULL;
    }
    return root;
}
