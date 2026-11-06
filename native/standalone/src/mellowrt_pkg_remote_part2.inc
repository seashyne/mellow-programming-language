/* ── remote package rows ─────────────────────────────────────────────────── */

static void pk_remote_row(const PjValue *item, const char *registry, PkgRow *row) {
    const PjValue *downloads;
    memset(row, 0, sizeof *row);
    snprintf(row->name, sizeof row->name, "%s", pj_str(item, "name", ""));
    snprintf(row->version, sizeof row->version, "%s", pj_str(item, "latest", ""));
    snprintf(row->creator, sizeof row->creator, "%s", pj_str(item, "creator", "unknown"));
    snprintf(row->description, sizeof row->description, "%s", pj_str(item, "description", ""));
    snprintf(row->path, sizeof row->path, "%s", registry ? registry : "");
    pk_join_string_array(pj_obj_get(item, "versions"), row->versions, sizeof row->versions, ",");
    pk_join_string_array(pj_obj_get(item, "badges"), row->badges, sizeof row->badges, ",");
    if (!row->versions[0] && row->version[0])
        snprintf(row->versions, sizeof row->versions, "%s", row->version);
    downloads = pj_obj_get(item, "downloads");
    if (downloads && downloads->type == PJ_NUMBER) row->downloads = (int)downloads->number;
}

static int pk_remote_search(const char *registry, const char *query, PkgRow *rows, int max_rows,
                            char *err, size_t cap) {
    const char *token = pk_registry_token(registry);
    PkgBuf path = {0};
    PjValue *root;
    PjValue *items;
    int count = 0;
    size_t i;
    pk_buf_puts(&path, "/api/v1/packages/search?q=");
    pk_url_encode(query, &path);
    if (!path.ptr) {
        snprintf(err, cap, "out of memory while building registry query");
        return 0;
    }
    root = pk_remote_json(registry, path.ptr, token, err, cap);
    pk_buf_free(&path);
    if (!root) return 0;
    items = pj_obj_get(root, "items");
    if (items && items->type == PJ_ARRAY) {
        for (i = 0; i < items->count && count < max_rows; ++i) {
            if (items->items[i] && items->items[i]->type == PJ_OBJECT)
                pk_remote_row(items->items[i], registry, &rows[count++]);
        }
    }
    pj_free(root);
    return count;
}

static int pk_remote_info(const char *registry, const char *ref, PkgRow *row, char *err, size_t cap) {
    const char *token = pk_registry_token(registry);
    char name[128];
    char version[64];
    PkgBuf path = {0};
    PjValue *root;
    pk_split_ref(ref, name, sizeof name, version, sizeof version);
    if (!name[0]) {
        snprintf(err, cap, "invalid package name: %s", ref ? ref : "");
        return 0;
    }
    pk_buf_puts(&path, "/api/v1/packages/");
    pk_url_quote_path(name, &path);
    if (!path.ptr) {
        snprintf(err, cap, "out of memory while building registry query");
        return 0;
    }
    root = pk_remote_json(registry, path.ptr, token, err, cap);
    pk_buf_free(&path);
    if (!root) return 0;
    pk_remote_row(root, registry, row);
    if (version[0]) {
        PkgBuf detail_path = {0};
        PjValue *detail;
        PkgList versions = {0};
        char chosen[64];
        const char *cursor = row->versions;
        while (cursor && *cursor) {
            const char *comma = strchr(cursor, ',');
            size_t len = comma ? (size_t)(comma - cursor) : strlen(cursor);
            char item[64];
            if (len >= sizeof item) len = sizeof item - 1;
            memcpy(item, cursor, len);
            item[len] = '\0';
            if (len) pk_list_push(&versions, item);
            if (!comma) break;
            cursor = comma + 1;
        }
        if (!pk_choose_version(&versions, version, chosen, sizeof chosen))
            snprintf(chosen, sizeof chosen, "%s", version);
        pk_list_free(&versions);
        pk_buf_puts(&detail_path, "/api/v1/packages/");
        pk_url_quote_path(name, &detail_path);
        pk_buf_puts(&detail_path, "/versions/");
        pk_url_quote_path(chosen, &detail_path);
        detail = detail_path.ptr ? pk_remote_json(registry, detail_path.ptr, token, err, cap) : NULL;
        pk_buf_free(&detail_path);
        if (!detail) {
            pj_free(root);
            return 0;
        }
        snprintf(row->version, sizeof row->version, "%s", chosen);
        {
            const PjValue *manifest = pj_obj_get(detail, "manifest");
            const PjValue *badges = pj_obj_get(detail, "badges");
            const PjValue *downloads = pj_obj_get(detail, "downloads");
            const char *text = pj_str(detail, "creator", row->creator);
            char held[512];
            snprintf(held, sizeof held, "%s", text);
            snprintf(row->creator, sizeof row->creator, "%s", held);
            text = pj_str(detail, "description", NULL);
            if (!text) text = pj_str(manifest, "description", NULL);
            snprintf(held, sizeof held, "%s", text ? text : row->description);
            snprintf(row->description, sizeof row->description, "%s", held);
            if (badges && badges->type == PJ_ARRAY)
                pk_join_string_array(badges, row->badges, sizeof row->badges, ",");
            if (downloads && downloads->type == PJ_NUMBER)
                row->downloads = (int)downloads->number;
        }
        pj_free(detail);
    }
    pj_free(root);
    return 1;
}
