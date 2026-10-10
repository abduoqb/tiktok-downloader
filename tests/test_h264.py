"""Tests de ensure_h264 avec un vrai ffmpeg (clips de 1 s, sans réseau).

Ignorés si ffmpeg/ffprobe sont absents.
"""
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402

pytestmark = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
    reason="ffmpeg/ffprobe requis",
)


def _make_clip(path, vcodec, acodec, pix_fmt=None):
    cmd = [
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=25",
        "-f", "lavfi", "-i", "sine=duration=1",
        "-c:v", vcodec, "-c:a", acodec,
    ]
    if pix_fmt:
        cmd += ["-pix_fmt", pix_fmt]
    subprocess.run(cmd + [str(path)], check=True, capture_output=True)


def _stream(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=codec_name,pix_fmt", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    ).stdout.strip()
    return out


def test_hevc_10bit_becomes_h264_yuv420p(tmp_path):
    clip = tmp_path / "hevc.mp4"
    try:
        _make_clip(clip, "libx265", "aac", "yuv420p10le")
    except subprocess.CalledProcessError:
        pytest.skip("encodeur libx265 indisponible")

    result = main.ensure_h264(str(clip))

    assert result == str(clip)
    assert _stream(clip) == "h264,yuv420p"


def test_h264_mp4_is_left_untouched(tmp_path):
    clip = tmp_path / "ok.mp4"
    _make_clip(clip, "libx264", "aac", "yuv420p")
    before = clip.read_bytes()

    assert main.ensure_h264(str(clip)) == str(clip)
    assert clip.read_bytes() == before


def test_webm_is_converted_to_mp4_and_original_removed(tmp_path):
    clip = tmp_path / "clip.webm"
    try:
        _make_clip(clip, "libvpx-vp9", "libopus")
    except subprocess.CalledProcessError:
        pytest.skip("encodeur vp9 indisponible")

    result = main.ensure_h264(str(clip))

    assert result == str(tmp_path / "clip.mp4")
    assert not clip.exists()
    assert _stream(result) == "h264,yuv420p"


def test_corrupt_file_is_kept(tmp_path):
    clip = tmp_path / "broken.mp4"
    clip.write_bytes(b"not a video")

    assert main.ensure_h264(str(clip)) == str(clip)
    assert clip.read_bytes() == b"not a video"
