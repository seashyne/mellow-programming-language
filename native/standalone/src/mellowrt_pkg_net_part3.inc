/* ── HTTPS through the platform TLS stack ───────────────────────────────── */
/* WinHTTP is loaded from winhttp.dll at call time so every existing native
   build list keeps linking without an extra import library. */

#ifdef _WIN32

#include <winhttp.h>

typedef struct {
    HMODULE module;
    HINTERNET (WINAPI *open)(LPCWSTR, DWORD, LPCWSTR, LPCWSTR, DWORD);
    BOOL (WINAPI *close)(HINTERNET);
    HINTERNET (WINAPI *connect)(HINTERNET, LPCWSTR, INTERNET_PORT, DWORD);
    HINTERNET (WINAPI *open_request)(HINTERNET, LPCWSTR, LPCWSTR, LPCWSTR, LPCWSTR, LPCWSTR *, DWORD);
    BOOL (WINAPI *add_headers)(HINTERNET, LPCWSTR, DWORD, DWORD);
    BOOL (WINAPI *set_timeouts)(HINTERNET, int, int, int, int);
    BOOL (WINAPI *send)(HINTERNET, LPCWSTR, DWORD, LPVOID, DWORD, DWORD, DWORD_PTR);
    BOOL (WINAPI *receive)(HINTERNET, LPVOID);
    BOOL (WINAPI *query)(HINTERNET, DWORD, LPCWSTR, LPVOID, LPDWORD, LPDWORD);
    BOOL (WINAPI *read)(HINTERNET, LPVOID, DWORD, LPDWORD);
} PkgWinHttp;

static PkgWinHttp pk_winhttp;

static int pk_winhttp_load(char *err, size_t cap) {
    if (pk_winhttp.module) return 1;
    memset(&pk_winhttp, 0, sizeof pk_winhttp);
    pk_winhttp.module = LoadLibraryA("winhttp.dll");
    if (!pk_winhttp.module) {
        snprintf(err, cap, "winhttp: library unavailable");
        return 0;
    }
    pk_winhttp.open = (HINTERNET (WINAPI *)(LPCWSTR, DWORD, LPCWSTR, LPCWSTR, DWORD))
        GetProcAddress(pk_winhttp.module, "WinHttpOpen");
    pk_winhttp.close = (BOOL (WINAPI *)(HINTERNET))GetProcAddress(pk_winhttp.module, "WinHttpCloseHandle");
    pk_winhttp.connect = (HINTERNET (WINAPI *)(HINTERNET, LPCWSTR, INTERNET_PORT, DWORD))
        GetProcAddress(pk_winhttp.module, "WinHttpConnect");
    pk_winhttp.open_request = (HINTERNET (WINAPI *)(HINTERNET, LPCWSTR, LPCWSTR, LPCWSTR, LPCWSTR, LPCWSTR *, DWORD))
        GetProcAddress(pk_winhttp.module, "WinHttpOpenRequest");
    pk_winhttp.add_headers = (BOOL (WINAPI *)(HINTERNET, LPCWSTR, DWORD, DWORD))
        GetProcAddress(pk_winhttp.module, "WinHttpAddRequestHeaders");
    pk_winhttp.set_timeouts = (BOOL (WINAPI *)(HINTERNET, int, int, int, int))
        GetProcAddress(pk_winhttp.module, "WinHttpSetTimeouts");
    pk_winhttp.send = (BOOL (WINAPI *)(HINTERNET, LPCWSTR, DWORD, LPVOID, DWORD, DWORD, DWORD_PTR))
        GetProcAddress(pk_winhttp.module, "WinHttpSendRequest");
    pk_winhttp.receive = (BOOL (WINAPI *)(HINTERNET, LPVOID))GetProcAddress(pk_winhttp.module, "WinHttpReceiveResponse");
    pk_winhttp.query = (BOOL (WINAPI *)(HINTERNET, DWORD, LPCWSTR, LPVOID, LPDWORD, LPDWORD))
        GetProcAddress(pk_winhttp.module, "WinHttpQueryHeaders");
    pk_winhttp.read = (BOOL (WINAPI *)(HINTERNET, LPVOID, DWORD, LPDWORD))
        GetProcAddress(pk_winhttp.module, "WinHttpReadData");
    if (!pk_winhttp.open || !pk_winhttp.close || !pk_winhttp.connect || !pk_winhttp.open_request ||
        !pk_winhttp.add_headers || !pk_winhttp.set_timeouts || !pk_winhttp.send ||
        !pk_winhttp.receive || !pk_winhttp.query || !pk_winhttp.read) {
        FreeLibrary(pk_winhttp.module);
        memset(&pk_winhttp, 0, sizeof pk_winhttp);
        snprintf(err, cap, "winhttp: missing entry points");
        return 0;
    }
    return 1;
}

