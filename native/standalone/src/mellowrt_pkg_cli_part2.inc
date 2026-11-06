/* ── search and info: local registry first, remote fallback ─────────────── */

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

static void pk_print_row(const PkgRow *row) {
    printf("- %s  latest=%s  creator=%s  downloads=%d  badges=%s  versions=%s\n",
           row->name, row->version, row->creator, row->downloads,
           row->badges[0] ? row->badges : "-",
           row->versions[0] ? row->versions : "-");
    if (row->description[0]) printf("    %s\n", row->description);
}

static int pk_cmd_search(int argc, char **argv, int start) {
    PkgArgs args;
    PkgCtx ctx;
    PkgRow rows[PKG_MAX_ROWS];
    const char *registry = NULL;
    char err[PKG_ERR_CAP] = {0};
    int remote = 0;
    int count;
    int i;
    pk_args_parse(argc, argv, start, &args);
    if (!args.first) {
        fprintf(stderr, "usage: mellow pkg search <query> [--registry URL]\n");
        return 2;
    }
    pk_ctx_init(&ctx);
    count = pk_search_rows(&ctx, args.first, rows, PKG_MAX_ROWS);
    if (!count) {
        registry = pk_registry_url(args.registry);
        count = pk_remote_search(registry, args.first, rows, PKG_MAX_ROWS, err, sizeof err);
        remote = 1;
    }
    if (!count) {
        if (err[0]) {
            fprintf(stderr, "%s\n", err);
            return 2;
        }
        printf("No packages found for '%s'.\n", args.first);
        return 0;
    }
    printf("Found %d package(s) for '%s'\n", count, args.first);
    if (remote) printf("Registry: %s\n", registry);
    for (i = 0; i < count; ++i) pk_print_row(&rows[i]);
    return 0;
}

static int pk_cmd_info(int argc, char **argv, int start) {
    PkgArgs args;
    PkgCtx ctx;
    PkgRow row;
    const char *registry = NULL;
    char err[PKG_ERR_CAP] = {0};
    int remote = 0;
    pk_args_parse(argc, argv, start, &args);
    if (!args.first) {
        fprintf(stderr, "usage: mellow pkg info <name> [--registry URL]\n");
        return 2;
    }
    pk_ctx_init(&ctx);
    if (!pk_info_row(&ctx, args.first, &row)) {
        registry = pk_registry_url(args.registry);
        if (!pk_remote_info(registry, args.first, &row, err, sizeof err)) {
            fprintf(stderr, "package not found in local registry: %s\n", args.first);
            if (err[0]) fprintf(stderr, "%s\n", err);
            return 2;
        }
        remote = 1;
    }
    printf("name       : %s\n", row.name);
    printf("latest     : %s\n", row.version);
    printf("versions   : ");
    pk_print_versions(row.versions);
    printf("\n");
    printf("creator    : %s\n", row.creator);
    printf("downloads  : %d\n", row.downloads);
    if (row.badges[0]) printf("badges     : %s\n", row.badges);
    if (row.description[0]) printf("description: %s\n", row.description);
    if (remote) printf("registry   : %s\n", registry);
    printf("install    : mellow install %s\n", row.name);
    return 0;
}
