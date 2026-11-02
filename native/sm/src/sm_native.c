#include "sm_native.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define SM3_MAGIC "SM3\0"
#define SM3_CODEC "sm3-token-native-crc32"
#define SM_MAX_DICT 240
#define SM_MAX_TOKEN 255

typedef struct {
    const unsigned char *ptr;
    uint16_t len;
    uint32_t count;
    uint32_t saving;
} Token;

static uint32_t le32(const unsigned char *p) {
    return (uint32_t)(p[0] | (p[1] << 8) | (p[2] << 16) | (p[3] << 24));
}

static uint16_t le16(const unsigned char *p) {
    return (uint16_t)(p[0] | (p[1] << 8));
}

static void put_le16(unsigned char *p, uint16_t v) {
    p[0] = (unsigned char)(v & 0xffu);
    p[1] = (unsigned char)((v >> 8) & 0xffu);
}

static void put_le32(unsigned char *p, uint32_t v) {
    p[0] = (unsigned char)(v & 0xffu);
    p[1] = (unsigned char)((v >> 8) & 0xffu);
    p[2] = (unsigned char)((v >> 16) & 0xffu);
    p[3] = (unsigned char)((v >> 24) & 0xffu);
}

static void set_error(SmInfo *info, const char *msg) {
    if (!info) return;
    memset(info, 0, sizeof(*info));
    snprintf(info->error, sizeof(info->error), "%s", msg);
}

static uint32_t crc32_bytes(const unsigned char *data, size_t size) {
    uint32_t crc = 0xffffffffu;
    for (size_t i = 0; i < size; i++) {
        crc ^= data[i];
        for (int bit = 0; bit < 8; bit++) {
            uint32_t mask = 0u - (crc & 1u);
            crc = (crc >> 1) ^ (0xedb88320u & mask);
        }
    }
    return ~crc;
}

static int is_alpha_(unsigned char c) {
    return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || c == '_';
}

static int is_alnum_(unsigned char c) {
    return is_alpha_(c) || (c >= '0' && c <= '9');
}

static int token_equal(const Token *t, const unsigned char *ptr, size_t len) {
    return t->len == len && memcmp(t->ptr, ptr, len) == 0;
}

static int add_token(Token *tokens, size_t *count, size_t cap, const unsigned char *ptr, size_t len) {
    if (len < 3 || len > SM_MAX_TOKEN) return 1;
    for (size_t i = 0; i < *count; i++) {
        if (token_equal(&tokens[i], ptr, len)) {
            tokens[i].count++;
            return 1;
        }
    }
    if (*count >= cap) return 1;
    tokens[*count].ptr = ptr;
    tokens[*count].len = (uint16_t)len;
    tokens[*count].count = 1;
    tokens[*count].saving = 0;
    (*count)++;
    return 1;
}

static int compare_tokens(const void *a, const void *b) {
    const Token *ta = (const Token *)a;
    const Token *tb = (const Token *)b;
    if (ta->saving != tb->saving) return ta->saving < tb->saving ? 1 : -1;
    if (ta->len != tb->len) return ta->len < tb->len ? 1 : -1;
    return memcmp(ta->ptr, tb->ptr, ta->len < tb->len ? ta->len : tb->len);
}

static size_t build_dictionary(const unsigned char *input, size_t size, Token *dict, size_t max_dict) {
    size_t cap = 4096;
    Token *tokens = (Token *)calloc(cap, sizeof(Token));
    size_t count = 0;
    size_t out_count = 0;
    if (!tokens) return 0;
    for (size_t i = 0; i < size;) {
        if (is_alpha_(input[i])) {
            size_t start = i++;
            while (i < size && is_alnum_(input[i])) i++;
            add_token(tokens, &count, cap, input + start, i - start);
            continue;
        }
        if (input[i] == '\n') {
            size_t start = i++;
            while (i < size && (input[i] == ' ' || input[i] == '\t')) i++;
            add_token(tokens, &count, cap, input + start, i - start);
            continue;
        }
        i++;
    }
    for (size_t i = 0; i < count; i++) {
        if (tokens[i].count < 2) {
            tokens[i].saving = 0;
            continue;
        }
        tokens[i].saving = (uint32_t)((tokens[i].len > 2 ? tokens[i].len - 2 : 0) * tokens[i].count);
    }
    qsort(tokens, count, sizeof(Token), compare_tokens);
    for (size_t i = 0; i < count && out_count < max_dict; i++) {
        if (tokens[i].saving <= 3) break;
        dict[out_count++] = tokens[i];
    }
    free(tokens);
    return out_count;
}

