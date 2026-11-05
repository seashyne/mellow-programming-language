/* MT19937 random source for the standalone runtime.
 *
 * The seeding and draw rules follow CPython's random.Random so a program that
 * passes --seed N sees the same numbers it would on the Python engine. Nothing
 * here calls into Python; it is a straight C port of the reference algorithm. */

#ifndef MELLOWRT_RANDOM_INC
#define MELLOWRT_RANDOM_INC

#include <math.h>
#include <stdint.h>
#include <string.h>
#include <time.h>

#define MRNG_N 624u
#define MRNG_M 397u

static void mrng_init_genrand(MRngState *r, uint32_t seed) {
    uint32_t i;
    r->state[0] = seed;
    for (i = 1; i < MRNG_N; ++i)
        r->state[i] = 1812433253u * (r->state[i - 1] ^ (r->state[i - 1] >> 30)) + i;
    r->index = (int)MRNG_N;
    r->gauss_valid = 0;
    r->gauss_next = 0.0;
}

static void mrng_init_by_array(MRngState *r, const uint32_t *key, size_t key_length) {
    uint32_t i = 1, j = 0;
    size_t k;
    mrng_init_genrand(r, 19650218u);
    k = (MRNG_N > key_length ? MRNG_N : key_length);
    for (; k; --k) {
        r->state[i] = (r->state[i] ^ ((r->state[i - 1] ^ (r->state[i - 1] >> 30)) * 1664525u))
                      + key[j] + j;
        ++i; ++j;
        if (i >= MRNG_N) { r->state[0] = r->state[MRNG_N - 1]; i = 1; }
        if (j >= key_length) j = 0;
    }
    for (k = MRNG_N - 1; k; --k) {
        r->state[i] = (r->state[i] ^ ((r->state[i - 1] ^ (r->state[i - 1] >> 30)) * 1566083941u)) - i;
        ++i;
        if (i >= MRNG_N) { r->state[0] = r->state[MRNG_N - 1]; i = 1; }
    }
    r->state[0] = 0x80000000u;
    r->index = (int)MRNG_N;
}

static void mrng_seed_int(MRngState *r, int64_t seed) {
    uint32_t key[2];
    size_t len = 1;
    uint64_t mag = seed < 0 ? (uint64_t)(-(seed + 1)) + 1u : (uint64_t)seed;
    key[0] = (uint32_t)(mag & 0xffffffffu);
    if ((mag >> 32) != 0) { key[1] = (uint32_t)(mag >> 32); len = 2; }
    mrng_init_by_array(r, key, len);
}

static void mrng_seed_entropy(MRngState *r, const void *salt) {
    uint64_t mix = (uint64_t)time(NULL);
    mix ^= (uint64_t)clock() << 17;
    mix ^= (uint64_t)(uintptr_t)salt;
    mrng_init_by_array(r, (const uint32_t[]){ (uint32_t)mix, (uint32_t)(mix >> 32) }, 2);
}

static uint32_t mrng_u32(MRngState *r) {
    static const uint32_t mag01[2] = { 0u, 0x9908b0dfu };
    uint32_t y;
    int kk;
    if (r->index >= (int)MRNG_N) {
        for (kk = 0; kk < (int)(MRNG_N - MRNG_M); ++kk) {
            y = (r->state[kk] & 0x80000000u) | (r->state[kk + 1] & 0x7fffffffu);
            r->state[kk] = r->state[kk + MRNG_M] ^ (y >> 1) ^ mag01[y & 1u];
        }
        for (; kk < (int)MRNG_N - 1; ++kk) {
            y = (r->state[kk] & 0x80000000u) | (r->state[kk + 1] & 0x7fffffffu);
            r->state[kk] = r->state[kk + (int)MRNG_M - (int)MRNG_N] ^ (y >> 1) ^ mag01[y & 1u];
        }
        y = (r->state[MRNG_N - 1] & 0x80000000u) | (r->state[0] & 0x7fffffffu);
        r->state[MRNG_N - 1] = r->state[MRNG_M - 1] ^ (y >> 1) ^ mag01[y & 1u];
        r->index = 0;
    }
    y = r->state[r->index++];
    y ^= (y >> 11);
    y ^= (y << 7) & 0x9d2c5680u;
    y ^= (y << 15) & 0xefc60000u;
    y ^= (y >> 18);
    return y;
}

static double mrng_random(MRngState *r) {
    uint32_t a = mrng_u32(r) >> 5;
    uint32_t b = mrng_u32(r) >> 6;
    return (a * 67108864.0 + b) * (1.0 / 9007199254740992.0);
}

static uint64_t mrng_getrandbits(MRngState *r, int k) {
    uint64_t result = 0;
    int remaining = k;
    int i, words;
    if (k <= 0) return 0;
    if (k <= 32) return (uint64_t)(mrng_u32(r) >> (32 - k));
    words = (k - 1) / 32 + 1;
    for (i = 0; i < words; ++i) {
        uint32_t w = mrng_u32(r);
        if (remaining < 32) w >>= (32 - remaining);
        result |= (uint64_t)w << (32 * i);
        remaining -= 32;
    }
    return result;
}

static uint64_t mrng_randbelow(MRngState *r, uint64_t n) {
    uint64_t value = n, draw;
    int k = 0;
    if (n == 0) return 0;
    while (value) { ++k; value >>= 1; }
    do { draw = mrng_getrandbits(r, k); } while (draw >= n);
    return draw;
}

static int64_t mrng_randint(MRngState *r, int64_t lo, int64_t hi) {
    uint64_t width;
    if (hi < lo) { int64_t tmp = lo; lo = hi; hi = tmp; }
    width = (uint64_t)hi - (uint64_t)lo + 1u;
    if (width == 0) return (int64_t)mrng_getrandbits(r, 64);
    return lo + (int64_t)mrng_randbelow(r, width);
}

static double mrng_gauss(MRngState *r, double mu, double sigma) {
    double z;
    if (r->gauss_valid) {
        z = r->gauss_next;
        r->gauss_valid = 0;
    } else {
        double x2pi = mrng_random(r) * 6.283185307179586;
        double g2rad = sqrt(-2.0 * log(1.0 - mrng_random(r)));
        z = cos(x2pi) * g2rad;
        r->gauss_next = sin(x2pi) * g2rad;
        r->gauss_valid = 1;
    }
    return mu + z * sigma;
}

static void mrng_ensure(MellowRuntimeContext *ctx) {
    if (!ctx || ctx->rng_ready) return;
    if (ctx->rng_seed_set) mrng_seed_int(&ctx->rng, ctx->rng_seed);
    else mrng_seed_entropy(&ctx->rng, ctx);
    ctx->rng_ready = 1;
}

#endif /* MELLOWRT_RANDOM_INC */
