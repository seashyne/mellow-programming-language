/* AI runtime fragment 14: LLM create, train, generate, and tokenize. */

typedef struct {
    int32_t cp;
    int count;
    int order;
} AiCandidate;

static int ai_llm_order_from(const MValue *config) {
    const MValue *order = config ? ai_map_get(config, "order") : NULL;
    const MValue *context = config ? ai_map_get(config, "context") : NULL;
    int value = (int)ai_int_or(order, (int)ai_int_or(context, 3));
    if (value < 1) value = 1;
    if (value > AI_MAX_ORDER) value = AI_MAX_ORDER;
    return value;
}

static MValue ai_llm_create_syscall(const MValue *args, size_t argc) {
    char name[64];
    const MValue *config = argc > 1 && args[1].tag == MVAL_MAP ? &args[1] : NULL;
    AiLlm *llm;
    MValue result;
    ai_take_name(argc > 0 ? &args[0] : NULL, "llm", name, sizeof(name));
    llm = ai_llm_alloc(name);
    if (!llm) return ai_error_map("AI_LLM: model registry is full");
    llm->order = ai_llm_order_from(config);
    llm->seed = ai_int_or(config ? ai_map_get(config, "seed") : NULL, 42);
    llm->created_at = (long long)time(NULL);
    ai_map_new(&result, 4);
    ai_map_put_str(&result, "model", name);
    ai_map_put_str(&result, "kind", "tiny-causal-char-lm");
    ai_map_put(&result, "order", mval_i64(llm->order));
    ai_map_put_str(&result, "status", "created");
    return result;
}

static MValue ai_llm_train_syscall(const MValue *args, size_t argc) {
    char name[64];
    AiTexts texts;
    AiLlm *llm;
    const MValue *options;
    int epochs = 1;
    double loss, perplexity;
    MValue result;
    if (argc < 2) return ai_error_map("ai.llm_train requires model name and text corpus");
    ai_take_name(&args[0], "", name, sizeof(name));
    if (!ai_texts_from_value(&args[1], &texts)) return ai_error_map("AI_LLM: out of memory");
    options = argc > 2 && args[2].tag == MVAL_MAP ? &args[2] : NULL;
    if (options) epochs = (int)ai_int_or(ai_map_get(options, "epochs"), 1);
    llm = ai_llm_slot(name);
    if (!llm) {
        llm = ai_llm_alloc(name);
        if (llm) { llm->order = 3; llm->seed = 42; llm->created_at = (long long)time(NULL); }
    }
    if (!llm) { ai_texts_free(&texts); return ai_error_map("AI_LLM: model registry is full"); }
    loss = ai_llm_train(llm, &texts, epochs);
    perplexity = exp(loss < 20.0 ? loss : 20.0);
    ai_map_new(&result, 8);
    ai_map_put_str(&result, "model", name);
    ai_map_put(&result, "epochs", mval_i64(epochs > 0 ? epochs : 1));
    ai_map_put(&result, "samples", mval_i64((int64_t)texts.count));
    ai_map_put(&result, "tokens", mval_i64(llm->trained_tokens));
    ai_map_put(&result, "vocab", mval_i64((int64_t)llm->vocab_count));
    ai_map_put(&result, "loss", mval_f64(ai_round6(loss)));
    ai_map_put(&result, "perplexity", mval_f64(ai_round6(perplexity)));
    ai_map_put_str(&result, "status", "trained");
    ai_texts_free(&texts);
    return result;
}

static int ai_llm_context_from(const char *text, size_t len, int order, int32_t *ctx) {
    int32_t ring[AI_MAX_ORDER];
    int hist_len = 0;
    size_t pos = 0;
    int32_t cp;
    while (pos < len && ai_utf8_decode(text, len, &pos, &cp))
        ai_history_push(ring, &hist_len, order, cp);
    if (hist_len > 0) memcpy(ctx, ring + (hist_len > order ? hist_len - order : 0), (size_t)hist_len * sizeof(int32_t));
    return hist_len;
}

static double ai_candidate_weight(const AiCandidate *candidate, double temperature) {
    double count = candidate->count > 0 ? (double)candidate->count : 0.001;
    return pow(count, 1.0 / temperature);
}

