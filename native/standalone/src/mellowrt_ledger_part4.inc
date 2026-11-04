static int ledger_verify(const MValue *args, MValue *out, char *error, size_t cap) {
    const MValue *entries;
    char book_currency[16], expected[LEDGER_HASH_HEX_LEN + 1], actual[LEDGER_HASH_HEX_LEN + 1];
    char message[256], reason[256], tx_id[128], scratch[64];
    MValue status;
    size_t i, j;
    int ok = 1;

    (void)error;
    (void)cap;
    reason[0] = '\0';
    entries = map_get(&args[0], "entries");
    if (!entries || entries->tag != MVAL_LIST) {
        if (!value_is(map_get(&args[0], "type"), "ledger")) snprintf(reason, sizeof(reason), "%s", "ledger: expected ledger");
        else snprintf(reason, sizeof(reason), "%s", "ledger: invalid entries");
        ok = 0;
    } else {
        book_currency[0] = '\0';
        if (entries->as.list.len) {
            if (!ledger_currency(map_get(&args[0], "currency"), book_currency, scratch, sizeof(scratch))) {
                snprintf(reason, sizeof(reason), "%s", scratch);
                ok = 0;
            }
        }
    }
    if (ok) snprintf(expected, sizeof(expected), "%s", LEDGER_GENESIS);

    for (i = 0; ok && i < entries->as.list.len; ++i) {
        const MValue *entry = &entries->as.list.items[i];
        const MValue *entry_id, *entry_previous, *entry_currency, *postings, *stored_hash;
        char entry_currency_text[16];
        int64_t total = 0;
        if (entry->tag != MVAL_MAP) {
            snprintf(reason, sizeof(reason), "ledger: invalid entry at index %u", (unsigned)i);
            ok = 0;
            break;
        }
        entry_id = map_get(entry, "id");
        tx_id[0] = '\0';
        if (entry_id) text_of(entry_id, tx_id, sizeof(tx_id));
        if (!tx_id[0]) {
            snprintf(reason, sizeof(reason),
                     "ledger: duplicate or missing transaction id at index %u", (unsigned)i);
            ok = 0;
            break;
        }
        for (j = 0; j < i; ++j) {
            char previous_id[128];
            const MValue *other_id = map_get(&entries->as.list.items[j], "id");
            previous_id[0] = '\0';
            if (other_id && text_of(other_id, previous_id, sizeof(previous_id)) &&
                strcmp(previous_id, tx_id) == 0) {
                snprintf(reason, sizeof(reason),
                         "ledger: duplicate or missing transaction id at index %u", (unsigned)i);
                ok = 0;
                break;
            }
        }
        if (!ok) break;
        entry_previous = map_get(entry, "previous_hash");
        if (!value_is(entry_previous, expected)) {
            snprintf(reason, sizeof(reason), "ledger: broken hash chain at index %u", (unsigned)i);
            ok = 0;
            break;
        }
        entry_currency = map_get(entry, "currency");
        if (!ledger_currency(entry_currency, entry_currency_text, scratch, sizeof(scratch))) {
            snprintf(reason, sizeof(reason), "%s", scratch);
            ok = 0;
            break;
        }
        if (strcmp(entry_currency_text, book_currency) != 0) {
            snprintf(reason, sizeof(reason), "ledger: currency mismatch at index %u", (unsigned)i);
            ok = 0;
            break;
        }
        postings = map_get(entry, "postings");
        if (!postings || postings->tag != MVAL_LIST) {
            snprintf(reason, sizeof(reason), "ledger: invalid postings at index %u", (unsigned)i);
            ok = 0;
            break;
        }
        for (j = 0; j < postings->as.list.len; ++j) {
            const MValue *row = &postings->as.list.items[j];
            const MValue *amount = map_get(row, "amount");
            int64_t cents = 0;
            if (row->tag != MVAL_MAP) {
                snprintf(reason, sizeof(reason), "ledger: invalid posting at index %u", (unsigned)i);
                ok = 0;
                break;
            }
            if (!amount) continue;
            if (!mellowrt_money_cents(amount, &cents)) {
                char detail[96];
                if (!text_of(amount, detail, sizeof(detail)))
                    snprintf(detail, sizeof(detail), "%s", mvalue_tag_name(amount->tag));
                snprintf(reason, sizeof(reason), "ledger: invalid amount: %s", detail);
                ok = 0;
                break;
            }
            total += cents;
        }
        if (!ok) break;
        if (total != 0) {
            snprintf(reason, sizeof(reason), "ledger: unbalanced entry at index %u", (unsigned)i);
            ok = 0;
            break;
        }
        if (!canonical_hash(entry, actual)) {
            snprintf(reason, sizeof(reason),
                     "ledger: metadata must be JSON serializable at index %u", (unsigned)i);
            ok = 0;
            break;
        }
        stored_hash = map_get(entry, "hash");
        if (!stored_hash || stored_hash->tag != MVAL_STR ||
            stored_hash->as.str.len != LEDGER_HASH_HEX_LEN || !stored_hash->as.str.ptr ||
            memcmp(stored_hash->as.str.ptr, actual, LEDGER_HASH_HEX_LEN) != 0) {
            snprintf(reason, sizeof(reason), "ledger: hash mismatch at index %u", (unsigned)i);
            ok = 0;
            break;
        }
        snprintf(expected, sizeof(expected), "%s", actual);
    }

    if (ok) {
        char head_text[LEDGER_HASH_HEX_LEN + 1];
        head_hash_of(&args[0], head_text);
        if (strcmp(head_text, expected) != 0) {
            snprintf(reason, sizeof(reason), "%s", "ledger: head hash mismatch");
            ok = 0;
        }
    }

    status = map_of(4);
    if (status.tag != MVAL_MAP) return 0;
    status.as.map.keys[0] = owned_text("ok");
    status.as.map.values[0] = mval_bool(ok);
    status.as.map.keys[1] = owned_text("count");
    status.as.map.values[1] = mval_i64(ok && entries ? (int64_t)entries->as.list.len : 0);
    status.as.map.keys[2] = owned_text("head");
    status.as.map.values[2] = ok ? owned_text(expected) : mval_none();
    status.as.map.keys[3] = owned_text("error");
    status.as.map.values[3] = ok ? mval_none() : owned_text(reason);
    snprintf(message, sizeof(message), "%s", reason);
    (void)message;
    *out = status;
    return 1;
}

