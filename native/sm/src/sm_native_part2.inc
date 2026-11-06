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
