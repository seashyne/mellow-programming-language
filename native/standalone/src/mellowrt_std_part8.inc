/* Standard-library fragment 8: std.math scalar helpers and vectors. */

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

/* 0.0/0.0 through a volatile keeps MSVC's C2124 constant-division check from
 * rejecting the NaN path; gcc folds it either way. */
static double std_math_nan(void) {
    volatile double zero = 0.0;
    return zero / zero;
}

static int std_vec_list(const MValue *value, size_t *n) {
    if (!value || value->tag != MVAL_LIST) return 0;
    if (value->as.list.len < 2 || value->as.list.len > 16) return 0;
    *n = value->as.list.len;
    return 1;
}

static int std_vec_component(const MValue *vector, size_t index, double *out) {
    if (index >= vector->as.list.len) return 0;
    return ai_number(&vector->as.list.items[index], out);
}

static int std_vec_result(MValue *out, const double *values, size_t n) {
    size_t i;
    if (!ai_list_new(out, n)) return 0;
    for (i = 0; i < n; ++i) std_list_append(out, mval_f64(values[i]));
    return 1;
}

static int std_vec_len_of(const MValue *vector, size_t n, double *len) {
    size_t i;
    double total = 0.0, value;
    for (i = 0; i < n; ++i) {
        if (!std_vec_component(vector, i, &value)) return 0;
        total += value * value;
    }
    *len = sqrt(total);
    return 1;
}

static int std_vector_construct(const MValue *args, size_t argc, MValue *out) {
    size_t i, n = 0, start = 0;
    double values[16];
    if (argc == 1 && args[0].tag == MVAL_LIST) {
        if (!std_vec_list(&args[0], &n)) return 0;
        for (i = 0; i < n; ++i)
            if (!std_vec_component(&args[0], i, &values[i])) return 0;
        return std_vec_result(out, values, n);
    }
    if (argc >= 3 && (args[0].tag == MVAL_I64 || args[0].tag == MVAL_F64)) {
        int64_t dim = ai_int_or(&args[0], -1);
        if (dim >= 2 && dim <= 16 && (size_t)dim == argc - 1) start = 1;
    }
    n = argc - start;
    if (n < 2 || n > 16) return 0;
    for (i = 0; i < n; ++i)
        if (!ai_number(&args[start + i], &values[i])) return 0;
    return std_vec_result(out, values, n);
}

static int std_vec_pair(const MValue *args, size_t argc, size_t *n, MValue *out) {
    if (argc != 2 || !std_vec_list(&args[0], n) || !std_vec_list(&args[1], n)) return 0;
    (void)out;
    return 1;
}

static int std_vec_binary_syscall(const MValue *args, size_t argc, MValue *out, int op) {
    size_t i, na, nb;
    double a, b, values[16];
    if (std_vec_pair(args, argc, &na, out) == 0 || !std_vec_list(&args[1], &nb) || na != nb) return 0;
    for (i = 0; i < na; ++i) {
        if (!std_vec_component(&args[0], i, &a) || !std_vec_component(&args[1], i, &b)) return 0;
        values[i] = op == 0 ? a + b : (op == 1 ? a - b : a * b);
    }
    return std_vec_result(out, values, na);
}

static int std_vec_scalar_syscall(const MValue *args, size_t argc, MValue *out) {
    size_t i, n;
    double scale, value, values[16];
    if (argc != 2 || !std_vec_list(&args[0], &n) || !ai_number(&args[1], &scale)) return 0;
    for (i = 0; i < n; ++i) {
        if (!std_vec_component(&args[0], i, &value)) return 0;
        values[i] = value * scale;
    }
    return std_vec_result(out, values, n);
}

static int std_vec_dot_syscall(const MValue *args, size_t argc, MValue *out) {
    size_t i, na, nb;
    double a, b, total = 0.0;
    if (std_vec_pair(args, argc, &na, out) == 0 || !std_vec_list(&args[1], &nb) || na != nb) return 0;
    for (i = 0; i < na; ++i) {
        if (!std_vec_component(&args[0], i, &a) || !std_vec_component(&args[1], i, &b)) return 0;
        total += a * b;
    }
    *out = mval_f64(total);
    return 1;
}

static int std_vec_len_syscall(const MValue *args, size_t argc, MValue *out) {
    size_t n;
    double len = 0.0;
    if (argc != 1 || !std_vec_list(&args[0], &n) || !std_vec_len_of(&args[0], n, &len)) return 0;
    *out = mval_f64(len);
    return 1;
}

