import sys
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


import wechat_decrypt_tool.image_key_memory_scan as memory_scan
from wechat_decrypt_tool.image_key_memory_scan import (
    MEM_COMMIT,
    PAGE_GUARD,
    PAGE_NOACCESS,
    PAGE_READWRITE,
    PAGE_WRITECOPY,
    MemoryRegion,
    ProcessMemoryKeyMatch,
    find_verified_aes_key_in_chunk,
    find_wechat_pids,
    iter_memory_aes_candidates,
    scan_image_key_from_memory,
    scan_process_for_image_key,
)
from wechat_decrypt_tool.image_key_resolver import TemplateScanResult, V2Template


AES_KEY = "0123456789abcdef"
FULL_CANDIDATE = AES_KEY + "ABCDEF0123456789"


def _encrypted_block(aes_key: str = AES_KEY, prefix: bytes = b"\xff\xd8\xff") -> bytes:
    plaintext = prefix + (b"\x00" * (16 - len(prefix)))
    encryptor = Cipher(algorithms.AES(aes_key.encode("ascii")), modes.ECB()).encryptor()
    return encryptor.update(plaintext) + encryptor.finalize()


def _template_scan(tmp_path: Path, *, xor_key: int | None = 0x8A) -> TemplateScanResult:
    return TemplateScanResult(
        templates=(
            V2Template(
                path=tmp_path / "sample_t.dat",
                ciphertext=_encrypted_block(),
                mtime_ns=1,
                tail_xor_key=xor_key,
            ),
        ),
        inferred_xor_key=xor_key,
        used_fallback=False,
        files_scanned=1,
    )


class _FakeProcess:
    def __init__(self, pid: object, name: object) -> None:
        self.pid = pid
        self.info = {"pid": pid, "name": name}


def test_find_wechat_pids_returns_all_matching_processes() -> None:
    requested_attrs: list[tuple[str, ...]] = []

    def process_iter(attrs: tuple[str, ...]):
        requested_attrs.append(attrs)
        return (
            _FakeProcess(41, "Weixin.exe"),
            _FakeProcess(12, "wechat.EXE"),
            _FakeProcess(41, "Weixin.exe"),
            _FakeProcess(99, "helper.exe"),
            _FakeProcess(0, "WeChat.exe"),
        )

    assert find_wechat_pids(process_iter=process_iter) == (12, 41)
    assert requested_attrs == [("pid", "name")]


def test_win32_api_is_not_loaded_on_non_windows(monkeypatch) -> None:
    monkeypatch.setattr(memory_scan.sys, "platform", "linux")
    assert memory_scan._create_win32_api() is None


def test_macos_scanner_uses_bundled_helper_and_retries_with_elevation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    helper = tmp_path / "image_scan_helper"
    library = tmp_path / "libwx_key.dylib"
    helper.write_bytes(b"helper")
    library.write_bytes(b"library")
    scan = _template_scan(tmp_path)
    calls: list[tuple[Path, int, bool]] = []

    def run_helper(helper_path, pid, ciphertext, *, elevated, timeout):
        calls.append((helper_path, pid, elevated))
        return (AES_KEY, False) if elevated else (None, True)

    monkeypatch.setattr(memory_scan.sys, "platform", "darwin")
    monkeypatch.setattr(memory_scan, "mac_image_scan_helper_path", lambda: helper)
    monkeypatch.setattr(memory_scan, "mac_image_scan_library_path", lambda: library)
    monkeypatch.setattr(memory_scan, "_run_macos_image_scan_helper", run_helper)

    result = scan_process_for_image_key(321, scan)

    assert result == ProcessMemoryKeyMatch(
        aes_key=AES_KEY,
        template_path=scan.templates[0].path,
        encoding="ascii",
    )
    assert calls == [(helper, 321, False), (helper, 321, True)]


