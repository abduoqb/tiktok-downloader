"""Tests de POST /api/import (run_import mocké, cwd = tmp_path : jamais de downloads/ réel)."""
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import web_app  # noqa: E402
import orchestrator  # noqa: E402

FAKE_COOKIES = os.path.join(os.sep, "fake", "tiktok.com_cookies.txt")


def U(user, vid, kind="video"):
    return f"https://www.tiktok.com/@{user}/{kind}/{vid}"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    web_app.active_tasks.clear()
    web_app.active_threads.clear()
    monkeypatch.setattr(web_app.ytdlp_options, "default_cookies_file", lambda: FAKE_COOKIES)
    yield web_app.app.test_client()
    web_app.active_tasks.clear()
    web_app.active_threads.clear()


def _stats(**kw):
    base = {"videos": 0, "slideshows": 0, "failed": 0, "unknown": 0, "skipped": 0,
            "total_extracted": 0, "size_mb": 0.0, "duration_s": 0.0, "stopped": False,
            "results": [], "downloaded": 0, "processed": 0}
    base.update(kw)
    return base


@pytest.fixture
def runs(monkeypatch):
    """Remplace run_import ; `runs.calls` = (username, items, kwargs) ; `runs.done` = tout fini."""
    class R:
        calls = []
        expected = 1
        done = threading.Event()
        release = None

    r = R()
    r.calls = []
    r.done = threading.Event()

    def fake(username, items, **kwargs):
        if r.release is not None:
            r.release.wait(5)
        r.calls.append((username, items, kwargs))
        if len(r.calls) >= r.expected:
            r.done.set()
        return _stats()

    monkeypatch.setattr(orchestrator, "run_import", fake)
    return r


def _wait(r):
    assert r.done.wait(5)
    for _ in range(100):
        if not web_app.active_threads:
            return
        next(iter(web_app.active_threads.values())).join(0.05)


def test_no_text_is_400(client, runs):
    for body in ({}, {"text": ""}, {"text": "   \n"}, {"text": 5}):
        resp = client.post("/api/import", json=body)
        assert resp.status_code == 400
    assert client.post("/api/import", data="pas du json").status_code == 400
    assert runs.calls == []


def test_no_valid_link_is_400_with_report(client, runs):
    resp = client.post("/api/import", json={"text": "bonjour\nhttps://vm.tiktok.com/ZM1/"})
    body = resp.get_json()
    assert resp.status_code == 400
    assert "Aucun lien" in body["error"]
    assert body["ignored"] == 1 and body["invalid"] == ["bonjour"]
    assert not web_app.active_threads


def test_more_than_5000_links_is_400(client, runs):
    text = "\n".join(U("a", 1000 + i) for i in range(5001))
    resp = client.post("/api/import", json={"text": text})
    assert resp.status_code == 400 and "5000" in resp.get_json()["error"]
    assert runs.calls == []


def test_exactly_5000_links_accepted(client, runs):
    text = "\n".join(U("a", 1000 + i) for i in range(5000))
    resp = client.post("/api/import", json={"text": text})
    assert resp.status_code == 200 and resp.get_json()["counts"] == {"a": 5000}
    _wait(runs)


def test_single_user_started(client, runs):
    resp = client.post("/api/import", json={
        "text": U("bob", 1) + "\n" + U("bob", 2) + "\nvm.tiktok.com/x\nrubbish",
        "min_sleep": 1, "max_sleep": 3, "force_update": True})
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["status"] == "started" and body["task_id"] == "bob"
    assert body["counts"] == {"bob": 2} and body["ignored"] == 1 and body["invalid"] == ["rubbish"]
    assert "message" in body
    _wait(runs)
    username, items, kwargs = runs.calls[0]
    assert username == "bob" and [i["id"] for i in items] == ["1", "2"]
    assert (kwargs["min_sleep"], kwargs["max_sleep"]) == (1.0, 3.0)
    assert kwargs["force_update"] is True
    assert kwargs["cookies_file"] == FAKE_COOKIES
    assert callable(kwargs["should_stop"]) and callable(kwargs["log"])
    assert web_app.active_tasks["bob"] == "done"


def test_grouped_by_pseudo_sequentially(client, runs):
    runs.expected = 2
    text = "\n".join([U("alice", 1), U("bob", 2), U("alice", 3)])
    resp = client.post("/api/import", json={"text": text})
    assert resp.get_json()["counts"] == {"alice": 2, "bob": 1}
    _wait(runs)
    assert [(c[0], [i["id"] for i in c[1]]) for c in runs.calls] == [
        ("alice", ["1", "3"]), ("bob", ["2"])]
    assert web_app.active_tasks == {"alice": "done", "bob": "done"}


