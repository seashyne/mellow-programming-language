/* AI runtime fragment 13: the character n-gram language model. */

#define AI_MAX_LLM 8
#define AI_MAX_ORDER 8
#define AI_LLM_LOSS 50

typedef struct {
    int32_t cp;
    int count;
} AiCharCount;

typedef struct {
    int32_t ctx[AI_MAX_ORDER];
    int ctx_len;
    AiCharCount *items;
    size_t count;
    size_t cap;
} AiTransition;

typedef struct {
    int used;
    char name[64];
    int order;
    int64_t seed;
    int32_t *vocab;
    size_t vocab_count;
    size_t vocab_cap;
    AiTransition *trans;
    size_t trans_count;
    size_t trans_cap;
    long long trained_tokens;
    double loss[AI_LLM_LOSS];
    int loss_count;
    long long created_at;
    int seq;
} AiLlm;

static AiLlm ai_llms[AI_MAX_LLM];
static int ai_llm_seq;

static void ai_llm_free(AiLlm *llm) {
    size_t i;
    if (!llm) return;
    for (i = 0; i < llm->trans_count; ++i) free(llm->trans[i].items);
    free(llm->trans);
    free(llm->vocab);
    memset(llm, 0, sizeof(*llm));
}

static AiLlm *ai_llm_slot(const char *name) {
    int i;
    for (i = 0; i < AI_MAX_LLM; ++i)
        if (ai_llms[i].used && strcmp(ai_llms[i].name, name) == 0) return &ai_llms[i];
    return NULL;
}

static AiLlm *ai_llm_alloc(const char *name) {
    int i;
    AiLlm *found = ai_llm_slot(name);
    if (found) {
        int seq = found->seq;
        ai_llm_free(found);
        found->used = 1;
        found->seq = seq;
        snprintf(found->name, sizeof(found->name), "%s", name);
        return found;
    }
    for (i = 0; i < AI_MAX_LLM; ++i) {
        if (!ai_llms[i].used) {
            memset(&ai_llms[i], 0, sizeof(ai_llms[i]));
            ai_llms[i].used = 1;
            ai_llms[i].seq = ++ai_llm_seq;
            snprintf(ai_llms[i].name, sizeof(ai_llms[i].name), "%s", name);
            return &ai_llms[i];
        }
    }
    return NULL;
}

static int ai_vocab_add(AiLlm *llm, int32_t cp) {
    size_t lo = 0, hi = llm->vocab_count;
    while (lo < hi) {
        size_t mid = (lo + hi) / 2;
        if (llm->vocab[mid] < cp) lo = mid + 1;
        else hi = mid;
    }
    if (lo < llm->vocab_count && llm->vocab[lo] == cp) return 1;
    if (llm->vocab_count == llm->vocab_cap) {
        size_t next = llm->vocab_cap ? llm->vocab_cap * 2 : 32;
        int32_t *grown = (int32_t *)realloc(llm->vocab, next * sizeof(int32_t));
        if (!grown) return 0;
        llm->vocab = grown;
        llm->vocab_cap = next;
    }
    memmove(llm->vocab + lo + 1, llm->vocab + lo, (llm->vocab_count - lo) * sizeof(int32_t));
    llm->vocab[lo] = cp;
    llm->vocab_count++;
    return 1;
}

static AiTransition *ai_trans_find(AiLlm *llm, const int32_t *ctx, int ctx_len) {
    size_t i;
    for (i = 0; i < llm->trans_count; ++i) {
        AiTransition *t = &llm->trans[i];
        if (t->ctx_len == ctx_len && (ctx_len == 0 || memcmp(t->ctx, ctx, (size_t)ctx_len * sizeof(int32_t)) == 0))
            return t;
    }
    return NULL;
}

static AiTransition *ai_trans_find_or_add(AiLlm *llm, const int32_t *ctx, int ctx_len) {
    AiTransition *found = ai_trans_find(llm, ctx, ctx_len);
    if (found) return found;
    if (llm->trans_count == llm->trans_cap) {
        size_t next = llm->trans_cap ? llm->trans_cap * 2 : 32;
        AiTransition *grown = (AiTransition *)realloc(llm->trans, next * sizeof(AiTransition));
        if (!grown) return NULL;
        llm->trans = grown;
        llm->trans_cap = next;
    }
    found = &llm->trans[llm->trans_count++];
    memset(found, 0, sizeof(*found));
    found->ctx_len = ctx_len;
    if (ctx_len > 0) memcpy(found->ctx, ctx, (size_t)ctx_len * sizeof(int32_t));
    return found;
}

