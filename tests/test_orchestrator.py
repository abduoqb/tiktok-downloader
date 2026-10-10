"""
Tests de orchestrator.run_download (fonctions réseau de main mockées, aucun accès réseau).

L'historique (metadata.json) est réel, dans un répertoire temporaire.
"""
import json
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main
import orchestrator


USERNAME = "user"
COOKIES_FILE = "cookies.txt"
COOKIES_BROWSER = "firefox"


def _url(video_id):
    return f"https://www.tiktok.com/@{USERNAME}/video/{video_id}"


class Fake:
    """État des faux main.* : types, échecs, appels enregistrés."""

    def __init__(self):
        self.ids = []                  # ids renvoyés par get_video_links
        self.types = {}                # id -> True / False / None / Exception
        self.fail = set()              # ids dont le téléchargement échoue
        self.raise_on = set()          # ids dont le téléchargement lève une exception
        self.no_file = set()           # ids : download_video renvoie True sans fichier
        self.calls = []                # (nom, id)
        self.cookies = []              # (nom, cookies_file, cookies_browser)
        self.links_kwargs = None
        self.history_seen = None       # historique reçu par get_video_links
        self.on_download = None        # callable(id) appelé à chaque téléchargement
        self.lock = threading.Lock()

    def record(self, name, video_id, kwargs):
        with self.lock:
            self.calls.append((name, video_id))
            self.cookies.append((name, kwargs.get("cookies_file"), kwargs.get("cookies_browser")))


