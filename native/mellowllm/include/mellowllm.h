#ifndef MELLOWLLM_H
#define MELLOWLLM_H

#include <stddef.h>

void mellowllm_matmul(const double *a, const double *b, double *out, size_t m, size_t n, size_t k);
void mellowllm_softmax(const double *values, double *out, size_t len);
void mellowllm_gelu(const double *values, double *out, size_t len);
void mellowllm_layer_norm(const double *values, const double *gamma, const double *beta, double *out, size_t len, double eps);

#endif
