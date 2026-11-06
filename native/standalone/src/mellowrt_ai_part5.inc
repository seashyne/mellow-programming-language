/* AI runtime fragment 5: the small feed-forward model registry. */

#define AI_MAX_LAYERS 8
#define AI_MAX_MODELS 16
#define AI_MAX_DIM 128
#define AI_MAX_LOSS 64

enum { AI_ACT_RELU = 0, AI_ACT_SIGMOID = 1, AI_ACT_SOFTMAX = 2, AI_ACT_LINEAR = 3 };

typedef struct {
    int in;
    int out;
    int act;
    double *W;
    double *b;
    double *cache_in;
    double *cache_z;
    double *cache_out;
} AiLayer;

typedef struct {
    int used;
    char name[64];
    char task[16];
    int is_classify;
    int trained;
    int layer_count;
    AiLayer layers[AI_MAX_LAYERS];
    double loss[AI_MAX_LOSS];
    int loss_count;
    int chat_memory;
} AiModel;

static AiModel ai_models[AI_MAX_MODELS];

static int ai_act_from_name(const char *name) {
    if (name && strcmp(name, "sigmoid") == 0) return AI_ACT_SIGMOID;
    if (name && strcmp(name, "softmax") == 0) return AI_ACT_SOFTMAX;
    if (name && strcmp(name, "linear") == 0) return AI_ACT_LINEAR;
    return AI_ACT_RELU;
}

static const char *ai_act_name(int act) {
    if (act == AI_ACT_SIGMOID) return "sigmoid";
    if (act == AI_ACT_SOFTMAX) return "softmax";
    if (act == AI_ACT_LINEAR) return "linear";
    return "relu";
}

static void ai_layer_free(AiLayer *layer) {
    free(layer->W);
    free(layer->b);
    free(layer->cache_in);
    free(layer->cache_z);
    free(layer->cache_out);
    memset(layer, 0, sizeof(*layer));
}

static void ai_model_free(AiModel *model) {
    int i;
    if (!model) return;
    for (i = 0; i < model->layer_count; ++i) ai_layer_free(&model->layers[i]);
    memset(model, 0, sizeof(*model));
}

static AiModel *ai_model_slot(const char *name) {
    int i;
    for (i = 0; i < AI_MAX_MODELS; ++i) {
        if (ai_models[i].used && strcmp(ai_models[i].name, name) == 0) return &ai_models[i];
    }
    return NULL;
}

static AiModel *ai_model_alloc(const char *name) {
    int i;
    AiModel *existing = ai_model_slot(name);
    if (existing) {
        ai_model_free(existing);
        return existing;
    }
    for (i = 0; i < AI_MAX_MODELS; ++i) {
        if (!ai_models[i].used) {
            memset(&ai_models[i], 0, sizeof(ai_models[i]));
            ai_models[i].used = 1;
            snprintf(ai_models[i].name, sizeof(ai_models[i].name), "%s", name);
            return &ai_models[i];
        }
    }
    return NULL;
}

static int ai_layer_init(AiLayer *layer, int in, int out, int act) {
    MRngState rng;
    double stddev;
    int i, j;
    if (in <= 0 || out <= 0 || in > AI_MAX_DIM || out > AI_MAX_DIM) return 0;
    if (in * out > 65536) return 0;
    memset(layer, 0, sizeof(*layer));
    layer->in = in;
    layer->out = out;
    layer->act = act;
    layer->W = (double *)calloc((size_t)in * (size_t)out, sizeof(double));
    layer->b = (double *)calloc((size_t)out, sizeof(double));
    layer->cache_in = (double *)calloc((size_t)in, sizeof(double));
    layer->cache_z = (double *)calloc((size_t)out, sizeof(double));
    layer->cache_out = (double *)calloc((size_t)out, sizeof(double));
    if (!layer->W || !layer->b || !layer->cache_in || !layer->cache_z || !layer->cache_out) {
        ai_layer_free(layer);
        return 0;
    }
    stddev = sqrt(2.0 / (double)in);
    mrng_seed_int(&rng, 42);
    for (i = 0; i < out; ++i)
        for (j = 0; j < in; ++j)
            layer->W[(size_t)i * (size_t)in + (size_t)j] = mrng_gauss(&rng, 0.0, stddev);
    return 1;
}

static void ai_layer_forward(AiLayer *layer, const double *x, double *out) {
    int i, j;
    memcpy(layer->cache_in, x, (size_t)layer->in * sizeof(double));
    for (i = 0; i < layer->out; ++i) {
        double z = layer->b[i];
        for (j = 0; j < layer->in; ++j) z += layer->W[(size_t)i * (size_t)layer->in + (size_t)j] * x[j];
        layer->cache_z[i] = z;
        out[i] = z;
    }
    if (layer->act == AI_ACT_SIGMOID) {
        for (i = 0; i < layer->out; ++i) {
            double clamped = layer->cache_z[i] < -500.0 ? -500.0 : (layer->cache_z[i] > 500.0 ? 500.0 : layer->cache_z[i]);
            out[i] = 1.0 / (1.0 + exp(-clamped));
        }
    } else if (layer->act == AI_ACT_SOFTMAX) {
        double peak = out[0], total = 0.0;
        for (i = 1; i < layer->out; ++i) if (out[i] > peak) peak = out[i];
        for (i = 0; i < layer->out; ++i) { out[i] = exp(out[i] - peak); total += out[i]; }
        for (i = 0; i < layer->out; ++i) out[i] = total ? out[i] / total : 0.0;
    } else if (layer->act == AI_ACT_RELU) {
        for (i = 0; i < layer->out; ++i) out[i] = out[i] > 0.0 ? out[i] : 0.0;
    }
    memcpy(layer->cache_out, out, (size_t)layer->out * sizeof(double));
}

