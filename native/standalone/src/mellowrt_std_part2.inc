/* Standard-library fragment 2: std.string. */

static MValue std_utf8_char(int32_t cp) {
    char bytes[4];
    int n = ai_utf8_encode(cp, bytes);
    return mval_owned_copy(bytes, (size_t)(n > 0 ? n : 0));
}

static int std_string_len_syscall(const MValue *args, size_t argc, MValue *out) {
    char *text;
    size_t len = 0, count = 0, pos = 0;
    int32_t cp;
    if (argc != 1) return 0;
    text = std_text(&args[0], &len);
    if (!text) return 0;
    while (pos < len && ai_utf8_decode(text, len, &pos, &cp)) ++count;
    free(text);
    *out = mval_i64((int64_t)count);
    return 1;
}

static int std_string_case_syscall(const MValue *args, size_t argc, MValue *out, int upper) {
    char *text;
    size_t len = 0, i;
    if (argc != 1) return 0;
    text = std_text(&args[0], &len);
    if (!text) return 0;
    for (i = 0; i < len; ++i) {
        unsigned char c = (unsigned char)text[i];
        if (upper && c >= 'a' && c <= 'z') text[i] = (char)(c - 32);
        else if (!upper && c >= 'A' && c <= 'Z') text[i] = (char)(c + 32);
    }
    *out = mval_owned_copy(text, len);
    free(text);
    return 1;
}

static int std_string_trim_syscall(const MValue *args, size_t argc, MValue *out) {
    char *text;
    size_t len = 0, start = 0;
    if (argc != 1) return 0;
    text = std_text(&args[0], &len);
    if (!text) return 0;
    while (start < len && std_space(text[start])) ++start;
    while (len > start && std_space(text[len - 1])) --len;
    *out = mval_owned_copy(text + start, len - start);
    free(text);
    return 1;
}

static int std_string_replace_syscall(const MValue *args, size_t argc, MValue *out) {
    char *text, *old_text, *new_text;
    size_t len = 0, old_len = 0, new_len = 0, pos = 0;
    AiTextBuf buf;
    if (argc != 3) return 0;
    text = std_text(&args[0], &len);
    old_text = std_text(&args[1], &old_len);
    new_text = std_text(&args[2], &new_len);
    if (!text || !old_text || !new_text) {
        free(text); free(old_text); free(new_text);
        return 0;
    }
    memset(&buf, 0, sizeof(buf));
    while (pos < len) {
        long hit = std_find_sub(text, len, old_text, old_len, pos);
        if (hit < 0 || old_len == 0) break;
        ai_text_append(&buf, text + pos, (size_t)hit - pos);
        ai_text_append(&buf, new_text, new_len);
        pos = (size_t)hit + old_len;
    }
    if (old_len == 0) {
        /* Python inserts the replacement at every boundary, including the ends. */
        size_t index = 0, next = 0;
        int32_t cp;
        ai_text_append(&buf, new_text, new_len);
        while (index < len) {
            next = index;
            ai_utf8_decode(text, len, &next, &cp);
            ai_text_append(&buf, text + index, next - index);
            ai_text_append(&buf, new_text, new_len);
            index = next;
        }
    } else {
        ai_text_append(&buf, text + pos, len - pos);
    }
    *out = mval_owned_copy(buf.ptr ? buf.ptr : "", buf.len);
    free(buf.ptr);
    free(text); free(old_text); free(new_text);
    return 1;
}

static int std_string_find_syscall(const MValue *args, size_t argc, MValue *out) {
    char *text, *needle;
    size_t len = 0, needle_len = 0;
    long hit;
    if (argc != 2) return 0;
    text = std_text(&args[0], &len);
    needle = std_text(&args[1], &needle_len);
    if (!text || !needle) { free(text); free(needle); return 0; }
    hit = std_find_sub(text, len, needle, needle_len, 0);
    free(text); free(needle);
    *out = mval_i64((int64_t)hit);
    return 1;
}

static int std_string_split_syscall(const MValue *args, size_t argc, MValue *out) {
    char *text, *sep = NULL;
    size_t len = 0, sep_len = 0, start = 0, i = 0;
    MValue list;
    if (argc < 1 || argc > 2) return 0;
    text = std_text(&args[0], &len);
    if (!text) return 0;
    if (argc == 2 && args[1].tag != MVAL_NONE) {
        sep = std_text(&args[1], &sep_len);
        if (!sep) { free(text); return 0; }
        if (sep_len == 0) { free(text); free(sep); return 0; }
    }
    if (!ai_list_new(&list, 8)) { free(text); free(sep); return 0; }
    if (sep) {
        while (1) {
            long hit = std_find_sub(text, len, sep, sep_len, start);
            if (hit < 0) break;
            std_list_append(&list, mval_owned_copy(text + start, (size_t)hit - start));
            start = (size_t)hit + sep_len;
        }
        std_list_append(&list, mval_owned_copy(text + start, len - start));
    } else {
        while (i < len) {
            while (i < len && std_space(text[i])) ++i;
            start = i;
            while (i < len && !std_space(text[i])) ++i;
            if (i > start) std_list_append(&list, mval_owned_copy(text + start, i - start));
        }
    }
    *out = list;
    free(text); free(sep);
    return 1;
}

static int std_string_join_syscall(const MValue *args, size_t argc, MValue *out) {
    const MValue *list;
    char *sep = NULL;
    size_t sep_len = 0, i;
    AiTextBuf buf;
    if (argc < 1 || argc > 2 || args[0].tag != MVAL_LIST) return 0;
    list = &args[0];
    if (argc == 2) {
        sep = std_text(&args[1], &sep_len);
        if (!sep) return 0;
    }
    memset(&buf, 0, sizeof(buf));
    for (i = 0; i < list->as.list.len; ++i) {
        size_t item_len = 0;
        char *item = std_text(&list->as.list.items[i], &item_len);
        if (!item) continue;
        if (i && sep_len) ai_text_append(&buf, sep, sep_len);
        ai_text_append(&buf, item, item_len);
        free(item);
    }
    free(sep);
    *out = mval_owned_copy(buf.ptr ? buf.ptr : "", buf.len);
    free(buf.ptr);
    return 1;
}

