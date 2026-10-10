"""Tests de POST /api/download (adaptateur web autour de orchestrator.run_download)."""
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import web_app  # noqa: E402
import orchestrator  # noqa: E402


FAKE_COOKIES = os.path.join(os.sep, "fake", "tiktok.com_cookies.txt")


@pytest.fixture
def client(monkeypatch):
    web_app.active_tasks.clear()
    web_app.active_threads.clear()
    monkeypatch.setattr(web_app, "load_history", lambda username: [])
    monkeypatch.setattr(web_app.ytdlp_options, "default_cookies_file", lambda: FAKE_COOKIES)
    yield web_app.app.test_client()
    web_app.active_tasks.clear()
    web_app.active_threads.clear()


def _fake_stats():
    return {"videos": 0, "slideshows": 0, "failed": 0, "unknown": 0, "skipped": 0,
            "total_extracted": 0, "size_mb": 0.0, "duration_s": 0.0, "stopped": False,
            "results": [], "downloaded": 0, "processed": 0}


def _patch_run_download(monkeypatch):
    calls = []
    done = threading.Event()

    def fake(username, platform="tiktok", **kwargs):
        calls.append((username, platform, kwargs))
        done.set()
        return _fake_stats()

    monkeypatch.setattr(orchestrator, "run_download", fake)
    return calls, done


def _wait_cleanup(done):
    assert done.wait(5)
    thread = None
    for _ in range(100):
        if not web_app.active_threads:
            return
        thread = next(iter(web_app.active_threads.values()), None)
        if thread is not None:
            thread.join(0.05)


def test_limit_is_forwarded(client, monkeypatch):
    calls, done = _patch_run_download(monkeypatch)
    resp = client.post("/api/download", json={"username": "bob", "limit": 7})
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "started"
    _wait_cleanup(done)
    assert calls[0][0] == "bob"
    assert calls[0][2]["limit"] == 7


def test_missing_limit_is_none(client, monkeypatch):
    calls, done = _patch_run_download(monkeypatch)
    resp = client.post("/api/download", json={"username": "bob"})
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "started", "task_id": "bob",
                               "message": "Download started for @bob"}
    _wait_cleanup(done)
    assert calls[0][2]["limit"] is None


@pytest.mark.parametrize("bad", [-3, "abc", "5", 2.5, True, [1]])
def test_invalid_limit_rejected(client, monkeypatch, bad):
    calls, _ = _patch_run_download(monkeypatch)
    resp = client.post("/api/download", json={"username": "bob", "limit": bad})
    assert resp.status_code == 400
    assert calls == []
    assert not web_app.active_threads


def test_limit_zero_means_unlimited(client, monkeypatch):
    calls, done = _patch_run_download(monkeypatch)
    resp = client.post("/api/download", json={"username": "bob", "limit": 0})
    assert resp.status_code == 200
    _wait_cleanup(done)
    assert calls[0][2]["limit"] is None


@pytest.mark.parametrize("lo, hi, expected", [
    (None, None, (2.0, 6.0)),
    ("", "", (2.0, 6.0)),
    (-1, -2, (2.0, 6.0)),
    ("abc", [1], (2.0, 6.0)),
    ("nan", "inf", (2.0, 6.0)),
    ("3", "8", (3.0, 8.0)),
    (20, 10, (10.0, 20.0)),
    (0, 0, (0.0, 0.0)),
])
def test_sleep_values_are_validated(client, monkeypatch, lo, hi, expected):
    calls, done = _patch_run_download(monkeypatch)
    resp = client.post("/api/download", json={"username": "bob", "min_sleep": lo, "max_sleep": hi})
    assert resp.status_code == 200
    _wait_cleanup(done)
    kwargs = calls[0][2]
    assert (kwargs["min_sleep"], kwargs["max_sleep"]) == expected


def test_conflict_when_task_running(client, monkeypatch):
    calls, _ = _patch_run_download(monkeypatch)
    release = threading.Event()
    running = threading.Thread(target=release.wait, daemon=True)
    running.start()
    web_app.active_threads["bob"] = running
    try:
        resp = client.post("/api/download", json={"username": "bob", "limit": 3})
        assert resp.status_code == 409
        assert calls == []
    finally:
        release.set()
        running.join(2)


def test_default_cookies_are_passed(client, monkeypatch):
    calls, done = _patch_run_download(monkeypatch)
    resp = client.post("/api/download", json={
        "username": "bob", "min_sleep": 1, "max_sleep": 2, "force_update": True})
    assert resp.status_code == 200
    _wait_cleanup(done)
    kwargs = calls[0][2]
    assert kwargs["cookies_file"] == FAKE_COOKIES
    assert kwargs["min_sleep"] == 1
    assert kwargs["max_sleep"] == 2
    assert kwargs["force_update"] is True
    assert callable(kwargs["should_stop"])
