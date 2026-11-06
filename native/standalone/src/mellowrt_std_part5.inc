/* Standard-library fragment 5: std.map and std.type. */

static int std_map_lookup(const MValue *map, const MValue *key, const MValue **value) {
    size_t i;
    for (i = 0; i < map->as.map.len; ++i) {
        if (std_values_equal(&map->as.map.keys[i], key)) {
            *value = &map->as.map.values[i];
            return 1;
        }
    }
    return 0;
}

static int std_map_syscall(MellowRuntimeContext *ctx, int id, const MValue *args,
                           size_t argc, MValue *out) {
    const MValue *value = NULL;
    size_t i;
    (void)ctx;
    if (argc < 1 || args[0].tag != MVAL_MAP) return 0;
    switch (id) {
    case 245:
        if (argc < 2 || argc > 3) return 0;
        if (std_map_lookup(&args[0], &args[1], &value)) *out = std_clone(value);
        else *out = argc == 3 ? std_clone(&args[2]) : mval_none();
        return 1;
    case 246:
        if (argc != 3) return 0;
        *out = std_clone(&args[0]);
        return std_map_set(out, std_clone(&args[1]), std_clone(&args[2]));
    case 247:
        if (argc != 1 || !ai_list_new(out, args[0].as.map.len)) return 0;
        for (i = 0; i < args[0].as.map.len; ++i)
            std_list_append(out, std_clone(&args[0].as.map.keys[i]));
        return 1;
    case 248:
        if (argc != 1 || !ai_list_new(out, args[0].as.map.len)) return 0;
        for (i = 0; i < args[0].as.map.len; ++i)
            std_list_append(out, std_clone(&args[0].as.map.values[i]));
        return 1;
    case 249:
        if (argc != 2) return 0;
        *out = mval_bool(std_map_lookup(&args[0], &args[1], &value));
        return 1;
    default:
        return 0;
    }
}

static int std_to_int_syscall(const MValue *args, size_t argc, MValue *out) {
    double number = 0.0;
    if (argc != 1) return 0;
    if (ai_number(&args[0], &number)) {
        *out = mval_i64((int64_t)number);
        return 1;
    }
    if (args[0].tag == MVAL_STR) {
        char *text = std_text(&args[0], NULL);
        char *end = NULL;
        double parsed;
        if (!text) return 0;
        parsed = strtod(text, &end);
        free(text);
        if (end && *end == '\0') { *out = mval_i64((int64_t)parsed); return 1; }
    }
    *out = mval_i64(0);
    return 1;
}

static int std_to_float_syscall(const MValue *args, size_t argc, MValue *out) {
    double number = 0.0;
    if (argc != 1) return 0;
    if (ai_number(&args[0], &number)) {
        *out = mval_f64(number);
        return 1;
    }
    if (args[0].tag == MVAL_STR) {
        char *text = std_text(&args[0], NULL);
        char *end = NULL;
        double parsed;
        if (!text) return 0;
        parsed = strtod(text, &end);
        free(text);
        if (end && *end == '\0') { *out = mval_f64(parsed); return 1; }
    }
    *out = mval_f64(0.0);
    return 1;
}

static int std_to_bool_syscall(const MValue *args, size_t argc, MValue *out) {
    if (argc != 1) return 0;
    if (args[0].tag == MVAL_STR) {
        const char *text = args[0].as.str.ptr;
        size_t len = args[0].as.str.len;
        int truth = 1;
        if (len == 0) truth = 0;
        else if (len == 1 && text[0] == '0') truth = 0;
        else if (len == 4 && (text[0] == 'n' || text[0] == 'N') &&
                 (text[1] == 'o' || text[1] == 'O') && (text[2] == 'n' || text[2] == 'N') &&
                 (text[3] == 'e' || text[3] == 'E')) truth = 0;
        else if (len == 5 && (text[0] == 'f' || text[0] == 'F') &&
                 (text[1] == 'a' || text[1] == 'A') && (text[2] == 'l' || text[2] == 'L') &&
                 (text[3] == 's' || text[3] == 'S') && (text[4] == 'e' || text[4] == 'E')) truth = 0;
        *out = mval_bool(truth);
        return 1;
    }
    if (args[0].tag == MVAL_BOOL) { *out = mval_bool(args[0].as.boolean); return 1; }
    if (args[0].tag == MVAL_I64) { *out = mval_bool(args[0].as.i64 != 0); return 1; }
    if (args[0].tag == MVAL_F64) { *out = mval_bool(args[0].as.f64 != 0.0); return 1; }
    *out = mval_bool(args[0].tag != MVAL_NONE);
    return 1;
}

static int std_to_list_syscall(const MValue *args, size_t argc, MValue *out) {
    size_t i;
    if (argc != 1) return 0;
    if (args[0].tag == MVAL_LIST) { *out = std_clone(&args[0]); return 1; }
    if (!ai_list_new(out, 8)) return 0;
    if (args[0].tag == MVAL_STR) {
        size_t pos = 0, len = args[0].as.str.len;
        int32_t cp;
        while (pos < len && ai_utf8_decode(args[0].as.str.ptr, len, &pos, &cp)) {
            char bytes[4];
            int n = ai_utf8_encode(cp, bytes);
            std_list_append(out, mval_owned_copy(bytes, (size_t)(n > 0 ? n : 0)));
        }
        return 1;
    }
    if (args[0].tag == MVAL_MAP) {
        for (i = 0; i < args[0].as.map.len; ++i)
            std_list_append(out, std_clone(&args[0].as.map.keys[i]));
        return 1;
    }
    if (args[0].tag != MVAL_NONE) std_list_append(out, std_clone(&args[0]));
    return 1;
}

static int std_type_syscall(MellowRuntimeContext *ctx, int id, const MValue *args,
                            size_t argc, MValue *out) {
    (void)ctx;
    if (argc != 1) return 0;
    switch (id) {
    case 252: *out = mval_bool(args[0].tag == MVAL_I64 || args[0].tag == MVAL_F64); return 1;
    case 253: *out = mval_bool(args[0].tag == MVAL_STR); return 1;
    case 254: *out = mval_bool(args[0].tag == MVAL_BOOL); return 1;
    case 255: *out = mval_bool(args[0].tag == MVAL_LIST); return 1;
    case 256: *out = mval_bool(args[0].tag == MVAL_MAP); return 1;
    case 257: *out = mval_bool(args[0].tag == MVAL_NONE); return 1;
    case 258:
        if (args[0].tag == MVAL_BOOL) *out = std_own_text("bool", 4);
        else if (args[0].tag == MVAL_I64 || args[0].tag == MVAL_F64) *out = std_own_text("number", 6);
        else if (args[0].tag == MVAL_STR) *out = std_own_text("string", 6);
        else if (args[0].tag == MVAL_LIST) *out = std_own_text("list", 4);
        else if (args[0].tag == MVAL_MAP) *out = std_own_text("map", 3);
        else if (args[0].tag == MVAL_NONE) *out = std_own_text("none", 4);
        else *out = std_own_text("unknown", 7);
        return 1;
    case 259: return std_to_int_syscall(args, argc, out);
    case 260: return std_to_float_syscall(args, argc, out);
    case 261: {
        char *text = std_mellow_text(&args[0], NULL);
        if (!text) return 0;
        *out = mval_owned_copy(text, strlen(text));
        free(text);
        return 1;
    }
    case 262: return std_to_bool_syscall(args, argc, out);
    case 263: return std_to_list_syscall(args, argc, out);
    default: return 0;
    }
}
