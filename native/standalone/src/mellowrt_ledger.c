#include "mellowrt_ledger.h"
#include "mellowrt_money.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define LEDGER_GENESIS "0000000000000000000000000000000000000000000000000000000000000000"
#define LEDGER_HASH_HEX_LEN 64
#define LEDGER_MAX_DEPTH 24
#define LEDGER_MAX_MAP_KEYS 64

static MValue owned_copy(const char *src, size_t len) {
    char *buf = (char *)calloc(len + 1, 1);
    MValue v = mval_none();
    if (!buf) return v;
    if (src && len) memcpy(buf, src, len);
    buf[len] = '\0';
    v.tag = MVAL_STR;
    v.flags = 1u;
    v.as.str.ptr = buf;
    v.as.str.len = len;
    return v;
}

static MValue owned_text(const char *text) {
    return owned_copy(text, strlen(text));
}

static MValue list_of(size_t n) {
    MValue v = mval_none();
    v.as.list.len = n;
    v.as.list.cap = n;
    v.as.list.items = (MValue *)calloc(n ? n : 1, sizeof(MValue));
    if (!v.as.list.items) return mval_none();
    v.tag = MVAL_LIST;
    return v;
}

static MValue map_of(size_t n) {
    MValue v = mval_none();
    v.as.map.len = n;
    v.as.map.cap = n;
    v.as.map.keys = (MValue *)calloc(n ? n : 1, sizeof(MValue));
    v.as.map.values = (MValue *)calloc(n ? n : 1, sizeof(MValue));
    if (!v.as.map.keys || !v.as.map.values) {
        free(v.as.map.keys);
        free(v.as.map.values);
        return mval_none();
    }
    v.tag = MVAL_MAP;
    return v;
}

static MValue clone_value(const MValue *src) {
    MValue out;
    size_t i;
    if (!src) return mval_none();
    if (src->tag == MVAL_STR) return owned_copy(src->as.str.ptr, src->as.str.len);
    if (src->tag == MVAL_LIST) {
        out = list_of(src->as.list.len);
        if (out.tag != MVAL_LIST) return mval_none();
        for (i = 0; i < src->as.list.len; ++i)
            out.as.list.items[i] = clone_value(&src->as.list.items[i]);
        return out;
    }
    if (src->tag == MVAL_MAP) {
        out = map_of(src->as.map.len);
        if (out.tag != MVAL_MAP) return mval_none();
        for (i = 0; i < src->as.map.len; ++i) {
            out.as.map.keys[i] = clone_value(&src->as.map.keys[i]);
            out.as.map.values[i] = clone_value(&src->as.map.values[i]);
        }
        return out;
    }
    return *src;
}

static MValue *map_slot(const MValue *map, const char *key) {
    size_t i, n = strlen(key);
    if (!map || map->tag != MVAL_MAP) return NULL;
    for (i = 0; i < map->as.map.len; ++i) {
        const MValue *name = &map->as.map.keys[i];
        if (name->tag == MVAL_STR && name->as.str.len == n && name->as.str.ptr &&
            memcmp(name->as.str.ptr, key, n) == 0)
            return &map->as.map.values[i];
    }
    return NULL;
}

static const MValue *map_get(const MValue *map, const char *key) {
    return map_slot(map, key);
}

static int list_append(MValue *list, MValue item) {
    if (!list || list->tag != MVAL_LIST) return 0;
    if (list->as.list.len == list->as.list.cap) {
        size_t cap = list->as.list.cap ? list->as.list.cap * 2 : 1;
        MValue *grown = (MValue *)realloc(list->as.list.items, cap * sizeof(MValue));
        if (!grown) return 0;
        list->as.list.items = grown;
        list->as.list.cap = cap;
    }
    list->as.list.items[list->as.list.len++] = item;
    return 1;
}

static void set_error(char *error, size_t cap, const char *message) {
    if (error && cap) snprintf(error, cap, "%s", message);
}

/* ── growable byte buffer ───────────────────────────────────────────────── */

typedef struct {
    char *data;
    size_t len;
    size_t cap;
    int failed;
} Sink;

static void sink_init(Sink *s) {
    s->data = NULL;
    s->len = 0;
    s->cap = 0;
    s->failed = 0;
}

