/* Standard-library fragment 3: std.string predicates, padding, and formatting. */

static int std_string_prefix_syscall(const MValue *args, size_t argc, MValue *out, int mode) {
    /* mode 0 starts_with, 1 ends_with, 2 contains. */
    char *text, *needle;
    size_t len = 0, needle_len = 0;
    int hit = 0;
    if (argc != 2) return 0;
    text = std_text(&args[0], &len);
    needle = std_text(&args[1], &needle_len);
    if (!text || !needle) { free(text); free(needle); return 0; }
    if (needle_len == 0) hit = 1;
    else if (mode == 0) hit = len >= needle_len && memcmp(text, needle, needle_len) == 0;
    else if (mode == 1) hit = len >= needle_len && memcmp(text + len - needle_len, needle, needle_len) == 0;
    else hit = std_find_sub(text, len, needle, needle_len, 0) >= 0;
    free(text); free(needle);
    *out = mval_bool(hit);
    return 1;
}

static int std_string_repeat_syscall(const MValue *args, size_t argc, MValue *out) {
    char *text;
    int64_t count = 0;
    size_t len = 0;
    AiTextBuf buf;
    if (argc != 2) return 0;
    text = std_text(&args[0], &len);
    if (!text || !ai_integer(&args[1], &count)) { free(text); return 0; }
    if (count < 0) count = 0;
    if (len && (uint64_t)count > (uint64_t)(64u * 1024u * 1024u) / len) { free(text); return 0; }
    memset(&buf, 0, sizeof(buf));
    while (count-- > 0) ai_text_append(&buf, text, len);
    *out = mval_owned_copy(buf.ptr ? buf.ptr : "", buf.len);
    free(buf.ptr);
    free(text);
    return 1;
}

static int std_string_pad_syscall(const MValue *args, size_t argc, MValue *out, int left) {
    char *text, *fill = NULL;
    size_t len = 0, fill_len = 0, pos = 0, pad, i;
    int64_t width = 0;
    int32_t cp = ' ';
    AiTextBuf buf, padding;
    if (argc < 2 || argc > 3) return 0;
    text = std_text(&args[0], &len);
    if (!text || !ai_integer(&args[1], &width)) { free(text); return 0; }
    if (argc == 3) {
        fill = std_text(&args[2], &fill_len);
        if (!fill) { free(text); return 0; }
        if (!ai_utf8_decode(fill, fill_len, &pos, &cp)) cp = ' ';
        free(fill);
    }
    if (width <= (int64_t)ai_utf8_count(text, len)) {
        *out = mval_owned_copy(text, len);
        free(text);
        return 1;
    }
    pad = (size_t)width - ai_utf8_count(text, len);
    memset(&buf, 0, sizeof(buf));
    memset(&padding, 0, sizeof(padding));
    for (i = 0; i < pad; ++i) {
        char bytes[4];
        int n = ai_utf8_encode(cp, bytes);
        ai_text_append(&padding, bytes, (size_t)(n > 0 ? n : 0));
    }
    if (left) {
        ai_text_append(&buf, padding.ptr ? padding.ptr : "", padding.len);
        ai_text_append(&buf, text, len);
    } else {
        ai_text_append(&buf, text, len);
        ai_text_append(&buf, padding.ptr ? padding.ptr : "", padding.len);
    }
    free(padding.ptr);
    *out = mval_owned_copy(buf.ptr ? buf.ptr : "", buf.len);
    free(buf.ptr);
    free(text);
    return 1;
}

static int std_string_format_syscall(const MValue *args, size_t argc, MValue *out) {
    char *tmpl;
    size_t len = 0, i = 0, arg_index = 1;
    AiTextBuf buf;
    int ok = 1;
    if (argc < 1) return 0;
    tmpl = std_text(&args[0], &len);
    if (!tmpl) return 0;
    memset(&buf, 0, sizeof(buf));
    while (i < len && ok) {
        if (tmpl[i] != '{') { ai_text_append(&buf, tmpl + i, 1); ++i; continue; }
        if (i + 1 < len && tmpl[i + 1] == '{') { ai_text_append(&buf, "{", 1); i += 2; continue; }
        {
            size_t close = i + 1, index = 0;
            int has_index = 0, digits = 1;
            while (close < len && tmpl[close] != '}') {
                char c = tmpl[close];
                if (c < '0' || c > '9') digits = 0;
                else { index = index * 10 + (size_t)(c - '0'); has_index = 1; }
                ++close;
            }
            if (close >= len || !digits) { ok = 0; break; }
            if (has_index) arg_index = index + 1;
            if (arg_index >= argc) { ok = 0; break; }
            {
                size_t value_len = 0;
                char *value = std_text(&args[arg_index], &value_len);
                if (value) { ai_text_append(&buf, value, value_len); free(value); }
            }
            arg_index++;
            i = close + 1;
        }
    }
    if (!ok) {
        free(buf.ptr);
        *out = std_own_text(tmpl, len);
        free(tmpl);
        return 1;
    }
    free(tmpl);
    *out = mval_owned_copy(buf.ptr ? buf.ptr : "", buf.len);
    free(buf.ptr);
    return 1;
}

static int std_string_chr_syscall(const MValue *args, size_t argc, MValue *out) {
    int64_t cp = 0;
    if (argc != 1 || !ai_integer(&args[0], &cp)) return 0;
    if (cp < 0 || cp > 0x10FFFF) return 0;
    *out = std_utf8_char((int32_t)cp);
    return 1;
}

static int std_string_ord_syscall(const MValue *args, size_t argc, MValue *out) {
    char *text;
    size_t len = 0, pos = 0;
    int32_t cp = 0;
    if (argc != 1) return 0;
    text = std_text(&args[0], &len);
    if (!text) return 0;
    if (!ai_utf8_decode(text, len, &pos, &cp)) cp = 0;
    free(text);
    *out = mval_i64((int64_t)cp);
    return 1;
}

static int std_string_syscall(MellowRuntimeContext *ctx, int id, const MValue *args,
                              size_t argc, MValue *out) {
    (void)ctx;
    switch (id) {
    case 200: return std_string_len_syscall(args, argc, out);
    case 201: return std_string_case_syscall(args, argc, out, 0);
    case 202: return std_string_case_syscall(args, argc, out, 1);
    case 203: return std_string_trim_syscall(args, argc, out);
    case 204: return std_string_replace_syscall(args, argc, out);
    case 205: return std_string_find_syscall(args, argc, out);
    case 206: return std_string_split_syscall(args, argc, out);
    case 207: return std_string_join_syscall(args, argc, out);
    case 208: return std_string_prefix_syscall(args, argc, out, 0);
    case 209: return std_string_prefix_syscall(args, argc, out, 1);
    case 210: return std_string_prefix_syscall(args, argc, out, 2);
    case 211: return std_string_repeat_syscall(args, argc, out);
    case 212: return std_string_pad_syscall(args, argc, out, 1);
    case 213: return std_string_pad_syscall(args, argc, out, 0);
    case 214: return std_string_format_syscall(args, argc, out);
    case 215: return std_string_chr_syscall(args, argc, out);
    case 216: return std_string_ord_syscall(args, argc, out);
    case 217: {
        char *text;
        size_t len = 0;
        if (argc != 1) return 0;
        text = std_mellow_text(&args[0], &len);
        if (!text) return 0;
        *out = mval_owned_copy(text, len);
        free(text);
        return 1;
    }
    default: return 0;
    }
}
