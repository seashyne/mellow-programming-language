#include "melv_native.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

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

int melv_native_pack_ppm_sequence(const char **frames, size_t frame_count, const char *output_path, double fps, MelvInfo *out) {
    FILE *f;
    uint32_t fps_num;
    int width = 0;
    int height = 0;
    memset(out, 0, sizeof(*out));
    out->native_supported = 1;
    snprintf(out->codec, sizeof(out->codec), "%s", "mellow-rgb-rle");
    if (!frames || frame_count == 0) {
        set_error(out, "native MELV encode needs at least one PPM frame");
        return 0;
    }
    if (fps <= 0.0) {
        set_error(out, "fps must be greater than zero");
        return 0;
    }
    f = fopen(output_path, "wb");
    if (!f) {
        set_error(out, "cannot create output MELV file");
        return 0;
    }
    fps_num = (uint32_t)(fps * 1000.0 + 0.5);
    fwrite("MELV2", 1, 5, f);
    write_le32(f, 1u);
    write_le32(f, 0u);
    write_le32(f, 0u);
    write_le32(f, fps_num);
    write_le32(f, 1000u);
    write_le32(f, (uint32_t)frame_count);
    for (size_t idx = 0; idx < frame_count; idx++) {
        unsigned char *pixels = NULL;
        unsigned char *payload = NULL;
        size_t pixel_size = 0;
        uint32_t payload_len = 0;
        int w = 0;
        int h = 0;
        char err[256];
        if (!read_ppm_file(frames[idx], &w, &h, &pixels, &pixel_size, err, sizeof(err))) {
            fclose(f);
            remove(output_path);
            set_error(out, err);
            return 0;
        }
        if (idx == 0) {
            width = w;
            height = h;
        } else if (w != width || h != height) {
            free(pixels);
            fclose(f);
            remove(output_path);
            set_error(out, "frame size mismatch");
            return 0;
        }
        if (!rle_encode_rgb(pixels, pixel_size, &payload, &payload_len)) {
            free(pixels);
            fclose(f);
            remove(output_path);
            set_error(out, "failed to encode MELV RLE payload");
            return 0;
        }
        write_le32(f, payload_len);
        fwrite(payload, 1, payload_len, f);
        free(payload);
        free(pixels);
    }
    if (fseek(f, 9, SEEK_SET) == 0) {
        write_le32(f, (uint32_t)width);
        write_le32(f, (uint32_t)height);
    }
    fclose(f);
    melv_native_inspect_file(output_path, out);
    return out->ok ? 1 : 0;
}

int melv_native_extract_ppm_frames(const char *input_path, const char *out_dir, MelvInfo *out) {
    unsigned char *buf = NULL;
    size_t size = 0;
    uint32_t version;
    uint32_t width;
    uint32_t height;
    uint32_t fps_num;
    uint32_t fps_den;
    uint32_t frames;
    size_t pos = 29;
    memset(out, 0, sizeof(*out));
    out->native_supported = 1;
    snprintf(out->codec, sizeof(out->codec), "%s", "mellow-rgb-rle");
    if (!read_file(input_path, &buf, &size)) {
        set_error(out, "cannot read file");
        return 0;
    }
    if (size < 29 || memcmp(buf, "MELV2", 5) != 0) {
        set_error(out, "not a supported native MELV2 file");
        free(buf);
        return 0;
    }
    version = le32(buf + 5);
    width = le32(buf + 9);
    height = le32(buf + 13);
    fps_num = le32(buf + 17);
    fps_den = le32(buf + 21);
    frames = le32(buf + 25);
    if (version != 1 || width == 0 || height == 0 || fps_num == 0 || fps_den == 0) {
        set_error(out, "invalid MELV2 header");
        free(buf);
        return 0;
    }
    for (uint32_t idx = 0; idx < frames; idx++) {
        uint32_t payload_len;
        unsigned char *pixels = NULL;
        size_t pixel_size = 0;
        char out_path[1024];
        FILE *f;
        if (pos + 4 > size) {
            set_error(out, "truncated MELV2 frame table");
            free(buf);
            return 0;
        }
        payload_len = le32(buf + pos);
        pos += 4;
        if (pos + payload_len > size) {
            set_error(out, "truncated MELV2 frame payload");
            free(buf);
            return 0;
        }
        if (!rle_decode_rgb(buf + pos, payload_len, width * height, &pixels, &pixel_size)) {
            set_error(out, "failed to decode MELV RLE payload");
            free(buf);
            return 0;
        }
        pos += payload_len;
        snprintf(out_path, sizeof(out_path), "%s/%06u.ppm", out_dir, idx);
        f = fopen(out_path, "wb");
        if (!f) {
            free(pixels);
            set_error(out, "cannot create output PPM frame");
            free(buf);
            return 0;
        }
        fprintf(f, "P6\n%u %u\n255\n", width, height);
        fwrite(pixels, 1, pixel_size, f);
        fclose(f);
        free(pixels);
    }
    out->ok = 1;
    out->width = (int)width;
    out->height = (int)height;
    out->fps = (double)fps_num / (double)fps_den;
    out->frames = (int)frames;
    out->expected_frames = (int)frames;
    out->bytes = (long long)size;
    free(buf);
    return 1;
}

