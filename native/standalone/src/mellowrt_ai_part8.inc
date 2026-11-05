/* AI runtime fragment 8: model checkpoint, runtime, and session syscalls. */

static MValue ai_model_save_syscall(const MValue *args, size_t argc) {
    char name[64], path[640];
    AiModel *model;
    MValue document;
    char *json;
    size_t json_len = 0;
    int i;
    if (argc < 2) return ai_error_map("ai.model_save requires model_name and path");
    ai_take_name(&args[0], "", name, sizeof(name));
    model = ai_model_slot(name);
    if (!model) return ai_model_error(name);
    if (!ai_model_path(&args[1], ".mmodel", path, sizeof(path)))
        return ai_error_map("AI_MODEL: invalid checkpoint path");
    ai_map_new(&document, 5);
    ai_map_put_str(&document, "name", model->name);
    ai_map_put_str(&document, "task", model->task);
    ai_map_put(&document, "trained", mval_bool(model->trained));
    {
        MValue history;
        int start = model->loss_count > 20 ? model->loss_count - 20 : 0;
        ai_list_new(&history, (size_t)(model->loss_count - start));
        for (i = start; i < model->loss_count; ++i) ai_list_push(&history, mval_f64(model->loss[i]));
        ai_map_put(&document, "loss_history", history);
    }
    ai_map_put(&document, "layers", ai_model_layers_value(model));
    json = ai_json_dump(&document, &json_len);
    mvalue_free(&document);
    if (!json) return ai_error_map("AI_MODEL: could not serialise the checkpoint");
    if (!ai_write_file(path, json, json_len)) {
        free(json);
        return ai_error_map("AI_MODEL: could not write the checkpoint");
    }
    free(json);
    {
        MValue result;
        ai_map_new(&result, 2);
        ai_map_put_str(&result, "saved", path);
        ai_map_put_str(&result, "model", name);
        return result;
    }
}

static int ai_load_layer(const MValue *spec, AiLayer *layer) {
    const MValue *weights, *biases, *activation;
    char *act_name;
    int rows, cols, i, j;
    if (!spec || spec->tag != MVAL_MAP) return 0;
    weights = ai_map_get(spec, "W");
    biases = ai_map_get(spec, "b");
    activation = ai_map_get(spec, "activation");
    if (!weights || weights->tag != MVAL_LIST || weights->as.list.len == 0) return 0;
    rows = (int)weights->as.list.len;
    if (weights->as.list.items[0].tag != MVAL_LIST) return 0;
    cols = (int)weights->as.list.items[0].as.list.len;
    act_name = activation ? ai_value_text(activation, NULL) : NULL;
    if (!ai_layer_init(layer, cols, rows, ai_act_from_name(act_name))) {
        free(act_name);
        return 0;
    }
    free(act_name);
    for (i = 0; i < rows; ++i) {
        const MValue *row = &weights->as.list.items[i];
        if (row->tag != MVAL_LIST || (int)row->as.list.len != cols) return 0;
        for (j = 0; j < cols; ++j)
            layer->W[(size_t)i * (size_t)cols + (size_t)j] =
                ai_num_or(&row->as.list.items[j], 0.0);
    }
    if (biases && biases->tag == MVAL_LIST) {
        for (i = 0; i < rows && i < (int)biases->as.list.len; ++i)
            layer->b[i] = ai_num_or(&biases->as.list.items[i], 0.0);
    }
    return 1;
}

