/* std.data fragment 2: JSONL lines and RFC4180 CSV records. */

/* Python opens text files with universal newlines, so CRLF and lone CR both
 * count as one line break. raw_len mirrors the translated line length that the
 * record-size guard measures. */
static int std_data_next_line(StdDataStream *stream, const char **line,
                              size_t *line_len, size_t *raw_len) {
    size_t start, pos;
    if (stream->pos >= stream->len) return 0;
    start = stream->pos;
    pos = start;
    while (pos < stream->len && stream->text[pos] != '\n' && stream->text[pos] != '\r') ++pos;
    *line = stream->text + start;
    *line_len = pos - start;
    if (pos < stream->len) {
        if (stream->text[pos] == '\r' && pos + 1 < stream->len && stream->text[pos + 1] == '\n')
            stream->pos = pos + 2;
        else
            stream->pos = pos + 1;
        *raw_len = *line_len + 1;
    } else {
        stream->pos = pos;
        *raw_len = *line_len;
    }
    return 1;
}

static int std_data_strip(const char **text, size_t *len) {
    size_t start = 0, end = *len;
    while (start < end && std_space((*text)[start])) ++start;
    while (end > start && std_space((*text)[end - 1])) --end;
    *text += start;
    *len = end - start;
    return *len > 0;
}

static int std_data_jsonl_row(MellowRuntimeContext *ctx, StdDataStream *stream,
                              MValue *out, int *eof) {
    const char *line;
    size_t line_len, raw_len;
    *eof = 0;
    while (std_data_next_line(stream, &line, &line_len, &raw_len)) {
        MValue parsed = mval_none();
        ++stream->line_no;
        if (raw_len > DATA_MAX_RECORD_BYTES) {
            std_data_error(ctx, "JSONL record too large at line %lld", stream->line_no);
            return 0;
        }
        if (!std_data_strip(&line, &line_len)) continue;
        {
            MValue source = mval_none();
            source.tag = MVAL_STR;
            source.as.str.ptr = line;
            source.as.str.len = line_len;
            if (!std_json_decode_syscall(ctx, &source, 1, &parsed)) return 0;
        }
        *out = parsed;
        return 1;
    }
    *eof = 1;
    return 1;
}

typedef struct StdCsvRecord {
    MValue fields;
} StdCsvRecord;

static void std_csv_record_free(StdCsvRecord *record) {
    if (!record) return;
    mvalue_free(&record->fields);
    memset(record, 0, sizeof(*record));
}

static int std_csv_append_field(StdCsvRecord *record, AiTextBuf *buf) {
    MValue text = ai_strn(buf->ptr ? buf->ptr : "", buf->len);
    free(buf->ptr);
    memset(buf, 0, sizeof(*buf));
    return std_list_append(&record->fields, text);
}

/* One physical CSV record; an empty line yields an empty field list, which the
 * row reader skips like csv.DictReader does before its header lookup. */
static int std_data_csv_record(StdDataStream *stream, StdCsvRecord *record, int *eof) {
    AiTextBuf buf;
    int in_quotes = 0;
    memset(record, 0, sizeof(*record));
    *eof = 0;
    if (stream->pos >= stream->len) { *eof = 1; return 1; }
    if (!ai_list_new(&record->fields, 8)) return 0;
    if (stream->text[stream->pos] == '\n' || stream->text[stream->pos] == '\r') {
        if (stream->text[stream->pos] == '\r' && stream->pos + 1 < stream->len &&
            stream->text[stream->pos + 1] == '\n')
            stream->pos += 2;
        else
            ++stream->pos;
        return 1;
    }
    memset(&buf, 0, sizeof(buf));
    while (stream->pos < stream->len) {
        char c = stream->text[stream->pos];
        if (in_quotes) {
            if (c == '"') {
                if (stream->pos + 1 < stream->len && stream->text[stream->pos + 1] == '"') {
                    ai_text_append(&buf, "\"", 1);
                    stream->pos += 2;
                    continue;
                }
                in_quotes = 0;
                ++stream->pos;
                continue;
            }
            ai_text_append(&buf, &c, 1);
            ++stream->pos;
            continue;
        }
        if (c == '"' && buf.len == 0) {
            in_quotes = 1;
            ++stream->pos;
            continue;
        }
        if (c == ',') {
            if (!std_csv_append_field(record, &buf)) { std_csv_record_free(record); return 0; }
            ++stream->pos;
            continue;
        }
        if (c == '\n' || c == '\r') {
            if (c == '\r' && stream->pos + 1 < stream->len && stream->text[stream->pos + 1] == '\n')
                stream->pos += 2;
            else
                ++stream->pos;
            break;
        }
        ai_text_append(&buf, &c, 1);
        ++stream->pos;
    }
    if (!std_csv_append_field(record, &buf)) { std_csv_record_free(record); return 0; }
    return 1;
}

