"""Tests de orchestrator.run_import (mode import de liens ; main.* réseau mocké, tmp_path)."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main  # noqa: E402
import orchestrator  # noqa: E402

USER = "user"


def _item(i):
    return {"id": str(i), "url": f"https://www.tiktok.com/@{USER}/video/{i}"}


class Fake:
    def __init__(self):
        self.types = {}
        self.fail = set()
        self.calls = []
        self.listing_called = False
        self.on_download = None


@pytest.fixture
def fake(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    f = Fake()
    user_dir = os.path.join("downloads", USER)

    def get_video_links(*a, **k):
        f.listing_called = True
        raise AssertionError("le listing ne doit pas être appelé en mode import")
        yield  # pragma: no cover

    def is_slideshow(url, username=None, use_cache=True, cookies_browser=None, cookies_file=None):
        vid = url.rsplit("/", 1)[1]
        f.calls.append(("type", vid, cookies_file, cookies_browser))
        return f.types.get(vid, False)

    def download_video(url, username, video_id, retries=3, cookies_browser=None, cookies_file=None):
        f.calls.append(("video", video_id))
        if f.on_download:
            f.on_download(video_id)
        if video_id in f.fail:
            return False
        os.makedirs(user_dir, exist_ok=True)
        with open(os.path.join(user_dir, f"20240101_{username}_{video_id}.mp4"), "wb") as fh:
            fh.write(b"x" * 100)
        return True

    def download_slideshow(url, username, video_id, cookies_browser=None, cookies_file=None):
        f.calls.append(("slideshow", video_id))
        os.makedirs(user_dir, exist_ok=True)
        with open(os.path.join(user_dir, f"20240101_{username}_{video_id}_img=1.jpg"), "wb") as fh:
            fh.write(b"i")
        return True

    monkeypatch.setattr(main, "get_video_links", get_video_links)
    monkeypatch.setattr(main, "is_slideshow", is_slideshow)
    monkeypatch.setattr(main, "download_video", download_video)
    monkeypatch.setattr(main, "download_slideshow", download_slideshow)
    monkeypatch.setattr(orchestrator.random, "uniform", lambda a, b: 2.5)
    return f


def _history():
    path = os.path.join("downloads", USER, "metadata.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _run(items, **kw):
    sleeps = kw.pop("sleeps", [])
    kw.setdefault("log", lambda m, l="info": None)
    return orchestrator.run_import(USER, items, sleep=sleeps.append, **kw)


def test_downloads_all_without_listing_and_records_history(fake):
    stats = _run([_item(1), _item(2), _item(3)])
    assert not fake.listing_called
    assert stats["videos"] == 3 and stats["failed"] == 0 and stats["downloaded"] == 3
    assert set(_history()) >= {"1", "2", "3"}
    assert [c[1] for c in fake.calls if c[0] == "video"] == ["1", "2", "3"]


def test_pause_before_each_item_except_first(fake):
    sleeps = []
    _run([_item(1), _item(2), _item(3)], sleeps=sleeps)
    # 2 pauses de 2.5 s découpées en tranches (1, 1, 0.5)
    assert sum(sleeps) == pytest.approx(5.0)


def test_history_items_skipped(fake):
    main.save_to_history(USER, "2", url=_item(2)["url"], success=True)
    stats = _run([_item(1), _item(2), _item(3)])
    assert [c[1] for c in fake.calls if c[0] == "video"] == ["1", "3"]
    assert stats["skipped"] == 1 and stats["videos"] == 2


def test_failed_in_history_skipped_unless_force_update(fake):
    main.save_to_history(USER, "2", url=_item(2)["url"], item_type="video", success=False)
    _run([_item(1), _item(2)])
    assert [c[1] for c in fake.calls if c[0] == "video"] == ["1"]
    fake.calls.clear()
    stats = _run([_item(1), _item(2)], force_update=True)
    # l'échec est retenté, le succès (1) reste sauté
    assert [c[1] for c in fake.calls if c[0] == "video"] == ["2"]
    assert stats["videos"] == 1
    assert _history()["2"].get("success", True) is not False


def test_duplicates_and_invalid_entries_skipped(fake):
    items = [_item(1), _item(1), {"id": "", "url": "x"}, {"id": "9", "url": ""}]
    stats = _run(items)
    assert stats["videos"] == 1 and stats["skipped"] == 3


def test_unknown_type_not_downloaded_nor_historized(fake):
    fake.types["2"] = None
    stats = _run([_item(1), _item(2)])
    assert stats["unknown"] == 1 and stats["videos"] == 1
    assert "2" not in _history()
    assert ("video", "2") not in fake.calls


def test_slideshow_detected(fake):
    fake.types["1"] = True
    stats = _run([_item(1)])
    assert stats["slideshows"] == 1 and ("slideshow", "1") in fake.calls


def test_failure_is_historized_and_counted(fake):
    fake.fail.add("2")
    stats = _run([_item(1), _item(2), _item(3)])
    assert stats["failed"] == 1 and stats["videos"] == 2 and stats["processed"] == 3
    assert _history()["2"]["success"] is False


def test_should_stop_halts_run(fake):
    stop = {"flag": False}
    fake.on_download = lambda vid: stop.update(flag=True)
    stats = _run([_item(1), _item(2), _item(3)], should_stop=lambda: stop["flag"])
    assert stats["stopped"] is True
    assert [c[1] for c in fake.calls if c[0] == "video"] == ["1"]


def test_progress_total_is_known(fake):
    events = []
    _run([_item(1), _item(2), _item(3)], progress=lambda e, d: events.append((e, d)))
    starts = [d for e, d in events if e == "item_start"]
    dones = [d for e, d in events if e == "item_done"]
    assert [d["total"] for d in starts] == [3, 3, 3]
    assert [d["total"] for d in dones] == [3, 3, 3]
    assert events[-1][0] == "complete"


def test_progress_total_excludes_history(fake):
    main.save_to_history(USER, "1", url=_item(1)["url"], success=True)
    events = []
    _run([_item(1), _item(2)], progress=lambda e, d: events.append((e, d)))
    assert [d["total"] for e, d in events if e == "item_start"] == [1]


def test_cookies_forwarded(fake):
    _run([_item(1)], cookies_file="c.txt", cookies_browser="firefox")
    assert ("type", "1", "c.txt", "firefox") in fake.calls


def test_scan_state_never_touched(fake):
    # profil non scanné : un import complet ne le marque PAS comme scanné
    main.save_scan_state(USER, False)
    path = os.path.join("downloads", USER, main.SCAN_STATE_FILENAME)
    before = open(path, "rb").read()
    mtime = os.stat(path).st_mtime_ns
    _run([_item(1), _item(2)])
    assert open(path, "rb").read() == before and os.stat(path).st_mtime_ns == mtime
    assert main.load_scan_state(USER)["fully_scanned"] is False


def test_scan_state_not_created_and_scanned_profile_stays_scanned(fake):
    _run([_item(1)])
    assert not os.path.exists(os.path.join("downloads", USER, main.SCAN_STATE_FILENAME))

    main.save_scan_state(USER, True)
    fake.fail.add("5")
    stats = _run([_item(5), _item(6)], should_stop=lambda: False)
    assert main.load_scan_state(USER)["fully_scanned"] is True  # même avec un échec
    assert stats["scan_complete"] is True


def test_scan_state_unchanged_after_stop(fake):
    main.save_scan_state(USER, True)
    fake.on_download = lambda vid: None
    stats = _run([_item(1), _item(2)], should_stop=lambda: True)
    assert stats["stopped"] is True
    assert main.load_scan_state(USER)["fully_scanned"] is True


def test_no_links_file_written(fake):
    _run([_item(1)])
    assert not os.path.exists(os.path.join("downloads", USER, f"{USER}_videos.txt"))


def test_empty_list(fake):
    stats = _run([])
    assert stats["processed"] == 0 and stats["downloaded"] == 0
