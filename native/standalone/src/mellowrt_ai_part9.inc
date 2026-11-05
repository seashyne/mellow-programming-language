/* AI runtime fragment 9: embeddings, retrieval, and prompt templates. */

#define AI_EMBED_DIM 64

static void ai_embed_vector(const char *text, size_t len, double out[AI_EMBED_DIM]) {
    size_t pos = 0, index = 0;
    int i;
    double count = (double)ai_utf8_count(text, len);
    double magnitude = 0.0;
    int32_t cp;
    for (i = 0; i < AI_EMBED_DIM; ++i) out[i] = 0.0;
    if (count <= 0.0) return;
    while (pos < len && ai_utf8_decode(text, len, &pos, &cp)) {
        int slot = (int)(((cp % AI_EMBED_DIM) + AI_EMBED_DIM) % AI_EMBED_DIM);
        out[slot] += 1.0 / count;
        out[(slot + (int)(index % AI_EMBED_DIM)) % AI_EMBED_DIM] += 0.5 / count;
        index++;
    }
    for (i = 0; i < AI_EMBED_DIM; ++i) magnitude += out[i] * out[i];
    magnitude = sqrt(magnitude);
    if (magnitude == 0.0) magnitude = 1.0;
    for (i = 0; i < AI_EMBED_DIM; ++i) out[i] = ai_round6(out[i] / magnitude);
}

static double ai_cosine(const double *a, const double *b) {
    double dot = 0.0, ma = 0.0, mb = 0.0;
    int i;
    for (i = 0; i < AI_EMBED_DIM; ++i) {
        dot += a[i] * b[i];
        ma += a[i] * a[i];
        mb += b[i] * b[i];
    }
    ma = sqrt(ma);
    mb = sqrt(mb);
    if (ma == 0.0) ma = 1.0;
    if (mb == 0.0) mb = 1.0;
    return dot / (ma * mb);
}

static MValue ai_embed_list(const char *text, size_t len) {
    double vector[AI_EMBED_DIM];
    MValue list;
    int i;
    ai_embed_vector(text, len, vector);
    ai_list_new(&list, AI_EMBED_DIM);
    for (i = 0; i < AI_EMBED_DIM; ++i) ai_list_push(&list, mval_f64(vector[i]));
    return list;
}

typedef struct {
    size_t index;
    char *text;
    size_t text_len;
    double score;
} AiRankedDoc;

static MValue ai_vector_search_syscall(const MValue *args, size_t argc, int default_top) {
    char *query = NULL;
    size_t query_len = 0, i, kept = 0;
    const MValue *docs;
    double query_vector[AI_EMBED_DIM];
    int top_k = default_top;
    AiRankedDoc *ranked;
    MValue result;
    if (argc < 2) return ai_error_map("ai.vector_search requires query and docs");
    query = ai_value_text(&args[0], &query_len);
    if (!query) return ai_error_map("AI_VECTOR: out of memory");
    docs = &args[1];
    if (docs->tag != MVAL_LIST) {
        ai_list_new(&result, 0);
        free(query);
        return result;
    }
    if (argc > 2) top_k = (int)ai_int_or(&args[2], default_top);
    if (top_k < 1) top_k = 1;
    ai_embed_vector(query, query_len, query_vector);
    free(query);
    ranked = (AiRankedDoc *)calloc(docs->as.list.len ? docs->as.list.len : 1, sizeof(AiRankedDoc));
    if (!ranked) return ai_error_map("AI_VECTOR: out of memory");
    for (i = 0; i < docs->as.list.len; ++i) {
        double vector[AI_EMBED_DIM];
        char *text = ai_value_text(&docs->as.list.items[i], &ranked[kept].text_len);
        if (!text) continue;
        ranked[kept].index = i;
        ranked[kept].text = text;
        ai_embed_vector(text, ranked[kept].text_len, vector);
        ranked[kept].score = ai_cosine(query_vector, vector);
        kept++;
    }
    for (i = 0; i < kept; ++i) {
        size_t j = i;
        while (j > 0 && ranked[j].score > ranked[j - 1].score) {
            AiRankedDoc tmp = ranked[j];
            ranked[j] = ranked[j - 1];
            ranked[j - 1] = tmp;
            --j;
        }
    }
    ai_list_new(&result, (size_t)top_k);
    for (i = 0; i < (size_t)top_k && i < kept; ++i) {
        MValue entry;
        ai_map_new(&entry, 3);
        ai_map_put(&entry, "index", mval_i64((int64_t)ranked[i].index));
        ai_map_put(&entry, "text", ai_strn(ranked[i].text, ranked[i].text_len));
        ai_map_put(&entry, "score", mval_f64(ai_round6(ranked[i].score)));
        ai_list_push(&result, entry);
    }
    for (i = 0; i < docs->as.list.len; ++i) free(ranked[i].text);
    free(ranked);
    return result;
}

