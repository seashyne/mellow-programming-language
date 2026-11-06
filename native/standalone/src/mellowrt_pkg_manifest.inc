/* ── package manifest (mellow.toml / mellow.pkg.json) ────────────────────── */

#define PKG_MAX_AUTHORS 8
#define PKG_MAX_KEYWORDS 16
#define PKG_MAX_DEPS 32

typedef struct {
    char name[128];
    char version[64];
    char entry[256];
    char description[512];
    char license[64];
    char visibility[64];
    char namespace_[128];
    char authors[PKG_MAX_AUTHORS][128];
    int author_count;
    char keywords[PKG_MAX_KEYWORDS][64];
    int keyword_count;
    char badges[PKG_MAX_KEYWORDS][64];
    int badge_count;
    char dep_names[PKG_MAX_DEPS][128];
    char dep_specs[PKG_MAX_DEPS][128];
    int dep_count;
    int official;
    int deprecated;
} PkgManifest;

static void pk_manifest_defaults(PkgManifest *m, const char *folder) {
    memset(m, 0, sizeof *m);
    if (folder && *folder) pk_normalize_name(folder, m->name, sizeof m->name);
    else snprintf(m->name, sizeof m->name, "pkg");
    snprintf(m->version, sizeof m->version, "0.1.0");
    snprintf(m->entry, sizeof m->entry, "src/main.mellow");
    snprintf(m->description, sizeof m->description, "Mellow package");
    snprintf(m->license, sizeof m->license, "MIT");
    snprintf(m->visibility, sizeof m->visibility, "public");
    snprintf(m->keywords[0], sizeof m->keywords[0], "mellow");
    m->keyword_count = 1;
}

static int pk_manifest_dep_index(const PkgManifest *m, const char *name) {
    int i;
    for (i = 0; i < m->dep_count; ++i) {
        if (!strcmp(m->dep_names[i], name)) return i;
    }
    return -1;
}

static int pk_manifest_set_dep(PkgManifest *m, const char *name, const char *spec) {
    int index = pk_manifest_dep_index(m, name);
    if (index < 0) {
        if (m->dep_count >= PKG_MAX_DEPS) return 0;
        index = m->dep_count++;
        snprintf(m->dep_names[index], sizeof m->dep_names[index], "%s", name);
    }
    snprintf(m->dep_specs[index], sizeof m->dep_specs[index], "%s", spec ? spec : "*");
    return 1;
}

static int pk_manifest_remove_dep(PkgManifest *m, const char *name) {
    int index = pk_manifest_dep_index(m, name);
    int i;
    if (index < 0) return 0;
    for (i = index; i + 1 < m->dep_count; ++i) {
        char dep_name[sizeof m->dep_names[0]];
        char dep_spec[sizeof m->dep_specs[0]];
        snprintf(dep_name, sizeof dep_name, "%s", m->dep_names[i + 1]);
        snprintf(dep_spec, sizeof dep_spec, "%s", m->dep_specs[i + 1]);
        snprintf(m->dep_names[i], sizeof m->dep_names[i], "%s", dep_name);
        snprintf(m->dep_specs[i], sizeof m->dep_specs[i], "%s", dep_spec);
    }
    m->dep_count--;
    return 1;
}

static void pk_manifest_add_author(PkgManifest *m, const char *author) {
    char text[128];
    char *trimmed;
    int i;
    if (!author || m->author_count >= PKG_MAX_AUTHORS) return;
    snprintf(text, sizeof text, "%s", author);
    trimmed = pk_trim(text);
    if (!*trimmed) return;
    for (i = 0; i < m->author_count; ++i) {
        if (!strcmp(m->authors[i], trimmed)) return;
    }
    snprintf(m->authors[m->author_count++], sizeof m->authors[0], "%s", trimmed);
}

