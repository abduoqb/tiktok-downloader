"""Tests de la CLI `main.py --links-file` (run_import mocké, aucun réseau)."""
import io
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main  # noqa: E402
import orchestrator  # noqa: E402
import preflight  # noqa: E402


def U(user, vid):
    return f"https://www.tiktok.com/@{user}/video/{vid}"


STATS = {"videos": 1, "slideshows": 0, "downloaded": 1, "failed": 0, "unknown": 0,
         "size_mb": 0.5, "duration_s": 1.0}


@pytest.fixture
def cli(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(preflight, "check_environment", lambda cookies=None: [])
    calls = []

    def fake_import(username, items, **kwargs):
        calls.append((username, items, kwargs))
        return dict(STATS)

    monkeypatch.setattr(orchestrator, "run_import", fake_import)

    def run(*argv):
        monkeypatch.setattr(sys, "argv", ["main.py", *argv])
        try:
            main.main()
        except SystemExit as e:
            return e.code
        return 0

    run.calls = calls
    return run


def _file(tmp_path, text, name="liens.txt"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_links_file_groups_by_pseudo_and_forwards_options(cli, tmp_path):
    path = _file(tmp_path, "\n".join([U("alice", 1), U("bob", 2), U("alice", 3)]))
    code = cli("--links-file", path, "--min-sleep", "1", "--max-sleep", "3",
               "--cookies-file", "c.txt", "--cookies-browser", "firefox", "--force-update")
    assert code == 0
    assert [(c[0], [i["id"] for i in c[1]]) for c in cli.calls] == [
        ("alice", ["1", "3"]), ("bob", ["2"])]
    kw = cli.calls[0][2]
    assert kw["min_sleep"] == 1 and kw["max_sleep"] == 3
    assert kw["cookies_file"] == "c.txt" and kw["cookies_browser"] == "firefox"
    assert kw["force_update"] is True


def test_positional_pseudo_overrides_grouping(cli, tmp_path):
    path = _file(tmp_path, U("alice", 1) + "\n" + U("bob", 2))
    assert cli("carol", "--links-file", path) == 0
    assert len(cli.calls) == 1 and cli.calls[0][0] == "carol" and len(cli.calls[0][1]) == 2


def test_positional_pseudo_validated(cli, tmp_path):
    path = _file(tmp_path, U("alice", 1))
    assert cli("../evil", "--links-file", path) == 1
    assert cli.calls == []


def test_stdin_dash(cli, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO(U("zed", 5) + "\n"))
    assert cli("--links-file", "-") == 0
    assert cli.calls[0][0] == "zed"


def test_no_valid_link_exits_1(cli, tmp_path, capsys):
    path = _file(tmp_path, "rien\nhttps://vm.tiktok.com/abc/\n")
    assert cli("--links-file", path) == 1
    assert cli.calls == []
    out = capsys.readouterr().out
    assert "aucun lien" in out.lower() and "ignoré" in out


def test_missing_file_exits_1(cli, tmp_path):
    assert cli("--links-file", str(tmp_path / "absent.txt")) == 1
    assert cli.calls == []


def test_bom_file_ok(cli, tmp_path):
    path = tmp_path / "bom.txt"
    path.write_bytes(b"\xef\xbb\xbf" + U("alice", 1).encode() + b"\r\n")
    assert cli("--links-file", str(path)) == 0
    assert cli.calls[0][1][0]["id"] == "1"


def test_pseudo_still_required_without_links_file(cli, capsys):
    assert cli() == 2
    assert "username_or_url" in capsys.readouterr().err


def test_default_sleep_values(cli, tmp_path):
    cli("--links-file", _file(tmp_path, U("a", 1)))
    kw = cli.calls[0][2]
    assert (kw["min_sleep"], kw["max_sleep"]) == (2, 6)