static int std_vec_norm_syscall(const MValue *args, size_t argc, MValue *out) {
    size_t i, n;
    double len = 0.0, value, values[16];
    if (argc != 1 || !std_vec_list(&args[0], &n) || !std_vec_len_of(&args[0], n, &len)) return 0;
    for (i = 0; i < n; ++i) {
        if (!std_vec_component(&args[0], i, &value)) return 0;
        values[i] = len == 0.0 ? 0.0 : value / len;
    }
    return std_vec_result(out, values, n);
}

static int std_vec_dist_syscall(const MValue *args, size_t argc, MValue *out) {
    size_t i, na, nb;
    double a, b, total = 0.0;
    if (std_vec_pair(args, argc, &na, out) == 0 || !std_vec_list(&args[1], &nb) || na != nb) return 0;
    for (i = 0; i < na; ++i) {
        if (!std_vec_component(&args[0], i, &a) || !std_vec_component(&args[1], i, &b)) return 0;
        total += (a - b) * (a - b);
    }
    *out = mval_f64(sqrt(total));
    return 1;
}

static int std_vec_dim_syscall(const MValue *args, size_t argc, MValue *out) {
    size_t n;
    if (argc != 1 || !std_vec_list(&args[0], &n)) return 0;
    *out = mval_i64((int64_t)n);
    return 1;
}

static int std_vec_axis_syscall(const MValue *args, size_t argc, MValue *out) {
    size_t n;
    int64_t index = 0;
    double value = 0.0;
    if (argc != 2 || !std_vec_list(&args[0], &n) || !ai_integer(&args[1], &index)) return 0;
    if (index < 0 || index >= (int64_t)n) return 0;
    if (!std_vec_component(&args[0], (size_t)index, &value)) return 0;
    *out = mval_f64(value);
    return 1;
}

static int std_vec_lerp_syscall(const MValue *args, size_t argc, MValue *out) {
    size_t i, na, nb;
    double a, b, t, values[16];
    if (argc != 3 || !std_vec_list(&args[0], &na) || !std_vec_list(&args[1], &nb) ||
        na != nb || !ai_number(&args[2], &t)) return 0;
    for (i = 0; i < na; ++i) {
        if (!std_vec_component(&args[0], i, &a) || !std_vec_component(&args[1], i, &b)) return 0;
        values[i] = a + (b - a) * t;
    }
    return std_vec_result(out, values, na);
}

static int std_vec_limit_syscall(const MValue *args, size_t argc, MValue *out) {
    size_t i, n;
    double limit, len = 0.0, value, values[16];
    if (argc != 2 || !std_vec_list(&args[0], &n) || !ai_number(&args[1], &limit)) return 0;
    if (!std_vec_len_of(&args[0], n, &len)) return 0;
    if (limit < 0.0) limit = 0.0;
    for (i = 0; i < n; ++i) {
        if (!std_vec_component(&args[0], i, &value)) return 0;
        values[i] = (len == 0.0 || len <= limit) ? value : value * (limit / len);
    }
    return std_vec_result(out, values, n);
}

static int std_xy_arg(const MValue *value, double *x, double *y) {
    if (!value || value->tag != MVAL_LIST || value->as.list.len < 2) return 0;
    return ai_number(&value->as.list.items[0], x) && ai_number(&value->as.list.items[1], y);
}

/* Mirror Python's sum(): floats keep the total a float, and a value that
 * int() could not convert turns the whole call into 0. */
static int std_math_sum_syscall(const MValue *args, size_t argc, MValue *out) {
    size_t i;
    int use_float = 0;
    double total = 0.0;
    long long integer_total = 0;
    if (argc != 1) return 0;
    if (args[0].tag != MVAL_LIST) { *out = mval_i64(0); return 1; }
    for (i = 0; i < args[0].as.list.len; ++i) {
        const MValue *item = &args[0].as.list.items[i];
        if (item->tag == MVAL_F64) {
            use_float = 1;
            total += item->as.f64;
        } else if (item->tag == MVAL_I64) {
            integer_total += (long long)item->as.i64;
        } else if (item->tag == MVAL_BOOL) {
            integer_total += item->as.boolean ? 1 : 0;
        } else if (item->tag == MVAL_STR) {
            char *text = std_text(item, NULL), *end = NULL;
            long long parsed;
            if (!text) { *out = mval_i64(0); return 1; }
            errno = 0;
            parsed = strtoll(text, &end, 10);
            if (end == text || errno == ERANGE) { free(text); *out = mval_i64(0); return 1; }
            while (*end == ' ' || *end == '\t' || *end == '\n' || *end == '\r') end++;
            if (*end != '\0') { free(text); *out = mval_i64(0); return 1; }
            free(text);
            integer_total += parsed;
        } else {
            *out = mval_i64(0);
            return 1;
        }
    }
    if (use_float) *out = mval_f64(total + (double)integer_total);
    else *out = mval_i64((int64_t)integer_total);
    return 1;
}

