/* AI runtime fragment 10: session messages, chat, and decide. */

static MValue ai_session_message_syscall(MellowRuntimeContext *ctx, const MValue *args, size_t argc) {
    char *sid, *prompt, *merged, *response;
    AiSession *session;
    size_t i, start, cap, used = 0;
    if (argc < 2) return ai_error_map("ai.session_message requires session_id and prompt");
    sid = ai_value_text(&args[0], NULL);
    prompt = ai_value_text(&args[1], NULL);
    if (!sid || !prompt) { free(sid); free(prompt); return ai_error_map("AI_SESSION: out of memory"); }
    session = ai_session_find(sid);
    if (!session) {
        char message[160];
        MValue result;
        snprintf(message, sizeof(message), "Session '%s' not found", sid);
        result = ai_error_map(message);
        free(sid);
        free(prompt);
        return result;
    }
    start = session->count > 4 ? (size_t)(session->count - 4) : 0;
    cap = strlen(prompt) + 8;
    for (i = start; i < (size_t)session->count; ++i)
        cap += 8 + strlen(session->messages[i].user) + 12 + strlen(session->messages[i].assistant);
    merged = (char *)calloc(cap + 1, 1);
    if (!merged) { free(sid); free(prompt); return ai_error_map("AI_SESSION: out of memory"); }
    for (i = start; i < (size_t)session->count; ++i) {
        int written = snprintf(merged + used, cap + 1 - used, "%suser:%s assistant:%s",
                               used ? " " : "", session->messages[i].user, session->messages[i].assistant);
        if (written > 0) used += (size_t)written;
    }
    if (used) {
        int written = snprintf(merged + used, cap + 1 - used, " user:%s", prompt);
        if (written > 0) used += (size_t)written;
    } else {
        snprintf(merged, cap + 1, "%s", prompt);
    }
    response = ai_chat_generate(ctx, merged, sid);
    free(merged);
    if (!response) { free(sid); free(prompt); return ai_error_map("AI_SESSION: out of memory"); }
    if (session->count < AI_MAX_MESSAGES) {
        AiChatMessage *message = &session->messages[session->count++];
        ai_copy_bounded(message->user, sizeof(message->user), prompt);
        ai_copy_bounded(message->assistant, sizeof(message->assistant), response);
        message->at = (long long)time(NULL);
    }
    {
        MValue result;
        ai_map_new(&result, 3);
        ai_map_put_str(&result, "session", sid);
        ai_map_put_str(&result, "response", response);
        ai_map_put(&result, "messages", mval_i64(session->count));
        free(response);
        free(sid);
        free(prompt);
        return result;
    }
}

static MValue ai_session_history_syscall(const MValue *args, size_t argc) {
    MValue list;
    char *sid;
    AiSession *session;
    int i;
    ai_list_new(&list, AI_MAX_MESSAGES);
    if (argc < 1) return list;
    sid = ai_value_text(&args[0], NULL);
    if (!sid) return list;
    session = ai_session_find(sid);
    free(sid);
    if (!session) return list;
    for (i = 0; i < session->count; ++i) {
        MValue entry;
        ai_map_new(&entry, 3);
        ai_map_put_str(&entry, "user", session->messages[i].user);
        ai_map_put_str(&entry, "assistant", session->messages[i].assistant);
        ai_map_put(&entry, "at", mval_i64(session->messages[i].at));
        ai_list_push(&list, entry);
    }
    return list;
}

static MValue ai_chat_syscall(MellowRuntimeContext *ctx, const MValue *args, size_t argc) {
    char *prompt, *model_name, *response;
    AiModel *model;
    MValue result;
    if (argc < 1) return ai_error_map("ai.chat requires a prompt");
    prompt = ai_value_text(&args[0], NULL);
    model_name = ai_value_text(argc > 1 && args[1].tag != MVAL_NONE ? &args[1] : NULL, NULL);
    if (!prompt || !model_name) { free(prompt); free(model_name); return ai_error_map("AI_CHAT: out of memory"); }
    if (!*model_name) { free(model_name); model_name = (char *)calloc(14, 1); if (model_name) memcpy(model_name, "_chat_default", 14); }
    if (!model_name) { free(prompt); return ai_error_map("AI_CHAT: out of memory"); }
    response = ai_chat_generate(ctx, prompt, model_name);
    if (!response) { free(prompt); free(model_name); return ai_error_map("AI_CHAT: out of memory"); }
    model = ai_model_slot(model_name);
    ai_map_new(&result, 3);
    ai_map_put_str(&result, "response", response);
    ai_map_put_str(&result, "model", model_name);
    ai_map_put(&result, "memory_size", mval_i64(model ? model->chat_memory : 1));
    free(response);
    free(prompt);
    free(model_name);
    return result;
}

/* ai.decide(label, reason?) mirrors the runtime helper: it returns the label
 * so a script can record a branch choice, and never consumes randomness. */
static MValue ai_decide_syscall(MellowRuntimeContext *ctx, const MValue *args, size_t argc) {
    char *label;
    MValue result;
    (void)ctx;
    if (argc == 0) return ai_str("");
    label = ai_value_text(&args[0], NULL);
    if (!label) return ai_str("");
    result = ai_str(label);
    free(label);
    return result;
}
