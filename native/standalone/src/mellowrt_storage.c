#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#endif

#include "mellowrt_storage.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>

#ifdef _WIN32
#include <direct.h>
#define STOR_MAKE_DIR(path) _mkdir(path)
#define STOR_GET_CWD(buf, cap) _getcwd((buf), (int)(cap))
#else
#include <unistd.h>
#define STOR_MAKE_DIR(path) mkdir((path), 0777)
#define STOR_GET_CWD(buf, cap) getcwd((buf), (cap))
#endif

#define STOR_PATH_MAX 512
#define STOR_DEFAULT_BASE "mellow_saves"
#define STOR_MAX_DEPTH 24

#define ERR_STORAGE_TRAVERSAL "SANDBOX: invalid storage path (path traversal blocked)"
#define ERR_FILE_TRAVERSAL "SANDBOX: invalid file path (path traversal blocked)"
#define ERR_FS_TRAVERSAL "SANDBOX: fs: \"..\" traversal is blocked"
#define ERR_FS_ABSOLUTE "SANDBOX: fs: absolute paths are disabled by default"
#define ERR_DIR_ABSOLUTE "SANDBOX: storage_dir: absolute paths are disabled by default"
#define ERR_DIR_TRAVERSAL "SANDBOX: storage_dir: \"..\" traversal is blocked"
#define ERR_NOT_JSON "RUNTIME: value is not storable as JSON"
#define ERR_WRITE "RUNTIME: could not write the file"
#define ERR_READ "RUNTIME: could not read the file"
#define ERR_CORRUPT "RUNTIME: invalid JSON in save document"

#include "mellowrt_storage_part1.inc"
#include "mellowrt_storage_part2.inc"
#include "mellowrt_storage_part3.inc"
#include "mellowrt_storage_part4.inc"