static int sink_write(Sink *s, const char *bytes, size_t n) {
    if (s->failed) return 0;
    if (!n) return 1;
    if (s->len + n + 1 > s->cap) {
        size_t next = s->cap ? s->cap : 256;
        char *grown;
        while (next < s->len + n + 1) next *= 2;
        grown = (char *)realloc(s->data, next);
        if (!grown) {
            s->failed = 1;
            return 0;
        }
        s->data = grown;
        s->cap = next;
    }
    memcpy(s->data + s->len, bytes, n);
    s->len += n;
    s->data[s->len] = '\0';
    return 1;
}

static void sink_free(Sink *s) {
    free(s->data);
    sink_init(s);
}

/* ── sha256 ─────────────────────────────────────────────────────────────── */

typedef struct {
    uint32_t h[8];
    uint64_t total;
    unsigned char buf[64];
    size_t fill;
} Sha256;

static const uint32_t SHA_K[64] = {
    0x428a2f98u, 0x71374491u, 0xb5c0fbcfu, 0xe9b5dba5u, 0x3956c25bu, 0x59f111f1u, 0x923f82a4u, 0xab1c5ed5u,
    0xd807aa98u, 0x12835b01u, 0x243185beu, 0x550c7dc3u, 0x72be5d74u, 0x80deb1feu, 0x9bdc06a7u, 0xc19bf174u,
    0xe49b69c1u, 0xefbe4786u, 0x0fc19dc6u, 0x240ca1ccu, 0x2de92c6fu, 0x4a7484aau, 0x5cb0a9dcu, 0x76f988dau,
    0x983e5152u, 0xa831c66du, 0xb00327c8u, 0xbf597fc7u, 0xc6e00bf3u, 0xd5a79147u, 0x06ca6351u, 0x14292967u,
    0x27b70a85u, 0x2e1b2138u, 0x4d2c6dfcu, 0x53380d13u, 0x650a7354u, 0x766a0abbu, 0x81c2c92eu, 0x92722c85u,
    0xa2bfe8a1u, 0xa81a664bu, 0xc24b8b70u, 0xc76c51a3u, 0xd192e819u, 0xd6990624u, 0xf40e3585u, 0x106aa070u,
    0x19a4c116u, 0x1e376c08u, 0x2748774cu, 0x34b0bcb5u, 0x391c0cb3u, 0x4ed8aa4au, 0x5b9cca4fu, 0x682e6ff3u,
    0x748f82eeu, 0x78a5636fu, 0x84c87814u, 0x8cc70208u, 0x90befffau, 0xa4506cebu, 0xbef9a3f7u, 0xc67178f2u
};

#define SHA_ROTR(x, n) (((x) >> (n)) | ((x) << (32 - (n))))

static void sha_block(Sha256 *s, const unsigned char *p) {
    uint32_t w[64], a, b, c, d, e, f, g, h, t1, t2, small0, small1, big0, big1, ch, maj;
    int i;
    for (i = 0; i < 16; ++i)
        w[i] = ((uint32_t)p[i * 4] << 24) | ((uint32_t)p[i * 4 + 1] << 16) |
               ((uint32_t)p[i * 4 + 2] << 8) | (uint32_t)p[i * 4 + 3];
    for (i = 16; i < 64; ++i) {
        small0 = SHA_ROTR(w[i - 15], 7) ^ SHA_ROTR(w[i - 15], 18) ^ (w[i - 15] >> 3);
        small1 = SHA_ROTR(w[i - 2], 17) ^ SHA_ROTR(w[i - 2], 19) ^ (w[i - 2] >> 10);
        w[i] = w[i - 16] + small0 + w[i - 7] + small1;
    }
    a = s->h[0]; b = s->h[1]; c = s->h[2]; d = s->h[3];
    e = s->h[4]; f = s->h[5]; g = s->h[6]; h = s->h[7];
    for (i = 0; i < 64; ++i) {
        big1 = SHA_ROTR(e, 6) ^ SHA_ROTR(e, 11) ^ SHA_ROTR(e, 25);
        ch = (e & f) ^ ((~e) & g);
        t1 = h + big1 + ch + SHA_K[i] + w[i];
        big0 = SHA_ROTR(a, 2) ^ SHA_ROTR(a, 13) ^ SHA_ROTR(a, 22);
        maj = (a & b) ^ (a & c) ^ (b & c);
        t2 = big0 + maj;
        h = g; g = f; f = e; e = d + t1;
        d = c; c = b; b = a; a = t1 + t2;
    }
    s->h[0] += a; s->h[1] += b; s->h[2] += c; s->h[3] += d;
    s->h[4] += e; s->h[5] += f; s->h[6] += g; s->h[7] += h;
}

