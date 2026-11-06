/* Game runtime fragment 1: numeric conversions and easing curves.
 *
 * Mirrors the Python host family for std.game. Numbers accept ints, floats,
 * bools, and strings exactly where Python's float()/int() would.
 */

static int std_game_parse_double(const char *text, size_t len, double *out) {
    char stack[64];
    char *buf = stack;
    char *end = NULL;
    double value;
    if (!text) return 0;
    if (len >= sizeof(stack)) {
        buf = (char *)malloc(len + 1);
        if (!buf) return 0;
    }
    memcpy(buf, text, len);
    buf[len] = '\0';
    value = strtod(buf, &end);
    if (end == buf) {
        if (buf != stack) free(buf);
        return 0;
    }
    while (*end && std_space(*end)) ++end;
    if (*end) {
        if (buf != stack) free(buf);
        return 0;
    }
    *out = value;
    if (buf != stack) free(buf);
    return 1;
}

static int std_game_parse_int(const char *text, size_t len, int64_t *out) {
    char stack[64];
    char *buf = stack;
    char *end = NULL;
    long long value;
    if (!text) return 0;
    if (len >= sizeof(stack)) {
        buf = (char *)malloc(len + 1);
        if (!buf) return 0;
    }
    memcpy(buf, text, len);
    buf[len] = '\0';
    value = strtoll(buf, &end, 10);
    if (end == buf) {
        if (buf != stack) free(buf);
        return 0;
    }
    while (*end && std_space(*end)) ++end;
    if (*end) {
        if (buf != stack) free(buf);
        return 0;
    }
    *out = (int64_t)value;
    if (buf != stack) free(buf);
    return 1;
}

static int std_game_number(const MValue *value, double *out) {
    if (!value) return 0;
    if (value->tag == MVAL_F64) { *out = value->as.f64; return 1; }
    if (value->tag == MVAL_I64) { *out = (double)value->as.i64; return 1; }
    if (value->tag == MVAL_BOOL) { *out = value->as.boolean ? 1.0 : 0.0; return 1; }
    if (value->tag == MVAL_STR)
        return std_game_parse_double(value->as.str.ptr ? value->as.str.ptr : "",
                                     value->as.str.len, out);
    return 0;
}

static int std_game_integer(const MValue *value, int64_t *out) {
    if (!value) return 0;
    if (value->tag == MVAL_I64) { *out = value->as.i64; return 1; }
    if (value->tag == MVAL_BOOL) { *out = value->as.boolean ? 1 : 0; return 1; }
    if (value->tag == MVAL_F64) {
        if (!isfinite(value->as.f64)) return 0;
        if (value->as.f64 < -9.2233720368547758e18 ||
            value->as.f64 > 9.2233720368547758e18) return 0;
        *out = (int64_t)value->as.f64;
        return 1;
    }
    if (value->tag == MVAL_STR)
        return std_game_parse_int(value->as.str.ptr ? value->as.str.ptr : "",
                                  value->as.str.len, out);
    return 0;
}

/* Optional argument: defaults when absent, but a present value must convert. */
static int std_game_opt_number(const MValue *args, size_t argc, size_t index,
                               double fallback, double *out) {
    if (index >= argc) { *out = fallback; return 1; }
    return std_game_number(&args[index], out);
}

static int std_game_opt_integer(const MValue *args, size_t argc, size_t index,
                                int64_t fallback, int64_t *out) {
    if (index >= argc) { *out = fallback; return 1; }
    return std_game_integer(&args[index], out);
}

/* Python's modulo keeps the sign of the divisor; C99 truncates toward zero. */
static int64_t std_game_mod(int64_t value, int64_t base) {
    int64_t result;
    if (base == 0) return 0;
    result = value % base;
    if (result < 0) result += base;
    return result;
}

static double std_game_mod_double(double value, double base) {
    double result = fmod(value, base);
    if (result < 0) result += base;
    return result;
}

