/*
 * image_scan_helper - small wrapper around libwx_key.dylib.
 *
 * Usage: image_scan_helper <pid> <ciphertext_hex>
 */
#include <dlfcn.h>
#include <libgen.h>
#include <mach-o/dyld.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef const char *(*ScanMemoryForImageKeyFn)(int pid, const char *ciphertext);
typedef void (*FreeStringFn)(const char *str);

int main(int argc, char *argv[]) {
    if (argc != 3) {
        fprintf(stderr, "Usage: %s <pid> <ciphertext_hex>\n", argv[0]);
        printf("{\"success\":false,\"error\":\"invalid arguments\"}\n");
        return 1;
    }

    int pid = atoi(argv[1]);
    const char *ciphertext_hex = argv[2];
    if (pid <= 0) {
        printf("{\"success\":false,\"error\":\"invalid pid\"}\n");
        return 1;
    }

    char executable_path[4096];
    uint32_t executable_path_size = sizeof(executable_path);
    if (_NSGetExecutablePath(executable_path, &executable_path_size) != 0) {
        printf("{\"success\":false,\"error\":\"cannot get executable path\"}\n");
        return 1;
    }

    char *executable_dir = dirname(executable_path);
    char library_path[4096];
    snprintf(library_path, sizeof(library_path), "%s/libwx_key.dylib", executable_dir);

    void *handle = dlopen(library_path, RTLD_LAZY);
    if (!handle) {
        printf("{\"success\":false,\"error\":\"dlopen failed: %s\"}\n", dlerror());
        return 1;
    }

    ScanMemoryForImageKeyFn scan_memory =
        (ScanMemoryForImageKeyFn)dlsym(handle, "ScanMemoryForImageKey");
    if (!scan_memory) {
        printf("{\"success\":false,\"error\":\"symbol not found: ScanMemoryForImageKey\"}\n");
        dlclose(handle);
        return 1;
    }

    FreeStringFn free_string = (FreeStringFn)dlsym(handle, "FreeString");
    fprintf(stderr, "[image_scan_helper] calling ScanMemoryForImageKey(pid=%d)\n", pid);

    const char *result = scan_memory(pid, ciphertext_hex);
    if (result && strlen(result) > 0) {
        if (strncmp(result, "ERROR", 5) == 0) {
            printf("{\"success\":false,\"error\":\"%s\"}\n", result);
        } else {
            printf("{\"success\":true,\"aesKey\":\"%s\"}\n", result);
        }
        if (free_string) free_string(result);
    } else {
        printf("{\"success\":false,\"error\":\"no key found\"}\n");
    }

    dlclose(handle);
    return 0;
}
