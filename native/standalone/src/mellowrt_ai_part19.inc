/* AI runtime fragment 19: the tensor kernels behind ai.llm_tensor. */

static const char *ai_tensor_backend = "mellow-native-c";

static double *ai_double_list(const MValue *value, size_t *count) {
    size_t i;
    double *out;
    *count = 0;
    if (!value || value->tag != MVAL_LIST || value->as.list.len == 0) return NULL;
    out = (double *)calloc(value->as.list.len, sizeof(double));
    if (!out) return NULL;
    for (i = 0; i < value->as.list.len; ++i)
        out[i] = ai_num_or(&value->as.list.items[i], 0.0);
    *count = value->as.list.len;
    return out;
}

static MValue ai_values_from_doubles(const double *values, size_t count) {
    MValue list;
    size_t i;
    ai_list_new(&list, count);
    for (i = 0; i < count; ++i) ai_list_push(&list, mval_f64(values[i]));
    return list;
}

static MValue ai_tensor_result(const char *op, MValue values) {
    MValue result;
    ai_map_new(&result, 3);
    ai_map_put_str(&result, "op", op);
    ai_map_put_str(&result, "backend", ai_tensor_backend);
    ai_map_put(&result, "values", values);
    return result;
}

static MValue ai_tensor_failure(const char *op, const char *reason) {
    char message[256];
    snprintf(message, sizeof(message), "%s failed: %s", op, reason);
    return ai_error_map(message);
}

static MValue ai_tensor_matmul_values(const MValue *a, const MValue *b, int m, int n, int k) {
    size_t acount = 0, bcount = 0;
    double *af = ai_double_list(a, &acount);
    double *bf = ai_double_list(b, &bcount);
    MValue values;
    int row, col, idx;
    if (m < 0 || n < 0 || k < 0 || (size_t)(m * k) > acount || (size_t)(k * n) > bcount) {
        free(af);
        free(bf);
        return ai_tensor_failure("matmul", "index out of range");
    }
    ai_list_new(&values, (size_t)(m * n));
    for (row = 0; row < m; ++row) {
        for (col = 0; col < n; ++col) {
            double total = 0.0;
            for (idx = 0; idx < k; ++idx) total += af[row * k + idx] * bf[idx * n + col];
            ai_list_push(&values, mval_f64(total));
        }
    }
    free(af);
    free(bf);
    return ai_tensor_result("matmul", values);
}

static MValue ai_tensor_softmax_values(const MValue *values) {
    size_t count = 0, i;
    double *xs = ai_double_list(values, &count);
    MValue out;
    if (!xs || count == 0) { free(xs); ai_list_new(&out, 0); return ai_tensor_result("softmax", out); }
    {
        double peak = xs[0], total = 0.0;
        for (i = 1; i < count; ++i) if (xs[i] > peak) peak = xs[i];
        for (i = 0; i < count; ++i) { xs[i] = exp(xs[i] - peak); total += xs[i]; }
        if (total == 0.0) total = 1.0;
        for (i = 0; i < count; ++i) xs[i] /= total;
    }
    out = ai_values_from_doubles(xs, count);
    free(xs);
    return ai_tensor_result("softmax", out);
}

static MValue ai_tensor_gelu_values(const MValue *values) {
    size_t count = 0, i;
    double *xs = ai_double_list(values, &count);
    MValue out;
    if (!xs || count == 0) { free(xs); ai_list_new(&out, 0); return ai_tensor_result("gelu", out); }
    for (i = 0; i < count; ++i) {
        double x = xs[i];
        xs[i] = 0.5 * x * (1.0 + tanh(sqrt(2.0 / 3.141592653589793) * (x + 0.044715 * x * x * x)));
    }
    out = ai_values_from_doubles(xs, count);
    free(xs);
    return ai_tensor_result("gelu", out);
}

static MValue ai_tensor_layer_norm_values(const MValue *values, const MValue *gamma,
                                          const MValue *beta, double eps) {
    size_t count = 0, i;
    double *xs = ai_double_list(values, &count);
    MValue out;
    size_t gcount = 0, bcount = 0;
    double *g = ai_double_list(gamma, &gcount);
    double *b = ai_double_list(beta, &bcount);
    if (!xs || count == 0) {
        free(xs);
        free(g);
        free(b);
        ai_list_new(&out, 0);
        return ai_tensor_result("layer_norm", out);
    }
    {
        double mean = 0.0, variance = 0.0, scale;
        for (i = 0; i < count; ++i) mean += xs[i];
        mean /= (double)count;
        for (i = 0; i < count; ++i) variance += (xs[i] - mean) * (xs[i] - mean);
        variance /= (double)count;
        scale = 1.0 / sqrt(variance + eps);
        for (i = 0; i < count; ++i) {
            double gain = i < gcount ? g[i] : 1.0;
            double shift = i < bcount ? b[i] : 0.0;
            xs[i] = (xs[i] - mean) * scale * gain + shift;
        }
    }
    out = ai_values_from_doubles(xs, count);
    free(xs);
    free(g);
    free(b);
    return ai_tensor_result("layer_norm", out);
}

