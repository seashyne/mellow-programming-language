#include <stdint.h>
#include <stdio.h>

int main(void) {
    const int64_t values[5] = {1, 2, 3, 4, 5};
    int64_t i = 0;
    int64_t total = 0;
    const int64_t n = 500000;

    while (i < n) {
        total += values[i % 5];
        i += 1;
    }

    printf("%lld\n", (long long)total);
    return 0;
}
