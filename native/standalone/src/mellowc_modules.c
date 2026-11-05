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
        {"clamp",50},{"math.clamp",50},{"lerp",51},{"math.lerp",51},
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
        {"canvas_save",34},{"canvas.save",34},
        {"workers",35},{"thread.workers",35},{"worker_count",36},{"thread.worker_count",36},
        {"scheduler_mode",37},{"thread.scheduler_mode",37},
        {"money",38},{"money_of",38},{"money.of",38},
        {"money_add",39},{"money.add",39},
        {"money_sub",40},{"money.sub",40},
        {"money_mul",41},{"money.mul",41},
        {"money_div",42},{"money.div",42},
        {"money_quantize",43},{"money.quantize",43},
        {"money_format",44},{"money.format",44},
        {"money_amount",45},{"money.amount",45},
        {"money_currency",46},{"money.currency",46},
        {"money_eq",47},{"money.eq",47},
        {"money_lt",48},{"money.lt",48},
        {"money_gt",49},{"money.gt",49},
        {"server_request",52},{"server.request",52},
        {"server_json",53},{"server.json",53},
        {"server_text",54},{"server.text",54},
        {"server_status",55},{"server.status",55},
        {"ledger_create",56},{"ledger.create",56},
        {"ledger_post",57},{"ledger.post",57},
        {"ledger_verify",58},{"ledger.verify",58},
        {"ledger_balance",59},{"ledger.balance",59},
        {"ledger_entries",60},{"ledger.entries",60},
        {"storage_dir",61},{"storage.dir",61},
        {"storage_pwd",62},{"storage.pwd",62},
        {"storage_info",63},{"storage.info",63},
        {"save_data",64},{"storage.save",64},
        {"load_data",65},{"storage.load",65},
        {"mkdir",66},{"storage.mkdir",66},
        {"fs_read",67},{"fs.read",67},
        {"fs_write",68},{"fs.write",68},
        {"fs_append",69},{"fs.append",69},
        {"fs_exists",70},{"fs.exists",70},
        {"fs_delete",71},{"fs.delete",71},
        {"fs_mkdir",72},{"fs.mkdir",72},
        {"fs_pwd",73},{"fs.pwd",73},
        {"file_read",74},{"file.read",74},
        {"file_write",75},{"file.write",75},
        {"file_append",76},{"file.append",76},
        {"file_exists",77},{"file.exists",77},
        {"file_delete",78},{"file.delete",78},
        {"random",100},{"random.range",100},
        {"ai.model_create",110},{"ai.train",111},{"ai.predict",112},
        {"ai.model_save",113},{"ai.model_load",114},{"ai.embed",115},
        {"ai.chat",116},{"ai.runtime_boot",117},{"ai.runtime_info",118},
        {"ai.session_open",119},{"ai.session_message",120},{"ai.session_history",121},
        {"ai.prompt_template",122},{"ai.vector_search",123},{"ai.rag_answer",124},
        {"ai.loss_history",125},{"ai.model_info",126},{"ai.models_list",127},
        {"ai.api_providers",128},{"ai.api_configure",129},{"ai.api_complete",130},
        {"ai.api_embed",131},{"ai.decide",132},
        {"ai.llm_create",140},{"ai.llm_train",141},{"ai.llm_generate",142},
        {"ai.llm_tokenize",143},{"ai.llm_info",144},{"ai.llm_dataset",145},
        {"ai.llm_eval",146},{"ai.llm_complete",147},{"ai.llm_chat",148},
        {"ai.llm_models",149},{"ai.llm_backends",150},{"ai.llm_device_plan",151},
        {"ai.llm_tensor",152},{"ai.llm_tensor_batch",153},{"ai.llm_save",154},
        {"ai.llm_load",155},
        {"ai.seek",156},{"ai.steering.seek",156},
        {"ai.flee",157},{"ai.steering.flee",157},
        {"ai.arrive",158},{"ai.steering.arrive",158},
        {"ai.wander",159},{"ai.steering.wander",159},
        {"ai.patrol",160},{"ai.steering.patrol",160},
        {"ai.in_range",161},{"ai.perception.in_range",161},
        {"ai.in_sight",162},{"ai.perception.in_sight",162},
        {"ai.nearest",163},{"ai.perception.nearest",163},
        {"ai.filter_range",164},{"ai.perception.filter_range",164},
        {"string.len",200},{"string.lower",201},{"string.upper",202},
        {"string.trim",203},{"string.replace",204},{"string.find",205},
        {"string.split",206},{"string.join",207},
        {"string.starts_with",208},{"string.ends_with",209},{"string.contains",210},
        {"string.repeat",211},{"string.pad_left",212},{"string.pad_right",213},
        {"string.format",214},{"string.chr",215},{"string.ord",216},
        {"string.tostr",217},
        {"list.push",220},{"list.pop",221},{"list.len",222},
        {"list.insert",223},{"list.remove",224},{"list.has",225},
        {"list.sort",226},{"list.find",229},{"list.slice",230},
        {"list.reverse",231},{"list.count",233},{"list.enumerate",234},
        {"list.zip",235},{"list.sorted",236},{"list.reversed",237},
        {"list.any",238},{"list.all",239},
        {"list._extend",240},{"list._append_to_top",241},
        {"map.get",245},{"map.set",246},{"map.keys",247},
        {"map.values",248},{"map.has",249},
        {"type.is_number",252},{"type.is_string",253},{"type.is_bool",254},
        {"type.is_list",255},{"type.is_map",256},{"type.is_none",257},
        {"type.of",258},{"type.to_int",259},{"type.to_float",260},
        {"type.to_str",261},{"type.to_bool",262},{"type.to_list",263},
        {"json.encode",266},{"json.decode",267},
        {"math.round",270},{"math.pow",271},{"math.sin",272},{"math.cos",273},
        {"math.tan",274},{"math.atan2",275},{"math.pi",276},{"math.sign",277},
        {"math.fmod",278},{"math.deg_to_rad",279},{"math.rad_to_deg",280},
        {"math.distance",281},{"math.angle_between",282},{"math.sum",283},
        {"math.vec2",284},{"math.vec3",285},{"math.vector",286},
        {"math.vec",286},{"math.vec_add",287},{"math.vec_sub",288},
        {"math.vec_mul",289},{"math.vec_dot",290},{"math.vec_len",291},
        {"math.vec_norm",292},{"math.vec_dist",293},{"math.vec_dim",294},
        {"math.vec_axis",295},{"math.vec_lerp",296},{"math.vec_limit",297},
        {"time.unix",320},{"time.ms",321},{"time.now",322},
        {"assert.check",330},{"assert.eq",331},{"assert.ne",332},
        {"event.emit",333},
        {"game.ease_linear",340},{"game.easing.linear",340},
        {"game.ease_in_quad",341},{"game.easing.in_quad",341},
        {"game.ease_out_quad",342},{"game.easing.out_quad",342},
        {"game.ease_in_out_quad",343},{"game.easing.in_out_quad",343},
        {"game.ease_in_cubic",344},{"game.easing.in_cubic",344},
        {"game.ease_out_cubic",345},{"game.easing.out_cubic",345},
        {"game.ease_in_out_cubic",346},{"game.easing.in_out_cubic",346},
        {"game.ease_in_back",347},{"game.easing.in_back",347},
        {"game.ease_out_back",348},{"game.easing.out_back",348},
        {"game.ease_out_bounce",349},{"game.easing.out_bounce",349},
        {"game.ease_out_elastic",350},{"game.easing.out_elastic",350},
        {"game.tween",351},{"game.tween.step",351},
        {"game.neighbors4",352},{"game.grid.neighbors4",352},
        {"game.neighbors8",353},{"game.grid.neighbors8",353},
        {"game.astar",354},{"game.path.astar",354},
        {"game.scene_create",355},{"game.scene.create",355},
        {"game.entity_create",356},{"game.entity.create",356},
        {"game.entity_move",357},{"game.entity.move",357},
        {"game.collide_aabb",358},{"game.physics.collide_aabb",358},
        {"game.anim_frame",359},{"game.anim.frame",359}
    };
    size_t i;
    for (i=0;i<sizeof(builtins)/sizeof(builtins[0]);++i)
        if (strlen(builtins[i].name)==len && memcmp(name,builtins[i].name,len)==0) return builtins[i].id;
    if (len > 4 && memcmp(name, "std.", 4) == 0) return builtin_id(name + 4, len - 4);
    return 0;
}

