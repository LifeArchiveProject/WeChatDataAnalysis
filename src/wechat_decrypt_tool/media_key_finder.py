import ctypes
import json
import os
import re
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from ctypes import wintypes
from functools import lru_cache
from pathlib import Path
from typing import Any

import pymem
import yara
from Crypto.Cipher import AES

PROCESS_ALL_ACCESS = 0x1F0FFF
MEM_COMMIT = 0x1000
MEM_PRIVATE = 0x20000

kernel32 = ctypes.windll.kernel32


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", ctypes.c_ulong),
        ("RegionSize", ctypes.c_size_t),
        ("State", ctypes.c_ulong),
        ("Protect", ctypes.c_ulong),
        ("Type", ctypes.c_ulong),
    ]


def _open_process(pid: int):
    return kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)


def _read_process_memory(process_handle, address: int, size: int) -> bytes | None:
    buffer = ctypes.create_string_buffer(size)
    bytes_read = ctypes.c_size_t(0)
    success = kernel32.ReadProcessMemory(
        process_handle,
        ctypes.c_void_p(address),
        buffer,
        size,
        ctypes.byref(bytes_read),
    )
    if not success:
        return None
    return buffer.raw


def _get_memory_regions(process_handle) -> list[tuple[int, int]]:
    regions: list[tuple[int, int]] = []
    mbi = MEMORY_BASIC_INFORMATION()
    address = 0
    while kernel32.VirtualQueryEx(
        process_handle,
        ctypes.c_void_p(address),
        ctypes.byref(mbi),
        ctypes.sizeof(mbi),
    ):
        if mbi.State == MEM_COMMIT and mbi.Type == MEM_PRIVATE:
            regions.append((int(mbi.BaseAddress), int(mbi.RegionSize)))
        address += int(mbi.RegionSize)
    return regions


@lru_cache
def _verify(encrypted: bytes, key: bytes) -> bool:
    aes_key = key[:16]
    cipher = AES.new(aes_key, AES.MODE_ECB)
    text = cipher.decrypt(encrypted)
    if text.startswith(b"\xff\xd8\xff"):
        return True
    if text.startswith(b"\x89PNG\r\n\x1a\n"):
        return True
    if text.startswith(b"GIF87a") or text.startswith(b"GIF89a"):
        return True
    if text.startswith(b"wxgf"):
        return True
    if len(text) >= 12 and text.startswith(b"RIFF") and text[8:12] == b"WEBP":
        return True
    if len(text) >= 8 and text[4:8] == b"ftyp":
        return True
    return False


def _search_memory_chunk(process_handle, base_address: int, region_size: int, encrypted: bytes, rules):
    memory = _read_process_memory(process_handle, base_address, region_size)
    if not memory:
        return None

    matches = rules.match(data=memory)
    if matches:
        for match in matches:
            if match.rule == "AesKey":
                for string in match.strings:
                    for instance in string.instances:
                        content = instance.matched_data[1:-1]
                        if _verify(encrypted, content):
                            return content[:16]
    return None


def _get_aes_key(encrypted: bytes, pid: int) -> Any:
    process_handle = _open_process(pid)
    if not process_handle:
        raise RuntimeError(f"无法打开进程 {pid}")

    rules_key = r"""
    rule AesKey {
        strings:
            $pattern = /[^0-9a-z]([0-9a-z]{16}|[0-9a-z]{32})[^0-9a-z]/ nocase
        condition:
            $pattern
    }
    """
    rules = yara.compile(source=rules_key)

    process_infos = _get_memory_regions(process_handle)

    found_result = threading.Event()
    result = [None]

    def process_chunk(args):
        if found_result.is_set():
            return None
        base_address, region_size = args
        res = _search_memory_chunk(process_handle, base_address, region_size, encrypted, rules)
        if res:
            result[0] = res
            found_result.set()
        return res

    with ThreadPoolExecutor(max_workers=min(32, len(process_infos) or 1)) as executor:
        executor.map(process_chunk, process_infos)

    kernel32.CloseHandle(process_handle)
    return result[0]


def _dump_wechat_info_v4(encrypted: bytes, pid: int) -> bytes:
    result = _get_aes_key(encrypted, pid)
    if isinstance(result, bytes):
        return result[:16]
    raise RuntimeError("未找到 AES 密钥")


def _sort_template_files_by_date(template_files: list[Path]) -> list[Path]:
    def get_date_from_path(filepath: Path) -> str:
        match = re.search(r"(\d{4}-\d{2})", str(filepath))
        if match:
            return match.group(1)
        return "0000-00"

    return sorted(template_files, key=get_date_from_path, reverse=True)


def find_key(
    weixin_dir: Path,
    version: int = 4,
    xor_key_: int | None = None,
    aes_key_: bytes | None = None,
) -> tuple[int, bytes]:
    if os.name != "nt":
        raise RuntimeError("仅支持 Windows")
    if version not in (3, 4):
        raise RuntimeError("version must be 3 or 4")

    template_files = _sort_template_files_by_date(list(weixin_dir.rglob("*_t.dat")))
    if not template_files:
        raise RuntimeError("未找到模板文件")

    last_bytes_list: list[bytes] = []
    for file in template_files[:16]:
        try:
            with open(file, "rb") as f:
                f.seek(-2, 2)
                last_bytes_list.append(f.read(2))
        except Exception:
            continue

    if not last_bytes_list:
        raise RuntimeError("对于 XOR, 未能成功读取任何模板文件")

    counter = Counter(last_bytes_list)
    most_common = counter.most_common(1)[0][0]

    x, y = most_common
    xor_key = x ^ 0xFF
    if xor_key != (y ^ 0xD9):
        raise RuntimeError("未能找到 XOR 密钥")

    if xor_key_ is not None:
        if xor_key_ != xor_key:
            raise RuntimeError("XOR 密钥校验失败")
        return xor_key_, aes_key_ or b""

    if version == 3:
        return xor_key, b"cfcd208495d565ef"

    ciphertext: bytes | None = None
    for file in template_files:
        with open(file, "rb") as f:
            if f.read(6) != b"\x07\x08V2\x08\x07":
                continue
            f.seek(-2, 2)
            if f.read(2) != most_common:
                continue
            f.seek(0xF)
            ciphertext = f.read(16)
            break

    if not ciphertext:
        raise RuntimeError("对于 AES, 未能成功读取任何模板文件")

    try:
        pm = pymem.Pymem("Weixin.exe")
        pid = pm.process_id
        if not isinstance(pid, int):
            raise RuntimeError("找不到微信进程")
    except Exception:
        raise RuntimeError("找不到微信进程")

    aes_key = _dump_wechat_info_v4(ciphertext, pid)
    return xor_key, aes_key


CONFIG_FILE = "config.json"


def read_key_from_config() -> tuple[int, bytes]:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            key_dict = json.loads(f.read())
        x, y = key_dict["xor"], key_dict["aes"]
        return x, y.encode()[:16]
    return 0, b""


def store_key(xor_k: int, aes_k: bytes) -> None:
    key_dict = {
        "xor": xor_k,
        "aes": aes_k.decode(),
    }
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        f.write(json.dumps(key_dict))