@pytest.fixture
def fake(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    f = Fake()
    user_dir = os.path.join("downloads", USERNAME)

    def get_video_links(username, history, platform="tiktok", limit=None, callback_log=None,
                        force_update=False, cookies_browser=None, cookies_file=None):
        f.history_seen = set(history)
        f.links_kwargs = {"limit": limit, "force_update": force_update,
                          "cookies_file": cookies_file, "cookies_browser": cookies_browser}
        f.record("get_video_links", None, f.links_kwargs)
        for video_id in f.ids:
            # Le faux ignore volontairement limit : l'orchestrateur doit l'appliquer lui-même
            yield {"id": video_id, "url": _url(video_id)}

    def is_slideshow(url, username=None, use_cache=True, cookies_browser=None, cookies_file=None):
        video_id = url.rsplit("/", 1)[1]
        f.record("is_slideshow", video_id, {"cookies_file": cookies_file,
                                            "cookies_browser": cookies_browser})
        value = f.types.get(video_id, False)
        if isinstance(value, Exception):
            raise value
        return value

    def download_video(url, username, video_id, retries=3, cookies_browser=None, cookies_file=None):
        f.record("download_video", video_id, {"cookies_file": cookies_file,
                                              "cookies_browser": cookies_browser})
        if f.on_download:
            f.on_download(video_id)
        if video_id in f.raise_on:
            raise RuntimeError("boom")
        if video_id in f.fail:
            return False
        if video_id in f.no_file:
            return True
        os.makedirs(user_dir, exist_ok=True)
        with open(os.path.join(user_dir, f"20240101_{username}_{video_id}.mp4"), "wb") as fh:
            fh.write(b"x" * 2048)
        return True

    def download_slideshow(url, username, video_id, cookies_browser=None, cookies_file=None):
        f.record("download_slideshow", video_id, {"cookies_file": cookies_file,
                                                  "cookies_browser": cookies_browser})
        if f.on_download:
            f.on_download(video_id)
        if video_id in f.raise_on:
            raise RuntimeError("boom")
        if video_id in f.fail:
            return False
        os.makedirs(user_dir, exist_ok=True)
        for i in (1, 2, 3):
            with open(os.path.join(user_dir, f"20240101_{username}_{video_id}_img={i}.jpg"), "wb") as fh:
                fh.write(b"img")
        return True

    monkeypatch.setattr(orchestrator.main, "get_video_links", get_video_links)
    monkeypatch.setattr(orchestrator.main, "is_slideshow", is_slideshow)
    monkeypatch.setattr(orchestrator.main, "download_video", download_video)
    monkeypatch.setattr(orchestrator.main, "download_slideshow", download_slideshow)
    monkeypatch.setattr(orchestrator.random, "uniform", lambda a, b: 2.5)
    f.user_dir = user_dir
    return f


def _history():
    path = os.path.join("downloads", USERNAME, "metadata.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


class SleepRecorder:
    def __init__(self, fake=None):
        self.calls = []
        self.fake = fake

    def __call__(self, seconds):
        self.calls.append(seconds)
        if self.fake is not None:
            with self.fake.lock:
                self.fake.calls.append(("sleep", seconds))


def _run(**kwargs):
    kwargs.setdefault("sleep", SleepRecorder())
    kwargs.setdefault("log", lambda msg, level="info": None)
    return orchestrator.run_download(USERNAME, **kwargs)


# ---------------------------------------------------------------- cas nominaux

def test_video_success(fake):
    fake.ids = ["1"]
    stats = _run()

    assert stats["videos"] == 1 and stats["failed"] == 0 and stats["unknown"] == 0
    assert stats["total_extracted"] == 1
    assert stats["stopped"] is False
    assert stats["size_mb"] == pytest.approx(2048 / (1024 * 1024))
    [res] = stats["results"]
    assert res["success"] is True and res["type"] == "video" and res["size"] == 2048
    assert os.path.basename(res["files"][0]) == f"20240101_{USERNAME}_1.mp4"

    hist = _history()
    assert hist["1"]["success"] is True and hist["1"]["size"] == 2048 and hist["1"]["type"] == "video"
    # Liens sauvegardés comme les boucles historiques
    with open(os.path.join(fake.user_dir, f"{USERNAME}_videos.txt"), encoding="utf-8") as fh:
        assert fh.read().strip() == _url("1")


def test_slideshow_success(fake):
    fake.ids = ["2"]
    fake.types["2"] = True
    stats = _run()

    assert stats["slideshows"] == 1 and stats["videos"] == 0 and stats["failed"] == 0
    assert stats["results"][0]["file_count"] == 3
    hist = _history()
    assert hist["2"]["type"] == "slideshow" and hist["2"]["file_count"] == 3
    assert hist["2"]["success"] is True
    assert ("download_video", "2") not in fake.calls


def test_unknown_type_not_in_history_and_never_downloaded(fake):
    fake.ids = ["3", "4"]
    fake.types["3"] = None
    fake.types["4"] = RuntimeError("is_slideshow a planté")
    logs = []
    stats = _run(log=lambda m, level="info": logs.append((level, m)))

    assert stats["unknown"] == 2 and stats["failed"] == 0 and stats["videos"] == 0
    assert _history() == {}
    assert not any(name.startswith("download") for name, _ in fake.calls)
    assert any(level == "error" and "3" in m for level, m in logs)
    assert all(r["type"] == "unknown" and not r["success"] for r in stats["results"])


@pytest.mark.parametrize("mode", ["fail", "no_file"])
def test_video_failure_is_recorded(fake, mode):
    fake.ids = ["5"]
    getattr(fake, mode).add("5")
    stats = _run()

    assert stats["failed"] == 1 and stats["videos"] == 0
    assert _history()["5"]["success"] is False
    assert stats["results"][0]["error"]


def test_slideshow_failure_is_recorded(fake):
    fake.ids = ["6"]
    fake.types["6"] = True
    fake.fail.add("6")
    stats = _run()
    assert stats["failed"] == 1
    entry = _history()["6"]
    assert entry["type"] == "slideshow" and entry["success"] is False


def test_exception_in_item_does_not_kill_run(fake):
    fake.ids = ["7", "8", "9"]
    fake.raise_on.add("8")
    stats = _run()

    assert stats["videos"] == 2 and stats["failed"] == 1
    assert [r["id"] for r in stats["results"]] == ["7", "8", "9"]
    assert "boom" in stats["results"][1]["error"]
    hist = _history()
    assert hist["8"]["success"] is False and hist["9"]["success"] is True


def test_extraction_error_is_logged_and_run_returns(fake, monkeypatch):
    def broken(*a, **k):
        yield {"id": "10", "url": _url("10")}
        raise RuntimeError("extraction cassée")

    monkeypatch.setattr(orchestrator.main, "get_video_links", broken)
    logs = []
    stats = _run(log=lambda m, level="info": logs.append((level, m)))
    assert stats["total_extracted"] == 1 and stats["videos"] == 1
    assert any(level == "error" and "extraction cassée" in m for level, m in logs)


# ---------------------------------------------------------------- limit / historique

def test_limit_is_applied(fake):
    fake.ids = [str(i) for i in range(10)]
    stats = _run(limit=3)

    assert fake.links_kwargs["limit"] == 3
    assert stats["total_extracted"] == 3 and stats["videos"] == 3
    assert [r["id"] for r in stats["results"]] == ["0", "1", "2"]


def test_history_items_are_skipped_unless_force_update(fake):
    main.save_to_history(USERNAME, "11", url=_url("11"), success=True)
    fake.ids = ["11", "12"]

    stats = _run()
    assert stats["skipped"] == 1 and stats["videos"] == 1
    assert fake.links_kwargs["force_update"] is False

    stats = _run(force_update=True)
    assert fake.links_kwargs["force_update"] is True
    assert stats["skipped"] == 0 and stats["videos"] == 2


def test_failed_history_retried_only_with_force_update(fake):
    main.save_to_history(USERNAME, "13", url=_url("13"), success=False)
    main.save_to_history(USERNAME, "14", url=_url("14"), success=True)
    fake.ids = ["13", "14"]

    stats = _run()
    assert fake.history_seen == {"13", "14"}
    assert stats["skipped"] == 2 and stats["videos"] == 0

    stats = _run(force_update=True)
    assert fake.history_seen == {"14"}          # l'échec 13 n'est plus dans l'historique
    assert [r["id"] for r in stats["results"]] == ["13", "14"]
    assert _history()["13"]["success"] is True


def test_stats_downloaded_and_processed(fake):
    fake.ids = ["15", "16", "17"]
    fake.types["16"] = True
    fake.fail.add("17")
    stats = _run()
    assert stats["downloaded"] == 2 and stats["processed"] == 3


def test_sleep_swapped_and_pause_error_is_guarded(fake, monkeypatch):
    assert orchestrator._normalize_sleep(9, 2) == (2.0, 9.0)
    assert orchestrator._normalize_sleep(None, float("nan")) == (0.0, 0.0)

    def boom(a, b):
        raise RuntimeError("uniform cassé")
    monkeypatch.setattr(orchestrator.random, "uniform", boom)
    fake.ids = ["92", "93"]
    stats = _run()
    assert stats["videos"] == 2


@pytest.mark.parametrize("lo, hi", [(None, None), (float("nan"), float("nan"))])
def test_none_nan_sleep_runs(fake, monkeypatch, lo, hi):
    bounds = []
    monkeypatch.setattr(orchestrator.random, "uniform", lambda a, b: bounds.append((a, b)) or 0.0)
    fake.ids = ["94", "95"]
    sleeper = SleepRecorder()
    stats = _run(min_sleep=lo, max_sleep=hi, sleep=sleeper)
    assert stats["videos"] == 2 and sleeper.calls == []
    assert bounds == [(0.0, 0.0)]


# ---------------------------------------------------------------- arrêt

def test_should_stop_between_items(fake):
    fake.ids = ["20", "21", "22"]
    downloaded = []
    fake.on_download = downloaded.append
    stats = _run(should_stop=lambda: len(downloaded) >= 1)

    assert stats["stopped"] is True
    assert downloaded == ["20"]
    assert len(stats["results"]) == 1


def test_should_stop_during_sleep(fake):
    fake.ids = ["30", "31"]
    sleeper = SleepRecorder()
    stats = _run(sleep=sleeper, should_stop=lambda: len(sleeper.calls) >= 1)

    assert stats["stopped"] is True
    # Pause de 2.5 s découpée en tranches <= 1 s : interrompue après la première tranche
    assert sleeper.calls == [1.0]
    assert [r["id"] for r in stats["results"]] == ["30"]
    assert ("download_video", "31") not in fake.calls


def test_should_stop_before_start(fake):
    fake.ids = ["40"]
    stats = _run(should_stop=lambda: True)
    assert stats["stopped"] is True and stats["results"] == []
    assert not any(name.startswith("download") for name, _ in fake.calls)


# ---------------------------------------------------------------- anti-ban

def test_sleep_before_each_item_except_first_including_after_failure(fake):
    fake.ids = ["50", "51", "52"]
    fake.fail.add("50")            # échec sur le premier : la pause suit quand même
    fake.types["51"] = None        # type inconnu : pause avant le suivant aussi
    sleeper = SleepRecorder(fake)
    stats = _run(sleep=sleeper)

    assert stats["failed"] == 1 and stats["unknown"] == 1 and stats["videos"] == 1
    # 2 pauses de 2.5 s, chacune en tranches de 1 s max
    assert sleeper.calls == [1.0, 1.0, 0.5, 1.0, 1.0, 0.5]
    assert all(s <= 1.0 for s in sleeper.calls)
    sequence = [name for name, _ in fake.calls if name != "get_video_links"]
    assert sequence == ["is_slideshow", "download_video",
                        "sleep", "sleep", "sleep", "is_slideshow",
                        "sleep", "sleep", "sleep", "is_slideshow", "download_video"]


# ---------------------------------------------------------------- parallélisme

def _scenario(fake):
    fake.ids = [str(i) for i in range(60, 68)]
    fake.types.update({"61": True, "64": True, "62": None})
    fake.fail.add("63")
    fake.raise_on.add("65")


def test_workers_2_gives_same_counters(fake, tmp_path, monkeypatch):
    _scenario(fake)
    seq_sleep = SleepRecorder()
    seq = _run(sleep=seq_sleep)
    seq_history = _history()

    # Nouveau répertoire propre pour le run parallèle
    other = tmp_path / "parallel"
    other.mkdir()
    monkeypatch.chdir(other)
    par_sleep = SleepRecorder()
    par = _run(workers=2, sleep=par_sleep)

    keys = ["videos", "slideshows", "failed", "unknown", "skipped", "total_extracted"]
    assert {k: par[k] for k in keys} == {k: seq[k] for k in keys}
    assert par["size_mb"] == pytest.approx(seq["size_mb"])
    assert [r["id"] for r in par["results"]] == [r["id"] for r in seq["results"]]
    assert [r["success"] for r in par["results"]] == [r["success"] for r in seq["results"]]
    # Même historique (pas de mise à jour perdue malgré les threads)
    assert {k: v["success"] for k, v in _history().items()} == \
           {k: v["success"] for k, v in seq_history.items()}
    # Pause appliquée avant chaque tâche sauf la première, aussi en parallèle
    assert sum(par_sleep.calls) == pytest.approx(sum(seq_sleep.calls)) == pytest.approx(2.5 * 7)


# ---------------------------------------------------------------- cookies

def test_cookies_passed_to_every_main_function(fake):
    fake.ids = ["70", "71"]
    fake.types["71"] = True
    _run(cookies_file=COOKIES_FILE, cookies_browser=COOKIES_BROWSER)

    names = {name for name, _, _ in fake.cookies}
    assert names == {"get_video_links", "is_slideshow", "download_video", "download_slideshow"}
    assert all(cf == COOKIES_FILE and cb == COOKIES_BROWSER for _, cf, cb in fake.cookies)


def test_progress_events(fake):
    fake.ids = ["80", "81"]
    events = []
    _run(progress=lambda e, d: events.append((e, d)))
    names = [e for e, _ in events]
    assert names[0] == "extraction_done" and names[-1] == "complete"
    assert names.count("item_start") == 2 and names.count("item_done") == 2
    done = [d for e, d in events if e == "item_done"]
    assert done[-1]["done"] == 2 and done[-1]["total"] == 2
