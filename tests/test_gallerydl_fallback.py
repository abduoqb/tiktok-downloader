"""Tests du listing de profil : yt-dlp puis repli gallery-dl (aucun accès réseau)."""
import os
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main
import orchestrator

USER = "someone"


def vurl(i, kind="video"):
    return f"https://www.tiktok.com/@{USER}/{kind}/{i}"


class FakeYDL:
    mode = "json_error"  # json_error | raise | entries | empty
    entries = []

    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download=False):
        mode = FakeYDL.mode
        if mode == "raise":
            raise Exception("boom Failed to parse JSON")
        if mode == "json_error":
            # ignoreerrors=True : l'erreur passe par le logger, l'entrée est vide
            self.opts["logger"].error("ERROR: Failed to parse JSON")
            return {"entries": []}
        if mode == "empty":
            return {"entries": [], "title": USER}
        return {"entries": list(FakeYDL.entries), "title": USER}


class FakeProc:
    """Faux Popen : stdout itérable, wait/poll/terminate/kill, returncode."""

    def __init__(self, state):
        self.state = state
        self.returncode = None
        self.terminated = False
        self.killed = False
        self._stop = threading.Event()
        self.stdout = self._gen()

    def _gen(self):
        st = self.state
        for chunk in st.stdout.splitlines(keepends=True):
            if st.delay:
                time.sleep(st.delay)
            if self._stop.is_set():
                return
            yield chunk
        if st.hang:  # n'émet plus rien, ne se termine que si on le tue
            self._stop.wait(30)
            return
        if st.stderr:
            yield st.stderr + "\n"
        self.returncode = st.returncode

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        if self.returncode is None:
            self._stop.wait(timeout)
            if self.returncode is None:
                raise subprocess.TimeoutExpired("gallery-dl", timeout)
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15
        self._stop.set()

    def kill(self):
        self.killed = True
        self.returncode = -9
        self._stop.set()


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # scan_state.json lu dans un downloads/ temporaire
    FakeYDL.mode = "json_error"
    FakeYDL.entries = []
    monkeypatch.setattr(main.yt_dlp, "YoutubeDL", FakeYDL)
    state = SimpleNamespace(cmds=[], procs=[], stdout="", returncode=0, stderr="", exc=None,
                            delay=0, hang=False)

    def fake_popen(cmd, **kwargs):
        state.cmds.append(cmd)
        state.kwargs = kwargs
        if state.exc:
            raise state.exc
        proc = FakeProc(state)
        state.procs.append(proc)
        return proc

    monkeypatch.setattr(main.subprocess, "Popen", fake_popen)
    return state


def listing(*ids, extra=()):
    lines = list(extra) + [vurl(i) for i in ids]
    return "\n".join(lines) + "\n"


def run(history=None, **kw):
    return list(main.get_video_links(USER, history or set(), **kw))


def test_fallback_when_ytdlp_logs_error(env):
    env.stdout = listing("3", "2", "1")
    out = run(cookies_file="c.txt")
    assert out == [{"url": vurl(i), "id": i} for i in ("3", "2", "1")]
    assert len(env.cmds) == 1 and env.cmds[0][0] == "gallery-dl"


def test_fallback_when_ytdlp_raises(env):
    FakeYDL.mode = "raise"
    env.stdout = listing("5")
    assert run() == [{"url": vurl("5"), "id": "5"}]


def test_fallback_logs_message(env):
    env.stdout = listing("5")
    logs = []
    run(callback_log=lambda m, level="info": logs.append(m))
    assert any("repli sur gallery-dl" in m for m in logs)


def test_parsing_ignores_noise_dedups_keeps_order(env):
    env.stdout = "\n".join([
        "https://p16-sign.tiktokcdn.com/avatar.jpeg",
        vurl("20"),
        "ytdl:" + vurl("10"),
        vurl("20"),
        "not a url",
        vurl("30", "photo"),
        "https://www.tiktok.com/@someone",
    ]) + "\n"
    out = run()
    assert [v["id"] for v in out] == ["20", "10", "30"]
    assert out[2]["url"] == vurl("30", "photo")


