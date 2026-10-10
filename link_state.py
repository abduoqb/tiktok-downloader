"""Etats persistants par identifiant dans <dossier>/link_state.json.

Module feuille : bibliotheque standard uniquement.
Format : {"version": 1, "items": {"<id>": {"status", "attempts", "last_error",
"reason", "last_attempt", "next_retry"}}}
"""
import copy
import json
import os
import tempfile
import threading
from datetime import datetime, timedelta

STATE_FILENAME = "link_state.json"
RETRY_DELAYS_S = (600, 3600, 21600)
MAX_ATTEMPTS = 3
STATUSES = ("ignored", "unavailable", "retry")
MAX_ERROR_LEN = 300


def _iso(dt):
    return dt.isoformat(timespec="seconds")


def _parse_iso(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _clip(text):
    return str(text or "")[:MAX_ERROR_LEN]


class LinkState:
    """Etats ignored / unavailable / retry d'un profil, avec sauvegarde atomique."""

    def __init__(self, user_dir):
        self.user_dir = str(user_dir)
        self.path = os.path.join(self.user_dir, STATE_FILENAME)
        self._items = {}
        # id -> 'set' | 'delete' : seules ces cles sont reappliquees a l'ecriture
        self._touched = {}
        self._lock = threading.RLock()
        self.dirty = False
        self.recovered_from_corruption = False

    @classmethod
    def load(cls, user_dir):
        """Charge l'etat ; un fichier corrompu est renomme en .corrupt-<horodatage>."""
        state = cls(user_dir)
        try:
            with open(state.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError:
            return state
        except (OSError, ValueError):
            state._quarantine()
            return state
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, dict):
            state._quarantine()
            return state
        for key, raw in items.items():
            if not isinstance(raw, dict) or raw.get("status") not in STATUSES:
                continue
            attempts = raw.get("attempts", 0)
            state._items[str(key)] = {
                "status": raw["status"],
                "attempts": attempts if isinstance(attempts, int) else 0,
                "last_error": _clip(raw.get("last_error")),
                "reason": str(raw.get("reason") or ""),
                "last_attempt": raw.get("last_attempt"),
                "next_retry": raw.get("next_retry"),
            }
        return state

    def _quarantine(self):
        self.recovered_from_corruption = True
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        target = f"{self.path}.corrupt-{stamp}"
        try:
            os.replace(self.path, target)
        except OSError:
            pass

    # Lecture

    def get(self, item_id):
        with self._lock:
            entry = self._items.get(str(item_id))
            return dict(entry) if entry else None

    def status(self, item_id):
        with self._lock:
            entry = self._items.get(str(item_id))
            return entry["status"] if entry else None

    def items(self):
        with self._lock:
            return copy.deepcopy(self._items)

    def list_by_status(self, status):
        with self._lock:
            return [k for k, v in self._items.items() if v["status"] == status]

    def is_retry_due(self, item_id, now=None):
        now = now or datetime.now()
        with self._lock:
            entry = self._items.get(str(item_id))
            if not entry or entry["status"] != "retry":
                return False
            due = _parse_iso(entry.get("next_retry"))
            return due is None or due <= now

    # Ecriture

    def _set(self, item_id, entry):
        self._items[item_id] = entry
        self._touched[item_id] = 'set'
        self.dirty = True

    def ignore(self, item_id, reason=""):
        key = str(item_id)
        with self._lock:
            self._set(key, {"status": "ignored", "attempts": 0, "last_error": "",
                            "reason": str(reason or ""),
                            "last_attempt": _iso(datetime.now()), "next_retry": None})

    def restore(self, item_id):
        """Retire UNIQUEMENT un etat 'ignored'. Retourne True si retire."""
        key = str(item_id)
        with self._lock:
            entry = self._items.get(key)
            if entry and entry["status"] == "ignored":
                del self._items[key]
                self._touched[key] = 'delete'
                self.dirty = True
                return True
            return False

    def mark_unavailable(self, item_id, reason, error=""):
        key = str(item_id)
        with self._lock:
            old = self._items.get(key)
            if old and old["status"] == "ignored":
                return
            self._set(key, {"status": "unavailable",
                            "attempts": old["attempts"] if old else 0,
                            "last_error": _clip(error), "reason": str(reason or ""),
                            "last_attempt": _iso(datetime.now()), "next_retry": None})

    def record_failure(self, item_id, kind, message="", now=None):
        """Enregistre un echec ('transient' ou 'permanent'). Retourne le nouveau statut."""
        key = str(item_id)
        now = now or datetime.now()
        with self._lock:
            old = self._items.get(key)
            if old and old["status"] == "ignored":
                return "ignored"
            attempts = (old["attempts"] if old else 0) + 1
            entry = {"status": "unavailable", "attempts": attempts,
                     "last_error": _clip(message), "reason": "",
                     "last_attempt": _iso(now), "next_retry": None}
            if kind == "permanent":
                entry["reason"] = "echec permanent"
            elif attempts >= MAX_ATTEMPTS:
                entry["reason"] = "tentatives épuisées"
            else:
                delay = RETRY_DELAYS_S[min(attempts - 1, len(RETRY_DELAYS_S) - 1)]
                entry["status"] = "retry"
                entry["next_retry"] = _iso(now + timedelta(seconds=delay))
            self._set(key, entry)
            return entry["status"]

    def clear(self, item_id):
        """Retire un etat retry/unavailable (apres succes), jamais un 'ignored'."""
        key = str(item_id)
        with self._lock:
            entry = self._items.get(key)
            if entry and entry["status"] in ("retry", "unavailable"):
                del self._items[key]
                self._touched[key] = 'delete'
                self.dirty = True
                return True
            return False

    def _read_disk_items(self):
        """Etat actuellement sur disque (tolerant : absent/illisible => {})."""
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return {}
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, dict):
            return {}
        return {str(k): v for k, v in items.items()
                if isinstance(v, dict) and v.get("status") in STATUSES}

    def save(self):
        """Ecriture atomique ; sans effet si rien n'a change.

        Fusion a l'ecriture : le fichier est relu et seules les cles modifiees par CETTE
        instance sont reappliquees. Un etat 'ignored' ecrit entre-temps par une autre
        instance (suppression depuis la page profil pendant un import) n'est donc jamais
        perdu, et jamais ecrase par un echec/une indisponibilite de cette instance.
        """
        with self._lock:
            if not self.dirty:
                return False
            os.makedirs(self.user_dir, exist_ok=True)
            merged = self._read_disk_items()
            for key, op in self._touched.items():
                on_disk = merged.get(key)
                if op == "delete":
                    merged.pop(key, None)
                    continue
                mine = self._items.get(key)
                if mine is None:
                    continue
                if on_disk and on_disk.get("status") == "ignored" and mine["status"] != "ignored":
                    continue  # une ignorance posee ailleurs prime sur un retry/unavailable
                merged[key] = mine
            payload = {"version": 1, "items": merged}
            fd, tmp_path = tempfile.mkstemp(dir=self.user_dir, prefix=".link_state_",
                                            suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(payload, fh, indent=2, ensure_ascii=False)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp_path, self.path)
            except BaseException:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
                raise
            # La vue en memoire rejoint l'etat fusionne (ignorances posees ailleurs incluses)
            self._items = {k: dict(v) for k, v in merged.items()}
            self._touched = {}
            self.dirty = False
            return True
