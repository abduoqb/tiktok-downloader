"""Tri des liens dans l'orchestrateur : adoption, ignorés, réessais, indisponibles, état
link_state.json, arrêt incrémental (main.* réseau mocké, tmp_path, aucun accès réseau)."""
import json
import os
import sys
import threading
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import link_state  # noqa: E402
import main  # noqa: E402
import orchestrator  # noqa: E402

USER = "user"
BASE = 7300000000000000000


def vid(n):
    """Identifiant TikTok réaliste (19 chiffres : reconnu par disk_index)."""
    return str(BASE + n)


def url(i, kind="video"):
    return f"https://www.tiktok.com/@{USER}/{kind}/{i}"


def item(i):
    return {"id": i, "url": url(i)}


DELETED = "ERROR: [TikTok] {}: Video not available, status code 10204"
FORBIDDEN = "ERROR: [TikTok] {}: Unable to download webpage: HTTP Error 403: Forbidden"


class Fake:
    def __init__(self):
        self.ids = []
        self.types = {}          # id -> True / False / None / Exception
        self.probe_errors = {}   # id -> message exposé via main.last_error() (sonde)
        self.errors = {}         # id -> message d'échec (download renvoie False)
        self.calls = []
        self.history_seen = None
        self.use_filter = False  # True = vrai filtrage main._filter_entries
        self.ended_by = "exhausted"
        self.on_download = None
        self.lock = threading.Lock()


