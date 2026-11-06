#include "sm_native.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define SM3_MAGIC "SM3\0"
#define SM3_CODEC "sm3-token-native-crc32"
#define SM_MAX_DICT 240
#define SM_MAX_TOKEN 255

typedef struct {
    const unsigned char *ptr;
    uint16_t len;
    uint32_t count;
    uint32_t saving;
} Token;

#include "sm_native_part1.inc"
#include "sm_native_part2.inc"
