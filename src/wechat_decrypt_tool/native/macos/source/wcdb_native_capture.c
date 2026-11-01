#include <CommonCrypto/CommonHMAC.h>
#include <CommonCrypto/CommonKeyDerivation.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <limits.h>
#include <mach/exc.h>
#include <mach/arm/thread_status.h>
#include <mach/mach.h>
#include <mach/mach_vm.h>
#include <mach-o/dyld_images.h>
#include <mach-o/loader.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <unistd.h>

#define PAGE_SIZE_BYTES 4096
#define SALT_SIZE 16
#define KEY_SIZE 32
#define IV_SIZE 16
#define HMAC_SIZE 64
#define RESERVE_SIZE (IV_SIZE + HMAC_SIZE)
#define BR_X16_INSN 0xD61F0200u
#define MAX_EXCEPTION_PORTS 16
#define MAX_HW_BREAKPOINTS 16
#define REMOTE_PATH_LIMIT 1024
#define HW_BREAKPOINT_CONTROL_EXEC_4BYTES (((uint64_t)0xFull << 5) | 0x7ull)

extern boolean_t exc_server(mach_msg_header_t *in, mach_msg_header_t *out);

typedef struct {
    char mode[16];
    pid_t pid;
    uint64_t stub_file_address;
    uint64_t breakpoint_address;
    char image_name[256];
    char database_path[PATH_MAX];
    char page1_path[PATH_MAX];
    char ready_file[PATH_MAX];
    char transaction_id[129];
    int timeout_seconds;
} options_t;

typedef struct {
    task_t task;
    pid_t target_pid;
    mach_port_t exception_port;
    exception_mask_t masks[MAX_EXCEPTION_PORTS];
    mach_msg_type_number_t old_count;
    mach_port_t old_ports[MAX_EXCEPTION_PORTS];
    exception_behavior_t old_behaviors[MAX_EXCEPTION_PORTS];
    thread_state_flavor_t old_flavors[MAX_EXCEPTION_PORTS];
    mach_vm_address_t breakpoint_address;
    uint32_t original_instruction;
    thread_act_array_t debug_threads;
    mach_msg_type_number_t debug_thread_count;
    arm_debug_state64_t *saved_debug_states;
    bool *saved_debug_valid;
    bool *debug_state_modified;
    bool hw_breakpoints_installed;
    bool cleanup_failed;
    uint8_t page1[PAGE_SIZE_BYTES];
    bool page1_loaded;
    bool captured;
    bool validated;
    char db_key_hex[65];
    uint64_t pbkdf_calls;
    uint64_t wcdb_profile_hits;
    uint64_t rounds2_hits;
    uint64_t rounds256000_hits;
    uint64_t salt_matches;
    uint64_t candidate_rejects;
    uint64_t salt_read_failures;
    uint64_t candidate_read_failures;
    const char *last_stage;
    volatile sig_atomic_t stop_requested;
} capture_context_t;

static capture_context_t g_ctx;

/* Only fixed stage labels and counters belong in diagnostics; never key bytes,
 * salts, addresses, page data, or arbitrary strings from the target process. */
static void json_diagnostics(void) {
    printf(
        "\"diagnostics\":{\"pbkdf_calls\":%" PRIu64 ",\"wcdb_profile_hits\":%" PRIu64
        ",\"rounds2_hits\":%" PRIu64 ",\"rounds256000_hits\":%" PRIu64
        ",\"salt_matches\":%" PRIu64 ",\"candidate_rejects\":%" PRIu64
        ",\"salt_read_failures\":%" PRIu64 ",\"candidate_read_failures\":%" PRIu64
        ",\"last_stage\":\"%s\"}",
        g_ctx.pbkdf_calls, g_ctx.wcdb_profile_hits, g_ctx.rounds2_hits, g_ctx.rounds256000_hits,
        g_ctx.salt_matches, g_ctx.candidate_rejects, g_ctx.salt_read_failures,
        g_ctx.candidate_read_failures, g_ctx.last_stage ? g_ctx.last_stage : "initializing"
    );
}

static void json_success_preflight(const options_t *options) {
    printf(
        "{\"status\":\"ok\",\"mode\":\"preflight\",\"method\":\"macos_native_mach\","
        "\"pid\":%d,\"stub_file_address\":%" PRIu64 "}\n",
        options->pid,
        options->stub_file_address
    );
}

static void json_success_capture(const options_t *options) {
    (void)options;
    printf(
        "{\"status\":\"ok\",\"mode\":\"capture\",\"method\":\"macos_native_mach\","
        "\"pid\":%d,\"stub_file_address\":%" PRIu64 ",\"validated\":%s,"
        "\"db_key\":\"%s\",\"pbkdf_calls\":%" PRIu64 ",",
        options->pid,
        options->stub_file_address,
        g_ctx.validated ? "true" : "false",
        g_ctx.db_key_hex,
        g_ctx.pbkdf_calls
    );
    json_diagnostics();
    printf("}\n");
}

static void json_error(const char *code, const char *message) {
    printf(
        "{\"status\":\"error\",\"code\":\"%s\",\"message\":\"%s\","
        "\"method\":\"macos_native_mach\",\"pid\":%d,",
        code ? code : "native_capture_failed",
        message ? message : "native capture failed",
        g_ctx.target_pid
    );
    json_diagnostics();
    printf("}\n");
}

static void on_signal(int signum) {
    (void)signum;
    g_ctx.stop_requested = 1;
}

static void install_signal_handlers(void) {
    struct sigaction action;
    memset(&action, 0, sizeof(action));
    action.sa_handler = on_signal;
    sigemptyset(&action.sa_mask);
    sigaction(SIGINT, &action, NULL);
    sigaction(SIGTERM, &action, NULL);
}

