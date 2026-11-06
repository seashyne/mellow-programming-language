#ifndef MELLOWRT_MONEY_H
#define MELLOWRT_MONEY_H

#include "mellowrt.h"

int mellowrt_money_syscall(int32_t id, const MValue *args, size_t argc, MValue *out_result);
int mellowrt_money_cents(const MValue *value, int64_t *out);
void mellowrt_money_format_cents(int64_t cents, char out[64]);
MValue mellowrt_money_make(int64_t cents, const char *currency);

#endif
