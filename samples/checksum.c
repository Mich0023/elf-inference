/* Checksums y hashes simples. */
#include <stdio.h>
#include <stdint.h>
#include <string.h>

uint32_t crc32_compute(const uint8_t *data, size_t len) {
    uint32_t crc = 0xFFFFFFFFu;
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (int k = 0; k < 8; k++)
            crc = (crc >> 1) ^ (0xEDB88320u & (uint32_t)-(int32_t)(crc & 1));
    }
    return ~crc;
}

uint32_t adler32_checksum(const uint8_t *data, size_t len) {
    uint32_t a = 1, b = 0;
    for (size_t i = 0; i < len; i++) {
        a = (a + data[i]) % 65521;
        b = (b + a) % 65521;
    }
    return (b << 16) | a;
}

uint32_t fnv1a_hash(const char *s) {
    uint32_t h = 2166136261u;
    for (; *s; s++) { h ^= (uint8_t)*s; h *= 16777619u; }
    return h;
}

uint8_t xor_checksum(const uint8_t *data, size_t len) {
    uint8_t x = 0;
    for (size_t i = 0; i < len; i++) x ^= data[i];
    return x;
}

uint16_t fletcher16(const uint8_t *data, size_t len) {
    uint16_t s1 = 0, s2 = 0;
    for (size_t i = 0; i < len; i++) {
        s1 = (uint16_t)((s1 + data[i]) % 255);
        s2 = (uint16_t)((s2 + s1) % 255);
    }
    return (uint16_t)((s2 << 8) | s1);
}

int main(int argc, char **argv) {
    const char *msg = argc > 1 ? argv[1] : "hola mundo";
    size_t n = strlen(msg);
    const uint8_t *p = (const uint8_t *)msg;
    printf("crc32=%08x adler=%08x fnv=%08x xor=%02x fl16=%04x\n",
           crc32_compute(p, n), adler32_checksum(p, n), fnv1a_hash(msg),
           xor_checksum(p, n), fletcher16(p, n));
    return 0;
}