static void sha_init(Sha256 *s) {
    s->h[0] = 0x6a09e667u; s->h[1] = 0xbb67ae85u; s->h[2] = 0x3c6ef372u;
    s->h[3] = 0xa54ff53au; s->h[4] = 0x510e527fu; s->h[5] = 0x9b05688cu;
    s->h[6] = 0x1f83d9abu; s->h[7] = 0x5be0cd19u;
    s->total = 0;
    s->fill = 0;
}

static void sha_update(Sha256 *s, const unsigned char *p, size_t n) {
    s->total += (uint64_t)n;
    while (n) {
        size_t take = 64 - s->fill;
        if (take > n) take = n;
        memcpy(s->buf + s->fill, p, take);
        s->fill += take;
        p += take;
        n -= take;
        if (s->fill == 64) {
            sha_block(s, s->buf);
            s->fill = 0;
        }
    }
}

static void sha_final(Sha256 *s, unsigned char out[32]) {
    uint64_t bits = s->total * 8u;
    unsigned char pad[72];
    size_t pad_len;
    int i;
    memset(pad, 0, sizeof(pad));
    pad[0] = 0x80;
    pad_len = (s->fill < 56) ? (56 - s->fill) : (120 - s->fill);
    for (i = 0; i < 8; ++i) pad[pad_len + i] = (unsigned char)(bits >> (56 - i * 8));
    sha_update(s, pad, pad_len + 8);
    for (i = 0; i < 8; ++i) {
        out[i * 4] = (unsigned char)(s->h[i] >> 24);
        out[i * 4 + 1] = (unsigned char)(s->h[i] >> 16);
        out[i * 4 + 2] = (unsigned char)(s->h[i] >> 8);
        out[i * 4 + 3] = (unsigned char)s->h[i];
    }
}

static void sha_hex(const unsigned char digest[32], char out[LEDGER_HASH_HEX_LEN + 1]) {
    static const char digits[] = "0123456789abcdef";
    int i;
    for (i = 0; i < 32; ++i) {
        out[i * 2] = digits[digest[i] >> 4];
        out[i * 2 + 1] = digits[digest[i] & 0x0f];
    }
    out[LEDGER_HASH_HEX_LEN] = '\0';
}

/* ── canonical JSON, matching json.dumps(sort_keys=True, ensure_ascii=False) ── */

typedef struct {
    const char *ptr;
    size_t len;
} KeyRef;

static int key_compare(const void *a, const void *b) {
    const KeyRef *x = (const KeyRef *)a;
    const KeyRef *y = (const KeyRef *)b;
    size_t common = x->len < y->len ? x->len : y->len;
    int c = common ? memcmp(x->ptr, y->ptr, common) : 0;
    if (c) return c;
    if (x->len == y->len) return 0;
    return x->len < y->len ? -1 : 1;
}

static void json_string(Sink *s, const char *p, size_t n) {
    size_t i;
    sink_write(s, "\"", 1);
    for (i = 0; i < n; ++i) {
        unsigned char ch = p[i] & 0xffu;
        char esc[8];
        switch (ch) {
        case '"': sink_write(s, "\\\"", 2); break;
        case '\\': sink_write(s, "\\\\", 2); break;
        case '\b': sink_write(s, "\\b", 2); break;
        case '\t': sink_write(s, "\\t", 2); break;
        case '\n': sink_write(s, "\\n", 2); break;
        case '\f': sink_write(s, "\\f", 2); break;
        case '\r': sink_write(s, "\\r", 2); break;
        default:
            if (ch < 0x20) {
                snprintf(esc, sizeof(esc), "\\u00%02x", ch);
                sink_write(s, esc, strlen(esc));
            } else {
                sink_write(s, (const char *)&ch, 1);
            }
        }
    }
    sink_write(s, "\"", 1);
}

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
