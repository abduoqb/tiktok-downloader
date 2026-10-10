"""Tests de POST /api/import/preview et du plan_hash de POST /api/import.

Aucun réseau : run_import est mocké, cwd = tmp_path (jamais le vrai dossier downloads/).
"""
import json
import os
import sys
import threading
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import link_state  # noqa: E402
import orchestrator  # noqa: E402
import web_app  # noqa: E402

ID = "7100000000000000{:03d}"   # 19 chiffres


def vid(n):
    return ID.format(n)


def U(user, n, kind="video"):
    return f"https://www.tiktok.com/@{user}/{kind}/{vid(n)}"


def make_profile(root, name, history=(), failed=(), disk=(), states=None):
    """Crée downloads/<name> : metadata.json, fichiers vidéo et link_state.json."""
    folder = root / "downloads" / name
    folder.mkdir(parents=True, exist_ok=True)
    meta = {vid(n): {"url": "u", "type": "video", "success": True} for n in history}
    meta.update({vid(n): {"url": "u", "type": "video", "success": False} for n in failed})
    (folder / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    for n in disk:
        (folder / f"20240101_{name}_{vid(n)}.mp4").write_bytes(b"x" * 10)
    if states:
        state = link_state.LinkState(str(folder))
        for n, kind in states.items():
            if kind == "ignored":
                state.ignore(vid(n), "supprimée par l'utilisateur")
            elif kind == "unavailable":
                state.mark_unavailable(vid(n), "vidéo supprimée")
            elif kind == "retry_waiting":
                state.record_failure(vid(n), "transient", "reseau")
            elif kind == "retry_due":
                state.record_failure(vid(n), "transient", "reseau",
                                     now=datetime.now() - timedelta(days=1))
        state.save()
    return folder


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for store in (web_app.active_tasks, web_app.active_threads, web_app.task_states):
        store.clear()
    monkeypatch.setattr(web_app.ytdlp_options, "default_cookies_file", lambda: "/fake/c.txt")
    monkeypatch.setattr(web_app, "emit_log", lambda *a, **k: None)
    yield web_app.app.test_client()
    for store in (web_app.active_tasks, web_app.active_threads, web_app.task_states):
        store.clear()


@pytest.fixture
def runs(monkeypatch):
    calls, done = [], threading.Event()

    def fake(username, items, **kwargs):
        calls.append((username, items, kwargs))
        done.set()
        return {"videos": 0, "slideshows": 0, "failed": 0, "unknown": 0, "skipped": 0,
                "total_extracted": 0, "size_mb": 0.0, "duration_s": 0.0, "stopped": False,
                "results": [], "downloaded": 0, "processed": 0}

    monkeypatch.setattr(orchestrator, "run_import", fake)
    calls_obj = type("R", (), {})()
    calls_obj.calls, calls_obj.done = calls, done
    return calls_obj


def wait_threads():
    for _ in range(100):
        if not web_app.active_threads:
            return
        next(iter(web_app.active_threads.values())).join(0.05)


def mixed_text():
    """Jeu mixte pour @bob : 1-2 téléchargées, 3 sur disque, 4 ignorée, 5 indisponible,
    6 retry échu, 7 retry en attente, 8-9 nouvelles, 2 en double, 1 lien court, 1 ligne illisible."""
    lines = [U("bob", n) for n in range(1, 10)] + [U("bob", 2), "vm.tiktok.com/abc", "bonjour"]
    return "\n".join(lines)


def mixed_profile(root):
    return make_profile(root, "bob", history=(1, 2), disk=(3,),
                        states={4: "ignored", 5: "unavailable", 6: "retry_due",
                                7: "retry_waiting"})


# ---------------------------------------------------------------- validations

def test_preview_400s(client, runs):
    for body in ({}, {"text": ""}, {"text": "  \n"}, {"text": 5}):
        assert client.post("/api/import/preview", json=body).status_code == 400
    assert client.post("/api/import/preview", data="pas du json").status_code == 400
    resp = client.post("/api/import/preview", json={"text": "bonjour\nvm.tiktok.com/x"})
    assert resp.status_code == 400 and resp.get_json()["invalid"] == ["bonjour"]
    assert client.post("/api/import/preview", json={"text": U("a", 1), "mode": "x"}).status_code == 400
    assert client.post("/api/import/preview",
                       json={"text": U("a", 1), "destination": "../x"}).status_code == 400


def test_preview_max_links(client):
    text = "\n".join(U("a", 1) .replace(vid(1), str(1000000000000000000 + i)) for i in range(5001))
    resp = client.post("/api/import/preview", json={"text": text})
    assert resp.status_code == 400 and "5000" in resp.get_json()["error"]
    text = "\n".join(f"https://www.tiktok.com/@a/video/{1000000000000000000 + i}"
                     for i in range(5000))
    resp = client.post("/api/import/preview", json={"text": text})
    body = resp.get_json()
    assert resp.status_code == 200 and body["totals"]["valid"] == 5000
    assert body["limits"] == {"max_links": 5000}
    assert all(len(v) <= 20 for v in body["samples"].values())


# ---------------------------------------------------------------- catégories

def test_preview_exact_categories_on_mixed_set(client, tmp_path):
    mixed_profile(tmp_path)
    resp = client.post("/api/import/preview", json={"text": mixed_text()})
    body = resp.get_json()
    assert resp.status_code == 200 and body["status"] == "ok"
    assert body["mode"] == "single" and body["destination"] == "bob" and body["exists"] is True
    assert body["pseudos"] == {"bob": 9}
    assert body["totals"] == {
        "valid": 9, "to_download": 3, "downloaded": 2, "adopt": 1, "ignored": 1,
        "unavailable": 1, "retry_due": 1, "retry_waiting": 1, "new": 2, "duplicates": 1,
        "invalid": 0, "ignored_short_links": 1, "invalid_count": 1}
    assert body["invalid"] == ["bonjour"]
    assert body["estimate_s"] > 0 and body["busy"] == []
    assert any("court" in w for w in body["warnings"])
    assert body["samples"]["new"] == [[vid(8), U("bob", 8)], [vid(9), U("bob", 9)]]
    assert [p[0] for p in body["samples"]["retry_due"]] == [vid(6)]
    assert "folders" not in body


def test_preview_force_update_retries_unavailable(client, tmp_path):
    mixed_profile(tmp_path)
    body = client.post("/api/import/preview",
                       json={"text": mixed_text(), "force_update": True}).get_json()
    assert body["totals"]["unavailable"] == 0 and body["totals"]["to_download"] == 5
    assert body["totals"]["retry_due"] == 3 and body["totals"]["retry_waiting"] == 0


def test_preview_legacy_failed_history_is_retried(client, tmp_path):
    make_profile(tmp_path, "bob", history=(1,), failed=(2,))
    text = U("bob", 1) + "\n" + U("bob", 2)
    totals = client.post("/api/import/preview", json={"text": text}).get_json()["totals"]
    assert totals["downloaded"] == 1 and totals["retry_due"] == 1


def test_preview_estimate_uses_normalized_sleeps(client):
    text = U("bob", 1) + "\n" + U("bob", 2)
    body = client.post("/api/import/preview",
                       json={"text": text, "min_sleep": 10, "max_sleep": 2}).get_json()
    assert body["estimate_s"] == 1 * 6 + 2 * 6.0   # (n-1)*moy(2,10) + n*6
    assert body["estimate_s"] == 18


# ---------------------------------------------------------------- lecture seule

def test_preview_is_read_only(client, tmp_path, monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("effet de bord interdit dans l'aperçu")

    monkeypatch.setattr(web_app, "set_task_state", forbidden)
    monkeypatch.setattr(os, "makedirs", forbidden)
    web_app.active_threads.clear()
    resp = client.post("/api/import/preview", json={"text": U("ghost", 1)})
    assert resp.status_code == 200
    assert resp.get_json()["exists"] is False and resp.get_json()["destination"] == "ghost"
    assert not (tmp_path / "downloads").exists()
    assert web_app.task_states == {} and web_app.active_threads == {}


def test_preview_does_not_modify_existing_files(client, tmp_path):
    folder = mixed_profile(tmp_path)
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in folder.iterdir()}
    client.post("/api/import/preview", json={"text": mixed_text()})
    after = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in folder.iterdir()}
    assert before == after


