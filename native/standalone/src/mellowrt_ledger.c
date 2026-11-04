#include "mellowrt_ledger.h"
#include "mellowrt_money.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define LEDGER_GENESIS "0000000000000000000000000000000000000000000000000000000000000000"
#define LEDGER_HASH_HEX_LEN 64
#define LEDGER_MAX_DEPTH 24
#define LEDGER_MAX_MAP_KEYS 64

#include "mellowrt_ledger_part1.inc"
#include "mellowrt_ledger_part2.inc"
#include "mellowrt_ledger_part3.inc"
#include "mellowrt_ledger_part4.inc"
