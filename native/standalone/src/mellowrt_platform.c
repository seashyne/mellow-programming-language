#include "mellowrt.h"

#include <stdint.h>

static const char *runtime_architecture(void) {
#if defined(__aarch64__) || defined(_M_ARM64)
    return "arm64";
#elif defined(__arm__) || defined(_M_ARM)
    return "arm32";
#elif defined(__x86_64__) || defined(_M_X64) || defined(_M_AMD64)
    return "x86_64";
#elif defined(__i386__) || defined(_M_IX86)
    return "x86";
#else
    return "unknown";
#endif
}

static int runtime_is_little_endian(void) {
    const uint16_t marker = 1;
    return *((const uint8_t *)&marker) == 1;
}

MRuntimePlatform mellow_runtime_platform(void) {
    MRuntimePlatform platform;
    platform.architecture = runtime_architecture();
    platform.backend = "generic-c";
    platform.pointer_bits = (uint32_t)(sizeof(void *) * 8u);
    platform.little_endian = runtime_is_little_endian();
#if defined(__aarch64__) || defined(_M_ARM64) || defined(__ARM_NEON) || defined(__ARM_NEON__)
    platform.arm_neon_available = 1;
#else
    platform.arm_neon_available = 0;
#endif
    /* Set this only after architecture-specific kernels are wired into the VM. */
    platform.optimized_kernels = 0;
    return platform;
}