static int ledger_balance(const MValue *args, MValue *out, char *error, size_t cap) {
    const MValue *entries = require_ledger(&args[0], error, cap);
    char currency[16], wanted[128], given[128], detail[96], message[256];
    int64_t total = 0;
    size_t i, j;
    if (!entries) return 0;
    if (!ledger_currency(map_get(&args[0], "currency"), currency, error, cap)) return 0;
    given[0] = '\0';
    if (text_of(&args[1], given, sizeof(given))) trim_text(given);
    for (i = 0; i < entries->as.list.len; ++i) {
        const MValue *postings = map_get(&entries->as.list.items[i], "postings");
        if (!postings || postings->tag != MVAL_LIST) continue;
        for (j = 0; j < postings->as.list.len; ++j) {
            const MValue *row = &postings->as.list.items[j];
            const MValue *account, *amount;
            int64_t cents = 0;
            if (row->tag != MVAL_MAP) continue;
            account = map_get(row, "account");
            amount = map_get(row, "amount");
            wanted[0] = '\0';
            if (account) text_of(account, wanted, sizeof(wanted));
            if (strcmp(wanted, given) != 0) continue;
            if (amount && !mellowrt_money_cents(amount, &cents)) {
                if (!text_of(amount, detail, sizeof(detail)))
                    snprintf(detail, sizeof(detail), "%s", mvalue_tag_name(amount->tag));
                snprintf(message, sizeof(message), "ledger: invalid amount: %s", detail);
                set_error(error, cap, message);
                return 0;
            }
            total += cents;
        }
    }
    *out = mellowrt_money_make(total, currency);
    return out->tag == MVAL_MAP;
}

static int ledger_entries(const MValue *args, MValue *out, char *error, size_t cap) {
    const MValue *entries = require_ledger(&args[0], error, cap);
    MValue copy;
    if (!entries) return 0;
    copy = clone_value(entries);
    if (copy.tag != MVAL_LIST) {
        set_error(error, cap, "ledger: out of memory");
        return 0;
    }
    *out = copy;
    return 1;
}

int mellowrt_ledger_syscall(int32_t id, const MValue *args, size_t argc, MValue *out_result,
                            char *error, size_t error_cap) {
    if (error && error_cap) error[0] = '\0';
    if (!out_result || !args) return 0;
    switch (id) {
    case 56:
        if (argc > 1) return 0;
        return ledger_create(args, argc, out_result, error, error_cap);
    case 57:
        if (argc < 3 || argc > 5) return 0;
        return ledger_post(args, argc, out_result, error, error_cap);
    case 58:
        if (argc != 1) return 0;
        return ledger_verify(args, out_result, error, error_cap);
    case 59:
        if (argc != 2) return 0;
        return ledger_balance(args, out_result, error, error_cap);
    case 60:
        if (argc != 1) return 0;
        return ledger_entries(args, out_result, error, error_cap);
    default:
        return 0;
    }
}
