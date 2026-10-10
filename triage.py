"""Classification pure (sans E/S) des liens avant telechargement.

Module feuille : bibliotheque standard uniquement.
"""
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime

CATEGORIES = ('invalid', 'duplicate', 'downloaded', 'adopt', 'ignored',
              'unavailable', 'retry_due', 'retry_waiting', 'new')


@dataclass
class TriageContext:
    """Donnees deja chargees servant a classer les identifiants."""
    history_success: set = field(default_factory=set)
    history_failed: set = field(default_factory=set)
    disk: object = field(default_factory=dict)   # dict[str, DiskEntry] ou set d'ids
    state: dict = field(default_factory=dict)    # id -> entree de LinkState.items()


@dataclass
class TriageResult:
    counts: dict = field(default_factory=lambda: {c: 0 for c in CATEGORIES})
    by_category: dict = field(default_factory=lambda: {c: [] for c in CATEGORIES})
    to_process: list = field(default_factory=list)
    to_adopt: list = field(default_factory=list)
    total: int = 0

    def plan_hash(self, destination, force_update):
        """sha1 stable du plan : destination, force_update, ids a traiter et a adopter."""
        payload = json.dumps(
            [str(destination).lower(), bool(force_update),
             [str(i['id']) for i in self.to_process],
             [str(i['id']) for i, _ in self.to_adopt]],
            ensure_ascii=False)
        return hashlib.sha1(payload.encode('utf-8')).hexdigest()

    def sample(self, n=20):
        """Premiers n elements (id, url) de chaque categorie, pour l'interface."""
        return {c: [(str(i.get('id')), i.get('url')) for i in self.by_category[c][:n]]
                for c in CATEGORIES}


def _parse_dt(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def classify_id(item_id, ctx, *, force_update=False, now=None):
    """Categorie d'un identifiant, selon l'ordre de priorite documente."""
    key = str(item_id)
    now = now or datetime.now()
    if key in ctx.history_success:
        return 'downloaded'
    entry = ctx.state.get(key) if ctx.state else None
    status = entry.get('status') if entry else None
    if status == 'ignored':
        return 'ignored'
    if key in ctx.disk:
        return 'adopt'
    if status == 'unavailable':
        return 'retry_due' if force_update else 'unavailable'
    if status == 'retry':
        due = _parse_dt(entry.get('next_retry'))
        if force_update or due is None or due <= now:
            return 'retry_due'
        return 'retry_waiting'
    if key in ctx.history_failed:
        return 'retry_due'
    return 'new'


def classify_links(items, ctx, *, force_update=False, now=None):
    """Classe une liste d'items {id, url, ...} et retourne un TriageResult."""
    now = now or datetime.now()
    result = TriageResult()
    seen = set()
    for item in items:
        raw_id = item.get('id') if isinstance(item, dict) else None
        url = item.get('url') if isinstance(item, dict) else None
        key = str(raw_id).strip() if raw_id is not None else ''
        if not key or not url:
            cat = 'invalid'
        elif key in seen:
            cat = 'duplicate'
        else:
            seen.add(key)
            cat = classify_id(key, ctx, force_update=force_update, now=now)
        result.by_category[cat].append(item)
        result.counts[cat] += 1
        result.total += 1
        if cat in ('new', 'retry_due'):
            result.to_process.append(item)
        elif cat == 'adopt':
            disk = ctx.disk
            result.to_adopt.append((item, disk.get(key) if isinstance(disk, dict) else None))
    return result


def estimate_seconds(count, min_sleep, max_sleep, per_item_s=6.0):
    """Duree estimee : pauses moyennes entre elements + temps par element."""
    if count <= 0:
        return 0
    avg = (float(min_sleep) + float(max_sleep)) / 2.0
    return int(round((count - 1) * avg + count * per_item_s))