static MValue ai_model_load_syscall(const MValue *args, size_t argc) {
    char path[640], name[64];
    char *text;
    size_t len = 0;
    MValue document, *layers;
    const MValue *name_value, *task_value, *trained_value, *history;
    AiModel *model;
    int i, count;
    if (argc < 1) return ai_error_map("ai.model_load requires path");
    if (!ai_model_path(&args[0], ".mmodel", path, sizeof(path)))
        return ai_error_map("AI_MODEL: invalid checkpoint path");
    text = ai_read_file(path, &len);
    if (!text) return ai_error_map("AI_MODEL: checkpoint not found");
    if (!ai_json_parse(text, len, &document)) {
        free(text);
        return ai_error_map("AI_MODEL: checkpoint is not valid JSON");
    }
    free(text);
    if (document.tag != MVAL_MAP) { mvalue_free(&document); return ai_error_map("AI_MODEL: checkpoint is not a map"); }
    name_value = ai_map_get(&document, "name");
    ai_take_name(name_value, "model", name, sizeof(name));
    layers = NULL;
    {
        const MValue *value = ai_map_get(&document, "layers");
        if (value && value->tag == MVAL_LIST) layers = (MValue *)value;
    }
    if (!layers || layers->as.list.len == 0) {
        mvalue_free(&document);
        return ai_error_map("AI_MODEL: checkpoint has no layers");
    }
    model = ai_model_alloc(name);
    if (!model) { mvalue_free(&document); return ai_error_map("AI_MODEL: model registry is full"); }
    count = (int)layers->as.list.len;
    if (count > AI_MAX_LAYERS) count = AI_MAX_LAYERS;
    task_value = ai_map_get(&document, "task");
    ai_take_name(task_value, "classify", model->task, sizeof(model->task));
    model->is_classify = strcmp(model->task, "classify") == 0;
    trained_value = ai_map_get(&document, "trained");
    model->trained = trained_value ? ai_truthy(trained_value) : 0;
    for (i = 0; i < count; ++i) {
        if (!ai_load_layer(&layers->as.list.items[i], &model->layers[i])) {
            ai_model_free(model);
            mvalue_free(&document);
            return ai_error_map("AI_MODEL: checkpoint layer is malformed");
        }
    }
    model->layer_count = count;
    history = ai_map_get(&document, "loss_history");
    if (history && history->tag == MVAL_LIST) {
        for (i = 0; i < (int)history->as.list.len && model->loss_count < AI_MAX_LOSS; ++i)
            model->loss[model->loss_count++] = ai_num_or(&history->as.list.items[i], 0.0);
    }
    mvalue_free(&document);
    {
        MValue result;
        ai_map_new(&result, 3);
        ai_map_put_str(&result, "loaded", name);
        ai_map_put(&result, "layers", mval_i64(count));
        ai_map_put_str(&result, "task", model->task);
        return result;
    }
}

static MValue ai_model_info_syscall(const MValue *args, size_t argc) {
    char name[64];
    AiModel *model;
    MValue result, shapes;
    int i;
    if (argc < 1) return ai_error_map("ai.model_info requires model_name");
    ai_take_name(&args[0], "", name, sizeof(name));
    model = ai_model_slot(name);
    if (!model) return ai_model_error(name);
    ai_map_new(&result, 7);
    ai_map_put_str(&result, "name", model->name);
    ai_map_put_str(&result, "task", model->task);
    ai_map_put(&result, "trained", mval_bool(model->trained));
    ai_map_put(&result, "layers", mval_i64(model->layer_count));
    ai_list_new(&shapes, (size_t)model->layer_count);
    for (i = 0; i < model->layer_count; ++i) {
        MValue shape;
        ai_map_new(&shape, 2);
        ai_map_put(&shape, "out", mval_i64(model->layers[i].out));
        ai_map_put(&shape, "in", mval_i64(model->layers[i].in));
        ai_list_push(&shapes, shape);
    }
    ai_map_put(&result, "layer_shapes", shapes);
    ai_map_put(&result, "loss_points", mval_i64(model->loss_count));
    ai_map_put(&result, "chat_memory", mval_i64(model->chat_memory));
    return result;
}

static MValue ai_models_list_syscall(void) {
    MValue list;
    int i;
    ai_list_new(&list, AI_MAX_MODELS);
    for (i = 0; i < AI_MAX_MODELS; ++i)
        if (ai_models[i].used) ai_list_push(&list, ai_str(ai_models[i].name));
    return list;
}

