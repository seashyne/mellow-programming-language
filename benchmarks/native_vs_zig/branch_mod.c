#include <stdint.h>
#include <stdio.h>

int main(void) {
    int64_t i = 0;
    int64_t total = 0;
    const int64_t n = 500000;

    while (i < n) {
        if ((i % 2) == 0) {
            total += 3;
        } else {
            total += 1;
        }
        i += 1;
    }

    printf("%lld\n", (long long)total);
    return 0;
}
