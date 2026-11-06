/* std.data fragment 6: SQLite syscalls and dispatch. */

static int std_data_sqlite_open_syscall(MellowRuntimeContext *ctx, const MValue *args,
                                        size_t argc, MValue *out) {
    StdDataState *state = std_data_state(ctx);
    MValue memory = mval_str(":memory:", 8);
    const MValue *target = (argc > 0 && args[0].tag != MVAL_NONE) ? &args[0] : &memory;
    int readonly = argc > 1 && std_data_truthy(&args[1]);
    sqlite3 *db = NULL;
    size_t i;
    if (!state) return 0;
    if (!std_data_sqlite_open_connection(ctx, target, readonly, 1, &db)) return 0;
    for (i = 0; i < DATA_MAX_OPEN_STREAMS; ++i) {
        char text[32];
        if (state->databases[i]) continue;
        state->databases[i] = db;
        state->database_ids[i] = ++state->next_id;
        snprintf(text, sizeof(text), "db:%d", state->database_ids[i]);
        *out = mval_owned_copy(text, strlen(text));
        return 1;
    }
    sqlite3_close(db);
    return std_data_error(ctx, "too many open databases (max %d)", DATA_MAX_OPEN_STREAMS);
}

static int std_data_sqlite_close_syscall(MellowRuntimeContext *ctx, const MValue *args,
                                         size_t argc, MValue *out) {
    StdDataState *state = ctx ? (StdDataState *)ctx->data_state : NULL;
    char *text;
    size_t i;
    *out = mval_bool(0);
    if (argc < 1 || !state) return 1;
    text = std_data_handle_text(&args[0]);
    if (text && !strncmp(text, "db:", 3)) {
        int id = atoi(text + 3);
        for (i = 0; i < DATA_MAX_OPEN_STREAMS; ++i) {
            if (state->databases[i] && state->database_ids[i] == id) {
                sqlite3_close(state->databases[i]);
                state->databases[i] = NULL;
                state->database_ids[i] = 0;
                *out = mval_bool(1);
                break;
            }
        }
    }
    free(text);
    return 1;
}

static int std_data_sqlite_query_syscall(MellowRuntimeContext *ctx, const MValue *args,
                                         size_t argc, MValue *out) {
    char *sql;
    char verb[16];
    long long limit, count = 0;
    sqlite3 *db = NULL;
    sqlite3_stmt *stmt = NULL;
    MValue rows = mval_none();
    int owned = 0, rc = SQLITE_DONE, status = 1;
    if (argc < 2) return std_data_error(ctx, "data.sqlite_query expects a database and SQL");
    if (!ctx) return 0;
    sql = std_text(&args[1], NULL);
    if (!sql) return 0;
    if (!std_data_sql_verb(sql, verb, sizeof(verb)) ||
        (strcmp(verb, "SELECT") && strcmp(verb, "WITH") && strcmp(verb, "PRAGMA"))) {
        free(sql);
        return std_data_error(ctx, "data.sqlite_query only allows read-only statements");
    }
    limit = std_data_sqlite_limit(ctx, args, argc);
    if (limit < 0) { free(sql); return 0; }
    if (!std_data_sqlite_acquire(ctx, &args[0], 1, &db, &owned)) { free(sql); return 0; }
    if (!std_data_sqlite_prepare(ctx, db, sql, argc > 2 ? &args[2] : NULL, &stmt)) {
        if (owned) sqlite3_close(db);
        free(sql);
        return 0;
    }
    if (!ai_list_new(&rows, 8)) status = 0;
    while (status && stmt && (rc = sqlite3_step(stmt)) == SQLITE_ROW) {
        MValue row = mval_none();
        int columns, i;
        if (count >= limit) {
            status = std_data_error(ctx, "SQLite result exceeds row limit %lld", limit);
            break;
        }
        columns = sqlite3_column_count(stmt);
        if (!ai_map_new(&row, (size_t)columns)) { status = 0; break; }
        for (i = 0; i < columns; ++i) {
            const char *name = sqlite3_column_name(stmt, i);
            if (!std_map_set(&row, ai_str(name ? name : ""),
                             std_data_sqlite_column(stmt, i))) {
                status = 0;
                break;
            }
        }
        if (status) {
            if (!std_list_append(&rows, row)) status = 0;
        }
        if (!status) mvalue_free(&row);
        ++count;
    }
    if (status && stmt && rc != SQLITE_DONE) status = std_data_error(ctx, "%s", sqlite3_errmsg(db));
    sqlite3_finalize(stmt);
    if (owned) sqlite3_close(db);
    free(sql);
    if (!status) { mvalue_free(&rows); return 0; }
    *out = rows;
    return 1;
}

