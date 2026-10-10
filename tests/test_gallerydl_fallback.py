"""Tests du listing de profil : yt-dlp puis repli gallery-dl (aucun accès réseau)."""
import os
import subprocess
import sys
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


@pytest.fixture
def env(monkeypatch):
    FakeYDL.mode = "json_error"
    FakeYDL.entries = []
    monkeypatch.setattr(main.yt_dlp, "YoutubeDL", FakeYDL)
    state = SimpleNamespace(cmds=[], stdout="", returncode=0, stderr="", exc=None)

    def fake_run(cmd, **kwargs):
        state.cmds.append(cmd)
        if state.exc:
            raise state.exc
        return subprocess.CompletedProcess(cmd, state.returncode, state.stdout, state.stderr)

    monkeypatch.setattr(main.subprocess, "run", fake_run)
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


def test_gallerydl_timeout_raises(env):
    env.exc = subprocess.TimeoutExpired("gallery-dl", 300)
    with pytest.raises(RuntimeError):
        run()


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
