/* AI runtime fragment 7: model create/train/predict/save/load syscall bodies. */

typedef struct {
    char **items;
    size_t count;
    size_t cap;
} AiTexts;

static void ai_texts_free(AiTexts *texts) {
    size_t i;
    if (!texts) return;
    for (i = 0; i < texts->count; ++i) free(texts->items[i]);
    free(texts->items);
    texts->items = NULL;
    texts->count = texts->cap = 0;
}

static int ai_texts_push(AiTexts *texts, const MValue *value) {
    char *text = ai_value_text(value, NULL);
    if (!text) return 0;
    if (!*text) { free(text); return 1; }
    if (texts->count == texts->cap) {
        size_t next = texts->cap ? texts->cap * 2 : 8;
        char **grown = (char **)realloc(texts->items, next * sizeof(char *));
        if (!grown) { free(text); return 0; }
        texts->items = grown;
        texts->cap = next;
    }
    texts->items[texts->count++] = text;
    return 1;
}

/* list of texts, or {"samples": [...]}, or one scalar. */
static int ai_texts_from_value(const MValue *value, AiTexts *out) {
    size_t i;
    memset(out, 0, sizeof(*out));
    if (!value || value->tag == MVAL_NONE) return 1;
    if (value->tag == MVAL_MAP) {
        const MValue *samples = ai_map_get(value, "samples");
        if (samples) return ai_texts_from_value(samples, out);
        return 1;
    }
    if (value->tag == MVAL_LIST) {
        for (i = 0; i < value->as.list.len; ++i)
            if (!ai_texts_push(out, &value->as.list.items[i])) return 0;
        return 1;
    }
    return ai_texts_push(out, value);
}

static MValue ai_error_map(const char *message) {
    MValue map;
    ai_map_new(&map, 1);
    ai_map_put_str(&map, "error", message);
    return map;
}

static MValue ai_model_error(const char *name) {
    char message[160];
    snprintf(message, sizeof(message), "Model '%s' not found", name);
    return ai_error_map(message);
}

static void ai_take_name(const MValue *value, const char *fallback, char *out, size_t cap) {
    char *text;
    if (!value || value->tag == MVAL_NONE) { snprintf(out, cap, "%s", fallback); return; }
    text = ai_value_text(value, NULL);
    if (!text) { snprintf(out, cap, "%s", fallback); return; }
    snprintf(out, cap, "%s", text);
    free(text);
}

static MValue ai_model_create_syscall(const MValue *args, size_t argc) {
    char name[64];
    const MValue *raw_layers;
    char task[16] = "classify";
    AiModel *model;
    int count = 0, i;
    ai_take_name(argc > 0 ? &args[0] : NULL, "model", name, sizeof(name));
    raw_layers = argc > 1 ? &args[1] : NULL;
    if (argc > 2) ai_take_name(&args[2], "classify", task, sizeof(task));
    model = ai_model_alloc(name);
    if (!model) return ai_error_map("AI_MODEL: model registry is full");
    ai_copy_bounded(model->task, sizeof(model->task), task);
    model->is_classify = strcmp(task, "classify") == 0;
    if (raw_layers && raw_layers->tag == MVAL_LIST) {
        for (i = 0; i < (int)raw_layers->as.list.len && count < AI_MAX_LAYERS; ++i) {
            int in, out, act;
            ai_model_read_layer_spec(&raw_layers->as.list.items[i], &in, &out, &act);
            if (!ai_layer_init(&model->layers[count], in, out, act)) {
                ai_model_free(model);
                return ai_error_map("AI_MODEL: invalid layer size");
            }
            count++;
        }
    }
    if (count == 0) {
        if (!ai_layer_init(&model->layers[0], 2, 2, AI_ACT_RELU)) {
            ai_model_free(model);
            return ai_error_map("AI_MODEL: invalid layer size");
        }
        count = 1;
    }
    model->layer_count = count;
    {
        MValue result;
        ai_map_new(&result, 4);
        ai_map_put_str(&result, "model", name);
        ai_map_put(&result, "layers", mval_i64(count));
        ai_map_put_str(&result, "task", model->task);
        ai_map_put_str(&result, "status", "created");
        return result;
    }
}

static int ai_input_vector(const MValue *value, double *out, int cap) {
    size_t i, len;
    if (!value) return 0;
    if (value->tag != MVAL_LIST) {
        if (cap < 1 || !ai_number(value, &out[0])) return 0;
        return 1;
    }
    len = value->as.list.len;
    if (len > (size_t)cap) return 0;
    for (i = 0; i < len; ++i)
        if (!ai_number(&value->as.list.items[i], &out[i])) return 0;
    return (int)len;
}

