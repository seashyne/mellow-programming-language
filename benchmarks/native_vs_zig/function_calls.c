#include <stdint.h>
#include <stdio.h>

static int64_t add_i64(int64_t a, int64_t b) {
    return a + b;
}

int main(void) {
    int64_t i = 0;
    int64_t total = 0;
    const int64_t n = 200000;

    while (i < n) {
        total = add_i64(total, i);
        i += 1;
    }

    printf("%lld\n", (long long)total);
    return 0;
}
