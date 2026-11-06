/* ── registry context, install, publish ──────────────────────────────────── */

static int pk_lock_update(const char *base, const PkgManifest *m, const char *version, const char *registry);
static void pk_lock_remove(const char *base, const char *name);

typedef struct {
    char cwd[PKG_PATH_MAX];
    char project[PKG_PATH_MAX];
    int has_project;
} PkgCtx;

typedef struct {
    char name[128];
    char version[64];
    char entry[256];
    char creator[128];
    char installed_to[PKG_PATH_MAX];
    char source[PKG_PATH_MAX];
} PkgResult;

static int pk_dir_has_manifest(const char *dir) {
    char path[PKG_PATH_MAX];
    pk_join(path, sizeof path, dir, "mellow.toml");
    if (pk_exists(path)) return 1;
    pk_join(path, sizeof path, dir, "mellow.pkg.json");
    if (pk_exists(path)) return 1;
    pk_join(path, sizeof path, dir, "mellow.json");
    return pk_exists(path);
}

static void pk_project_from(const char *start, char *out, size_t cap, int *found) {
    char current[PKG_PATH_MAX];
    *found = 0;
    out[0] = '\0';
    if (!start || !*start) return;
    snprintf(current, sizeof current, "%s", start);
    if (!pk_isdir(current)) pk_dirname(current, current, sizeof current);
    for (;;) {
        char parent[PKG_PATH_MAX];
        if (pk_dir_has_manifest(current)) {
            snprintf(out, cap, "%s", current);
            *found = 1;
            return;
        }
        pk_dirname(current, parent, sizeof parent);
        if (!strcmp(parent, current) || !*parent) return;
        snprintf(current, sizeof current, "%s", parent);
    }
}

static void pk_ctx_init(PkgCtx *ctx) {
    char cwd[PKG_PATH_MAX];
    memset(ctx, 0, sizeof *ctx);
    if (PKG_GETCWD(cwd, sizeof cwd)) {
        snprintf(ctx->cwd, sizeof ctx->cwd, "%s", cwd);
        pk_slashes(ctx->cwd);
    } else {
        snprintf(ctx->cwd, sizeof ctx->cwd, ".");
    }
    pk_project_from(ctx->cwd, ctx->project, sizeof ctx->project, &ctx->has_project);
}

static void pk_installed_root(const PkgCtx *ctx, int project_mode, char *out, size_t cap) {
    const char *base = (project_mode && ctx->has_project) ? ctx->project : ctx->cwd;
    pk_join(out, cap, base, "mellow_packages/installed");
}

static void pk_project_base(const PkgCtx *ctx, const char *project_dir, char *out, size_t cap) {
    int found = 0;
    pk_project_from(project_dir && *project_dir ? project_dir : ctx->cwd, out, cap, &found);
    if (!found) {
        if (project_dir && *project_dir) snprintf(out, cap, "%s", project_dir);
        else snprintf(out, cap, "%s", ctx->cwd);
        pk_slashes(out);
    }
}

static void pk_publish_root(const PkgCtx *ctx, char *out, size_t cap) {
    pk_join(out, cap, ctx->cwd, "mellow_packages/registry");
}

static int pk_find_source(const PkgCtx *ctx, const char *name, const char *version,
                          char *src, size_t src_cap, char *resolved, size_t version_cap) {
    char roots[2][PKG_PATH_MAX];
    int root_count = 0;
    int r;
    resolved[0] = '\0';
    pk_join(roots[root_count++], PKG_PATH_MAX, ctx->cwd, "mellow_packages/registry");
    if (ctx->has_project) {
        char project_registry[PKG_PATH_MAX];
        pk_join(project_registry, sizeof project_registry, ctx->project, "mellow_packages/registry");
        if (strcmp(project_registry, roots[0])) snprintf(roots[root_count++], PKG_PATH_MAX, "%s", project_registry);
    }
    for (r = 0; r < root_count; ++r) {
        char package_dir[PKG_PATH_MAX];
        PkgList versions = {0};
        pk_join(package_dir, sizeof package_dir, roots[r], name);
        if (!pk_isdir(package_dir)) continue;
        pk_list_dir(package_dir, 1, &versions);
        if (!versions.count) {
            pk_list_free(&versions);
            continue;
        }
        if (!version || !*version) {
            snprintf(resolved, version_cap, "%s", versions.items[versions.count - 1]);
        } else if (!pk_choose_version(&versions, version, resolved, version_cap)) {
            pk_list_free(&versions);
            continue;
        }
        pk_join(src, src_cap, package_dir, resolved);
        pk_list_free(&versions);
        if (pk_isdir(src)) return 1;
    }
    {
        char starter_root[PKG_PATH_MAX];
        char starter[PKG_PATH_MAX];
        pk_join(starter_root, sizeof starter_root, ctx->cwd, "starter_packages");
        pk_join(starter, sizeof starter, starter_root, name);
        if (pk_isdir(starter)) {
            PkgManifest manifest;
            char err[PKG_ERR_CAP];
            snprintf(src, src_cap, "%s", starter);
            if (pk_manifest_read_dir(starter, &manifest, err, sizeof err))
                snprintf(resolved, version_cap, "%s", version && *version ? version : manifest.version);
            else
                snprintf(resolved, version_cap, "%s", version && *version ? version : "0.1.0");
            return 1;
        }
    }
    return 0;
}

