/* AI runtime fragment 20: the syscall dispatcher for random and std.ai. */

static MValue ai_embed_syscall(const MValue *args, size_t argc) {
    char *text = argc > 0 ? ai_value_text(&args[0], NULL) : (char *)calloc(1, 1);
    MValue list;
    size_t len;
    if (!text) return ai_error_map("AI_EMBED: out of memory");
    len = strlen(text);
    list = ai_embed_list(text, len);
    free(text);
    return list;
}

static int mellowrt_ai_syscall(MellowRuntimeContext *ctx, int32_t id,
                               const MValue *args, size_t argc, MValue *out) {
    switch (id) {
    case 100:
        if (argc > 2) return ai_config_error(ctx, "random expects 0, 1, or 2 arguments");
        if (argc == 0) {
            mrng_ensure(ctx);
            *out = mval_f64(mrng_random(&ctx->rng));
            return 1;
        }
        {
            int64_t lo = 0, hi = 0;
            if (!ai_integer(&args[0], &lo)) return ai_config_error(ctx, "random expects numbers");
            if (argc == 1) {
                hi = lo;
                lo = 0;
                if (hi < 0) return ai_config_error(ctx, "random: empty range");
            } else if (!ai_integer(&args[1], &hi)) {
                return ai_config_error(ctx, "random expects numbers");
            }
            mrng_ensure(ctx);
            *out = mval_i64(mrng_randint(&ctx->rng, lo, hi));
            return 1;
        }
    case 110: *out = ai_model_create_syscall(args, argc); return 1;
    case 111: *out = ai_train_syscall(ctx, args, argc); return 1;
    case 112: *out = ai_predict_syscall(args, argc); return 1;
    case 113: *out = ai_model_save_syscall(args, argc); return 1;
    case 114: *out = ai_model_load_syscall(args, argc); return 1;
    case 115: *out = ai_embed_syscall(args, argc); return 1;
    case 116: *out = ai_chat_syscall(ctx, args, argc); return 1;
    case 117: *out = ai_runtime_boot_syscall(ctx, args, argc); return 1;
    case 118: *out = ai_runtime_info_syscall(); return 1;
    case 119: *out = ai_session_open_syscall(args, argc); return 1;
    case 120: *out = ai_session_message_syscall(ctx, args, argc); return 1;
    case 121: *out = ai_session_history_syscall(args, argc); return 1;
    case 122: *out = ai_prompt_template_syscall(args, argc); return 1;
    case 123: *out = ai_vector_search_syscall(args, argc, 3); return 1;
    case 124: *out = ai_rag_answer_syscall(args, argc); return 1;
    case 125: *out = ai_loss_history_syscall(args, argc); return 1;
    case 126: *out = ai_model_info_syscall(args, argc); return 1;
    case 127: *out = ai_models_list_syscall(); return 1;
    case 128: *out = ai_providers_syscall(ctx); return 1;
    case 129: return ai_configure_syscall(ctx, args, argc, out);
    case 130: return ai_complete_syscall(ctx, args, argc, out);
    case 131: *out = ai_api_embed_syscall(args, argc); return 1;
    case 132: *out = ai_decide_syscall(ctx, args, argc); return 1;
    case 140: *out = ai_llm_create_syscall(args, argc); return 1;
    case 141: *out = ai_llm_train_syscall(args, argc); return 1;
    case 142: *out = ai_llm_generate_syscall(args, argc, 1); return 1;
    case 143: *out = ai_llm_tokenize_syscall(args, argc); return 1;
    case 144: *out = ai_llm_info_syscall(args, argc); return 1;
    case 145: *out = ai_llm_dataset_syscall(args, argc); return 1;
    case 146: *out = ai_llm_eval_syscall(args, argc); return 1;
    case 147: *out = ai_llm_complete_syscall(ctx, args, argc); return 1;
    case 148: *out = ai_llm_chat_syscall(ctx, args, argc); return 1;
    case 149: *out = ai_llm_models_syscall(); return 1;
    case 150: *out = ai_llm_backends_syscall(); return 1;
    case 151: *out = ai_llm_device_plan_syscall(ctx, args, argc); return 1;
    case 152: *out = ai_tensor_syscall(args, argc); return 1;
    case 153: *out = ai_llm_tensor_batch_syscall(args, argc); return 1;
    case 154: *out = ai_llm_save_syscall(args, argc); return 1;
    case 155: *out = ai_llm_load_syscall(args, argc); return 1;
    default: return 0;
    }
}
