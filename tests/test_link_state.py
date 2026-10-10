"""Tests de link_state (aucun reseau, uniquement tmp_path)."""
import json
import os
import sys
import threading
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import link_state  # noqa: E402
from link_state import LinkState, STATE_FILENAME, RETRY_DELAYS_S, MAX_ATTEMPTS  # noqa: E402

NOW = datetime(2025, 1, 1, 12, 0, 0)


def test_constants():
    assert RETRY_DELAYS_S == (600, 3600, 21600)
    assert MAX_ATTEMPTS == 3
    assert STATE_FILENAME == "link_state.json"


def test_missing_file_is_empty(tmp_path):
    st = LinkState.load(str(tmp_path / "absent"))
    assert st.items() == {} and not st.dirty and not st.recovered_from_corruption
    st.save()
    assert not (tmp_path / "absent").exists()


def test_full_cycle(tmp_path):
    d = str(tmp_path / "u")
    st = LinkState.load(d)
    st.ignore(1, "pas interessant")
    st.mark_unavailable("2", "prive", "err")
    st.record_failure("3", "transient", "timeout", now=NOW)
    assert st.dirty
    st.save()
    assert not st.dirty
    st2 = LinkState.load(d)
    assert st2.status("1") == "ignored"
    assert st2.status("2") == "unavailable"
    assert st2.status("3") == "retry"
    assert st2.get("1")["reason"] == "pas interessant"
    assert st2.list_by_status("retry") == ["3"]
    with open(os.path.join(d, STATE_FILENAME), encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["version"] == 1 and set(data["items"]) == {"1", "2", "3"}
    assert st2.restore(1) is True
    assert st2.status("1") is None
    assert st2.restore(1) is False


def test_backoff_then_unavailable(tmp_path):
    st = LinkState.load(str(tmp_path))
    t = NOW
    for n, delay in enumerate(RETRY_DELAYS_S[:2], start=1):
        assert st.record_failure("9", "transient", "e", now=t) == "retry"
        e = st.get("9")
        assert e["attempts"] == n
        assert datetime.fromisoformat(e["next_retry"]) == t + timedelta(seconds=delay)
    assert st.record_failure("9", "transient", "e", now=t) == "unavailable"
    e = st.get("9")
    assert e["attempts"] == 3 and e["reason"] == "tentatives épuisées"
    assert e["next_retry"] is None


def test_first_delay_is_600(tmp_path):
    st = LinkState.load(str(tmp_path))
    st.record_failure("1", "transient", now=NOW)
    assert st.is_retry_due("1", now=NOW) is False
    assert st.is_retry_due("1", now=NOW + timedelta(seconds=600)) is True
    assert st.is_retry_due("zzz") is False


def test_permanent(tmp_path):
    st = LinkState.load(str(tmp_path))
    st.record_failure("1", "permanent", "video supprimee", now=NOW)
    assert st.status("1") == "unavailable"


def test_restore_keeps_unavailable_and_clear_keeps_ignored(tmp_path):
    st = LinkState.load(str(tmp_path))
    st.mark_unavailable("1", "x")
    st.ignore("2")
    assert st.restore("1") is False and st.status("1") == "unavailable"
    st.clear("2")
    assert st.status("2") == "ignored"
    st.clear("1")
    assert st.status("1") is None
    st.record_failure("2", "permanent")
    assert st.status("2") == "ignored"


def test_error_truncated(tmp_path):
    st = LinkState.load(str(tmp_path))
    st.record_failure("1", "permanent", "x" * 1000)
    assert len(st.get("1")["last_error"]) == 300


def test_save_noop_when_clean_and_atomic(tmp_path, monkeypatch):
    st = LinkState.load(str(tmp_path))
    assert st.save() is False
    st.ignore("1")
    st.save()
    assert os.listdir(tmp_path) == [STATE_FILENAME]
    st.ignore("2")

    def fail(*a, **k):
        raise OSError("disque plein")
    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError):
        st.save()
    monkeypatch.undo()
    assert os.listdir(tmp_path) == [STATE_FILENAME]
    assert st.dirty
    assert set(LinkState.load(str(tmp_path)).items()) == {"1"}


@pytest.mark.parametrize("content", ["{pas du json", "[1, 2]", '{"items": []}'])
def test_corruption_recovered(tmp_path, content):
    p = tmp_path / STATE_FILENAME
    p.write_text(content, encoding="utf-8")
    st = LinkState.load(str(tmp_path))
    assert st.recovered_from_corruption is True
    assert st.items() == {}
    names = os.listdir(tmp_path)
    assert STATE_FILENAME not in names
    corrupt = [n for n in names if n.startswith("link_state.json.corrupt-")]
    assert len(corrupt) == 1
    assert (tmp_path / corrupt[0]).read_text(encoding="utf-8") == content


def test_thread_safety(tmp_path):
    st = LinkState.load(str(tmp_path))

    def work(k):
        for i in range(50):
            st.record_failure(f"{k}-{i}", "transient", now=NOW)
            st.ignore(f"i{k}-{i}")
            st.items()
    threads = [threading.Thread(target=work, args=(k,)) for k in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(st.items()) == 800
    st.save()
    assert len(LinkState.load(str(tmp_path)).items()) == 800


def test_str_int_normalisation(tmp_path):
    st = LinkState.load(str(tmp_path))
    st.ignore(123)
    assert st.status("123") == "ignored" and st.status(123) == "ignored"
    assert "123" in st.items()
    assert st.restore("123") is True