static bool write_ready_file(const char *path, pid_t pid, const char *transaction_id) {
    if (!path || !*path) {
        return true;
    }
    int flags = O_WRONLY | O_TRUNC;
#ifdef O_NOFOLLOW
    flags |= O_NOFOLLOW;
#endif
#ifdef O_CLOEXEC
    flags |= O_CLOEXEC;
#endif
    int descriptor = open(path, flags);
    if (descriptor < 0) {
        return false;
    }
    char payload[320];
    int length = snprintf(
        payload,
        sizeof(payload),
        "{\"status\":\"ready\",\"method\":\"macos_native_mach\",\"pid\":%d%s%s%s}\n",
        pid,
        transaction_id && *transaction_id ? ",\"transaction_id\":\"" : "",
        transaction_id && *transaction_id ? transaction_id : "",
        transaction_id && *transaction_id ? "\"" : ""
    );
    bool ok = length > 0 && (size_t)length < sizeof(payload)
        && write(descriptor, payload, (size_t)length) == length
        && fsync(descriptor) == 0;
    close(descriptor);
    return ok;
}

static bool streq(const char *a, const char *b) {
    return a && b && strcmp(a, b) == 0;
}

static bool parse_uint64(const char *value, uint64_t *out) {
    if (!value || !*value || !out) {
        return false;
    }
    errno = 0;
    char *end = NULL;
    unsigned long long parsed = strtoull(value, &end, 0);
    if (errno != 0 || !end || *end != '\0') {
        return false;
    }
    *out = (uint64_t)parsed;
    return true;
}

static bool parse_int(const char *value, int *out) {
    if (!value || !*value || !out) {
        return false;
    }
    errno = 0;
    char *end = NULL;
    long parsed = strtol(value, &end, 10);
    if (errno != 0 || !end || *end != '\0' || parsed <= 0 || parsed > INT32_MAX) {
        return false;
    }
    *out = (int)parsed;
    return true;
}

static bool valid_transaction_id(const char *value) {
    if (!value || !*value || strlen(value) > 128) {
        return false;
    }
    /* This opaque correlation token is deliberately restricted for JSON. */
    for (const char *cursor = value; *cursor; cursor++) {
        if (!((*cursor >= 'a' && *cursor <= 'z') || (*cursor >= 'A' && *cursor <= 'Z') ||
              (*cursor >= '0' && *cursor <= '9') || *cursor == '-' || *cursor == '_')) {
            return false;
        }
    }
    return true;
}

static bool parse_args(int argc, char **argv, options_t *options) {
    if (!options) {
        return false;
    }
    memset(options, 0, sizeof(*options));
    options->timeout_seconds = 240;
    strlcpy(options->image_name, "wechat.dylib", sizeof(options->image_name));
    for (int index = 1; index < argc; index++) {
        const char *arg = argv[index];
        if (streq(arg, "--mode") && index + 1 < argc) {
            strlcpy(options->mode, argv[++index], sizeof(options->mode));
        } else if (streq(arg, "--pid") && index + 1 < argc) {
            int pid_value = 0;
            if (!parse_int(argv[++index], &pid_value)) {
                return false;
            }
            options->pid = (pid_t)pid_value;
        } else if (streq(arg, "--stub-file-address") && index + 1 < argc) {
            if (!parse_uint64(argv[++index], &options->stub_file_address)) {
                return false;
            }
        } else if (streq(arg, "--breakpoint-address") && index + 1 < argc) {
            if (!parse_uint64(argv[++index], &options->breakpoint_address)) {
                return false;
            }
        } else if (streq(arg, "--database") && index + 1 < argc) {
            strlcpy(options->database_path, argv[++index], sizeof(options->database_path));
        } else if (streq(arg, "--page1-file") && index + 1 < argc) {
            strlcpy(options->page1_path, argv[++index], sizeof(options->page1_path));
        } else if (streq(arg, "--ready-file") && index + 1 < argc) {
            strlcpy(options->ready_file, argv[++index], sizeof(options->ready_file));
        } else if (streq(arg, "--transaction-id") && index + 1 < argc) {
            const char *value = argv[++index];
            if (!valid_transaction_id(value)) {
                return false;
            }
            strlcpy(options->transaction_id, value, sizeof(options->transaction_id));
        } else if (streq(arg, "--timeout") && index + 1 < argc) {
            if (!parse_int(argv[++index], &options->timeout_seconds)) {
                return false;
            }
        } else if (streq(arg, "--image") && index + 1 < argc) {
            strlcpy(options->image_name, argv[++index], sizeof(options->image_name));
        } else {
            return false;
        }
    }
    if (options->pid <= 0 || options->stub_file_address == 0 || options->mode[0] == '\0') {
        return false;
    }
    if (!streq(options->mode, "preflight") && !streq(options->mode, "capture")) {
        return false;
    }
    if (streq(options->mode, "capture") && options->database_path[0] == '\0' && options->page1_path[0] == '\0') {
        return false;
    }
    return options->breakpoint_address > 0;
}

static kern_return_t remote_read_exact(task_t task, mach_vm_address_t address, void *buffer, mach_vm_size_t size) {
    mach_vm_size_t read_size = 0;
    return mach_vm_read_overwrite(task, address, size, (mach_vm_address_t)buffer, &read_size) == KERN_SUCCESS &&
                   read_size == size
               ? KERN_SUCCESS
               : KERN_FAILURE;
}

static bool read_page1(const char *path, uint8_t *page1) {
    int descriptor = open(path, O_RDONLY);
    if (descriptor < 0) {
        return false;
    }
    ssize_t total = 0;
    while (total < PAGE_SIZE_BYTES) {
        ssize_t read_now = read(descriptor, page1 + total, PAGE_SIZE_BYTES - total);
        if (read_now <= 0) {
            close(descriptor);
            return false;
        }
        total += read_now;
    }
    close(descriptor);
    return true;
}

static void xor_mac_salt(const uint8_t *salt, uint8_t *mac_salt) {
    for (size_t index = 0; index < SALT_SIZE; index++) {
        mac_salt[index] = (uint8_t)(salt[index] ^ 0x3A);
    }
}

