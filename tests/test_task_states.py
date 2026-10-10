"""Tests de l'état structuré des tâches (panneau Activité) : aucun réseau, orchestrateur mocké."""
import json
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import web_app  # noqa: E402
import orchestrator  # noqa: E402

FAKE_COOKIES = os.path.join(os.sep, "fake", "tiktok.com_cookies.txt")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for store in (web_app.active_tasks, web_app.active_threads, web_app.task_states):
        store.clear()
    monkeypatch.setattr(web_app, "load_history", lambda username: [])
    monkeypatch.setattr(web_app.ytdlp_options, "default_cookies_file", lambda: FAKE_COOKIES)
    monkeypatch.setattr(web_app, "emit_log", lambda *a, **k: None)
    yield web_app.app.test_client()
    for store in (web_app.active_tasks, web_app.active_threads, web_app.task_states):
        store.clear()


def _stats(**kw):
    base = {"videos": 0, "slideshows": 0, "failed": 0, "unknown": 0, "skipped": 0,
            "total_extracted": 0, "size_mb": 0.0, "duration_s": 0.0, "stopped": False,
            "results": [], "downloaded": 0, "processed": 0, "extraction_error": None}
    base.update(kw)
    return base


def _state(name):
    return web_app.get_task_states_by_name(name) if hasattr(web_app, "get_task_states_by_name") \
        else next(t for t in web_app.get_task_states() if t["username"] == name)


# ---------------------------------------------------------------- téléchargement

def test_download_transitions_listing_downloading_pausing_done(client, monkeypatch):
    snaps = []

    def snap(label):
        t = _state("bob")
        snaps.append((label, t["status"], t["phase"], t["listing_active"], t["pause_s"],
                      dict(t["current"]) if t["current"] else None, dict(t["counts"]),
                      t["total"]))

    def fake(username, platform="tiktok", progress=None, log=None, **kw):
        log("Analyse du profil @bob...", "info")
        snap("start")
        progress("item_start", {"index": 0, "total": None, "id": "11", "url": "u1"})
        snap("item_start")
        progress("step", {"id": "11", "step": "detection"})
        progress("step", {"id": "11", "step": "telechargement"})
        snap("step")
        progress("item_done", {"success": True, "type": "video", "total": None, "done": 1,
                               "total_size_mb": 2.5, "elapsed_s": 3.0})
        snap("item_done")
        progress("pause", {"seconds": 4.2})
        snap("pause")
        progress("pause_end", {})
        progress("item_start", {"index": 1, "total": None, "id": "12", "url": "u2"})
        progress("item_done", {"success": False, "type": "video", "total": None, "done": 2,
                               "total_size_mb": 2.5, "elapsed_s": 6.0})
        progress("extraction_done", {"total": 2})
        snap("extraction_done")
        stats = _stats(videos=1, failed=1, downloaded=1, processed=2, total_extracted=2,
                       size_mb=2.5, duration_s=6.0)
        progress("complete", {k: v for k, v in stats.items() if k != "results"})
        return stats

    monkeypatch.setattr(orchestrator, "run_download", fake)
    web_app.background_download_task("bob", "tiktok", 0, 0)

    by = {s[0]: s for s in snaps}
    assert by["start"][1:4] == ("running", "listing", True)
    assert by["item_start"][2] == "downloading" and by["item_start"][3] is True
    assert by["item_start"][5]["id"] == "11" and by["item_start"][5]["step"] == "detection"
    assert by["step"][5]["step"] == "telechargement"
    assert by["item_done"][6]["videos"] == 1 and by["item_done"][6]["done"] == 1
    assert by["item_done"][2] == "listing" and by["item_done"][5] is None  # le listing continue
    assert by["pause"][2] == "pausing" and by["pause"][4] == 4.2
    assert by["extraction_done"][3] is False and by["extraction_done"][7] == 2

    final = _state("bob")
    assert final["status"] == "done" and final["phase"] == "done"
    assert final["listing_active"] is False and final["pause_s"] is None
    assert final["finished_at"] is not None and final["current"] is None
    assert final["counts"]["videos"] == 1 and final["counts"]["failed"] == 1
    assert final["summary"]["downloaded"] == 1 and final["summary"]["failed"] == 1
    assert final["size_mb"] == 2.5
    assert web_app.active_tasks["bob"] == "done"