static int module_is_builtin(const char *module) {
    return strcmp(module, "io") == 0 || strcmp(module, "sys") == 0 ||
           strcmp(module, "math") == 0 || strcmp(module, "time") == 0 ||
           strcmp(module, "gc") == 0 || strcmp(module, "thread") == 0 ||
           strcmp(module, "chan") == 0 || strcmp(module, "canvas") == 0 ||
           strcmp(module, "money") == 0 || strcmp(module, "server") == 0 ||
           strcmp(module, "ledger") == 0 || strcmp(module, "storage") == 0 ||
           strcmp(module, "fs") == 0 || strcmp(module, "file") == 0 ||
           strcmp(module, "ai") == 0 || strcmp(module, "std.ai") == 0 ||
           strcmp(module, "random") == 0 || strcmp(module, "std.random") == 0 ||
           strcmp(module, "string") == 0 || strcmp(module, "std.string") == 0 ||
           strcmp(module, "list") == 0 || strcmp(module, "std.list") == 0 ||
           strcmp(module, "map") == 0 || strcmp(module, "std.map") == 0 ||
           strcmp(module, "type") == 0 || strcmp(module, "std.type") == 0 ||
           strcmp(module, "json") == 0 || strcmp(module, "std.json") == 0 ||
           strcmp(module, "assert") == 0 || strcmp(module, "std.assert") == 0 ||
           strcmp(module, "event") == 0 || strcmp(module, "std.event") == 0 ||
           strcmp(module, "game") == 0 || strcmp(module, "std.game") == 0;
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

static int add_package_alias(Compiler *c, const char *package_name, const char *alias) {
    int i;
    if (!alias || !*alias) alias = package_name;
    for (i = 0; i < c->module_alias_count; ++i) {
        if (strcmp(c->module_aliases[i].alias, alias) == 0) {
            snprintf(c->module_aliases[i].module, sizeof(c->module_aliases[i].module), "pkg");
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
             sizeof(c->module_aliases[c->module_alias_count].module), "pkg");
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

Function *resolve_package_function(Compiler *c, const char *name, size_t len) {
    const char *dot = memchr(name, '.', len);
    int i;
    if (!dot) return NULL;
    for (i = 0; i < c->module_alias_count; ++i) {
        size_t alias_len = strlen(c->module_aliases[i].alias);
        if (strcmp(c->module_aliases[i].module, "pkg") != 0) continue;
        if ((size_t)(dot - name) == alias_len && memcmp(name, c->module_aliases[i].alias, alias_len) == 0) {
            return find_function(c, dot + 1, len - alias_len - 1);
        }
    }
    return NULL;
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
            (void)resolved;
            return add_package_alias(c, module, alias) ? 1 : -1;
        }
    }
    set_error(c, "package import not installed");
    return -1;
}
