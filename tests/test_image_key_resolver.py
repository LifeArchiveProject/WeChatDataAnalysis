import hashlib
import os
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool.image_key_resolver import (
    TemplateScanResult,
    V2_MAGIC,
    V2Template,
    clean_wxid,
    collect_wxid_candidates,
    derive_image_keys,
    enumerate_kvcomm_codes,
    infer_xor_key_from_v2_tails,
    resolve_local_image_key,
    scan_v2_templates,
    trusted_xor_for_verified_aes_key,
    verify_aes_key,
    verify_key_pair,
)


def _encrypt_first_block(aes_key: str, prefix: bytes) -> bytes:
    plaintext = prefix + (b"\x00" * (16 - len(prefix)))
    encryptor = Cipher(algorithms.AES(aes_key.encode("ascii")), modes.ECB()).encryptor()
    return encryptor.update(plaintext) + encryptor.finalize()


def _write_v2_template(
    path: Path,
    *,
    aes_key: str,
    xor_key: int,
    prefix: bytes = b"\xff\xd8\xff",
    mtime_ns: int | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    ciphertext = _encrypt_first_block(aes_key, prefix)
    tail = bytes((xor_key ^ 0xFF, xor_key ^ 0xD9))
    path.write_bytes(V2_MAGIC + (b"\x00" * 9) + ciphertext + b"payload" + tail)
    if mtime_ns is not None:
        os.utime(path, ns=(mtime_ns, mtime_ns))
    return path


def test_enumerate_kvcomm_codes_deduplicates_and_filters(tmp_path: Path) -> None:
    kvcomm = tmp_path / "kvcomm"
    kvcomm.mkdir()
    for name in (
        "key_123_first.statistic",
        "key_123_second.statistic",
        "key_456_any.STATISTIC",
        "key_0_zero.statistic",
        "key_4294967296_too_large.statistic",
        "key_not-a-number_bad.statistic",
        "prefix_key_789_bad.statistic",
    ):
        (kvcomm / name).write_bytes(b"")
    (kvcomm / "key_789_directory.statistic").mkdir()

    assert enumerate_kvcomm_codes(kvcomm) == (123, 456)
    assert enumerate_kvcomm_codes(tmp_path / "missing") == ()


def test_collect_wxid_candidates_cleans_and_deduplicates_in_priority_order() -> None:
    assert clean_wxid(" wxid_alpha_ab12 ") == "wxid_alpha"
    assert clean_wxid("wxid_alpha_more_parts") == "wxid_alpha"
    assert clean_wxid("custom_account_ab12") == "custom_account_ab12"

    candidates = collect_wxid_candidates(
        target_wxid=" wxid_alpha_ab12 ",
        account="wxid_alpha",
        local_native_wxids=["wxid_beta_dead", "wxid_beta", "custom_account_ab12", ""],
    )

    assert candidates == ("wxid_alpha", "wxid_beta", "custom_account_ab12", "unknown")


def test_collect_wxid_candidates_keeps_unknown_as_verified_last_resort() -> None:
    assert collect_wxid_candidates() == ("unknown",)
    assert collect_wxid_candidates(target_wxid="wxid_target") == ("wxid_target", "unknown")
    assert collect_wxid_candidates(local_native_wxids="unknown") == ("unknown",)


def test_derive_image_keys_uses_cleaned_wxid_and_ascii_md5_prefix() -> None:
    code = 0x1234AB
    result = derive_image_keys(code, "wxid_example_dead")

    expected = hashlib.md5(f"{code}wxid_example".encode("utf-8")).hexdigest()[:16]
    assert result.xor_key == (code & 0xFF)
    assert result.aes_key == expected
    assert len(result.aes_key.encode("ascii")) == 16


@pytest.mark.parametrize(
    "prefix",
    [
        b"\xff\xd8\xff",
        b"\x89PNG\r\n\x1a\n",
        b"RIFF\x00\x00\x00\x00WEBP",
        b"wxgf",
        b"WXGF",
        b"GIF89a",
    ],
)
def test_verify_aes_key_accepts_weflow_image_signatures(prefix: bytes) -> None:
    aes_key = "0123456789abcdef"
    ciphertext = _encrypt_first_block(aes_key, prefix)

    assert verify_aes_key(aes_key, ciphertext)
    assert not verify_aes_key("fedcba9876543210", ciphertext)


def test_scan_v2_templates_prefers_recent_attach_img_files(tmp_path: Path) -> None:
    account_dir = tmp_path / "wxid_test_abcd"
    aes_key = "0123456789abcdef"
    old_path = _write_v2_template(
        account_dir / "msg" / "attach" / "contact-a" / "2025-12" / "Img" / "old_t.dat",
        aes_key=aes_key,
        xor_key=0xA6,
        mtime_ns=1_000_000_000,
    )
    new_path = _write_v2_template(
        account_dir / "msg" / "attach" / "contact-b" / "2026-07" / "Img" / "new_t.dat",
        aes_key=aes_key,
        xor_key=0xA6,
        mtime_ns=2_000_000_000,
    )
    _write_v2_template(
        account_dir / "cache" / "newest_fallback_t.dat",
        aes_key=aes_key,
        xor_key=0x55,
        mtime_ns=3_000_000_000,
    )

    scan = scan_v2_templates(account_dir)

    assert [item.path for item in scan.templates] == [new_path, old_path]
    assert scan.inferred_xor_key == 0xA6
    assert scan.xor_support == 2
    assert scan.used_fallback is False
    assert scan.files_scanned == 2


def test_scan_v2_templates_uses_bounded_fallback(tmp_path: Path) -> None:
    account_dir = tmp_path / "wxid_test"
    aes_key = "0123456789abcdef"
    fallback_path = _write_v2_template(
        account_dir / "cache" / "2026-07" / "Img" / "fallback_t.dat",
        aes_key=aes_key,
        xor_key=0x42,
    )
    _write_v2_template(
        account_dir / "cache" / "thumbnail-cache" / "ignored_t.dat",
        aes_key=aes_key,
        xor_key=0x42,
    )

    bounded = scan_v2_templates(account_dir, max_fallback_dirs=1)
    complete = scan_v2_templates(account_dir, max_fallback_dirs=10)

    assert bounded.used_fallback is True
    assert bounded.templates == ()
    assert [item.path for item in complete.templates] == [fallback_path]
    assert complete.inferred_xor_key == 0x42
    assert complete.xor_support == 1


def test_infer_xor_key_uses_mode_of_valid_tail_pairs() -> None:
    def tail(key: int) -> bytes:
        return bytes((key ^ 0xFF, key ^ 0xD9))

    tails = [tail(0xA6), tail(0xA6), tail(0x22), b"\x00\x00", b"bad"]
    assert infer_xor_key_from_v2_tails(tails) == 0xA6
    assert infer_xor_key_from_v2_tails([b"\x00\x00"]) is None

    # Do not cherry-pick an accidental valid-looking pair from non-modal tails.
    assert infer_xor_key_from_v2_tails([b"\x01\x02", tail(0x42), b"\x03\x04"]) is None


def test_resolve_local_image_key_checks_all_codes_and_cleaned_wxids(tmp_path: Path) -> None:
    kvcomm = tmp_path / "kvcomm"
    kvcomm.mkdir()
    (kvcomm / "key_111_old.statistic").write_bytes(b"")
    correct_code = 0x1234
    (kvcomm / f"key_{correct_code}_current.statistic").write_bytes(b"")

    account_dir = tmp_path / "wxid_real_abcd"
    correct_keys = derive_image_keys(correct_code, "wxid_real")
    template_path = _write_v2_template(
        account_dir / "msg" / "attach" / "contact" / "2026-07" / "Img" / "image_t.dat",
        aes_key=correct_keys.aes_key,
        xor_key=correct_keys.xor_key,
    )

    result = resolve_local_image_key(
        kvcomm_dir=kvcomm,
        account_dir=account_dir,
        target_wxid="wxid_wrong",
        account="custom_account_abcd",
        local_native_wxids=["wxid_real_dead", "wxid_real"],
    )

    assert result is not None
    assert result.verified is True
    assert result.code == correct_code
    assert result.wxid == "wxid_real"
    assert result.xor_key == correct_keys.xor_key
    assert result.aes_key == correct_keys.aes_key
    assert result.template_path == template_path
    assert result.inferred_xor_key == correct_keys.xor_key
    assert result.as_dict()["xor_key_hex"] == f"0x{correct_keys.xor_key:02X}"


def test_verify_key_pair_and_resolver_can_reuse_template_scan(tmp_path: Path) -> None:
    kvcomm = tmp_path / "kvcomm"
    kvcomm.mkdir()
    code = 998877
    (kvcomm / f"key_{code}_current.statistic").write_bytes(b"")

    account_dir = tmp_path / "wxid_native_dead"
    keys = derive_image_keys(code, "wxid_native")
    template_path = _write_v2_template(
        account_dir / "cache" / "image_t.dat",
        aes_key=keys.aes_key,
        xor_key=keys.xor_key,
    )
    scan = scan_v2_templates(account_dir)

    assert verify_key_pair(keys.xor_key, keys.aes_key, scan)
    assert not verify_key_pair(
        (keys.xor_key + 1) & 0xFF,
        keys.aes_key,
        scan,
    )
    assert verify_key_pair(
        (keys.xor_key + 1) & 0xFF,
        keys.aes_key,
        scan,
        require_xor_match=False,
    )

    scan_without_xor = TemplateScanResult(
        templates=tuple(
            V2Template(
                path=template.path,
                ciphertext=template.ciphertext,
                mtime_ns=template.mtime_ns,
                tail_xor_key=None,
            )
            for template in scan.templates
        ),
        inferred_xor_key=None,
        used_fallback=scan.used_fallback,
        files_scanned=scan.files_scanned,
    )
    assert not verify_key_pair(keys.xor_key, keys.aes_key, scan_without_xor)
    assert verify_key_pair(
        keys.xor_key,
        keys.aes_key,
        scan_without_xor,
        require_xor_match=False,
    )

    template_path.unlink()
    result = resolve_local_image_key(
        kvcomm_dir=kvcomm,
        account_dir=account_dir,
        local_native_wxids="wxid_native",
        template_scan=scan,
    )
    assert result is not None
    assert result.verified is True


def test_resolver_uses_newest_ciphertext_instead_of_an_old_template_match(
    tmp_path: Path,
) -> None:
    kvcomm = tmp_path / "kvcomm"
    kvcomm.mkdir()
    old_code = 100
    current_code = 200
    for code in (old_code, current_code):
        (kvcomm / f"key_{code}_candidate.statistic").write_bytes(b"")

    wxid = "wxid_demo"
    old_keys = derive_image_keys(old_code, wxid)
    current_keys = derive_image_keys(current_code, wxid)
    scan = TemplateScanResult(
        templates=(
            V2Template(
                path=tmp_path / "current_t.dat",
                ciphertext=_encrypt_first_block(current_keys.aes_key, b"\x89PNG\r\n\x1a\n"),
                mtime_ns=2,
                tail_xor_key=None,
            ),
            V2Template(
                path=tmp_path / "old_t.dat",
                ciphertext=_encrypt_first_block(old_keys.aes_key, b"\xff\xd8\xff"),
                mtime_ns=1,
                tail_xor_key=old_keys.xor_key,
            ),
        ),
        inferred_xor_key=old_keys.xor_key,
        used_fallback=False,
        files_scanned=2,
    )

    result = resolve_local_image_key(
        kvcomm_dir=kvcomm,
        account_dir=tmp_path / "wxid_demo_abcd",
        target_wxid=wxid,
        template_scan=scan,
    )

    assert result is not None
    assert result.code == current_code
    assert result.aes_key == current_keys.aes_key
    assert result.template_path == tmp_path / "current_t.dat"
    assert not verify_key_pair(old_keys.xor_key, old_keys.aes_key, scan)


def test_trusted_xor_uses_only_templates_from_the_verified_aes_generation(
    tmp_path: Path,
) -> None:
    current_aes = "0123456789abcdef"
    old_aes = "fedcba9876543210"
    current_xor = 0x8A
    old_xor = 0x2C

    def template(
        name: str,
        aes_key: str,
        xor_key: int,
        mtime_ns: int,
        prefix: bytes,
    ) -> V2Template:
        tail = bytes((xor_key ^ 0xFF, xor_key ^ 0xD9))
        return V2Template(
            path=tmp_path / name,
            ciphertext=_encrypt_first_block(aes_key, prefix),
            mtime_ns=mtime_ns,
            tail_xor_key=xor_key,
            tail_bytes=tail,
        )

    scan = TemplateScanResult(
        templates=(
            template("current-1_t.dat", current_aes, current_xor, 5, b"\x89PNG\r\n\x1a\n"),
            template("current-2_t.dat", current_aes, current_xor, 4, b"\xff\xd8\xff"),
            template("old-1_t.dat", old_aes, old_xor, 3, b"\xff\xd8\xff"),
            template("old-2_t.dat", old_aes, old_xor, 2, b"\xff\xd8\xff"),
            template("old-3_t.dat", old_aes, old_xor, 1, b"\xff\xd8\xff"),
        ),
        inferred_xor_key=old_xor,
        used_fallback=False,
        files_scanned=5,
        xor_support=3,
    )

    assert trusted_xor_for_verified_aes_key(current_aes, scan) == current_xor
    assert verify_key_pair(current_xor, current_aes, scan)
    assert not verify_key_pair(old_xor, current_aes, scan)


def test_trusted_xor_ignores_non_jpeg_tails_within_the_same_aes_generation(
    tmp_path: Path,
) -> None:
    aes_key = "0123456789abcdef"
    correct_xor = 0x8A
    misleading_xor = 0x2C

    def template(name: str, prefix: bytes, xor_key: int, mtime_ns: int) -> V2Template:
        return V2Template(
            path=tmp_path / name,
            ciphertext=_encrypt_first_block(aes_key, prefix),
            mtime_ns=mtime_ns,
            tail_xor_key=xor_key,
            tail_bytes=bytes((xor_key ^ 0xFF, xor_key ^ 0xD9)),
        )

    scan = TemplateScanResult(
        templates=(
            template("current-png_t.dat", b"\x89PNG\r\n\x1a\n", misleading_xor, 5),
            template("other-png-1_t.dat", b"\x89PNG\r\n\x1a\n", misleading_xor, 4),
            template("other-png-2_t.dat", b"\x89PNG\r\n\x1a\n", misleading_xor, 3),
            template("jpeg-1_t.dat", b"\xff\xd8\xff", correct_xor, 2),
            template("jpeg-2_t.dat", b"\xff\xd8\xff", correct_xor, 1),
        ),
        inferred_xor_key=misleading_xor,
        used_fallback=False,
        files_scanned=5,
        xor_support=3,
    )

    assert trusted_xor_for_verified_aes_key(aes_key, scan) == correct_xor
    assert verify_key_pair(correct_xor, aes_key, scan)
    assert not verify_key_pair(misleading_xor, aes_key, scan)


def test_resolver_never_returns_an_unverified_fallback(tmp_path: Path) -> None:
    kvcomm = tmp_path / "kvcomm"
    kvcomm.mkdir()
    (kvcomm / "key_123_candidate.statistic").write_bytes(b"")
    account_dir = tmp_path / "wxid_candidate_dead"
    account_dir.mkdir()

    assert resolve_local_image_key(kvcomm_dir=kvcomm, account_dir=account_dir) is None

    wrong_keys = derive_image_keys(999, "wxid_other")
    _write_v2_template(
        account_dir / "cache" / "wrong_t.dat",
        aes_key=wrong_keys.aes_key,
        xor_key=wrong_keys.xor_key,
    )
    assert resolve_local_image_key(kvcomm_dir=kvcomm, account_dir=account_dir) is None
