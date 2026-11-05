/* AI runtime fragment 12: offline completions and provider embeddings. */

/* Join the first max_words whitespace-separated words with single spaces. */
static char *ai_join_words(const char *text, size_t len, int max_words) {
    char *out = (char *)calloc(len + 1, 1);
    size_t pos = 0, used = 0;
    int words = 0;
    if (!out) return NULL;
    while (pos < len && words < max_words) {
        size_t start;
        while (pos < len && (text[pos] == ' ' || text[pos] == '\t' || text[pos] == '\n' || text[pos] == '\r')) ++pos;
        start = pos;
        while (pos < len && text[pos] != ' ' && text[pos] != '\t' && text[pos] != '\n' && text[pos] != '\r') ++pos;
        if (pos == start) break;
        if (words && used + 1 < len + 1) out[used++] = ' ';
        {
            size_t part = pos - start;
            memmove(out + used, text + start, part);
            used += part;
        }
        words++;
    }
    out[used] = '\0';
    return out;
}

static int ai_complete_syscall(MellowRuntimeContext *ctx, const MValue *args, size_t argc, MValue *out) {
    char *provider_name, *prompt, *style, *text, *response = NULL;
    AiProvider *provider;
    MValue result, options_value, config_copy;
    const MValue *options;
    int max_words = 48;
    size_t prompt_len = 0, start = 0, end;
    if (argc < 1) { provider_name = (char *)calloc(8, 1); if (provider_name) memcpy(provider_name, "offline", 8); }
    else provider_name = ai_value_text(&args[0], NULL);
    prompt = argc > 1 ? ai_value_text(&args[1], &prompt_len) : (char *)calloc(1, 1);
    options = argc > 2 ? &args[2] : NULL;
    if (!provider_name || !prompt) { free(provider_name); free(prompt); return ai_config_error(ctx, "AI_PROVIDER_ERROR: out of memory"); }
    provider = ai_provider_find(provider_name);
    if (!provider) provider = ai_provider_find("offline");
    {
        const MValue *mode = provider ? ai_map_get(&provider->config, "mode") : NULL;
        char *mode_text = mode ? ai_value_text(mode, NULL) : NULL;
        if (mode_text && ai_ieq(mode_text, "openai")) {
            free(mode_text);
            free(provider_name);
            free(prompt);
            return ai_config_error(ctx, "AI_PROVIDER_ERROR: network transport is not available in the standalone runtime");
        }
        free(mode_text);
    }
    if (options && options->tag == MVAL_MAP) {
        const MValue *style_value = ai_map_get(options, "style");
        const MValue *words_value = ai_map_get(options, "max_words");
        style = style_value ? ai_value_text(style_value, NULL) : NULL;
        if (!style) { style = (char *)calloc(8, 1); if (style) memcpy(style, "concise", 8); }
        max_words = (int)ai_int_or(words_value, 48);
    } else {
        style = (char *)calloc(8, 1);
        if (style) memcpy(style, "concise", 8);
    }
    if (!style) { free(provider_name); free(prompt); return ai_config_error(ctx, "AI_PROVIDER_ERROR: out of memory"); }
    if (max_words < 0) max_words = 0;
    while (start < prompt_len && (prompt[start] == ' ' || prompt[start] == '\t' || prompt[start] == '\n' || prompt[start] == '\r')) ++start;
    end = prompt_len;
    while (end > start && (prompt[end - 1] == ' ' || prompt[end - 1] == '\t' || prompt[end - 1] == '\n' || prompt[end - 1] == '\r')) --end;
    text = ai_utf8_prefix(prompt + start, end - start, end - start, NULL);
    if (!text) { free(style); free(provider_name); free(prompt); return ai_config_error(ctx, "AI_PROVIDER_ERROR: out of memory"); }
    {
        char *low = (char *)calloc(strlen(text) + 1, 1);
        size_t i;
        if (low) { for (i = 0; text[i]; ++i) low[i] = (char)tolower((unsigned char)text[i]); }
        if (strcmp(provider_name, "local-rag") == 0) {
            char *slice = ai_utf8_prefix(text, strlen(text), (size_t)(max_words * 2), NULL);
            size_t cap = (slice ? strlen(slice) : 0) + 24;
            response = (char *)calloc(cap, 1);
            if (response) snprintf(response, cap, "[local-rag] %s", slice ? slice : "");
            free(slice);
        } else if (low && strstr(low, "summar")) {
            response = ai_join_words(text, strlen(text), max_words);
        } else {
            size_t cap = strlen(text) + strlen(provider_name) + strlen(style) + 8;
            char *full = (char *)calloc(cap, 1);
            size_t limit;
            if (full) {
                snprintf(full, cap, "[%s/%s] %s", provider_name, style, text);
                limit = (size_t)(max_words * 8) > 24u ? (size_t)(max_words * 8) : 24u;
                response = ai_utf8_prefix(full, strlen(full), limit, NULL);
            }
            free(full);
        }
        free(low);
    }
    free(text);
    free(style);
    if (!response) { free(provider_name); free(prompt); return ai_config_error(ctx, "AI_PROVIDER_ERROR: out of memory"); }
    ai_map_new(&result, 4);
    ai_map_put_str(&result, "provider", provider_name);
    ai_map_put_str(&result, "response", response);
    options_value = options ? clone_value(ctx, options) : mval_none();
    if (!options) { ai_map_new(&options_value, 0); }
    ai_map_put(&result, "options", options_value);
    config_copy = ai_redact(ctx, provider ? &provider->config : NULL);
    ai_map_put(&result, "config", config_copy);
    free(response);
    free(provider_name);
    free(prompt);
    *out = result;
    return 1;
}

static MValue ai_api_embed_syscall(const MValue *args, size_t argc) {
    char *provider_name;
    char *text;
    size_t text_len = 0;
    MValue result;
    provider_name = argc > 0 ? ai_value_text(&args[0], NULL) : NULL;
    text = argc > 1 ? ai_value_text(&args[1], &text_len) : (char *)calloc(1, 1);
    if (!provider_name) { provider_name = (char *)calloc(8, 1); if (provider_name) memcpy(provider_name, "offline", 8); }
    if (!provider_name || !text) { free(provider_name); free(text); return ai_error_map("AI_API: out of memory"); }
    ai_map_new(&result, 2);
    ai_map_put_str(&result, "provider", provider_name);
    ai_map_put(&result, "embedding", ai_embed_list(text, text_len));
    free(provider_name);
    free(text);
    return result;
}
