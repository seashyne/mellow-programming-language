/* std.data: streaming JSONL/CSV readers, the row transforms, and SQLite.
 *
 * Included by mellowrt_std.inc after the JSON encoder and decoder fragments so
 * the stream reader can reuse them. SQLite is the vendored amalgamation under
 * vendor/sqlite, so the data syscalls need no host. */

#ifndef MELLOWRT_DATA_INC
#define MELLOWRT_DATA_INC

#include <stdarg.h>

#include <sqlite3.h>

#include "mellowrt_data_part1.inc"
#include "mellowrt_data_part2.inc"
#include "mellowrt_data_part3.inc"
#include "mellowrt_data_part4.inc"
#include "mellowrt_data_part5.inc"
#include "mellowrt_data_part6.inc"

#endif /* MELLOWRT_DATA_INC */
