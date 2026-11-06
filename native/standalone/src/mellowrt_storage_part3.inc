static MValue json_parse_object(SJson *p, int depth) {
    SVec keys, values;
    MValue out = mval_none();
    keys.items = NULL;
    keys.len = keys.cap = 0;
    values.items = NULL;
    values.len = values.cap = 0;
    p->pos++;
    json_skip_space(p);
    if (p->pos < p->len && p->text[p->pos] == '}') {
        p->pos++;
        return empty_map();
    }
    while (p->pos < p->len && !p->failed) {
        MValue key;
        MValue value;
        json_skip_space(p);
        if (p->pos >= p->len || p->text[p->pos] != '"') { p->failed = 1; break; }
        key = json_parse_string(p);
        if (p->failed) break;
        json_skip_space(p);
        if (p->pos >= p->len || p->text[p->pos] != ':') { p->failed = 1; break; }
        p->pos++;
        json_skip_space(p);
        value = json_parse_value(p, depth + 1);
        if (p->failed) { mvalue_free(&key); break; }
        if (!svec_push(&keys, key) || !svec_push(&values, value)) {
            mvalue_free(&key);
            mvalue_free(&value);
            p->failed = 1;
            break;
        }
        json_skip_space(p);
        if (p->pos < p->len && p->text[p->pos] == ',') { p->pos++; continue; }
        if (p->pos < p->len && p->text[p->pos] == '}') { p->pos++; break; }
        p->failed = 1;
    }
    if (p->failed) {
        size_t i;
        for (i = 0; i < keys.len; ++i) { mvalue_free(&keys.items[i]); mvalue_free(&values.items[i]); }
        free(keys.items);
        free(values.items);
        return mval_none();
    }
    if (!keys.items || !values.items) return empty_map();
    out.tag = MVAL_MAP;
    out.as.map.keys = keys.items;
    out.as.map.values = values.items;
    out.as.map.len = out.as.map.cap = keys.len;
    return out;
}

static MValue json_parse_value(SJson *p, int depth) {
    char c;
    json_skip_space(p);
    if (depth > STOR_MAX_DEPTH || p->pos >= p->len) { p->failed = 1; return mval_none(); }
    c = p->text[p->pos];
    if (c == '{') return json_parse_object(p, depth);
    if (c == '[') return json_parse_array(p, depth);
    if (c == '"') return json_parse_string(p);
    if (c == 't' && p->pos + 4 <= p->len && memcmp(p->text + p->pos, "true", 4) == 0) {
        p->pos += 4;
        return mval_bool(1);
    }
    if (c == 'f' && p->pos + 5 <= p->len && memcmp(p->text + p->pos, "false", 5) == 0) {
        p->pos += 5;
        return mval_bool(0);
    }
    if (c == 'n' && p->pos + 4 <= p->len && memcmp(p->text + p->pos, "null", 4) == 0) {
        p->pos += 4;
        return mval_none();
    }
    if (c == '-' || (c >= '0' && c <= '9')) return json_parse_number(p);
    p->failed = 1;
    return mval_none();
}

static MValue parse_document(const char *text, size_t len, int *ok) {
    SJson parser;
    MValue value;
    parser.text = text;
    parser.pos = 0;
    parser.len = len;
    parser.failed = 0;
    value = json_parse_value(&parser, 0);
    if (!parser.failed) json_skip_space(&parser);
    *ok = !parser.failed && parser.pos == parser.len;
    if (!*ok) mvalue_free(&value);
    return value;
}

/* ── syscall implementations ───────────────────────────────────── */

static MValue arg_at(const MValue *args, size_t argc, size_t index) {
    if (args && index < argc) return args[index];
    return mval_none();
}

static const MValue *arg_ptr(const MValue *args, size_t argc, size_t index) {
    return (args && index < argc) ? &args[index] : NULL;
}

static int storage_move(char *dir, size_t cap, const MValue *target, char *error, size_t error_cap) {
    char clean[STOR_PATH_MAX];
    path_clean(target, clean, sizeof clean);
    /* "" and "." both mean "the current working directory", as in the Python VM. */
    if (!*clean || strcmp(clean, ".") == 0) {
        snprintf(dir, cap, ".");
        return 1;
    }
    if (path_is_absolute(clean)) {
        set_error(error, error_cap, ERR_DIR_ABSOLUTE);
        return 0;
    }
    if (path_is_unsafe(clean)) {
        set_error(error, error_cap, ERR_DIR_TRAVERSAL);
        return 0;
    }
    snprintf(dir, cap, "%s", clean);
    return 1;
}

/* Mirrors _save_json: the base is created on demand, sub-folders are not. */
static int storage_write_slot(const char *base, const MValue *key, const MValue *value,
                             char *error, size_t error_cap) {
    char path[STOR_PATH_MAX];
    char parent[STOR_PATH_MAX];
    Sbuf document;
    int moved;
    if (!slot_path(path, sizeof path, base, key)) {
        set_error(error, error_cap, ERR_STORAGE_TRAVERSAL);
        return 0;
    }
    sbuf_init(&document);
    json_encode(&document, value, 0);
    if (!document.ok || !document.buf) {
        free(document.buf);
        set_error(error, error_cap, ERR_NOT_JSON);
        return 0;
    }
    if (!file_exists(base)) make_dirs(base);
    parent_dir(path, parent, sizeof parent);
    if (*parent && strcmp(parent, base) != 0) {
        if (!file_exists(parent)) {
            free(document.buf);
            set_errorf(error, error_cap, "RUNTIME: Folder not found: %s (create it first)", parent);
            return 0;
        }
    }
    moved = write_atomic(path, document.buf, document.len);
    free(document.buf);
    if (!moved) set_error(error, error_cap, "RUNTIME: could not write the save document");
    return moved;
}

