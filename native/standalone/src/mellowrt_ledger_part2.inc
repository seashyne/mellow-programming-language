static int number_to_text(double value, char out[64]) {
    char best[64];
    int precision;
    if (!isfinite(value)) return 0;
    for (precision = 1; precision <= 17; ++precision) {
        snprintf(best, sizeof(best), "%.*g", precision, value);
        if (strtod(best, NULL) == value) break;
    }
    if (!strpbrk(best, ".eEnN")) {
        size_t len = strlen(best);
        if (len + 2 < sizeof(best)) {
            best[len] = '.';
            best[len + 1] = '0';
            best[len + 2] = '\0';
        }
    }
    snprintf(out, 64, "%s", best);
    return 1;
}

static int json_map(Sink *s, const MValue *map, const char *skip_key, int depth);

static int json_value(Sink *s, const MValue *value, int depth) {
    char text[64];
    size_t i;
    if (depth > LEDGER_MAX_DEPTH || !value) return 0;
    switch (value->tag) {
    case MVAL_NONE:
        return sink_write(s, "null", 4);
    case MVAL_BOOL:
        return value->as.boolean ? sink_write(s, "true", 4) : sink_write(s, "false", 5);
    case MVAL_I64:
        snprintf(text, sizeof(text), "%lld", (long long)value->as.i64);
        return sink_write(s, text, strlen(text));
    case MVAL_F64:
        if (!number_to_text(value->as.f64, text)) return 0;
        return sink_write(s, text, strlen(text));
    case MVAL_STR:
        json_string(s, value->as.str.ptr, value->as.str.len);
        return !s->failed;
    case MVAL_LIST:
        if (!sink_write(s, "[", 1)) return 0;
        for (i = 0; i < value->as.list.len; ++i) {
            if (i && !sink_write(s, ",", 1)) return 0;
            if (!json_value(s, &value->as.list.items[i], depth + 1)) return 0;
        }
        return sink_write(s, "]", 1);
    case MVAL_MAP:
        return json_map(s, value, NULL, depth);
    default:
        return 0;
    }
}

static int json_map(Sink *s, const MValue *map, const char *skip_key, int depth) {
    KeyRef keys[LEDGER_MAX_MAP_KEYS];
    size_t keep = 0, i;
    if (depth > LEDGER_MAX_DEPTH) return 0;
    if (map->as.map.len > LEDGER_MAX_MAP_KEYS) return 0;
    for (i = 0; i < map->as.map.len; ++i) {
        const MValue *name = &map->as.map.keys[i];
        if (name->tag != MVAL_STR) return 0;
        if (skip_key && name->as.str.len == strlen(skip_key) && name->as.str.ptr &&
            memcmp(name->as.str.ptr, skip_key, name->as.str.len) == 0)
            continue;
        keys[keep].ptr = name->as.str.ptr;
        keys[keep].len = name->as.str.len;
        ++keep;
    }
    if (keep) qsort(keys, keep, sizeof(keys[0]), key_compare);
    if (!sink_write(s, "{", 1)) return 0;
    for (i = 0; i < keep; ++i) {
        const MValue *value = NULL;
        size_t j;
        if (i && !sink_write(s, ",", 1)) return 0;
        json_string(s, keys[i].ptr, keys[i].len);
        if (s->failed) return 0;
        if (!sink_write(s, ":", 1)) return 0;
        for (j = 0; j < map->as.map.len; ++j) {
            const MValue *name = &map->as.map.keys[j];
            if (name->as.str.len == keys[i].len && name->as.str.ptr &&
                memcmp(name->as.str.ptr, keys[i].ptr, keys[i].len) == 0) {
                value = &map->as.map.values[j];
                break;
            }
        }
        if (!value) return 0;
        if (!json_value(s, value, depth + 1)) return 0;
    }
    return sink_write(s, "}", 1);
}

/* The hash body is every entry field except the stored hash, like Python's
   {key: value for key, value in entry.items() if key != "hash"}. */
static int canonical_hash(const MValue *body, char out[LEDGER_HASH_HEX_LEN + 1]) {
    Sink sink;
    unsigned char digest[32];
    Sha256 sha;
    int ok;
    sink_init(&sink);
    ok = json_map(&sink, body, "hash", 0) && !sink.failed && sink.data;
    if (ok) {
        sha_init(&sha);
        sha_update(&sha, (const unsigned char *)sink.data, sink.len);
        sha_final(&sha, digest);
        sha_hex(digest, out);
    }
    sink_free(&sink);
    return ok;
}

/* ── ledger shapes ──────────────────────────────────────────────────────── */

static int value_is(const MValue *value, const char *text) {
    size_t n = strlen(text);
    return value && value->tag == MVAL_STR && value->as.str.len == n && value->as.str.ptr &&
           memcmp(value->as.str.ptr, text, n) == 0;
}

