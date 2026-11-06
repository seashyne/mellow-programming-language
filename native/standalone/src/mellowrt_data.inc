/* std.data: streaming JSONL/CSV readers and the row transforms.
 *
 * Included by mellowrt_std.inc after the JSON encoder and decoder fragments so
 * the stream reader can reuse them. SQLite stays Python-only. */

#ifndef MELLOWRT_DATA_INC
#define MELLOWRT_DATA_INC

#include <stdarg.h>

#include "mellowrt_data_part1.inc"
#include "mellowrt_data_part2.inc"
#include "mellowrt_data_part3.inc"
#include "mellowrt_data_part4.inc"

#endif /* MELLOWRT_DATA_INC */