static bool derive_key(const uint8_t *password, size_t password_length, const uint8_t *salt, uint32_t rounds, uint8_t *out_key) {
    return CCKeyDerivationPBKDF(
               kCCPBKDF2,
               (const char *)password,
               password_length,
               salt,
               SALT_SIZE,
               kCCPRFHmacAlgSHA512,
               rounds,
               out_key,
               KEY_SIZE
           ) == 0;
}

static bool compute_page1_hmac(const uint8_t *mac_key, const uint8_t *page1, uint8_t *out_digest) {
    CCHmacContext context;
    CCHmacInit(&context, kCCHmacAlgSHA512, mac_key, KEY_SIZE);
    CCHmacUpdate(&context, page1 + SALT_SIZE, PAGE_SIZE_BYTES - RESERVE_SIZE);
    const uint32_t page_number = 1;
    CCHmacUpdate(&context, &page_number, sizeof(page_number));
    CCHmacFinal(&context, out_digest);
    return true;
}

static bool candidate_matches_page1(const uint8_t *candidate) {
    if (!g_ctx.page1_loaded) {
        return false;
    }
    const uint8_t *salt = g_ctx.page1;
    const uint8_t *stored_hmac = g_ctx.page1 + PAGE_SIZE_BYTES - HMAC_SIZE;
    uint8_t enc_key[KEY_SIZE];
    uint8_t mac_salt[SALT_SIZE];
    uint8_t mac_key[KEY_SIZE];
    uint8_t digest[HMAC_SIZE];

    /*
     * Only accept the account passphrase seen at the 256000-round PBKDF call.
     * The later 2-round call receives the already-derived per-database raw
     * encryption key.  Accepting that value validates one message database but
     * cannot open the session database, so it must never be returned as the
     * account passphrase.
     */
    if (!derive_key(candidate, KEY_SIZE, salt, 256000, enc_key)) {
        return false;
    }
    xor_mac_salt(salt, mac_salt);
    if (!derive_key(enc_key, KEY_SIZE, mac_salt, 2, mac_key)) {
        return false;
    }
    compute_page1_hmac(mac_key, g_ctx.page1, digest);
    return memcmp(digest, stored_hmac, HMAC_SIZE) == 0;
}

static void bytes_to_hex(const uint8_t *bytes, size_t length, char *out_hex) {
    static const char table[] = "0123456789abcdef";
    for (size_t index = 0; index < length; index++) {
        out_hex[index * 2] = table[(bytes[index] >> 4) & 0xF];
        out_hex[index * 2 + 1] = table[bytes[index] & 0xF];
    }
    out_hex[length * 2] = '\0';
}

static bool breakpoint_profile_matches(const arm_thread_state64_t *state) {
    uint64_t algorithm = state->__x[0];
    uint64_t password_len = state->__x[2];
    uint64_t salt_len = state->__x[4];
    uint64_t prf = state->__x[5];
    return algorithm == 2 && password_len == KEY_SIZE && salt_len == SALT_SIZE && prf == 5;
}

static bool breakpoint_operands_match(const arm_thread_state64_t *state) {
    return breakpoint_profile_matches(state) && state->__x[6] == 256000;
}

static bool salt_matches_expected(uint64_t rounds, const uint8_t *salt) {
    uint8_t mac_salt[SALT_SIZE];
    xor_mac_salt(g_ctx.page1, mac_salt);
    (void)mac_salt;
    return rounds == 256000 && memcmp(salt, g_ctx.page1, SALT_SIZE) == 0;
}

static kern_return_t attach_task(pid_t pid, task_t *task) {
    if (!task) {
        return KERN_INVALID_ARGUMENT;
    }
    return task_for_pid(mach_task_self(), pid, task);
}

static bool basename_matches(const char *path, const char *basename) {
    if (!path || !basename) {
        return false;
    }
    const char *tail = strrchr(path, '/');
    tail = tail ? tail + 1 : path;
    return strcmp(tail, basename) == 0;
}

static kern_return_t resolve_remote_image_header(task_t task, const char *image_name, mach_vm_address_t *load_address) {
    task_dyld_info_data_t dyld_info;
    mach_msg_type_number_t count = TASK_DYLD_INFO_COUNT;
    kern_return_t kr = task_info(task, TASK_DYLD_INFO, (task_info_t)&dyld_info, &count);
    if (kr != KERN_SUCCESS) {
        return kr;
    }

    struct dyld_all_image_infos infos;
    kr = remote_read_exact(task, dyld_info.all_image_info_addr, &infos, sizeof(infos));
    if (kr != KERN_SUCCESS) {
        return kr;
    }
    if (infos.infoArrayCount == 0 || infos.infoArray == 0) {
        return KERN_FAILURE;
    }

    size_t infos_size = sizeof(struct dyld_image_info) * infos.infoArrayCount;
    struct dyld_image_info *image_infos = calloc(infos.infoArrayCount, sizeof(struct dyld_image_info));
    if (!image_infos) {
        return KERN_RESOURCE_SHORTAGE;
    }
    kr = remote_read_exact(task, (mach_vm_address_t)infos.infoArray, image_infos, infos_size);
    if (kr != KERN_SUCCESS) {
        free(image_infos);
        return kr;
    }

    char path_buffer[REMOTE_PATH_LIMIT];
    for (uint32_t index = 0; index < infos.infoArrayCount; index++) {
        memset(path_buffer, 0, sizeof(path_buffer));
        if (image_infos[index].imageFilePath == NULL) {
            continue;
        }
        kr = remote_read_exact(task, (mach_vm_address_t)image_infos[index].imageFilePath, path_buffer, sizeof(path_buffer) - 1);
        if (kr != KERN_SUCCESS) {
            continue;
        }
        path_buffer[sizeof(path_buffer) - 1] = '\0';
        if (basename_matches(path_buffer, image_name)) {
            *load_address = (mach_vm_address_t)image_infos[index].imageLoadAddress;
            free(image_infos);
            return KERN_SUCCESS;
        }
    }
    free(image_infos);
    return KERN_FAILURE;
}

