/* ── CLI ─────────────────────────────────────────────────────────────────── */

typedef struct {
    const char *first;
    const char *second;
    const char *version;
    const char *project_dir;
    const char *alias;
    const char *entry;
    const char *author;
    int no_deps;
} PkgArgs;

static void pk_args_parse(int argc, char **argv, int start, PkgArgs *args) {
    int i;
    int positionals = 0;
    memset(args, 0, sizeof *args);
    for (i = start; i < argc; ++i) {
        const char *arg = argv[i];
        if (!strcmp(arg, "--no-deps")) {
            args->no_deps = 1;
            continue;
        }
        if (!strncmp(arg, "--", 2)) {
            const char *eq = strchr(arg, '=');
            char key[64];
            const char *value = NULL;
            if (eq) {
                size_t len = (size_t)(eq - arg);
                if (len >= sizeof key) len = sizeof key - 1;
                memcpy(key, arg, len);
                key[len] = '\0';
                value = eq + 1;
            } else if (i + 1 < argc) {
                snprintf(key, sizeof key, "%s", arg);
                value = argv[++i];
            } else {
                snprintf(key, sizeof key, "%s", arg);
            }
            if (!strcmp(key, "--version")) args->version = value;
            else if (!strcmp(key, "--project-dir")) args->project_dir = value;
            else if (!strcmp(key, "--alias")) args->alias = value;
            else if (!strcmp(key, "--entry")) args->entry = value;
            else if (!strcmp(key, "--author")) args->author = value;
            continue;
        }
        if (positionals == 0) args->first = arg;
        else if (positionals == 1) args->second = arg;
        positionals++;
    }
}

static void pk_abs_path(const PkgCtx *ctx, const char *path, char *out, size_t cap) {
    if (!path || !*path) {
        snprintf(out, cap, "%s", ctx->cwd);
        return;
    }
    if (path[0] == '/' || path[0] == '\\' || (path[0] && path[1] == ':'))
        snprintf(out, cap, "%s", path);
    else
        pk_join(out, cap, ctx->cwd, path);
    pk_slashes(out);
}

static const char *pk_arg_name(int argc, char **argv, int start) {
    int i;
    for (i = start; i < argc; ++i) {
        if (!strcmp(argv[i], "--name") && i + 1 < argc) return argv[i + 1];
        if (!strncmp(argv[i], "--name=", 7)) return argv[i] + 7;
    }
    return NULL;
}

static void pk_print_manifest_json(const char *path) {
    PkgBuf data = {0};
    if (pk_read_file(path, &data)) {
        if (data.ptr) fwrite(data.ptr, 1, data.len, stdout);
    }
    pk_buf_free(&data);
}

static int pk_cmd_init(int argc, char **argv, int start) {
    PkgArgs args;
    PkgCtx ctx;
    char target[PKG_PATH_MAX];
    char manifest_path[PKG_PATH_MAX];
    PkgManifest manifest;
    char err[PKG_ERR_CAP] = {0};
    const char *name;
    pk_args_parse(argc, argv, start, &args);
    if (!args.first) {
        fprintf(stderr, "usage: mellow pkg init <dir> [--name N] [--entry F] [--author A]\n");
        return 2;
    }
    pk_ctx_init(&ctx);
    name = pk_arg_name(argc, argv, start);
    if (!pk_init_package(args.first, name, args.entry, args.author, &manifest, err, sizeof err)) {
        fprintf(stderr, "%s\n", err[0] ? err : "package init failed");
        return 2;
    }
    pk_abs_path(&ctx, args.first, target, sizeof target);
    printf("[OK] package initialized: %s\n", target);
    pk_join(manifest_path, sizeof manifest_path, args.first, "mellow.pkg.json");
    pk_print_manifest_json(manifest_path);
    return 0;
}

static int pk_cmd_publish(int argc, char **argv, int start) {
    PkgArgs args;
    PkgCtx ctx;
    PkgManifest manifest;
    char target[PKG_PATH_MAX];
    char creator[512];
    char err[PKG_ERR_CAP] = {0};
    pk_args_parse(argc, argv, start, &args);
    pk_ctx_init(&ctx);
    if (!pk_publish_dir(&ctx, args.first ? args.first : ".", &manifest, target, sizeof target, err, sizeof err)) {
        fprintf(stderr, "%s\n", err[0] ? err : "publish failed");
        return 2;
    }
    pk_manifest_creator(&manifest, creator, sizeof creator);
    printf("package published: %s@%s\n", manifest.name, manifest.version);
    printf("creator : %s\n", creator);
    printf("%s\n", target);
    return 0;
}