static MValue ai_loss_history_syscall(const MValue *args, size_t argc) {
    char name[64];
    AiModel *model;
    MValue list;
    int i;
    ai_list_new(&list, AI_MAX_LOSS);
    if (argc < 1) return list;
    ai_take_name(&args[0], "", name, sizeof(name));
    model = ai_model_slot(name);
    if (!model) return list;
    for (i = 0; i < model->loss_count; ++i) ai_list_push(&list, mval_f64(model->loss[i]));
    return list;
}

static MValue ai_runtime_boot_syscall(MellowRuntimeContext *ctx, const MValue *args, size_t argc) {
    MValue result, features;
    static const char *const names[] = {
        "chat", "train", "predict", "embed", "sessions", "retrieval", "prompt_template"
    };
    size_t i;
    ai_runtime.booted = 1;
    ai_runtime.boot_count++;
    ai_runtime.last_boot_at = (long long)time(NULL);
    ai_map_new(&result, 5);
    ai_map_put_str(&result, "status", "ready");
    ai_map_put(&result, "booted", mval_bool(1));
    ai_map_put(&result, "boot_count", mval_i64(ai_runtime.boot_count));
    ai_list_new(&features, 7);
    for (i = 0; i < 7; ++i) ai_list_push(&features, ai_str(names[i]));
    ai_map_put(&result, "features", features);
    if (argc > 0 && args[0].tag == MVAL_MAP) ai_map_put(&result, "config", clone_value(ctx, &args[0]));
    else { MValue empty; ai_map_new(&empty, 0); ai_map_put(&result, "config", empty); }
    return result;
}

static MValue ai_runtime_info_syscall(void) {
    MValue result, features;
    static const char *const names[] = {
        "offline", "sandboxed", "chat", "ml", "embedding", "retrieval"
    };
    size_t i;
    int models = 0, sessions = 0;
    for (i = 0; i < AI_MAX_MODELS; ++i) if (ai_models[i].used) models++;
    for (i = 0; i < AI_MAX_SESSIONS; ++i) if (ai_sessions[i].used) sessions++;
    ai_map_new(&result, 6);
    ai_map_put(&result, "booted", mval_bool(ai_runtime.booted));
    ai_map_put(&result, "boot_count", mval_i64(ai_runtime.boot_count));
    if (ai_runtime.last_boot_at) ai_map_put(&result, "last_boot_at", mval_i64(ai_runtime.last_boot_at));
    else ai_map_put(&result, "last_boot_at", mval_none());
    ai_map_put(&result, "models", mval_i64(models));
    ai_map_put(&result, "sessions", mval_i64(sessions));
    ai_list_new(&features, 6);
    for (i = 0; i < 6; ++i) ai_list_push(&features, ai_str(names[i]));
    ai_map_put(&result, "features", features);
    return result;
}

static MValue ai_session_open_syscall(const MValue *args, size_t argc) {
    char name[64], id[96];
    const char *system = "You are a helpful offline assistant.";
    AiSession *session = NULL;
    int i;
    ai_take_name(argc > 0 ? &args[0] : NULL, "default", name, sizeof(name));
    for (i = 0; i < AI_MAX_SESSIONS; ++i) if (!ai_sessions[i].used) { session = &ai_sessions[i]; break; }
    if (!session) return ai_error_map("AI_SESSION: session registry is full");
    memset(session, 0, sizeof(*session));
    session->used = 1;
    ai_session_id(name, id, sizeof(id));
    ai_session_total++;
    ai_copy_bounded(session->id, sizeof(session->id), id);
    ai_copy_bounded(session->name, sizeof(session->name), name);
    ai_copy_bounded(session->system, sizeof(session->system), system);
    if (argc > 1 && args[1].tag != MVAL_NONE) {
        char *text = ai_value_text(&args[1], NULL);
        if (text) { ai_copy_bounded(session->system, sizeof(session->system), text); free(text); }
    }
    session->created_at = (long long)time(NULL);
    {
        MValue result;
        ai_map_new(&result, 4);
        ai_map_put_str(&result, "session", session->id);
        ai_map_put_str(&result, "name", session->name);
        ai_map_put_str(&result, "system", session->system);
        ai_map_put_str(&result, "status", "opened");
        return result;
    }
}
