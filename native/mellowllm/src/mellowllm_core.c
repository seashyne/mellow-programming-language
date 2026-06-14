#include "mellowllm.h"

#include <math.h>

void mellowllm_matmul(const double *a, const double *b, double *out, size_t m, size_t n, size_t k) {
    for (size_t row = 0; row < m; row++) {
        for (size_t col = 0; col < n; col++) {
            double total = 0.0;
            for (size_t idx = 0; idx < k; idx++) {
                total += a[row * k + idx] * b[idx * n + col];
            }
            out[row * n + col] = total;
        }
    }
}

void mellowllm_softmax(const double *values, double *out, size_t len) {
    if (len == 0) {
        return;
    }
    double peak = values[0];
    for (size_t i = 1; i < len; i++) {
        if (values[i] > peak) {
            peak = values[i];
        }
    }
    double total = 0.0;
    for (size_t i = 0; i < len; i++) {
        out[i] = exp(values[i] - peak);
        total += out[i];
    }
    if (total == 0.0) {
        total = 1.0;
    }
    for (size_t i = 0; i < len; i++) {
        out[i] /= total;
    }
}

void mellowllm_gelu(const double *values, double *out, size_t len) {
    const double scale = sqrt(2.0 / 3.14159265358979323846);
    for (size_t i = 0; i < len; i++) {
        double x = values[i];
        out[i] = 0.5 * x * (1.0 + tanh(scale * (x + 0.044715 * x * x * x)));
    }
}

void mellowllm_layer_norm(const double *values, const double *gamma, const double *beta, double *out, size_t len, double eps) {
    if (len == 0) {
        return;
    }
    double mean = 0.0;
    for (size_t i = 0; i < len; i++) {
        mean += values[i];
    }
    mean /= (double)len;

    double var = 0.0;
    for (size_t i = 0; i < len; i++) {
        double delta = values[i] - mean;
        var += delta * delta;
    }
    var /= (double)len;

    double inv = 1.0 / sqrt(var + eps);
    for (size_t i = 0; i < len; i++) {
        out[i] = ((values[i] - mean) * inv) * gamma[i] + beta[i];
    }
}
