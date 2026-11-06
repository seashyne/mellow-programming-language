/* ── HTTP response parsing and the raw-socket GET ───────────────────────── */

static const char *pk_ci_find(const char *hay, const char *end, const char *needle) {
    size_t len = strlen(needle);
    const char *p;
    if (!len) return hay;
    for (p = hay; p + len <= end; ++p) {
        size_t i;
        for (i = 0; i < len; ++i) {
            if (tolower((unsigned char)p[i]) != tolower((unsigned char)needle[i])) break;
        }
        if (i == len) return p;
    }
    return NULL;
}

/* Header names are matched at the start of a line so that, for example,
   Content-Location cannot be mistaken for Location. */
static int pk_header_name_match(const char *start, const char *stop, const char *name) {
    size_t len = (size_t)(stop - start);
    size_t i;
    while (len && (start[len - 1] == ' ' || start[len - 1] == '\t')) --len;
    if (len != strlen(name)) return 0;
    for (i = 0; i < len; ++i) {
        if (tolower((unsigned char)start[i]) != tolower((unsigned char)name[i])) return 0;
    }
    return 1;
}

static int pk_header_value(const char *headers, const char *end, const char *name,
                           char *out, size_t cap) {
    const char *p = headers;
    if (!out || !cap) return 0;
    out[0] = '\0';
    while (p < end) {
        const char *line_end = (const char *)memchr(p, '\n', (size_t)(end - p));
        const char *colon;
        const char *start;
        size_t len;
        if (!line_end) line_end = end;
        colon = (const char *)memchr(p, ':', (size_t)(line_end - p));
        if (colon && pk_header_name_match(p, colon, name)) {
            start = colon + 1;
            while (start < line_end && (*start == ' ' || *start == '\t' || *start == '\r')) ++start;
            len = (size_t)(line_end - start);
            while (len && (start[len - 1] == '\r' || start[len - 1] == ' ' || start[len - 1] == '\t')) --len;
            if (len >= cap) len = cap - 1;
            memcpy(out, start, len);
            out[len] = '\0';
            return 1;
        }
        if (line_end == end) break;
        p = line_end + 1;
    }
    return 0;
}

static int pk_http_dechunk(const char *p, const char *end, PkgBuf *out) {
    while (p < end) {
        char *stop = NULL;
        unsigned long size = strtoul(p, &stop, 16);
        if (!stop || stop == p) return 0;
        p = stop;
        while (p < end && *p != '\n') ++p;
        if (p < end) ++p;
        if (size == 0) return 1;
        if ((size_t)(end - p) < (size_t)size) return 0;
        if (!pk_buf_put(out, p, (size_t)size)) return 0;
        p += size;
        while (p < end && (*p == '\r' || *p == '\n')) ++p;
    }
    return 1;
}

static int pk_http_parse(PkgBuf *raw, int *status, PkgBuf *body,
                         char *location, size_t loc_cap, char *err, size_t cap) {
    const char *data = raw->ptr ? raw->ptr : "";
    const char *end = data + raw->len;
    const char *first_end = (const char *)memchr(data, '\n', raw->len);
    const char *sep = NULL;
    const char *body_start;
    char chunked[32];
    char length[32];
    size_t i;
    if (!first_end || sscanf(data, "HTTP/%*d.%*d %d", status) != 1) {
        snprintf(err, cap, "malformed http response");
        return 0;
    }
    for (i = 0; i + 3 < raw->len; ++i) {
        if (data[i] == '\r' && data[i + 1] == '\n' && data[i + 2] == '\r' && data[i + 3] == '\n') {
            sep = data + i;
            break;
        }
        if (data[i] == '\n' && data[i + 1] == '\n') {
            sep = data + i;
            break;
        }
    }
    if (!sep) {
        snprintf(err, cap, "http response has no header terminator");
        return 0;
    }
    body_start = (sep[1] == '\n' && sep[2] == '\r') ? sep + 4 : sep + 2;
    chunked[0] = '\0';
    length[0] = '\0';
    if (location && loc_cap) location[0] = '\0';
    if (location) pk_header_value(first_end, sep, "location", location, loc_cap);
    pk_header_value(first_end, sep, "transfer-encoding", chunked, sizeof chunked);
    pk_header_value(first_end, sep, "content-length", length, sizeof length);
    if (chunked[0] && pk_ci_find(chunked, chunked + strlen(chunked), "chunked")) {
        if (!pk_http_dechunk(body_start, end, body)) {
            snprintf(err, cap, "malformed chunked response body");
            return 0;
        }
        return 1;
    }
    if (length[0]) {
        unsigned long want = strtoul(length, NULL, 10);
        if ((size_t)want < (size_t)(end - body_start)) {
            if (!pk_buf_put(body, body_start, (size_t)want)) {
                snprintf(err, cap, "out of memory while buffering response");
                return 0;
            }
            return 1;
        }
    }
    if (!pk_buf_put(body, body_start, (size_t)(end - body_start))) {
        snprintf(err, cap, "out of memory while buffering response");
        return 0;
    }
    return 1;
}

static int pk_http_socket_get(const PkgUrl *url, const char *token, PkgBuf *body, int *status,
                              char *location, size_t loc_cap, char *err, size_t cap) {
    PkgSocket fd;
    PkgBuf request = {0};
    PkgBuf raw = {0};
    int ok = 0;
    fd = pk_net_connect(url->host, url->port, err, cap);
    if (fd == PKG_INVALID_SOCKET) return 0;
    pk_buf_puts(&request, "GET ");
    pk_buf_puts(&request, url->path);
    pk_buf_puts(&request, " HTTP/1.1\r\nHost: ");
    if (strchr(url->host, ':')) pk_buf_putc(&request, '[');
    pk_buf_puts(&request, url->host);
    if (strchr(url->host, ':')) pk_buf_putc(&request, ']');
    pk_buf_putc(&request, ':');
    pk_buf_puts(&request, url->port);
    pk_buf_puts(&request, "\r\nUser-Agent: MellowCLI\r\nAccept: application/json\r\nConnection: close\r\n");
    if (token && *token) {
        pk_buf_puts(&request, "Authorization: Bearer ");
        pk_buf_puts(&request, token);
        pk_buf_puts(&request, "\r\n");
    }
    pk_buf_puts(&request, "\r\n");
    if (!request.ptr) {
        snprintf(err, cap, "out of memory while building request");
        goto done;
    }
    if (!pk_send_all(fd, request.ptr, request.len, err, cap)) goto done;
    if (!pk_read_all(fd, &raw, err, cap)) goto done;
    if (!pk_http_parse(&raw, status, body, location, loc_cap, err, cap)) goto done;
    ok = 1;
done:
    pk_buf_free(&request);
    pk_buf_free(&raw);
    pk_socket_close(fd);
    return ok;
}
