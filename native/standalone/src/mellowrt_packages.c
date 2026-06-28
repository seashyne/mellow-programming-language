#include "mellowrt_packages.h"

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if defined(_WIN32)
#include <direct.h>
#define PATH_SEP '\\'
#define ACCESS _access
#define GETCWD _getcwd
#else
#include <unistd.h>
#define PATH_SEP '/'
#define ACCESS access
#define GETCWD getcwd
#endif

#ifndef F_OK
#define F_OK 0
#endif

static int path_exists(const char *path) {
    return path && *path && ACCESS(path, F_OK) == 0;
}

static void normalize_separators(char *path) {
    char *p;
    for (p = path; p && *p; ++p) {
        if (*p == '/' || *p == '\\') *p = PATH_SEP;
    }
}

static int join2(char *out, size_t out_size, const char *a, const char *b) {
    size_t n;
    char tmp[1024];
    if (!out || out_size == 0 || !a || !b) return 0;
    n = strlen(a);
    if (n && (a[n - 1] == '/' || a[n - 1] == '\\'))
        snprintf(tmp, sizeof(tmp), "%s%s", a, b);
    else
        snprintf(tmp, sizeof(tmp), "%s%c%s", a, PATH_SEP, b);
    snprintf(out, out_size, "%s", tmp);
    out[out_size - 1] = '\0';
    normalize_separators(out);
    return strlen(out) < out_size - 1;
}

static int dirname_of(const char *path, char *out, size_t out_size) {
    const char *slash1;
    const char *slash2;
    const char *slash;
    size_t n;
    if (!path || !*path || !out || out_size == 0) return 0;
    slash1 = strrchr(path, '/');
    slash2 = strrchr(path, '\\');
    slash = slash1 > slash2 ? slash1 : slash2;
    if (!slash) {
        if (!GETCWD(out, (int)out_size)) return 0;
        out[out_size - 1] = '\0';
        normalize_separators(out);
        return 1;
    }
    n = (size_t)(slash - path);
    if (n == 0) n = 1;
    if (n >= out_size) n = out_size - 1;
    memcpy(out, path, n);
    out[n] = '\0';
    normalize_separators(out);
    return 1;
}

static int parent_dir(char *path) {
    char *slash1;
    char *slash2;
    char *slash;
    size_t len;
    if (!path || !*path) return 0;
    len = strlen(path);
    while (len > 1 && (path[len - 1] == '/' || path[len - 1] == '\\')) path[--len] = '\0';
    slash1 = strrchr(path, '/');
    slash2 = strrchr(path, '\\');
    slash = slash1 > slash2 ? slash1 : slash2;
    if (!slash || slash == path) return 0;
    *slash = '\0';
    return 1;
}

static int has_manifest(const char *dir) {
    char path[1024];
    if (!join2(path, sizeof(path), dir, "mellow.json")) return 0;
    if (path_exists(path)) return 1;
    if (!join2(path, sizeof(path), dir, "mellow.toml")) return 0;
    return path_exists(path);
}

static int file_contains_entry(const char *manifest_path, char *entry, size_t entry_size) {
    FILE *f;
    char line[512];
    if (!manifest_path || !entry || entry_size == 0) return 0;
    f = fopen(manifest_path, "r");
    if (!f) return 0;
    while (fgets(line, sizeof(line), f)) {
        char *p = strstr(line, "\"entry\"");
        char quote = '"';
        if (!p) {
            p = strstr(line, "entry");
            quote = '"';
        }
        if (!p) continue;
        p = strchr(p, ':');
        if (!p) p = strchr(line, '=');
        if (!p) continue;
        while (*p && *p != '"' && *p != '\'') p++;
        if (*p == '"' || *p == '\'') {
            char *q;
            quote = *p++;
            q = strchr(p, quote);
            if (q && (size_t)(q - p) < entry_size) {
                memcpy(entry, p, (size_t)(q - p));
                entry[q - p] = '\0';
                fclose(f);
                return 1;
            }
        }
    }
    fclose(f);
    return 0;
}

