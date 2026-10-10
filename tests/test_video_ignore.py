"""Suppression d'une vidéo (marquage « ignorée ») et routes Restaurer. Aucun réseau, cwd = tmp_path."""
import json
import os
import sys
from urllib.parse import quote

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import link_state  # noqa: E402
import web_app  # noqa: E402

LONG = "7123456789012345678"       # 19 chiffres
SHORT = "812345678901234"         # 15 chiffres


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(web_app, "emit_log", lambda *a, **k: None)
    return web_app.app.test_client()


def make(tmp_path, user, files=(), history=()):
    folder = tmp_path / "downloads" / user
    folder.mkdir(parents=True, exist_ok=True)
    for name in files:
        (folder / name).write_bytes(b"data")
    meta = {i: {"url": "u", "type": "video", "success": True} for i in history}
    (folder / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    return folder


def history_ids(folder):
    return set(json.loads((folder / "metadata.json").read_text(encoding="utf-8")))


def states(folder):
    return link_state.LinkState.load(str(folder)).items()


def delete(client, user, name):
    return client.delete(f"/api/video/{quote(user)}/{quote(name)}/delete")


@pytest.mark.parametrize("name", [
    f"20240101_bob_{LONG}.mp4", f"20240101_bob_{LONG}.webm", f"20240101_bob_{LONG}.mkv",
    f"20240101_bob_{LONG}.mov", f"NA_bob_{LONG}.mp4", f"bob_{LONG}.mp4",
    f"20240101_bob_{SHORT}.mp4", f"20240101_bob_{LONG}_img=1.jpg",
])
def test_delete_extracts_id_for_all_extensions(client, tmp_path, name):
    folder = make(tmp_path, "bob", [name])
    ident = SHORT if SHORT in name else LONG
    resp = delete(client, "bob", name)
    body = resp.get_json()
    assert resp.status_code == 200 and body["success"] is True and body["video_id"] == ident
    assert not (folder / name).exists()
    assert states(folder)[ident]["status"] == "ignored"
    assert states(folder)[ident]["reason"] == "supprimée par l'utilisateur"
    assert "warning" not in body


@pytest.mark.parametrize("user", ["my_user", "dot.user", "a_b.c-d"])
def test_delete_with_underscore_and_dot_pseudos(client, tmp_path, user):
    name = f"20240101_{user}_{LONG}.mp4"
    folder = make(tmp_path, user, [name], history=[LONG, "999999999999999999"])
    resp = delete(client, user, name)
    assert resp.get_json()["video_id"] == LONG
    assert history_ids(folder) == {"999999999999999999"}      # retiré de l'historique
    assert states(folder)[LONG]["status"] == "ignored"        # et marqué ignoré
    assert resp.get_json()["removed_from_history"] is True


def test_delete_marks_ignored_even_if_not_in_history(client, tmp_path):
    name = f"20240101_bob_{LONG}.mp4"
    folder = make(tmp_path, "bob", [name], history=["111111111111111111"])
    resp = delete(client, "bob", name)
    assert resp.status_code == 200 and resp.get_json()["removed_from_history"] is False
    assert history_ids(folder) == {"111111111111111111"}
    assert states(folder)[LONG]["status"] == "ignored"


def test_delete_without_extractable_id_warns_but_deletes(client, tmp_path):
    folder = make(tmp_path, "bob", ["video_sans_id.mp4"], history=[LONG])
    resp = delete(client, "bob", "video_sans_id.mp4")
    body = resp.get_json()
    assert resp.status_code == 200 and body["success"] is True and body["video_id"] is None
    assert "Identifiant" in body["warning"]
    assert not (folder / "video_sans_id.mp4").exists()
    assert history_ids(folder) == {LONG} and states(folder) == {}


def test_delete_missing_file_is_404(client, tmp_path):
    make(tmp_path, "bob")
    assert delete(client, "bob", f"bob_{LONG}.mp4").status_code == 404


@pytest.mark.parametrize("filename", ["..%2F..%2Fsecret.mp4", "..%5Csecret.mp4", "a%2Fb.mp4"])
def test_delete_path_traversal_refused(client, tmp_path, filename):
    make(tmp_path, "bob")
    outside = tmp_path / "secret.mp4"
    outside.write_bytes(b"x")
    resp = client.delete(f"/api/video/bob/{filename}/delete")
    assert resp.status_code in (400, 404) and outside.exists()


def test_delete_username_traversal_refused(client, tmp_path):
    make(tmp_path, "bob")
    (tmp_path / "downloads" / "x.mp4").write_bytes(b"x")
    resp = client.delete("/api/video/..%2Fbob/x.mp4/delete")
    assert resp.status_code in (400, 404)
    assert (tmp_path / "downloads" / "x.mp4").exists()


# ---------------------------------------------------------------- liste / restauration

def seeded(tmp_path):
    folder = make(tmp_path, "bob")
    state = link_state.LinkState(str(folder))
    state.ignore("1" * 18, "supprimée par l'utilisateur")
    state.ignore("2" * 18, "supprimée par l'utilisateur")
    state.ignore("3" * 18, "autre raison")
    state.mark_unavailable("4" * 18, "vidéo supprimée")
    state.record_failure("5" * 18, "transient", "reseau")
    state.save()
    return folder


def test_ignored_list(client, tmp_path):
    seeded(tmp_path)
    body = client.get("/api/profile/bob/ignored").get_json()
    assert body["count"] == 3
    assert {i["id"] for i in body["items"]} == {"1" * 18, "2" * 18, "3" * 18}
    item = next(i for i in body["items"] if i["id"] == "3" * 18)
    assert item["url"] == "https://www.tiktok.com/@bob/video/" + "3" * 18
    assert item["reason"] == "autre raison" and item["date"]


def test_ignored_list_is_read_only_and_validated(client, tmp_path):
    assert client.get("/api/profile/absent/ignored").status_code == 404
    assert not (tmp_path / "downloads").exists()
    assert client.get("/api/profile/..%2Fx/ignored").status_code in (400, 404)
    assert client.get("/api/profile/a b/ignored").status_code == 400
    make(tmp_path, "vide")
    assert client.get("/api/profile/vide/ignored").get_json() == {"count": 0, "items": []}


def test_restore_partial_then_all(client, tmp_path):
    folder = seeded(tmp_path)
    resp = client.post("/api/profile/bob/restore", json={"ids": ["1" * 18, "999"]})
    assert resp.get_json() == {"restored": 1, "ids": ["1" * 18]}
    assert "1" * 18 not in states(folder) and states(folder)["2" * 18]["status"] == "ignored"
    resp = client.post("/api/profile/bob/restore", json={"all": True})
    body = resp.get_json()
    assert body["restored"] == 2 and set(body["ids"]) == {"2" * 18, "3" * 18}
    left = states(folder)
    assert set(left) == {"4" * 18, "5" * 18}
    assert left["4" * 18]["status"] == "unavailable"
    assert client.get("/api/profile/bob/ignored").get_json()["count"] == 0


def test_restore_never_lifts_unavailable_or_retry(client, tmp_path):
    folder = seeded(tmp_path)
    resp = client.post("/api/profile/bob/restore", json={"ids": ["4" * 18, "5" * 18]})
    assert resp.get_json() == {"restored": 0, "ids": []}
    left = states(folder)
    assert left["4" * 18]["status"] == "unavailable" and left["5" * 18]["status"] == "retry"


def test_restore_validation(client, tmp_path):
    seeded(tmp_path)
    assert client.post("/api/profile/bob/restore", json={}).status_code == 400
    assert client.post("/api/profile/bob/restore", json={"ids": []}).status_code == 400
    assert client.post("/api/profile/bob/restore", json={"ids": [{"x": 1}]}).status_code == 400
    assert client.post("/api/profile/bob/restore", data="x").status_code == 400
    assert client.post("/api/profile/absent/restore", json={"all": True}).status_code == 404
    assert client.post("/api/profile/a b/restore", json={"all": True}).status_code == 400
    assert not (tmp_path / "downloads" / "absent").exists()


def test_restored_video_becomes_new_again(client, tmp_path):
    name = f"20240101_bob_{LONG}.mp4"
    make(tmp_path, "bob", [name], history=[LONG])
    delete(client, "bob", name)
    text = f"https://www.tiktok.com/@bob/video/{LONG}"
    before = client.post("/api/import/preview", json={"text": text}).get_json()["totals"]
    assert before["ignored"] == 1 and before["to_download"] == 0
    client.post("/api/profile/bob/restore", json={"ids": [LONG]})
    after = client.post("/api/import/preview", json={"text": text}).get_json()["totals"]
    assert after["new"] == 1 and after["to_download"] == 1