static kern_return_t compute_breakpoint_address(task_t task, const char *image_name, uint64_t file_stub_address, mach_vm_address_t *out_address) {
    mach_vm_address_t image_header = 0;
    kern_return_t kr = resolve_remote_image_header(task, image_name, &image_header);
    if (kr != KERN_SUCCESS) {
        return kr;
    }

    struct mach_header_64 header;
    kr = remote_read_exact(task, image_header, &header, sizeof(header));
    if (kr != KERN_SUCCESS) {
        return kr;
    }
    if (header.magic != MH_MAGIC_64) {
        return KERN_FAILURE;
    }

    size_t commands_size = header.sizeofcmds;
    uint8_t *commands = calloc(1, commands_size);
    if (!commands) {
        return KERN_RESOURCE_SHORTAGE;
    }
    kr = remote_read_exact(task, image_header + sizeof(header), commands, commands_size);
    if (kr != KERN_SUCCESS) {
        free(commands);
        return kr;
    }

    uint64_t text_vmaddr = 0;
    size_t offset = 0;
    for (uint32_t index = 0; index < header.ncmds && offset + sizeof(struct load_command) <= commands_size; index++) {
        struct load_command *load_command = (struct load_command *)(commands + offset);
        if (load_command->cmd == LC_SEGMENT_64 && offset + sizeof(struct segment_command_64) <= commands_size) {
            struct segment_command_64 *segment = (struct segment_command_64 *)(commands + offset);
            if (strncmp(segment->segname, "__TEXT", sizeof(segment->segname)) == 0) {
                text_vmaddr = segment->vmaddr;
                break;
            }
        }
        if (load_command->cmdsize == 0) {
            break;
        }
        offset += load_command->cmdsize;
    }
    free(commands);
    if (text_vmaddr == 0) {
        return KERN_FAILURE;
    }
    uint64_t slide = image_header - text_vmaddr;
    *out_address = (mach_vm_address_t)(slide + file_stub_address + 8);
    return KERN_SUCCESS;
}

static kern_return_t resolve_breakpoint_address(task_t task, const options_t *options, mach_vm_address_t *out_address) {
    if (options->breakpoint_address > 0) {
        *out_address = (mach_vm_address_t)options->breakpoint_address;
        return KERN_SUCCESS;
    }
    return compute_breakpoint_address(task, options->image_name, options->stub_file_address, out_address);
}

static kern_return_t read_instruction(task_t task, mach_vm_address_t address, uint32_t *instruction) {
    return remote_read_exact(task, address, instruction, sizeof(*instruction));
}

static void release_debug_threads(void) {
    if (g_ctx.debug_threads != NULL) {
        for (mach_msg_type_number_t index = 0; index < g_ctx.debug_thread_count; index++) {
            if (g_ctx.debug_threads[index] != MACH_PORT_NULL) {
                (void)mach_port_deallocate(mach_task_self(), g_ctx.debug_threads[index]);
            }
        }
        (void)mach_vm_deallocate(
            mach_task_self(),
            (mach_vm_address_t)g_ctx.debug_threads,
            (mach_vm_size_t)(sizeof(thread_t) * g_ctx.debug_thread_count)
        );
        g_ctx.debug_threads = NULL;
    }
    free(g_ctx.saved_debug_states);
    g_ctx.saved_debug_states = NULL;
    free(g_ctx.saved_debug_valid);
    g_ctx.saved_debug_valid = NULL;
    free(g_ctx.debug_state_modified);
    g_ctx.debug_state_modified = NULL;
    g_ctx.debug_thread_count = 0;
    g_ctx.hw_breakpoints_installed = false;
}

static kern_return_t restore_hardware_breakpoints(void) {
    if (g_ctx.debug_threads == NULL || g_ctx.saved_debug_states == NULL) {
        release_debug_threads();
        return KERN_SUCCESS;
    }
    kern_return_t first_error = KERN_SUCCESS;
    for (mach_msg_type_number_t index = 0; index < g_ctx.debug_thread_count; index++) {
        thread_t thread = g_ctx.debug_threads[index];
        if (thread == MACH_PORT_NULL || !g_ctx.saved_debug_valid[index] || !g_ctx.debug_state_modified[index]) {
            continue;
        }
        kern_return_t kr = thread_set_state(
            thread,
            ARM_DEBUG_STATE64,
            (thread_state_t)&g_ctx.saved_debug_states[index],
            ARM_DEBUG_STATE64_COUNT
        );
        if (
            kr != KERN_SUCCESS &&
            kr != KERN_TERMINATED &&
            kr != MACH_SEND_INVALID_DEST &&
            first_error == KERN_SUCCESS
        ) {
            first_error = kr;
        }
    }
    if (first_error != KERN_SUCCESS) {
        g_ctx.cleanup_failed = true;
    }
    release_debug_threads();
    return first_error;
}

