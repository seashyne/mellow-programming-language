/* AI runtime fragment 17: chat prompt shaping and the completion surface. */

typedef struct {
    char *ptr;
    size_t len;
    size_t cap;
} AiBuf;

static int ai_buf_reserve(AiBuf *buffer, size_t extra) {
    size_t need = buffer->len + extra + 1;
    size_t cap;
    char *grown;
    if (need <= buffer->cap) return 1;
    cap = buffer->cap ? buffer->cap : 64;
    while (cap < need) cap *= 2;
    grown = (char *)realloc(buffer->ptr, cap);
    if (!grown) return 0;
    buffer->ptr = grown;
    buffer->cap = cap;
    return 1;
}

static int ai_buf_add(AiBuf *buffer, const char *text, size_t len) {
    if (!ai_buf_reserve(buffer, len)) return 0;
    if (len) memcpy(buffer->ptr + buffer->len, text, len);
    buffer->len += len;
    buffer->ptr[buffer->len] = '\0';
    return 1;
}

static int ai_buf_add_str(AiBuf *buffer, const char *text) {
    return ai_buf_add(buffer, text ? text : "", text ? strlen(text) : 0);
}

static int ai_buf_add_char(AiBuf *buffer, char value) {
    return ai_buf_add(buffer, &value, 1);
}

static char *ai_buf_take(AiBuf *buffer) {
    char *out = buffer->ptr;
    if (!out) out = (char *)calloc(1, 1);
    buffer->ptr = NULL;
    buffer->len = 0;
    buffer->cap = 0;
    return out;
}

/* Python's _llm_prompt_from_messages: role lines plus a trailing assistant cue. */
static char *ai_prompt_from_messages(const MValue *messages) {
    AiBuf buffer = {0, 0, 0};
    if (messages && messages->tag == MVAL_LIST) {
        size_t i;
        for (i = 0; i < messages->as.list.len; ++i) {
            const MValue *item = &messages->as.list.items[i];
            if (buffer.len) ai_buf_add_char(&buffer, '\n');
            if (item->tag == MVAL_MAP) {
                const MValue *role = ai_map_get(item, "role");
                const MValue *content = ai_map_get(item, "content");
                char *role_text = role ? ai_value_text(role, NULL) : NULL;
                char *content_text = content ? ai_value_text(content, NULL) : NULL;
                if (content_text && *content_text) {
                    ai_buf_add_str(&buffer, role_text ? role_text : "user");
                    ai_buf_add_str(&buffer, ": ");
                    ai_buf_add_str(&buffer, content_text);
                } else {
                    char *text = ai_value_text(item, NULL);
                    ai_buf_add_str(&buffer, "user: ");
                    if (text) { ai_buf_add_str(&buffer, text); free(text); }
                }
                free(role_text);
                free(content_text);
            } else {
                char *text = ai_value_text(item, NULL);
                ai_buf_add_str(&buffer, "user: ");
                if (text) { ai_buf_add_str(&buffer, text); free(text); }
            }
        }
        if (buffer.len) ai_buf_add_char(&buffer, '\n');
        ai_buf_add_str(&buffer, "assistant:");
    } else {
        char *text = ai_value_text(messages, NULL);
        ai_buf_add_str(&buffer, text ? text : "");
        free(text);
    }
    return ai_buf_take(&buffer);
}

