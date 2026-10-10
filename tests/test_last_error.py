"""main.last_error() / reset_last_error(), logger yt-dlp léger, known_ids, historique en lecture
seule et fusion des champs utilisateur (yt-dlp / gallery-dl mockés, aucun réseau)."""
import json
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main  # noqa: E402
from metadata_manager import OptimizedMetadataManager  # noqa: E402

VIDEO_ID = "7400000000000000009"
URL = f"https://www.tiktok.com/@user/video/{VIDEO_ID}"
USER = "user"


class FakeYDL:
    extract_behavior = None
    download_behavior = None

    def __init__(self, opts=None):
        self.opts = opts or {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        return FakeYDL.extract_behavior(self.opts, url)

    def download(self, urls):
        return FakeYDL.download_behavior(self.opts, urls)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    FakeYDL.extract_behavior = None
    FakeYDL.download_behavior = None
    monkeypatch.setattr(main.yt_dlp, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(main.time, "sleep", lambda *_: None)
    monkeypatch.setattr(main, "ensure_h264", lambda p: p)
    main.reset_last_error()
    yield tmp_path
    main.reset_last_error()


def _raise(exc):
    def f(*a, **k):
        raise exc
    return f


# ---------------------------------------------------------------- download_video

def test_download_video_error_from_ytdlp_logger(env):
    def dl(opts, urls):
        # ignoreerrors=True : l'erreur passe par le logger, aucun fichier
        opts["logger"].error(f"ERROR: [TikTok] {VIDEO_ID}: Video not available, status code 10204")
        return 1
    FakeYDL.download_behavior = dl
    assert main.download_video(URL, USER, VIDEO_ID, retries=2) is False
    assert "status code 10204" in main.last_error()


def test_download_video_fake_ignoring_logger_still_works(env):
    FakeYDL.download_behavior = lambda opts, urls: 1
    assert main.download_video(URL, USER, VIDEO_ID, retries=1) is False
    assert "no video file found" in main.last_error()


def test_download_video_success_resets_error(env):
    main._set_last_error("ancienne erreur")

    def dl(opts, urls):
        with open(os.path.join("downloads", USER, f"20240101_{VIDEO_ID}.mp4"), "wb") as fh:
            fh.write(b"data")
        return 0
    FakeYDL.download_behavior = dl
    assert main.download_video(URL, USER, VIDEO_ID, retries=1) is True
    assert main.last_error() is None


def test_console_logger_keeps_output_and_captures_errors(capsys):
    logger = main._YtdlpConsoleLogger()
    logger.debug("[debug] secret")
    logger.debug("[info] Downloading 1 format(s)")
    logger.debug("[download]  42.0% of 1.00MiB at 1.00MiB/s ETA 00:01")
    logger.warning("attention")
    logger.error("ERROR: boom")
    out = capsys.readouterr().out
    assert "[debug] secret" not in out
    assert "[info] Downloading" in out and "42.0%" in out
    assert "WARNING: attention" in out and "ERROR: boom" in out
    assert logger.errors == ["ERROR: boom"]


# ---------------------------------------------------------------- is_slideshow

def test_is_slideshow_exposes_probe_error(env):
    FakeYDL.extract_behavior = _raise(Exception("ERROR: [TikTok] 1: This video is private"))
    assert main.is_slideshow(URL) is None
    assert "This video is private" in main.last_error()

    FakeYDL.extract_behavior = lambda opts, url: None
    assert main.is_slideshow(URL) is None
    assert "no info returned" in main.last_error()

    FakeYDL.extract_behavior = lambda opts, url: {"formats": [{"vcodec": "h264", "acodec": "aac"}]}
    assert main.is_slideshow(URL) is False
    assert main.last_error() is None
    main._info_cache.clear()


def test_last_error_is_per_thread(env):
    main._set_last_error("thread principal")
    seen = []

    def worker():
        seen.append(main.last_error())
        main._set_last_error("worker")

    t = threading.Thread(target=worker)
    t.start()
    t.join()
    assert seen == [None]
    assert main.last_error() == "thread principal"
    main.reset_last_error()
    assert main.last_error() is None


# ---------------------------------------------------------------- download_slideshow

class _Result:
    def __init__(self, returncode, stderr=""):
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = ""


def test_download_slideshow_exposes_gallerydl_stderr(env, monkeypatch):
    FakeYDL.extract_behavior = lambda opts, url: {"upload_date": "20240101"}
    stderr = ("[tiktok][info] start\n"
              "[tiktok][error] HttpError: '404 Not Found' for 'https://www.tiktok.com/@u/photo/1'\n")
    monkeypatch.setattr(main.subprocess, "run", lambda cmd, **k: _Result(1, stderr))
    assert main.download_slideshow(URL, USER, VIDEO_ID) is False
    assert "404 Not Found" in main.last_error()


def test_download_slideshow_exposes_exception(env):
    FakeYDL.extract_behavior = _raise(RuntimeError("Video unavailable"))
    assert main.download_slideshow(URL, USER, VIDEO_ID) is False
    assert main.last_error() == "Video unavailable"


# ---------------------------------------------------------------- known_ids

def _entries(ids):
    return iter([{"id": i, "url": f"https://x/{i}"} for i in ids])


def test_filter_entries_default_uses_history():
    out = list(main._filter_entries(_entries(["1", "2", "3"]), {"2"}, None, False,
                                    lambda *a: None))
    assert [e["id"] for e in out] == ["1", "3"]


def test_filter_entries_known_ids_replace_history_for_skip_and_stop():
    known = {str(i) for i in range(10)}
    ids = [str(i) for i in range(10)] + ["new"]
    report = {}
    out = list(main._filter_entries(_entries(ids), set(), None, False, lambda *a: None,
                                    scan_report=report, known_ids=known))
    assert out == [] and report["ended_by"] == "incremental"
    # history ignoré quand known_ids est fourni
    out = list(main._filter_entries(_entries(["1", "2"]), {"1", "2"}, None, False,
                                    lambda *a: None, known_ids=set()))
    assert [e["id"] for e in out] == ["1", "2"]


def test_get_video_links_accepts_known_ids(env, monkeypatch):
    class ListYDL(FakeYDL):
        def extract_info(self, url, download=False):
            return {"entries": [{"id": "1", "url": "u1"}, {"id": "2", "url": "u2"}]}
    monkeypatch.setattr(main.yt_dlp, "YoutubeDL", ListYDL)
    out = list(main.get_video_links(USER, {"1"}, known_ids={"2"}))
    assert [e["id"] for e in out] == ["1"]


# ---------------------------------------------------------------- historique

def test_load_history_split_read_only(env):
    assert main.load_history_split(USER) == (set(), set())
    assert not os.path.exists(os.path.join("downloads", USER))

    main.save_to_history(USER, "1", url="u1", success=True)
    main.save_to_history(USER, "2", url="u2", success=False)
    path = os.path.join("downloads", USER, "metadata.json")
    data = json.load(open(path, encoding="utf-8"))
    data["3"] = {"url": "u3"}  # ancienne entrée sans clé success = réussie
    json.dump(data, open(path, "w", encoding="utf-8"))
    assert main.load_history_split(USER) == ({"1", "3"}, {"2"})


def test_add_preserve_user_fields(tmp_path):
    manager = OptimizedMetadataManager(USER, str(tmp_path))
    manager.add("1", "u", "video", success=False, tags=["chat"], favorite=True, notes="n")
    manager.add("1", "u", "video", file_size=5, success=True, preserve_user_fields=True)
    entry = OptimizedMetadataManager(USER, str(tmp_path)).load()["1"]
    assert entry["success"] is True and entry["size"] == 5
    assert entry["tags"] == ["chat"] and entry["favorite"] is True and entry["notes"] == "n"
    # Comportement par défaut inchangé : l'entrée est entièrement remplacée
    manager.add("1", "u", "video", success=True)
    entry = OptimizedMetadataManager(USER, str(tmp_path)).load()["1"]
    assert entry["tags"] == [] and entry["favorite"] is False and entry["notes"] == ""