static int ensure_cap(unsigned char **buf, size_t *cap, size_t need) {
    unsigned char *next;
    if (need <= *cap) return 1;
    while (*cap < need) {
        if (*cap > ((size_t)-1) / 2u) return 0;
        *cap *= 2u;
    }
    next = (unsigned char *)realloc(*buf, *cap);
    if (!next) return 0;
    *buf = next;
    return 1;
}

static int find_dict(const Token *dict, size_t dict_count, const unsigned char *input, size_t size, size_t pos, unsigned char *idx, uint16_t *len) {
    for (size_t i = 0; i < dict_count; i++) {
        if (pos + dict[i].len <= size && memcmp(input + pos, dict[i].ptr, dict[i].len) == 0) {
            *idx = (unsigned char)i;
            *len = dict[i].len;
            return 1;
        }
    }
    return 0;
}

static int encode_stream(const unsigned char *input, size_t size, const Token *dict, size_t dict_count, unsigned char **out, size_t *out_size) {
    size_t cap = size ? size + (size / 16u) + 64u : 64u;
    size_t len = 0;
    unsigned char *buf = (unsigned char *)malloc(cap);
    if (!buf) return 0;
    for (size_t i = 0; i < size;) {
        unsigned char idx = 0;
        uint16_t tok_len = 0;
        if (find_dict(dict, dict_count, input, size, i, &idx, &tok_len)) {
            if (!ensure_cap(&buf, &cap, len + 2u)) {
                free(buf);
                return 0;
            }
            buf[len++] = 0xffu;
            buf[len++] = idx;
            i += tok_len;
            continue;
        }
        size_t start = i++;
        while (i < size && i - start < 254u) {
            unsigned char next_idx = 0;
            uint16_t next_len = 0;
            if (find_dict(dict, dict_count, input, size, i, &next_idx, &next_len)) break;
            i++;
        }
        if (!ensure_cap(&buf, &cap, len + 1u + (i - start))) {
            free(buf);
            return 0;
        }
        buf[len++] = (unsigned char)(i - start);
        memcpy(buf + len, input + start, i - start);
        len += i - start;
    }
    *out = buf;
    *out_size = len;
    return 1;
}

static int decode_stream(const unsigned char *stream, size_t stream_size, const unsigned char **dict_ptrs, const uint16_t *dict_lens, size_t dict_count, unsigned char **out, size_t *out_size) {
    size_t cap = stream_size ? stream_size * 2u + 64u : 64u;
    size_t len = 0;
    unsigned char *buf = (unsigned char *)malloc(cap);
    if (!buf) return 0;
    for (size_t i = 0; i < stream_size;) {
        unsigned char marker = stream[i++];
        if (marker == 0xffu) {
            unsigned char idx;
            size_t tok_len;
            if (i >= stream_size) {
                free(buf);
                return 0;
            }
            idx = stream[i++];
            if ((size_t)idx >= dict_count) {
                free(buf);
                return 0;
            }
            tok_len = dict_lens[idx];
            if (!ensure_cap(&buf, &cap, len + tok_len)) {
                free(buf);
                return 0;
            }
            memcpy(buf + len, dict_ptrs[idx], tok_len);
            len += tok_len;
            continue;
        }
        if (marker == 0 || i + marker > stream_size) {
            free(buf);
            return 0;
        }
        if (!ensure_cap(&buf, &cap, len + marker)) {
            free(buf);
            return 0;
        }
        memcpy(buf + len, stream + i, marker);
        len += marker;
        i += marker;
    }
    *out = buf;
    *out_size = len;
    return 1;
}

