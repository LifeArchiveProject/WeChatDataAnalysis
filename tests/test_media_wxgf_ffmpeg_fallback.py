"""wxgf（HEVC）图片在没有 WxAM 解码器时（非 Windows）改由 ffmpeg 解码。"""

import asyncio
import ctypes
import functools
import io
import logging
import os
import subprocess

import pytest
from PIL import Image

from wechat_decrypt_tool import media_helpers


JPEG = b"\xff\xd8\xff\xe0" + bytes(16) + b"\xff\xd9"
VPS = b"\x00\x00\x00\x01\x40\x01"
# IDR 条带的起始码 + NAL 头，后一个字节的最高位是 first_slice_segment_in_pic_flag。
IDR = b"\x00\x00\x01\x26\x01\x80"
# 真实文件在头部和码流之间夹着 ICC 等元数据，里面会出现形似起始码的字节。
METADATA = b"\x03\x02\x02\x00\x01" + b"\x00\x00\x01\x2a" * 4 + b"\x00\x00\x00\x01\x00\x00"
# 单分区文件在码流之后还有 24 字节容器数据，里面同样可能出现起始码。
TAIL = IDR * 4
FAKE_FFMPEG = "/fake/bin/ffmpeg"


def hevc(body=b"picture", pictures=1):
    return VPS + (IDR + body) * pictures


def wxgf(*partitions, tail=TAIL):
    """按真实文件的布局拼容器：19 字节头、元数据，然后是带 4 字节大端长度前缀的各分区。"""
    header = b"wxgf\x13\x00\x02\x00\xa0\x00\x78" + bytes(5) + b"\x40\x01\xa2"
    return header + METADATA + b"".join(len(part).to_bytes(4, "big") + part for part in partitions) + tail


class FfmpegSpy:
    def __init__(self, returncode=0, stdout=JPEG, stderr=b"decode error", error=None, alpha=b"\xff" * 16):
        self.calls = []
        self.returncode, self.stdout, self.stderr, self.error, self.alpha = returncode, stdout, stderr, error, alpha

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if self.error is not None:
            raise self.error
        stdout = self.alpha if "rawvideo" in command else self.stdout
        return subprocess.CompletedProcess(command, self.returncode, stdout=stdout, stderr=self.stderr)


@pytest.fixture(autouse=True)
def empty_conversion_cache():
    media_helpers._WXGF_FFMPEG_CACHE.clear()
    yield
    media_helpers._WXGF_FFMPEG_CACHE.clear()


@pytest.fixture
def use_ffmpeg(monkeypatch):
    """默认按非 Windows 处理：没有 WxAM 解码器，ffmpeg 可用但被替身接管。"""
    monkeypatch.setattr(media_helpers, "_get_wxam_decoder", lambda: None)
    monkeypatch.setattr(media_helpers, "_find_ffmpeg_executable", lambda: FAKE_FFMPEG)

    def install(**kwargs):
        spy = FfmpegSpy(**kwargs)
        monkeypatch.setattr(subprocess, "run", spy)
        return spy

    return install


def test_fallback_pipes_only_the_picture_stream_through_ffmpeg(use_ffmpeg):
    ffmpeg = use_ffmpeg()
    picture = hevc(b"main picture" * 8)

    assert media_helpers._wxgf_to_image_bytes(wxgf(picture)) == JPEG

    (command, kwargs), = ffmpeg.calls
    assert command[0] == FAKE_FFMPEG
    assert command[command.index("-i") + 1] == "pipe:0" and command[-1] == "pipe:1"
    assert command[command.index("-frames:v") + 1] == "1"
    # 解码出错即失败，不输出残缺的画面。
    assert "-xerror" in command
    assert command[command.index("-err_detect") + 1] == "explode"
    assert command.index("-err_detect") < command.index("-i")
    # 解码尺寸有上限，且作为输入选项放在 -i 之前。
    assert command[command.index("-max_pixels") + 1] == str(media_helpers._WXGF_FFMPEG_MAX_PIXELS)
    assert command.index("-max_pixels") < command.index("-i")
    # 只喂码流本身：不含容器头、元数据、长度前缀和尾部数据。
    assert kwargs["input"] == picture
    assert 0 < kwargs["timeout"] <= 60
    assert kwargs["creationflags"] == (subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)