def test_candidate_extraction_requires_exact_32_character_runs() -> None:
    ascii_data = b"!" + FULL_CANDIDATE.encode("ascii") + b"?"
    utf16_data = b"!\x00" + FULL_CANDIDATE.encode("utf-16le") + b"?\x00"

    assert list(iter_memory_aes_candidates(ascii_data)) == [(AES_KEY, "ascii")]
    assert list(iter_memory_aes_candidates(utf16_data)) == [(AES_KEY, "utf-16le")]

    assert list(iter_memory_aes_candidates(b"!" + b"A" * 31 + b"?")) == []
    assert list(iter_memory_aes_candidates(b"!" + b"A" * 33 + b"?")) == []
    assert list(iter_memory_aes_candidates(b"!\x00" + (b"A\x00" * 33) + b"?\x00")) == []


def test_candidate_extraction_defers_unknown_chunk_boundaries() -> None:
    candidate = FULL_CANDIDATE.encode("ascii")
    assert list(
        iter_memory_aes_candidates(candidate, allow_start_boundary=False)
    ) == []
    assert list(
        iter_memory_aes_candidates(candidate, allow_end_boundary=False)
    ) == []


def test_chunk_candidate_must_verify_against_real_v2_ciphertext(tmp_path: Path) -> None:
    scan = _template_scan(tmp_path)
    match = find_verified_aes_key_in_chunk(
        b"!" + FULL_CANDIDATE.encode("ascii") + b"?",
        scan,
    )
    assert match == ProcessMemoryKeyMatch(
        aes_key=AES_KEY,
        template_path=scan.templates[0].path,
        encoding="ascii",
    )

    wrong = b"!fedcba9876543210ABCDEF0123456789?"
    assert find_verified_aes_key_in_chunk(wrong, scan) is None


class _FakeMemoryApi:
    def __init__(self, regions: list[MemoryRegion], memory: dict[int, bytes]) -> None:
        self.regions = iter(regions)
        self.memory = memory
        self.opened_pids: list[int] = []
        self.read_calls: list[tuple[int, int]] = []
        self.closed = 0

    def open_process(self, pid: int) -> object:
        self.opened_pids.append(pid)
        return object()

    def query_region(self, handle: object, address: int) -> MemoryRegion | None:
        return next(self.regions, None)

    def read_memory(self, handle: object, address: int, size: int) -> bytes:
        self.read_calls.append((address, size))
        for base, data in self.memory.items():
            if base <= address < base + len(data):
                offset = address - base
                return data[offset : offset + size]
        return b""

    def close_handle(self, handle: object) -> None:
        self.closed += 1


def test_process_scan_filters_regions_and_finds_cross_chunk_candidate(tmp_path: Path) -> None:
    chunk_size = memory_scan.MEMORY_CHUNK_SIZE
    valid_base = 0x6000_0000
    payload = (
        b"!" * (chunk_size - 10)
        + FULL_CANDIDATE.encode("ascii")
        + b"?"
    )
    regions = [
        MemoryRegion(0x1000, 4096, 0, PAGE_READWRITE),
        MemoryRegion(0x2000, 4096, MEM_COMMIT, PAGE_NOACCESS),
        MemoryRegion(0x3000, 4096, MEM_COMMIT, PAGE_READWRITE | PAGE_GUARD),
        MemoryRegion(
            0x4000,
            memory_scan.MAX_MEMORY_REGION_SIZE + 1,
            MEM_COMMIT,
            PAGE_WRITECOPY,
        ),
        MemoryRegion(valid_base, len(payload), MEM_COMMIT, PAGE_READWRITE),
    ]
    api = _FakeMemoryApi(regions, {valid_base: payload})

    match = scan_process_for_image_key(
        1234,
        _template_scan(tmp_path),
        memory_api=api,
    )

    assert match is not None
    assert match.aes_key == AES_KEY
    assert api.opened_pids == [1234]
    assert api.read_calls == [
        (valid_base, chunk_size),
        (valid_base + chunk_size, len(payload) - chunk_size),
    ]
    assert all(size <= chunk_size for _, size in api.read_calls)
    assert memory_scan.MEMORY_CHUNK_OVERLAP >= 65
    assert api.closed == 1


