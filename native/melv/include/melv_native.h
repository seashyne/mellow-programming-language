#ifndef MELV_NATIVE_H
#define MELV_NATIVE_H

#include <stddef.h>
#include <stdint.h>

typedef struct {
    int ok;
    int native_supported;
    char error[256];
    char warning[256];
    char codec[64];
    double fps;
    int width;
    int height;
    int frames;
    int expected_frames;
    long long bytes;
} MelvInfo;

int melv_native_inspect_file(const char *path, MelvInfo *out);
int melv_native_pack_ppm_sequence(const char **frames, size_t frame_count, const char *output_path, double fps, MelvInfo *out);
int melv_native_extract_ppm_frames(const char *input_path, const char *out_dir, MelvInfo *out);

#endif