def test_fallback_returns_none_without_ffmpeg(use_ffmpeg, monkeypatch):
    ffmpeg = use_ffmpeg()
    monkeypatch.setattr(media_helpers, "_find_ffmpeg_executable", lambda: "")

    assert media_helpers._wxgf_to_image_bytes(wxgf(hevc())) is None
    assert ffmpeg.calls == []


@pytest.mark.parametrize(
    "failure",
    [
        {"returncode": 1, "stdout": b""},
        {"returncode": 1},
        {"stdout": b""},
        {"stdout": b"not a jpeg"},
        {"error": subprocess.TimeoutExpired(FAKE_FFMPEG, 1)},
        {"error": OSError("exec format error")},
    ],
    ids=["non-zero-exit", "non-zero-exit-with-output", "no-output", "garbage-output", "timeout", "spawn-error"],
)
def test_fallback_never_raises_on_ffmpeg_failure(use_ffmpeg, failure):
    ffmpeg = use_ffmpeg(**failure)

    assert media_helpers._wxgf_to_image_bytes(wxgf(hevc())) is None
    assert len(ffmpeg.calls) == 1


@pytest.mark.parametrize(
    "payload",
    [
        b"wxgf",
        b"wxgf\x13" + bytes(range(256)) * 4,
        b"wxgf\x13" + METADATA + IDR + b"slice only",
        wxgf(VPS + b"parameter sets only"),
        # 长度前缀比剩余数据长：文件被截断。
        wxgf(hevc(b"main picture" * 8))[:-40],
        # 多帧（动图）：单帧 JPEG 表示不了，留给调用方原有的回退。
        wxgf(hevc(pictures=3)),
        # 真实文件至多 [alpha, 画面] 两个分区，更多的一律不解码。
        wxgf(hevc(b"alpha"), hevc(b"alpha"), hevc()),
        # 一张图片不会有这么多 NAL。
        wxgf(VPS + b"\x00\x00\x01\x4e\x01" * (media_helpers._WXGF_MAX_NAL_UNITS + 1) + IDR + b"picture"),
    ],
    ids=[
        "header-only",
        "no-start-code",
        "no-parameter-sets",
        "no-picture",
        "truncated-file",
        "animation",
        "too-many-partitions",
        "too-many-nal-units",
    ],
)
def test_fallback_does_not_spawn_without_a_single_decodable_picture(use_ffmpeg, payload):
    ffmpeg = use_ffmpeg()

    assert media_helpers._wxgf_to_image_bytes(payload) is None
    assert ffmpeg.calls == []


def test_prefix_scan_does_not_spawn_for_a_stray_wxgf_marker(use_ffmpeg):
    ffmpeg = use_ffmpeg()
    payload = bytes(64) + b"wxgf" + bytes(range(256)) * 64

    assert media_helpers._try_strip_media_prefix(payload) == (payload, "application/octet-stream")
    assert ffmpeg.calls == []


def test_fallback_decodes_the_picture_behind_an_opaque_alpha_partition(use_ffmpeg):
    ffmpeg = use_ffmpeg()
    # 画面分区 300 字节，它的长度前缀 00 00 01 2c 紧跟在 alpha 分区后面，本身就像一个起始码。
    alpha, picture = hevc(b"alpha"), hevc(b"p" * 288)
    assert len(picture) == 300

    assert media_helpers._wxgf_to_image_bytes(wxgf(alpha, picture, tail=b"")) == JPEG

    (alpha_command, alpha_kwargs), (picture_command, picture_kwargs) = ffmpeg.calls
    assert alpha_command[alpha_command.index("-pix_fmt") + 1] == "gray" and "rawvideo" in alpha_command
    assert alpha_kwargs["input"] == alpha
    assert "mjpeg" in picture_command
    assert picture_kwargs["input"] == picture


def test_partitions_share_one_deadline(use_ffmpeg, monkeypatch):
    ffmpeg = use_ffmpeg()
    clock = iter([100.0, 100.0, 112.0])
    monkeypatch.setattr(media_helpers.time, "monotonic", lambda: next(clock))

    assert media_helpers._wxgf_to_image_bytes(wxgf(hevc(b"alpha"), hevc())) == JPEG

    (_, alpha_kwargs), (_, picture_kwargs) = ffmpeg.calls
    budget = media_helpers._WXGF_FFMPEG_TIMEOUT_SECONDS
    assert alpha_kwargs["timeout"] == budget
    # alpha 分区用掉的 12 秒从画面分区的时限里扣除。
    assert picture_kwargs["timeout"] == budget - 12


