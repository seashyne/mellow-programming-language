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