static void pk_manifest_add_keyword(PkgManifest *m, const char *keyword) {
    char text[64];
    char *trimmed;
    int i;
    if (!keyword || m->keyword_count >= PKG_MAX_KEYWORDS) return;
    snprintf(text, sizeof text, "%s", keyword);
    trimmed = pk_trim(text);
    if (!*trimmed) return;
    for (i = 0; i < m->keyword_count; ++i) {
        if (!strcmp(m->keywords[i], trimmed)) return;
    }
    snprintf(m->keywords[m->keyword_count++], sizeof m->keywords[0], "%s", trimmed);
}

static void pk_manifest_creator(const PkgManifest *m, char *out, size_t cap) {
    size_t used = 0;
    int i;
    out[0] = '\0';
    for (i = 0; i < m->author_count; ++i) {
        int wrote = snprintf(out + used, cap - used, "%s%s", i ? ", " : "", m->authors[i]);
        if (wrote < 0 || (size_t)wrote >= cap - used) break;
        used += (size_t)wrote;
    }
    if (!out[0]) snprintf(out, cap, "unknown");
}

/* ── TOML subset ─────────────────────────────────────────────────────────── */

static void pk_toml_unescape(const char *src, char *out, size_t cap) {
    size_t j = 0;
    const char *p;
    for (p = src; p && *p && j + 1 < cap; ++p) {
        if (*p == '\\' && p[1]) {
            ++p;
            if (*p == 'n') out[j++] = '\n';
            else if (*p == 't') out[j++] = '\t';
            else if (*p == 'r') out[j++] = '\r';
            else out[j++] = *p;
        } else {
            out[j++] = *p;
        }
    }
    out[j] = '\0';
}

static const char *pk_toml_value(const char *value, char *out, size_t cap) {
    const char *start;
    const char *end;
    if (!value) {
        if (cap) out[0] = '\0';
        return NULL;
    }
    value = pk_trim((char *)value);
    if (*value != '"' && *value != '\'') {
        snprintf(out, cap, "%s", value);
        return value + strlen(value);
    }
    start = value + 1;
    end = strchr(start, *value);
    if (!end) end = start + strlen(start);
    {
        size_t len = (size_t)(end - start);
        char raw[1024];
        if (len >= sizeof raw) len = sizeof raw - 1;
        memcpy(raw, start, len);
        raw[len] = '\0';
        pk_toml_unescape(raw, out, cap);
    }
    return *end ? end + 1 : end;
}

/* Collect "a", "b" items from one or more bracketed array lines. */
static void pk_toml_array(const char *value, PkgManifest *m, int keywords) {
    const char *p = value;
    while (p && *p) {
        while (*p && *p != '"' && *p != '\'') ++p;
        if (!*p) break;
        {
            char item[256];
            const char *next = pk_toml_value(p, item, sizeof item);
            if (!next) break;
            if (keywords) pk_manifest_add_keyword(m, item);
            else pk_manifest_add_author(m, item);
            p = next;
        }
    }
}