def test_picture_is_not_decoded_once_the_deadline_has_passed(use_ffmpeg, monkeypatch):
    ffmpeg = use_ffmpeg()
    clock = iter([100.0, 100.0, 100.0 + media_helpers._WXGF_FFMPEG_TIMEOUT_SECONDS])
    monkeypatch.setattr(media_helpers.time, "monotonic", lambda: next(clock))

    assert media_helpers._wxgf_to_image_bytes(wxgf(hevc(b"alpha"), hevc())) is None
    assert len(ffmpeg.calls) == 1


@pytest.mark.parametrize("alpha_plane", [b"\xff" * 15 + b"\x80", b""], ids=["translucent", "undecodable"])
def test_fallback_declines_a_picture_with_transparency(use_ffmpeg, alpha_plane):
    ffmpeg = use_ffmpeg(alpha=alpha_plane)

    assert media_helpers._wxgf_to_image_bytes(wxgf(hevc(b"alpha"), hevc())) is None
    # 画面分区不再解码：结果只会是丢了透明度的 JPEG。
    assert len(ffmpeg.calls) == 1


def test_emoji_route_still_fetches_the_remote_gif_for_an_animated_wxgf(use_ffmpeg, monkeypatch, tmp_path):
    from wechat_decrypt_tool.routers import chat_media

    ffmpeg = use_ffmpeg()
    local = tmp_path / "sticker.dat"
    local.write_bytes(wxgf(hevc(pictures=3)))
    gif = b"GIF89a" + bytes(16) + b"\x3b"
    monkeypatch.setattr(chat_media, "_resolve_account_dir", lambda _account: tmp_path)
    monkeypatch.setattr(chat_media, "_resolve_account_wxid_dir", lambda _account_dir: None)
    monkeypatch.setattr(chat_media, "_resolve_media_path_for_kind", lambda *_args, **_kwargs: local)
    monkeypatch.setattr(chat_media, "_try_fetch_emoticon_from_remote", lambda _account_dir, _md5: (gif, "image/gif"))

    response = asyncio.run(chat_media.get_chat_emoji(md5="0123456789abcdef0123456789abcdef", account="wxid_demo"))

    assert (response.body, response.media_type) == (gif, "image/gif")
    assert ffmpeg.calls == []


def test_same_payload_is_converted_only_once(use_ffmpeg):
    ffmpeg = use_ffmpeg()
    payload = wxgf(hevc())

    assert media_helpers._wxgf_to_image_bytes(payload) == JPEG
    assert media_helpers._wxgf_to_image_bytes(bytes(payload)) == JPEG
    assert len(ffmpeg.calls) == 1


def test_undecodable_file_spawns_ffmpeg_once_per_read(use_ffmpeg, tmp_path):
    # 读取路径会从多个入口把同一份 wxgf 交给转换函数，失败结果也要记住。
    ffmpeg = use_ffmpeg(returncode=1, stdout=b"")
    path = tmp_path / "0123456789abcdef0123456789abcdef.dat"
    path.write_bytes(wxgf(hevc()))

    for _ in range(2):
        data, media_type = media_helpers._read_and_maybe_decrypt_media(path)
        assert (data, media_type) == (path.read_bytes(), "application/octet-stream")
    assert len(ffmpeg.calls) == 1


def test_conversion_cache_stays_within_its_byte_budget(use_ffmpeg, monkeypatch):
    use_ffmpeg()
    monkeypatch.setattr(media_helpers, "_WXGF_FFMPEG_CACHE_BYTES", 2 * len(JPEG))

    for index in range(5):
        assert media_helpers._wxgf_to_image_bytes(wxgf(hevc(b"picture %d" % index))) == JPEG

    assert len(media_helpers._WXGF_FFMPEG_CACHE) == 2


def test_failure_log_keeps_only_the_end_of_ffmpeg_stderr(use_ffmpeg, caplog):
    use_ffmpeg(returncode=1, stdout=b"", stderr=b"decode error\n" * 20_000 + b"last line")

    with caplog.at_level(logging.WARNING, logger=media_helpers.logger.name):
        assert media_helpers._wxgf_to_image_bytes(wxgf(hevc())) is None

    (record,) = caplog.records
    assert "last line" in record.getMessage() and "rc=1" in record.getMessage()
    assert len(record.getMessage()) < 1000


