#include <stdint.h>
#include <stdio.h>

int main(void) {
    int64_t i = 0;
    int64_t total = 0;
    const int64_t n = 2000000;

    while (i < n) {
        total += i;
        i += 1;
    }

    printf("%lld\n", (long long)total);
    return 0;
}