def test_cookies_and_limit_passed(env):
    env.stdout = listing("3", "2", "1")
    out = run(limit=2, cookies_file="c.txt")
    cmd = env.cmds[0]
    assert cmd[:3] == ["gallery-dl", "--cookies", "c.txt"]
    assert "--no-download" in cmd and "-N" in cmd and "-g" not in cmd
    assert cmd[cmd.index("--range") + 1] == "1-2"
    assert cmd[-1] == f"https://www.tiktok.com/@{USER}/posts"
    assert [v["id"] for v in out] == ["3", "2"]


def test_cookies_browser_passed(env):
    env.stdout = listing("1")
    run(cookies_browser="firefox")
    assert env.cmds[0][1:3] == ["--cookies-from-browser", "firefox"]


def test_range_accounts_for_history(env):
    env.stdout = listing("3", "2", "1")
    out = run(history={"3", "2"}, limit=1)
    assert env.cmds[0][env.cmds[0].index("--range") + 1] == "1-3"
    assert [v["id"] for v in out] == ["1"]


def test_history_skipped_and_incremental_stop(env):
    ids = [str(100 - i) for i in range(15)]
    env.stdout = listing("999", *ids)
    history = set(ids[:12])
    main.save_scan_state(USER, True)  # profil déjà entièrement scanné : mode incrémental actif
    out = run(history=history)
    assert [v["id"] for v in out] == ["999"]  # arrêt après 10 doublons consécutifs

    out = run(history=history, force_update=True)
    assert [v["id"] for v in out] == ["999", *ids[12:]]


def test_both_fail_raises(env):
    env.returncode = 1
    env.stderr = "[tiktok][error] nope"
    with pytest.raises(RuntimeError) as exc:
        run()
    assert "Listing impossible" in str(exc.value) and "cookies" in str(exc.value)


def test_gallerydl_missing_raises(env):
    env.exc = FileNotFoundError()
    with pytest.raises(RuntimeError, match="gallery-dl"):
        run()


def test_stall_timeout_kills_process(env, monkeypatch):
    monkeypatch.setattr(main, "GALLERYDL_STALL_TIMEOUT", 0.3)
    env.hang = True
    with pytest.raises(RuntimeError, match="ne répond plus depuis"):
        run()
    assert env.procs[0].terminated or env.procs[0].killed


def test_stall_after_entries_keeps_them(env, monkeypatch):
    monkeypatch.setattr(main, "GALLERYDL_STALL_TIMEOUT", 0.3)
    env.hang = True
    env.stdout = listing("2", "1")
    logs = []
    out = run(callback_log=lambda m, level="info": logs.append((level, m)))
    assert [v["id"] for v in out] == ["2", "1"]
    assert any(l == "error" and "interrompu après 2" in m for l, m in logs)
    assert env.procs[0].terminated


def test_stall_error_mentions_entries_already_listed(env, monkeypatch):
    monkeypatch.setattr(main, "GALLERYDL_STALL_TIMEOUT", 0.3)
    env.hang = True
    env.stdout = listing("2", "1")
    gen = main._gallerydl_entries("https://www.tiktok.com/@x", None, 0, None, None)
    assert next(gen)["id"] == "2" and next(gen)["id"] == "1"
    with pytest.raises(RuntimeError, match="2 élément"):
        next(gen)


def test_total_timeout_kills_process(env, monkeypatch):
    monkeypatch.setattr(main, "GALLERYDL_LIST_TIMEOUT", 0.4)
    env.delay = 0.1  # sortie continue (pas d'inactivité) mais jamais finie
    env.stdout = listing(*[str(i) for i in range(100)])
    gen = main._gallerydl_entries("https://www.tiktok.com/@x", None, 0, None, None)
    got = []
    with pytest.raises(RuntimeError, match="délai total"):
        for e in gen:
            got.append(e)
    assert 0 < len(got) < 100
    assert env.procs[0].terminated or env.procs[0].killed


def test_progressive_output(env):
    env.delay = 0.05
    env.stdout = listing("3", "2", "1")
    gen = main._gallerydl_entries("https://www.tiktok.com/@x", None, 0, None, None)
    first = next(gen)  # produit avant la fin du processus
    assert first == {"id": "3", "url": vurl("3")}
    assert env.procs[0].returncode is None
    assert [e["id"] for e in gen] == ["2", "1"]


