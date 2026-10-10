"""Options yt-dlp / gallery-dl centralisées (module feuille, stdlib uniquement)."""
import os

DEFAULT_COOKIES_FILENAME = "tiktok.com_cookies.txt"

_PURPOSES = {
    "list": {
        'extract_flat': True,
        'quiet': True,
        'ignoreerrors': True,
    },
    # Sans ignoreerrors : les exceptions doivent remonter à l'appelant
    "probe": {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
    },
    # Préfère H.264 (avc1), repli sur le meilleur format disponible
    "download": {
        'format': 'bestvideo[vcodec^=avc1]+bestaudio/best[vcodec^=avc1]/best',
        'quiet': False,
        'ignoreerrors': True,
        'restrictfilenames': True,
        'writeallthumbnails': True,
    },
}


def default_cookies_file():
    """Chemin du fichier de cookies par défaut (à côté du module), ou None s'il n'existe pas."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), DEFAULT_COOKIES_FILENAME)
    return path if os.path.isfile(path) else None


def resolve_cookies(cookies_file=None, cookies_browser=None):
    """Applique la précédence : le fichier prime sur le navigateur. Renvoie (fichier, navigateur)."""
    return (cookies_file, None) if cookies_file else (None, cookies_browser or None)


def build_ydl_opts(purpose, cookies_file=None, cookies_browser=None, **overrides):
    """Construit le dict d'options yt-dlp pour 'list', 'probe' ou 'download' (ValueError sinon)."""
    if purpose not in _PURPOSES:
        raise ValueError(f"purpose inconnu: {purpose!r} (attendu: {sorted(_PURPOSES)})")
    opts = dict(_PURPOSES[purpose])
    cfile, cbrowser = resolve_cookies(cookies_file, cookies_browser)
    if cfile:
        opts['cookiefile'] = cfile
    elif cbrowser:
        opts['cookiesfrombrowser'] = (cbrowser,)
    opts.update(overrides)
    return opts


def build_gallerydl_cookie_args(cookies_file=None, cookies_browser=None):
    """Arguments de ligne de commande gallery-dl pour les cookies (liste vide si aucun)."""
    cfile, cbrowser = resolve_cookies(cookies_file, cookies_browser)
    if cfile:
        return ['--cookies', cfile]
    if cbrowser:
        return ['--cookies-from-browser', cbrowser]
    return []
