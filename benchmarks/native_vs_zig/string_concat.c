#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(void) {
    int i = 0;
    const int n = 2000;
    char *text = (char *)calloc((size_t)n + 1, 1);
    if (!text) return 1;

    while (i < n) {
        text[i] = 'a';
        i += 1;
    }

    printf("%d\n", (int)strlen(text));
    free(text);
    return 0;
}