static int text_of(const MValue *value, char *out, size_t cap) {
    out[0] = '\0';
    if (!value) return 0;
    switch (value->tag) {
    case MVAL_STR: {
        size_t n;
        if (!value->as.str.ptr) return 1;
        n = value->as.str.len < cap - 1 ? value->as.str.len : cap - 1;
        memcpy(out, value->as.str.ptr, n);
        out[n] = '\0';
        return 1;
    }
    case MVAL_I64:
        snprintf(out, cap, "%lld", (long long)value->as.i64);
        return 1;
    case MVAL_F64: {
        char text[64];
        if (!number_to_text(value->as.f64, text)) return 0;
        snprintf(out, cap, "%s", text);
        return 1;
    }
    case MVAL_BOOL:
        snprintf(out, cap, "%s", value->as.boolean ? "true" : "false");
        return 1;
    case MVAL_NONE:
        return 1;
    default:
        return 0;
    }
}

static void trim_text(char *text) {
    size_t start = 0, end = strlen(text);
    while (start < end && (text[start] == ' ' || text[start] == '\t')) start++;
    while (end > start && (text[end - 1] == ' ' || text[end - 1] == '\t')) end--;
    if (start) memmove(text, text + start, end - start);
    text[end - start] = '\0';
}

/* Python ledger_core._currency trims and uppercases; charset matches money core. */
static int ledger_currency(const MValue *value, char out[16], char *reason, size_t reason_cap) {
    char text[64];
    size_t start, end, len, i;
    out[0] = '\0';
    if (!value || value->tag == MVAL_NONE) {
        snprintf(out, 16, "USD");
        return 1;
    }
    if (!text_of(value, text, sizeof(text))) {
        set_error(reason, reason_cap, "ledger: invalid currency");
        return 0;
    }
    start = 0;
    end = strlen(text);
    while (start < end && (text[start] == ' ' || text[start] == '\t')) start++;
    while (end > start && (text[end - 1] == ' ' || text[end - 1] == '\t')) end--;
    len = end - start;
    if (!len || len > 12) {
        set_error(reason, reason_cap, "ledger: invalid currency");
        return 0;
    }
    for (i = 0; i < len; ++i) {
        char ch = text[start + i];
        if (ch >= 'a' && ch <= 'z') ch = (char)(ch - 'a' + 'A');
        if (!((ch >= 'A' && ch <= 'Z') || (ch >= '0' && ch <= '9') || ch == '_')) {
            set_error(reason, reason_cap, "ledger: invalid currency");
            return 0;
        }
        out[i] = ch;
    }
    out[len] = '\0';
    return 1;
}

static const MValue *require_ledger(const MValue *value, char *error, size_t cap) {
    const MValue *entries;
    if (!value_is(map_get(value, "type"), "ledger")) {
        set_error(error, cap, "ledger: expected ledger");
        return NULL;
    }
    entries = map_get(value, "entries");
    if (!entries || entries->tag != MVAL_LIST) {
        set_error(error, cap, "ledger: invalid entries");
        return NULL;
    }
    return entries;
}

static int head_hash_of(const MValue *book, char out[LEDGER_HASH_HEX_LEN + 1]) {
    const MValue *head = map_get(book, "head");
    if (!head || head->tag != MVAL_STR || head->as.str.len != LEDGER_HASH_HEX_LEN || !head->as.str.ptr) {
        snprintf(out, LEDGER_HASH_HEX_LEN + 1, "%s", LEDGER_GENESIS);
        return 1;
    }
    memcpy(out, head->as.str.ptr, LEDGER_HASH_HEX_LEN);
    out[LEDGER_HASH_HEX_LEN] = '\0';
    return 1;
}

static int ledger_create(const MValue *args, size_t argc, MValue *out, char *error, size_t cap) {
    char currency[16];
    MValue book;
    if (!ledger_currency(argc ? &args[0] : NULL, currency, error, cap)) return 0;
    book = map_of(5);
    if (book.tag != MVAL_MAP) {
        set_error(error, cap, "ledger: out of memory");
        return 0;
    }
    book.as.map.keys[0] = owned_text("type");
    book.as.map.values[0] = owned_text("ledger");
    book.as.map.keys[1] = owned_text("version");
    book.as.map.values[1] = mval_i64(1);
    book.as.map.keys[2] = owned_text("currency");
    book.as.map.values[2] = owned_text(currency);
    book.as.map.keys[3] = owned_text("entries");
    book.as.map.values[3] = list_of(0);
    book.as.map.keys[4] = owned_text("head");
    book.as.map.values[4] = owned_text(LEDGER_GENESIS);
    *out = book;
    return 1;
}

static MValue posting_row(const char *account, int64_t cents) {
    MValue row = map_of(2);
    char amount[64];
    if (row.tag != MVAL_MAP) return mval_none();
    mellowrt_money_format_cents(cents, amount);
    row.as.map.keys[0] = owned_text("account");
    row.as.map.values[0] = owned_text(account);
    row.as.map.keys[1] = owned_text("amount");
    row.as.map.values[1] = owned_text(amount);
    return row;
}

