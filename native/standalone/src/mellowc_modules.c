#include "mellowc_internal.h"
#include "mellowrt_packages.h"

#include <ctype.h>
#include <stdio.h>
#include <string.h>

static int builtin_id(const char *name, size_t len) {
    static const struct { const char *name; int id; } builtins[] = {
        {"print",1},{"println",1},{"io.print",1},{"io.println",1},
        {"len",2},{"clock_ms",3},{"time.clock_ms",3},{"getenv",4},{"sys.getenv",4},
        {"str",5},{"type",6},
        {"abs",7},{"math.abs",7},{"floor",8},{"math.floor",8},{"ceil",9},{"math.ceil",9},
        {"sqrt",10},{"math.sqrt",10},{"min",11},{"math.min",11},{"max",12},{"math.max",12},
        {"write",14},{"io.write",14},{"input",15},{"io.input",15},{"readline",15},{"io.readline",15},
        {"read_line",15},{"io.read_line",15},{"ask",15},{"io.ask",15},
        {"args",16},{"argv",16},{"sys.args",16},{"sys.argv",16},{"cwd",17},{"sys.cwd",17},
        {"sleep_ms",18},{"sys.sleep_ms",18},{"exit",19},{"sys.exit",19},{"range",20},
        {"gc_collect",21},{"gc.collect",21},{"gc_stats",22},{"gc.stats",22},
        {"spawn",23},{"thread.spawn",23},{"yield",24},{"thread.yield",24},
        {"channel",25},{"chan.channel",25},{"send",26},{"chan.send",26},
        {"recv",27},{"chan.recv",27},
        {"canvas_create",28},{"canvas.create",28},
        {"canvas_clear",29},{"canvas.clear",29},
        {"canvas_pixel",30},{"canvas.pixel",30},
        {"canvas_line",31},{"canvas.line",31},
        {"canvas_rect",32},{"canvas.rect",32},
        {"canvas_circle",33},{"canvas.circle",33},
        {"canvas_save",34},{"canvas.save",34}
    };
    size_t i;
    for (i=0;i<sizeof(builtins)/sizeof(builtins[0]);++i)
        if (strlen(builtins[i].name)==len && memcmp(name,builtins[i].name,len)==0) return builtins[i].id;
    return 0;
}

static int module_is_builtin(const char *module) {
    return strcmp(module, "io") == 0 || strcmp(module, "sys") == 0 ||
           strcmp(module, "math") == 0 || strcmp(module, "time") == 0 ||
           strcmp(module, "gc") == 0 || strcmp(module, "thread") == 0 ||
           strcmp(module, "chan") == 0 || strcmp(module, "canvas") == 0;
}

static int add_module_alias(Compiler *c, const char *module, const char *alias) {
    int i;
    if (!module_is_builtin(module)) {
        set_error(c, "unknown native module");
        return 0;
    }
    if (!alias || !*alias) alias = module;
    for (i = 0; i < c->module_alias_count; ++i) {
        if (strcmp(c->module_aliases[i].alias, alias) == 0) {
            snprintf(c->module_aliases[i].module, sizeof(c->module_aliases[i].module), "%s", module);
            return 1;
        }
    }
    if (c->module_alias_count >= 32) {
        set_error(c, "too many module imports");
        return 0;
    }
    snprintf(c->module_aliases[c->module_alias_count].alias,
             sizeof(c->module_aliases[c->module_alias_count].alias), "%s", alias);
    snprintf(c->module_aliases[c->module_alias_count].module,
             sizeof(c->module_aliases[c->module_alias_count].module), "%s", module);
    c->module_alias_count++;
    return 1;
}

int resolve_builtin_id(Compiler *c, const char *name, size_t len) {
    char rewritten[128];
    const char *dot = memchr(name, '.', len);
    int direct = builtin_id(name, len);
    int i;
    if (direct || !dot) return direct;
    for (i = 0; i < c->module_alias_count; ++i) {
        size_t alias_len = strlen(c->module_aliases[i].alias);
        if ((size_t)(dot - name) == alias_len && memcmp(name, c->module_aliases[i].alias, alias_len) == 0) {
            snprintf(rewritten, sizeof(rewritten), "%s.%.*s",
                     c->module_aliases[i].module, (int)(len - alias_len - 1), dot + 1);
            return builtin_id(rewritten, strlen(rewritten));
        }
    }
    return 0;
}

int parse_import_statement(Compiler *c, const char *text) {
    char module[64] = {0};
    char alias[64] = {0};
    const char *rest = NULL;
    const char *as_pos = NULL;
    size_t module_len;
    if (starts(text, "import ")) rest = trim((char *)text + 7);
    else if (starts(text, "use ")) rest = trim((char *)text + 4);
    else if (starts(text, "need ")) rest = trim((char *)text + 5);
    else return 0;

    as_pos = strstr(rest, " as ");
    if (!as_pos) {
        set_error(c, "module import requires 'as'");
        return -1;
    }
    module_len = (size_t)(as_pos - rest);
    while (module_len && isspace((unsigned char)rest[module_len - 1])) module_len--;
    if (module_len >= sizeof(module)) module_len = sizeof(module) - 1;
    snprintf(module, sizeof(module), "%.*s", (int)module_len, rest);
    snprintf(alias, sizeof(alias), "%s", trim((char *)as_pos + 4));

    if ((module[0] == '"' || module[0] == '\'') && module[strlen(module) - 1] == module[0]) {
        size_t n = strlen(module);
        memmove(module, module + 1, n - 2);
        module[n - 2] = '\0';
    }
    if (strncmp(module, "pkg:", 4) == 0) memmove(module, module + 4, strlen(module + 4) + 1);
    if (module_is_builtin(module)) return add_module_alias(c, module, alias) ? 1 : -1;
    {
        char resolved[1024];
        if (mellowrt_resolve_package_entry(c->source_name, module, resolved, sizeof(resolved))) {
            (void)alias;
            return 1;
        }
    }
    set_error(c, "package import not installed");
    return -1;
}