@pytest.fixture
def fake(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    f = Fake()
    user_dir = os.path.join("downloads", USER)

    def get_video_links(username, history, platform="tiktok", limit=None, callback_log=None,
                        force_update=False, cookies_browser=None, cookies_file=None,
                        scan_all=None, scan_report=None):
        f.history_seen = set(history)
        entries = [{"id": i, "url": url(i)} for i in f.ids]
        if f.use_filter:
            if scan_all is None:
                scan_all = not main.load_scan_state(username)["fully_scanned"]
            yield from main._filter_entries(iter(entries), history, limit, force_update,
                                            lambda *a, **k: None, scan_all=scan_all,
                                            scan_report=scan_report)
            return
        if scan_report is not None:
            scan_report["ended_by"] = f.ended_by
        yield from entries

    def is_slideshow(u, username=None, use_cache=True, cookies_browser=None, cookies_file=None):
        i = u.rsplit("/", 1)[1]
        with f.lock:
            f.calls.append(("probe", i))
        main.reset_last_error()
        value = f.types.get(i, False)
        if isinstance(value, Exception):
            raise value
        if value is None and i in f.probe_errors:
            main._set_last_error(f.probe_errors[i])
        return value

    def download_video(u, username, video_id, retries=3, cookies_browser=None, cookies_file=None):
        with f.lock:
            f.calls.append(("video", video_id))
        main.reset_last_error()
        if f.on_download:
            f.on_download(video_id)
        if video_id in f.errors:
            main._set_last_error(f.errors[video_id])
            return False
        os.makedirs(user_dir, exist_ok=True)
        with open(os.path.join(user_dir, f"20240101_{username}_{video_id}.mp4"), "wb") as fh:
            fh.write(b"x" * 100)
        return True

    def download_slideshow(u, username, video_id, cookies_browser=None, cookies_file=None):
        with f.lock:
            f.calls.append(("slideshow", video_id))
        main.reset_last_error()
        if video_id in f.errors:
            main._set_last_error(f.errors[video_id])
            return False
        os.makedirs(user_dir, exist_ok=True)
        with open(os.path.join(user_dir, f"20240101_{username}_{video_id}_img=1.jpg"), "wb") as fh:
            fh.write(b"i")
        return True

    monkeypatch.setattr(main, "get_video_links", get_video_links)
    monkeypatch.setattr(main, "is_slideshow", is_slideshow)
    monkeypatch.setattr(main, "download_video", download_video)
    monkeypatch.setattr(main, "download_slideshow", download_slideshow)
    monkeypatch.setattr(orchestrator.random, "uniform", lambda a, b: 0)
    f.user_dir = user_dir
    return f


def run(**kw):
    kw.setdefault("log", lambda m, level="info": None)
    return orchestrator.run_download(USER, min_sleep=0, max_sleep=0, sleep=lambda s: None, **kw)


def run_import(items, **kw):
    kw.setdefault("log", lambda m, level="info": None)
    return orchestrator.run_import(USER, items, min_sleep=0, max_sleep=0,
                                   sleep=lambda s: None, **kw)


def history():
    path = os.path.join("downloads", USER, "metadata.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def states():
    path = os.path.join("downloads", USER, "link_state.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)["items"]


def write_states(mutator):
    state = link_state.LinkState.load(os.path.join("downloads", USER))
    mutator(state)
    state.dirty = True
    state.save()


def make_due(i):
    """Rend le réessai de i échu (next_retry dans le passé)."""
    path = os.path.join("downloads", USER, "link_state.json")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    data["items"][i]["next_retry"] = (datetime.now() - timedelta(seconds=1)).isoformat(
        timespec="seconds")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def put_video_file(i, size=100):
    os.makedirs(os.path.join("downloads", USER), exist_ok=True)
    with open(os.path.join("downloads", USER, f"20240101_{USER}_{i}.mp4"), "wb") as fh:
        fh.write(b"v" * size)


def downloads(f):
    return [c for c in f.calls if c[0] in ("video", "slideshow")]


SUBCOUNTERS = ("known", "adopted", "ignored", "unavailable", "retry_waiting", "duplicate",
               "invalid")


def assert_skipped_consistent(stats):
    assert stats["skipped"] == sum(stats[k] for k in SUBCOUNTERS)


# ---------------------------------------------------------------- adoption

def test_adoption_scan_mode_no_download_tags_preserved(fake):
    a, b, c = vid(1), vid(2), vid(3)
    put_video_file(a, size=321)
    for n in (1, 2):
        with open(os.path.join("downloads", USER, f"20240101_{USER}_{b}_img={n}.jpg"), "wb") as fh:
            fh.write(b"img")
    # Ancienne entrée en échec, avec des champs utilisateur à conserver
    with open(os.path.join("downloads", USER, "metadata.json"), "w", encoding="utf-8") as fh:
        json.dump({a: {"url": url(a), "type": "video", "success": False, "tags": ["chat"],
                       "favorite": True, "notes": "à revoir"}}, fh)
    write_states(lambda s: s.record_failure(b, "transient", "403"))
    fake.ids = [a, b, c]

    stats = run()
    assert downloads(fake) == [("video", c)]
    assert ("probe", a) not in fake.calls and ("probe", b) not in fake.calls
    assert stats["adopted"] == 2 and stats["videos"] == 1
    assert_skipped_consistent(stats)
    h = history()
    assert h[a]["success"] is True and h[a]["type"] == "video" and h[a]["size"] == 321
    assert h[a]["tags"] == ["chat"] and h[a]["favorite"] is True and h[a]["notes"] == "à revoir"
    assert h[b]["type"] == "slideshow" and h[b]["file_count"] == 2
    assert h[b]["url"] == url(b, "photo")
    assert b not in states()                     # état retry effacé par l'adoption
    assert {a, b} <= fake.history_seen           # adoptés = « connus » pour le listing

    stats = run()                                # second run : déjà téléchargés
    assert stats["adopted"] == 0 and stats["known"] == 3 and downloads(fake) == [("video", c)]


def test_adoption_import_mode(fake):
    a, c = vid(1), vid(3)
    put_video_file(a)
    logs = []
    events = []
    stats = run_import([item(a), item(c)], log=lambda m, level="info": logs.append(m),
                       progress=lambda e, d: events.append((e, d)))
    assert downloads(fake) == [("video", c)]
    assert stats["adopted"] == 1 and stats["skipped"] == 1 and stats["videos"] == 1
    assert history()[a]["success"] is True and history()[a]["url"] == url(a)
    assert [d["total"] for e, d in events if e == "item_start"] == [1]
    assert any("2 liens : 0 déjà téléchargés, 1 adoptés depuis le disque, 0 à retenter, "
               "0 ignorés, 0 indisponibles, 1 nouveaux" in m for m in logs)


# ---------------------------------------------------------------- ignorés

@pytest.mark.parametrize("force_update", [False, True])
def test_ignored_never_downloaded(fake, force_update):
    a, b = vid(1), vid(2)
    put_video_file(b)                            # ignoré même si un fichier existe encore
    write_states(lambda s: (s.ignore(a, "supprimée"), s.ignore(b, "supprimée")))
    fake.ids = [a, b]
    stats = run(force_update=force_update)
    assert downloads(fake) == [] and not any(c[0] == "probe" for c in fake.calls)
    assert stats["ignored"] == 2 and stats["skipped"] == 2 and stats["adopted"] == 0
    assert a not in history() and b not in history()
    assert states()[a]["status"] == "ignored"

    stats = run_import([item(a), item(b)], force_update=force_update)
    assert downloads(fake) == [] and stats["ignored"] == 2


# ---------------------------------------------------------------- réessais

def test_transient_failure_retry_then_waiting_then_due(fake):
    a = vid(1)
    fake.ids = [a]
    fake.errors[a] = FORBIDDEN.format(a)
    stats = run()
    entry = states()[a]
    assert entry["status"] == "retry" and entry["attempts"] == 1
    next_retry = datetime.fromisoformat(entry["next_retry"])
    assert timedelta(seconds=590) < next_retry - datetime.now() <= timedelta(seconds=600)
    assert "403" in entry["last_error"]
    assert stats["results"][0]["link_status"] == "retry"
    assert a not in history()

    stats = run()                                # avant l'échéance : pas retenté
    assert downloads(fake) == [("video", a)]
    assert stats["retry_waiting"] == 1 and stats["skipped"] == 1
    assert a in fake.history_seen                # compte comme « connu »

    make_due(a)
    del fake.errors[a]
    stats = run()                                # après l'échéance : retenté, succès
    assert downloads(fake) == [("video", a), ("video", a)]
    assert stats["retried"] == 1 and stats["videos"] == 1
    assert stats["results"][0]["category"] == "retry_due"
    assert a not in states() and history()[a]["success"] is True


def test_three_transient_failures_become_unavailable(fake):
    a = vid(1)
    fake.ids = [a]
    fake.errors[a] = FORBIDDEN.format(a)
    run()
    make_due(a)
    run()
    assert states()[a]["attempts"] == 2 and states()[a]["status"] == "retry"
    make_due(a)
    stats = run()
    entry = states()[a]
    assert entry["status"] == "unavailable" and entry["attempts"] == link_state.MAX_ATTEMPTS
    assert stats["marked_unavailable"] == 1
    stats = run()
    assert len(downloads(fake)) == 3 and stats["unavailable"] == 1


def test_permanent_failure_unavailable_immediately(fake):
    a = vid(1)
    fake.ids = [a]
    fake.errors[a] = DELETED.format(a)
    stats = run()
    entry = states()[a]
    assert entry["status"] == "unavailable" and entry["attempts"] == 1
    assert entry["reason"] and stats["results"][0]["link_status"] == "unavailable"
    assert stats["marked_unavailable"] == 1 and a not in history()

    stats = run()
    assert len(downloads(fake)) == 1 and stats["unavailable"] == 1
    assert a in fake.history_seen

    del fake.errors[a]
    stats = run(force_update=True)               # MAJ forcée : les indisponibles sont retentés
    assert len(downloads(fake)) == 2 and stats["retried"] == 1 and stats["videos"] == 1
    assert a not in states()


def test_success_clears_state(fake):
    a = vid(1)
    write_states(lambda s: s.record_failure(a, "transient", "x",
                                            now=datetime.now() - timedelta(hours=1)))
    stats = run_import([item(a)])
    assert stats["retried"] == 1 and stats["videos"] == 1
    assert states() == {}


# ---------------------------------------------------------------- sonde

def test_probe_permanent_error_becomes_unavailable(fake):
    a, b = vid(1), vid(2)
    fake.ids = [a, b]
    fake.types[a] = None
    fake.probe_errors[a] = f"ERROR: [TikTok] {a}: This video is private"
    fake.types[b] = RuntimeError(DELETED.format(b))     # exception de sonde
    stats = run()
    assert downloads(fake) == []
    assert stats["unknown"] == 0 and stats["failed"] == 2 and stats["marked_unavailable"] == 2
    assert all(r["type"] == "unavailable" and not r["success"] for r in stats["results"])
    assert states()[a]["status"] == "unavailable" and states()[a]["reason"] == "Vidéo privée"
    assert states()[b]["status"] == "unavailable"
    assert history() == {}
    # Plus de « type inconnu » rejoué : le profil peut être marqué comme entièrement scanné
    assert stats["scan_complete"] is True
    stats = run()
    assert stats["unavailable"] == 2 and stats["results"] == []


def test_probe_transient_error_stays_unknown_with_attempt(fake):
    a = vid(1)
    fake.ids = [a]
    fake.types[a] = None
    fake.probe_errors[a] = "ERROR: [TikTok] 1: Unable to extract webpage video data"
    stats = run()
    assert stats["unknown"] == 1 and stats["failed"] == 0 and history() == {}
    assert states()[a]["status"] == "retry" and states()[a]["attempts"] == 1
    assert stats["scan_complete"] is False


# ---------------------------------------------------------------- sauvegarde de l'état

def test_state_saved_on_stop(fake):
    a, b = vid(1), vid(2)
    fake.ids = [a, b]
    fake.errors[a] = FORBIDDEN.format(a)
    stats = run(should_stop=lambda: len(downloads(fake)) >= 1)
    assert stats["stopped"] is True
    assert states()[a]["status"] == "retry"


def test_state_saved_on_exception(fake):
    a, b = vid(1), vid(2)
    fake.ids = [a, b]
    fake.errors[a] = FORBIDDEN.format(a)

    def boom(i):
        if i == b:
            raise KeyboardInterrupt
    fake.on_download = boom
    with pytest.raises(KeyboardInterrupt):
        run()
    assert states()[a]["status"] == "retry"


def test_state_saved_every_ten_items(fake):
    ids = [vid(n) for n in range(12)]
    fake.ids = ids
    fake.errors = {i: FORBIDDEN.format(i) for i in ids}
    seen_on_disk = {}

    def check(i):
        seen_on_disk[i] = len(states())
    fake.on_download = check
    run()
    assert seen_on_disk[ids[9]] == 0             # pas encore de sauvegarde
    assert seen_on_disk[ids[10]] == 10           # sauvegarde après 10 éléments traités
    assert len(states()) == 12                   # sauvegarde finale


# ---------------------------------------------------------------- arrêt incrémental

def _known_mix(start):
    """10 ids « connus » de catégories différentes à partir de start."""
    ids = [vid(start + n) for n in range(10)]
    for i in ids[:3]:
        main.save_to_history(USER, i, url=url(i))
    put_video_file(ids[3])
    put_video_file(ids[4])

    def mutate(s):
        s.ignore(ids[5])
        s.ignore(ids[6])
        s.record_failure(ids[7], "permanent", "x")
        s.record_failure(ids[8], "transient", "x")       # réessai non échu
        s.record_failure(ids[9], "transient", "x")
    write_states(mutate)
    return ids


def test_incremental_stop_counts_new_categories_as_known(fake):
    main.save_scan_state(USER, True)
    fake.use_filter = True
    known = _known_mix(0)
    new = vid(50)
    fake.ids = known + [new]
    stats = run()
    assert downloads(fake) == []                 # arrêt après 10 « connus » consécutifs
    assert stats["adopted"] == 2                 # adoptions faites en lot, sans le listing
    assert set(known) <= fake.history_seen and new not in fake.history_seen


def test_incremental_stop_reset_by_retry_due(fake):
    main.save_scan_state(USER, True)
    fake.use_filter = True
    known = _known_mix(0)
    due = vid(40)
    write_states(lambda s: s.record_failure(due, "transient", "x",
                                            now=datetime.now() - timedelta(hours=1)))
    new = vid(50)
    fake.ids = known[:5] + [due] + known[5:] + [new]
    stats = run()
    assert due not in fake.history_seen
    assert downloads(fake) == [("video", due), ("video", new)]
    assert stats["retried"] == 1 and stats["videos"] == 2


# ---------------------------------------------------------------- lecture seule

def test_no_folder_created_on_read(fake, monkeypatch):
    run_import([])
    assert not os.path.exists("downloads")

    def broken(*a, **k):
        raise RuntimeError("listing impossible")
        yield  # pragma: no cover
    monkeypatch.setattr(main, "get_video_links", broken)
    stats = run()
    assert stats["extraction_error"] and not os.path.exists("downloads")


# ---------------------------------------------------------------- parallélisme

def test_workers_2_state_not_corrupted(fake, tmp_path, monkeypatch):
    ids = [vid(n) for n in range(24)]
    fake.ids = ids
    for n, i in enumerate(ids):
        if n % 3 == 1:
            fake.errors[i] = FORBIDDEN.format(i)
        elif n % 3 == 2:
            fake.errors[i] = DELETED.format(i)
    seq = run()
    seq_states = {k: v["status"] for k, v in states().items()}
    seq_history = {k: v["success"] for k, v in history().items()}

    other = tmp_path / "parallel"
    other.mkdir()
    monkeypatch.chdir(other)
    par = run(workers=2)
    assert {k: v["status"] for k, v in states().items()} == seq_states
    assert {k: v["success"] for k, v in history().items()} == seq_history
    assert list(seq_states.values()).count("retry") == 8
    assert list(seq_states.values()).count("unavailable") == 8
    keys = ("videos", "failed", "skipped", "marked_unavailable", "retried")
    assert {k: par[k] for k in keys} == {k: seq[k] for k in keys}


# ---------------------------------------------------------------- statistiques

def test_stats_skipped_total_and_subcounters(fake):
    known_id, adopt_id, ign, unav, wait, due, new = (vid(n) for n in range(7))
    main.save_to_history(USER, known_id, url=url(known_id))
    put_video_file(adopt_id)

    def mutate(s):
        s.ignore(ign)
        s.record_failure(unav, "permanent", "x")
        s.record_failure(wait, "transient", "x")
        s.record_failure(due, "transient", "x", now=datetime.now() - timedelta(hours=1))
    write_states(mutate)
    items = [item(i) for i in (known_id, adopt_id, ign, unav, wait, due, new)]
    items += [item(new), {"id": "", "url": "x"}]
    events = []
    stats = run_import(items, progress=lambda e, d: events.append((e, d)))
    assert (stats["known"], stats["adopted"], stats["ignored"], stats["unavailable"],
            stats["retry_waiting"], stats["duplicate"], stats["invalid"]) == (1, 1, 1, 1, 1, 1, 1)
    assert stats["skipped"] == 7
    assert_skipped_consistent(stats)
    assert stats["retried"] == 1 and stats["videos"] == 2 and stats["processed"] == 2
    assert [r["category"] for r in stats["results"]] == ["retry_due", "new"]
    complete = events[-1]
    assert complete[0] == "complete"
    for key in SUBCOUNTERS + ("skipped", "retried", "marked_unavailable"):
        assert complete[1][key] == stats[key]
