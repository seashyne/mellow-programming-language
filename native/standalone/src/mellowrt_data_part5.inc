/* std.data fragment 5: SQLite value and statement helpers. */

static int std_data_truthy(const MValue *value) {
    if (!value) return 0;
    switch (value->tag) {
    case MVAL_BOOL: return value->as.boolean != 0;
    case MVAL_I64: return value->as.i64 != 0;
    case MVAL_F64: return value->as.f64 != 0.0;
    case MVAL_STR: return value->as.str.len != 0;
    case MVAL_LIST: return value->as.list.len != 0;
    case MVAL_MAP: return value->as.map.len != 0;
    default: return 0;
    }
}

/* The statement verb Python's data core compares before touching the DB. */
static int std_data_sql_verb(const char *sql, char *out, size_t size) {
    size_t i = 0, start, n, j;
    while (sql[i] && std_space(sql[i])) ++i;
    start = i;
    while (sql[i] && !std_space(sql[i])) ++i;
    n = i - start;
    if (!n || n >= size) return 0;
    for (j = 0; j < n; ++j) {
        char c = sql[start + j];
        if (c >= 'a' && c <= 'z') c = (char)(c - 32);
        out[j] = c;
    }
    out[n] = '\0';
    return 1;
}

static long long std_data_sqlite_limit(MellowRuntimeContext *ctx, const MValue *args,
                                       size_t argc) {
    long long max_rows = ctx && ctx->data_max_query_rows > 0
                             ? ctx->data_max_query_rows
                             : DATA_DEFAULT_MAX_QUERY_ROWS;
    long long limit = max_rows;
    int given = 0;
    if (argc > 3 && std_data_truthy(&args[3])) {
        int64_t wanted = 0;
        if (!std_game_integer(&args[3], &wanted)) {
            std_data_error(ctx, "data sqlite query limit must be an integer");
            return -1;
        }
        limit = (long long)wanted;
        given = 1;
    }
    if (!given) limit = max_rows;
    if (limit < 1) limit = 1;
    return limit < max_rows ? limit : max_rows;
}

static int std_data_sqlite_open_connection(MellowRuntimeContext *ctx, const MValue *target,
                                           int readonly, int allow_memory, sqlite3 **out) {
    int is_memory = target->tag == MVAL_STR && target->as.str.len == 8 &&
                    memcmp(target->as.str.ptr, ":memory:", 8) == 0;
    char *path = NULL;
    sqlite3 *db = NULL;
    int flags, rc;
    if (is_memory && !allow_memory)
        return std_data_error(ctx, "use data.sqlite_open for a persistent in-memory database");
    if (is_memory) {
        flags = SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE | SQLITE_OPEN_MEMORY;
    } else {
        if (!readonly && (!ctx || !ctx->allow_data_write))
            return std_data_error(ctx, "data writes are disabled");
        path = std_data_resolve_path(ctx, target);
        if (!path) return 0;
        flags = readonly ? SQLITE_OPEN_READONLY : (SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE);
    }
    rc = sqlite3_open_v2(is_memory ? ":memory:" : path, &db, flags, NULL);
    if (rc != SQLITE_OK) {
        char message[256];
        snprintf(message, sizeof(message), "%s",
                 db ? sqlite3_errmsg(db) : "unable to open database file");
        if (db) sqlite3_close(db);
        if (path) std_data_error(ctx, "data: cannot open %s", path);
        else std_data_error(ctx, "%s", message);
        free(path);
        return 0;
    }
    free(path);
    sqlite3_busy_timeout(db, 1000);
    *out = db;
    return 1;
}

/* Reuse an open handle, or open a temporary connection for a bare path. */
static int std_data_sqlite_acquire(MellowRuntimeContext *ctx, const MValue *target,
                                   int readonly, sqlite3 **out, int *owned) {
    StdDataState *state = std_data_state(ctx);
    char *text = std_data_handle_text(target);
    size_t i;
    *owned = 0;
    if (!state) { free(text); return 0; }
    if (text && !strncmp(text, "db:", 3)) {
        int id = atoi(text + 3);
        for (i = 0; i < DATA_MAX_OPEN_STREAMS; ++i) {
            if (state->databases[i] && state->database_ids[i] == id) {
                *out = state->databases[i];
                free(text);
                return 1;
            }
        }
    }
    free(text);
    if (!std_data_sqlite_open_connection(ctx, target, readonly, 0, out)) return 0;
    *owned = 1;
    return 1;
}