def test_process_scan_requires_templates_and_inferred_xor(tmp_path: Path) -> None:
    api = _FakeMemoryApi([], {})
    assert scan_process_for_image_key(1, _template_scan(tmp_path, xor_key=None), memory_api=api) is None
    assert api.opened_pids == []


def test_top_level_reenumerates_pids_and_reverifies_injected_result(
    tmp_path: Path,
    monkeypatch,
) -> None:
    scan = _template_scan(tmp_path)
    monkeypatch.setattr(memory_scan, "scan_v2_templates", lambda account_dir: scan)

    pid_rounds = iter(((101,), (202,)))
    pid_calls = 0
    scanner_calls: list[int] = []
    now = [0.0]

    def pid_provider() -> tuple[int, ...]:
        nonlocal pid_calls
        pid_calls += 1
        return next(pid_rounds)

    def process_scanner(pid, template_scan, progress):
        scanner_calls.append(pid)
        if pid == 101:
            return "fedcba9876543210"
        return ProcessMemoryKeyMatch(AES_KEY, tmp_path / "untrusted.dat", "utf-16le")

    def sleep(seconds: float) -> None:
        now[0] += seconds

    result = scan_image_key_from_memory(
        tmp_path,
        timeout=10,
        interval=5,
        pid_provider=pid_provider,
        process_scanner=process_scanner,
        sleep=sleep,
        clock=lambda: now[0],
    )

    assert result is not None
    assert result.pid == 202
    assert result.aes_key == AES_KEY
    assert result.xor_key == 0x8A
    assert result.verified is True
    assert result.template_path == scan.templates[0].path
    assert result.encoding == "utf-16le"
    assert result.as_dict()["xor_key_hex"] == "0x8A"
    assert pid_calls == 2
    assert scanner_calls == [101, 202]


def test_top_level_never_returns_unverified_scanner_candidate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    scan = _template_scan(tmp_path)
    monkeypatch.setattr(memory_scan, "scan_v2_templates", lambda account_dir: scan)

    result = scan_image_key_from_memory(
        tmp_path,
        timeout=0,
        pid_provider=lambda: (77,),
        process_scanner=lambda pid, templates, progress: "fedcba9876543210",
    )

    assert result is None


def test_top_level_stops_before_process_enumeration_without_xor(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        memory_scan,
        "scan_v2_templates",
        lambda account_dir: _template_scan(tmp_path, xor_key=None),
    )

    def unexpected_pid_provider():
        raise AssertionError("PID enumeration must not run without an inferred XOR key")

    assert scan_image_key_from_memory(tmp_path, pid_provider=unexpected_pid_provider) is None


def test_memory_scan_uses_only_newest_template_generation(tmp_path: Path) -> None:
    old_key = "fedcba9876543210"
    current_scan = _template_scan(tmp_path)
    scan = TemplateScanResult(
        templates=(
            current_scan.templates[0],
            V2Template(
                path=tmp_path / "old_t.dat",
                ciphertext=_encrypted_block(old_key),
                mtime_ns=0,
                tail_xor_key=0x2C,
            ),
        ),
        inferred_xor_key=0x2C,
        used_fallback=False,
        files_scanned=2,
    )

    old_candidate = b"!" + (old_key + "ABCDEF0123456789").encode("ascii") + b"?"
    current_candidate = b"!" + FULL_CANDIDATE.encode("ascii") + b"?"

    assert find_verified_aes_key_in_chunk(old_candidate, scan) is None
    assert find_verified_aes_key_in_chunk(current_candidate, scan) is not None


