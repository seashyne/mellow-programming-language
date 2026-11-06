/* ── manifest IO ─────────────────────────────────────────────────────────── */

static int pk_manifest_read_file(const char *path, PkgManifest *m, char *err, size_t err_cap) {
    char folder[PKG_PATH_MAX];
    char dir[PKG_PATH_MAX];
    PkgBuf data = {0};
    int ok = 0;
    size_t len;
    if (!path || !pk_read_file(path, &data)) {
        snprintf(err, err_cap, "manifest not found: %s", path ? path : "");
        return 0;
    }
    pk_dirname(path, dir, sizeof dir);
    pk_basename(dir, folder, sizeof folder);
    pk_manifest_defaults(m, folder);
    len = strlen(path);
    if (len > 5 && !pk_ieq(path + len - 5, ".json")) {
        ok = pk_manifest_parse_toml(m, data.ptr ? data.ptr : "");
    } else {
        PjValue *root = pj_parse(data.ptr ? data.ptr : "", data.len);
        if (root) {
            pk_manifest_from_json(m, root);
            pj_free(root);
            ok = 1;
        } else {
            snprintf(err, err_cap, "invalid JSON manifest: %s", path);
        }
    }
    pk_buf_free(&data);
    return ok;
}

static int pk_manifest_read_dir(const char *dir, PkgManifest *m, char *err, size_t err_cap) {
    char path[PKG_PATH_MAX];
    pk_join(path, sizeof path, dir, "mellow.toml");
    if (pk_exists(path)) return pk_manifest_read_file(path, m, err, err_cap);
    pk_join(path, sizeof path, dir, "mellow.pkg.json");
    if (pk_exists(path)) return pk_manifest_read_file(path, m, err, err_cap);
    snprintf(err, err_cap, "no package manifest found in %s; expected one of: mellow.toml, mellow.pkg.json", dir);
    return 0;
}

/* ── writers ─────────────────────────────────────────────────────────────── */

static void pk_toml_escape(const char *text, PkgBuf *out) {
    const char *p;
    pk_buf_putc(out, '"');
    for (p = text ? text : ""; *p; ++p) {
        if (*p == '"' || *p == '\\') {
            pk_buf_putc(out, '\\');
            pk_buf_putc(out, *p);
        } else if (*p == '\n') {
            pk_buf_put(out, "\\n", 2);
        } else if (*p == '\t') {
            pk_buf_put(out, "\\t", 2);
        } else {
            pk_buf_putc(out, *p);
        }
    }
    pk_buf_putc(out, '"');
}

static void pk_toml_line(PkgBuf *out, const char *key, const char *value) {
    pk_buf_puts(out, key);
    pk_buf_puts(out, " = ");
    pk_toml_escape(value, out);
    pk_buf_putc(out, '\n');
}

static int pk_manifest_write_toml(const char *path, const PkgManifest *m) {
    PkgBuf out = {0};
    int i;
    int ok;
    pk_toml_line(&out, "name", m->name);
    pk_toml_line(&out, "version", m->version);
    pk_toml_line(&out, "description", m->description);
    pk_toml_line(&out, "entry", m->entry);
    pk_toml_line(&out, "license", m->license);
    pk_toml_line(&out, "visibility", m->visibility);
    if (m->namespace_[0]) pk_toml_line(&out, "namespace", m->namespace_);
    if (m->author_count) {
        pk_buf_puts(&out, "authors = [");
        for (i = 0; i < m->author_count; ++i) {
            if (i) pk_buf_puts(&out, ", ");
            pk_toml_escape(m->authors[i], &out);
        }
        pk_buf_puts(&out, "]\n");
    }
    if (m->keyword_count) {
        pk_buf_puts(&out, "keywords = [");
        for (i = 0; i < m->keyword_count; ++i) {
            if (i) pk_buf_puts(&out, ", ");
            pk_toml_escape(m->keywords[i], &out);
        }
        pk_buf_puts(&out, "]\n");
    }
    if (m->badge_count) {
        pk_buf_puts(&out, "badges = [");
        for (i = 0; i < m->badge_count; ++i) {
            if (i) pk_buf_puts(&out, ", ");
            pk_toml_escape(m->badges[i], &out);
        }
        pk_buf_puts(&out, "]\n");
    }
    if (m->official) pk_buf_puts(&out, "official = true\n");
    if (m->deprecated) pk_buf_puts(&out, "deprecated = true\n");
    pk_buf_puts(&out, "\n[dependencies]\n");
    if (m->dep_count) {
        for (i = 0; i < m->dep_count; ++i) pk_toml_line(&out, m->dep_names[i], m->dep_specs[i]);
    } else {
        pk_buf_puts(&out, "# add package = \"^1.0.0\"\n");
    }
    ok = pk_write_file(path, out.ptr ? out.ptr : "", out.len);
    pk_buf_free(&out);
    return ok;
}

