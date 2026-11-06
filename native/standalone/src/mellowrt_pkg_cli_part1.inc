/* ── add / remove / dispatch ─────────────────────────────────────────────── */

static int pk_manifest_target(const char *base, char *path, size_t cap, int *is_json) {
    char toml[PKG_PATH_MAX];
    char json[PKG_PATH_MAX];
    pk_join(toml, sizeof toml, base, "mellow.toml");
    pk_join(json, sizeof json, base, "mellow.pkg.json");
    if (pk_exists(toml)) {
        snprintf(path, cap, "%s", toml);
        *is_json = 0;
        return 1;
    }
    if (pk_exists(json)) {
        snprintf(path, cap, "%s", json);
        *is_json = 1;
        return 1;
    }
    snprintf(path, cap, "%s", toml);
    *is_json = 0;
    return 0;
}

static int pk_latest_version(const PkgCtx *ctx, const char *name, char *out, size_t cap) {
    char src[PKG_PATH_MAX];
    char resolved[64];
    if (!pk_find_source(ctx, name, NULL, src, sizeof src, resolved, sizeof resolved)) return 0;
    snprintf(out, cap, "%s", resolved);
    return 1;
}

static int pk_cmd_add(int argc, char **argv, int start) {
    PkgArgs args;
    PkgCtx ctx;
    char base[PKG_PATH_MAX];
    char manifest_path[PKG_PATH_MAX];
    char latest[64];
    char spec[80];
    char alias[128];
    char folder[PKG_PATH_MAX];
    char err[PKG_ERR_CAP] = {0};
    PkgManifest manifest;
    PkgResult result;
    int is_json = 0;
    int existed;
    int project_mode = 1;
    const char *spec_in = NULL;
    pk_args_parse(argc, argv, start, &args);
    if (!args.first) {
        fprintf(stderr, "usage: mellow add <name>[@version] [--project-dir DIR] [--alias A]\n");
        return 2;
    }
    pk_ctx_init(&ctx);
    pk_project_base(&ctx, args.project_dir, base, sizeof base);
    snprintf(ctx.project, sizeof ctx.project, "%s", base);
    ctx.has_project = 1;
    existed = pk_manifest_target(base, manifest_path, sizeof manifest_path, &is_json);
    if (!existed) {
        pk_basename(base, folder, sizeof folder);
        pk_manifest_defaults(&manifest, folder);
        snprintf(manifest.description, sizeof manifest.description, "Mellow project");
        manifest.keyword_count = 0;
        pk_join(manifest_path, sizeof manifest_path, base, "mellow.toml");
        is_json = 0;
    } else if (!pk_manifest_read_file(manifest_path, &manifest, err, sizeof err)) {
        fprintf(stderr, "%s\n", err[0] ? err : "could not read project manifest");
        return 2;
    }
    if (args.version && *args.version) {
        spec_in = args.version;
    } else {
        if (!pk_latest_version(&ctx, args.first, latest, sizeof latest)) {
            fprintf(stderr, "package not found in local registry: %s\n", args.first);
            return 2;
        }
        snprintf(spec, sizeof spec, "^%s", latest);
        spec_in = spec;
    }
    pk_manifest_set_dep(&manifest, args.first, spec_in);
    if (!(is_json ? pk_manifest_write_json(manifest_path, &manifest, 0)
                  : pk_manifest_write_toml(manifest_path, &manifest))) {
        fprintf(stderr, "could not write manifest: %s\n", manifest_path);
        return 2;
    }
    if (!pk_install_package(&ctx, project_mode, args.first, spec_in, !args.no_deps,
                            &result, err, sizeof err)) {
        fprintf(stderr, "%s\n", err[0] ? err : "install failed");
        return 2;
    }
    pk_aliases_add(base, result.name, args.alias);
    if (args.alias && *args.alias) snprintf(alias, sizeof alias, "%s", args.alias);
    else pk_alias_default(result.name, alias, sizeof alias);
    printf("dependency added: %s (%s)\n", result.name, spec_in);
    printf("alias: %s\n", alias);
    {
        char aliases_path[PKG_PATH_MAX];
        pk_join(aliases_path, sizeof aliases_path, base, ".mellow_aliases.json");
        printf("aliases: %s\n", aliases_path);
    }
    return 0;
}