def test_forced_username_gets_all_links(client, runs):
    text = "\n".join([U("alice", 1), U("bob", 2)])
    resp = client.post("/api/import", json={"text": text, "username": "@carol"})
    assert resp.get_json()["counts"] == {"carol": 2}
    _wait(runs)
    assert len(runs.calls) == 1 and runs.calls[0][0] == "carol"


@pytest.mark.parametrize("bad", ["../x", "a/b", "..", "a\\b", "a b", 5, "x" * 80])
def test_forced_username_validated(client, runs, bad):
    resp = client.post("/api/import", json={"text": U("a", 1), "username": bad})
    assert resp.status_code == 400
    assert runs.calls == [] and not web_app.active_threads


@pytest.mark.parametrize("evil", [
    "https://www.tiktok.com/@../video/1",
    "https://www.tiktok.com/@../../x/video/1",
    "https://www.tiktok.com/@..\\x/video/1",
])
def test_path_traversal_in_urls_rejected(client, runs, evil):
    resp = client.post("/api/import", json={"text": evil})
    assert resp.status_code == 400
    assert runs.calls == [] and not web_app.active_threads


def test_traversal_mixed_with_valid_only_valid_user_runs(client, runs):
    resp = client.post("/api/import", json={
        "text": "https://www.tiktok.com/@../video/9\n" + U("ok", 1)})
    assert resp.get_json()["counts"] == {"ok": 1}
    _wait(runs)
    assert [c[0] for c in runs.calls] == ["ok"]
    assert all(".." not in c[0] for c in runs.calls)


def test_conflict_when_task_running(client, runs):
    release = threading.Event()
    running = threading.Thread(target=release.wait, daemon=True)
    running.start()
    web_app.active_threads["bob"] = running
    try:
        resp = client.post("/api/import", json={"text": U("bob", 1)})
        assert resp.status_code == 409 and "bob" in resp.get_json()["error"]
        # un seul pseudo occupé bloque tout l'import (aucun thread démarré)
        resp = client.post("/api/import", json={"text": U("alice", 1) + "\n" + U("bob", 2)})
        assert resp.status_code == 409
        assert runs.calls == [] and "alice" not in web_app.active_threads
    finally:
        release.set()
        running.join(2)


def test_conflict_applies_across_case(client, runs, tmp_path):
    (tmp_path / "downloads" / "Bob").mkdir(parents=True)
    release = threading.Event()
    running = threading.Thread(target=release.wait, daemon=True)
    running.start()
    web_app.active_threads["Bob"] = running
    try:
        assert client.post("/api/import", json={"text": U("bob", 1)}).status_code == 409
    finally:
        release.set()
        running.join(2)


def test_finished_thread_does_not_block(client, runs):
    dead = threading.Thread(target=lambda: None)
    dead.start()
    dead.join()
    web_app.active_threads["bob"] = dead
    web_app.active_tasks["bob"] = "done"
    resp = client.post("/api/import", json={"text": U("bob", 1)})
    assert resp.status_code == 200
    _wait(runs)


def test_existing_folder_case_reused(client, runs, tmp_path):
    (tmp_path / "downloads" / "Bob").mkdir(parents=True)
    resp = client.post("/api/import", json={"text": U("bob", 1)})
    assert resp.get_json()["counts"] == {"Bob": 1}
    _wait(runs)
    assert runs.calls[0][0] == "Bob"


def test_stop_flag_is_seen_by_should_stop(client, runs):
    runs.release = threading.Event()
    resp = client.post("/api/import", json={"text": U("bob", 1)})
    assert resp.status_code == 200
    web_app.active_tasks["bob"] = "stopping"
    runs.release.set()
    _wait(runs)
    # arrêt demandé avant le début : run_import n'est même pas appelé OU l'est avec should_stop vrai
    assert all(c[2]["should_stop"]() for c in runs.calls)


def test_run_error_does_not_leave_task_stuck(client, monkeypatch):
    done = threading.Event()

    def boom(username, items, **kwargs):
        done.set()
        raise RuntimeError("boom")

    monkeypatch.setattr(orchestrator, "run_import", boom)
    assert client.post("/api/import", json={"text": U("bob", 1)}).status_code == 200
    assert done.wait(5)
    for _ in range(100):
        if not web_app.active_threads:
            break
        next(iter(web_app.active_threads.values())).join(0.05)
    assert web_app.active_tasks["bob"] == "done" and not web_app.active_threads


def test_index_page_contains_import_section_and_command(client):
    html = client.get("/").get_data(as_text=True)
    assert "Importer une liste de liens" in html
    assert "tiktok_liens_" in html and 'id="importText"' in html
    assert client.get("/static/js/export_links.js").status_code == 200
