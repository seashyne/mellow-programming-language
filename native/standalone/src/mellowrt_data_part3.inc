/* std.data fragment 3: open/next/info/close syscalls. */

static int std_data_batch_size(MellowRuntimeContext *ctx, const MValue *args,
                               size_t argc, long long *out) {
    long long size = 100;
    if (argc > 1) {
        MValue value = args[1];
        if (value.tag == MVAL_NONE ||
            (value.tag == MVAL_STR && value.as.str.len == 0)) {
            size = 100;
        } else if (!std_game_integer(&value, &size)) {
            return std_data_error(ctx, "data batch size must be 1-%d", DATA_MAX_BATCH_SIZE);
        }
        if (size == 0) size = 100;
    }
    if (size < 1 || size > DATA_MAX_BATCH_SIZE)
        return std_data_error(ctx, "data batch size must be 1-%d", DATA_MAX_BATCH_SIZE);
    *out = size;
    return 1;
}

static char *std_data_handle_text(const MValue *handle) {
    return std_text(handle, NULL);
}

static StdDataStream *std_data_stream_for(StdDataState *state, const MValue *handle) {
    char *text = std_data_handle_text(handle);
    StdDataStream *stream = NULL;
    if (text && !strncmp(text, "data:", 5)) stream = std_data_stream_by_id(state, atoi(text + 5));
    free(text);
    return stream;
}

static void std_data_remove(StdDataState *state, StdDataStream *stream) {
    if (!state || !stream) return;
    std_data_stream_free(stream);
}

static int std_data_open_syscall(MellowRuntimeContext *ctx, const MValue *args,
                                 size_t argc, int kind, MValue *out) {
    StdDataState *state;
    char *path, *text = NULL, *handle;
    size_t len = 0, i;
    long long batch = 100;
    StdDataStream *stream = NULL;
    if (argc < 1) return std_data_error(ctx, "data.open expects a path");
    state = std_data_state(ctx);
    if (!state) return 0;
    path = std_data_resolve_path(ctx, &args[0]);
    if (!path) return 0;
    if (!std_data_load_file(ctx, path, &text, &len)) { free(path); return 0; }
    free(path);
    if (!std_data_batch_size(ctx, args, argc, &batch)) { free(text); return 0; }
    for (i = 0; i < DATA_MAX_OPEN_STREAMS; ++i) {
        if (!state->streams[i].used) { stream = &state->streams[i]; break; }
    }
    if (!stream) {
        free(text);
        return std_data_error(ctx, "too many open data streams (max %d)", DATA_MAX_OPEN_STREAMS);
    }
    memset(stream, 0, sizeof(*stream));
    stream->used = 1;
    stream->id = ++state->next_id;
    stream->kind = kind;
    stream->batch_size = batch;
    stream->text = text;
    stream->len = len;
    handle = std_data_make_handle(stream);
    if (!handle) { std_data_remove(state, stream); return 0; }
    *out = mval_owned_copy(handle, strlen(handle));
    free(handle);
    return 1;
}

static int std_data_next_syscall(MellowRuntimeContext *ctx, const MValue *args,
                                 size_t argc, MValue *out) {
    StdDataState *state;
    StdDataStream *stream;
    MValue batch = mval_none();
    long long count = 0;
    char *handle_text;
    if (argc < 1) return std_data_error(ctx, "unknown or closed data stream: None");
    state = std_data_state(ctx);
    stream = std_data_stream_for(state, &args[0]);
    if (!stream) {
        handle_text = std_data_handle_text(&args[0]);
        std_data_error(ctx, "unknown or closed data stream: %s", handle_text ? handle_text : "");
        free(handle_text);
        return 0;
    }
    if (!ai_list_new(&batch, 8)) return 0;
    while (count < stream->batch_size) {
        MValue row = mval_none();
        int eof = 0;
        int got = stream->kind == DATA_KIND_JSONL
                      ? std_data_jsonl_row(ctx, stream, &row, &eof)
                      : std_data_csv_row(ctx, stream, &row, &eof);
        if (!got) { mvalue_free(&batch); return 0; }
        if (eof) {
            /* The Python reader closes itself when next() raises StopIteration. */
            std_data_remove(state, stream);
            break;
        }
        if (!std_data_row_size_ok(ctx, &row)) {
            mvalue_free(&row);
            mvalue_free(&batch);
            return 0;
        }
        if (!std_list_append(&batch, row)) {
            mvalue_free(&row);
            mvalue_free(&batch);
            return 0;
        }
        ++stream->rows_read;
        ++count;
    }
    *out = batch;
    return 1;
}

static int std_data_info_syscall(MellowRuntimeContext *ctx, const MValue *args,
                                 size_t argc, MValue *out) {
    StdDataState *state = std_data_state(ctx);
    StdDataStream *stream;
    MValue info = mval_none();
    char *handle_text;
    if (argc < 1 || !state) return std_data_error(ctx, "data.info expects a handle");
    handle_text = std_data_handle_text(&args[0]);
    if (!handle_text) return 0;
    stream = std_data_stream_for(state, &args[0]);
    if (!ai_map_new(&info, stream ? 5 : 2)) { free(handle_text); return 0; }
    ai_map_put(&info, "handle", ai_strn(handle_text, strlen(handle_text)));
    ai_map_put(&info, "open", mval_bool(stream ? 1 : 0));
    if (stream) {
        ai_map_put(&info, "kind", ai_str(stream->kind == DATA_KIND_JSONL ? "jsonl" : "csv"));
        ai_map_put(&info, "batch_size", mval_i64(stream->batch_size));
        ai_map_put(&info, "rows_read", mval_i64(stream->rows_read));
    }
    free(handle_text);
    *out = info;
    return 1;
}

static int std_data_close_syscall(MellowRuntimeContext *ctx, const MValue *args,
                                  size_t argc, MValue *out) {
    StdDataState *state = ctx ? (StdDataState *)ctx->data_state : NULL;
    StdDataStream *stream;
    if (argc < 1) { *out = mval_bool(0); return 1; }
    stream = std_data_stream_for(state, &args[0]);
    if (!stream) { *out = mval_bool(0); return 1; }
    std_data_remove(state, stream);
    *out = mval_bool(1);
    return 1;
}
