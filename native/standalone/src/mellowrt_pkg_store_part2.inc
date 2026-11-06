/* ── search, info, uninstall, init ───────────────────────────────────────── */

static int pk_name_matches(const char *name, const char *query) {
    char lower_name[256];
    char lower_query[256];
    size_t i;
    if (!query || !*query) return 1;
    snprintf(lower_name, sizeof lower_name, "%s", name);
    snprintf(lower_query, sizeof lower_query, "%s", query);
    for (i = 0; lower_name[i]; ++i) lower_name[i] = (char)tolower((unsigned char)lower_name[i]);
    for (i = 0; lower_query[i]; ++i) lower_query[i] = (char)tolower((unsigned char)lower_query[i]);
    return strstr(lower_name, lower_query) != NULL;
}

static int pk_row_known(const PkgRow *rows, int count, const char *name) {
    int i;
    for (i = 0; i < count; ++i) {
        if (!strcmp(rows[i].name, name)) return 1;
    }
    return 0;
}

static int pk_package_dir_row(const char *package_dir, const char *name, PkgRow *row) {
    PkgList versions = {0};
    char latest[64];
    PkgManifest manifest;
    char err[PKG_ERR_CAP];
    size_t used = 0;
    int i;
    pk_list_dir(package_dir, 1, &versions);
    if (!versions.count) {
        PkgManifest flat;
        memset(row, 0, sizeof *row);
        snprintf(row->name, sizeof row->name, "%s", name);
        snprintf(row->path, sizeof row->path, "%s", package_dir);
        if (!pk_manifest_read_dir(package_dir, &flat, err, sizeof err)) {
            pk_list_free(&versions);
            return 0;
        }
        snprintf(row->version, sizeof row->version, "%s", flat.version);
        snprintf(row->versions, sizeof row->versions, "%s", flat.version);
        pk_manifest_creator(&flat, row->creator, sizeof row->creator);
        snprintf(row->description, sizeof row->description, "%s", flat.description);
        pk_list_free(&versions);
        return 1;
    }
    snprintf(latest, sizeof latest, "%s", versions.items[versions.count - 1]);
    memset(row, 0, sizeof *row);
    snprintf(row->name, sizeof row->name, "%s", name);
    snprintf(row->version, sizeof row->version, "%s", latest);
    snprintf(row->path, sizeof row->path, "%s", package_dir);
    for (i = 0; i < versions.count; ++i) {
        int wrote = snprintf(row->versions + used, sizeof row->versions - used, "%s%s",
                             i ? "," : "", versions.items[i]);
        if (wrote < 0 || (size_t)wrote >= sizeof row->versions - used) break;
        used += (size_t)wrote;
    }
    {
        char latest_dir[PKG_PATH_MAX];
        pk_join(latest_dir, sizeof latest_dir, package_dir, latest);
        if (pk_manifest_read_dir(latest_dir, &manifest, err, sizeof err)) {
            pk_manifest_creator(&manifest, row->creator, sizeof row->creator);
            snprintf(row->description, sizeof row->description, "%s", manifest.description);
        }
    }
    pk_list_free(&versions);
    return 1;
}

static int pk_search_rows(const PkgCtx *ctx, const char *query, PkgRow *rows, int max_rows) {
    char roots[3][PKG_PATH_MAX];
    int root_count = 0;
    int r;
    int count = 0;
    pk_join(roots[root_count++], PKG_PATH_MAX, ctx->cwd, "mellow_packages/registry");
    if (ctx->has_project) {
        char project_registry[PKG_PATH_MAX];
        pk_join(project_registry, sizeof project_registry, ctx->project, "mellow_packages/registry");
        if (strcmp(project_registry, roots[0])) snprintf(roots[root_count++], PKG_PATH_MAX, "%s", project_registry);
    }
    pk_join(roots[root_count++], PKG_PATH_MAX, ctx->cwd, "starter_packages");
    for (r = 0; r < root_count && count < max_rows; ++r) {
        PkgList packages = {0};
        int i;
        pk_list_dir(roots[r], 1, &packages);
        for (i = 0; i < packages.count && count < max_rows; ++i) {
            char package_dir[PKG_PATH_MAX];
            PkgRow row;
            if (!pk_name_matches(packages.items[i], query)) continue;
            if (pk_row_known(rows, count, packages.items[i])) continue;
            pk_join(package_dir, sizeof package_dir, roots[r], packages.items[i]);
            if (pk_package_dir_row(package_dir, packages.items[i], &row)) rows[count++] = row;
        }
        pk_list_free(&packages);
    }
    return count;
}

