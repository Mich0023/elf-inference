/* Utilidades de cadenas: proyecto de ejemplo para validar el pipeline. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>

size_t string_length(const char *s) {
    size_t n = 0;
    while (s[n] != '\0') n++;
    return n;
}

void reverse_string(char *s) {
    size_t i = 0, j = string_length(s);
    if (j == 0) return;
    j--;
    while (i < j) {
        char t = s[i]; s[i] = s[j]; s[j] = t;
        i++; j--;
    }
}

int count_vowels(const char *s) {
    int c = 0;
    for (; *s; s++) {
        char ch = (char)tolower((unsigned char)*s);
        if (ch == 'a' || ch == 'e' || ch == 'i' || ch == 'o' || ch == 'u') c++;
    }
    return c;
}

void to_uppercase(char *s) {
    for (; *s; s++) *s = (char)toupper((unsigned char)*s);
}

int is_palindrome(const char *s) {
    size_t i = 0, j = strlen(s);
    if (j == 0) return 1;
    j--;
    while (i < j) {
        if (s[i] != s[j]) return 0;
        i++; j--;
    }
    return 1;
}

char *duplicate_string(const char *s) {
    size_t n = strlen(s) + 1;
    char *d = malloc(n);
    if (d) memcpy(d, s, n);
    return d;
}

int count_words(const char *s) {
    int words = 0, in_word = 0;
    for (; *s; s++) {
        if (isspace((unsigned char)*s)) in_word = 0;
        else if (!in_word) { in_word = 1; words++; }
    }
    return words;
}

int main(int argc, char **argv) {
    const char *in = argc > 1 ? argv[1] : "Anita lava la tina";
    char *copy = duplicate_string(in);
    printf("len=%zu vocales=%d palabras=%d pal=%d\n",
           string_length(copy), count_vowels(copy), count_words(copy), is_palindrome(copy));
    reverse_string(copy);
    to_uppercase(copy);
    puts(copy);
    free(copy);
    return 0;
}
