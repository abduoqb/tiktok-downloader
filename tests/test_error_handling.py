"""
Tests de gestion d'erreurs (yt-dlp / ffmpeg mockés, aucun accès réseau).

- is_slideshow() renvoie None (inconnu) sur erreur et ne met jamais ce résultat en cache
- download_video() renvoie False quand yt-dlp ne produit aucun fichier (ignoreerrors)
- ensure_h264() conserve l'original si ffmpeg échoue
"""
import os
import sys
import subprocess

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main
from metadata_manager import OptimizedMetadataManager


URL = "https://www.tiktok.com/@user/video/7400000000000000001"
VIDEO_ID = "7400000000000000001"
USERNAME = "user"


class FakeYDL:
    """Remplace yt_dlp.YoutubeDL. Comportement défini par les attributs de classe."""
    calls = 0
    extract_behavior = None   # callable(url) -> info, ou exception
    download_behavior = None  # callable(opts, urls) -> retcode

    def __init__(self, opts=None):
        self.opts = opts or {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        FakeYDL.calls += 1
        return FakeYDL.extract_behavior(url)

    def download(self, urls):
        FakeYDL.calls += 1
        return FakeYDL.download_behavior(self.opts, urls)


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Répertoire de travail isolé + yt-dlp mocké + manager partagé (cache observable)."""
    monkeypatch.chdir(tmp_path)
    FakeYDL.calls = 0
    FakeYDL.extract_behavior = None
    FakeYDL.download_behavior = None
    monkeypatch.setattr(main.yt_dlp, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(main.time, "sleep", lambda *_: None)

    user_dir = os.path.join("downloads", USERNAME)
    os.makedirs(user_dir, exist_ok=True)
    manager = OptimizedMetadataManager(USERNAME, user_dir)
    monkeypatch.setattr(main, "get_metadata_manager", lambda username: manager)
    return {"tmp": tmp_path, "user_dir": user_dir, "manager": manager}


# ---------------------------------------------------------------- is_slideshow

def _raise(exc):
    def _f(*_a, **_k):
        raise exc
    return _f


@pytest.mark.parametrize("exc", [
    Exception("ERROR: [TikTok] HTTP Error 403: Forbidden"),
    ValueError("Failed to parse JSON"),
    ConnectionError("getaddrinfo failed"),
])
def test_is_slideshow_unknown_on_error_not_cached(env, exc):
    FakeYDL.extract_behavior = _raise(exc)

    assert main.is_slideshow(URL, username=USERNAME) is None
    # Pas mis en cache
    assert env["manager"].get_slideshow_type_from_cache(URL) is None

    # Un second appel refait bien l'appel API (pas de cache)
    assert main.is_slideshow(URL, username=USERNAME) is None
    assert FakeYDL.calls == 2


def test_is_slideshow_unknown_when_no_info(env):
    FakeYDL.extract_behavior = lambda url: None
    assert main.is_slideshow(URL, username=USERNAME) is None
    assert env["manager"].get_slideshow_type_from_cache(URL) is None


def test_is_slideshow_known_results_are_cached(env):
    FakeYDL.extract_behavior = lambda url: {
        "formats": [{"vcodec": "none", "acodec": "mp3"}]
    }
    assert main.is_slideshow(URL, username=USERNAME) is True
    assert env["manager"].get_slideshow_type_from_cache(URL) is True
    # Le second appel vient du cache
    assert main.is_slideshow(URL, username=USERNAME) is True
    assert FakeYDL.calls == 1


# ---------------------------------------------------------------- download_video

def test_download_video_fails_when_ytdlp_returns_without_file(env, monkeypatch):
    # ignoreerrors=True : yt-dlp ne lève rien, renvoie un code d'erreur et aucun fichier
    FakeYDL.download_behavior = lambda opts, urls: 1
    h264_calls = []
    monkeypatch.setattr(main, "ensure_h264", lambda p: h264_calls.append(p) or p)

    assert main.download_video(URL, USERNAME, VIDEO_ID, retries=2) is False
    assert FakeYDL.calls == 2          # retry effectué
    assert h264_calls == []            # pas de post-traitement sans fichier


def test_download_video_fails_with_empty_or_partial_file(env, monkeypatch):
    user_dir = env["user_dir"]

    def fake_download(opts, urls):
        open(os.path.join(user_dir, f"20240101_{VIDEO_ID}.mp4"), "wb").close()        # vide
        with open(os.path.join(user_dir, f"20240101_{VIDEO_ID}.mp4.part"), "wb") as f:  # partiel
            f.write(b"x" * 10)
        return 1

    FakeYDL.download_behavior = fake_download
    monkeypatch.setattr(main, "ensure_h264", lambda p: p)

    assert main.download_video(URL, USERNAME, VIDEO_ID, retries=1) is False


def test_download_video_success_with_real_file(env, monkeypatch):
    user_dir = env["user_dir"]

    def fake_download(opts, urls):
        with open(os.path.join(user_dir, f"20240101_{VIDEO_ID}.mp4"), "wb") as f:
            f.write(b"data")
        return 0

    FakeYDL.download_behavior = fake_download
    h264_calls = []
    monkeypatch.setattr(main, "ensure_h264", lambda p: h264_calls.append(p) or p)

    assert main.download_video(URL, USERNAME, VIDEO_ID, retries=3) is True
    files = main.find_downloaded_videos(USERNAME, VIDEO_ID)
    assert [os.path.basename(f) for f in files] == [f"20240101_{USERNAME}_{VIDEO_ID}.mp4"]
    assert len(h264_calls) == 1        # une seule fois, hors boucle de retry


# ---------------------------------------------------------------- ensure_h264

class _Result:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _fake_run_factory(ffmpeg_returncode, ffmpeg_output=None):
    def fake_run(cmd, **kwargs):
        if cmd[0] == "ffprobe":
            return _Result(stdout="hevc\n")
        # ffmpeg : le fichier de sortie est le dernier argument
        out = cmd[-1]
        if ffmpeg_output is not None:
            with open(out, "wb") as f:
                f.write(ffmpeg_output)
        return _Result(returncode=ffmpeg_returncode, stderr="boom")
    return fake_run


@pytest.mark.parametrize("returncode,output", [
    (1, b"partial"),   # ffmpeg échoue après avoir écrit un fichier partiel
    (1, None),         # ffmpeg échoue sans rien écrire
    (0, b""),          # ffmpeg "réussit" mais produit un fichier vide
])
def test_ensure_h264_keeps_original_when_ffmpeg_fails(tmp_path, monkeypatch, returncode, output):
    original = tmp_path / f"20240101_{USERNAME}_{VIDEO_ID}.mp4"
    original.write_bytes(b"ORIGINAL-HEVC")
    monkeypatch.setattr(main.subprocess, "run", _fake_run_factory(returncode, output))

    assert main.ensure_h264(str(original)) == str(original)
    assert original.read_bytes() == b"ORIGINAL-HEVC"
    # Aucun fichier temporaire laissé
    assert sorted(p.name for p in tmp_path.iterdir()) == [original.name]


def test_ensure_h264_keeps_original_on_timeout(tmp_path, monkeypatch):
    original = tmp_path / f"{VIDEO_ID}.mp4"
    original.write_bytes(b"ORIGINAL")

    def fake_run(cmd, **kwargs):
        if cmd[0] == "ffprobe":
            return _Result(stdout="hevc")
        raise subprocess.TimeoutExpired(cmd, 300)

    monkeypatch.setattr(main.subprocess, "run", fake_run)
    main.ensure_h264(str(original))
    assert original.read_bytes() == b"ORIGINAL"
    assert [p.name for p in tmp_path.iterdir()] == [original.name]


def test_ensure_h264_replaces_on_success(tmp_path, monkeypatch):
    original = tmp_path / f"{VIDEO_ID}.mp4"
    original.write_bytes(b"ORIGINAL")
    monkeypatch.setattr(main.subprocess, "run", _fake_run_factory(0, b"H264-OUTPUT"))

    main.ensure_h264(str(original))
    assert original.read_bytes() == b"H264-OUTPUT"
    assert [p.name for p in tmp_path.iterdir()] == [original.name]
