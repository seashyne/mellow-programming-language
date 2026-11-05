/* AI runtime fragment 15: LLM metadata and dataset chunking. */

static MValue ai_llm_missing(const char *name) {
    char message[160];
    snprintf(message, sizeof(message), "LLM model '%s' not found", name);
    return ai_error_map(message);
}

static MValue ai_llm_info_value(const AiLlm *llm) {
    MValue info, capabilities;
    ai_map_new(&info, 10);
    ai_map_put_str(&info, "name", llm->name);
    ai_map_put_str(&info, "kind", "tiny-causal-char-lm");
    ai_map_put(&info, "order", mval_i64(llm->order));
    ai_map_put(&info, "vocab", mval_i64((int64_t)llm->vocab_count));
    ai_map_put(&info, "tokens", mval_i64(llm->trained_tokens));
    ai_map_put(&info, "loss_points", mval_i64(llm->loss_count));
    ai_map_put(&info, "loss", llm->loss_count > 0 ? mval_f64(llm->loss[llm->loss_count - 1]) : mval_none());
    ai_map_put(&info, "created_at", mval_i64((int64_t)llm->created_at));
    ai_map_put(&info, "trained", mval_bool(llm->trained_tokens > 0));
    ai_list_new(&capabilities, 5);
    ai_list_push(&capabilities, ai_str("train"));
    ai_list_push(&capabilities, ai_str("generate"));
    ai_list_push(&capabilities, ai_str("evaluate"));
    ai_list_push(&capabilities, ai_str("checkpoint"));
    ai_list_push(&capabilities, ai_str("chat-format"));
    ai_map_put(&info, "capabilities", capabilities);
    return info;
}

static MValue ai_llm_info_syscall(const MValue *args, size_t argc) {
    char name[64];
    if (argc == 0) {
        int order[AI_MAX_LLM], count = 0, i, j;
        MValue result, models;
        for (i = 0; i < AI_MAX_LLM; ++i)
            if (ai_llms[i].used) order[count++] = i;
        for (i = 1; i < count; ++i) {
            int key = order[i];
            j = i - 1;
            while (j >= 0 && ai_llms[order[j]].seq > ai_llms[key].seq) {
                order[j + 1] = order[j];
                --j;
            }
            order[j + 1] = key;
        }
        ai_list_new(&models, (size_t)count);
        for (i = 0; i < count; ++i) ai_list_push(&models, ai_str(ai_llms[order[i]].name));
        ai_map_new(&result, 2);
        ai_map_put(&result, "models", models);
        ai_map_put(&result, "count", mval_i64((int64_t)count));
        return result;
    }
    ai_take_name(&args[0], "", name, sizeof(name));
    {
        AiLlm *llm = ai_llm_slot(name);
        if (!llm) return ai_llm_missing(name);
        return ai_llm_info_value(llm);
    }
}

static void ai_dataset_options(const MValue *options, int *chunk, int *stride, int *min_chars) {
    const MValue *chunk_value = ai_map_get(options, "chunk_chars");
    if (!chunk_value) chunk_value = ai_map_get(options, "max_chars");
    *chunk = (int)ai_int_or(chunk_value, 512);
    if (*chunk < 1) *chunk = 1;
    *stride = (int)ai_int_or(ai_map_get(options, "stride"), *chunk);
    if (*stride < 1) *stride = 1;
    if (*stride > *chunk) *stride = *chunk;
    *min_chars = (int)ai_int_or(ai_map_get(options, "min_chars"), 1);
    if (*min_chars < 1) *min_chars = 1;
}

static void ai_dataset_push(MValue *samples, const char *text, size_t len,
                            size_t start_char, size_t count) {
    size_t start = ai_utf8_offset(text, len, start_char);
    size_t end = ai_utf8_offset(text, len, start_char + count);
    ai_json_append(samples, ai_strn(text + start, end - start));
}

static MValue ai_llm_dataset_syscall(const MValue *args, size_t argc) {
    AiTexts texts;
    MValue result, samples;
    const MValue *options;
    int chunk = 512, stride = 512, min_chars = 1;
    int64_t total_chars = 0;
    size_t t;
    if (argc == 0) {
        ai_list_new(&samples, 0);
        ai_map_new(&result, 3);
        ai_map_put(&result, "samples", samples);
        ai_map_put(&result, "count", mval_i64(0));
        ai_map_put(&result, "chars", mval_i64(0));
        return result;
    }
    if (!ai_texts_from_value(&args[0], &texts)) return ai_error_map("AI_LLM: out of memory");
    options = argc > 1 && args[1].tag == MVAL_MAP ? &args[1] : NULL;
    if (options) ai_dataset_options(options, &chunk, &stride, &min_chars);
    ai_list_new(&samples, 0);
    for (t = 0; t < texts.count; ++t) {
        const char *text = texts.items[t];
        size_t len = strlen(text);
        size_t chars = ai_utf8_count(text, len);
        total_chars += (int64_t)chars;
        if (chars <= (size_t)chunk) {
            if (chars >= (size_t)min_chars) ai_json_append(&samples, ai_strn(text, len));
            continue;
        }
        {
            size_t start = 0;
            while (start < chars) {
                size_t take = chars - start < (size_t)chunk ? chars - start : (size_t)chunk;
                if (take >= (size_t)min_chars) ai_dataset_push(&samples, text, len, start, take);
                start += (size_t)stride;
            }
        }
    }
    ai_texts_free(&texts);
    ai_map_new(&result, 5);
    ai_map_put(&result, "samples", samples);
    ai_map_put(&result, "count", mval_i64((int64_t)samples.as.list.len));
    ai_map_put(&result, "chars", mval_i64(total_chars));
    ai_map_put(&result, "chunk_chars", mval_i64(chunk));
    ai_map_put(&result, "stride", mval_i64(stride));
    return result;
}
