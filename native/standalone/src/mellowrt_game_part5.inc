/* Game runtime fragment 5: AI decision helpers.
 *
 * utility_choose picks the highest scored option, bt_tick walks a behaviour
 * tree, and fsm_tick dispatches the current state. Behaviour-tree leaves call
 * back into the runtime by syscall name, resolved through the same builtin
 * table the compiler uses for static calls.
 */

static int std_game_utility_syscall(MellowRuntimeContext *ctx, const MValue *args,
                                    size_t argc, MValue *out) {
    const MValue *options, *best = NULL;
    double best_score = 0.0;
    size_t i;
    if (argc < 1) { *out = mval_none(); return 1; }
    options = &args[0];
    if (options->tag != MVAL_LIST)
        return std_error(ctx, "utility_choose expects list");
    for (i = 0; i < options->as.list.len; ++i) {
        const MValue *item = &options->as.list.items[i];
        const MValue *score_value;
        double score = 0.0;
        if (item->tag != MVAL_MAP) continue;
        score_value = ai_map_get(item, "score");
        if (!score_value || !std_game_number(score_value, &score)) score = 0.0;
        if (!best || score > best_score) {
            best = item;
            best_score = score;
        }
    }
    if (!best) {
        *out = mval_none();
        return 1;
    }
    {
        const MValue *value = ai_map_get(best, "value");
        *out = value ? std_clone(value) : mval_none();
    }
    return 1;
}

/* Call a runtime syscall chosen by name. A missing args value means zero
 * arguments; a non-list value becomes the single argument, matching the
 * Python VM's [value] fallback. */
static int std_game_dynamic_argv(MellowRuntimeContext *ctx, const char *name,
                                 size_t name_len, const MValue *argv, size_t argc,
                                 MValue *out) {
    int id = mellowrt_builtin_lookup(name, name_len);
    if (!id) {
        if (ctx)
            snprintf(ctx->syscall_error, sizeof(ctx->syscall_error),
                     "SANDBOX: syscall not allowed: %.*s", (int)name_len, name ? name : "");
        return 0;
    }
    return mellowrt_default_syscall(ctx, id, argv, argc, out);
}

static int std_game_dynamic_syscall(MellowRuntimeContext *ctx, const char *name,
                                    size_t name_len, const MValue *args_value,
                                    MValue *out) {
    if (!args_value) return std_game_dynamic_argv(ctx, name, name_len, NULL, 0, out);
    if (args_value->tag == MVAL_LIST)
        return std_game_dynamic_argv(ctx, name, name_len, args_value->as.list.items,
                                     args_value->as.list.len, out);
    return std_game_dynamic_argv(ctx, name, name_len, args_value, 1, out);
}

static int std_game_text_is(const char *text, size_t len, const char *wanted) {
    size_t wanted_len = strlen(wanted);
    return len == wanted_len && (!len || memcmp(text, wanted, len) == 0);
}

static int std_game_status_is(const MValue *value, const char *wanted) {
    return value->tag == MVAL_STR && value->as.str.ptr &&
           std_game_text_is(value->as.str.ptr, value->as.str.len, wanted);
}

