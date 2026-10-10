"""Index des fichiers d'un profil en un seul parcours de dossier (os.scandir).

Module feuille : bibliotheque standard uniquement.
"""
import os
import re
from dataclasses import dataclass, field

VIDEO_RE = re.compile(
    r'^(?:(?:\d{8}|NA)_)?(?:.+?_)?(\d{15,20})\.(mp4|webm|mkv|mov)$', re.IGNORECASE)
IMAGE_RE = re.compile(
    r'_(\d{15,20})_img=(\d+)\.(jpg|jpeg|png|webp)$', re.IGNORECASE)
FOLDER_RE = re.compile(r'(?:^|_)(\d{15,20})$')
IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.webp')

_FRAGMENT_RE = re.compile(r'\.f\d+\.', re.IGNORECASE)
_TEMP_SUFFIXES = ('.tmp', '.part', '.ytdl', '.backup', '.json')
_SERVICE_NAMES = ('scan_state.json', 'link_state.json')


@dataclass
class DiskEntry:
    """Un element (video ou slideshow) present sur le disque."""
    id: str
    kind: str  # 'video' | 'slideshow'
    files: list = field(default_factory=list)
    size: int = 0
    image_count: int = 0
    mtime: float = 0.0


def _is_ignored_name(name):
    """Vrai pour les fichiers temporaires, partiels ou de service."""
    low = name.lower()
    if low.startswith('.') or low in _SERVICE_NAMES:
        return True
    if low.endswith(_TEMP_SUFFIXES) or '.temp.' in low or _FRAGMENT_RE.search(low):
        return True
    return False


def parse_filename(name):
    """Retourne (id, kind) pour un nom de fichier video ou image de slideshow, sinon None.

    L'id est ancre en fin de nom : les pseudos peuvent contenir '_' et '.'.
    """
    m = IMAGE_RE.search(name)
    if m:
        return m.group(1), 'slideshow'
    m = VIDEO_RE.match(name)
    if m:
        return m.group(1), 'video'
    return None


def _add(entries, item_id, kind, rel_name, size, mtime, images=0):
    entry = entries.get(item_id)
    if entry is None:
        entry = DiskEntry(id=item_id, kind=kind)
        entries[item_id] = entry
    elif kind == 'video':
        entry.kind = 'video'
    entry.files.append(rel_name)
    entry.size += size
    entry.image_count += images
    if mtime > entry.mtime:
        entry.mtime = mtime


def scan_profile_dir(user_dir):
    """Indexe le dossier d'un profil : {id: DiskEntry}. Dossier absent => {} (non cree)."""
    entries = {}
    user_name = os.path.basename(os.path.normpath(str(user_dir))).lower()
    videos_txt = f'{user_name}_videos.txt'
    try:
        it = os.scandir(user_dir)
    except OSError:
        return entries
    with it:
        for de in it:
            name = de.name
            try:
                if de.is_dir(follow_symlinks=False):
                    _scan_legacy_folder(de, entries)
                    continue
                if _is_ignored_name(name) or name.lower() == videos_txt:
                    continue
                parsed = parse_filename(name)
                if parsed is None:
                    continue
                st = de.stat()
                if st.st_size <= 0:
                    continue
                item_id, kind = parsed
                is_img = kind == 'slideshow'
                _add(entries, item_id, kind, name, st.st_size, st.st_mtime,
                     images=1 if is_img else 0)
            except OSError:
                continue
    return entries


def _scan_legacy_folder(folder, entries):
    """Ancien slideshow : dossier '..._<id>' contenant les images."""
    m = FOLDER_RE.search(folder.name)
    if not m:
        return
    item_id = m.group(1)
    try:
        sub = os.scandir(folder.path)
    except OSError:
        return
    with sub:
        for de in sub:
            low = de.name.lower()
            if _is_ignored_name(de.name) or not low.endswith(IMAGE_EXTS):
                continue
            try:
                if not de.is_file():
                    continue
                st = de.stat()
            except OSError:
                continue
            if st.st_size <= 0:
                continue
            _add(entries, item_id, 'slideshow', f'{folder.name}/{de.name}',
                 st.st_size, st.st_mtime, images=1)


def ids_on_disk(user_dir):
    """Ensemble des ids presents sur le disque pour ce profil."""
    return set(scan_profile_dir(user_dir))
