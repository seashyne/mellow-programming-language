/* AI runtime fragment 11: the provider registry and configuration. */

#define AI_MAX_PROVIDERS 8

typedef struct {
    int used;
    char name[64];
    MValue config;
} AiProvider;

static AiProvider ai_provider_registry[AI_MAX_PROVIDERS];
static int ai_providers_ready;

static int ai_ieq(const char *a, const char *b) {
    while (*a && *b) {
        if (tolower((unsigned char)*a) != tolower((unsigned char)*b)) return 0;
        ++a;
        ++b;
    }
    return *a == *b;
}

static int ai_map_set(MValue *map, const char *key, MValue value) {
    size_t i, len = strlen(key);
    for (i = 0; i < map->as.map.len; ++i) {
        const MValue *k = &map->as.map.keys[i];
        if (k->tag == MVAL_STR && k->as.str.len == len && k->as.str.ptr &&
            memcmp(k->as.str.ptr, key, len) == 0) {
            mvalue_free(&map->as.map.values[i]);
            map->as.map.values[i] = value;
            return 1;
        }
    }
    if (map->as.map.len == map->as.map.cap) {
        size_t next = map->as.map.cap ? map->as.map.cap * 2 : 8;
        MValue *keys = (MValue *)realloc(map->as.map.keys, next * sizeof(MValue));
        MValue *values;
        if (!keys) return 0;
        map->as.map.keys = keys;
        values = (MValue *)realloc(map->as.map.values, next * sizeof(MValue));
        if (!values) return 0;
        map->as.map.values = values;
        map->as.map.cap = next;
    }
    map->as.map.keys[map->as.map.len] = ai_str(key);
    map->as.map.values[map->as.map.len] = value;
    map->as.map.len++;
    return 1;
}

static void ai_providers_init(void) {
    MValue offline, rag;
    if (ai_providers_ready) return;
    ai_map_new(&offline, 3);
    ai_map_put_str(&offline, "mode", "offline");
    ai_map_put(&offline, "max_context", mval_i64(16));
    ai_map_put_str(&offline, "status", "ready");
    ai_map_new(&rag, 3);
    ai_map_put_str(&rag, "mode", "offline");
    ai_map_put(&rag, "max_context", mval_i64(8));
    ai_map_put_str(&rag, "status", "ready");
    ai_provider_registry[0].used = 1;
    snprintf(ai_provider_registry[0].name, sizeof(ai_provider_registry[0].name), "offline");
    ai_provider_registry[0].config = offline;
    ai_provider_registry[1].used = 1;
    snprintf(ai_provider_registry[1].name, sizeof(ai_provider_registry[1].name), "local-rag");
    ai_provider_registry[1].config = rag;
    ai_providers_ready = 1;
}

static AiProvider *ai_provider_find(const char *name) {
    int i;
    ai_providers_init();
    for (i = 0; i < AI_MAX_PROVIDERS; ++i)
        if (ai_provider_registry[i].used && strcmp(ai_provider_registry[i].name, name) == 0)
            return &ai_provider_registry[i];
    return NULL;
}

static AiProvider *ai_provider_alloc(const char *name) {
    int i;
    AiProvider *found = ai_provider_find(name);
    if (found) return found;
    for (i = 0; i < AI_MAX_PROVIDERS; ++i) {
        if (!ai_provider_registry[i].used) {
            ai_provider_registry[i].used = 1;
            snprintf(ai_provider_registry[i].name, sizeof(ai_provider_registry[i].name), "%s", name);
            ai_map_new(&ai_provider_registry[i].config, 2);
            ai_map_put_str(&ai_provider_registry[i].config, "mode", "offline");
            return &ai_provider_registry[i];
        }
    }
    return NULL;
}

static int ai_header_is_secret(const MValue *key) {
    char text[64];
    char *name = ai_value_text(key, NULL);
    int result;
    if (!name) return 0;
    snprintf(text, sizeof(text), "%s", name);
    free(name);
    result = ai_ieq(text, "authorization") || ai_ieq(text, "api-key") || ai_ieq(text, "x-api-key");
    return result;
}

static MValue ai_redact(MellowRuntimeContext *ctx, const MValue *config) {
    MValue out;
    size_t i;
    ai_map_new(&out, config && config->tag == MVAL_MAP ? config->as.map.len : 0);
    if (!config || config->tag != MVAL_MAP) return out;
    for (i = 0; i < config->as.map.len; ++i) {
        const MValue *key = &config->as.map.keys[i];
        const MValue *value = &config->as.map.values[i];
        if (key->tag == MVAL_STR && key->as.str.len == 7 && key->as.str.ptr &&
            memcmp(key->as.str.ptr, "api_key", 7) == 0 && ai_truthy(value)) {
            ai_map_put_str(&out, "api_key", "***");
        } else if (key->tag == MVAL_STR && key->as.str.len == 7 && key->as.str.ptr &&
                   memcmp(key->as.str.ptr, "headers", 7) == 0 && value->tag == MVAL_MAP) {
            MValue headers;
            size_t j;
            ai_map_new(&headers, value->as.map.len);
            for (j = 0; j < value->as.map.len; ++j) {
                const MValue *hkey = &value->as.map.keys[j];
                if (ai_header_is_secret(hkey)) {
                    char *name = ai_value_text(hkey, NULL);
                    if (name) { ai_map_put_str(&headers, name, "***"); free(name); }
                } else {
                    char *name = ai_value_text(hkey, NULL);
                    if (name) { ai_map_put(&headers, name, clone_value(ctx, &value->as.map.values[j])); free(name); }
                }
            }
            ai_map_put(&out, "headers", headers);
        } else {
            char *name = ai_value_text(key, NULL);
            if (name) { ai_map_put(&out, name, clone_value(ctx, value)); free(name); }
        }
    }
    return out;
}

