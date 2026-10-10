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
        self.ended_by = "exhausted"    # valeur écrite dans scan_report par le faux listing
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
                        force_update=False, cookies_browser=None, cookies_file=None,
                        scan_all=None, scan_report=None):
        if scan_report is not None:
            scan_report["ended_by"] = f.ended_by
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


def _link_state():
    """États par id de link_state.json (source de vérité des échecs)."""
    path = os.path.join("downloads", USERNAME, "link_state.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)["items"]


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
    # L'échec n'est plus écrit dans metadata.json mais dans link_state.json (réessai prévu)
    assert "5" not in _history()
    state = _link_state()["5"]
    assert state["status"] == "retry" and state["attempts"] == 1 and state["next_retry"]
    assert stats["results"][0]["error"]
    assert stats["results"][0]["link_status"] == "retry"


def test_slideshow_failure_is_recorded(fake):
    fake.ids = ["6"]
    fake.types["6"] = True
    fake.fail.add("6")
    stats = _run()
    assert stats["failed"] == 1
    assert stats["results"][0]["type"] == "slideshow"
    assert "6" not in _history()
    assert _link_state()["6"]["status"] == "retry"


def test_exception_in_item_does_not_kill_run(fake):
    fake.ids = ["7", "8", "9"]
    fake.raise_on.add("8")
    stats = _run()

    assert stats["videos"] == 2 and stats["failed"] == 1
    assert [r["id"] for r in stats["results"]] == ["7", "8", "9"]
    assert "boom" in stats["results"][1]["error"]
    hist = _history()
    assert "8" not in hist and hist["9"]["success"] is True
    assert _link_state()["8"]["status"] == "retry" and "boom" in _link_state()["8"]["last_error"]


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


def test_history_items_are_skipped_even_with_force_update(fake):
    # Nouvelle règle du tri : un succès historisé n'est JAMAIS retéléchargé (force_update ne
    # fait que désactiver l'arrêt incrémental et retenter indisponibles / réessais en attente)
    main.save_to_history(USERNAME, "11", url=_url("11"), success=True)
    fake.ids = ["11", "12"]

    stats = _run()
    assert stats["skipped"] == 1 and stats["known"] == 1 and stats["videos"] == 1
    assert fake.links_kwargs["force_update"] is False

    stats = _run(force_update=True)
    assert fake.links_kwargs["force_update"] is True
    assert stats["skipped"] == 2 and stats["known"] == 2 and stats["videos"] == 0
    assert [c for c in fake.calls if c[0] == "download_video"] == [("download_video", "12")]


def test_legacy_failed_history_retried_once(fake):
    # Échec hérité (success=False dans metadata.json, sans état) : retenté une fois par le tri
    main.save_to_history(USERNAME, "13", url=_url("13"), success=False)
    main.save_to_history(USERNAME, "14", url=_url("14"), success=True)
    fake.ids = ["13", "14"]

    stats = _run()
    assert fake.history_seen == {"14"}          # l'échec 13 n'est pas « connu »
    assert [r["id"] for r in stats["results"]] == ["13"]
    assert stats["results"][0]["category"] == "retry_due" and stats["retried"] == 1
    assert stats["skipped"] == 1 and stats["known"] == 1
    assert _history()["13"]["success"] is True


def test_legacy_failed_then_follows_new_model(fake):
    main.save_to_history(USERNAME, "13", url=_url("13"), success=False)
    fake.ids = ["13"]
    fake.fail.add("13")

    stats = _run()                              # retenté une fois, échoue encore
    assert stats["retried"] == 1 and stats["failed"] == 1
    assert _link_state()["13"]["status"] == "retry"

    stats = _run()                              # réessai pas encore échu : sauté et « connu »
    assert stats["results"] == [] and stats["retry_waiting"] == 1 and stats["skipped"] == 1
    assert fake.history_seen == {"13"}

    stats = _run(force_update=True)             # force_update : retenté tout de suite
    assert fake.history_seen == set()
    assert [r["id"] for r in stats["results"]] == ["13"] and stats["retried"] == 1


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
    # Flux continu : le listing se termine après les traitements
    assert names[-1] == "complete" and names[-2] == "extraction_done"
    assert names.count("item_start") == 2 and names.count("item_done") == 2
    done = [d for e, d in events if e == "item_done"]
    assert done[-1]["done"] == 2
    assert dict(events)["extraction_done"] == {"total": 2}


# ---------------------------------------------------------------- flux continu

class Tracer:
    """Faux get_video_links qui enregistre l'ordre listing / traitements."""

    def __init__(self, fake, ids, error=None):
        self.events = []
        self.closed = False
        self.finished = False
        self.ids = ids
        self.error = error
        fake.on_download = lambda vid: self.events.append(("download", vid))

    def __call__(self, username, history, platform="tiktok", limit=None, callback_log=None,
                 force_update=False, cookies_browser=None, cookies_file=None, scan_all=None,
                 scan_report=None):
        if scan_report is not None:
            scan_report["ended_by"] = "error"
        try:
            for video_id in self.ids:
                self.events.append(("list", video_id))
                yield {"id": video_id, "url": _url(video_id)}
            if self.error:
                raise RuntimeError(self.error)
            if scan_report is not None:
                scan_report["ended_by"] = "exhausted"
            self.finished = True
            self.events.append(("list_end", None))
        finally:
            self.closed = True


def test_first_download_happens_before_listing_ends(fake, monkeypatch):
    tracer = Tracer(fake, ["1", "2", "3"])
    monkeypatch.setattr(orchestrator.main, "get_video_links", tracer)
    stats = _run()
    assert tracer.events == [("list", "1"), ("download", "1"), ("list", "2"), ("download", "2"),
                             ("list", "3"), ("download", "3"), ("list_end", None)]
    assert stats["videos"] == 3 and stats["total_extracted"] == 3


def test_limit_closes_generator(fake, monkeypatch):
    tracer = Tracer(fake, [str(i) for i in range(10)])
    monkeypatch.setattr(orchestrator.main, "get_video_links", tracer)
    stats = _run(limit=2)
    assert stats["videos"] == 2 and stats["total_extracted"] == 2
    assert tracer.closed and not tracer.finished
    assert [e for e in tracer.events if e[0] == "list"] == [("list", "0"), ("list", "1")]


def test_listing_error_midway_keeps_downloaded(fake, monkeypatch):
    tracer = Tracer(fake, ["1", "2"], error="listing coupé")
    monkeypatch.setattr(orchestrator.main, "get_video_links", tracer)
    logs = []
    stats = _run(log=lambda m, level="info": logs.append((level, m)))
    assert stats["videos"] == 2 and stats["extraction_error"] == "listing coupé"
    assert any(level == "error" and "listing coupé" in m for level, m in logs)
    assert _history()["1"]["success"] is True and _history()["2"]["success"] is True
    assert stats["scan_complete"] is False and stats["full_scan"] is False
    assert main.load_scan_state(USERNAME)["fully_scanned"] is False
    with open(os.path.join(fake.user_dir, f"{USERNAME}_videos.txt"), encoding="utf-8") as fh:
        assert sorted(fh.read().split()) == [_url("1"), _url("2")]


def test_stop_midway_closes_generator_and_saves_links(fake, monkeypatch):
    tracer = Tracer(fake, ["1", "2", "3", "4"])
    monkeypatch.setattr(orchestrator.main, "get_video_links", tracer)
    saved = []
    real_save = orchestrator.main.save_links_to_file
    monkeypatch.setattr(orchestrator.main, "save_links_to_file",
                        lambda u, v: (saved.append(list(v)), real_save(u, v)))
    stats = _run(should_stop=lambda: sum(1 for e in tracer.events if e[0] == "download") >= 1)
    assert stats["stopped"] is True and stats["videos"] == 1
    assert tracer.closed and not tracer.finished
    assert len(saved) == 1 and [v["id"] for v in saved[0]] == ["1"]
    assert main.load_scan_state(USERNAME)["fully_scanned"] is False


def test_unknown_type_in_stream_not_historized(fake, monkeypatch):
    tracer = Tracer(fake, ["1", "2"])
    fake.types["1"] = None
    monkeypatch.setattr(orchestrator.main, "get_video_links", tracer)
    stats = _run()
    assert stats["unknown"] == 1 and stats["videos"] == 1
    assert "1" not in _history() and _history()["2"]["success"] is True
    assert stats["scan_complete"] is False


def test_complete_stream_marks_fully_scanned_and_saves_links_once(fake, monkeypatch):
    tracer = Tracer(fake, ["1", "2"])
    monkeypatch.setattr(orchestrator.main, "get_video_links", tracer)
    saved = []
    monkeypatch.setattr(orchestrator.main, "save_links_to_file", lambda u, v: saved.append(list(v)))
    stats = _run()
    assert stats["full_scan"] is True and stats["scan_complete"] is True
    assert main.load_scan_state(USERNAME)["fully_scanned"] is True
    assert len(saved) == 1 and [v["id"] for v in saved[0]] == ["1", "2"]


def test_progress_total_unknown_while_listing_then_known(fake, monkeypatch):
    tracer = Tracer(fake, ["1", "2"])
    monkeypatch.setattr(orchestrator.main, "get_video_links", tracer)
    events = []
    _run(progress=lambda e, d: events.append((e, d)))
    assert [d["total"] for e, d in events if e in ("item_start", "item_done")] == [None] * 4
    assert ("extraction_done", {"total": 2}) in events
    complete = events[-1][1]
    assert events[-1][0] == "complete" and complete["total_extracted"] == 2


def test_parallel_mode_collects_listing_first(fake, monkeypatch):
    tracer = Tracer(fake, ["1", "2", "3"])
    monkeypatch.setattr(orchestrator.main, "get_video_links", tracer)
    events = []
    stats = _run(workers=2, progress=lambda e, d: events.append((e, d)))
    names = [e for e, _ in events]
    assert names[0] == "extraction_done" and names[-1] == "complete"
    assert tracer.events[:4] == [("list", "1"), ("list", "2"), ("list", "3"), ("list_end", None)]
    assert all(d["total"] == 3 for e, d in events if e in ("item_start", "item_done"))
    assert stats["videos"] == 3


# ---------------------------------------------------------------- événements pause / step

def test_step_events_detection_then_download(fake):
    fake.ids = ["1", "2"]
    fake.types = {"2": True}
    events = []
    _run(progress=lambda e, d: events.append((e, d)))
    steps = [(d["id"], d["step"]) for e, d in events if e == "step"]
    assert steps == [("1", "detection"), ("1", "telechargement"),
                     ("2", "detection"), ("2", "telechargement")]
    # step arrive entre item_start et item_done du même élément
    names = [e for e, _ in events if e in ("item_start", "step", "item_done")]
    assert names[:4] == ["item_start", "step", "step", "item_done"]


def test_step_unknown_type_has_no_download_step(fake):
    fake.ids = ["1"]
    fake.types = {"1": None}
    events = []
    _run(progress=lambda e, d: events.append((e, d)))
    assert [d["step"] for e, d in events if e == "step"] == ["detection"]


def test_pause_events_around_each_pause(fake):
    fake.ids = ["1", "2", "3"]
    events = []
    _run(min_sleep=2, max_sleep=3, progress=lambda e, d: events.append((e, d)))
    names = [e for e, _ in events]
    assert names.count("pause") == 2 and names.count("pause_end") == 2  # pas avant le premier
    assert [d["seconds"] for e, d in events if e == "pause"] == [2.5, 2.5]
    # chaque pause se ferme avant l'item_start suivant
    i = names.index("pause")
    assert names[i + 1] == "pause_end" and names[i + 2] == "item_start"
    assert [d for e, d in events if e == "pause_end"] == [{}, {}]


def test_pause_end_emitted_when_stopped_during_pause(fake):
    fake.ids = ["1", "2"]
    events = []
    calls = {"n": 0}

    def should_stop():
        calls["n"] += 1
        return any(e == "pause" for e, _ in events) and calls["n"] > 3

    _run(should_stop=should_stop, progress=lambda e, d: events.append((e, d)))
    names = [e for e, _ in events]
    assert "pause" in names and names.index("pause_end") > names.index("pause")


def test_no_pause_event_when_sleep_is_zero(fake, monkeypatch):
    monkeypatch.setattr(orchestrator.random, "uniform", lambda a, b: 0)
    fake.ids = ["1", "2"]
    events = []
    _run(min_sleep=0, max_sleep=0, progress=lambda e, d: events.append((e, d)))
    assert not any(e in ("pause", "pause_end") for e, _ in events)