def test_elapsed_is_computed_at_read_time(client, monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(web_app, "_now", lambda: clock["t"])
    web_app.set_task_state("bob", "download")
    clock["t"] = 1042.5
    assert _state("bob")["elapsed_s"] == 42.5
    web_app.finish_task_state("bob", "done")
    clock["t"] = 5000.0
    assert _state("bob")["elapsed_s"] == 42.5  # figé à la fin


def test_exception_ends_in_error(client, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(orchestrator, "run_download", boom)
    web_app.background_download_task("bob", "tiktok", 0, 0)
    t = _state("bob")
    assert t["status"] == "error" and t["phase"] == "error" and t["finished_at"] is not None
    assert any("kaboom" in p["message"] for p in t["problems"])


def test_extraction_failure_is_error(client, monkeypatch):
    monkeypatch.setattr(orchestrator, "run_download", lambda *a, **k: _stats(
        extraction_error="listing impossible", total_extracted=0))
    web_app.background_download_task("bob", "tiktok", 0, 0)
    t = _state("bob")
    assert t["status"] == "error"
    assert t["summary"]["extraction_error"] == "listing impossible"


def test_stop_never_leaves_running(client, monkeypatch):
    def stopped(username, platform="tiktok", progress=None, should_stop=None, **kw):
        web_app.active_tasks["bob"] = "stopping"
        assert should_stop() is True
        assert _state("bob")["status"] == "stopping"   # visible pendant l'arrêt
        return _stats(stopped=True)

    monkeypatch.setattr(orchestrator, "run_download", stopped)
    web_app.background_download_task("bob", "tiktok", 0, 0)
    t = _state("bob")
    assert t["status"] == "done" and t["summary"]["stopped"] is True


def test_shutdown_before_start_is_done_not_running(client, monkeypatch):
    web_app.shutdown_event.set()
    try:
        web_app.background_download_task("bob", "tiktok", 0, 0)
    finally:
        web_app.shutdown_event.clear()
    t = _state("bob")
    assert t["status"] == "done" and t["summary"] == {"stopped": True}


def test_nothing_processed_is_done(client, monkeypatch):
    monkeypatch.setattr(orchestrator, "run_download", lambda *a, **k: _stats())
    web_app.background_download_task("bob", "tiktok", 0, 0)
    assert _state("bob")["status"] == "done"


def test_route_creates_state_immediately(client, monkeypatch):
    release = threading.Event()
    started = threading.Event()

    def slow(username, platform="tiktok", **kw):
        started.set()
        release.wait(5)
        return _stats()

    monkeypatch.setattr(orchestrator, "run_download", slow)
    assert client.post("/api/download", json={"username": "bob"}).status_code == 200
    assert started.wait(5)
    tasks = client.get("/api/tasks").get_json()["tasks"]
    assert [(t["username"], t["kind"], t["status"]) for t in tasks] == [("bob", "download", "running")]
    release.set()
    web_app.active_threads["bob"].join(5) if "bob" in web_app.active_threads else None
    for _ in range(100):
        if _state("bob")["status"] == "done":
            break
        threading.Event().wait(0.05)
    assert _state("bob")["status"] == "done"


# ---------------------------------------------------------------- import

def test_import_task_states(client, monkeypatch):
    seen = {}

    def fake(username, items, progress=None, log=None, **kw):
        if "start" in seen:
            return _stats(videos=1, downloaded=1, processed=1)
        seen["start"] = _state(username)
        progress("item_start", {"index": 0, "total": 2, "id": "1", "url": "u"})
        progress("pause", {"seconds": 3.0})
        seen["pause"] = _state(username)
        progress("pause_end", {})
        progress("item_done", {"success": True, "type": "slideshow", "total": 2, "done": 1,
                               "total_size_mb": 0.0, "elapsed_s": 1.0})
        seen["mid"] = _state(username)
        return _stats(slideshows=1, downloaded=1, processed=1, duration_s=2.0)

    monkeypatch.setattr(orchestrator, "run_import", fake)
    plan = [("alice", [{"id": "1", "url": "u"}, {"id": "2", "url": "v"}]),
            ("bob", [{"id": "3", "url": "w"}])]
    for name, _ in plan:
        web_app.active_tasks[name] = "queued"
    web_app.background_import_task(plan, 0, 0)

    assert seen["start"]["kind"] == "import" and seen["start"]["status"] == "running"
    assert seen["start"]["listing_active"] is False and seen["start"]["total"] == 2
    assert seen["pause"]["phase"] == "pausing" and seen["pause"]["total"] == 2
    assert seen["mid"]["counts"]["slideshows"] == 1 and seen["mid"]["counts"]["done"] == 1
    for name in ("alice", "bob"):
        t = _state(name)
        assert t["status"] == "done" and t["finished_at"] is not None
    assert _state("alice")["summary"]["slideshows"] == 1


def test_import_error_ends_in_error_and_continues(client, monkeypatch):
    def fake(username, items, **kw):
        if username == "alice":
            raise RuntimeError("boom")
        return _stats(videos=1, downloaded=1, processed=1)

    monkeypatch.setattr(orchestrator, "run_import", fake)
    plan = [("alice", [{"id": "1", "url": "u"}]), ("bob", [{"id": "2", "url": "v"}])]
    web_app.background_import_task(plan, 0, 0)
    assert _state("alice")["status"] == "error"
    assert any("boom" in p["message"] for p in _state("alice")["problems"])
    assert _state("bob")["status"] == "done"


def test_import_stop_marks_pending_users_done(client, monkeypatch):
    def fake(username, items, **kw):
        web_app.active_tasks[username] = "stopping"
        return _stats(stopped=True)

    monkeypatch.setattr(orchestrator, "run_import", fake)
    plan = [("alice", [{"id": "1", "url": "u"}]), ("bob", [{"id": "2", "url": "v"}])]
    web_app.background_import_task(plan, 0, 0)
    assert all(_state(n)["status"] == "done" for n in ("alice", "bob"))
    assert _state("bob")["summary"]["stopped"] is True


def test_import_route_creates_states(client, monkeypatch):
    release = threading.Event()
    monkeypatch.setattr(orchestrator, "run_import",
                        lambda username, items, **kw: (release.wait(5), _stats())[1])
    text = "https://www.tiktok.com/@alice/video/1\nhttps://www.tiktok.com/@bob/video/2"
    assert client.post("/api/import", json={"text": text}).status_code == 200
    tasks = {t["username"]: t for t in client.get("/api/tasks").get_json()["tasks"]}
    assert set(tasks) == {"alice", "bob"} and all(t["kind"] == "import" for t in tasks.values())
    assert tasks["alice"]["total"] == 1
    release.set()
    for _ in range(100):
        if all(_state(n)["status"] == "done" for n in ("alice", "bob")):
            break
        threading.Event().wait(0.05)
    assert all(_state(n)["status"] == "done" for n in ("alice", "bob"))


# ---------------------------------------------------------------- extraction

def test_extract_task_states(client, monkeypatch):
    monkeypatch.setattr(web_app, "get_user_dir", lambda u: os.path.join("downloads", u))
    monkeypatch.setattr(web_app, "append_link_to_file", lambda u, url: None)

    def gen(username, history, platform, limit=None, callback_log=None, cookies_file=None):
        callback_log("Using cookies from file: C:\\secret\\cookies.txt", "info")
        for i in range(3):
            yield {"url": f"https://www.tiktok.com/@{username}/video/{i}"}

    monkeypatch.setattr(web_app, "get_video_links", gen)
    web_app.background_extract_task("bob", "tiktok", None)
    t = _state("bob")
    assert t["kind"] == "extract" and t["status"] == "done"
    assert t["counts"]["listed"] == 3 and t["summary"]["listed"] == 3
    assert "secret" not in json.dumps(t)


def test_extract_exception_is_error(client, monkeypatch):
    monkeypatch.setattr(web_app, "get_user_dir", lambda u: os.path.join("downloads", u))

    def gen(*a, **k):
        raise RuntimeError("nope")
        yield  # pragma: no cover

    monkeypatch.setattr(web_app, "get_video_links", gen)
    web_app.background_extract_task("bob", "tiktok", None)
    assert _state("bob")["status"] == "error"


# ---------------------------------------------------------------- problèmes

def test_problems_limited_to_five_without_consecutive_duplicates(client):
    web_app.set_task_state("bob", "download")
    for i in range(8):
        web_app.record_problem("bob", f"erreur {i}", "error")
        web_app.record_problem("bob", f"erreur {i}", "error")  # doublon consécutif
    problems = _state("bob")["problems"]
    assert [p["message"] for p in problems] == [f"erreur {i}" for i in range(3, 8)]
    assert all(set(p) == {"time", "level", "message"} for p in problems)
    # un même message non consécutif est conservé
    web_app.record_problem("bob", "erreur 7", "error")
    web_app.record_problem("bob", "autre", "warning")
    web_app.record_problem("bob", "erreur 7", "error")
    assert [p["message"] for p in _state("bob")["problems"]][-3:] == ["erreur 7", "autre", "erreur 7"]


def test_problems_come_from_warning_and_error_logs(client, monkeypatch):
    def fake(username, platform="tiktok", log=None, **kw):
        log("info normale", "info")
        log("[1] Échec (video) : réseau", "error")
        log("[2] Échec (video) : réseau", "error")
        log("attention", "warning")
        return _stats()

    monkeypatch.setattr(orchestrator, "run_download", fake)
    web_app.background_download_task("bob", "tiktok", 0, 0)
    t = _state("bob")
    assert [p["level"] for p in t["problems"]] == ["error", "error", "warning"]
    assert t["last_message"] == "attention"


def test_messages_are_short_and_hide_paths(client):
    web_app.set_task_state("bob", "download")
    web_app.record_problem("bob", "x" * 1000)
    web_app.record_problem("bob", "échec avec C:\\Users\\moi\\cookies.txt dedans")
    problems = _state("bob")["problems"]
    assert len(problems[0]["message"]) <= web_app.MAX_MESSAGE_LEN
    assert "Users" not in problems[1]["message"] and "cookies.txt" not in problems[1]["message"]


# ---------------------------------------------------------------- API

def test_api_tasks_sorting_and_serialization(client, monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(web_app, "_now", lambda: clock["t"])
    web_app.set_task_state("old", "download")
    clock["t"] = 1010.0
    web_app.finish_task_state("old", "done")
    web_app.set_task_state("recent_err", "download")
    clock["t"] = 1020.0
    web_app.finish_task_state("recent_err", "error")
    web_app.set_task_state("run_a", "download")
    clock["t"] = 1030.0
    web_app.set_task_state("run_b", "import")
    clock["t"] = 1040.0

    resp = client.get("/api/tasks")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["server_time"] == 1040.0
    assert [t["username"] for t in body["tasks"]] == ["run_b", "run_a", "recent_err", "old"]
    first = body["tasks"][0]
    for key in ("username", "kind", "status", "phase", "listing_active", "started_at",
                "updated_at", "finished_at", "elapsed_s", "current", "pause_s", "counts",
                "total", "size_mb", "problems", "last_message", "summary"):
        assert key in first
    assert set(first["counts"]) == {"listed", "done", "videos", "slideshows", "failed",
                                    "unknown", "skipped"}
    assert first["elapsed_s"] == 10.0 and first["total"] is None


def test_api_tasks_empty(client):
    body = client.get("/api/tasks").get_json()
    assert body["tasks"] == [] and "server_time" in body


def test_api_tasks_has_no_sensitive_keys(client, monkeypatch):
    def fake(username, platform="tiktok", log=None, cookies_file=None, **kw):
        log(f"Using cookies from file: {cookies_file}", "info")
        log(f"Erreur avec {cookies_file}", "error")
        return _stats()

    monkeypatch.setattr(orchestrator, "run_download", fake)
    web_app.background_download_task("bob", "tiktok", 0, 0)
    raw = client.get("/api/tasks").get_data(as_text=True)
    assert "cookie" not in raw.lower().replace("cookies non", "")
    assert "fake" not in raw and "txt" not in raw
    for key in ("cookies_file", "cookies", "path"):
        assert f'"{key}"' not in raw


def test_clear_keeps_running_tasks_and_removes_finished(client):
    web_app.set_task_state("running", "download")
    web_app.set_task_state("stopping", "download")
    web_app.active_tasks["stopping"] = "stopping"
    web_app.set_task_state("fini", "download")
    web_app.finish_task_state("fini", "done")
    web_app.set_task_state("casse", "import")
    web_app.finish_task_state("casse", "error")
    resp = client.post("/api/tasks/clear")
    assert resp.status_code == 200 and resp.get_json()["success"] is True
    names = {t["username"]: t["status"] for t in client.get("/api/tasks").get_json()["tasks"]}
    # (le nettoyage historique vide active_tasks : « stopping » redevient « running »)
    assert set(names) == {"running", "stopping"}
    assert all(status in ("running", "stopping") for status in names.values())


def test_legacy_endpoints_still_work(client):
    web_app.active_tasks["bob"] = "running"
    assert client.get("/api/task/bob").get_json() == {"task_id": "bob", "status": "running"}
    assert client.get("/stream_logs").status_code == 200


def test_index_has_activity_panel(client):
    html = client.get("/").get_data(as_text=True)
    assert "Activité" in html and "Détails techniques" in html
    assert "/api/tasks" in html and "Journal en direct" not in html
    assert "Aucune tâche en cours" in html
