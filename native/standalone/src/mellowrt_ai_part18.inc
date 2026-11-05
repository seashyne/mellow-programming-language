/* AI runtime fragment 18: backend capability reports and device placement. */

static int ai_cpu_workers(void) {
#ifdef _WIN32
    SYSTEM_INFO info;
    GetSystemInfo(&info);
    return info.dwNumberOfProcessors > 0 ? (int)info.dwNumberOfProcessors : 1;
#else
    long count = sysconf(_SC_NPROCESSORS_ONLN);
    return count > 0 ? (int)count : 1;
#endif
}

/* The standalone runtime never loads torch; report the same shape Python does. */
static MValue ai_torch_status_value(void) {
    MValue status, devices, cpu;
    ai_map_new(&status, 4);
    ai_map_put(&status, "available", mval_bool(0));
    ai_map_put_str(&status, "backend", "transformer-torch");
    ai_map_put_str(&status, "reason", "torch unavailable: ModuleNotFoundError");
    ai_map_new(&cpu, 4);
    ai_map_put_str(&cpu, "id", "cpu");
    ai_map_put_str(&cpu, "type", "cpu");
    ai_map_put(&cpu, "available", mval_bool(1));
    ai_map_put(&cpu, "workers", mval_i64(ai_cpu_workers()));
    ai_list_new(&devices, 1);
    ai_list_push(&devices, cpu);
    ai_map_put(&status, "devices", devices);
    return status;
}

static MValue ai_kernels_value(void) {
    MValue kernels;
    int i;
    static const char *kernel_names[] = { "matmul", "softmax", "gelu", "layer_norm", "batch" };
    ai_list_new(&kernels, 5);
    for (i = 0; i < 5; ++i) ai_list_push(&kernels, ai_str(kernel_names[i]));
    return kernels;
}

static MValue ai_native_caps_value(void) {
    MValue caps, devices;
    ai_map_new(&caps, 5);
    ai_map_put(&caps, "available", mval_bool(0));
    ai_map_put_str(&caps, "backend", "mellow-native-c");
    ai_map_put(&caps, "kernels", ai_kernels_value());
    ai_list_new(&devices, 1);
    ai_list_push(&devices, ai_str("cpu"));
    ai_map_put(&caps, "devices", devices);
    ai_map_put_str(&caps, "dtype", "float64");
    return caps;
}

static MValue ai_llm_backends_syscall(void) {
    MValue list, tiny, native, torch, detail, planned_kernels, planned_devices;
    MValue devices;
    static const char *planned[] = { "matmul", "softmax", "layer_norm", "gelu", "attention", "adamw" };
    int i;
    ai_map_new(&tiny, 6);
    ai_map_put_str(&tiny, "name", "tiny-causal-char-lm");
    ai_map_put(&tiny, "available", mval_bool(1));
    ai_map_put_str(&tiny, "kind", "statistical-char-lm");
    ai_list_new(&devices, 1);
    ai_list_push(&devices, ai_str("cpu"));
    ai_map_put(&tiny, "devices", devices);
    ai_map_put(&tiny, "training", mval_bool(1));
    ai_map_put(&tiny, "production", mval_bool(0));

    ai_map_new(&native, 8);
    ai_map_put_str(&native, "name", "mellow-native");
    ai_map_put(&native, "available", mval_bool(1));
    ai_map_put_str(&native, "kind", "mellow-owned-transformer-runtime");
    ai_list_new(&devices, 1);
    ai_list_push(&devices, ai_str("cpu"));
    ai_map_put(&native, "devices", devices);
    ai_map_put(&native, "training", mval_bool(0));
    ai_map_put(&native, "inference", mval_bool(1));
    ai_map_put(&native, "production", mval_bool(0));
    ai_map_put_str(&native, "status", "kernels-ready");
    ai_map_new(&detail, 8);
    ai_map_put_str(&detail, "runtime", "mellow");
    ai_map_put(&detail, "native_extension", mval_bool(0));
    ai_map_put(&detail, "cpu_workers", mval_i64(ai_cpu_workers()));
    ai_map_put(&detail, "kernels", ai_kernels_value());
    ai_map_new(&planned_kernels, 6);
    for (i = 0; i < 6; ++i) ai_list_push(&planned_kernels, ai_str(planned[i]));
    ai_map_put(&detail, "planned_kernels", planned_kernels);
    ai_map_new(&planned_devices, 4);
    ai_list_push(&planned_devices, ai_str("cpu"));
    ai_list_push(&planned_devices, ai_str("cuda"));
    ai_list_push(&planned_devices, ai_str("vulkan"));
    ai_list_push(&planned_devices, ai_str("metal"));
    ai_map_put(&detail, "planned_devices", planned_devices);
    ai_map_put(&detail, "capabilities", ai_native_caps_value());
    ai_map_put(&native, "detail", detail);

    ai_map_new(&torch, 6);
    ai_map_put_str(&torch, "name", "transformer-torch");
    ai_map_put(&torch, "available", mval_bool(0));
    ai_map_put_str(&torch, "kind", "gpt-transformer");
    ai_list_new(&devices, 1);
    ai_list_push(&devices, ai_str("cpu"));
    ai_map_put(&torch, "devices", devices);
    ai_map_put(&torch, "training", mval_bool(0));
    ai_map_put(&torch, "production", mval_bool(1));
    ai_map_put(&torch, "detail", ai_torch_status_value());

    ai_list_new(&list, 3);
    ai_list_push(&list, tiny);
    ai_list_push(&list, native);
    ai_list_push(&list, torch);
    return list;
}

