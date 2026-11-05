/* AI runtime fragment 16: LLM evaluation and JSON checkpoints. */

static MValue ai_llm_eval_syscall(const MValue *args, size_t argc) {
    char name[64];
    AiLlm *llm;
    AiTexts texts;
    double loss;
    int64_t tokens = 0;
    size_t t;
    MValue result;
    if (argc < 2) return ai_error_map("ai.llm_eval requires model name and eval texts");
    ai_take_name(&args[0], "", name, sizeof(name));
    llm = ai_llm_slot(name);
    if (!llm) return ai_llm_missing(name);
    if (!ai_texts_from_value(&args[1], &texts)) return ai_error_map("AI_LLM: out of memory");
    loss = ai_llm_loss(llm, &texts);
    for (t = 0; t < texts.count; ++t) tokens += (int64_t)ai_utf8_count(texts.items[t], strlen(texts.items[t]));
    ai_map_new(&result, 5);
    ai_map_put(&result, "loss", mval_f64(ai_round6(loss)));
    ai_map_put(&result, "perplexity", mval_f64(ai_round6(exp(loss < 20.0 ? loss : 20.0))));
    ai_map_put(&result, "samples", mval_i64((int64_t)texts.count));
    ai_map_put(&result, "tokens", mval_i64(tokens));
    ai_map_put_str(&result, "model", name);
    ai_texts_free(&texts);
    return result;
}

static void ai_trans_set(AiTransition *trans, int32_t cp, int count) {
    size_t i;
    for (i = 0; i < trans->count; ++i)
        if (trans->items[i].cp == cp) { trans->items[i].count = count; return; }
    if (trans->count == trans->cap) {
        size_t next = trans->cap ? trans->cap * 2 : 4;
        AiCharCount *grown = (AiCharCount *)realloc(trans->items, next * sizeof(AiCharCount));
        if (!grown) return;
        trans->items = grown;
        trans->cap = next;
    }
    trans->items[trans->count].cp = cp;
    trans->items[trans->count].count = count;
    trans->count++;
}

static void ai_llm_context_text(const int32_t *ctx, int ctx_len, char *out, size_t cap) {
    size_t used = 0;
    int i;
    for (i = 0; i < ctx_len; ++i) {
        char encoded[4];
        int n = ai_utf8_encode(ctx[i], encoded);
        if (used + (size_t)n + 1 > cap) break;
        memcpy(out + used, encoded, (size_t)n);
        used += (size_t)n;
    }
    out[used] = '\0';
}

static MValue ai_llm_save_syscall(const MValue *args, size_t argc) {
    char name[64], path[640];
    AiLlm *llm;
    MValue document, vocab, transitions, history;
    size_t i, j;
    char *json;
    size_t json_len = 0;
    int written;
    if (argc < 2) return ai_error_map("ai.llm_save requires model name and path");
    ai_take_name(&args[0], "", name, sizeof(name));
    llm = ai_llm_slot(name);
    if (!llm) return ai_llm_missing(name);
    if (!ai_model_path(&args[1], ".mllm", path, sizeof(path)))
        return ai_error_map("AI_LLM: invalid checkpoint path");
    ai_map_new(&document, 9);
    ai_map_put_str(&document, "kind", "tiny-causal-char-lm");
    ai_map_put_str(&document, "name", llm->name);
    ai_map_put(&document, "order", mval_i64(llm->order));
    ai_map_put(&document, "seed", mval_i64(llm->seed));
    ai_list_new(&vocab, llm->vocab_count);
    for (i = 0; i < llm->vocab_count; ++i) {
        char encoded[4];
        int n = ai_utf8_encode(llm->vocab[i], encoded);
        ai_list_push(&vocab, ai_strn(encoded, (size_t)n));
    }
    ai_map_put(&document, "vocab", vocab);
    ai_map_new(&transitions, llm->trans_count);
    for (i = 0; i < llm->trans_count; ++i) {
        AiTransition *bucket = &llm->trans[i];
        MValue counts;
        char context[AI_MAX_ORDER * 4 + 1];
        ai_llm_context_text(bucket->ctx, bucket->ctx_len, context, sizeof(context));
        ai_map_new(&counts, bucket->count);
        for (j = 0; j < bucket->count; ++j) {
            char encoded[4];
            int n = ai_utf8_encode(bucket->items[j].cp, encoded);
            char key[5];
            memcpy(key, encoded, (size_t)n);
            key[n] = '\0';
            ai_map_put(&counts, key, mval_i64(bucket->items[j].count));
        }
        ai_map_put(&transitions, context, counts);
    }
    ai_map_put(&document, "transitions", transitions);
    ai_map_put(&document, "trained_tokens", mval_i64(llm->trained_tokens));
    ai_list_new(&history, (size_t)llm->loss_count);
    for (i = 0; i < (size_t)llm->loss_count; ++i) ai_list_push(&history, mval_f64(llm->loss[i]));
    ai_map_put(&document, "loss_history", history);
    ai_map_put(&document, "created_at", mval_i64((int64_t)llm->created_at));
    json = ai_json_dump(&document, &json_len);
    mvalue_free(&document);
    written = json && ai_write_file(path, json, json_len);
    free(json);
    if (!written) return ai_error_map("AI_LLM: failed to write checkpoint");
    {
        MValue result;
        ai_map_new(&result, 2);
        ai_map_put_str(&result, "saved", path);
        ai_map_put_str(&result, "model", name);
        return result;
    }
}