def test_early_close_terminates_process(env):
    env.hang = True
    env.stdout = listing("3", "2", "1")
    gen = main._gallerydl_entries("https://www.tiktok.com/@x", None, 0, None, None)
    assert next(gen)["id"] == "3"
    gen.close()
    assert env.procs[0].terminated or env.procs[0].killed
    assert not any(t.name == "gallerydl-reader" and t.is_alive() for t in threading.enumerate())


def test_limit_stops_and_terminates_process(env):
    env.hang = True
    env.stdout = listing("3", "2", "1")
    out = run(limit=1)
    assert [v["id"] for v in out] == ["3"]
    assert env.procs[0].terminated


def test_nonzero_exit_after_entries_is_not_an_error(env):
    env.stdout = listing("2", "1")
    env.returncode = 1
    env.stderr = "[tiktok][error] partial"
    assert [v["id"] for v in run()] == ["2", "1"]


def test_nonzero_exit_reports_last_error_line(env):
    env.returncode = 4
    env.stderr = "[tiktok][error] nope"
    with pytest.raises(RuntimeError) as exc:
        run()
    assert "code 4" in str(exc.value) and "[tiktok][error] nope" in str(exc.value)


def test_stderr_merged_into_stdout(env):
    env.stdout = listing("1")
    run()
    assert env.kwargs["stderr"] == subprocess.STDOUT
    assert env.kwargs["stdout"] == subprocess.PIPE


def test_empty_profile_is_not_an_error(env):
    FakeYDL.mode = "empty"
    assert run() == []
    assert env.cmds == []  # pas de repli : yt-dlp a listé sans erreur


def test_ytdlp_success_no_fallback(env):
    FakeYDL.mode = "entries"
    FakeYDL.entries = [{"id": "1", "url": vurl("1")}, {"id": "2", "url": vurl("2")}]
    assert [v["id"] for v in run()] == ["1", "2"]
    assert env.cmds == []


def test_gallerydl_empty_listing_ok(env):
    env.stdout = "https://example.com/avatar.jpg\n"
    assert run() == []


def test_orchestrator_reports_extraction_error(env, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    env.returncode = 1
    logs = []
    stats = orchestrator.run_download(USER, log=lambda m, level="info": logs.append((level, m)),
                                      min_sleep=0, max_sleep=0)
    assert "Listing impossible" in stats["extraction_error"]
    assert any(level == "error" and "Listing impossible" in m for level, m in logs)


def test_orchestrator_no_error_on_empty_profile(env, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    FakeYDL.mode = "empty"
    stats = orchestrator.run_download(USER, log=lambda *a: None, min_sleep=0, max_sleep=0)
    assert stats["extraction_error"] is None


def test_slow_consumer_does_not_trigger_total_timeout(env, monkeypatch):
    """Le temps du consommateur (téléchargements entre deux entrées) n'est pas compté."""
    monkeypatch.setattr(main, "GALLERYDL_LIST_TIMEOUT", 0.3)
    monkeypatch.setattr(main, "GALLERYDL_STALL_TIMEOUT", 0.3)
    env.stdout = listing("3", "2", "1")
    gen = main._gallerydl_entries("https://www.tiktok.com/@x", None, 0, None, None)
    got = []
    for entry in gen:
        got.append(entry["id"])
        time.sleep(0.5)  # consommateur lent : dépasse largement les deux délais cumulés
    assert got == ["3", "2", "1"]
    assert not any(t.name == "gallerydl-reader" and t.is_alive() for t in threading.enumerate())


def test_slow_consumer_does_not_block_reader_thread(env):
    """La file est non bornée : le lecteur vide tout le pipe pendant que le consommateur dort."""
    env.stdout = listing(*[str(i) for i in range(200)])
    gen = main._gallerydl_entries("https://www.tiktok.com/@x", None, 0, None, None)
    assert next(gen)["id"] == "0"
    for reader in [t for t in threading.enumerate() if t.name == "gallerydl-reader"]:
        reader.join(2)  # le lecteur finit sans que le consommateur n'avance
        assert not reader.is_alive()
    assert [e["id"] for e in gen] == [str(i) for i in range(1, 200)]