static kern_return_t install_hardware_breakpoints(task_t task) {
    thread_act_array_t threads = NULL;
    mach_msg_type_number_t thread_count = 0;
    kern_return_t kr = task_threads(task, &threads, &thread_count);
    if (kr != KERN_SUCCESS) {
        return kr;
    }
    if (thread_count == 0) {
        if (threads != NULL) {
            (void)mach_vm_deallocate(mach_task_self(), (mach_vm_address_t)threads, 0);
        }
        return KERN_FAILURE;
    }

    arm_debug_state64_t *saved_states = calloc(thread_count, sizeof(*saved_states));
    bool *saved_valid = calloc(thread_count, sizeof(*saved_valid));
    bool *modified = calloc(thread_count, sizeof(*modified));
    if (!saved_states || !saved_valid || !modified) {
        free(saved_states);
        free(saved_valid);
        free(modified);
        for (mach_msg_type_number_t index = 0; index < thread_count; index++) {
            if (threads[index] != MACH_PORT_NULL) {
                (void)mach_port_deallocate(mach_task_self(), threads[index]);
            }
        }
        (void)mach_vm_deallocate(
            mach_task_self(),
            (mach_vm_address_t)threads,
            (mach_vm_size_t)(sizeof(thread_t) * thread_count)
        );
        return KERN_RESOURCE_SHORTAGE;
    }

    g_ctx.debug_threads = threads;
    g_ctx.debug_thread_count = thread_count;
    g_ctx.saved_debug_states = saved_states;
    g_ctx.saved_debug_valid = saved_valid;
    g_ctx.debug_state_modified = modified;

    const uint64_t control = HW_BREAKPOINT_CONTROL_EXEC_4BYTES;
    const uint64_t address = ((uint64_t)g_ctx.breakpoint_address) & ~0x3ull;

    for (mach_msg_type_number_t index = 0; index < thread_count; index++) {
        thread_t thread = threads[index];
        if (thread == MACH_PORT_NULL) {
            continue;
        }
        arm_debug_state64_t debug_state;
        memset(&debug_state, 0, sizeof(debug_state));
        mach_msg_type_number_t count = ARM_DEBUG_STATE64_COUNT;
        kr = thread_get_state(thread, ARM_DEBUG_STATE64, (thread_state_t)&debug_state, &count);
        if (kr == KERN_TERMINATED || kr == MACH_SEND_INVALID_DEST) {
            continue;
        }
        if (kr != KERN_SUCCESS) {
            (void)restore_hardware_breakpoints();
            return kr;
        }
        saved_states[index] = debug_state;
        saved_valid[index] = true;

        bool installed = false;
        for (size_t slot = 0; slot < MAX_HW_BREAKPOINTS; slot++) {
            if ((debug_state.__bcr[slot] & 0x1ull) != 0) {
                continue;
            }
            debug_state.__bvr[slot] = address;
            debug_state.__bcr[slot] = control;
            installed = true;
            break;
        }
        if (!installed) {
            (void)restore_hardware_breakpoints();
            return KERN_NO_SPACE;
        }
        kr = thread_set_state(thread, ARM_DEBUG_STATE64, (thread_state_t)&debug_state, ARM_DEBUG_STATE64_COUNT);
        if (kr == KERN_TERMINATED || kr == MACH_SEND_INVALID_DEST) {
            continue;
        }
        if (kr != KERN_SUCCESS) {
            (void)restore_hardware_breakpoints();
            return kr;
        }
        modified[index] = true;
    }

    g_ctx.hw_breakpoints_installed = true;
    return KERN_SUCCESS;
}

static bool thread_set_matches(thread_act_array_t threads, mach_msg_type_number_t count) {
    if (!threads || count != g_ctx.debug_thread_count || !g_ctx.debug_threads) {
        return false;
    }
    for (mach_msg_type_number_t index = 0; index < count; index++) {
        bool found = false;
        for (mach_msg_type_number_t existing = 0; existing < g_ctx.debug_thread_count; existing++) {
            if (threads[index] == g_ctx.debug_threads[existing]) {
                found = true;
                break;
            }
        }
        if (!found) {
            return false;
        }
    }
    return true;
}

static void deallocate_thread_list(thread_act_array_t threads, mach_msg_type_number_t count) {
    if (!threads) {
        return;
    }
    for (mach_msg_type_number_t index = 0; index < count; index++) {
        if (threads[index] != MACH_PORT_NULL) {
            (void)mach_port_deallocate(mach_task_self(), threads[index]);
        }
    }
    (void)mach_vm_deallocate(
        mach_task_self(),
        (mach_vm_address_t)threads,
        (mach_vm_size_t)(sizeof(thread_t) * count)
    );
}

/*
 * ARM hardware breakpoints are per-thread.  WeChat creates its WCDB/login
 * worker threads lazily, after the initial attach, so installing once at
 * startup misses the actual PBKDF call.  Refresh the breakpoint set when the
 * task's thread set changes; the short suspend window prevents a new thread
 * from running without the breakpoint.
 */
static kern_return_t refresh_hardware_breakpoints_if_needed(void) {
    thread_act_array_t threads = NULL;
    mach_msg_type_number_t count = 0;
    kern_return_t kr = task_threads(g_ctx.task, &threads, &count);
    if (kr != KERN_SUCCESS) {
        return kr;
    }
    bool changed = !thread_set_matches(threads, count);
    if (!changed) {
        deallocate_thread_list(threads, count);
        return KERN_SUCCESS;
    }
    deallocate_thread_list(threads, count);

    kr = task_suspend(g_ctx.task);
    if (kr != KERN_SUCCESS) {
        return kr;
    }
    kr = restore_hardware_breakpoints();
    if (kr == KERN_SUCCESS) {
        kr = install_hardware_breakpoints(g_ctx.task);
    }
    kern_return_t resume_kr = task_resume(g_ctx.task);
    if (resume_kr != KERN_SUCCESS) {
        g_ctx.cleanup_failed = true;
        return resume_kr;
    }
    return kr;
}

static kern_return_t install_exception_port(task_t task) {
    g_ctx.old_count = MAX_EXCEPTION_PORTS;
    kern_return_t kr = task_get_exception_ports(
        task,
        EXC_MASK_BREAKPOINT,
        g_ctx.masks,
        &g_ctx.old_count,
        g_ctx.old_ports,
        g_ctx.old_behaviors,
        g_ctx.old_flavors
    );
    if (kr != KERN_SUCCESS) {
        return kr;
    }
    kr = mach_port_allocate(mach_task_self(), MACH_PORT_RIGHT_RECEIVE, &g_ctx.exception_port);
    if (kr != KERN_SUCCESS) {
        return kr;
    }
    kr = mach_port_insert_right(mach_task_self(), g_ctx.exception_port, g_ctx.exception_port, MACH_MSG_TYPE_MAKE_SEND);
    if (kr != KERN_SUCCESS) {
        return kr;
    }
    /*
     * This helper is linked with the legacy exc_server MIG dispatcher and
     * implements catch_exception_raise(), whose exception codes are the
     * exception_data_t (32-bit) form.  MACH_EXCEPTION_CODES changes the wire
     * protocol to mach_exception_raise() with 64-bit codes; feeding that
     * message to exc_server leaves the breakpoint request unanswered and the
     * WeChat login thread suspended forever at "正在进入".  Keep both sides on
     * the EXCEPTION_DEFAULT/exc_server protocol.
     */
    return task_set_exception_ports(
        task,
        EXC_MASK_BREAKPOINT,
        g_ctx.exception_port,
        EXCEPTION_DEFAULT,
        THREAD_STATE_NONE
    );
}

