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
