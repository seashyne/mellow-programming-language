/* ── URL parsing, sockets, and the HTTP/1.1 response parser ─────────────── */

static int pk_net_ready = 0;

static int pk_net_timeout_s(void) {
    const char *raw = getenv("MELLOW_HTTP_TIMEOUT");
    int seconds = raw && *raw ? atoi(raw) : PKG_NET_DEFAULT_TIMEOUT;
    if (seconds <= 0) seconds = PKG_NET_DEFAULT_TIMEOUT;
    if (seconds > 300) seconds = 300;
    return seconds;
}

static int pk_net_init(char *err, size_t cap) {
#ifdef _WIN32
    WSADATA wsa;
    if (pk_net_ready) return 1;
    if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) {
        snprintf(err, cap, "winsock initialization failed");
        return 0;
    }
#else
    (void)err;
    (void)cap;
#endif
    pk_net_ready = 1;
    return 1;
}

static int pk_url_parse(const char *url, PkgUrl *out) {
    const char *rest;
    const char *slash;
    const char *host_end;
    size_t host_len;
    memset(out, 0, sizeof *out);
    if (!url) return 0;
    if (!strncmp(url, "https://", 8)) {
        out->https = 1;
        rest = url + 8;
    } else if (!strncmp(url, "http://", 7)) {
        out->https = 0;
        rest = url + 7;
    } else {
        return 0;
    }
    slash = strchr(rest, '/');
    host_end = slash ? slash : rest + strlen(rest);
    host_len = (size_t)(host_end - rest);
    if (!host_len || host_len >= sizeof out->host) return 0;
    memcpy(out->host, rest, host_len);
    out->host[host_len] = '\0';
    if (out->host[0] == '[') {
        char *close = strchr(out->host, ']');
        if (!close || (close[1] && close[1] != ':')) return 0;
        if (close[1] == ':') {
            if (!close[2] || strlen(close + 2) >= sizeof out->port) return 0;
            snprintf(out->port, sizeof out->port, "%s", close + 2);
        }
        *close = '\0';
        memmove(out->host, out->host + 1, strlen(out->host));
    } else {
        char *colon = strchr(out->host, ':');
        if (colon) {
            *colon++ = '\0';
            if (!*colon || strlen(colon) >= sizeof out->port) return 0;
            snprintf(out->port, sizeof out->port, "%s", colon);
        }
    }
    if (!out->host[0]) return 0;
    if (!out->port[0]) snprintf(out->port, sizeof out->port, "%s", out->https ? "443" : "80");
    if (slash && slash[1]) snprintf(out->path, sizeof out->path, "%s", slash);
    else snprintf(out->path, sizeof out->path, "/");
    return 1;
}

static int pk_socket_nonblocking(PkgSocket fd, int enable) {
#ifdef _WIN32
    u_long mode = enable ? 1u : 0u;
    return ioctlsocket(fd, FIONBIO, &mode) == 0;
#else
    int flags = fcntl(fd, F_GETFL, 0);
    if (flags < 0) return 0;
    flags = enable ? (flags | O_NONBLOCK) : (flags & ~O_NONBLOCK);
    return fcntl(fd, F_SETFL, flags) == 0;
#endif
}

static void pk_socket_timeouts(PkgSocket fd, int seconds) {
#ifdef _WIN32
    DWORD ms = (DWORD)seconds * 1000u;
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, (const char *)&ms, (int)sizeof ms);
    setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, (const char *)&ms, (int)sizeof ms);
#else
    struct timeval tv;
    tv.tv_sec = seconds;
    tv.tv_usec = 0;
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv);
    setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof tv);
#ifdef SO_NOSIGPIPE
    {
        int on = 1;
        setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &on, sizeof on);
    }
#endif
#endif
}

static int pk_socket_in_progress(void) {
#ifdef _WIN32
    int code = WSAGetLastError();
    return code == WSAEWOULDBLOCK || code == WSAEINPROGRESS;
#else
    return errno == EINPROGRESS || errno == EWOULDBLOCK;
#endif
}