static int pk_cmd_install(int argc, char **argv, int start) {
    PkgArgs args;
    PkgCtx ctx;
    PkgResult result;
    char err[PKG_ERR_CAP] = {0};
    int project_mode;
    pk_args_parse(argc, argv, start, &args);
    if (!args.first) {
        fprintf(stderr, "usage: mellow pkg install <name>[@version] [--project-dir DIR]\n");
        return 2;
    }
    pk_ctx_init(&ctx);
    project_mode = args.project_dir != NULL;
    if (project_mode) {
        char base[PKG_PATH_MAX];
        pk_project_base(&ctx, args.project_dir, base, sizeof base);
        snprintf(ctx.project, sizeof ctx.project, "%s", base);
        ctx.has_project = 1;
    }
    if (!pk_install_package(&ctx, project_mode, args.first, args.version, !args.no_deps,
                            &result, err, sizeof err)) {
        fprintf(stderr, "%s\n", err[0] ? err : "install failed");
        return 2;
    }
    printf("package installed: %s@%s\n", result.name, result.version);
    if (result.entry[0]) printf("entry   : %s\n", result.entry);
    printf("creator : %s\n", result.creator);
    printf("path    : %s\n", result.installed_to);
    return 0;
}

static int pk_cmd_list(int argc, char **argv, int start) {
    PkgArgs args;
    PkgCtx ctx;
    PkgRow rows[PKG_MAX_ROWS];
    int count;
    int i;
    pk_args_parse(argc, argv, start, &args);
    pk_ctx_init(&ctx);
    if (args.project_dir) {
        char base[PKG_PATH_MAX];
        pk_project_base(&ctx, args.project_dir, base, sizeof base);
        snprintf(ctx.project, sizeof ctx.project, "%s", base);
        ctx.has_project = 1;
    }
    count = pk_list_installed(&ctx, args.project_dir != NULL, rows, PKG_MAX_ROWS);
    if (!count) {
        printf("No packages installed.\n");
        return 0;
    }
    for (i = 0; i < count; ++i)
        printf("- %s@%s by %s -> %s\n", rows[i].name, rows[i].version, rows[i].creator, rows[i].path);
    return 0;
}

static int pk_cmd_search(int argc, char **argv, int start) {
    PkgArgs args;
    PkgCtx ctx;
    PkgRow rows[PKG_MAX_ROWS];
    int count;
    int i;
    pk_args_parse(argc, argv, start, &args);
    if (!args.first) {
        fprintf(stderr, "usage: mellow pkg search <query>\n");
        return 2;
    }
    pk_ctx_init(&ctx);
    count = pk_search_rows(&ctx, args.first, rows, PKG_MAX_ROWS);
    if (!count) {
        printf("No packages found for '%s'.\n", args.first);
        return 0;
    }
    printf("Found %d package(s) for '%s'\n", count, args.first);
    for (i = 0; i < count; ++i) {
        printf("- %s  latest=%s  creator=%s  downloads=0  badges=-  versions=%s\n",
               rows[i].name, rows[i].version, rows[i].creator,
               rows[i].versions[0] ? rows[i].versions : "-");
        if (rows[i].description[0]) printf("    %s\n", rows[i].description);
    }
    return 0;
}

static void pk_print_versions(const char *versions) {
    const char *p = versions;
    if (!p || !*p) {
        printf("-");
        return;
    }
    while (*p) {
        const char *comma = strchr(p, ',');
        if (!comma) {
            fputs(p, stdout);
            break;
        }
        fwrite(p, 1, (size_t)(comma - p), stdout);
        fputs(", ", stdout);
        p = comma + 1;
    }
}

static int pk_cmd_info(int argc, char **argv, int start) {
    PkgArgs args;
    PkgCtx ctx;
    PkgRow row;
    pk_args_parse(argc, argv, start, &args);
    if (!args.first) {
        fprintf(stderr, "usage: mellow pkg info <name>\n");
        return 2;
    }
    pk_ctx_init(&ctx);
    if (!pk_info_row(&ctx, args.first, &row)) {
        fprintf(stderr, "package not found in local registry: %s\n", args.first);
        return 2;
    }
    printf("name       : %s\n", row.name);
    printf("latest     : %s\n", row.version);
    printf("versions   : ");
    pk_print_versions(row.versions);
    printf("\n");
    printf("creator    : %s\n", row.creator);
    printf("downloads  : 0\n");
    if (row.description[0]) printf("description: %s\n", row.description);
    printf("install    : mellow install %s\n", row.name);
    return 0;
}

#include "mellowrt_pkg_cli_part1.inc"