static void restore_exception_ports(task_t task) {
    for (mach_msg_type_number_t index = 0; index < g_ctx.old_count; index++) {
        if (g_ctx.masks[index] == 0) {
            continue;
        }
        kern_return_t kr = task_set_exception_ports(task, g_ctx.masks[index], g_ctx.old_ports[index], g_ctx.old_behaviors[index], g_ctx.old_flavors[index]);
        if (kr != KERN_SUCCESS && kr != KERN_TERMINATED && kr != MACH_SEND_INVALID_DEST) {
            g_ctx.cleanup_failed = true;
        }
    }
    if (g_ctx.exception_port != MACH_PORT_NULL) {
        mach_port_mod_refs(mach_task_self(), g_ctx.exception_port, MACH_PORT_RIGHT_RECEIVE, -1);
        g_ctx.exception_port = MACH_PORT_NULL;
    }
}

static kern_return_t continue_thread_at_x16(thread_t thread) {
    arm_thread_state64_t state;
    mach_msg_type_number_t count = ARM_THREAD_STATE64_COUNT;
    kern_return_t kr = thread_get_state(thread, ARM_THREAD_STATE64, (thread_state_t)&state, &count);
    if (kr != KERN_SUCCESS) {
        return kr;
    }
    arm_thread_state64_ptrauth_strip(state);
    void (*next_pc)(void) = (void (*)(void))(uintptr_t)state.__x[16];
    arm_thread_state64_set_pc_fptr(state, next_pc);
    return thread_set_state(thread, ARM_THREAD_STATE64, (thread_state_t)&state, ARM_THREAD_STATE64_COUNT);
}

static kern_return_t handle_breakpoint(thread_t thread) {
    arm_thread_state64_t state;
    mach_msg_type_number_t count = ARM_THREAD_STATE64_COUNT;
    kern_return_t kr = thread_get_state(thread, ARM_THREAD_STATE64, (thread_state_t)&state, &count);
    if (kr != KERN_SUCCESS) {
        return kr;
    }
    arm_thread_state64_ptrauth_strip(state);
    uintptr_t pc = arm_thread_state64_get_pc(state);
    uintptr_t expected = (uintptr_t)g_ctx.breakpoint_address;
    if (pc != expected && pc != expected + 4) {
        return continue_thread_at_x16(thread);
    }

    g_ctx.pbkdf_calls += 1;
    g_ctx.last_stage = "pbkdf_seen";
    if (breakpoint_profile_matches(&state)) {
        g_ctx.wcdb_profile_hits += 1;
        g_ctx.last_stage = "profile_matched";
        if (state.__x[6] == 2) {
            /* Count this call without reading/accepting its per-database raw key. */
            g_ctx.rounds2_hits += 1;
            g_ctx.last_stage = "rounds2_seen";
        } else if (state.__x[6] == 256000) {
            g_ctx.rounds256000_hits += 1;
            g_ctx.last_stage = "rounds256000_seen";
        }
    }
    if (!breakpoint_operands_match(&state) || !g_ctx.page1_loaded) {
        return continue_thread_at_x16(thread);
    }

    uint8_t salt[SALT_SIZE];
    uint8_t candidate[KEY_SIZE];
    kr = remote_read_exact(g_ctx.task, (mach_vm_address_t)state.__x[3], salt, sizeof(salt));
    if (kr != KERN_SUCCESS) {
        g_ctx.salt_read_failures += 1;
        g_ctx.last_stage = "salt_read_failed";
        return continue_thread_at_x16(thread);
    }
    if (!salt_matches_expected(state.__x[6], salt)) {
        g_ctx.last_stage = "salt_mismatch";
        return continue_thread_at_x16(thread);
    }
    g_ctx.salt_matches += 1;
    g_ctx.last_stage = "salt_matched";
    kr = remote_read_exact(g_ctx.task, (mach_vm_address_t)state.__x[1], candidate, sizeof(candidate));
    if (kr != KERN_SUCCESS) {
        g_ctx.candidate_read_failures += 1;
        g_ctx.last_stage = "candidate_read_failed";
        return continue_thread_at_x16(thread);
    }
    if (candidate_matches_page1(candidate)) {
        bytes_to_hex(candidate, KEY_SIZE, g_ctx.db_key_hex);
        g_ctx.captured = true;
        g_ctx.validated = true;
        g_ctx.last_stage = "validated";
        g_ctx.stop_requested = 1;
        /*
         * The candidate has already passed the encrypted page-1 HMAC check.
         * This is a disposable, temporarily re-signed WeChat process which the
         * transactional wrapper must close before restoring the official app.
         * Do not resume the thread from this hardware-breakpoint exception:
         * macOS 27 can redeliver the pending SIGTRAP after the exception port
         * is removed, producing a crash report despite a successful capture.
         * Terminate the temporary process while it is still exception-stopped;
         * SIGKILL does not become an application crash and cannot leak the
         * breakpoint exception back into WeChat.
         */
        if (g_ctx.target_pid > 0) {
            (void)kill(g_ctx.target_pid, SIGKILL);
        }
        return KERN_SUCCESS;
    }
    g_ctx.candidate_rejects += 1;
    g_ctx.last_stage = "candidate_rejected";
    return continue_thread_at_x16(thread);
}

kern_return_t catch_exception_raise(
    mach_port_t exception_port,
    mach_port_t thread,
    mach_port_t task,
    exception_type_t exception,
    exception_data_t code,
    mach_msg_type_number_t code_count
) {
    (void)exception_port;
    (void)task;
    (void)code;
    (void)code_count;
    if (exception != EXC_BREAKPOINT) {
        return KERN_FAILURE;
    }
    return handle_breakpoint(thread);
}