static MValue ai_predict_syscall(const MValue *args, size_t argc) {
    char name[64];
    AiModel *model;
    double input[AI_MAX_DIM];
    double output[AI_MAX_DIM];
    int input_len, output_len = 0, i;
    MValue result, inputs, probabilities;
    if (argc < 2) return ai_error_map("ai.predict requires model_name and input");
    ai_take_name(&args[0], "", name, sizeof(name));
    model = ai_model_slot(name);
    if (!model) return ai_model_error(name);
    if (model->layer_count == 0) return ai_error_map("AI_MODEL: model has no layers");
    input_len = ai_input_vector(&args[1], input, AI_MAX_DIM);
    if (input_len != model->layers[0].in)
        return ai_error_map("AI_MODEL: input size does not match the first layer");
    if (!ai_model_forward(model, input, output, &output_len))
        return ai_error_map("AI_MODEL: forward pass failed");
    ai_map_new(&result, 4);
    ai_map_put_str(&result, "model", name);
    ai_list_new(&inputs, (size_t)input_len);
    for (i = 0; i < input_len; ++i) ai_list_push(&inputs, mval_f64(input[i]));
    ai_map_put(&result, "input", inputs);
    if (model->is_classify) {
        int best = 0;
        for (i = 1; i < output_len; ++i) if (output[i] > output[best]) best = i;
        ai_map_put(&result, "prediction", mval_i64(best));
    } else if (output_len == 1) {
        ai_map_put(&result, "prediction", mval_f64(output[0]));
    } else {
        MValue predicted;
        ai_list_new(&predicted, (size_t)output_len);
        for (i = 0; i < output_len; ++i) ai_list_push(&predicted, mval_f64(output[i]));
        ai_map_put(&result, "prediction", predicted);
    }
    ai_list_new(&probabilities, (size_t)output_len);
    for (i = 0; i < output_len; ++i)
        ai_list_push(&probabilities, mval_f64(round(output[i] * 10000.0) / 10000.0));
    ai_map_put(&result, "probabilities", probabilities);
    return result;
}

static MValue ai_train_syscall(MellowRuntimeContext *ctx, const MValue *args, size_t argc) {
    char name[64];
    AiModel *model;
    const MValue *data, *labels;
    int epochs = 10, i, epoch;
    double lr = 0.01, final_loss = 0.0;
    size_t n, *order;
    MRngState rng;
    (void)ctx;
    if (argc < 3) return ai_error_map("ai.train requires model_name, data, labels");
    ai_take_name(&args[0], "", name, sizeof(name));
    model = ai_model_slot(name);
    if (!model) return ai_model_error(name);
    data = &args[1];
    labels = &args[2];
    if (argc > 3) epochs = (int)ai_int_or(&args[3], 10);
    if (argc > 4) lr = ai_num_or(&args[4], 0.01);
    if (data->tag != MVAL_LIST || labels->tag != MVAL_LIST)
        return ai_error_map("data and labels must be lists");
    if (epochs < 1) epochs = 1;
    n = data->as.list.len < labels->as.list.len ? data->as.list.len : labels->as.list.len;
    if (n == 0) {
        MValue empty;
        ai_map_new(&empty, 5);
        ai_map_put_str(&empty, "model", name);
        ai_map_put(&empty, "epochs", mval_i64(epochs));
        ai_map_put(&empty, "samples", mval_i64(0));
        ai_map_put(&empty, "final_loss", mval_f64(0.0));
        ai_map_put_str(&empty, "status", "trained");
        return empty;
    }
    order = (size_t *)calloc(n, sizeof(size_t));
    if (!order) return ai_error_map("AI_MODEL: out of memory");
    for (i = 0; i < (int)n; ++i) order[i] = (size_t)i;
    mrng_seed_int(&rng, 42);
    for (epoch = 0; epoch < epochs; ++epoch) {
        double total = 0.0;
        for (i = (int)n - 1; i > 0; --i) {
            size_t j = (size_t)mrng_randbelow(&rng, (uint64_t)i + 1);
            size_t tmp = order[i];
            order[i] = order[j];
            order[j] = tmp;
        }
        for (i = 0; i < (int)n; ++i) {
            size_t index = order[i];
            const MValue *label = &labels->as.list.items[index];
            double input[AI_MAX_DIM];
            int len = ai_input_vector(&data->as.list.items[index], input, AI_MAX_DIM);
            double target = ai_num_or(label, 0.0);
            int class_label = (int)ai_int_or(label, 0);
            if (len <= 0) continue;
            total += ai_model_train_step(model, input, target, class_label, lr);
        }
        final_loss = total / (double)n;
        if (model->loss_count < AI_MAX_LOSS) {
            model->loss[model->loss_count++] = ai_round6(final_loss);
        } else {
            memmove(model->loss, model->loss + 1, (AI_MAX_LOSS - 1) * sizeof(double));
            model->loss[AI_MAX_LOSS - 1] = ai_round6(final_loss);
        }
    }
    free(order);
    model->trained = 1;
    {
        MValue result;
        ai_map_new(&result, 6);
        ai_map_put_str(&result, "model", name);
        ai_map_put(&result, "epochs", mval_i64(epochs));
        ai_map_put(&result, "samples", mval_i64((int64_t)n));
        ai_map_put(&result, "final_loss", mval_f64(ai_round6(final_loss)));
        ai_map_put_str(&result, "status", "trained");
        return result;
    }
}