static int pk_install_recursive(PkgCtx *ctx, int project_mode, const char *ref, const char *version,
                                int with_deps, int depth, PkgList *visited,
                                PkgResult *out, char *err, size_t err_cap) {
    char name[128];
    char ref_version[64];
    char resolved[64];
    char src[PKG_PATH_MAX];
    char installed_root[PKG_PATH_MAX];
    char target[PKG_PATH_MAX];
    char package_dir[PKG_PATH_MAX];
    char manifest_path[PKG_PATH_MAX];
    PkgManifest manifest;
    char visit_key[256];
    int i;
    if (depth > PKG_MAX_DEPTH) {
        snprintf(err, err_cap, "dependency depth exceeded for %s", ref);
        return 0;
    }
    pk_split_ref(ref, name, sizeof name, ref_version, sizeof ref_version);
    if (!*name) {
        snprintf(err, err_cap, "invalid package name: %s", ref ? ref : "");
        return 0;
    }
    if (!version || !*version) version = ref_version;
    if (!pk_find_source(ctx, name, version, src, sizeof src, resolved, sizeof resolved)) {
        snprintf(err, err_cap, "package not found in local registry: %s", name);
        return 0;
    }
    snprintf(visit_key, sizeof visit_key, "%s@%s", name, resolved);
    for (i = 0; i < visited->count; ++i) {
        if (!strcmp(visited->items[i], visit_key)) {
            snprintf(out->name, sizeof out->name, "%s", name);
            snprintf(out->version, sizeof out->version, "%s", resolved);
            return 1;
        }
    }
    pk_list_push(visited, visit_key);

    pk_installed_root(ctx, project_mode, installed_root, sizeof installed_root);
    pk_join(target, sizeof target, installed_root, name);
    pk_join2(target, sizeof target, "current");
    {
        char parent[PKG_PATH_MAX];
        pk_dirname(target, parent, sizeof parent);
        pk_remove_tree(parent);
    }
    pk_join(package_dir, sizeof package_dir, target, "package");
    if (!pk_mkdirs(package_dir) || !pk_copy_tree(src, package_dir, 0, NULL)) {
        snprintf(err, err_cap, "could not copy package files: %s", name);
        return 0;
    }
    if (!pk_manifest_read_dir(src, &manifest, err, err_cap)) return 0;
    pk_join(manifest_path, sizeof manifest_path, target, "manifest.json");
    if (!pk_manifest_write_json(manifest_path, &manifest, 0)) {
        snprintf(err, err_cap, "could not write manifest: %s", manifest_path);
        return 0;
    }
    snprintf(out->name, sizeof out->name, "%s", name);
    snprintf(out->version, sizeof out->version, "%s", resolved);
    snprintf(out->entry, sizeof out->entry, "%s", manifest.entry);
    pk_manifest_creator(&manifest, out->creator, sizeof out->creator);
    snprintf(out->installed_to, sizeof out->installed_to, "%s", target);
    snprintf(out->source, sizeof out->source, "%s", src);
    if (project_mode && ctx->has_project) pk_lock_update(ctx->project, &manifest, resolved, "local");
    if (with_deps) {
        for (i = 0; i < manifest.dep_count; ++i) {
            const char *spec = manifest.dep_specs[i];
            PkgResult child;
            if (pk_ieq(spec, "host") || pk_ieq(spec, "builtin") || pk_ieq(spec, "built-in") || pk_ieq(spec, "internal"))
                continue;
            memset(&child, 0, sizeof child);
            if (!pk_install_recursive(ctx, project_mode, manifest.dep_names[i], spec, 1, depth + 1,
                                      visited, &child, err, err_cap))
                return 0;
        }
    }
    return 1;
}

static int pk_install_package(PkgCtx *ctx, int project_mode, const char *ref, const char *version,
                              int with_deps, PkgResult *out, char *err, size_t err_cap) {
    PkgList visited = {0};
    int ok;
    memset(out, 0, sizeof *out);
    ok = pk_install_recursive(ctx, project_mode, ref, version, with_deps, 0, &visited, out, err, err_cap);
    pk_list_free(&visited);
    return ok;
}

static int pk_publish_dir(PkgCtx *ctx, const char *dir, PkgManifest *manifest, char *out, size_t out_cap,
                          char *err, size_t err_cap) {
    char root[PKG_PATH_MAX];
    char target[PKG_PATH_MAX];
    char source[PKG_PATH_MAX];
    pk_resolve_path(ctx->cwd, dir, source, sizeof source);
    if (!pk_manifest_read_dir(source, manifest, err, err_cap)) return 0;
    pk_publish_root(ctx, root, sizeof root);
    pk_join(target, sizeof target, root, manifest->name);
    pk_join2(target, sizeof target, manifest->version);
    pk_remove_tree(target);
    if (!pk_copy_tree(source, target, 0, target)) {
        snprintf(err, err_cap, "could not copy package into registry: %s", target);
        return 0;
    }
    snprintf(out, out_cap, "%s", target);
    return 1;
}

#include "mellowrt_pkg_store_part1.inc"
#include "mellowrt_pkg_store_part2.inc"
