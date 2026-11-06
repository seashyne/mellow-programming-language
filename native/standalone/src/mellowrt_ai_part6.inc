/* AI runtime fragment 6: boot state, chat sessions, replies, and templates. */

#define AI_MAX_SESSIONS 8
#define AI_MAX_MESSAGES 32
#define AI_REPLY_CHARS 512

typedef struct {
    char user[AI_REPLY_CHARS];
    char assistant[AI_REPLY_CHARS];
    long long at;
} AiChatMessage;

typedef struct {
    int used;
    char id[96];
    char name[64];
    char system[AI_REPLY_CHARS];
    AiChatMessage messages[AI_MAX_MESSAGES];
    int count;
    long long created_at;
} AiSession;

static AiSession ai_sessions[AI_MAX_SESSIONS];
static int ai_session_total;
static struct { int booted; long long boot_count; long long last_boot_at; } ai_runtime;

static AiSession *ai_session_find(const char *id) {
    int i;
    for (i = 0; i < AI_MAX_SESSIONS; ++i)
        if (ai_sessions[i].used && strcmp(ai_sessions[i].id, id) == 0) return &ai_sessions[i];
    return NULL;
}

static void ai_session_id(const char *name, char *out, size_t cap) {
    char safe[64];
    size_t i, len = 0, start = 0, end;
    for (i = 0; name && name[i] && len + 1 < sizeof(safe); ++i) {
        unsigned char c = (unsigned char)name[i];
        safe[len++] = (isalnum(c) || c == '_' || c == '-') ? (char)c : '_';
    }
    safe[len] = '\0';
    while (start < len && safe[start] == '_') start++;
    end = len;
    while (end > start && safe[end - 1] == '_') end--;
    if (end == start) {
        snprintf(out, cap, "session_%d", ai_session_total + 1);
        return;
    }
    snprintf(out, cap, "%.*s_%d", (int)(end - start), safe + start, ai_session_total + 1);
}

static void ai_copy_bounded(char *out, size_t cap, const char *text) {
    size_t len;
    if (!out || cap == 0) return;
    if (!text) { out[0] = '\0'; return; }
    len = strlen(text);
    if (len >= cap) len = cap - 1;
    memcpy(out, text, len);
    out[len] = '\0';
}

/* Pick one reply from a group with the runtime RNG, like random.choice. */
static const char *ai_pick(MellowRuntimeContext *ctx, const char *const *choices, size_t count) {
    mrng_ensure(ctx);
    return choices[mrng_randbelow(&ctx->rng, count)];
}

static const char *const AI_GREETING[] = {
    "Hello! How can I help you today?",
    "Hi there! What can I do for you?",
    "Hey! Ready to assist."
};
static const char *const AI_FAREWELL[] = {
    "Goodbye! Have a great time!",
    "See you later!",
    "Farewell! Come back anytime."
};
static const char *const AI_WELLBEING[] = {
    "I'm doing great, thanks for asking!",
    "All systems running smoothly!",
    "Feeling helpful as always!"
};
static const char *const AI_IDENTITY[] = {
    "I'm MellowAI, built into MellowLang v1.4.8.",
    "My name is MellowAI — your in-language AI assistant."
};
static const char *const AI_HELP[] = {
    "I can chat, answer questions, and I'm part of MellowLang's AI module.\n"
    "You can also train custom models, make predictions, and more!"
};
static const char *const AI_MELLOW[] = {
    "MellowLang is a sandboxed scripting language with built-in AI, game, and math modules.",
    "MellowLang v1.4.8 introduces full AI capabilities via the `ai` module!"
};
static const char *const AI_TRAIN[] = {
    "To train a model: ai.model_create(name, layers), then ai.train(name, data, labels)."
};
static const char *const AI_PREDICT[] = {
    "Use ai.predict(model_name, input) to get predictions from a trained model."
};

static int ai_contains(const char *haystack, const char *needle) {
    return strstr(haystack, needle) != NULL;
}

