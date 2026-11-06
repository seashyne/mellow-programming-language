/* std.data fragment 1: sandboxed paths, file loading, and stream state. */

#define DATA_MAX_OPEN_STREAMS 8
#define DATA_MAX_BATCH_SIZE 1000
#define DATA_MAX_RECORD_BYTES 1048576

#define DATA_KIND_JSONL 1
#define DATA_KIND_CSV 2

typedef struct StdDataStream {
    int used;
    int id;
    int kind;
    long long batch_size;
    long long rows_read;
    long long line_no;
    char *text;
    size_t len;
    size_t pos;
    int header_ready;
    size_t header_count;
    char **headers;
    size_t *header_lens;
} StdDataStream;

typedef struct StdDataState {
    StdDataStream streams[DATA_MAX_OPEN_STREAMS];
    int next_id;
} StdDataState;

static int std_data_error(MellowRuntimeContext *ctx, const char *format, ...) {
    va_list args;
    if (ctx) {
        va_start(args, format);
        vsnprintf(ctx->syscall_error, sizeof(ctx->syscall_error), format, args);
        va_end(args);
    }
    return 0;
}

static StdDataState *std_data_state(MellowRuntimeContext *ctx) {
    if (!ctx) return NULL;
    if (!ctx->data_state) ctx->data_state = calloc(1, sizeof(StdDataState));
    return (StdDataState *)ctx->data_state;
}

static void std_data_stream_free(StdDataStream *stream) {
    size_t i;
    if (!stream) return;
    free(stream->text);
    for (i = 0; i < stream->header_count; ++i) free(stream->headers[i]);
    free(stream->headers);
    free(stream->header_lens);
    memset(stream, 0, sizeof(*stream));
}

/* Release every open stream. Called from the runtime teardown paths. */
void mellowrt_data_release(MellowRuntimeContext *ctx) {
    StdDataState *state;
    size_t i;
    if (!ctx) return;
    state = (StdDataState *)ctx->data_state;
    if (!state) return;
    for (i = 0; i < DATA_MAX_OPEN_STREAMS; ++i) std_data_stream_free(&state->streams[i]);
    free(state);
    ctx->data_state = NULL;
}

/* Paths follow the host fs sandbox: no absolute paths, no parent traversal. */
static char *std_data_resolve_path(MellowRuntimeContext *ctx, const MValue *target) {
    char *text;
    char *clean;
    size_t len = 0, start = 0, end;
    if (!target || target->tag != MVAL_STR) {
        std_data_error(ctx, "data path expects a string");
        return NULL;
    }
    text = (char *)calloc(target->as.str.len + 2, 1);
    if (!text) return NULL;
    if (target->as.str.len) memcpy(text, target->as.str.ptr, target->as.str.len);
    len = target->as.str.len;
    while (start < len && std_space(text[start])) ++start;
    end = len;
    while (end > start && std_space(text[end - 1])) --end;
    if (end - start >= 2 && ((text[start] == '"' && text[end - 1] == '"') ||
                             (text[start] == '\'' && text[end - 1] == '\''))) {
        ++start;
        --end;
    }
    clean = (char *)calloc(end - start + 2, 1);
    if (!clean) { free(text); return NULL; }
    memcpy(clean, text + start, end - start);
    free(text);
    len = end - start;
    while (len && std_space(clean[len - 1])) clean[--len] = '\0';
    {
        size_t i;
        for (i = 0; i < len; ++i)
            if (clean[i] == '\\') clean[i] = '/';
    }
    if (!len) snprintf(clean, 2, ".");
    if (clean[0] == '/' || (len >= 2 && clean[1] == ':'))
        std_data_error(ctx, "SANDBOX: fs: absolute paths are disabled by default (run with --unsafe-fs for dev)");
    else if (!strcmp(clean, "..") || !strncmp(clean, "../", 3))
        std_data_error(ctx, "SANDBOX: fs: \"..\" traversal is blocked");
    else
        return clean;
    free(clean);
    return NULL;
}

static int std_data_load_file(MellowRuntimeContext *ctx, const char *path,
                              char **out_text, size_t *out_len) {
    FILE *handle = fopen(path, "rb");
    long size;
    char *buffer;
    size_t got;
    if (!handle) {
        std_data_error(ctx, "data: cannot open %s", path);
        return 0;
    }
    if (fseek(handle, 0, SEEK_END) != 0) { fclose(handle); std_data_error(ctx, "data: cannot read %s", path); return 0; }
    size = ftell(handle);
    if (size < 0) { fclose(handle); std_data_error(ctx, "data: cannot read %s", path); return 0; }
    rewind(handle);
    buffer = (char *)calloc((size_t)size + 1, 1);
    if (!buffer) { fclose(handle); return 0; }
    got = fread(buffer, 1, (size_t)size, handle);
    fclose(handle);
    if (got != (size_t)size) { free(buffer); std_data_error(ctx, "data: cannot read %s", path); return 0; }
    *out_text = buffer;
    *out_len = got;
    return 1;
}

static StdDataStream *std_data_stream_by_id(StdDataState *state, int id) {
    size_t i;
    if (!state) return NULL;
    for (i = 0; i < DATA_MAX_OPEN_STREAMS; ++i) {
        StdDataStream *stream = &state->streams[i];
        if (stream->used && stream->id == id) return stream;
    }
    return NULL;
}

static char *std_data_make_handle(StdDataStream *stream) {
    char *text = (char *)calloc(32, 1);
    if (!text) return NULL;
    snprintf(text, 32, "data:%d", stream->id);
    return text;
}