kern_return_t catch_exception_raise_state(
    mach_port_t exception_port,
    exception_type_t exception,
    const exception_data_t code,
    mach_msg_type_number_t code_count,
    int *flavor,
    const thread_state_t old_state,
    mach_msg_type_number_t old_state_count,
    thread_state_t new_state,
    mach_msg_type_number_t *new_state_count
) {
    (void)exception_port;
    (void)exception;
    (void)code;
    (void)code_count;
    (void)flavor;
    (void)old_state;
    (void)old_state_count;
    (void)new_state;
    (void)new_state_count;
    return KERN_FAILURE;
}

kern_return_t catch_exception_raise_state_identity(
    mach_port_t exception_port,
    mach_port_t thread,
    mach_port_t task,
    exception_type_t exception,
    exception_data_t code,
    mach_msg_type_number_t code_count,
    int *flavor,
    thread_state_t old_state,
    mach_msg_type_number_t old_state_count,
    thread_state_t new_state,
    mach_msg_type_number_t *new_state_count
) {
    (void)exception_port;
    (void)thread;
    (void)task;
    (void)exception;
    (void)code;
    (void)code_count;
    (void)flavor;
    (void)old_state;
    (void)old_state_count;
    (void)new_state;
    (void)new_state_count;
    return KERN_FAILURE;
}

static kern_return_t wait_for_breakpoint(int timeout_seconds) {
    union {
        mach_msg_header_t head;
        union __RequestUnion__exc_subsystem request;
    } request;
    union {
        mach_msg_header_t head;
        union __ReplyUnion__exc_subsystem reply;
    } reply;

    struct timeval start;
    gettimeofday(&start, NULL);
    struct timeval last_refresh = start;
    while (!g_ctx.stop_requested) {
        struct timeval now;
        gettimeofday(&now, NULL);
        /* A dead task/PID is a terminal result, not another login timeout. */
        mach_port_type_t port_type = 0;
        kern_return_t port_kr = mach_port_type(mach_task_self(), g_ctx.task, &port_type);
        if ((port_kr == KERN_SUCCESS && (port_type & MACH_PORT_TYPE_DEAD_NAME) != 0) ||
            (g_ctx.target_pid > 0 && kill(g_ctx.target_pid, 0) < 0 && errno == ESRCH)) {
            return KERN_TERMINATED;
        }
        if ((now.tv_sec - start.tv_sec) >= timeout_seconds) {
            return KERN_OPERATION_TIMED_OUT;
        }

        if ((now.tv_sec - last_refresh.tv_sec) >= 1) {
            kern_return_t refresh_kr = refresh_hardware_breakpoints_if_needed();
            if (refresh_kr == KERN_TERMINATED || refresh_kr == MACH_SEND_INVALID_DEST) {
                return refresh_kr;
            }
            if (refresh_kr != KERN_SUCCESS) {
                return refresh_kr;
            }
            last_refresh = now;
        }

        kern_return_t kr = mach_msg(
            &request.head,
            MACH_RCV_MSG | MACH_RCV_TIMEOUT,
            0,
            sizeof(request),
            g_ctx.exception_port,
            1000,
            MACH_PORT_NULL
        );
        if (kr == MACH_RCV_TIMED_OUT) {
            continue;
        }
        if (kr != KERN_SUCCESS) {
            return kr;
        }
        if (!exc_server(&request.head, &reply.head)) {
            continue;
        }
        kr = mach_msg(&reply.head, MACH_SEND_MSG, reply.head.msgh_size, 0, MACH_PORT_NULL, MACH_MSG_TIMEOUT_NONE, MACH_PORT_NULL);
        if (kr != KERN_SUCCESS) {
            if (g_ctx.captured && (kr == MACH_SEND_INVALID_DEST || kr == KERN_TERMINATED)) {
                return KERN_SUCCESS;
            }
            return kr;
        }
    }
    return g_ctx.captured ? KERN_SUCCESS : KERN_ABORTED;
}

static int run_preflight(const options_t *options) {
    memset(&g_ctx, 0, sizeof(g_ctx));
    g_ctx.target_pid = options->pid;
    g_ctx.last_stage = "attach";
    kern_return_t kr = attach_task(options->pid, &g_ctx.task);
    if (kr != KERN_SUCCESS) {
        json_error("native_attach_failed", "task_for_pid failed");
        return 1;
    }
    g_ctx.last_stage = "resolve_breakpoint";
    kr = resolve_breakpoint_address(g_ctx.task, options, &g_ctx.breakpoint_address);
    if (kr != KERN_SUCCESS) {
        json_error("native_image_not_found", "wechat.dylib not found in target task");
        return 1;
    }
    uint32_t instruction = 0;
    g_ctx.last_stage = "read_breakpoint";
    kr = read_instruction(g_ctx.task, g_ctx.breakpoint_address, &instruction);
    if (kr != KERN_SUCCESS) {
        json_error("native_breakpoint_read_failed", "cannot read PBKDF stub instruction");
        return 1;
    }
    if (instruction != BR_X16_INSN) {
        json_error("native_breakpoint_shape_mismatch", "PBKDF stub layout changed");
        return 1;
    }
    g_ctx.last_stage = "install_breakpoint";
    kr = task_suspend(g_ctx.task);
    if (kr != KERN_SUCCESS) {
        json_error("native_cleanup_failed", "cannot safely suspend target for preflight");
        return 1;
    }
    kr = install_hardware_breakpoints(g_ctx.task);
    kern_return_t restore_kr = restore_hardware_breakpoints();
    kern_return_t resume_kr = task_resume(g_ctx.task);
    if (g_ctx.cleanup_failed || restore_kr != KERN_SUCCESS || resume_kr != KERN_SUCCESS) {
        json_error("native_cleanup_failed", "preflight debug state cleanup failed");
        return 1;
    }
    if (kr != KERN_SUCCESS) {
        json_error("native_breakpoint_install_failed", "cannot install hardware breakpoint");
        return 1;
    }
    json_success_preflight(options);
    return 0;
}