static int std_math_syscall(MellowRuntimeContext *ctx, int id, const MValue *args,
                            size_t argc, MValue *out) {
    double a = 0.0, b = 0.0;
    (void)ctx;
    switch (id) {
    case 281: {
        double ax = 0.0, ay = 0.0, bx = 0.0, by = 0.0;
        if (argc != 2 || !std_xy_arg(&args[0], &ax, &ay) || !std_xy_arg(&args[1], &bx, &by)) return 0;
        *out = mval_f64(sqrt((bx - ax) * (bx - ax) + (by - ay) * (by - ay)));
        return 1;
    }
    case 282: {
        double ax = 0.0, ay = 0.0, bx = 0.0, by = 0.0;
        if (argc != 2 || !std_xy_arg(&args[0], &ax, &ay) || !std_xy_arg(&args[1], &bx, &by)) return 0;
        *out = mval_f64(atan2(by - ay, bx - ax) * 180.0 / M_PI);
        return 1;
    }
    case 283: return std_math_sum_syscall(args, argc, out);
    case 284:
    case 285: {
        size_t i, n = id == 284 ? 2 : 3;
        double values[3];
        if (argc != n) return 0;
        for (i = 0; i < n; ++i)
            if (!ai_number(&args[i], &values[i])) return 0;
        return std_vec_result(out, values, n);
    }
    case 286: return std_vector_construct(args, argc, out);
    case 287: return std_vec_binary_syscall(args, argc, out, 0);
    case 288: return std_vec_binary_syscall(args, argc, out, 1);
    case 289: return std_vec_scalar_syscall(args, argc, out);
    case 290: return std_vec_dot_syscall(args, argc, out);
    case 291: return std_vec_len_syscall(args, argc, out);
    case 292: return std_vec_norm_syscall(args, argc, out);
    case 293: return std_vec_dist_syscall(args, argc, out);
    case 294: return std_vec_dim_syscall(args, argc, out);
    case 295: return std_vec_axis_syscall(args, argc, out);
    case 296: return std_vec_lerp_syscall(args, argc, out);
    case 297: return std_vec_limit_syscall(args, argc, out);
    default:
        break;
    }
    if (argc == 0 && id == 276) { *out = mval_f64(M_PI); return 1; }
    if (id == 279 || id == 280) {
        if (argc != 1 || !ai_number(&args[0], &a)) return 0;
        *out = mval_f64(id == 279 ? a * M_PI / 180.0 : a * 180.0 / M_PI);
        return 1;
    }
    if (id == 275 || id == 278) {
        if (argc != 2 || !ai_number(&args[0], &a) || !ai_number(&args[1], &b)) return 0;
        if (id == 275) *out = mval_f64(atan2(a, b));
        else if (b == 0.0) *out = mval_f64(std_math_nan());
        else *out = mval_f64(a - floor(a / b) * b);
        return 1;
    }
    if (argc != 1 && id != 271) return 0;
    if (id == 271) {
        if (argc != 2 || !ai_number(&args[0], &a) || !ai_number(&args[1], &b)) return 0;
        *out = mval_f64(pow(a, b));
        return 1;
    }
    if (!ai_number(&args[0], &a)) return 0;
    switch (id) {
    case 270: *out = mval_i64((int64_t)nearbyint(a)); return 1;
    case 272: *out = mval_f64(sin(a)); return 1;
    case 273: *out = mval_f64(cos(a)); return 1;
    case 274: *out = mval_f64(tan(a)); return 1;
    case 277: *out = mval_i64(a > 0.0 ? 1 : (a < 0.0 ? -1 : 0)); return 1;
    default: return 0;
    }
}
