"""download_video(): le renommage ne doit pas ajouter le username deux fois (sans réseau)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main

VIDEO_ID = "7400000000000000002"
USERNAME = "someuser"


class FakeYDL:
    def __init__(self, opts=None):
        self.opts = opts or {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def download(self, urls):
        out_dir = os.path.dirname(self.opts["outtmpl"])
        with open(os.path.join(out_dir, f"20240101_{VIDEO_ID}.mp4"), "wb") as f:
            f.write(b"x" * 10)
        return 0


def _run(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "get_user_dir", lambda u: str(tmp_path))
    monkeypatch.setattr(main.yt_dlp, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(main, "ensure_h264", lambda p: None)
    monkeypatch.setattr(main, "organize_slideshow", lambda d, v: None)
    return main.download_video("http://x/video/" + VIDEO_ID, USERNAME, VIDEO_ID, retries=1)


def test_redownload_does_not_duplicate_username(tmp_path, monkeypatch):
    expected = f"20240101_{USERNAME}_{VIDEO_ID}.mp4"

    assert _run(tmp_path, monkeypatch) is True
    assert sorted(os.listdir(tmp_path)) == [expected]

    # Second download of the same id: the renamed file already exists, yt-dlp adds a fresh raw one
    assert _run(tmp_path, monkeypatch) is True
    names = os.listdir(tmp_path)
    assert expected in names
    assert not any(n.count(USERNAME) > 1 for n in names), names