static MValue ai_tensor_syscall(const MValue *args, size_t argc) {
    char *op;
    MValue result;
    if (argc == 0) return ai_error_map("ai.llm_tensor requires an operation");
    op = ai_value_text(&args[0], NULL);
    if (!op) return ai_error_map("AI_TENSOR: out of memory");
    if (strcmp(op, "matmul") == 0) {
        if (argc < 6) {
            free(op);
            return ai_error_map("matmul requires a, b, m, n, k");
        }
        result = ai_tensor_matmul_values(&args[1], &args[2],
                                         (int)ai_int_or(&args[3], 0),
                                         (int)ai_int_or(&args[4], 0),
                                         (int)ai_int_or(&args[5], 0));
    } else if (strcmp(op, "softmax") == 0) {
        if (argc < 2) { free(op); return ai_tensor_failure("softmax", "missing values"); }
        result = ai_tensor_softmax_values(&args[1]);
    } else if (strcmp(op, "gelu") == 0) {
        if (argc < 2) { free(op); return ai_tensor_failure("gelu", "missing values"); }
        result = ai_tensor_gelu_values(&args[1]);
    } else if (strcmp(op, "layer_norm") == 0) {
        if (argc < 2) { free(op); return ai_tensor_failure("layer_norm", "missing values"); }
        result = ai_tensor_layer_norm_values(
            &args[1],
            argc > 2 ? &args[2] : NULL,
            argc > 3 ? &args[3] : NULL,
            argc > 4 ? ai_num_or(&args[4], 1e-5) : 1e-5);
    } else {
        char message[160];
        snprintf(message, sizeof(message), "unknown tensor op: %s", op);
        free(op);
        return ai_error_map(message);
    }
    free(op);
    return result;
}

static MValue ai_tensor_operation(const MValue *item) {
    MValue call[6];
    char *op;
    MValue result;
    int argc = 1;
    if (!item || item->tag != MVAL_MAP) return ai_error_map("operation must be a map");
    {
        const MValue *op_value = ai_map_get(item, "op");
        op = op_value ? ai_value_text(op_value, NULL) : NULL;
    }
    if (!op) return ai_error_map("unknown tensor op: ");
    call[0] = ai_str(op);
    if (strcmp(op, "matmul") == 0) {
        const MValue *a = ai_map_get(item, "a");
        const MValue *b = ai_map_get(item, "b");
        const MValue *m = ai_map_get(item, "m");
        const MValue *n = ai_map_get(item, "n");
        const MValue *k = ai_map_get(item, "k");
        call[1] = a ? *a : mval_none();
        call[2] = b ? *b : mval_none();
        call[3] = m ? *m : mval_i64(0);
        call[4] = n ? *n : mval_i64(0);
        call[5] = k ? *k : mval_i64(0);
        result = ai_tensor_syscall(call, 6);
    } else if (strcmp(op, "softmax") == 0 || strcmp(op, "gelu") == 0) {
        const MValue *values = ai_map_get(item, "values");
        call[1] = values ? *values : mval_none();
        argc = 2;
        result = ai_tensor_syscall(call, (size_t)argc);
    } else if (strcmp(op, "layer_norm") == 0) {
        const MValue *values = ai_map_get(item, "values");
        const MValue *gamma = ai_map_get(item, "gamma");
        const MValue *beta = ai_map_get(item, "beta");
        const MValue *eps = ai_map_get(item, "eps");
        call[1] = values ? *values : mval_none();
        call[2] = gamma ? *gamma : mval_none();
        call[3] = beta ? *beta : mval_none();
        call[4] = eps ? *eps : mval_f64(1e-5);
        result = ai_tensor_syscall(call, 5);
    } else {
        char message[160];
        snprintf(message, sizeof(message), "unknown tensor op: %s", op);
        result = ai_error_map(message);
    }
    mvalue_free(&call[0]);
    free(op);
    return result;
}

static MValue ai_llm_tensor_batch_syscall(const MValue *args, size_t argc) {
    const MValue *operations = argc > 0 && args[0].tag == MVAL_LIST ? &args[0] : NULL;
    MValue results;
    size_t i, count = operations ? operations->as.list.len : 0;
    int errors = 0;
    ai_list_new(&results, count);
    for (i = 0; i < count; ++i) {
        MValue result = ai_tensor_operation(&operations->as.list.items[i]);
        if (ai_map_get(&result, "error")) errors++;
        if (result.tag == MVAL_MAP) ai_map_set(&result, "index", mval_i64((int64_t)i));
        ai_list_push(&results, result);
    }
    {
        MValue summary;
        ai_map_new(&summary, 4);
        ai_map_put(&summary, "operations", mval_i64((int64_t)count));
        ai_map_put_str(&summary, "backend", ai_tensor_backend);
        ai_map_put(&summary, "results", results);
        ai_map_put(&summary, "errors", mval_i64(errors));
        return summary;
    }
}
