import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import preflight


def test_returns_list():
    assert isinstance(preflight.check_environment(), list)


def test_missing_cookies(tmp_path):
    res = preflight.check_environment(str(tmp_path / "absent.txt"))
    assert any("cookies" in p.lower() for p in res)


def test_old_cookies(tmp_path):
    f = tmp_path / "c.txt"
    f.write_text("x")
    old = time.time() - 40 * 86400
    os.utime(f, (old, old))
    assert any("jours" in p for p in preflight.check_environment(str(f)))


def test_fresh_cookies_no_cookie_problem(tmp_path):
    f = tmp_path / "c.txt"
    f.write_text("x")
    assert not any("cookies" in p.lower() for p in preflight.check_environment(str(f)))