/* The reply engine distilled from the Python AI models, keyword groups in order. */
static const char *ai_chat_reply(MellowRuntimeContext *ctx, const char *prompt) {
    char *low = (char *)calloc(strlen(prompt) + 1, 1);
    static char generic[1024];
    size_t i, len = 0, words = 0, take;
    const char *wanted[4];
    if (!low) return "I see you said something. Could you tell me more?";
    for (i = 0; prompt[i]; ++i) low[i] = (char)tolower((unsigned char)prompt[i]);
    while (low[0] == ' ') memmove(low, low + 1, strlen(low));
    len = strlen(low);
    while (len && low[len - 1] == ' ') low[--len] = '\0';

    if (ai_contains(low, "hello") || ai_contains(low, "hi") || ai_contains(low, "hey") ||
        ai_contains(low, "สวัสดี")) { free(low); return ai_pick(ctx, AI_GREETING, 3); }
    if (ai_contains(low, "bye") || ai_contains(low, "goodbye") || ai_contains(low, "ลาก่อน")) {
        free(low); return ai_pick(ctx, AI_FAREWELL, 3);
    }
    if (ai_contains(low, "how are you") || ai_contains(low, "how do you do") ||
        ai_contains(low, "เป็นยังไงบ้าง")) { free(low); return ai_pick(ctx, AI_WELLBEING, 3); }
    if (ai_contains(low, "what is your name") || ai_contains(low, "who are you") ||
        ai_contains(low, "ชื่ออะไร")) { free(low); return ai_pick(ctx, AI_IDENTITY, 2); }
    if (ai_contains(low, "help") || ai_contains(low, "what can you do") ||
        ai_contains(low, "ช่วยอะไรได้") || ai_contains(low, "ทำอะไรได้")) {
        free(low); return ai_pick(ctx, AI_HELP, 1);
    }
    if (ai_contains(low, "mellow")) {
        free(low); return ai_pick(ctx, AI_MELLOW, 2);
    }
    if (ai_contains(low, "train") || ai_contains(low, "training") || ai_contains(low, "เทรน")) {
        free(low); return ai_pick(ctx, AI_TRAIN, 1);
    }
    if (ai_contains(low, "predict") || ai_contains(low, "prediction") || ai_contains(low, "พยากรณ์")) {
        free(low); return ai_pick(ctx, AI_PREDICT, 1);
    }
    free(low);

    for (i = 0; prompt[i] && words < 4; ) {
        while (prompt[i] == ' ' || prompt[i] == '\t' || prompt[i] == '\n' || prompt[i] == '\r') ++i;
        if (!prompt[i]) break;
        wanted[words++] = prompt + i;
        while (prompt[i] && prompt[i] != ' ' && prompt[i] != '\t' && prompt[i] != '\n' && prompt[i] != '\r') ++i;
    }
    if (words <= 2) {
        snprintf(generic, sizeof(generic), "I see you said '%s'. Could you tell me more?", prompt);
        return generic;
    }
    take = strchr(prompt, '?') ? 3 : 4;
    if (take > words) take = words;
    {
        size_t used = 0;
        generic[0] = '\0';
        for (i = 0; i < take; ++i) {
            size_t part = 0;
            while (wanted[i][part] && wanted[i][part] != ' ' && wanted[i][part] != '\t' &&
                   wanted[i][part] != '\n' && wanted[i][part] != '\r') part++;
            if (used + part + 2 >= sizeof(generic)) break;
            if (i) generic[used++] = ' ';
            memcpy(generic + used, wanted[i], part);
            used += part;
            generic[used] = '\0';
        }
        if (strchr(prompt, '?'))
            snprintf(generic + used, sizeof(generic) - used,
                     "...' Let me think — as MellowAI I'd suggest exploring the docs or running more experiments!");
        else
            snprintf(generic + used, sizeof(generic) - used,
                     "...'. MellowAI is learning from your input. For deeper AI, use ai.train() with your own data!");
    }
    return generic;
}

/* ai.chat(prompt, model?, system?) with the chat memory kept on the model. */
static char *ai_chat_generate(MellowRuntimeContext *ctx, const char *prompt, const char *model_name) {
    const char *reply = ai_chat_reply(ctx, prompt);
    AiModel *model = ai_model_slot(model_name);
    char *copy;
    size_t len = strlen(reply);
    if (!model) model = ai_model_alloc(model_name);
    if (model) {
        ai_copy_bounded(model->task, sizeof(model->task), "chat");
        model->chat_memory++;
    }
    copy = (char *)calloc(len + 1, 1);
    if (!copy) return NULL;
    memcpy(copy, reply, len);
    return copy;
}
