static int ledger_post(const MValue *args, size_t argc, MValue *out, char *error, size_t cap) {
    const MValue *entries, *postings, *memo_value, *metadata_value;
    MValue entry, new_book, memo, postings_list;
    MValue *rows;
    char tx_id[128], currency[16], account[128], previous[LEDGER_HASH_HEX_LEN + 1];
    char hash[LEDGER_HASH_HEX_LEN + 1], amount_text[64], message[256], detail[96], memo_text[512];
    int64_t total = 0;
    size_t row_count, i;

    entries = require_ledger(&args[0], error, cap);
    if (!entries) return 0;
    if (!ledger_currency(map_get(&args[0], "currency"), currency, error, cap)) return 0;

    if (!text_of(&args[1], tx_id, sizeof(tx_id))) tx_id[0] = '\0';
    trim_text(tx_id);
    if (!tx_id[0]) {
        set_error(error, cap, "ledger: transaction id is required");
        return 0;
    }
    for (i = 0; i < entries->as.list.len; ++i) {
        char existing[128];
        const MValue *entry_id = map_get(&entries->as.list.items[i], "id");
        existing[0] = '\0';
        if (!entry_id || !text_of(entry_id, existing, sizeof(existing))) continue;
        if (strcmp(existing, tx_id) == 0) {
            snprintf(message, sizeof(message), "ledger: duplicate transaction id: %s", tx_id);
            set_error(error, cap, message);
            return 0;
        }
    }

    postings = &args[2];
    if (postings->tag != MVAL_LIST || postings->as.list.len < 2) {
        set_error(error, cap, "ledger: postings must contain at least two rows");
        return 0;
    }
    row_count = postings->as.list.len;
    postings_list = list_of(row_count);
    if (postings_list.tag != MVAL_LIST) {
        set_error(error, cap, "ledger: out of memory");
        return 0;
    }
    rows = postings_list.as.list.items;
    total = 0;
    for (i = 0; i < row_count; ++i) {
        const MValue *row = &postings->as.list.items[i];
        const MValue *amount_value;
        int64_t cents = 0;
        if (row->tag != MVAL_MAP) {
            set_error(error, cap, "ledger: each posting must be a map");
            postings_list.as.list.len = i;
            mvalue_free(&postings_list);
            return 0;
        }
        account[0] = '\0';
        {
            const MValue *account_value = map_get(row, "account");
            if (account_value) text_of(account_value, account, sizeof(account));
        }
        trim_text(account);
        if (!account[0]) {
            set_error(error, cap, "ledger: posting account is required");
            postings_list.as.list.len = i;
            mvalue_free(&postings_list);
            return 0;
        }
        amount_value = map_get(row, "amount");
        if (!amount_value) {
            cents = 0;
        } else if (!mellowrt_money_cents(amount_value, &cents)) {
            if (!text_of(amount_value, detail, sizeof(detail)))
                snprintf(detail, sizeof(detail), "%s", mvalue_tag_name(amount_value->tag));
            snprintf(message, sizeof(message), "ledger: invalid amount: %s", detail);
            set_error(error, cap, message);
            postings_list.as.list.len = i;
            mvalue_free(&postings_list);
            return 0;
        }
        rows[i] = posting_row(account, cents);
        if (rows[i].tag != MVAL_MAP) {
            set_error(error, cap, "ledger: out of memory");
            postings_list.as.list.len = i + 1;
            mvalue_free(&postings_list);
            return 0;
        }
        total += cents;
    }
    if (total != 0) {
        mellowrt_money_format_cents(total, amount_text);
        snprintf(message, sizeof(message), "ledger: transaction is not balanced: %s", amount_text);
        set_error(error, cap, message);
        postings_list.as.list.len = row_count;
        mvalue_free(&postings_list);
        return 0;
    }

    memo_value = argc > 3 ? &args[3] : NULL;
    if (memo_value && memo_value->tag == MVAL_STR) {
        memo = clone_value(memo_value);
        if (memo.tag != MVAL_STR) memo = owned_text("");
    } else {
        memo_text[0] = '\0';
        if (memo_value) text_of(memo_value, memo_text, sizeof(memo_text));
        memo = owned_copy(memo_text, strlen(memo_text));
    }

    metadata_value = argc > 4 ? &args[4] : NULL;
    entry = map_of(7);
    if (entry.tag != MVAL_MAP || memo.tag != MVAL_STR) {
        set_error(error, cap, "ledger: out of memory");
        mvalue_free(&memo);
        postings_list.as.list.len = row_count;
        mvalue_free(&postings_list);
        return 0;
    }
    entry.as.map.keys[0] = owned_text("id");
    entry.as.map.values[0] = owned_text(tx_id);
    entry.as.map.keys[1] = owned_text("currency");
    entry.as.map.values[1] = owned_text(currency);
    entry.as.map.keys[2] = owned_text("postings");
    entry.as.map.values[2] = postings_list;
    entry.as.map.keys[3] = owned_text("memo");
    entry.as.map.values[3] = memo;
    entry.as.map.keys[4] = owned_text("metadata");
    entry.as.map.values[4] =
        (metadata_value && metadata_value->tag == MVAL_MAP) ? clone_value(metadata_value) : map_of(0);
    entry.as.map.keys[5] = owned_text("previous_hash");
    head_hash_of(&args[0], previous);
    entry.as.map.values[5] = owned_text(previous);
    entry.as.map.keys[6] = owned_text("hash");
    entry.as.map.values[6] = owned_text("");

    if (!canonical_hash(&entry, hash)) {
        set_error(error, cap, "ledger: metadata must be JSON serializable");
        mvalue_free(&entry);
        return 0;
    }
    mvalue_free(&entry.as.map.values[6]);
    entry.as.map.values[6] = owned_text(hash);

    new_book = clone_value(&args[0]);
    if (new_book.tag != MVAL_MAP) {
        set_error(error, cap, "ledger: out of memory");
        mvalue_free(&entry);
        return 0;
    }
    {
        MValue *book_entries = map_slot(&new_book, "entries");
        MValue *book_head = map_slot(&new_book, "head");
        if (!book_head) {
            set_error(error, cap, "ledger: invalid entries");
            mvalue_free(&entry);
            mvalue_free(&new_book);
            return 0;
        }
        if (!book_entries || book_entries->tag != MVAL_LIST || !list_append(book_entries, entry)) {
            set_error(error, cap, "ledger: out of memory");
            mvalue_free(&entry);
            mvalue_free(&new_book);
            return 0;
        }
        mvalue_free(book_head);
        *book_head = owned_text(hash);
    }
    *out = new_book;
    return 1;
}