static int ai_device_list_has(const MValue *requested, const char *wanted) {
    size_t i;
    if (!requested || requested->tag != MVAL_LIST) return 0;
    for (i = 0; i < requested->as.list.len; ++i) {
        char *text = ai_value_text(&requested->as.list.items[i], NULL);
        int hit = text && strcmp(text, wanted) == 0;
        free(text);
        if (hit) return 1;
    }
    return 0;
}

/* kind: 0 plain placement, 1 enumerated device, 2 fallback device. */
static MValue ai_cpu_device(int workers, int kind) {
    MValue device;
    ai_map_new(&device, kind == 2 ? 4 : (kind == 1 ? 4 : 3));
    ai_map_put_str(&device, "id", "cpu");
    ai_map_put_str(&device, "type", "cpu");
    if (kind == 1) ai_map_put(&device, "available", mval_bool(1));
    ai_map_put(&device, "workers", mval_i64(workers));
    if (kind == 2) ai_map_put(&device, "fallback", mval_bool(1));
    return device;
}

static MValue ai_llm_device_plan_syscall(MellowRuntimeContext *ctx, const MValue *args, size_t argc) {
    const MValue *config = argc > 0 && args[0].tag == MVAL_MAP ? &args[0] : NULL;
    char backend_text[64] = "transformer-torch";
    MValue plan, selected, torch;
    const MValue *requested;
    int workers, use_native, kind = 0;
    if (config) {
        const MValue *backend_value = ai_map_get(config, "backend");
        if (backend_value) ai_take_name(backend_value, "transformer-torch", backend_text, sizeof(backend_text));
    }
    use_native = strcmp(backend_text, "mellow-native") == 0;
    workers = (int)ai_int_or(config ? ai_map_get(config, "cpu_workers") : NULL, ai_cpu_workers());
    if (workers < 1) workers = 1;
    requested = config ? ai_map_get(config, "devices") : NULL;
    if (use_native) {
        kind = 0;
    } else if (!requested) {
        kind = 0;
    } else if (requested->tag == MVAL_LIST) {
        kind = ai_device_list_has(requested, "cpu") ? 1 : 2;
    } else {
        char *text = ai_value_text(requested, NULL);
        if (text && strcmp(text, "auto") == 0) kind = 0;
        else if (text && strcmp(text, "cpu") == 0) kind = 0;
        else kind = 2;
        free(text);
    }
    ai_map_new(&plan, 8);
    if (requested) ai_map_put(&plan, "requested", clone_value(ctx, requested));
    else ai_map_put_str(&plan, "requested", use_native ? "cpu" : "auto");
    ai_list_new(&selected, 1);
    ai_list_push(&selected, ai_cpu_device(workers, kind));
    ai_map_put(&plan, "selected", selected);
    ai_map_put(&plan, "strategy", ai_str(workers > 1 ? "cpu-threaded" : "single"));
    torch = ai_torch_status_value();
    ai_map_put(&plan, "torch", torch);
    if (use_native) ai_map_put(&plan, "native", ai_native_caps_value());
    ai_map_put_str(&plan, "backend", backend_text);
    ai_map_put(&plan, "multi_device", mval_bool(0));
    if (use_native) {
        ai_map_put_str(&plan, "status", "kernels-ready");
        ai_map_put_str(&plan, "next", "add attention and optimizer kernels before enabling transformer training");
    } else {
        ai_map_put_str(&plan, "status", "requires-llm-extra");
        ai_map_put_str(&plan, "install", "python -m pip install -e .[llm]");
    }
    return plan;
}