static MValue std_game_float_pair(double x, double y) {
    MValue list;
    if (!ai_list_new(&list, 2)) return mval_none();
    ai_list_push(&list, mval_f64(x));
    ai_list_push(&list, mval_f64(y));
    return list;
}

static MValue std_game_int_pair(int64_t x, int64_t y) {
    MValue list;
    if (!ai_list_new(&list, 2)) return mval_none();
    ai_list_push(&list, mval_i64(x));
    ai_list_push(&list, mval_i64(y));
    return list;
}

static double std_game_ease(int id, double t) {
    switch (id) {
    case 340:
        return t;
    case 341:
        return t * t;
    case 342:
        return 1.0 - (1.0 - t) * (1.0 - t);
    case 343:
        if (t < 0.5) return 2.0 * t * t;
        return 1.0 - pow(-2.0 * t + 2.0, 2.0) / 2.0;
    case 344:
        return t * t * t;
    case 345:
        return 1.0 - pow(1.0 - t, 3.0);
    case 346:
        if (t < 0.5) return 4.0 * t * t * t;
        return 1.0 - pow(-2.0 * t + 2.0, 3.0) / 2.0;
    case 347: {
        const double c1 = 1.70158, c3 = 1.70158 + 1.0;
        return c3 * t * t * t - c1 * t * t;
    }
    case 348: {
        const double c1 = 1.70158, c3 = 1.70158 + 1.0;
        return 1.0 + c3 * pow(t - 1.0, 3.0) + c1 * pow(t - 1.0, 2.0);
    }
    case 349: {
        const double n1 = 7.5625, d1 = 2.75;
        if (t < 1.0 / d1) return n1 * t * t;
        if (t < 2.0 / d1) { t -= 1.5 / d1; return n1 * t * t + 0.75; }
        if (t < 2.5 / d1) { t -= 2.25 / d1; return n1 * t * t + 0.9375; }
        t -= 2.625 / d1;
        return n1 * t * t + 0.984375;
    }
    case 350: {
        double c4;
        if (t == 0.0) return 0.0;
        if (t == 1.0) return 1.0;
        c4 = (2.0 * 3.14159265358979323846) / 3.0;
        return pow(2.0, -10.0 * t) * sin((t * 10.0 - 0.75) * c4) + 1.0;
    }
    default:
        return t;
    }
}

static int std_game_ease_syscall(const MValue *args, size_t argc, MValue *out, int id) {
    double t;
    if (argc != 1 || !std_game_number(&args[0], &t)) return 0;
    *out = mval_f64(std_game_ease(id, t));
    return 1;
}

static int std_game_tween_syscall(const MValue *args, size_t argc, MValue *out) {
    double from, to, t, eased = 0.0;
    char *name = NULL;
    size_t name_len = 0;
    int known = 0, id = 340;
    if (argc < 3 || argc > 4) return 0;
    if (!std_game_number(&args[0], &from) || !std_game_number(&args[1], &to) ||
        !std_game_number(&args[2], &t)) return 0;
    if (argc >= 4) {
        name = std_text(&args[3], &name_len);
        if (!name) return 0;
        {
            static const struct { const char *name; int id; } curves[] = {
                {"linear", 340}, {"ease_linear", 340},
                {"in_quad", 341}, {"ease_in_quad", 341},
                {"out_quad", 342}, {"ease_out_quad", 342},
                {"in_out_quad", 343}, {"ease_in_out_quad", 343}
            };
            size_t i;
            for (i = 0; i < sizeof(curves) / sizeof(curves[0]); ++i) {
                if (strlen(curves[i].name) == name_len &&
                    memcmp(curves[i].name, name, name_len) == 0) {
                    id = curves[i].id;
                    known = 1;
                    break;
                }
            }
        }
        free(name);
        if (!known) id = 340;
    }
    eased = std_game_ease(id, t);
    *out = mval_f64(from + (to - from) * eased);
    return 1;
}