def _wxam_decoder(result, output=JPEG):
    def decode(_input, _input_size, output_address, output_size, _config):
        ctypes.memmove(output_address, output, len(output))
        output_size._obj.value = len(output)
        return result

    return decode


def test_wxam_decoder_success_does_not_call_ffmpeg(use_ffmpeg, monkeypatch):
    ffmpeg = use_ffmpeg()
    monkeypatch.setattr(media_helpers, "_get_wxam_decoder", lambda: _wxam_decoder(0))

    assert media_helpers._wxgf_to_image_bytes(wxgf(hevc())) == JPEG
    assert ffmpeg.calls == []


def test_wxam_decoder_failure_does_not_fall_back_to_ffmpeg(use_ffmpeg, monkeypatch):
    # Windows 上解码器存在时行为不变：它拒绝的数据不再交给 ffmpeg。
    ffmpeg = use_ffmpeg()
    monkeypatch.setattr(media_helpers, "_get_wxam_decoder", lambda: _wxam_decoder(-1))

    assert media_helpers._wxgf_to_image_bytes(wxgf(hevc())) is None
    assert ffmpeg.calls == []


@pytest.fixture
def real_ffmpeg(monkeypatch):
    # 绕过模块级缓存做一次真实查找，不改动其他测试会用到的缓存。
    ffmpeg_exe = media_helpers._find_ffmpeg_executable.__wrapped__()
    if not ffmpeg_exe:
        pytest.skip("未找到 ffmpeg（可用 WECHAT_TOOL_FFMPEG 指定）")
    monkeypatch.setattr(media_helpers, "_get_wxam_decoder", lambda: None)
    monkeypatch.setattr(media_helpers, "_find_ffmpeg_executable", lambda: ffmpeg_exe)
    return functools.partial(_encode_hevc, ffmpeg_exe)


@functools.lru_cache(maxsize=None)
def _encode_hevc(ffmpeg_exe, source, frames=1, pix_fmt="yuv420p", lossless=False):
    proc = subprocess.run(
        [
            ffmpeg_exe, "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", source,
            "-frames:v", str(frames), "-pix_fmt", pix_fmt,
            "-c:v", "libx265", "-x265-params", "log-level=none" + (":lossless=1" if lossless else ""),
            "-f", "hevc", "pipe:1",
        ],
        capture_output=True,
        timeout=120,
    )
    if proc.returncode != 0 or not proc.stdout.startswith(VPS):
        pytest.skip("ffmpeg 的 libx265 不可用，无法生成 HEVC 测试图")
    return proc.stdout


@pytest.mark.parametrize("with_alpha", [False, True], ids=["opaque", "opaque-alpha-partition"])
def test_real_ffmpeg_decodes_a_static_picture(real_ffmpeg, with_alpha):
    picture = real_ffmpeg("testsrc=size=160x120")
    partitions = (picture,)
    if with_alpha:
        # 真实文件先是 alpha 分区，后面才是画面；alpha 是全范围灰度，全不透明时每个像素都是 255。
        partitions = (real_ffmpeg("color=c=white:size=160x120", pix_fmt="gray", lossless=True), picture)

    converted = media_helpers._wxgf_to_image_bytes(wxgf(*partitions))

    assert converted is not None and converted.startswith(b"\xff\xd8\xff")
    with Image.open(io.BytesIO(converted)) as image:
        image.load()
        assert (image.format, image.size) == ("JPEG", (160, 120))


def test_real_ffmpeg_declines_a_picture_with_transparency(real_ffmpeg):
    picture = real_ffmpeg("testsrc=size=160x120")

    # alpha 分区不是全白，即图片带透明度。
    assert media_helpers._wxgf_to_image_bytes(wxgf(picture, picture)) is None


def test_real_ffmpeg_declines_a_picture_above_the_pixel_cap(real_ffmpeg, monkeypatch):
    picture = real_ffmpeg("testsrc=size=160x120")
    monkeypatch.setattr(media_helpers, "_WXGF_FFMPEG_MAX_PIXELS", 160 * 120 - 1)

    assert media_helpers._wxgf_to_image_bytes(wxgf(picture)) is None


def test_real_ffmpeg_declines_an_animation(real_ffmpeg):
    animation = real_ffmpeg("testsrc=size=160x120:rate=5", frames=3)

    assert media_helpers._hevc_picture_count(animation) == 3
    assert media_helpers._wxgf_to_image_bytes(wxgf(animation)) is None
