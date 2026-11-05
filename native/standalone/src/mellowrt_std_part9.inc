/* Standard-library fragment 9: std.time, std.assert, std.event and dispatch. */

static char *std_repr_text(const MValue *value, size_t *out_len) {
    AiTextBuf buf;
    memset(&buf, 0, sizeof(buf));
    if (!ai_render_value(&buf, value, 0, 1) || !buf.ptr) {
        free(buf.ptr);
        if (out_len) *out_len = 0;
        return NULL;
    }
    if (out_len) *out_len = buf.len;
    return buf.ptr;
}

static int std_assert_message(MellowRuntimeContext *ctx, const char *prefix, const MValue *args,
                              size_t argc, size_t message_index, const MValue *expected,
                              const MValue *actual) {
    char message[512];
    if (message_index < argc) {
        char *text = std_text(&args[message_index], NULL);
        snprintf(message, sizeof(message), "%s: %s", prefix, text ? text : "");
        free(text);
    } else if (expected && actual) {
        char *want = std_repr_text(expected, NULL);
        char *got = std_repr_text(actual, NULL);
        snprintf(message, sizeof(message), "%s: expected %s, got %s", prefix,
                 want ? want : "?", got ? got : "?");
        free(want);
        free(got);
    } else {
        snprintf(message, sizeof(message), "%s", prefix);
    }
    return std_error(ctx, message);
}

/* Wall-clock seconds since the Unix epoch. */
static double std_unix_seconds(void) {
#ifdef _WIN32
    FILETIME file_time;
    ULARGE_INTEGER ticks;
    GetSystemTimeAsFileTime(&file_time);
    ticks.LowPart = file_time.dwLowDateTime;
    ticks.HighPart = file_time.dwHighDateTime;
    return (double)ticks.QuadPart / 10000000.0 - 11644473600.0;
#else
    struct timespec ts;
    if (clock_gettime(CLOCK_REALTIME, &ts) == 0)
        return (double)ts.tv_sec + (double)ts.tv_nsec / 1000000000.0;
    return (double)time(NULL);
#endif
}

/* Monotonic seconds, matching Python's time.perf_counter(). */
static double std_monotonic_seconds(void) {
#ifdef _WIN32
    LARGE_INTEGER freq, count;
    if (QueryPerformanceFrequency(&freq) && QueryPerformanceCounter(&count))
        return (double)count.QuadPart / (double)freq.QuadPart;
    return (double)GetTickCount64() / 1000.0;
#else
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) == 0)
        return (double)ts.tv_sec + (double)ts.tv_nsec / 1000000000.0;
    return (double)clock() / (double)CLOCKS_PER_SEC;
#endif
}

static int std_misc_syscall(MellowRuntimeContext *ctx, int id, const MValue *args,
                            size_t argc, MValue *out) {
    switch (id) {
    case 320:
        if (argc != 0) return 0;
        *out = mval_f64(std_unix_seconds());
        return 1;
    case 321:
        if (argc != 0) return 0;
        *out = mval_i64((int64_t)(std_unix_seconds() * 1000.0));
        return 1;
    case 322: {
        static double start = 0.0;
        if (argc != 0) return 0;
        if (start == 0.0) start = std_monotonic_seconds();
        *out = mval_f64(std_monotonic_seconds() - start);
        return 1;
    }
    case 330:
        if (argc < 1 || argc > 2) return 0;
        if (ai_truthy(&args[0])) { *out = mval_bool(1); return 1; }
        if (argc >= 2)
            return std_assert_message(ctx, "AssertionError", args, argc, 1, NULL, NULL);
        return std_error(ctx, "AssertionError: assertion failed");
    case 331:
        if (argc < 2 || argc > 3) return 0;
        if (std_values_equal(&args[0], &args[1])) { *out = mval_bool(1); return 1; }
        return std_assert_message(ctx, "AssertionError", args, argc, 2, &args[1], &args[0]);
    case 332:
        if (argc < 2 || argc > 3) return 0;
        if (!std_values_equal(&args[0], &args[1])) { *out = mval_bool(1); return 1; }
        if (argc >= 3)
            return std_assert_message(ctx, "AssertionError", args, argc, 2, NULL, NULL);
        {
            char *left = std_repr_text(&args[0], NULL);
            char *right = std_repr_text(&args[1], NULL);
            char message[512];
            snprintf(message, sizeof(message), "AssertionError: expected %s != %s",
                     left ? left : "?", right ? right : "?");
            free(left);
            free(right);
            return std_error(ctx, message);
        }
    case 333:
        *out = mval_none();
        return 1;
    default:
        return 0;
    }
}

static int mellowrt_std_syscall(MellowRuntimeContext *ctx, int id, const MValue *args,
                                size_t argc, MValue *out_result) {
    if (id >= 200 && id <= 217) return std_string_syscall(ctx, id, args, argc, out_result);
    if (id >= 220 && id <= 241) return std_list_syscall(ctx, id, args, argc, out_result);
    if (id >= 245 && id <= 249) return std_map_syscall(ctx, id, args, argc, out_result);
    if (id >= 252 && id <= 263) return std_type_syscall(ctx, id, args, argc, out_result);
    if (id == 266) return std_json_syscall(ctx, id, args, argc, out_result);
    if (id == 267) return std_json_decode_syscall(ctx, args, argc, out_result);
    if (id >= 270 && id <= 297) return std_math_syscall(ctx, id, args, argc, out_result);
    if (id >= 320 && id <= 333) return std_misc_syscall(ctx, id, args, argc, out_result);
    if ((id >= 156 && id <= 164) || (id >= 340 && id <= 359))
        return std_game_syscall(ctx, id, args, argc, out_result);
    return mellowrt_ai_syscall(ctx, id, args, argc, out_result);
}
