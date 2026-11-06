/* ── HTTP(S) transport ───────────────────────────────────────────────────── */
/* `http://` uses a raw-socket HTTP/1.1 client so package operations work
   without linking a TLS stack. `https://` prefers the platform stack:
   WinHTTP on Windows and libcurl on POSIX when CMake found it. */

typedef struct {
    int https;
    char host[256];
    char port[8];
    char path[PKG_PATH_MAX];
} PkgUrl;

#define PKG_NET_DEFAULT_TIMEOUT 30
#define PKG_NET_MAX_REDIRECTS 3

#ifdef _WIN32
typedef SOCKET PkgSocket;
#define PKG_INVALID_SOCKET INVALID_SOCKET
#define pk_socket_close closesocket
#else
typedef int PkgSocket;
#define PKG_INVALID_SOCKET (-1)
#define pk_socket_close close
#endif

#include "mellowrt_pkg_net_part1.inc"
#include "mellowrt_pkg_net_part2.inc"
#include "mellowrt_pkg_net_part3.inc"
#include "mellowrt_pkg_net_part4.inc"