static int resolve_entry_under(const char *package_root, char *out, size_t out_size) {
    char manifest[1024];
    char entry[512] = "src/main.mellow";
    char candidate[1024];
    if (!join2(manifest, sizeof(manifest), package_root, "manifest.json") || !path_exists(manifest)) {
        if (!join2(manifest, sizeof(manifest), package_root, "mellow.pkg.json") || !path_exists(manifest)) {
            if (!join2(manifest, sizeof(manifest), package_root, "mellow.toml") || !path_exists(manifest)) {
                return 0;
            }
        }
    }
    (void)file_contains_entry(manifest, entry, sizeof(entry));
    if (!join2(candidate, sizeof(candidate), package_root, entry)) return 0;
    if (!path_exists(candidate)) {
        size_t len = strlen(candidate);
        if (len > 7 && strcmp(candidate + len - 7, ".mellow") == 0) {
            candidate[len - 7] = '\0';
            strncat(candidate, ".mel", sizeof(candidate) - strlen(candidate) - 1);
        } else if (len > 4 && strcmp(candidate + len - 4, ".mel") == 0) {
            candidate[len - 4] = '\0';
            strncat(candidate, ".mellow", sizeof(candidate) - strlen(candidate) - 1);
        }
    }
    if (!path_exists(candidate)) return 0;
    snprintf(out, out_size, "%s", candidate);
    out[out_size - 1] = '\0';
    normalize_separators(out);
    return 1;
}

int mellowrt_package_name_valid(const char *name) {
    const char *p;
    if (!name || !*name) return 0;
    if (strstr(name, "..") || strchr(name, ':') || name[0] == '/' || name[0] == '\\') return 0;
    for (p = name; *p; ++p) {
        if (isalnum((unsigned char)*p) || *p == '-' || *p == '_' || *p == '.' || *p == '/' || *p == '@') continue;
        return 0;
    }
    return 1;
}

int mellowrt_find_project_root(const char *source_path, char *out, size_t out_size) {
    char dir[1024];
    if (!dirname_of(source_path, dir, sizeof(dir))) return 0;
    for (;;) {
        if (has_manifest(dir)) {
            snprintf(out, out_size, "%s", dir);
            out[out_size - 1] = '\0';
            return 1;
        }
        if (!parent_dir(dir)) break;
    }
    return dirname_of(source_path, out, out_size);
}

int mellowrt_resolve_package_entry(const char *source_path, const char *package_name, char *out, size_t out_size) {
    char project[1024];
    char candidate[1024];
    char cwd[1024];
    if (!mellowrt_package_name_valid(package_name)) return 0;
    if (!mellowrt_find_project_root(source_path, project, sizeof(project))) return 0;

    if (join2(candidate, sizeof(candidate), project, "mellow_packages/installed") &&
        join2(candidate, sizeof(candidate), candidate, package_name) &&
        join2(candidate, sizeof(candidate), candidate, "current/package") &&
        resolve_entry_under(candidate, out, out_size)) return 1;

    if (join2(candidate, sizeof(candidate), project, "mellow_packages/registry") &&
        join2(candidate, sizeof(candidate), candidate, package_name)) {
        char ver_root[1024];
        snprintf(ver_root, sizeof(ver_root), "%s%c0.1.0", candidate, PATH_SEP);
        normalize_separators(ver_root);
        if (resolve_entry_under(ver_root, out, out_size)) return 1;
    }

    if (GETCWD(cwd, (int)sizeof(cwd))) {
        cwd[sizeof(cwd) - 1] = '\0';
        normalize_separators(cwd);
        if (join2(candidate, sizeof(candidate), cwd, "starter_packages") &&
            join2(candidate, sizeof(candidate), candidate, package_name) &&
            resolve_entry_under(candidate, out, out_size)) return 1;
        if (join2(candidate, sizeof(candidate), cwd, "mellow_packages/registry") &&
            join2(candidate, sizeof(candidate), candidate, package_name)) {
            char ver_root[1024];
            snprintf(ver_root, sizeof(ver_root), "%s%c0.1.0", candidate, PATH_SEP);
            normalize_separators(ver_root);
            if (resolve_entry_under(ver_root, out, out_size)) return 1;
        }
    }
    return 0;
}