static PjValue *pk_json_string_array(const char **items, int count) {
    PjValue *array = pj_new(PJ_ARRAY);
    int i;
    if (!array) return NULL;
    for (i = 0; i < count; ++i) {
        PjValue *item = pj_new_string(items[i]);
        if (!item || !pj_arr_push(array, item)) {
            pj_free(item);
            pj_free(array);
            return NULL;
        }
    }
    return array;
}

static void pj_set_bool(PjValue *object, const char *key, int value) {
    PjValue *child = pj_new(PJ_BOOL);
    if (!child) return;
    child->boolean = value;
    pj_obj_set(object, key, child);
}

static int pk_manifest_write_json(const char *path, const PkgManifest *m, int init_shape) {
    PjValue *root = pj_new(PJ_OBJECT);
    PjValue *deps;
    const char *author_ptrs[PKG_MAX_AUTHORS];
    const char *keyword_ptrs[PKG_MAX_KEYWORDS];
    const char *badge_ptrs[PKG_MAX_KEYWORDS];
    char creator[PKG_MAX_AUTHORS * 128 + 8];
    int i;
    int ok;
    if (!root) return 0;
    for (i = 0; i < m->author_count; ++i) author_ptrs[i] = m->authors[i];
    for (i = 0; i < m->keyword_count; ++i) keyword_ptrs[i] = m->keywords[i];
    for (i = 0; i < m->badge_count; ++i) badge_ptrs[i] = m->badges[i];
    deps = pj_new(PJ_OBJECT);
    if (deps) {
        for (i = 0; i < m->dep_count; ++i)
            pj_obj_set(deps, m->dep_names[i], pj_new_string(m->dep_specs[i]));
    }
    pj_obj_set(root, "name", pj_new_string(m->name));
    pj_obj_set(root, "version", pj_new_string(m->version));
    pj_obj_set(root, "entry", pj_new_string(m->entry));
    pj_obj_set(root, "description", pj_new_string(m->description));
    pj_obj_set(root, "authors", pk_json_string_array(author_ptrs, m->author_count));
    pj_obj_set(root, "license", pj_new_string(m->license));
    if (init_shape) {
        if (deps) pj_obj_set(root, "dependencies", deps);
        if (m->keyword_count)
            pj_obj_set(root, "keywords", pk_json_string_array(keyword_ptrs, m->keyword_count));
    } else {
        if (m->keyword_count)
            pj_obj_set(root, "keywords", pk_json_string_array(keyword_ptrs, m->keyword_count));
        pj_obj_set(root, "badges", pk_json_string_array(badge_ptrs, m->badge_count));
        pj_set_bool(root, "official", m->official);
        pj_set_bool(root, "deprecated", m->deprecated);
        if (deps) pj_obj_set(root, "dependencies", deps);
    }
    pj_obj_set(root, "visibility", pj_new_string(m->visibility));
    pj_obj_set(root, "namespace", pj_new_string(m->namespace_));
    if (!init_shape) {
        pk_manifest_creator(m, creator, sizeof creator);
        pj_obj_set(root, "creator", pj_new_string(creator));
    }
    ok = pj_save(path, root);
    pj_free(root);
    return ok;
}