static int std_data_sqlite_bind_value(MellowRuntimeContext *ctx, sqlite3 *db,
                                      sqlite3_stmt *stmt, int index, const MValue *value) {
    int rc;
    switch (value->tag) {
    case MVAL_NONE: rc = sqlite3_bind_null(stmt, index); break;
    case MVAL_BOOL: rc = sqlite3_bind_int(stmt, index, value->as.boolean ? 1 : 0); break;
    case MVAL_I64: rc = sqlite3_bind_int64(stmt, index, (sqlite3_int64)value->as.i64); break;
    case MVAL_F64: rc = sqlite3_bind_double(stmt, index, value->as.f64); break;
    case MVAL_STR:
        rc = sqlite3_bind_text(stmt, index, value->as.str.ptr ? value->as.str.ptr : "",
                               (int)value->as.str.len, SQLITE_TRANSIENT);
        break;
    case MVAL_BYTES:
        rc = sqlite3_bind_blob(stmt, index, value->as.str.ptr, (int)value->as.str.len,
                               SQLITE_TRANSIENT);
        break;
    default:
        return std_data_error(ctx,
                              "data sqlite parameters must be null, bool, number, text, or bytes");
    }
    if (rc != SQLITE_OK) return std_data_error(ctx, "%s", sqlite3_errmsg(db));
    return 1;
}

static int std_data_sqlite_bind(MellowRuntimeContext *ctx, sqlite3 *db, sqlite3_stmt *stmt,
                                const MValue *params) {
    int count = sqlite3_bind_parameter_count(stmt), i;
    if (params && params->tag == MVAL_LIST) {
        if ((int)params->as.list.len != count)
            return std_data_error(ctx, "Incorrect number of bindings supplied. The current "
                                       "statement uses %d, and there are %d supplied.",
                                  count, (int)params->as.list.len);
        for (i = 0; i < count; ++i)
            if (!std_data_sqlite_bind_value(ctx, db, stmt, i + 1, &params->as.list.items[i]))
                return 0;
        return 1;
    }
    if (params && params->tag == MVAL_MAP) {
        for (i = 0; i < count; ++i) {
            const char *name = sqlite3_bind_parameter_name(stmt, i + 1);
            const MValue *value;
            if (!name) return std_data_error(ctx, "data sqlite named binding %d has no name", i + 1);
            if (*name == ':' || *name == '@' || *name == '$') ++name;
            value = ai_map_get(params, name);
            if (!value)
                return std_data_error(ctx, "You did not supply a value for binding parameter %s.",
                                      name);
            if (!std_data_sqlite_bind_value(ctx, db, stmt, i + 1, value)) return 0;
        }
        return 1;
    }
    if (count != 0)
        return std_data_error(ctx, "Incorrect number of bindings supplied. The current "
                                   "statement uses %d, and there are 0 supplied.", count);
    return 1;
}

static int std_data_sqlite_prepare(MellowRuntimeContext *ctx, sqlite3 *db, const char *sql,
                                   const MValue *params, sqlite3_stmt **out) {
    sqlite3_stmt *stmt = NULL;
    const char *tail = NULL;
    int rc = sqlite3_prepare_v2(db, sql, -1, &stmt, &tail);
    if (rc != SQLITE_OK) return std_data_error(ctx, "%s", sqlite3_errmsg(db));
    if (tail) {
        while (*tail && (std_space(*tail) || *tail == ';')) ++tail;
        if (*tail) {
            sqlite3_finalize(stmt);
            return std_data_error(ctx, "You can only execute one statement at a time.");
        }
    }
    if (!stmt) { *out = NULL; return 1; }
    if (!std_data_sqlite_bind(ctx, db, stmt, params)) {
        sqlite3_finalize(stmt);
        return 0;
    }
    *out = stmt;
    return 1;
}

static MValue std_data_sqlite_column(sqlite3_stmt *stmt, int column) {
    MValue value = mval_none();
    switch (sqlite3_column_type(stmt, column)) {
    case SQLITE_INTEGER:
        return mval_i64((int64_t)sqlite3_column_int64(stmt, column));
    case SQLITE_FLOAT:
        return mval_f64(sqlite3_column_double(stmt, column));
    case SQLITE_TEXT:
        return std_own_text((const char *)sqlite3_column_text(stmt, column),
                            (size_t)sqlite3_column_bytes(stmt, column));
    case SQLITE_BLOB: {
        const void *blob = sqlite3_column_blob(stmt, column);
        size_t len = (size_t)sqlite3_column_bytes(stmt, column);
        char *buffer = (char *)calloc(len + 1, 1);
        if (!buffer) return value;
        if (blob && len) memcpy(buffer, blob, len);
        value.tag = MVAL_BYTES;
        value.flags = 1u;
        value.as.str.ptr = buffer;
        value.as.str.len = len;
        return value;
    }
    default:
        return value;
    }
}