def test_memory_scan_can_use_same_generation_jpeg_xor_for_current_png(
    tmp_path: Path,
    monkeypatch,
) -> None:
    scan = TemplateScanResult(
        templates=(
            V2Template(
                path=tmp_path / "current-png_t.dat",
                ciphertext=_encrypted_block(AES_KEY, b"\x89PNG\r\n\x1a\n"),
                mtime_ns=2,
                tail_xor_key=None,
            ),
            V2Template(
                path=tmp_path / "same-generation-jpeg_t.dat",
                ciphertext=_encrypted_block(AES_KEY, b"\xff\xd8\xff"),
                mtime_ns=1,
                tail_xor_key=0x8A,
                tail_bytes=bytes((0x8A ^ 0xFF, 0x8A ^ 0xD9)),
            ),
        ),
        inferred_xor_key=None,
        used_fallback=False,
        files_scanned=2,
        xor_support=0,
    )
    monkeypatch.setattr(memory_scan, "scan_v2_templates", lambda account_dir, **kwargs: scan)

    result = scan_image_key_from_memory(
        tmp_path,
        timeout=10,
        pid_provider=lambda: (123,),
        process_scanner=lambda pid, templates, progress: AES_KEY,
    )

    assert result is not None
    assert result.aes_key == AES_KEY
    assert result.xor_key == 0x8A


def test_memory_scan_expands_past_non_jpeg_modal_tails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    current_png = V2Template(
        path=tmp_path / "current-png_t.dat",
        ciphertext=_encrypted_block(AES_KEY, b"\x89PNG\r\n\x1a\n"),
        mtime_ns=2,
        tail_xor_key=None,
        tail_bytes=b"\x10\x20",
    )
    initial_scan = TemplateScanResult(
        templates=(current_png,),
        inferred_xor_key=None,
        used_fallback=False,
        files_scanned=32,
        xor_support=32,
    )
    expanded_scan = TemplateScanResult(
        templates=(
            current_png,
            V2Template(
                path=tmp_path / "later-jpeg_t.dat",
                ciphertext=_encrypted_block(AES_KEY, b"\xff\xd8\xff"),
                mtime_ns=1,
                tail_xor_key=0x8A,
                tail_bytes=bytes((0x8A ^ 0xFF, 0x8A ^ 0xD9)),
            ),
        ),
        inferred_xor_key=None,
        used_fallback=False,
        files_scanned=100,
        xor_support=32,
    )
    scan_limits: list[int | None] = []

    def template_scan(account_dir, **kwargs):
        limit = kwargs.get("limit")
        scan_limits.append(limit)
        return expanded_scan if limit == 100 else initial_scan

    monkeypatch.setattr(memory_scan, "scan_v2_templates", template_scan)

    result = scan_image_key_from_memory(
        tmp_path,
        timeout=10,
        pid_provider=lambda: (123,),
        process_scanner=lambda pid, templates, progress: AES_KEY,
    )

    assert result is not None
    assert result.xor_key == 0x8A
    assert scan_limits == [None, 100]


def test_top_level_rejects_candidate_found_after_deadline(tmp_path: Path, monkeypatch) -> None:
    scan = _template_scan(tmp_path)
    monkeypatch.setattr(memory_scan, "scan_v2_templates", lambda account_dir: scan)
    now = [0.0]

    def slow_scanner(pid, template_scan, progress):
        now[0] = 11.0
        return AES_KEY

    result = scan_image_key_from_memory(
        tmp_path,
        timeout=10,
        pid_provider=lambda: (123,),
        process_scanner=slow_scanner,
        clock=lambda: now[0],
    )

    assert result is None


def test_top_level_timeout_includes_template_discovery(tmp_path: Path, monkeypatch) -> None:
    scan = _template_scan(tmp_path)
    now = [0.0]
    scan_calls: list[dict[str, object]] = []
    pid_calls = 0

    def slow_template_scan(account_dir, **kwargs):
        scan_calls.append(kwargs)
        now[0] = 11.0
        return scan

    def pid_provider():
        nonlocal pid_calls
        pid_calls += 1
        return (123,)

    monkeypatch.setattr(memory_scan, "scan_v2_templates", slow_template_scan)

    result = scan_image_key_from_memory(
        tmp_path,
        timeout=10,
        pid_provider=pid_provider,
        clock=lambda: now[0],
    )

    assert result is None
    assert scan_calls == [{}]
    assert pid_calls == 0
