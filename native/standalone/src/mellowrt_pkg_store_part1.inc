/* ── lockfile, aliases, listings ─────────────────────────────────────────── */

static PjValue *pk_json_load(const char *path) {
    PkgBuf data = {0};
    PjValue *root;
    if (!pk_read_file(path, &data)) return NULL;
    root = pj_parse(data.ptr ? data.ptr : "", data.len);
    pk_buf_free(&data);
    return root;
}

static PjValue *pk_json_child_object(PjValue *parent, const char *key) {
    PjValue *child = pj_obj_get(parent, key);
    if (child && child->type == PJ_OBJECT) return child;
    child = pj_new(PJ_OBJECT);
    if (!child || !pj_obj_set(parent, key, child)) {
        pj_free(child);
        return NULL;
    }
    return child;
}

static PjValue *pk_json_string_list(const char **items, int count) {
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

static void pk_obj_remove(PjValue *object, const char *key) {
    size_t i;
    if (!object || object->type != PJ_OBJECT) return;
    for (i = 0; i < object->count; ++i) {
        if (strcmp(object->keys[i], key)) continue;
        pj_free(object->items[i]);
        free(object->keys[i]);
        memmove(object->keys + i, object->keys + i + 1, sizeof(char *) * (object->count - i - 1));
        memmove(object->items + i, object->items + i + 1, sizeof(PjValue *) * (object->count - i - 1));
        object->count--;
        return;
    }
}

static int pk_lock_update(const char *base, const PkgManifest *m, const char *version, const char *registry) {
    char path[PKG_PATH_MAX];
    PjValue *lock;
    PjValue *packages;
    PjValue *entry;
    PjValue *root;
    PjValue *root_deps;
    PjValue *deps;
    const char *author_ptrs[PKG_MAX_AUTHORS];
    char creator[PKG_MAX_AUTHORS * 128 + 8];
    int i;
    int ok;
    pk_join(path, sizeof path, base, "mellow.lock");
    lock = pk_json_load(path);
    if (!lock || lock->type != PJ_OBJECT) {
        pj_free(lock);
        lock = pj_new(PJ_OBJECT);
        if (!lock) return 0;
        pj_obj_set(lock, "lockfile_version", pj_new_number(1));
        pj_obj_set(lock, "registry", pj_new_string(registry));
        pj_obj_set(lock, "packages", pj_new(PJ_OBJECT));
        root = pj_new(PJ_OBJECT);
        if (root) {
            pj_obj_set(root, "dependencies", pj_new(PJ_OBJECT));
            pj_obj_set(root, "imports", pj_new(PJ_ARRAY));
            pj_obj_set(lock, "root", root);
        }
    }
    if (!pj_obj_get(lock, "registry")) pj_obj_set(lock, "registry", pj_new_string(registry));
    else if (pj_obj_get(lock, "registry")->type == PJ_STRING) {
        free(pj_obj_get(lock, "registry")->string);
        pj_obj_get(lock, "registry")->string = pk_strdup(registry);
    }
    packages = pk_json_child_object(lock, "packages");
    root = pk_json_child_object(lock, "root");
    if (!packages || !root) {
        pj_free(lock);
        return 0;
    }
    entry = pj_new(PJ_OBJECT);
    deps = pj_new(PJ_OBJECT);
    if (!entry || !deps) {
        pj_free(entry);
        pj_free(deps);
        pj_free(lock);
        return 0;
    }
    for (i = 0; i < m->dep_count; ++i)
        pj_obj_set(deps, m->dep_names[i], pj_new_string(m->dep_specs[i]));
    for (i = 0; i < m->author_count; ++i) author_ptrs[i] = m->authors[i];
    pk_manifest_creator(m, creator, sizeof creator);
    pj_obj_set(entry, "version", pj_new_string(version));
    pj_obj_set(entry, "entry", pj_new_string(m->entry));
    pj_obj_set(entry, "authors", pk_json_string_list(author_ptrs, m->author_count));
    pj_obj_set(entry, "creator", pj_new_string(creator));
    pj_obj_set(entry, "dependencies", deps);
    pj_obj_set(entry, "sha256", pj_new(PJ_NULL));
    pj_obj_set(packages, m->name, entry);
    root_deps = pk_json_child_object(root, "dependencies");
    if (root_deps && !pj_obj_get(root_deps, m->name))
        pj_obj_set(root_deps, m->name, pj_new_string(version));
    ok = pj_save(path, lock);
    pj_free(lock);
    return ok;
}

static void pk_lock_remove(const char *base, const char *name) {
    char path[PKG_PATH_MAX];
    PjValue *lock;
    PjValue *root_deps;
    pk_join(path, sizeof path, base, "mellow.lock");
    lock = pk_json_load(path);
    if (!lock) return;
    pk_obj_remove(pj_obj_get(lock, "packages"), name);
    root_deps = pj_obj_get(pj_obj_get(lock, "root"), "dependencies");
    pk_obj_remove(root_deps, name);
    pj_save(path, lock);
    pj_free(lock);
}

static void pk_alias_default(const char *name, char *out, size_t cap) {
    char bare[128];
    const char *slash = strrchr(name, '/');
    size_t i, j = 0;
    if (name[0] == '@' && slash) snprintf(bare, sizeof bare, "%s", slash + 1);
    else snprintf(bare, sizeof bare, "%s", name);
    for (i = 0; bare[i] && j + 1 < cap; ++i) {
        char c = bare[i];
        out[j++] = (isalnum((unsigned char)c) || c == '_') ? c : '_';
    }
    out[j] = '\0';
    if (!j) snprintf(out, cap, "pkg");
}

static int pk_aliases_add(const char *base, const char *name, const char *alias) {
    char path[PKG_PATH_MAX];
    char chosen[128];
    PjValue *root;
    PjValue *aliases;
    PjValue *packages;
    int ok;
    if (!alias || !*alias) pk_alias_default(name, chosen, sizeof chosen);
    else snprintf(chosen, sizeof chosen, "%s", alias);
    pk_join(path, sizeof path, base, ".mellow_aliases.json");
    root = pk_json_load(path);
    if (!root || root->type != PJ_OBJECT) {
        pj_free(root);
        root = pj_new(PJ_OBJECT);
        if (!root) return 0;
    }
    aliases = pk_json_child_object(root, "aliases");
    packages = pk_json_child_object(root, "packages");
    if (!aliases || !packages) {
        pj_free(root);
        return 0;
    }
    pj_obj_set(aliases, chosen, pj_new_string(name));
    pj_obj_set(packages, name, pj_new_string(chosen));
    ok = pj_save(path, root);
    pj_free(root);
    return ok;
}

static int pk_aliases_remove(const char *base, const char *name, char *removed, size_t removed_cap) {
    char path[PKG_PATH_MAX];
    char chosen[128] = "";
    PjValue *root;
    PjValue *aliases;
    PjValue *packages;
    PjValue *value;
    if (removed && removed_cap) removed[0] = '\0';
    pk_join(path, sizeof path, base, ".mellow_aliases.json");
    root = pk_json_load(path);
    if (!root) return 0;
    packages = pj_obj_get(root, "packages");
    aliases = pj_obj_get(root, "aliases");
    value = packages ? pj_obj_get(packages, name) : NULL;
    if (value && value->type == PJ_STRING && value->string) snprintf(chosen, sizeof chosen, "%s", value->string);
    pk_obj_remove(packages, name);
    if (chosen[0]) pk_obj_remove(aliases, chosen);
    if (removed && removed_cap && chosen[0]) snprintf(removed, removed_cap, "%s", chosen);
    pj_save(path, root);
    pj_free(root);
    return 1;
}

/* ── listings ────────────────────────────────────────────────────────────── */

#define PKG_MAX_ROWS 256

typedef struct {
    char name[128];
    char version[64];
    char creator[128];
    char description[512];
    char path[PKG_PATH_MAX];
    char versions[512];
    char badges[128];
    int downloads;
} PkgRow;

static int pk_read_installed_row(const char *installed_root, const char *name, PkgRow *row) {
    char manifest_path[PKG_PATH_MAX];
    char package_parent[PKG_PATH_MAX];
    PkgManifest manifest;
    char err[PKG_ERR_CAP];
    pk_join(manifest_path, sizeof manifest_path, installed_root, name);
    pk_join2(manifest_path, sizeof manifest_path, "current/manifest.json");
    if (!pk_manifest_read_file(manifest_path, &manifest, err, sizeof err)) return 0;
    memset(row, 0, sizeof *row);
    snprintf(row->name, sizeof row->name, "%s", manifest.name);
    snprintf(row->version, sizeof row->version, "%s", manifest.version);
    pk_manifest_creator(&manifest, row->creator, sizeof row->creator);
    snprintf(row->description, sizeof row->description, "%s", manifest.description);
    pk_join(package_parent, sizeof package_parent, installed_root, name);
    pk_join(row->path, sizeof row->path, package_parent, "current");
    return 1;
}

static int pk_list_installed(const PkgCtx *ctx, int project_mode, PkgRow *rows, int max_rows) {
    char installed_root[PKG_PATH_MAX];
    PkgList names = {0};
    int count = 0;
    int i;
    pk_installed_root(ctx, project_mode, installed_root, sizeof installed_root);
    pk_list_dir(installed_root, 1, &names);
    for (i = 0; i < names.count && count < max_rows; ++i) {
        if (pk_read_installed_row(installed_root, names.items[i], &rows[count])) count++;
    }
    pk_list_free(&names);
    return count;
}