static MValue ai_rag_answer_syscall(const MValue *args, size_t argc) {
    MValue matches, result, call_args[3];
    char *query = NULL;
    size_t query_len = 0, i, used = 0, cap = 1;
    char *context;
    int top_k = 2;
    if (argc < 2) return ai_error_map("ai.rag_answer requires query and docs");
    query = ai_value_text(&args[0], &query_len);
    if (!query) return ai_error_map("AI_RAG: out of memory");
    if (argc > 2) top_k = (int)ai_int_or(&args[2], 2);
    call_args[0] = ai_strn(query, query_len);
    call_args[1] = args[1];
    call_args[2] = mval_i64(top_k);
    matches = ai_vector_search_syscall(call_args, 3, 2);
    mvalue_free(&call_args[0]);
    for (i = 0; i < matches.as.list.len; ++i) {
        const MValue *text = ai_map_get(&matches.as.list.items[i], "text");
        if (text && text->tag == MVAL_STR) cap += text->as.str.len + 3;
    }
    context = (char *)calloc(cap, 1);
    if (!context) { mvalue_free(&matches); free(query); return ai_error_map("AI_RAG: out of memory"); }
    for (i = 0; i < matches.as.list.len; ++i) {
        const MValue *text = ai_map_get(&matches.as.list.items[i], "text");
        size_t take;
        if (!text || text->tag != MVAL_STR) continue;
        take = ai_utf8_offset(text->as.str.ptr, text->as.str.len, 180);
        if (used && used + 3 < cap) { memcpy(context + used, " | ", 3); used += 3; }
        if (used + take + 1 > cap) take = cap > used ? cap - used - 1 : 0;
        if (take) memcpy(context + used, text->as.str.ptr, take);
        used += take;
        context[used] = '\0';
    }
    ai_map_new(&result, 3);
    ai_map_put(&result, "query", ai_strn(query, query_len));
    ai_map_put(&result, "matches", matches);
    {
        size_t answer_cap = query_len + used + 96;
        char *answer = (char *)calloc(answer_cap, 1);
        if (!answer) { free(context); free(query); mvalue_free(&result); return ai_error_map("AI_RAG: out of memory"); }
        if (matches.as.list.len)
            snprintf(answer, answer_cap, "Offline RAG summary for '%s': best matches suggest %s", query, context);
        else
            snprintf(answer, answer_cap, "No relevant context found for '%s'.", query);
        ai_map_put_str(&result, "answer", answer);
        free(answer);
    }
    free(context);
    free(query);
    return result;
}

static MValue ai_prompt_template_syscall(const MValue *args, size_t argc) {
    char *result_text, *template_text;
    size_t i;
    if (argc < 2 || args[1].tag != MVAL_MAP) return ai_error_map("ai.prompt_template requires template and vars map");
    template_text = ai_value_text(&args[0], NULL);
    if (!template_text) return ai_error_map("AI_TEMPLATE: out of memory");
    result_text = template_text;
    for (i = 0; i < args[1].as.map.len; ++i) {
        const MValue *key = &args[1].as.map.keys[i];
        char *key_text = ai_value_text(key, NULL);
        char *value_text = ai_value_text(&args[1].as.map.values[i], NULL);
        if (key_text && value_text) {
            char needle[256];
            char *cursor;
            size_t needle_len, value_len, result_len;
            size_t cap;
            snprintf(needle, sizeof(needle), "{{%s}}", key_text);
            needle_len = strlen(needle);
            value_len = strlen(value_text);
            result_len = strlen(result_text);
            cap = result_len + 1;
            for (cursor = result_text; (cursor = strstr(cursor, needle)) != NULL; cursor += needle_len)
                cap += value_len > needle_len ? value_len - needle_len : 0;
            {
                char *next = (char *)calloc(cap + 1, 1);
                size_t used = 0;
                cursor = result_text;
                if (next) {
                    while (*cursor) {
                        char *hit = strstr(cursor, needle);
                        if (!hit) { size_t rest = strlen(cursor); memcpy(next + used, cursor, rest); used += rest; break; }
                        {
                            size_t head = (size_t)(hit - cursor);
                            memcpy(next + used, cursor, head); used += head;
                            memcpy(next + used, value_text, value_len); used += value_len;
                        }
                        cursor = hit + needle_len;
                    }
                    next[used] = '\0';
                    free(result_text);
                    result_text = next;
                }
            }
        }
        free(key_text);
        free(value_text);
    }
    {
        MValue result = ai_str(result_text);
        free(result_text);
        return result;
    }
}