static unsigned char *entry_data(unsigned char *buf, size_t size, uint32_t local_offset, uint32_t compressed_size) {
    uint16_t name_len;
    uint16_t extra_len;
    size_t data_offset;
    if ((size_t)local_offset + 30 > size || le32(buf + local_offset) != 0x04034b50u) {
        return NULL;
    }
    name_len = le16(buf + local_offset + 26);
    extra_len = le16(buf + local_offset + 28);
    data_offset = (size_t)local_offset + 30u + name_len + extra_len;
    if (data_offset + compressed_size > size) {
        return NULL;
    }
    return buf + data_offset;
}

static int json_string(const char *json, size_t len, const char *key, char *out, size_t out_size) {
    char needle[80];
    const char *p;
    const char *colon;
    const char *start;
    const char *end;
    snprintf(needle, sizeof(needle), "\"%s\"", key);
    p = strstr(json, needle);
    if (!p || p >= json + len) return 0;
    colon = strchr(p, ':');
    if (!colon || colon >= json + len) return 0;
    start = strchr(colon, '"');
    if (!start || start + 1 >= json + len) return 0;
    start++;
    end = strchr(start, '"');
    if (!end || end > json + len) return 0;
    {
        size_t n = (size_t)(end - start);
        if (n >= out_size) n = out_size - 1;
        memcpy(out, start, n);
        out[n] = '\0';
    }
    return 1;
}

static int json_number(const char *json, size_t len, const char *key, double *out) {
    char needle[80];
    const char *p;
    const char *colon;
    char *endp;
    snprintf(needle, sizeof(needle), "\"%s\"", key);
    p = strstr(json, needle);
    if (!p || p >= json + len) return 0;
    colon = strchr(p, ':');
    if (!colon || colon >= json + len) return 0;
    *out = strtod(colon + 1, &endp);
    return endp != colon + 1;
}

