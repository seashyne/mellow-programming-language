#ifndef SM_NATIVE_H
#define SM_NATIVE_H

#include <stddef.h>
#include <stdint.h>

typedef struct {
    int ok;
    char error[256];
    char codec[64];
    int version;
    int dictionary_entries;
    uint32_t original_size;
    uint32_t token_stream_size;
    uint32_t payload_size;
    uint32_t compressed_size;
    int checksum_ok;
} SmInfo;

int sm_native_pack_text(const unsigned char *input, size_t input_size, unsigned char **out, size_t *out_size, SmInfo *info);
int sm_native_unpack_bytes(const unsigned char *input, size_t input_size, unsigned char **out, size_t *out_size, SmInfo *info);
int sm_native_inspect_bytes(const unsigned char *input, size_t input_size, SmInfo *info);

#endif