int sm_native_pack_text(const unsigned char *input, size_t input_size, unsigned char **out, size_t *out_size, SmInfo *info) {
    Token dict[SM_MAX_DICT];
    size_t dict_count;
    unsigned char *stream = NULL;
    size_t stream_size = 0;
    size_t dict_bytes = 0;
    size_t total;
    size_t pos;
    if (!input || !out || !out_size) {
        set_error(info, "invalid SM native pack arguments");
        return 0;
    }
    memset(dict, 0, sizeof(dict));
    dict_count = build_dictionary(input, input_size, dict, SM_MAX_DICT);
    if (!encode_stream(input, input_size, dict, dict_count, &stream, &stream_size)) {
        set_error(info, "SM native encode failed");
        return 0;
    }
    for (size_t i = 0; i < dict_count; i++) dict_bytes += 2u + dict[i].len;
    total = 4u + 4u * 6u + 2u + dict_bytes + stream_size;
    *out = (unsigned char *)malloc(total ? total : 1u);
    if (!*out) {
        free(stream);
        set_error(info, "out of memory");
        return 0;
    }
    pos = 0;
    memcpy(*out + pos, SM3_MAGIC, 4u); pos += 4u;
    put_le32(*out + pos, 3u); pos += 4u;
    put_le32(*out + pos, (uint32_t)input_size); pos += 4u;
    put_le32(*out + pos, (uint32_t)stream_size); pos += 4u;
    put_le32(*out + pos, (uint32_t)stream_size); pos += 4u;
    put_le32(*out + pos, crc32_bytes(input, input_size)); pos += 4u;
    put_le32(*out + pos, crc32_bytes(stream, stream_size)); pos += 4u;
    put_le16(*out + pos, (uint16_t)dict_count); pos += 2u;
    for (size_t i = 0; i < dict_count; i++) {
        put_le16(*out + pos, dict[i].len); pos += 2u;
        memcpy(*out + pos, dict[i].ptr, dict[i].len); pos += dict[i].len;
    }
    memcpy(*out + pos, stream, stream_size); pos += stream_size;
    free(stream);
    *out_size = pos;
    if (info) {
        memset(info, 0, sizeof(*info));
        info->ok = 1;
        snprintf(info->codec, sizeof(info->codec), "%s", SM3_CODEC);
        info->version = 3;
        info->dictionary_entries = (int)dict_count;
        info->original_size = (uint32_t)input_size;
        info->token_stream_size = (uint32_t)stream_size;
        info->payload_size = (uint32_t)stream_size;
        info->compressed_size = (uint32_t)pos;
        info->checksum_ok = 1;
    }
    return 1;
}

