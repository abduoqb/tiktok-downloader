"""
Import d'une liste de liens de vidéos TikTok (module feuille, stdlib seule).

Filet de sécurité quand TikTok bloque le listing automatique d'un profil : l'utilisateur
exporte les liens depuis son navigateur connecté (static/js/export_links.js), puis les colle
dans l'interface web ou les donne à `main.py --links-file`.

parse_links(text) extrait d'un texte libre toutes les URLs tiktok.com/@<pseudo>/(video|photo)/<id>,
les normalise (https://www.tiktok.com/@pseudo/video/ID, sans paramètres), dédoublonne en gardant
l'ordre et les groupe par pseudo.

Ce module n'importe ni main ni web_app. Les mêmes règles sont répliquées en JavaScript dans
templates/index.html (compteur en direct) : garder LINK_PATTERN synchronisé.
"""
import os
import re

# Pseudo accepté : lettres/chiffres/_/./- uniquement (aucun séparateur de chemin possible).
USERNAME_RE = re.compile(r'^[\w.\-]+$')
MAX_USERNAME_LEN = 64

# Le motif accepte l'URL avec ou sans schéma, avec ou sans www./m., et ignore la suite
# (?query, #fragment, /). L'id doit être suivi d'un caractère non alphanumérique.
LINK_PATTERN = (r'(?<![\w.\-@/])(?:https?://)?(?:www\.|m\.)?tiktok\.com/@([\w.\-]+)'
                r'/(video|photo)/(\d+)(?!\w)')
_LINK_RE = re.compile(LINK_PATTERN, re.IGNORECASE)
# Liens courts : impossibles à résoudre sans réseau, donc ignorés (mais comptés)
_SHORT_RE = re.compile(r'(?<![\w.\-])(?:vm|vt)\.tiktok\.com/\S+', re.IGNORECASE)

MAX_INVALID_REPORTED = 5
MAX_INVALID_LINE_LEN = 120


def is_valid_username(name):
    """Pseudo sûr pour un nom de dossier : [\\w.\\-]+, pas uniquement des points, <= 64 car."""
    return bool(
        isinstance(name, str)
        and 0 < len(name) <= MAX_USERNAME_LEN
        and USERNAME_RE.match(name)
        and name.strip('.') != ''      # refuse « . » et « .. »
    )


def list_folders(downloads_dir="downloads"):
    """Noms des dossiers existants de downloads_dir (liste vide si absent). Lecture seule."""
    try:
        return [e for e in os.listdir(downloads_dir)
                if os.path.isdir(os.path.join(downloads_dir, e))]
    except OSError:
        return []


def resolve_folder(original, existing_folders=None):
    """Nom d'un dossier existant égal à `original` sans tenir compte de la casse (évite deux
    dossiers « Bob » / « bob »), sinon `original`. Fonction pure."""
    low = original.lower()
    for entry in existing_folders or ():
        if entry.lower() == low:
            return entry
    return original


def folder_name(original, downloads_dir="downloads"):
    """Comme resolve_folder, en listant le dossier `downloads_dir`."""
    return resolve_folder(original, list_folders(downloads_dir))


class _Link(dict):
    """Lien parsé : un dict ordinaire, avec sa position globale d'apparition (`pos`)."""
    pos = 0


def build_plan(groups, *, mode='by_author', destination=None, existing_folders=None):
    """Plan d'import : liste ordonnée de (dossier, éléments). Fonction pure (aucune E/S).

    mode 'by_author' : un dossier par pseudo, dans l'ordre d'apparition des pseudos.
    mode 'single'    : tous les liens, dans l'ordre d'apparition global, vers UN dossier
                       (`destination`, obligatoire).
    Les noms de dossier suivent la casse d'un dossier existant (`existing_folders`).
    Lève ValueError si le mode est inconnu ou si un pseudo / la destination est invalide.
    """
    if mode == 'single':
        if not is_valid_username(destination):
            raise ValueError('destination invalide')
        merged = [item for items in groups.values() for item in items]
        merged.sort(key=lambda item: getattr(item, 'pos', 0))  # tri stable
        return [(resolve_folder(destination, existing_folders), merged)] if merged else []
    if mode != 'by_author':
        raise ValueError(f'mode inconnu : {mode!r}')
    plan = []
    for items in groups.values():
        if not items:
            continue
        name = items[0]['username']
        if not is_valid_username(name):
            raise ValueError('pseudo invalide')
        plan.append((resolve_folder(name, existing_folders), items))
    return plan


def normalize_url(username, kind, video_id):
    return f"https://www.tiktok.com/@{username}/{kind.lower()}/{video_id}"


def parse_links(text):
    """Analyse un texte libre.

    Returns:
        (groups, report)
        groups : {pseudo_en_minuscules: [{"id", "url", "username"}, ...]} dans l'ordre
            d'apparition ; "username" est le pseudo tel qu'écrit dans la première URL du
            groupe (casse d'origine, utile pour le nom de dossier).
        report : {"ignored": nombre de liens courts vm./vt.tiktok.com ignorés,
                  "invalid": premières lignes sans lien exploitable (<= 5, tronquées),
                  "invalid_count": nombre total de telles lignes,
                  "duplicates": doublons supprimés,
                  "total": nombre de liens valides conservés}
    """
    groups = {}
    seen_ids = set()
    position = 0
    report = {"ignored": 0, "invalid": [], "invalid_count": 0, "duplicates": 0, "total": 0}
    if not isinstance(text, str):
        return groups, report

    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip('﻿')
        if not line or line.startswith('#'):
            continue
        report["ignored"] += len(_SHORT_RE.findall(line))
        found = False
        for match in _LINK_RE.finditer(line):
            username, kind, video_id = match.group(1), match.group(2), match.group(3)
            if not is_valid_username(username):
                continue
            found = True
            if video_id in seen_ids:
                report["duplicates"] += 1
                continue
            seen_ids.add(video_id)
            key = username.lower()
            link = _Link(id=video_id, url=normalize_url(username, kind, video_id),
                         username=username)
            link.pos = position
            position += 1
            groups.setdefault(key, []).append(link)
            report["total"] += 1
        if not found and not _SHORT_RE.search(line):
            report["invalid_count"] += 1
            if len(report["invalid"]) < MAX_INVALID_REPORTED:
                report["invalid"].append(line[:MAX_INVALID_LINE_LEN])
    return groups, report