int melv_native_inspect_file(const char *path, MelvInfo *out) {
    unsigned char *buf = NULL;
    size_t size = 0;
    size_t min_eocd;
    size_t i;
    size_t eocd = (size_t)-1;
    uint16_t entry_count;
    uint32_t cd_size;
    uint32_t cd_offset;
    size_t p;
    int found_magic = 0;
    int found_manifest = 0;
    int unsupported_compression = 0;
    char *manifest = NULL;
    size_t manifest_len = 0;
    double num = 0.0;

    memset(out, 0, sizeof(*out));
    out->expected_frames = -1;
    out->native_supported = 1;

    if (!read_file(path, &buf, &size)) {
        set_error(out, "cannot read file");
        return 0;
    }
    out->bytes = (long long)size;
    if (size >= 29 && memcmp(buf, "MELV2", 5) == 0) {
        uint32_t version = le32(buf + 5);
        uint32_t width = le32(buf + 9);
        uint32_t height = le32(buf + 13);
        uint32_t fps_num = le32(buf + 17);
        uint32_t fps_den = le32(buf + 21);
        uint32_t frames = le32(buf + 25);
        size_t pos = 29;
        uint32_t idx;
        snprintf(out->codec, sizeof(out->codec), "%s", "mellow-rgb-rle");
        out->width = (int)width;
        out->height = (int)height;
        out->fps = fps_den ? ((double)fps_num / (double)fps_den) : 0.0;
        out->frames = (int)frames;
        out->expected_frames = (int)frames;
        if (version != 1 || width == 0 || height == 0 || fps_num == 0 || fps_den == 0) {
            set_error(out, "invalid MELV2 header");
            free(buf);
            return 0;
        }
        for (idx = 0; idx < frames; idx++) {
            uint32_t payload_len;
            if (pos + 4 > size) {
                set_error(out, "truncated MELV2 frame table");
                free(buf);
                return 0;
            }
            payload_len = le32(buf + pos);
            pos += 4;
            if (pos + payload_len > size) {
                set_error(out, "truncated MELV2 frame payload");
                free(buf);
                return 0;
            }
            pos += payload_len;
        }
        out->ok = 1;
        out->native_supported = 1;
        free(buf);
        return 1;
    }
    if (size < 22) {
        set_error(out, "not a zip-based MELV file");
        free(buf);
        return 0;
    }

    min_eocd = size > 66000 ? size - 66000 : 0;
    for (i = size - 22; i + 1 > min_eocd; i--) {
        if (le32(buf + i) == 0x06054b50u) {
            eocd = i;
            break;
        }
        if (i == 0) break;
    }
    if (eocd == (size_t)-1) {
        set_error(out, "missing zip end-of-central-directory");
        free(buf);
        return 0;
    }

    entry_count = le16(buf + eocd + 10);
    cd_size = le32(buf + eocd + 12);
    cd_offset = le32(buf + eocd + 16);
    if ((size_t)cd_offset + cd_size > size) {
        set_error(out, "invalid zip central directory");
        free(buf);
        return 0;
    }

    p = cd_offset;
    for (uint16_t idx = 0; idx < entry_count; idx++) {
        uint16_t method;
        uint32_t compressed_size;
        uint32_t local_offset;
        uint16_t name_len;
        uint16_t extra_len;
        uint16_t comment_len;
        const char *name;
        if (p + 46 > size || le32(buf + p) != 0x02014b50u) {
            set_error(out, "invalid zip central directory entry");
            free(manifest);
            free(buf);
            return 0;
        }
        method = le16(buf + p + 10);
        compressed_size = le32(buf + p + 20);
        name_len = le16(buf + p + 28);
        extra_len = le16(buf + p + 30);
        comment_len = le16(buf + p + 32);
        local_offset = le32(buf + p + 42);
        name = (const char *)(buf + p + 46);
        if (p + 46u + name_len + extra_len + comment_len > size) {
            set_error(out, "invalid zip entry name");
            free(manifest);
            free(buf);
            return 0;
        }
        if (name_len == 9 && memcmp(name, "magic.bin", 9) == 0) {
            unsigned char *data;
            if (method != 0) {
                unsupported_compression = 1;
            } else {
                data = entry_data(buf, size, local_offset, compressed_size);
                found_magic = data && compressed_size == 5 && memcmp(data, "MELV1", 5) == 0;
            }
        } else if (name_len == 13 && memcmp(name, "manifest.json", 13) == 0) {
            unsigned char *data;
            if (method != 0) {
                unsupported_compression = 1;
            } else {
                data = entry_data(buf, size, local_offset, compressed_size);
                if (data) {
                    manifest = (char *)malloc((size_t)compressed_size + 1u);
                    if (!manifest) {
                        set_error(out, "out of memory");
                        free(buf);
                        return 0;
                    }
                    memcpy(manifest, data, compressed_size);
                    manifest[compressed_size] = '\0';
                    manifest_len = compressed_size;
                    found_manifest = 1;
                }
            }
        } else if (name_len > 11 && memcmp(name, "frames/", 7) == 0 && memcmp(name + name_len - 4, ".jpg", 4) == 0) {
            out->frames++;
            if (method != 0) {
                unsupported_compression = 1;
            }
        }
        p += 46u + name_len + extra_len + comment_len;
    }

    if (unsupported_compression) {
        set_error(out, "native MELV supports stored zip entries only; re-encode with current mellow melv encode");
        free(manifest);
        free(buf);
        return 0;
    }
    if (!found_magic) {
        set_error(out, "missing or invalid MELV magic");
        free(manifest);
        free(buf);
        return 0;
    }
    if (!found_manifest || !manifest) {
        set_error(out, "missing manifest.json");
        free(buf);
        return 0;
    }

    if (!json_string(manifest, manifest_len, "codec", out->codec, sizeof(out->codec))) {
        snprintf(out->warning, sizeof(out->warning), "%s", "manifest missing codec");
    }
    if (json_number(manifest, manifest_len, "fps", &num)) out->fps = num;
    if (json_number(manifest, manifest_len, "width", &num)) out->width = (int)num;
    if (json_number(manifest, manifest_len, "height", &num)) out->height = (int)num;
    if (json_number(manifest, manifest_len, "frames", &num)) out->expected_frames = (int)num;

    out->ok = 1;
    if (strcmp(out->codec, "jpeg-sequence") != 0 || out->fps <= 0 || out->width <= 0 || out->height <= 0) {
        out->ok = 0;
        snprintf(out->error, sizeof(out->error), "%s", "invalid MELV manifest fields");
    } else if (out->expected_frames >= 0 && out->expected_frames != out->frames) {
        out->ok = 0;
        snprintf(out->error, sizeof(out->error), "%s", "manifest frame count does not match archive");
    }

    free(manifest);
    free(buf);
    return out->ok ? 1 : 0;
}