static int read_sm3(const unsigned char *input, size_t input_size, const unsigned char ***dict_ptrs_out, uint16_t **dict_lens_out, size_t *dict_count_out, const unsigned char **stream_out, size_t *stream_size_out, SmInfo *info) {
    size_t pos = 0;
    uint32_t version, original_size, token_stream_size, payload_size, text_crc, token_crc;
    uint16_t dict_count;
    const unsigned char **dict_ptrs;
    uint16_t *dict_lens;
    if (!input || input_size < 30u || memcmp(input, SM3_MAGIC, 4u) != 0) {
        set_error(info, "not an SM3 payload");
        return 0;
    }
    pos += 4u;
    version = le32(input + pos); pos += 4u;
    original_size = le32(input + pos); pos += 4u;
    token_stream_size = le32(input + pos); pos += 4u;
    payload_size = le32(input + pos); pos += 4u;
    text_crc = le32(input + pos); pos += 4u;
    token_crc = le32(input + pos); pos += 4u;
    dict_count = le16(input + pos); pos += 2u;
    if (version != 3u || dict_count > SM_MAX_DICT) {
        set_error(info, "unsupported SM3 header");
        return 0;
    }
    dict_ptrs = (const unsigned char **)calloc(dict_count ? dict_count : 1u, sizeof(unsigned char *));
    dict_lens = (uint16_t *)calloc(dict_count ? dict_count : 1u, sizeof(uint16_t));
    if (!dict_ptrs || !dict_lens) {
        free(dict_ptrs);
        free(dict_lens);
        set_error(info, "out of memory");
        return 0;
    }
    for (uint16_t i = 0; i < dict_count; i++) {
        uint16_t len;
        if (pos + 2u > input_size) {
            free(dict_ptrs); free(dict_lens); set_error(info, "truncated SM3 dictionary"); return 0;
        }
        len = le16(input + pos); pos += 2u;
        if (len == 0 || pos + len > input_size) {
            free(dict_ptrs); free(dict_lens); set_error(info, "invalid SM3 dictionary"); return 0;
        }
        dict_lens[i] = len;
        dict_ptrs[i] = input + pos;
        pos += len;
    }
    if (payload_size != token_stream_size || pos + payload_size != input_size) {
        free(dict_ptrs); free(dict_lens); set_error(info, "SM3 payload size mismatch"); return 0;
    }
    if (crc32_bytes(input + pos, payload_size) != token_crc) {
        free(dict_ptrs); free(dict_lens); set_error(info, "SM3 token checksum mismatch"); return 0;
    }
    if (info) {
        memset(info, 0, sizeof(*info));
        info->ok = 1;
        snprintf(info->codec, sizeof(info->codec), "%s", SM3_CODEC);
        info->version = 3;
        info->dictionary_entries = dict_count;
        info->original_size = original_size;
        info->token_stream_size = token_stream_size;
        info->payload_size = payload_size;
        info->compressed_size = (uint32_t)input_size;
        info->checksum_ok = 1;
    }
    (void)text_crc;
    *dict_ptrs_out = dict_ptrs;
    *dict_lens_out = dict_lens;
    *dict_count_out = dict_count;
    *stream_out = input + pos;
    *stream_size_out = payload_size;
    return 1;
}

int sm_native_unpack_bytes(const unsigned char *input, size_t input_size, unsigned char **out, size_t *out_size, SmInfo *info) {
    const unsigned char **dict_ptrs = NULL;
    uint16_t *dict_lens = NULL;
    size_t dict_count = 0;
    const unsigned char *stream = NULL;
    size_t stream_size = 0;
    uint32_t expected_crc;
    if (!read_sm3(input, input_size, &dict_ptrs, &dict_lens, &dict_count, &stream, &stream_size, info)) return 0;
    expected_crc = le32(input + 20u);
    if (!decode_stream(stream, stream_size, dict_ptrs, dict_lens, dict_count, out, out_size)) {
        free(dict_ptrs); free(dict_lens); set_error(info, "SM3 decode failed"); return 0;
    }
    free(dict_ptrs);
    free(dict_lens);
    if (info && info->original_size != (uint32_t)*out_size) {
        free(*out); *out = NULL; *out_size = 0; set_error(info, "SM3 original size mismatch"); return 0;
    }
    if (crc32_bytes(*out, *out_size) != expected_crc) {
        free(*out); *out = NULL; *out_size = 0; set_error(info, "SM3 text checksum mismatch"); return 0;
    }
    return 1;
}

int sm_native_inspect_bytes(const unsigned char *input, size_t input_size, SmInfo *info) {
    const unsigned char **dict_ptrs = NULL;
    uint16_t *dict_lens = NULL;
    size_t dict_count = 0;
    const unsigned char *stream = NULL;
    size_t stream_size = 0;
    int ok = read_sm3(input, input_size, &dict_ptrs, &dict_lens, &dict_count, &stream, &stream_size, info);
    (void)stream;
    (void)stream_size;
    free(dict_ptrs);
    free(dict_lens);
    return ok;
}