static int pk_manifest_parse_toml(PkgManifest *m, const char *text) {
    char line[2048];
    char section[128] = "";
    const char *cursor = text;
    while (cursor && *cursor) {
        size_t len = 0;
        while (cursor[len] && cursor[len] != '\n' && len + 1 < sizeof line) ++len;
        memcpy(line, cursor, len);
        line[len] = '\0';
        cursor += len;
        if (*cursor == '\n') ++cursor;
        {
            char *body = pk_trim(line);
            char *eq;
            if (!*body || *body == '#') continue;
            if (*body == '[') {
                char *close = strchr(body, ']');
                if (close) {
                    *close = '\0';
                    snprintf(section, sizeof section, "%s", pk_trim(body + 1));
                }
                continue;
            }
            eq = strchr(body, '=');
            if (!eq) continue;
            *eq = '\0';
            {
                char *key = pk_trim(body);
                char *value = pk_trim(eq + 1);
                char text_value[1024];
                if (!strcmp(section, "dependencies")) {
                    pk_toml_value(value, text_value, sizeof text_value);
                    pk_manifest_set_dep(m, key, text_value);
                } else if (!strcmp(key, "name")) {
                    pk_toml_value(value, m->name, sizeof m->name);
                } else if (!strcmp(key, "version")) {
                    pk_toml_value(value, m->version, sizeof m->version);
                } else if (!strcmp(key, "entry")) {
                    pk_toml_value(value, m->entry, sizeof m->entry);
                } else if (!strcmp(key, "description")) {
                    pk_toml_value(value, m->description, sizeof m->description);
                } else if (!strcmp(key, "license")) {
                    pk_toml_value(value, m->license, sizeof m->license);
                } else if (!strcmp(key, "visibility")) {
                    pk_toml_value(value, m->visibility, sizeof m->visibility);
                } else if (!strcmp(key, "namespace")) {
                    pk_toml_value(value, m->namespace_, sizeof m->namespace_);
                } else if (!strcmp(key, "official")) {
                    m->official = !strncmp(value, "true", 4);
                } else if (!strcmp(key, "deprecated")) {
                    m->deprecated = !strncmp(value, "true", 4);
                } else if (!strcmp(key, "authors")) {
                    m->author_count = 0;
                    pk_toml_array(value, m, 0);
                } else if (!strcmp(key, "keywords")) {
                    m->keyword_count = 0;
                    pk_toml_array(value, m, 1);
                } else if (!strcmp(key, "badges")) {
                    m->badge_count = 0;
                    {
                        const char *p = value;
                        while (p && *p && m->badge_count < PKG_MAX_KEYWORDS) {
                            char item[64];
                            while (*p && *p != '"' && *p != '\'') ++p;
                            if (!*p) break;
                            p = pk_toml_value(p, item, sizeof item);
                            snprintf(m->badges[m->badge_count++], sizeof m->badges[0], "%s", item);
                        }
                    }
                }
            }
        }
    }
    return 1;
}

static void pk_manifest_from_json(PkgManifest *m, const PjValue *root) {
    PjValue *item;
    size_t i;
    if (!root || root->type != PJ_OBJECT) return;
    snprintf(m->name, sizeof m->name, "%s", pj_str(root, "name", m->name));
    snprintf(m->version, sizeof m->version, "%s", pj_str(root, "version", m->version));
    snprintf(m->entry, sizeof m->entry, "%s", pj_str(root, "entry", m->entry));
    snprintf(m->description, sizeof m->description, "%s", pj_str(root, "description", m->description));
    snprintf(m->license, sizeof m->license, "%s", pj_str(root, "license", m->license));
    snprintf(m->visibility, sizeof m->visibility, "%s", pj_str(root, "visibility", m->visibility));
    snprintf(m->namespace_, sizeof m->namespace_, "%s", pj_str(root, "namespace", ""));
    m->official = pj_bool(root, "official", 0);
    m->deprecated = pj_bool(root, "deprecated", 0);
    item = pj_obj_get(root, "authors");
    if (!item || item->type != PJ_ARRAY) item = pj_obj_get(root, "author");
    if (item && item->type == PJ_STRING) {
        pk_manifest_add_author(m, item->string);
    } else if (item && item->type == PJ_ARRAY) {
        m->author_count = 0;
        for (i = 0; i < item->count; ++i) {
            if (item->items[i]->type == PJ_STRING) pk_manifest_add_author(m, item->items[i]->string);
        }
    }
    item = pj_obj_get(root, "keywords");
    if (item && item->type == PJ_ARRAY) {
        m->keyword_count = 0;
        for (i = 0; i < item->count; ++i) {
            if (item->items[i]->type == PJ_STRING) pk_manifest_add_keyword(m, item->items[i]->string);
        }
    }
    item = pj_obj_get(root, "dependencies");
    if (item && item->type == PJ_OBJECT) {
        for (i = 0; i < item->count; ++i) {
            if (item->items[i]->type == PJ_STRING)
                pk_manifest_set_dep(m, item->keys[i], item->items[i]->string);
        }
    }
}

#include "mellowrt_pkg_manifest_part1.inc"
