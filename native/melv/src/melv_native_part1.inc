static uint16_t le16(const unsigned char *p) {
    return (uint16_t)(p[0] | (p[1] << 8));
}

static uint32_t le32(const unsigned char *p) {
    return (uint32_t)(p[0] | (p[1] << 8) | (p[2] << 16) | (p[3] << 24));
}

static void write_le32(FILE *f, uint32_t v) {
    unsigned char b[4];
    b[0] = (unsigned char)(v & 0xffu);
    b[1] = (unsigned char)((v >> 8) & 0xffu);
    b[2] = (unsigned char)((v >> 16) & 0xffu);
    b[3] = (unsigned char)((v >> 24) & 0xffu);
    fwrite(b, 1, 4, f);
}

static void set_error(MelvInfo *out, const char *msg) {
    out->ok = 0;
    out->native_supported = 0;
    snprintf(out->error, sizeof(out->error), "%s", msg);
}

static int read_file(const char *path, unsigned char **data, size_t *size) {
    FILE *f = fopen(path, "rb");
    long n;
    if (!f) {
        return 0;
    }
    if (fseek(f, 0, SEEK_END) != 0) {
        fclose(f);
        return 0;
    }
    n = ftell(f);
    if (n < 0) {
        fclose(f);
        return 0;
    }
    if (fseek(f, 0, SEEK_SET) != 0) {
        fclose(f);
        return 0;
    }
    *data = (unsigned char *)malloc((size_t)n);
    if (!*data) {
        fclose(f);
        return 0;
    }
    if (fread(*data, 1, (size_t)n, f) != (size_t)n) {
        free(*data);
        fclose(f);
        return 0;
    }
    fclose(f);
    *size = (size_t)n;
    return 1;
}

static void skip_ppm_space_and_comments(const unsigned char *data, size_t size, size_t *pos) {
    for (;;) {
        while (*pos < size && (data[*pos] == ' ' || data[*pos] == '\t' || data[*pos] == '\r' || data[*pos] == '\n')) {
            (*pos)++;
        }
        if (*pos < size && data[*pos] == '#') {
            while (*pos < size && data[*pos] != '\r' && data[*pos] != '\n') {
                (*pos)++;
            }
            continue;
        }
        break;
    }
}

static int read_ppm_token(const unsigned char *data, size_t size, size_t *pos, char *out, size_t out_size) {
    size_t start;
    size_t len;
    skip_ppm_space_and_comments(data, size, pos);
    start = *pos;
    while (*pos < size && data[*pos] != ' ' && data[*pos] != '\t' && data[*pos] != '\r' && data[*pos] != '\n') {
        (*pos)++;
    }
    if (*pos == start) {
        return 0;
    }
    len = *pos - start;
    if (len >= out_size) {
        len = out_size - 1;
    }
    memcpy(out, data + start, len);
    out[len] = '\0';
    return 1;
}

static int read_ppm_file(const char *path, int *width, int *height, unsigned char **pixels, size_t *pixel_size, char *error, size_t error_size) {
    unsigned char *data = NULL;
    size_t size = 0;
    size_t pos = 0;
    char tok[64];
    long w;
    long h;
    long maxv;
    if (!read_file(path, &data, &size)) {
        snprintf(error, error_size, "cannot read PPM frame: %s", path);
        return 0;
    }
    if (!read_ppm_token(data, size, &pos, tok, sizeof(tok)) || strcmp(tok, "P6") != 0) {
        snprintf(error, error_size, "unsupported image format for native MELV: %s (expected PPM P6)", path);
        free(data);
        return 0;
    }
    if (!read_ppm_token(data, size, &pos, tok, sizeof(tok))) {
        snprintf(error, error_size, "invalid PPM width: %s", path);
        free(data);
        return 0;
    }
    w = strtol(tok, NULL, 10);
    if (!read_ppm_token(data, size, &pos, tok, sizeof(tok))) {
        snprintf(error, error_size, "invalid PPM height: %s", path);
        free(data);
        return 0;
    }
    h = strtol(tok, NULL, 10);
    if (!read_ppm_token(data, size, &pos, tok, sizeof(tok))) {
        snprintf(error, error_size, "invalid PPM max value: %s", path);
        free(data);
        return 0;
    }
    maxv = strtol(tok, NULL, 10);
    if (w <= 0 || h <= 0 || maxv != 255) {
        snprintf(error, error_size, "unsupported PPM header: %s", path);
        free(data);
        return 0;
    }
    if (pos < size && (data[pos] == ' ' || data[pos] == '\t' || data[pos] == '\r' || data[pos] == '\n')) {
        pos++;
    }
    *pixel_size = (size_t)w * (size_t)h * 3u;
    if (size - pos != *pixel_size) {
        snprintf(error, error_size, "PPM pixel data size mismatch: %s", path);
        free(data);
        return 0;
    }
    *pixels = (unsigned char *)malloc(*pixel_size);
    if (!*pixels) {
        snprintf(error, error_size, "out of memory");
        free(data);
        return 0;
    }
    memcpy(*pixels, data + pos, *pixel_size);
    *width = (int)w;
    *height = (int)h;
    free(data);
    return 1;
}

static int rle_encode_rgb(const unsigned char *pixels, size_t pixel_size, unsigned char **payload, uint32_t *payload_len) {
    size_t total = pixel_size / 3u;
    size_t idx = 0;
    size_t cap = total ? total * 4u : 4u;
    size_t len = 0;
    unsigned char *out = (unsigned char *)malloc(cap);
    if (!out) {
        return 0;
    }
    while (idx < total) {
        size_t base = idx * 3u;
        unsigned char r = pixels[base];
        unsigned char g = pixels[base + 1u];
        unsigned char b = pixels[base + 2u];
        unsigned int run = 1;
        while (idx + run < total && run < 255u) {
            size_t p = (idx + run) * 3u;
            if (pixels[p] != r || pixels[p + 1u] != g || pixels[p + 2u] != b) {
                break;
            }
            run++;
        }
        out[len++] = (unsigned char)run;
        out[len++] = r;
        out[len++] = g;
        out[len++] = b;
        idx += run;
    }
    *payload = out;
    *payload_len = (uint32_t)len;
    return 1;
}

static int rle_decode_rgb(const unsigned char *payload, uint32_t payload_len, uint32_t expected_pixels, unsigned char **pixels, size_t *pixel_size) {
    size_t out_size = (size_t)expected_pixels * 3u;
    size_t pos = 0;
    size_t out_pos = 0;
    unsigned char *out;
    if (payload_len % 4u != 0u) {
        return 0;
    }
    out = (unsigned char *)malloc(out_size ? out_size : 1u);
    if (!out) {
        return 0;
    }
    while (pos < payload_len) {
        unsigned int run = payload[pos++];
        unsigned char r = payload[pos++];
        unsigned char g = payload[pos++];
        unsigned char b = payload[pos++];
        if (run == 0 || out_pos + ((size_t)run * 3u) > out_size) {
            free(out);
            return 0;
        }
        for (unsigned int i = 0; i < run; i++) {
            out[out_pos++] = r;
            out[out_pos++] = g;
            out[out_pos++] = b;
        }
    }
    if (out_pos != out_size) {
        free(out);
        return 0;
    }
    *pixels = out;
    *pixel_size = out_size;
    return 1;
}