static void ai_layer_backward(AiLayer *layer, const double *grad_out, double lr, double *grad_in) {
    double act_grad[AI_MAX_DIM];
    int i, j;
    for (i = 0; i < layer->out; ++i) {
        double g = grad_out[i];
        if (layer->act == AI_ACT_SIGMOID) g *= layer->cache_out[i] * (1.0 - layer->cache_out[i]);
        else if (layer->act == AI_ACT_RELU) g = layer->cache_z[i] > 0.0 ? g : 0.0;
        act_grad[i] = g;
    }
    for (i = 0; i < layer->out; ++i) {
        layer->b[i] -= lr * act_grad[i];
        for (j = 0; j < layer->in; ++j)
            layer->W[(size_t)i * (size_t)layer->in + (size_t)j] -=
                lr * act_grad[i] * layer->cache_in[j];
    }
    for (j = 0; j < layer->in; ++j) {
        double total = 0.0;
        for (i = 0; i < layer->out; ++i)
            total += layer->W[(size_t)i * (size_t)layer->in + (size_t)j] * act_grad[i];
        grad_in[j] = total;
    }
}

static int ai_model_forward(AiModel *model, const double *input, double *out, int *out_len) {
    double first[AI_MAX_DIM];
    double second[AI_MAX_DIM];
    double *current = first;
    double *next = second;
    int i, len = 0;
    if (!model || model->layer_count <= 0) return 0;
    if (model->layers[0].in > AI_MAX_DIM) return 0;
    memcpy(first, input, (size_t)model->layers[0].in * sizeof(double));
    for (i = 0; i < model->layer_count; ++i) {
        ai_layer_forward(&model->layers[i], current, next);
        len = model->layers[i].out;
        { double *tmp = current; current = next; next = tmp; }
    }
    memcpy(out, current, (size_t)len * sizeof(double));
    if (out_len) *out_len = len;
    return 1;
}

static double ai_model_train_step(AiModel *model, const double *x, double target, int label, double lr) {
    double out[AI_MAX_DIM];
    double grad[AI_MAX_DIM];
    double next_grad[AI_MAX_DIM];
    double *current_grad = grad;
    double *other_grad = next_grad;
    double loss;
    int len = 0, i;
    ai_model_forward(model, x, out, &len);
    if (model->is_classify) {
        int target_index = (int)label;
        if (target_index < 0) target_index = 0;
        if (target_index >= len) target_index = len - 1;
        loss = -log(out[target_index] > 1e-9 ? out[target_index] : 1e-9);
        for (i = 0; i < len; ++i) grad[i] = out[i];
        grad[target_index] -= 1.0;
    } else {
        double diff = out[0] - target;
        loss = 0.5 * diff * diff;
        grad[0] = diff;
        len = 1;
    }
    for (i = model->layer_count - 1; i >= 0; --i) {
        ai_layer_backward(&model->layers[i], current_grad, lr, other_grad);
        { double *tmp = current_grad; current_grad = other_grad; other_grad = tmp; }
    }
    return loss;
}

static int ai_model_read_layer_spec(const MValue *spec, int *in, int *out, int *act) {
    *in = 2; *out = 2; *act = AI_ACT_RELU;
    if (spec && spec->tag == MVAL_MAP) {
        const MValue *a = ai_map_get(spec, "in");
        const MValue *b = ai_map_get(spec, "out");
        const MValue *c = ai_map_get(spec, "activation");
        char *name;
        if (!a) a = ai_map_get(spec, "input");
        if (!b) b = ai_map_get(spec, "output");
        *in = (int)ai_int_or(a, 2);
        *out = (int)ai_int_or(b, 2);
        name = c ? ai_value_text(c, NULL) : NULL;
        *act = ai_act_from_name(name);
        free(name);
        return 1;
    }
    if (spec && (spec->tag == MVAL_LIST || spec->tag == MVAL_NONE) && spec->tag == MVAL_LIST &&
        spec->as.list.len >= 2) {
        char *name = NULL;
        *in = (int)ai_int_or(&spec->as.list.items[0], 2);
        *out = (int)ai_int_or(&spec->as.list.items[1], 2);
        if (spec->as.list.len > 2) name = ai_value_text(&spec->as.list.items[2], NULL);
        *act = ai_act_from_name(name);
        free(name);
        return 1;
    }
    return 1;
}

static MValue ai_model_layers_value(const AiModel *model) {
    MValue layers;
    int i, j, k;
    ai_list_new(&layers, (size_t)model->layer_count);
    for (i = 0; i < model->layer_count; ++i) {
        const AiLayer *layer = &model->layers[i];
        MValue weights, biases, layer_map;
        ai_list_new(&weights, (size_t)layer->out);
        for (j = 0; j < layer->out; ++j) {
            MValue row;
            ai_list_new(&row, (size_t)layer->in);
            for (k = 0; k < layer->in; ++k)
                ai_list_push(&row, mval_f64(layer->W[(size_t)j * (size_t)layer->in + (size_t)k]));
            ai_list_push(&weights, row);
        }
        ai_list_new(&biases, (size_t)layer->out);
        for (j = 0; j < layer->out; ++j) ai_list_push(&biases, mval_f64(layer->b[j]));
        ai_map_new(&layer_map, 3);
        ai_map_put(&layer_map, "W", weights);
        ai_map_put(&layer_map, "b", biases);
        ai_map_put_str(&layer_map, "activation", ai_act_name(layer->act));
        ai_list_push(&layers, layer_map);
    }
    return layers;
}