static MValue ai_llm_complete_syscall(MellowRuntimeContext *ctx, const MValue *args, size_t argc) {
    MValue generated = ai_llm_generate_syscall(args, argc, 1);
    const MValue *model, *prompt, *completion, *tokens, *text;
    MValue result, choices, choice, usage;
    int64_t prompt_tokens = 0, completion_tokens = 0;
    if (ai_map_get(&generated, "error")) return generated;
    model = ai_map_get(&generated, "model");
    prompt = ai_map_get(&generated, "prompt");
    completion = ai_map_get(&generated, "completion");
    tokens = ai_map_get(&generated, "generated_tokens");
    text = ai_map_get(&generated, "text");
    if (prompt && prompt->tag == MVAL_STR)
        prompt_tokens = (int64_t)ai_utf8_count(prompt->as.str.ptr, prompt->as.str.len);
    completion_tokens = ai_int_or(tokens, 0);
    ai_map_new(&choice, 2);
    if (completion) ai_map_put(&choice, "text", clone_value(ctx, completion));
    else ai_map_put_str(&choice, "text", "");
    ai_map_put_str(&choice, "finish_reason", "length");
    ai_list_new(&choices, 1);
    ai_list_push(&choices, choice);
    ai_map_new(&usage, 3);
    ai_map_put(&usage, "prompt_tokens", mval_i64(prompt_tokens));
    ai_map_put(&usage, "completion_tokens", mval_i64(completion_tokens));
    ai_map_put(&usage, "total_tokens", mval_i64(prompt_tokens + completion_tokens));
    ai_map_new(&result, 4);
    if (model) ai_map_put(&result, "model", clone_value(ctx, model));
    else ai_map_put_str(&result, "model", "");
    ai_map_put(&result, "choices", choices);
    ai_map_put(&result, "usage", usage);
    if (text) ai_map_put(&result, "text", clone_value(ctx, text));
    else ai_map_put_str(&result, "text", "");
    mvalue_free(&generated);
    return result;
}

static MValue ai_llm_chat_syscall(MellowRuntimeContext *ctx, const MValue *args, size_t argc) {
    char *prompt;
    MValue call[3], generated, result, message, usage;
    const MValue *completion, *tokens, *model;
    int64_t prompt_tokens, completion_tokens;
    int owns_options = 0;
    if (argc < 2) return ai_error_map("ai.llm_chat requires model name and messages");
    prompt = ai_prompt_from_messages(&args[1]);
    if (!prompt) return ai_error_map("AI_LLM: out of memory");
    if (argc > 2 && args[2].tag == MVAL_MAP) call[2] = args[2];
    else { ai_map_new(&call[2], 0); owns_options = 1; }
    call[0] = args[0];
    call[1] = ai_str(prompt);
    prompt_tokens = (int64_t)ai_utf8_count(call[1].as.str.ptr, call[1].as.str.len);
    generated = ai_llm_generate_syscall(call, 3, 0);
    free(prompt);
    mvalue_free(&call[1]);
    if (owns_options) mvalue_free(&call[2]);
    if (ai_map_get(&generated, "error")) return generated;
    model = ai_map_get(&generated, "model");
    completion = ai_map_get(&generated, "completion");
    tokens = ai_map_get(&generated, "generated_tokens");
    completion_tokens = ai_int_or(tokens, 0);
    ai_map_new(&message, 2);
    ai_map_put_str(&message, "role", "assistant");
    if (completion) ai_map_put(&message, "content", clone_value(ctx, completion));
    else ai_map_put_str(&message, "content", "");
    ai_map_new(&usage, 3);
    ai_map_put(&usage, "prompt_tokens", mval_i64(prompt_tokens));
    ai_map_put(&usage, "completion_tokens", mval_i64(completion_tokens));
    ai_map_put(&usage, "total_tokens", mval_i64(prompt_tokens + completion_tokens));
    ai_map_new(&result, 3);
    if (model) ai_map_put(&result, "model", clone_value(ctx, model));
    else ai_map_put_str(&result, "model", "");
    ai_map_put(&result, "message", message);
    ai_map_put(&result, "usage", usage);
    mvalue_free(&generated);
    return result;
}

static MValue ai_llm_models_syscall(void) {
    char *names[AI_MAX_LLM];
    int count = 0, i, j;
    MValue list;
    for (i = 0; i < AI_MAX_LLM; ++i)
        if (ai_llms[i].used) names[count++] = ai_llms[i].name;
    for (i = 1; i < count; ++i) {
        char *key = names[i];
        j = i - 1;
        while (j >= 0 && strcmp(names[j], key) > 0) {
            names[j + 1] = names[j];
            --j;
        }
        names[j + 1] = key;
    }
    ai_list_new(&list, (size_t)count);
    for (i = 0; i < count; ++i) {
        AiLlm *llm = ai_llm_slot(names[i]);
        if (llm) ai_list_push(&list, ai_llm_info_value(llm));
    }
    return list;
}