static void ai_llm_restore(AiLlm *llm, const MValue *document) {
    const MValue *vocab = ai_map_get(document, "vocab");
    const MValue *transitions = ai_map_get(document, "transitions");
    const MValue *history = ai_map_get(document, "loss_history");
    size_t i, j;
    if (vocab && vocab->tag == MVAL_LIST) {
        for (i = 0; i < vocab->as.list.len; ++i) {
            const MValue *entry = &vocab->as.list.items[i];
            size_t pos = 0;
            int32_t cp;
            if (entry->tag != MVAL_STR || !entry->as.str.ptr) continue;
            if (ai_utf8_decode(entry->as.str.ptr, entry->as.str.len, &pos, &cp))
                ai_vocab_add(llm, cp);
        }
    }
    if (transitions && transitions->tag == MVAL_MAP) {
        for (i = 0; i < transitions->as.map.len; ++i) {
            const MValue *key = &transitions->as.map.keys[i];
            const MValue *bucket_value = &transitions->as.map.values[i];
            int32_t ctx[AI_MAX_ORDER];
            int ctx_len = 0;
            AiTransition *bucket;
            size_t pos = 0;
            int32_t cp;
            if (key->tag != MVAL_STR || bucket_value->tag != MVAL_MAP) continue;
            while (ctx_len < AI_MAX_ORDER && pos < key->as.str.len &&
                   ai_utf8_decode(key->as.str.ptr, key->as.str.len, &pos, &cp))
                ctx[ctx_len++] = cp;
            bucket = ai_trans_find_or_add(llm, ctx, ctx_len);
            if (!bucket) continue;
            for (j = 0; j < bucket_value->as.map.len; ++j) {
                const MValue *char_key = &bucket_value->as.map.keys[j];
                size_t at = 0;
                int32_t target;
                if (char_key->tag != MVAL_STR || !char_key->as.str.ptr) continue;
                if (!ai_utf8_decode(char_key->as.str.ptr, char_key->as.str.len, &at, &target)) continue;
                ai_trans_set(bucket, target, (int)ai_int_or(&bucket_value->as.map.values[j], 1));
            }
        }
    }
    if (history && history->tag == MVAL_LIST) {
        for (i = 0; i < history->as.list.len && llm->loss_count < AI_LLM_LOSS; ++i)
            llm->loss[llm->loss_count++] = ai_num_or(&history->as.list.items[i], 0.0);
    }
}

static MValue ai_llm_load_syscall(const MValue *args, size_t argc) {
    char path[640], name[64];
    AiLlm *llm;
    char *data;
    size_t data_len = 0;
    MValue document;
    const MValue *field;
    if (argc < 1) return ai_error_map("ai.llm_load requires path");
    if (!ai_model_path(&args[0], ".mllm", path, sizeof(path)))
        return ai_error_map("AI_LLM: invalid checkpoint path");
    data = ai_read_file(path, &data_len);
    if (!data) {
        char message[700];
        snprintf(message, sizeof(message), "LLM file not found: %s", path);
        return ai_error_map(message);
    }
    if (!ai_json_parse(data, data_len, &document)) {
        free(data);
        return ai_error_map("AI_LLM: invalid checkpoint");
    }
    free(data);
    field = ai_map_get(&document, "name");
    if (field) ai_take_name(field, "llm", name, sizeof(name));
    else snprintf(name, sizeof(name), "llm");
    llm = ai_llm_alloc(name);
    if (!llm) { mvalue_free(&document); return ai_error_map("AI_LLM: model registry is full"); }
    llm->order = (int)ai_int_or(ai_map_get(&document, "order"), 3);
    if (llm->order < 1) llm->order = 1;
    if (llm->order > AI_MAX_ORDER) llm->order = AI_MAX_ORDER;
    llm->seed = ai_int_or(ai_map_get(&document, "seed"), 42);
    llm->created_at = (long long)ai_int_or(ai_map_get(&document, "created_at"), (int64_t)time(NULL));
    llm->trained_tokens = ai_int_or(ai_map_get(&document, "trained_tokens"), 0);
    ai_llm_restore(llm, &document);
    mvalue_free(&document);
    {
        MValue result;
        ai_map_new(&result, 3);
        ai_map_put_str(&result, "loaded", name);
        ai_map_put_str(&result, "kind", "tiny-causal-char-lm");
        ai_map_put(&result, "tokens", mval_i64(llm->trained_tokens));
        return result;
    }
}
