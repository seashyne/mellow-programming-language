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