def test_preview_hash_stable_and_sensitive(client, tmp_path):
    mixed_profile(tmp_path)
    one = client.post("/api/import/preview", json={"text": mixed_text()}).get_json()
    two = client.post("/api/import/preview", json={"text": mixed_text()}).get_json()
    assert one["plan_hash"] == two["plan_hash"] and len(one["plan_hash"]) == 40
    other = client.post("/api/import/preview", json={"text": mixed_text() + "\n" + U("bob", 50)})
    assert other.get_json()["plan_hash"] != one["plan_hash"]
    forced = client.post("/api/import/preview", json={"text": mixed_text(), "force_update": True})
    assert forced.get_json()["plan_hash"] != one["plan_hash"]


def test_preview_samples_capped_at_20(client):
    text = "\n".join(U("bob", n) for n in range(60))
    body = client.post("/api/import/preview", json={"text": text}).get_json()
    assert body["totals"]["new"] == 60 and len(body["samples"]["new"]) == 20


def test_preview_busy_folder_reported(client):
    release = threading.Event()
    thread = threading.Thread(target=release.wait, daemon=True)
    thread.start()
    web_app.active_threads["bob"] = thread
    try:
        body = client.post("/api/import/preview", json={"text": U("bob", 1)}).get_json()
        assert body["busy"] == ["bob"] and any("@bob" in w for w in body["warnings"])
    finally:
        release.set()
        thread.join(2)


# ---------------------------------------------------------------- destination

def test_preview_needs_destination_with_several_pseudos(client, tmp_path):
    text = "\n".join([U("alice", 1), U("bob", 2), U("bob", 3), U("alice", 4), U("bob", 5)])
    body = client.post("/api/import/preview", json={"text": text}).get_json()
    assert body == {"status": "needs_destination", "pseudos": {"alice": 2, "bob": 3},
                    "suggested": "bob"}
    assert not (tmp_path / "downloads").exists()