static MValue ai_providers_syscall(MellowRuntimeContext *ctx) {
    MValue list;
    int order[AI_MAX_PROVIDERS], count = 0, i, j;
    ai_providers_init();
    for (i = 0; i < AI_MAX_PROVIDERS; ++i)
        if (ai_provider_registry[i].used) order[count++] = i;
    for (i = 1; i < count; ++i) {
        int key = order[i];
        j = i - 1;
        while (j >= 0 && strcmp(ai_provider_registry[order[j]].name, ai_provider_registry[key].name) > 0) {
            order[j + 1] = order[j];
            --j;
        }
        order[j + 1] = key;
    }
    ai_list_new(&list, (size_t)count);
    for (i = 0; i < count; ++i) {
        AiProvider *provider = &ai_provider_registry[order[i]];
        MValue entry = ai_redact(ctx, &provider->config);
        MValue with_name;
        ai_map_new(&with_name, entry.as.map.len + 1);
        ai_map_put_str(&with_name, "name", provider->name);
        for (j = 0; j < (int)entry.as.map.len; ++j) {
            const MValue *key = &entry.as.map.keys[j];
            char *name = ai_value_text(key, NULL);
            if (name) { ai_map_put(&with_name, name, clone_value(ctx, &entry.as.map.values[j])); free(name); }
        }
        mvalue_free(&entry);
        ai_list_push(&list, with_name);
    }
    return list;
}

static int ai_config_error(MellowRuntimeContext *ctx, const char *message) {
    if (ctx) snprintf(ctx->syscall_error, sizeof(ctx->syscall_error), "%s", message);
    return 0;
}

static int ai_configure_syscall(MellowRuntimeContext *ctx, const MValue *args, size_t argc, MValue *out) {
    char name[64];
    AiProvider *provider;
    const MValue *config;
    MValue merged;
    size_t i;
    ai_take_name(argc > 0 ? &args[0] : NULL, "offline", name, sizeof(name));
    provider = ai_provider_alloc(name);
    if (!provider) return ai_config_error(ctx, "AI_PROVIDER_CONFIG: provider registry is full");
    config = argc > 1 ? &args[1] : NULL;
    merged = mval_none();
    ai_map_new(&merged, provider->config.as.map.len + (config && config->tag == MVAL_MAP ? config->as.map.len : 0));
    for (i = 0; i < provider->config.as.map.len; ++i) {
        char *key = ai_value_text(&provider->config.as.map.keys[i], NULL);
        if (key) { ai_map_put(&merged, key, clone_value(ctx, &provider->config.as.map.values[i])); free(key); }
    }
    if (config && config->tag == MVAL_MAP) {
        for (i = 0; i < config->as.map.len; ++i) {
            char *key = ai_value_text(&config->as.map.keys[i], NULL);
            if (key) { ai_map_set(&merged, key, clone_value(ctx, &config->as.map.values[i])); free(key); }
        }
        if (ai_map_get(config, "base_url") && !ai_map_get(config, "mode"))
            ai_map_set(&merged, "mode", ai_str("openai"));
    }
    {
        const MValue *timeout = ai_map_get(&merged, "timeout_s");
        if (timeout) {
            double seconds;
            if (!ai_number(timeout, &seconds)) {
                mvalue_free(&merged);
                return ai_config_error(ctx, "AI_PROVIDER_CONFIG: timeout_s must be a number");
            }
            if (seconds < 0.1) seconds = 0.1;
            if (seconds > 120.0) seconds = 120.0;
            ai_map_set(&merged, "timeout_s", mval_f64(seconds));
        }
    }
    {
        const MValue *mode = ai_map_get(&merged, "mode");
        char *mode_text = mode ? ai_value_text(mode, NULL) : NULL;
        if (mode_text && ai_ieq(mode_text, "openai")) {
            const MValue *base_url = ai_map_get(&merged, "base_url");
            char *url = base_url ? ai_value_text(base_url, NULL) : NULL;
            if (!url || (strncmp(url, "http://", 7) != 0 && strncmp(url, "https://", 8) != 0)) {
                free(mode_text);
                free(url);
                mvalue_free(&merged);
                return ai_config_error(ctx, "AI_PROVIDER_CONFIG: openai mode requires an http(s) base_url");
            }
            free(url);
        }
        free(mode_text);
    }
    if (!ai_map_get(&merged, "status")) ai_map_set(&merged, "status", ai_str("ready"));
    mvalue_free(&provider->config);
    provider->config = merged;
    {
        MValue result, redacted = ai_redact(ctx, &provider->config);
        ai_map_new(&result, 3);
        ai_map_put_str(&result, "provider", name);
        ai_map_put(&result, "config", redacted);
        ai_map_put_str(&result, "status", "configured");
        *out = result;
    }
    return 1;
}