static void ai_trans_increment(AiTransition *trans, int32_t cp) {
    size_t i;
    for (i = 0; i < trans->count; ++i)
        if (trans->items[i].cp == cp) { trans->items[i].count++; return; }
    if (trans->count == trans->cap) {
        size_t next = trans->cap ? trans->cap * 2 : 4;
        AiCharCount *grown = (AiCharCount *)realloc(trans->items, next * sizeof(AiCharCount));
        if (!grown) return;
        trans->items = grown;
        trans->cap = next;
    }
    trans->items[trans->count].cp = cp;
    trans->items[trans->count].count = 1;
    trans->count++;
}

static void ai_history_push(int32_t *history, int *len, int order, int32_t cp) {
    if (*len < order) {
        history[*len] = cp;
        (*len)++;
    } else if (order > 0) {
        if (order > 1) memmove(history, history + 1, (size_t)(order - 1) * sizeof(int32_t));
        history[order - 1] = cp;
    }
}

static void ai_llm_add_vocab_text(AiLlm *llm, const char *text, size_t len) {
    size_t pos = 0;
    int32_t cp;
    while (pos < len && ai_utf8_decode(text, len, &pos, &cp)) ai_vocab_add(llm, cp);
}

static double ai_llm_loss(AiLlm *llm, const AiTexts *texts) {
    double vocab_size = (double)(llm->vocab_count ? llm->vocab_count : 1);
    double nll = 0.0;
    long long count = 0;
    size_t t;
    for (t = 0; t < texts->count; ++t) {
        const char *text = texts->items[t];
        size_t len = strlen(text), pos = 0;
        int32_t history[AI_MAX_ORDER];
        int hist_len = 0;
        int32_t cp;
        while (pos < len && ai_utf8_decode(text, len, &pos, &cp)) {
            AiTransition *bucket = llm->trans_count ? ai_trans_find(llm, history, hist_len) : NULL;
            double total = 0.0, prob;
            size_t i;
            if (bucket) {
                for (i = 0; i < bucket->count; ++i) total += (double)bucket->items[i].count;
            }
            prob = 1.0;
            if (bucket) {
                int hits = 0;
                for (i = 0; i < bucket->count; ++i) if (bucket->items[i].cp == cp) { hits = bucket->items[i].count; break; }
                prob = ((double)hits + 1.0) / (total + vocab_size);
            } else {
                prob = 1.0 / vocab_size;
            }
            nll -= log(prob);
            count++;
            ai_history_push(history, &hist_len, llm->order, cp);
        }
    }
    return count ? nll / (double)count : 0.0;
}

static double ai_llm_train(AiLlm *llm, const AiTexts *texts, int epochs) {
    size_t t, i;
    int epoch;
    double total_loss = 0.0;
    if (texts->count == 0) return 0.0;
    for (t = 0; t < texts->count; ++t) ai_llm_add_vocab_text(llm, texts->items[t], strlen(texts->items[t]));
    for (i = 0; i + 1 < texts->count; ++i) ai_vocab_add(llm, '\n');
    for (epoch = 0; epoch < (epochs > 0 ? epochs : 1); ++epoch) {
        for (t = 0; t < texts->count; ++t) {
            const char *text = texts->items[t];
            size_t len = strlen(text), pos = 0;
            int32_t history[AI_MAX_ORDER];
            int hist_len = 0;
            int32_t cp;
            while (pos < len && ai_utf8_decode(text, len, &pos, &cp)) {
                AiTransition *bucket = ai_trans_find_or_add(llm, history, hist_len);
                if (bucket) ai_trans_increment(bucket, cp);
                ai_history_push(history, &hist_len, llm->order, cp);
                llm->trained_tokens++;
            }
        }
        total_loss = ai_llm_loss(llm, texts);
        if (llm->loss_count < AI_LLM_LOSS) llm->loss[llm->loss_count++] = ai_round6(total_loss);
        else {
            memmove(llm->loss, llm->loss + 1, (AI_LLM_LOSS - 1) * sizeof(double));
            llm->loss[AI_LLM_LOSS - 1] = ai_round6(total_loss);
        }
    }
    return total_loss;
}