static PkgSocket pk_net_connect(const char *host, const char *port, char *err, size_t cap) {
    struct addrinfo hints;
    struct addrinfo *found = NULL;
    struct addrinfo *it;
    PkgSocket fd = PKG_INVALID_SOCKET;
    int seconds = pk_net_timeout_s();
    if (!pk_net_init(err, cap)) return PKG_INVALID_SOCKET;
    memset(&hints, 0, sizeof hints);
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    if (getaddrinfo(host, port, &hints, &found) != 0 || !found) {
        snprintf(err, cap, "cannot resolve host: %s", host);
        return PKG_INVALID_SOCKET;
    }
    for (it = found; it && fd == PKG_INVALID_SOCKET; it = it->ai_next) {
        int connected = 0;
        fd = socket(it->ai_family, it->ai_socktype, it->ai_protocol);
        if (fd == PKG_INVALID_SOCKET) continue;
        if (!pk_socket_nonblocking(fd, 1)) {
            pk_socket_close(fd);
            fd = PKG_INVALID_SOCKET;
            continue;
        }
        if (connect(fd, it->ai_addr, (int)it->ai_addrlen) == 0) {
            connected = 1;
        } else if (pk_socket_in_progress()) {
            fd_set writable;
            fd_set failed;
            struct timeval tv;
            int ready;
            FD_ZERO(&writable);
            FD_SET(fd, &writable);
            FD_ZERO(&failed);
            FD_SET(fd, &failed);
            tv.tv_sec = seconds;
            tv.tv_usec = 0;
            ready = select((int)fd + 1, NULL, &writable, &failed, &tv);
            if (ready > 0) {
                int so_error = 0;
#ifdef _WIN32
                int so_len = (int)sizeof so_error;
#else
                socklen_t so_len = (socklen_t)sizeof so_error;
#endif
                if (getsockopt(fd, SOL_SOCKET, SO_ERROR, (char *)&so_error, &so_len) == 0 && so_error == 0)
                    connected = 1;
            }
        }
        if (connected) {
            pk_socket_nonblocking(fd, 0);
            pk_socket_timeouts(fd, seconds);
        } else {
            pk_socket_close(fd);
            fd = PKG_INVALID_SOCKET;
        }
    }
    freeaddrinfo(found);
    if (fd == PKG_INVALID_SOCKET) snprintf(err, cap, "cannot connect to %s:%s", host, port);
    return fd;
}

static int pk_send_all(PkgSocket fd, const char *data, size_t len, char *err, size_t cap) {
    while (len) {
        int want = len > 1048576u ? 1048576 : (int)len;
        int sent;
#ifdef MSG_NOSIGNAL
        sent = send(fd, data, want, MSG_NOSIGNAL);
#else
        sent = send(fd, data, want, 0);
#endif
        if (sent <= 0) {
            snprintf(err, cap, "request send failed");
            return 0;
        }
        data += sent;
        len -= (size_t)sent;
    }
    return 1;
}

static int pk_read_all(PkgSocket fd, PkgBuf *out, char *err, size_t cap) {
    char chunk[8192];
    for (;;) {
        int got = recv(fd, chunk, (int)sizeof chunk, 0);
        if (got == 0) return 1;
        if (got < 0) {
#ifdef _WIN32
            int code = WSAGetLastError();
            snprintf(err, cap, code == WSAETIMEDOUT || code == WSAEWOULDBLOCK
                                  ? "response timed out" : "response read failed");
            return 0;
#else
            if (errno == EINTR) continue;
            snprintf(err, cap, errno == EAGAIN || errno == EWOULDBLOCK
                                  ? "response timed out" : "response read failed");
            return 0;
#endif
        }
        if (!pk_buf_put(out, chunk, (size_t)got)) {
            snprintf(err, cap, "out of memory while reading response");
            return 0;
        }
    }
}