static const char *std_game_bt_tick_status(MellowRuntimeContext *ctx,
                                           const MValue *node, int *ok) {
    const MValue *type_value, *children, *sys_value, *args_value;
    char *type_text = NULL;
    size_t type_len = 0;
    const char *result = "fail";
    *ok = 1;
    if (!node || node->tag == MVAL_NONE) return "fail";
    if (node->tag != MVAL_MAP) {
        std_error(ctx, "bt_tick expects node map");
        *ok = 0;
        return "fail";
    }
    type_value = ai_map_get(node, "type");
    if (type_value)
        type_text = std_text(type_value, &type_len);
    else
        type_text = (char *)calloc(1, 1);
    if (!type_text) { *ok = 0; return "fail"; }

    if (std_game_text_is(type_text, type_len, "selector")) {
        children = ai_map_get(node, "children");
        if (children && children->tag == MVAL_LIST) {
            size_t i;
            for (i = 0; i < children->as.list.len; ++i) {
                const char *status = std_game_bt_tick_status(ctx, &children->as.list.items[i], ok);
                if (!*ok) break;
                if (strcmp(status, "success") == 0 || strcmp(status, "running") == 0) {
                    result = status;
                    break;
                }
            }
        }
    } else if (std_game_text_is(type_text, type_len, "sequence")) {
        children = ai_map_get(node, "children");
        result = "success";
        if (children && children->tag == MVAL_LIST) {
            size_t i;
            for (i = 0; i < children->as.list.len; ++i) {
                const char *status = std_game_bt_tick_status(ctx, &children->as.list.items[i], ok);
                if (!*ok) break;
                if (strcmp(status, "fail") == 0 || strcmp(status, "running") == 0) {
                    result = status;
                    break;
                }
            }
        }
    } else if (std_game_text_is(type_text, type_len, "condition") ||
               std_game_text_is(type_text, type_len, "action")) {
        MValue called = mval_none();
        char *sys_text = NULL;
        size_t sys_len = 0;
        int is_condition = std_game_text_is(type_text, type_len, "condition");
        sys_value = ai_map_get(node, "sys");
        sys_text = sys_value ? std_text(sys_value, &sys_len) : (char *)calloc(1, 1);
        args_value = ai_map_get(node, "args");
        if (!sys_text) { *ok = 0; free(type_text); return "fail"; }
        if (!std_game_dynamic_syscall(ctx, sys_text, sys_len, args_value, &called)) {
            free(sys_text);
            free(type_text);
            mvalue_free(&called);
            *ok = 0;
            return "fail";
        }
        free(sys_text);
        if (is_condition) {
            result = ai_truthy(&called) ? "success" : "fail";
        } else if (std_game_status_is(&called, "success")) {
            result = "success";
        } else if (std_game_status_is(&called, "fail")) {
            result = "fail";
        } else if (std_game_status_is(&called, "running")) {
            result = "running";
        } else {
            result = ai_truthy(&called) ? "success" : "fail";
        }
        mvalue_free(&called);
    }
    free(type_text);
    return result;
}

static int std_game_bt_syscall(MellowRuntimeContext *ctx, const MValue *args,
                               size_t argc, MValue *out) {
    int ok = 1;
    const char *status;
    if (argc < 1) {
        *out = ai_str("fail");
        return 1;
    }
    status = std_game_bt_tick_status(ctx, &args[0], &ok);
    if (!ok) return 0;
    *out = ai_str(status);
    return 1;
}

static int std_game_fsm_syscall(MellowRuntimeContext *ctx, const MValue *args,
                                size_t argc, MValue *out) {
    const MValue *fsm, *state_value, *table, *tick = NULL;
    char *state_text = NULL;
    size_t state_len = 0, i;
    if (argc < 1 || args[0].tag != MVAL_MAP)
        return std_error(ctx, "fsm_tick expects fsm map");
    fsm = &args[0];
    state_value = ai_map_get(fsm, "state");
    state_text = state_value ? std_text(state_value, &state_len) : (char *)calloc(1, 1);
    if (!state_text) return 0;
    table = ai_map_get(fsm, "on_tick");
    if (table && table->tag == MVAL_MAP) {
        for (i = 0; i < table->as.map.len; ++i) {
            const MValue *key = &table->as.map.keys[i];
            if (key->tag == MVAL_STR && key->as.str.len == state_len &&
                (!state_len || (key->as.str.ptr &&
                                memcmp(key->as.str.ptr, state_text, state_len) == 0))) {
                tick = &table->as.map.values[i];
                break;
            }
        }
    }
    if (tick) {
        char *sys_text = std_text(tick, NULL);
        size_t sys_len = sys_text ? strlen(sys_text) : 0;
        if (sys_len) {
            MValue called = mval_none();
            MValue one;
            if (argc >= 2 && args[1].tag == MVAL_NONE) {
                if (!std_game_dynamic_argv(ctx, sys_text, sys_len, NULL, 0, &called)) {
                    free(sys_text); free(state_text); mvalue_free(&called);
                    return 0;
                }
            } else {
                if (argc >= 2)
                    one = args[1];
                else if (!ai_map_new(&one, 0))
                    { free(sys_text); free(state_text); return 0; }
                if (!std_game_dynamic_argv(ctx, sys_text, sys_len, &one, 1, &called)) {
                    free(sys_text); free(state_text); mvalue_free(&called);
                    return 0;
                }
            }
            free(sys_text);
            free(state_text);
            *out = called;
            return 1;
        }
        free(sys_text);
    }
    free(state_text);
    *out = mval_none();
    return 1;
}