static int run_capture(const options_t *options) {
    memset(&g_ctx, 0, sizeof(g_ctx));
    g_ctx.target_pid = options->pid;
    install_signal_handlers();
    g_ctx.last_stage = "read_page1";
    const char *page1_source = options->page1_path[0] ? options->page1_path : options->database_path;
    if (!read_page1(page1_source, g_ctx.page1)) {
        json_error("native_probe_database_unreadable", "cannot read encrypted page1");
        return 1;
    }
    g_ctx.page1_loaded = true;

    g_ctx.last_stage = "attach";
    kern_return_t kr = attach_task(options->pid, &g_ctx.task);
    if (kr != KERN_SUCCESS) {
        json_error("native_attach_failed", "task_for_pid failed");
        return 1;
    }
    g_ctx.last_stage = "resolve_breakpoint";
    kr = resolve_breakpoint_address(g_ctx.task, options, &g_ctx.breakpoint_address);
    if (kr != KERN_SUCCESS) {
        json_error("native_image_not_found", "wechat.dylib not found in target task");
        return 1;
    }
    g_ctx.last_stage = "read_breakpoint";
    kr = read_instruction(g_ctx.task, g_ctx.breakpoint_address, &g_ctx.original_instruction);
    if (kr != KERN_SUCCESS) {
        json_error("native_breakpoint_read_failed", "cannot read PBKDF stub instruction");
        return 1;
    }
    if (g_ctx.original_instruction != BR_X16_INSN) {
        json_error("native_breakpoint_shape_mismatch", "PBKDF stub layout changed");
        return 1;
    }
    g_ctx.last_stage = "install_exception_port";
    kr = install_exception_port(g_ctx.task);
    if (kr != KERN_SUCCESS) {
        json_error("native_exception_port_failed", "cannot install breakpoint exception port");
        return 1;
    }

    g_ctx.last_stage = "install_breakpoint";
    kr = task_suspend(g_ctx.task);
    if (kr != KERN_SUCCESS) {
        restore_exception_ports(g_ctx.task);
        json_error("native_cleanup_failed", "cannot safely suspend target for capture");
        return 1;
    }
    kr = install_hardware_breakpoints(g_ctx.task);
    kern_return_t resume_kr = task_resume(g_ctx.task);
    if (kr != KERN_SUCCESS || resume_kr != KERN_SUCCESS) {
        (void)restore_hardware_breakpoints();
        restore_exception_ports(g_ctx.task);
        if (g_ctx.cleanup_failed || resume_kr != KERN_SUCCESS) {
            json_error("native_cleanup_failed", "capture startup debug state cleanup failed");
            return 1;
        }
        json_error("native_breakpoint_install_failed", "cannot install hardware breakpoint");
        return 1;
    }
    g_ctx.last_stage = "write_ready";
    if (!write_ready_file(options->ready_file, options->pid, options->transaction_id)) {
        kern_return_t suspend_kr = task_suspend(g_ctx.task);
        (void)restore_hardware_breakpoints();
        restore_exception_ports(g_ctx.task);
        if (suspend_kr == KERN_SUCCESS) {
            if (task_resume(g_ctx.task) != KERN_SUCCESS) {
                g_ctx.cleanup_failed = true;
            }
        } else {
            g_ctx.cleanup_failed = true;
        }
        if (g_ctx.cleanup_failed) {
            json_error("native_cleanup_failed", "readiness failure debug state cleanup failed");
            return 1;
        }
        json_error("native_ready_signal_failed", "cannot write monitor readiness signal");
        return 1;
    }

    g_ctx.last_stage = "waiting";
    kr = wait_for_breakpoint(options->timeout_seconds);

    if (g_ctx.captured) {
        /* The successful path intentionally terminated the disposable task. */
        (void)restore_hardware_breakpoints();
        restore_exception_ports(g_ctx.task);
    } else {
        kern_return_t suspend_kr = task_suspend(g_ctx.task);
        (void)restore_hardware_breakpoints();
        restore_exception_ports(g_ctx.task);
        if (suspend_kr == KERN_SUCCESS) {
            if (task_resume(g_ctx.task) != KERN_SUCCESS) {
                g_ctx.cleanup_failed = true;
            }
        } else if (suspend_kr != KERN_TERMINATED && suspend_kr != MACH_SEND_INVALID_DEST) {
            g_ctx.cleanup_failed = true;
        }
    }

    if (kr == KERN_TERMINATED || kr == MACH_SEND_INVALID_DEST) {
        json_error("native_capture_target_exited", "target process exited before capture completed");
        return 1;
    }
    if (g_ctx.cleanup_failed && !g_ctx.captured) {
        json_error("native_cleanup_failed", "capture debug state cleanup failed");
        return 1;
    }
    /* Signals can interrupt mach_msg with MACH_RCV_INTERRUPTED instead of
     * taking the ordinary loop exit; keep both paths explicitly classified. */
    if (g_ctx.stop_requested && !g_ctx.captured) {
        json_error("native_capture_interrupted", "capture helper was interrupted");
        return 1;
    }
    if (kr == KERN_OPERATION_TIMED_OUT) {
        json_error("native_capture_timeout", "timed out waiting for login-triggered PBKDF");
        return 1;
    }
    if (kr != KERN_SUCCESS) {
        json_error("native_capture_wait_failed", "breakpoint monitor failed");
        return 1;
    }
    if (!g_ctx.validated) {
        json_error("native_capture_unvalidated", "captured candidate did not validate against page1");
        return 1;
    }
    json_success_capture(options);
    return 0;
}

int main(int argc, char **argv) {
    options_t options;
    if (!parse_args(argc, argv, &options)) {
        json_error("native_invalid_arguments", "invalid arguments");
        return 1;
    }
    if (streq(options.mode, "preflight")) {
        return run_preflight(&options);
    }
    return run_capture(&options);
}
