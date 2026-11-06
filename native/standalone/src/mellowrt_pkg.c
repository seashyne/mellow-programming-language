/* mellowrt_pkg.c — native package manager (local registry, no Python).
   Mirrors the Python package layer's on-disk layout:
     mellow_packages/registry/<name>/<version>/      published sources
     mellow_packages/installed/<name>/current/       installed copy + manifest.json
     mellow.lock                                     resolved project packages
     .mellow_aliases.json                            import aliases
*/
#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#endif

#include "mellowrt_pkg.h"

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>

#ifdef _WIN32
#include <direct.h>
#include <windows.h>
#define PKG_MKDIR(path) _mkdir(path)
#define PKG_RMDIR(path) _rmdir(path)
#define PKG_GETCWD(buf, cap) (_getcwd((buf), (int)(cap)) != NULL)
#define PKG_SEP '\\'
#else
#include <dirent.h>
#include <unistd.h>
#define PKG_MKDIR(path) mkdir((path), 0777)
#define PKG_RMDIR(path) rmdir(path)
#define PKG_GETCWD(buf, cap) (getcwd((buf), (cap)) != NULL)
#define PKG_SEP '/'
#endif

#define PKG_PATH_MAX 1024
#define PKG_MAX_DEPTH 8
#define PKG_ERR_CAP 512

#include "mellowrt_pkg_util.inc"
#include "mellowrt_pkg_json.inc"
#include "mellowrt_pkg_manifest.inc"
#include "mellowrt_pkg_store.inc"
#include "mellowrt_pkg_cli.inc"