static int pk_info_row(const PkgCtx *ctx, const char *ref, PkgRow *row) {
    char name[128];
    char version[64];
    pk_split_ref(ref, name, sizeof name, version, sizeof version);
    {
        char src[PKG_PATH_MAX];
        char resolved[64];
        if (!pk_find_source(ctx, name, version, src, sizeof src, resolved, sizeof resolved)) return 0;
        memset(row, 0, sizeof *row);
        snprintf(row->name, sizeof row->name, "%s", name);
        snprintf(row->version, sizeof row->version, "%s", resolved);
        snprintf(row->path, sizeof row->path, "%s", src);
        {
            PkgManifest manifest;
            char err[PKG_ERR_CAP];
            char dir[PKG_PATH_MAX];
            PkgList versions = {0};
            size_t used = 0;
            int i;
            pk_dirname(src, dir, sizeof dir);
            if (pk_manifest_read_dir(src, &manifest, err, sizeof err)) {
                pk_manifest_creator(&manifest, row->creator, sizeof row->creator);
                snprintf(row->description, sizeof row->description, "%s", manifest.description);
            }
            pk_list_dir(dir, 1, &versions);
            for (i = 0; i < versions.count; ++i) {
                int wrote = snprintf(row->versions + used, sizeof row->versions - used, "%s%s",
                                     i ? "," : "", versions.items[i]);
                if (wrote < 0 || (size_t)wrote >= sizeof row->versions - used) break;
                used += (size_t)wrote;
            }
            pk_list_free(&versions);
        }
    }
    return 1;
}

static int pk_uninstall(const PkgCtx *ctx, int project_mode, const char *ref, char *removed, size_t cap) {
    char name[128];
    char ignored[64];
    char installed_root[PKG_PATH_MAX];
    char target[PKG_PATH_MAX];
    pk_split_ref(ref, name, sizeof name, ignored, sizeof ignored);
    pk_installed_root(ctx, project_mode, installed_root, sizeof installed_root);
    pk_join(target, sizeof target, installed_root, name);
    if (!pk_exists(target)) return 0;
    snprintf(removed, cap, "%s", target);
    if (!pk_remove_tree(target)) return 0;
    if (project_mode && ctx->has_project) pk_lock_remove(ctx->project, name);
    return 1;
}

static void pk_write_text(const char *path, const char *text) {
    pk_write_file(path, text, strlen(text));
}

static int pk_init_package(const char *dir, const char *name, const char *entry,
                           const char *author, PkgManifest *manifest, char *err, size_t err_cap) {
    char folder[PKG_PATH_MAX];
    char path[PKG_PATH_MAX];
    char source[4096];
    char readme[1024];
    if (!pk_mkdirs(dir)) {
        snprintf(err, err_cap, "could not create directory: %s", dir);
        return 0;
    }
    pk_join(path, sizeof path, dir, "src");
    pk_mkdirs(path);
    pk_join(path, sizeof path, dir, "tests");
    pk_mkdirs(path);
    pk_basename(dir, folder, sizeof folder);
    pk_manifest_defaults(manifest, name && *name ? name : folder);
    snprintf(manifest->entry, sizeof manifest->entry, "src/%s", entry && *entry ? entry : "main.mellow");
    manifest->keyword_count = 0;
    pk_manifest_add_keyword(manifest, "mellow");
    pk_manifest_add_keyword(manifest, "package");
    if (author && *author) pk_manifest_add_author(manifest, author);
    pk_join(path, sizeof path, dir, "mellow.toml");
    if (!pk_manifest_write_toml(path, manifest)) {
        snprintf(err, err_cap, "could not write manifest: %s", path);
        return 0;
    }
    pk_join(path, sizeof path, dir, "mellow.pkg.json");
    if (!pk_manifest_write_json(path, manifest, 1)) {
        snprintf(err, err_cap, "could not write manifest: %s", path);
        return 0;
    }
    pk_join(path, sizeof path, dir, manifest->entry);
    if (!pk_exists(path)) {
        snprintf(source, sizeof source, "def hello():\n    print(\"Hello from %s\")\n", manifest->name);
        {
            char parent[PKG_PATH_MAX];
            pk_dirname(path, parent, sizeof parent);
            pk_mkdirs(parent);
        }
        pk_write_text(path, source);
    }
    pk_join(path, sizeof path, dir, "README.md");
    if (!pk_exists(path)) {
        snprintf(readme, sizeof readme, "# %s\n\nGenerated by Mellow package manager.\n", manifest->name);
        pk_write_text(path, readme);
    }
    pk_join(path, sizeof path, dir, "tests/basic_test.mellow");
    if (!pk_exists(path)) pk_write_text(path, "print(\"basic package test\")\n");
    return 1;
}