static int pk_cmd_remove(int argc, char **argv, int start) {
    PkgArgs args;
    PkgCtx ctx;
    char base[PKG_PATH_MAX];
    char manifest_path[PKG_PATH_MAX];
    char removed[PKG_PATH_MAX];
    char alias[128];
    char name[128];
    char ignored[64];
    char err[PKG_ERR_CAP] = {0};
    PkgManifest manifest;
    int is_json = 0;
    pk_args_parse(argc, argv, start, &args);
    if (!args.first) {
        fprintf(stderr, "usage: mellow remove <name> [--project-dir DIR]\n");
        return 2;
    }
    pk_ctx_init(&ctx);
    pk_project_base(&ctx, args.project_dir, base, sizeof base);
    snprintf(ctx.project, sizeof ctx.project, "%s", base);
    ctx.has_project = 1;
    pk_split_ref(args.first, name, sizeof name, ignored, sizeof ignored);
    if (pk_manifest_target(base, manifest_path, sizeof manifest_path, &is_json) &&
        pk_manifest_read_file(manifest_path, &manifest, err, sizeof err)) {
        if (pk_manifest_remove_dep(&manifest, name)) {
            if (!(is_json ? pk_manifest_write_json(manifest_path, &manifest, 0)
                          : pk_manifest_write_toml(manifest_path, &manifest))) {
                fprintf(stderr, "could not write manifest: %s\n", manifest_path);
                return 2;
            }
        }
    }
    if (!pk_uninstall(&ctx, 1, name, removed, sizeof removed)) {
        fprintf(stderr, "package not installed: %s\n", name);
        return 2;
    }
    pk_aliases_remove(base, name, alias, sizeof alias);
    printf("dependency removed: %s\n", name);
    if (alias[0]) printf("alias removed: %s\n", alias);
    return 0;
}

static int pk_cmd_uninstall(int argc, char **argv, int start) {
    PkgArgs args;
    PkgCtx ctx;
    char removed[PKG_PATH_MAX];
    int project_mode;
    pk_args_parse(argc, argv, start, &args);
    if (!args.first) {
        fprintf(stderr, "usage: mellow uninstall <name> [--project-dir DIR]\n");
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
    if (!pk_uninstall(&ctx, project_mode, args.first, removed, sizeof removed)) {
        fprintf(stderr, "package not installed: %s\n", args.first);
        return 2;
    }
    printf("package removed: %s\n", args.first);
    printf("path    : %s\n", removed);
    return 0;
}

static void pk_usage(void) {
    puts("Mellow native package manager");
    puts("  mellow pkg init <dir> [--name N] [--entry F] [--author A]");
    puts("  mellow pkg publish <dir>");
    puts("  mellow pkg install <name>[@version] [--project-dir DIR] [--no-deps]");
    puts("  mellow pkg list [--project-dir DIR]");
    puts("  mellow pkg search <query> [--registry URL]");
    puts("  mellow pkg info <name> [--registry URL]");
    puts("  mellow pkg remove <name> [--project-dir DIR]");
    puts("  mellow add <name> [--project-dir DIR] [--alias A]");
    puts("  mellow remove <name> [--project-dir DIR]");
    puts("Local registry: mellow_packages/registry, mellow_packages/installed");
    puts("Remote registry: --registry, MELLOW_REGISTRY_URL, or ~/.mellow/config.json");
}

int mellowrt_pkg_cli(int argc, char **argv) {
    const char *cmd;
    int start;
    if (argc < 2) {
        pk_usage();
        return 2;
    }
    if (!strcmp(argv[1], "pkg")) {
        if (argc < 3) {
            pk_usage();
            return 2;
        }
        cmd = argv[2];
        start = 3;
    } else {
        cmd = argv[1];
        start = 2;
    }
    if (!strcmp(cmd, "--help") || !strcmp(cmd, "-h") || !strcmp(cmd, "help")) {
        pk_usage();
        return 0;
    }
    if (!strcmp(cmd, "init")) return pk_cmd_init(argc, argv, start);
    if (!strcmp(cmd, "publish")) return pk_cmd_publish(argc, argv, start);
    if (!strcmp(cmd, "install")) return pk_cmd_install(argc, argv, start);
    if (!strcmp(cmd, "list") || !strcmp(cmd, "ls")) return pk_cmd_list(argc, argv, start);
    if (!strcmp(cmd, "search")) return pk_cmd_search(argc, argv, start);
    if (!strcmp(cmd, "info")) return pk_cmd_info(argc, argv, start);
    if (!strcmp(cmd, "add")) return pk_cmd_add(argc, argv, start);
    if (!strcmp(cmd, "remove")) return pk_cmd_remove(argc, argv, start);
    if (!strcmp(cmd, "uninstall")) return pk_cmd_uninstall(argc, argv, start);
    fprintf(stderr, "unknown package command: %s\n", cmd);
    pk_usage();
    return 2;
}
