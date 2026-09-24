#include <stdio.h>
static int foo(int a, int b) { return a + b; }
int main(void) {
    printf("%d\n", foo(1, 2, 3));
    return 0
}
