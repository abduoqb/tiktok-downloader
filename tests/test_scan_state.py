"""Tests de l'etat de scan (mode incremental seulement apres un scan complet). Aucun reseau."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main
import orchestrator

USER = "user"
RECENT_12 = [str(n) for n in range(30, 18, -1)]


def _url(i):
    return f"https://www.tiktok.com/@{USER}/video/{i}"


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def env(base, monkeypatch):
    monkeypatch.setattr(orchestrator.random, "uniform", lambda a, b: 0)
    st = type("S", (), {})()
    st.listing = []            # ids du profil, du plus recent au plus ancien
    st.types = {}
    st.fail = set()
    st.stop_after = None       # should_stop devient vrai apres N telechargements
    st.downloads = 0
    st.extraction_error = None

    def get_video_links(username, history, platform="tiktok", limit=None, callback_log=None,
                        force_update=False, cookies_browser=None, cookies_file=None,
                        scan_all=None, scan_report=None):
        # Faux reseau : reutilise la vraie logique de filtrage
        if scan_all is None:
            scan_all = not main.load_scan_state(username)["fully_scanned"]
        entries = [{"id": i, "url": _url(i)} for i in st.listing]
        rep = scan_report if scan_report is not None else {}
        yield from main._filter_entries(iter(entries), history, limit, force_update,
                                        lambda m, level="info": None, scan_all=scan_all,
                                        scan_report=rep)
        if st.extraction_error:
            rep["ended_by"] = "error"
            raise RuntimeError(st.extraction_error)

    def dl(url, username, video_id, retries=3, cookies_browser=None, cookies_file=None):
        st.downloads += 1
        if video_id in st.fail:
            return False
        d = main.get_user_dir(username)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"20240101_{username}_{video_id}.mp4"), "wb") as fh:
            fh.write(b"x" * 100)
        return True

    monkeypatch.setattr(main, "get_video_links", get_video_links)
    monkeypatch.setattr(main, "is_slideshow",
                        lambda url, **k: st.types.get(url.rsplit("/", 1)[1], False))
    monkeypatch.setattr(main, "download_video", dl)

    def run(**kw):
        def stop():
            return st.stop_after is not None and st.downloads >= st.stop_after
        return orchestrator.run_download(USER, min_sleep=0, max_sleep=0, should_stop=stop,
                                         sleep=lambda s: None, **kw)

    st.run = run
    return st


def _known(ids):
    for i in ids:
        main.save_to_history(USER, i, url=_url(i))


def _tmp_files():
    return [n for n in os.listdir(main.get_user_dir(USER)) if n.endswith(".tmp")]


# ------------------------------------------------------------ etat de scan

def test_state_absent_is_not_scanned(base):
    assert main.load_scan_state(USER) == {"fully_scanned": False, "completed_at": None}


def test_state_roundtrip_and_atomic(base, monkeypatch):
    main.save_scan_state(USER, True)
    state = main.load_scan_state(USER)
    assert state["fully_scanned"] is True and state["completed_at"]
    path = os.path.join(main.get_user_dir(USER), "scan_state.json")
    with open(path, encoding="utf-8") as fh:
        assert json.load(fh)["fully_scanned"] is True
    assert _tmp_files() == []

    # Ecriture atomique : un echec de os.replace laisse l'ancien fichier intact, sans .tmp
    def boom(a, b):
        raise OSError("disque plein")
    with monkeypatch.context() as m:
        m.setattr(main.os, "replace", boom)
        with pytest.raises(OSError):
            main.save_scan_state(USER, False)
    assert main.load_scan_state(USER)["fully_scanned"] is True
    assert _tmp_files() == []


@pytest.mark.parametrize("content", ["{pas du json", "[]", '{"fully_scanned": "yes"}', ""])
def test_unreadable_state_is_not_scanned(base, content):
    os.makedirs(main.get_user_dir(USER))
    with open(os.path.join(main.get_user_dir(USER), "scan_state.json"), "w") as fh:
        fh.write(content)
    assert main.load_scan_state(USER)["fully_scanned"] is False


# ------------------------------------------------------------ get_video_links (bug reproduit)

class _FakeYDL:
    entries = []

    def __init__(self, opts):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download=False):
        return {"entries": list(_FakeYDL.entries), "title": USER}


def _links(monkeypatch, history, **kw):
    monkeypatch.setattr(main.yt_dlp, "YoutubeDL", _FakeYDL)
    ids = [str(n) for n in range(30, 0, -1)]  # 30 plus recent ... 1 plus ancien
    _FakeYDL.entries = [{"id": i, "url": _url(i)} for i in ids]
    report = {}
    out = list(main.get_video_links(USER, set(history), scan_report=report, **kw))
    return [v["id"] for v in out], report


def test_no_state_scans_everything_despite_12_known(base, monkeypatch):
    ids, report = _links(monkeypatch, RECENT_12)
    assert ids == [str(n) for n in range(18, 0, -1)]
    assert report == {"ended_by": "exhausted", "listed": 30}


def test_fully_scanned_keeps_incremental_stop(base, monkeypatch):
    main.save_scan_state(USER, True)
    ids, report = _links(monkeypatch, RECENT_12)
    assert ids == []
    assert report["ended_by"] == "incremental" and report["listed"] == 10


def test_force_update_disables_stop(base, monkeypatch):
    main.save_scan_state(USER, True)
    ids, report = _links(monkeypatch, RECENT_12, force_update=True)
    assert len(ids) == 18 and report["ended_by"] == "exhausted"


def test_explicit_scan_all_overrides_state(base, monkeypatch):
    main.save_scan_state(USER, True)
    ids, _ = _links(monkeypatch, RECENT_12, scan_all=True)
    assert len(ids) == 18
    main.save_scan_state(USER, False)
    ids, report = _links(monkeypatch, RECENT_12, scan_all=False)
    assert ids == [] and report["ended_by"] == "incremental"


def test_auto_scan_log_and_state_never_modified(base, monkeypatch):
    logs = []
    monkeypatch.setattr(main.yt_dlp, "YoutubeDL", _FakeYDL)
    _FakeYDL.entries = []
    list(main.get_video_links(USER, set(), callback_log=lambda m, level="info": logs.append(m)))
    assert any(m.startswith("Premier scan complet de ce profil") for m in logs)
    assert not os.path.exists(os.path.join("downloads", USER, "scan_state.json"))


def test_limit_report(base, monkeypatch):
    ids, report = _links(monkeypatch, [], limit=3)
    assert len(ids) == 3 and report["ended_by"] == "limit"


# ------------------------------------------------------------ orchestrateur

def test_full_run_marks_scanned(env):
    env.listing = ["3", "2", "1"]
    logs = []
    stats = env.run(log=lambda m, level="info": logs.append(m))
    assert stats["videos"] == 3
    assert stats["full_scan"] is True and stats["scan_complete"] is True
    assert main.load_scan_state(USER)["fully_scanned"] is True
    assert any(m.startswith("Scan complet terminé") for m in logs)


def test_orchestrator_reaches_old_videos_then_goes_incremental(env):
    env.listing = [str(n) for n in range(30, 0, -1)]
    _known(RECENT_12)
    stats = env.run()
    assert stats["videos"] == 18 and stats["scan_complete"] is True
    # profil desormais scanne : un nouveau run s'arrete de facon incrementale
    env.listing = ["31"] + [str(n) for n in range(30, 0, -1)]
    stats = env.run()
    assert stats["videos"] == 1 and stats["full_scan"] is False and stats["scan_complete"] is True


def test_limit_not_marked(env):
    env.listing = ["5", "4", "3", "2", "1"]
    stats = env.run(limit=2)
    assert stats["videos"] == 2
    assert stats["full_scan"] is False and stats["scan_complete"] is False
    assert main.load_scan_state(USER)["fully_scanned"] is False


def test_stop_not_marked(env):
    env.listing = ["5", "4", "3", "2", "1"]
    env.stop_after = 2
    stats = env.run()
    assert stats["stopped"] is True and stats["videos"] == 2
    assert main.load_scan_state(USER)["fully_scanned"] is False


def test_unknown_not_marked(env):
    env.listing = ["3", "2", "1"]
    env.types = {"2": None}
    stats = env.run()
    assert stats["unknown"] == 1 and stats["scan_complete"] is False
    assert main.load_scan_state(USER)["fully_scanned"] is False


def test_extraction_error_not_marked(env):
    env.listing = ["3", "2", "1"]
    env.extraction_error = "casse"
    stats = env.run()
    assert stats["extraction_error"] == "casse"
    assert main.load_scan_state(USER)["fully_scanned"] is False


def test_failed_download_still_marks(env):
    env.listing = ["3", "2", "1"]
    env.fail = {"2"}
    stats = env.run()
    assert stats["failed"] == 1 and stats["scan_complete"] is True


def test_already_scanned_state_kept_on_error_but_reset_if_untreated(env):
    main.save_scan_state(USER, True)
    env.listing = ["3", "2", "1"]
    env.extraction_error = "casse"
    env.run()  # tout a ete traite malgre l'erreur : etat inchange
    assert main.load_scan_state(USER)["fully_scanned"] is True

    env.extraction_error = None
    env.listing = ["9", "8", "7", "6"]
    env.stop_after = 1
    stats = env.run()
    assert stats["stopped"] is True
    assert main.load_scan_state(USER)["fully_scanned"] is False
    assert stats["scan_complete"] is False