static int std_data_sqlite_execute_syscall(MellowRuntimeContext *ctx, const MValue *args,
                                           size_t argc, MValue *out) {
    char *sql;
    char verb[16];
    sqlite3 *db = NULL;
    sqlite3_stmt *stmt = NULL;
    MValue result = mval_none();
    int owned = 0, rc = SQLITE_DONE;
    if (argc < 2) return std_data_error(ctx, "data.sqlite_execute expects a database and SQL");
    if (!ctx || !ctx->allow_data_write) return std_data_error(ctx, "data writes are disabled");
    sql = std_text(&args[1], NULL);
    if (!sql) return 0;
    if (!std_data_sql_verb(sql, verb, sizeof(verb)) ||
        (strcmp(verb, "INSERT") && strcmp(verb, "UPDATE") && strcmp(verb, "DELETE") &&
         strcmp(verb, "CREATE"))) {
        free(sql);
        return std_data_error(ctx, "unsupported SQLite write statement");
    }
    if (!std_data_sqlite_acquire(ctx, &args[0], 0, &db, &owned)) { free(sql); return 0; }
    if (!std_data_sqlite_prepare(ctx, db, sql, argc > 2 ? &args[2] : NULL, &stmt)) {
        if (owned) sqlite3_close(db);
        free(sql);
        return 0;
    }
    if (stmt) {
        rc = sqlite3_step(stmt);
        if (rc != SQLITE_DONE) std_data_error(ctx, "%s", sqlite3_errmsg(db));
    }
    sqlite3_finalize(stmt);
    if (rc == SQLITE_DONE) {
        /* Python reports rowcount -1 (clamped to 0) for DDL, while
         * sqlite3_changes keeps the last INSERT/UPDATE/DELETE count. */
        long long changed = strcmp(verb, "CREATE") ? (long long)sqlite3_changes(db) : 0;
        if (changed < 0) changed = 0;
        if (!ai_map_new(&result, 2)) rc = SQLITE_ERROR;
        else {
            ai_map_put(&result, "rows_changed", mval_i64(changed));
            ai_map_put(&result, "last_row_id", mval_i64((int64_t)sqlite3_last_insert_rowid(db)));
        }
    }
    if (owned) sqlite3_close(db);
    free(sql);
    if (rc != SQLITE_DONE) { mvalue_free(&result); return 0; }
    *out = result;
    return 1;
}

static int std_data_syscall(MellowRuntimeContext *ctx, int id, const MValue *args,
                            size_t argc, MValue *out) {
    switch (id) {
    case 360: return std_data_open_syscall(ctx, args, argc, DATA_KIND_JSONL, out);
    case 361: return std_data_open_syscall(ctx, args, argc, DATA_KIND_CSV, out);
    case 362: return std_data_next_syscall(ctx, args, argc, out);
    case 363:
    case 364: return std_data_close_syscall(ctx, args, argc, out);
    case 365: return std_data_info_syscall(ctx, args, argc, out);
    case 366: return std_data_project_syscall(ctx, args, argc, out);
    case 367: return std_data_where_syscall(ctx, args, argc, out);
    case 368: return std_data_sum_syscall(ctx, args, argc, out);
    case 369: return std_data_sqlite_open_syscall(ctx, args, argc, out);
    case 370: return std_data_sqlite_close_syscall(ctx, args, argc, out);
    case 371: return std_data_sqlite_query_syscall(ctx, args, argc, out);
    case 372: return std_data_sqlite_execute_syscall(ctx, args, argc, out);
    default: return 0;
    }
}
