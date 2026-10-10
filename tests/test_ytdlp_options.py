import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ytdlp_options as yo


def test_resolve_cookies_precedence():
    assert yo.resolve_cookies("f.txt", "chrome") == ("f.txt", None)
    assert yo.resolve_cookies(None, "chrome") == (None, "chrome")
    assert yo.resolve_cookies() == (None, None)


def test_list_opts():
    assert yo.build_ydl_opts("list") == {
        'extract_flat': True, 'quiet': True, 'ignoreerrors': True}


def test_probe_opts_no_ignoreerrors():
    opts = yo.build_ydl_opts("probe")
    assert opts == {'quiet': True, 'no_warnings': True, 'extract_flat': False}
    assert 'ignoreerrors' not in opts


def test_download_opts_and_outtmpl_override():
    opts = yo.build_ydl_opts("download", outtmpl="d/%(upload_date)s_%(id)s.%(ext)s")
    assert opts['format'] == 'best[vcodec~="^(h264|avc)"]/bestvideo[vcodec~="^(h264|avc)"]+bestaudio/best'
    assert opts['merge_output_format'] == 'mp4'
    assert opts['quiet'] is False
    assert opts['ignoreerrors'] is True
    assert opts['restrictfilenames'] is True
    assert opts['writeallthumbnails'] is True
    assert opts['outtmpl'] == "d/%(upload_date)s_%(id)s.%(ext)s"


def test_invalid_purpose():
    with pytest.raises(ValueError):
        yo.build_ydl_opts("nope")


def test_cookies_in_opts():
    o = yo.build_ydl_opts("list", cookies_file="f.txt", cookies_browser="chrome")
    assert o['cookiefile'] == "f.txt" and 'cookiesfrombrowser' not in o
    o = yo.build_ydl_opts("list", cookies_browser="firefox")
    assert o['cookiesfrombrowser'] == ("firefox",) and 'cookiefile' not in o
    o = yo.build_ydl_opts("list")
    assert 'cookiefile' not in o and 'cookiesfrombrowser' not in o


def test_overrides_win():
    o = yo.build_ydl_opts("list", quiet=False, extra=1)
    assert o['quiet'] is False and o['extra'] == 1


def test_gallerydl_args():
    assert yo.build_gallerydl_cookie_args("f.txt", "chrome") == ['--cookies', 'f.txt']
    assert yo.build_gallerydl_cookie_args(None, "chrome") == ['--cookies-from-browser', 'chrome']
    assert yo.build_gallerydl_cookie_args() == []


def test_default_cookies_file(tmp_path, monkeypatch):
    monkeypatch.setattr(yo, "__file__", str(tmp_path / "ytdlp_options.py"))
    assert yo.default_cookies_file() is None
    (tmp_path / yo.DEFAULT_COOKIES_FILENAME).write_text("x")
    assert yo.default_cookies_file() == str(tmp_path / yo.DEFAULT_COOKIES_FILENAME)