static int std_data_csv_headers(MellowRuntimeContext *ctx, StdDataStream *stream) {
    StdCsvRecord record;
    int eof = 0;
    size_t i;
    if (stream->header_ready) return 1;
    stream->header_ready = 1;
    if (!std_data_csv_record(stream, &record, &eof)) return 0;
    if (eof) return 1;
    stream->header_count = record.fields.as.list.len;
    stream->headers = (char **)calloc(stream->header_count, sizeof(char *));
    stream->header_lens = (size_t *)calloc(stream->header_count, sizeof(size_t));
    if (stream->header_count && (!stream->headers || !stream->header_lens)) {
        std_csv_record_free(&record);
        return std_data_error(ctx, "data: out of memory");
    }
    for (i = 0; i < stream->header_count; ++i) {
        const MValue *field = &record.fields.as.list.items[i];
        stream->headers[i] = (char *)calloc(field->as.str.len + 1, 1);
        if (!stream->headers[i]) { std_csv_record_free(&record); return 0; }
        if (field->as.str.len) memcpy(stream->headers[i], field->as.str.ptr, field->as.str.len);
        stream->header_lens[i] = field->as.str.len;
    }
    std_csv_record_free(&record);
    return 1;
}

static int std_data_csv_row(MellowRuntimeContext *ctx, StdDataStream *stream,
                            MValue *out, int *eof) {
    StdCsvRecord record;
    int done = 0;
    *eof = 0;
    if (!std_data_csv_headers(ctx, stream)) return 0;
    while (!done) {
        MValue row = mval_none();
        size_t i, field_count;
        if (!std_data_csv_record(stream, &record, eof)) return 0;
        if (*eof) return 1;
        if (record.fields.as.list.len == 0) { std_csv_record_free(&record); continue; }
        if (!ai_map_new(&row, stream->header_count + 1)) { std_csv_record_free(&record); return 0; }
        field_count = record.fields.as.list.len;
        for (i = 0; i < field_count && i < stream->header_count; ++i) {
            MValue key = ai_strn(stream->headers[i], stream->header_lens[i]);
            if (!std_map_set(&row, key, std_clone(&record.fields.as.list.items[i]))) {
                std_csv_record_free(&record);
                mvalue_free(&row);
                return 0;
            }
        }
        for (i = field_count; i < stream->header_count; ++i) {
            MValue key = ai_strn(stream->headers[i], stream->header_lens[i]);
            if (!std_map_set(&row, key, mval_none())) {
                std_csv_record_free(&record);
                mvalue_free(&row);
                return 0;
            }
        }
        if (field_count > stream->header_count) {
            MValue extras = mval_none();
            if (!ai_list_new(&extras, field_count - stream->header_count)) {
                std_csv_record_free(&record);
                mvalue_free(&row);
                return 0;
            }
            for (i = stream->header_count; i < field_count; ++i)
                std_list_append(&extras, std_clone(&record.fields.as.list.items[i]));
            if (!std_map_set(&row, mval_none(), extras)) {
                std_csv_record_free(&record);
                mvalue_free(&row);
                return 0;
            }
        }
        std_csv_record_free(&record);
        *out = row;
        done = 1;
    }
    return 1;
}

/* Python measures the encoded row after every read, not at open time. */
static int std_data_row_size_ok(MellowRuntimeContext *ctx, const MValue *row) {
    AiTextBuf buf;
    int encoded;
    size_t size;
    memset(&buf, 0, sizeof(buf));
    encoded = std_json_encode_value(&buf, row, 0);
    size = buf.len;
    free(buf.ptr);
    if (!encoded) return std_data_error(ctx, "data: unsupported row value");
    if (size > DATA_MAX_RECORD_BYTES)
        return std_data_error(ctx, "data record exceeds configured byte limit");
    return 1;
}