static int storage_read_slot(const char *base, const MValue *key, MValue *out_value,
                            char *error, size_t error_cap) {
    char path[STOR_PATH_MAX];
    char *text = NULL;
    size_t len = 0;
    int ok = 0;
    MValue value;
    if (!slot_path(path, sizeof path, base, key)) {
        set_error(error, error_cap, ERR_STORAGE_TRAVERSAL);
        return 0;
    }
    *out_value = mval_none();
    if (!file_exists(path)) return 1;
    if (!read_whole_file(path, &text, &len)) {
        set_error(error, error_cap, "RUNTIME: could not read the save document");
        return 0;
    }
    value = parse_document(text, len, &ok);
    free(text);
    if (!ok) {
        set_error(error, error_cap, ERR_CORRUPT);
        return 0;
    }
    *out_value = value;
    return 1;
}

static int storage_read_text(const char *path, MValue *out_result, char *error, size_t error_cap) {
    char *text = NULL;
    size_t len = 0;
    if (!read_whole_file(path, &text, &len)) {
        set_error(error, error_cap, ERR_READ);
        return 0;
    }
    *out_result = owned_copy(text, len);
    free(text);
    return 1;
}

static int storage_write_text(const char *path, const MValue *data, int append,
                             int make_parents, char *error, size_t error_cap) {
    char parent[STOR_PATH_MAX];
    const char *text = NULL;
    size_t len = 0;
    char scratch[64];
    int wrote;

    if (data) {
        if (data->tag == MVAL_STR) {
            text = data->as.str.ptr;
            len = data->as.str.len;
        } else if (data->tag == MVAL_I64 || data->tag == MVAL_F64) {
            Sbuf number;
            sbuf_init(&number);
            json_encode_number(&number, data);
            snprintf(scratch, sizeof scratch, "%s", number.buf ? number.buf : "");
            free(number.buf);
            text = scratch;
            len = strlen(scratch);
        } else if (data->tag == MVAL_BOOL) {
            text = data->as.boolean ? "true" : "false";
            len = strlen(text);
        } else if (data->tag != MVAL_NONE) {
            Sbuf document;
            sbuf_init(&document);
            json_encode(&document, data, 0);
            if (!document.ok) {
                free(document.buf);
                set_error(error, error_cap, ERR_NOT_JSON);
                return 0;
            }
            wrote = write_whole_file(path, document.buf ? document.buf : "", document.len, append);
            free(document.buf);
            if (!wrote) set_error(error, error_cap, ERR_WRITE);
            return wrote;
        }
    }
    if (!text) { text = ""; len = 0; }
    if (make_parents) {
        parent_dir(path, parent, sizeof parent);
        if (*parent && !file_exists(parent)) make_dirs(parent);
    }
    wrote = write_whole_file(path, text, len, append);
    if (!wrote) set_error(error, error_cap, ERR_WRITE);
    return wrote;
}

/* fs_* walks the host tree like _fs_resolve does in dev mode: no traversal, no absolutes. */
static int fs_host_path(const MValue *target, char *out, size_t cap, char *error, size_t error_cap) {
    char clean[STOR_PATH_MAX];
    path_clean(target, clean, sizeof clean);
    if (!*clean) snprintf(clean, sizeof clean, ".");
    if (path_is_absolute(clean)) {
        set_error(error, error_cap, ERR_FS_ABSOLUTE);
        return 0;
    }
    if (path_is_unsafe(clean)) {
        set_error(error, error_cap, ERR_FS_TRAVERSAL);
        return 0;
    }
    snprintf(out, cap, "%s", clean);
    return 1;
}

int mellowrt_storage_syscall(int32_t id, const MValue *args, size_t argc, MValue *out_result,
                             char *storage_dir, size_t storage_dir_cap,
                             char *error, size_t error_cap) {
    char base[STOR_PATH_MAX];
    char path[STOR_PATH_MAX];
    char clean[STOR_PATH_MAX];
    MValue none = mval_none();

    if (error && error_cap) error[0] = '\0';
    if (!out_result) return 0;
    *out_result = none;
    if (storage_dir && *storage_dir) path_use_separators(storage_dir, base, sizeof base);
    else snprintf(base, sizeof base, "%s", STOR_DEFAULT_BASE);

    switch (id) {
    case 61: /* storage_dir */
        if (argc > 1 || !storage_dir || !storage_dir_cap) return 0;
        if (!storage_move(storage_dir, storage_dir_cap, arg_ptr(args, argc, 0), error, error_cap)) return 0;
        *out_result = mval_bool(1);
        return 1;
    case 62: /* storage_pwd */
        if (argc != 0) return 0;
        *out_result = owned_text(base);
        return 1;