static char *ai_llm_generate_text(
    AiLlm *llm,
    const char *prompt,
    int max_tokens,
    double temperature,
    int64_t seed,
    int top_k,
    const AiTexts *stop
) {
    MRngState rng;
    size_t cap = strlen(prompt) + 16;
    size_t used = strlen(prompt);
    char *out;
    int step;
    if (llm->vocab_count == 0) {
        char *copy = (char *)calloc(strlen(prompt) + 1, 1);
        if (copy) memcpy(copy, prompt, strlen(prompt));
        return copy;
    }
    if (max_tokens < 0) max_tokens = 0;
    cap += (size_t)max_tokens * 4u;
    out = (char *)calloc(cap, 1);
    if (!out) return NULL;
    memcpy(out, prompt, used);
    mrng_seed_int(&rng, seed);
    if (temperature < 0.001) temperature = 0.001;
    for (step = 0; step < max_tokens; ++step) {
        int32_t ctx[AI_MAX_ORDER];
        int ctx_len = ai_llm_context_from(out, used, llm->order, ctx);
        AiTransition *bucket = llm->trans_count ? ai_trans_find(llm, ctx, ctx_len) : NULL;
        AiCandidate *candidates;
        size_t count = 0, i, total_count;
        double total = 0.0, upto = 0.0, pick;
        char encoded[4];
        int encoded_len, chosen = -1;
        total_count = bucket ? bucket->count : llm->vocab_count;
        candidates = (AiCandidate *)calloc(total_count ? total_count : 1, sizeof(AiCandidate));
        if (!candidates) { free(out); return NULL; }
        if (bucket) {
            for (i = 0; i < bucket->count; ++i) {
                candidates[i].cp = bucket->items[i].cp;
                candidates[i].count = bucket->items[i].count;
                candidates[i].order = (int)i;
            }
            count = bucket->count;
        } else {
            for (i = 0; i < llm->vocab_count; ++i) {
                candidates[i].cp = llm->vocab[i];
                candidates[i].count = 1;
                candidates[i].order = (int)i;
            }
            count = llm->vocab_count;
        }
        if (top_k > 0 && (size_t)top_k < count) {
            for (i = 1; i < count; ++i) {
                AiCandidate key = candidates[i];
                size_t j = i;
                while (j > 0 && (candidates[j - 1].count < key.count ||
                       (candidates[j - 1].count == key.count && candidates[j - 1].order > key.order))) {
                    candidates[j] = candidates[j - 1];
                    --j;
                }
                candidates[j] = key;
            }
            count = (size_t)top_k;
        }
        for (i = 1; i < count; ++i) {
            AiCandidate key = candidates[i];
            size_t j = i;
            while (j > 0 && candidates[j - 1].cp > key.cp) {
                candidates[j] = candidates[j - 1];
                --j;
            }
            candidates[j] = key;
        }
        for (i = 0; i < count; ++i) total += ai_candidate_weight(&candidates[i], temperature);
        pick = mrng_random(&rng) * total;
        for (i = 0; i < count; ++i) {
            upto += ai_candidate_weight(&candidates[i], temperature);
            if (upto >= pick) { chosen = (int)i; break; }
        }
        if (chosen < 0 && count > 0) chosen = (int)count - 1;
        if (chosen < 0) { free(candidates); break; }
        encoded_len = ai_utf8_encode(candidates[chosen].cp, encoded);
        free(candidates);
        if (used + (size_t)encoded_len + 1 >= cap) {
            size_t next = (used + (size_t)encoded_len + 1) * 2;
            char *grown = (char *)realloc(out, next);
            if (!grown) { free(out); return NULL; }
            out = grown;
            cap = next;
        }
        memcpy(out + used, encoded, (size_t)encoded_len);
        used += (size_t)encoded_len;
        out[used] = '\0';
        if (stop && stop->count) {
            for (i = 0; i < stop->count; ++i) {
                size_t n = strlen(stop->items[i]);
                if (n <= used && memcmp(out + used - n, stop->items[i], n) == 0) return out;
            }
        }
    }
    return out;
}