static wchar_t *pk_wide_from_utf8(const char *text) {
    wchar_t *wide;
    int need;
    if (!text) return NULL;
    need = MultiByteToWideChar(CP_UTF8, 0, text, -1, NULL, 0);
    if (need <= 0) return NULL;
    wide = (wchar_t *)malloc(sizeof(wchar_t) * (size_t)need);
    if (!wide) return NULL;
    if (!MultiByteToWideChar(CP_UTF8, 0, text, -1, wide, need)) {
        free(wide);
        return NULL;
    }
    return wide;
}

static int pk_https_winhttp(const PkgUrl *url, const char *token, PkgBuf *body,
                            int *status, char *err, size_t cap) {
    wchar_t *host = NULL;
    wchar_t *path = NULL;
    wchar_t *headers = NULL;
    HINTERNET session = NULL;
    HINTERNET connection = NULL;
    HINTERNET request = NULL;
    DWORD code = 0;
    DWORD code_len = (DWORD)sizeof code;
    int seconds = pk_net_timeout_s();
    int ok = 0;
    if (!pk_winhttp_load(err, cap)) return 0;
    host = pk_wide_from_utf8(url->host);
    path = pk_wide_from_utf8(url->path);
    if (!host || !path) {
        snprintf(err, cap, "out of memory while preparing https request");
        goto done;
    }
    {
        PkgBuf value = {0};
        pk_buf_puts(&value, "Accept: application/json\r\n");
        if (token && *token) {
            pk_buf_puts(&value, "Authorization: Bearer ");
            pk_buf_puts(&value, token);
            pk_buf_puts(&value, "\r\n");
        }
        headers = pk_wide_from_utf8(value.ptr);
        pk_buf_free(&value);
        if (!headers) {
            snprintf(err, cap, "out of memory while preparing https headers");
            goto done;
        }
    }
    session = pk_winhttp.open(L"MellowCLI", WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
                              WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
    if (!session) {
        snprintf(err, cap, "winhttp: session open failed");
        goto done;
    }
    pk_winhttp.set_timeouts(session, seconds * 1000, seconds * 1000, seconds * 1000, seconds * 1000);
    connection = pk_winhttp.connect(session, host, (INTERNET_PORT)atoi(url->port), 0);
    if (!connection) {
        snprintf(err, cap, "winhttp: connect failed");
        goto done;
    }
    request = pk_winhttp.open_request(connection, L"GET", path, NULL, WINHTTP_NO_REFERER,
                                      WINHTTP_DEFAULT_ACCEPT_TYPES, WINHTTP_FLAG_SECURE);
    if (!request) {
        snprintf(err, cap, "winhttp: request open failed");
        goto done;
    }
    pk_winhttp.add_headers(request, headers, (DWORD)-1, WINHTTP_ADDREQ_FLAG_ADD | WINHTTP_ADDREQ_FLAG_REPLACE);
    if (!pk_winhttp.send(request, WINHTTP_NO_ADDITIONAL_HEADERS, 0, NULL, 0, 0, 0)) {
        snprintf(err, cap, "winhttp: request send failed");
        goto done;
    }
    if (!pk_winhttp.receive(request, NULL)) {
        snprintf(err, cap, "winhttp: no response");
        goto done;
    }
    if (!pk_winhttp.query(request, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
                          NULL, &code, &code_len, NULL)) {
        snprintf(err, cap, "winhttp: status query failed");
        goto done;
    }
    *status = (int)code;
    for (;;) {
        char chunk[8192];
        DWORD got = 0;
        if (!pk_winhttp.read(request, chunk, (DWORD)sizeof chunk, &got)) {
            snprintf(err, cap, "winhttp: response read failed");
            goto done;
        }
        if (!got) break;
        if (!pk_buf_put(body, chunk, (size_t)got)) {
            snprintf(err, cap, "out of memory while reading response");
            goto done;
        }
    }
    ok = 1;
done:
    if (request) pk_winhttp.close(request);
    if (connection) pk_winhttp.close(connection);
    if (session) pk_winhttp.close(session);
    free(headers);
    free(path);
    free(host);
    return ok;
}

#endif /* _WIN32 */
