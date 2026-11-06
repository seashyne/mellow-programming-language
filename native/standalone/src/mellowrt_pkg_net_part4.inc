/* ── POSIX HTTPS through libcurl, and the request dispatcher ─────────────── */

#if defined(MELLOW_HAVE_LIBCURL) && !defined(_WIN32)

#include <curl/curl.h>

static size_t pk_curl_collect(char *data, size_t size, size_t count, void *user) {
    size_t len = size * count;
    PkgBuf *body = (PkgBuf *)user;
    return pk_buf_put(body, data, len) ? len : 0;
}

static int pk_https_curl(const char *url, const char *token, PkgBuf *body,
                         int *status, char *err, size_t cap) {
    static int curl_ready = 0;
    CURL *handle;
    struct curl_slist *headers = NULL;
    CURLcode result;
    long http_status = 0;
    int seconds = pk_net_timeout_s();
    int ok = 0;
    if (!curl_ready) {
        if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) {
            snprintf(err, cap, "libcurl initialization failed");
            return 0;
        }
        curl_ready = 1;
    }
    handle = curl_easy_init();
    if (!handle) {
        snprintf(err, cap, "libcurl handle unavailable");
        return 0;
    }
    headers = curl_slist_append(headers, "Accept: application/json");
    if (token && *token) {
        PkgBuf line = {0};
        pk_buf_puts(&line, "Authorization: Bearer ");
        pk_buf_puts(&line, token);
        if (line.ptr) headers = curl_slist_append(headers, line.ptr);
        pk_buf_free(&line);
    }
    curl_easy_setopt(handle, CURLOPT_URL, url);
    curl_easy_setopt(handle, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(handle, CURLOPT_USERAGENT, "MellowCLI");
    curl_easy_setopt(handle, CURLOPT_FOLLOWLOCATION, 1L);
    curl_easy_setopt(handle, CURLOPT_MAXREDIRS, (long)PKG_NET_MAX_REDIRECTS);
    curl_easy_setopt(handle, CURLOPT_CONNECTTIMEOUT, (long)seconds);
    curl_easy_setopt(handle, CURLOPT_TIMEOUT, (long)seconds);
    curl_easy_setopt(handle, CURLOPT_WRITEFUNCTION, pk_curl_collect);
    curl_easy_setopt(handle, CURLOPT_WRITEDATA, body);
    result = curl_easy_perform(handle);
    if (result != CURLE_OK) {
        snprintf(err, cap, "https: %s", curl_easy_strerror(result));
        goto done;
    }
    curl_easy_getinfo(handle, CURLINFO_RESPONSE_CODE, &http_status);
    *status = (int)http_status;
    ok = 1;
done:
    curl_slist_free_all(headers);
    curl_easy_cleanup(handle);
    return ok;
}

#endif

static int pk_net_get(const char *url, const char *token, PkgBuf *body, int *status,
                      char *err, size_t cap) {
    char current[PKG_PATH_MAX * 2];
    PkgUrl parsed;
    int redirects = 0;
    if (!url || strlen(url) >= sizeof current) {
        snprintf(err, cap, "registry url is too long");
        return 0;
    }
    snprintf(current, sizeof current, "%s", url);
    for (;;) {
        if (!pk_url_parse(current, &parsed)) {
            snprintf(err, cap, "unsupported registry url: %s", current);
            return 0;
        }
        body->len = 0;
        if (body->ptr) body->ptr[0] = '\0';
        if (parsed.https) {
#ifdef _WIN32
            if (!pk_https_winhttp(&parsed, token, body, status, err, cap)) return 0;
#elif defined(MELLOW_HAVE_LIBCURL)
            if (!pk_https_curl(current, token, body, status, err, cap)) return 0;
#else
            snprintf(err, cap, "https is unavailable in this build: rebuild with libcurl");
            return 0;
#endif
        } else {
            char location[PKG_PATH_MAX * 2];
            location[0] = '\0';
            if (!pk_http_socket_get(&parsed, token, body, status, location, sizeof location, err, cap))
                return 0;
            if ((*status == 301 || *status == 302 || *status == 303 || *status == 307 || *status == 308) &&
                location[0]) {
                if (redirects++ >= PKG_NET_MAX_REDIRECTS) {
                    snprintf(err, cap, "too many redirects");
                    return 0;
                }
                if (strncmp(location, "http://", 7) && strncmp(location, "https://", 8)) {
                    snprintf(err, cap, "relative redirects are not supported: %s", location);
                    return 0;
                }
                snprintf(current, sizeof current, "%s", location);
                continue;
            }
        }
        return 1;
    }
}