static MValue ai_llm_generate_syscall(const MValue *args, size_t argc, int include_default) {
    char name[64];
    AiLlm *llm;
    const MValue *options;
    char *prompt, *generated, *completion;
    size_t prompt_len = 0, prompt_chars, generated_chars;
    int max_tokens = 64, top_k = 0, include_prompt = include_default;
    int64_t seed;
    double temperature = 1.0;
    AiTexts stop;
    MValue result, stop_value;
    if (argc < 1) return ai_error_map("ai.llm_generate requires model name");
    ai_take_name(&args[0], "", name, sizeof(name));
    llm = ai_llm_slot(name);
    if (!llm) return ai_model_error(name);
    prompt = argc > 1 ? ai_value_text(&args[1], &prompt_len) : (char *)calloc(1, 1);
    if (!prompt) return ai_error_map("AI_LLM: out of memory");
    options = argc > 2 && args[2].tag == MVAL_MAP ? &args[2] : NULL;
    seed = llm->seed;
    memset(&stop, 0, sizeof(stop));
    if (options) {
        const MValue *tokens = ai_map_get(options, "max_tokens");
        if (!tokens) tokens = ai_map_get(options, "tokens");
        max_tokens = (int)ai_int_or(tokens, 64);
        temperature = ai_num_or(ai_map_get(options, "temperature"), 1.0);
        top_k = (int)ai_int_or(ai_map_get(options, "top_k"), 0);
        {
            const MValue *seed_value = ai_map_get(options, "seed");
            if (seed_value) seed = ai_int_or(seed_value, seed);
        }
        {
            const MValue *include = ai_map_get(options, "include_prompt");
            include_prompt = include ? ai_truthy(include) : include_default;
        }
        {
            const MValue *stops = ai_map_get(options, "stop");
            if (stops && stops->tag == MVAL_LIST) ai_texts_from_value(stops, &stop);
        }
    }
    generated = ai_llm_generate_text(llm, prompt, max_tokens, temperature, seed, top_k, &stop);
    ai_texts_free(&stop);
    if (!generated) { free(prompt); return ai_error_map("AI_LLM: generation failed"); }
    prompt_chars = ai_utf8_count(prompt, prompt_len);
    generated_chars = ai_utf8_count(generated, strlen(generated));
    if (strncmp(generated, prompt, prompt_len) == 0) {
        size_t offset = ai_utf8_offset(generated, strlen(generated), prompt_chars);
        completion = (char *)calloc(strlen(generated + offset) + 1, 1);
        if (completion) memcpy(completion, generated + offset, strlen(generated + offset));
    } else {
        completion = (char *)calloc(strlen(generated) + 1, 1);
        if (completion) memcpy(completion, generated, strlen(generated));
    }
    if (!completion) { free(generated); free(prompt); return ai_error_map("AI_LLM: out of memory"); }
    ai_map_new(&result, 5);
    ai_map_put_str(&result, "model", name);
    ai_map_put(&result, "prompt", ai_strn(prompt, prompt_len));
    ai_map_put_str(&result, "text", include_prompt ? generated : completion);
    ai_map_put_str(&result, "completion", completion);
    ai_map_put(&result, "generated_tokens",
                mval_i64((int64_t)(generated_chars >= prompt_chars ? generated_chars - prompt_chars : 0)));
    ai_map_new(&stop_value, 4);
    ai_map_put(&stop_value, "max_tokens", mval_i64(max_tokens));
    ai_map_put(&stop_value, "temperature", mval_f64(temperature));
    ai_map_put(&stop_value, "top_k", mval_i64(top_k));
    ai_map_put(&stop_value, "include_prompt", mval_bool(include_prompt));
    ai_map_put(&result, "options", stop_value);
    free(generated);
    free(completion);
    free(prompt);
    return result;
}

static MValue ai_llm_tokenize_syscall(const MValue *args, size_t argc) {
    char *text = argc > 0 ? ai_value_text(&args[0], NULL) : (char *)calloc(1, 1);
    MValue result, tokens;
    size_t pos = 0, len, count = 0;
    int32_t cp;
    if (!text) return ai_error_map("AI_LLM: out of memory");
    len = strlen(text);
    while (pos < len && ai_utf8_decode(text, len, &pos, &cp)) count++;
    ai_list_new(&tokens, count);
    pos = 0;
    while (pos < len && ai_utf8_decode(text, len, &pos, &cp)) ai_list_push(&tokens, mval_i64(cp));
    ai_map_new(&result, 3);
    ai_map_put(&result, "tokens", tokens);
    ai_map_put(&result, "count", mval_i64((int64_t)count));
    ai_map_put_str(&result, "tokenizer", "unicode-char");
    free(text);
    return result;
}