def test_preview_with_destination_and_case_resolution(client, tmp_path):
    make_profile(tmp_path, "Carol", history=(1,))
    text = U("alice", 1) + "\n" + U("bob", 2)
    body = client.post("/api/import/preview",
                       json={"text": text, "destination": "@carol"}).get_json()
    assert body["destination"] == "Carol" and body["exists"] is True
    assert body["totals"]["downloaded"] == 1 and body["totals"]["new"] == 1
    assert body["pseudos"] == {"alice": 1, "bob": 1}


def test_preview_by_author_has_folders(client, tmp_path):
    make_profile(tmp_path, "alice", history=(1,))
    text = "\n".join([U("alice", 1), U("alice", 2), U("bob", 3)])
    body = client.post("/api/import/preview", json={"text": text, "mode": "by_author"}).get_json()
    assert body["status"] == "ok" and body["mode"] == "by_author" and body["destination"] is None
    assert [(f["name"], f["exists"], f["totals"]["to_download"], f["busy"]) for f in body["folders"]] \
        == [("alice", True, 1, False), ("bob", False, 1, False)]
    assert body["totals"]["to_download"] == 2 and body["totals"]["downloaded"] == 1


# ---------------------------------------------------------------- /api/import

def test_import_response_has_totals_and_hash(client, runs, tmp_path):
    mixed_profile(tmp_path)
    preview = client.post("/api/import/preview", json={"text": mixed_text()}).get_json()
    resp = client.post("/api/import", json={"text": mixed_text(), "mode": "single",
                                            "destination": "bob",
                                            "plan_hash": preview["plan_hash"]})
    body = resp.get_json()
    assert resp.status_code == 200 and body["status"] == "started"
    assert body["plan_hash"] == preview["plan_hash"] and body["totals"] == preview["totals"]
    assert body["counts"] == {"bob": 9} and body["task_id"] == "bob"
    wait_threads()
    assert runs.calls[0][0] == "bob" and len(runs.calls[0][1]) == 9


def test_import_plan_changed_is_409_and_launches_nothing(client, runs, tmp_path):
    folder = mixed_profile(tmp_path)
    preview = client.post("/api/import/preview", json={"text": mixed_text()}).get_json()
    # l'état du disque change entre l'analyse et l'import
    (folder / f"20240101_bob_{vid(8)}.mp4").write_bytes(b"x")
    resp = client.post("/api/import", json={"text": mixed_text(), "destination": "bob",
                                            "mode": "single", "plan_hash": preview["plan_hash"]})
    assert resp.status_code == 409
    assert resp.get_json() == {
        "error": "plan_changed",
        "message": "Les données ont changé depuis l'analyse : relancez l'analyse."}
    assert runs.calls == [] and not web_app.active_threads and web_app.task_states == {}


def test_import_without_hash_still_works(client, runs):
    resp = client.post("/api/import", json={"text": U("bob", 1)})
    assert resp.status_code == 200 and "plan_hash" in resp.get_json()
    wait_threads()


def test_import_single_mode_puts_everything_in_one_folder_in_global_order(client, runs):
    text = "\n".join([U("alice", 1), U("bob", 2), U("alice", 3)])
    resp = client.post("/api/import", json={"text": text, "mode": "single", "destination": "zed"})
    assert resp.get_json()["counts"] == {"zed": 3}
    wait_threads()
    assert [i["id"] for i in runs.calls[0][1]] == [vid(1), vid(2), vid(3)]


def test_import_by_author_mode_groups(client, runs):
    text = "\n".join([U("alice", 1), U("bob", 2), U("alice", 3)])
    resp = client.post("/api/import", json={"text": text, "mode": "by_author"})
    assert resp.get_json()["counts"] == {"alice": 2, "bob": 1}
    wait_threads()
    assert [c[0] for c in runs.calls] == ["alice", "bob"]


def test_import_destination_required_400(client, runs):
    text = "\n".join([U("alice", 1), U("bob", 2), U("bob", 3)])
    resp = client.post("/api/import", json={"text": text, "mode": "single"})
    body = resp.get_json()
    assert resp.status_code == 400 and body["error"] == "destination_required"
    assert body["pseudos"] == {"alice": 1, "bob": 2} and body["suggested"] == "bob"
    assert runs.calls == [] and not web_app.active_threads


def test_import_single_mode_one_pseudo_defaults_destination(client, runs):
    resp = client.post("/api/import", json={"text": U("bob", 1), "mode": "single"})
    assert resp.status_code == 200 and resp.get_json()["counts"] == {"bob": 1}
    wait_threads()


def test_import_busy_is_still_409_before_hash_check(client, runs):
    release = threading.Event()
    thread = threading.Thread(target=release.wait, daemon=True)
    thread.start()
    web_app.active_threads["bob"] = thread
    try:
        resp = client.post("/api/import", json={"text": U("bob", 1), "plan_hash": "zzz"})
        assert resp.status_code == 409 and "bob" in resp.get_json()["error"]
    finally:
        release.set()
        thread.join(2)
