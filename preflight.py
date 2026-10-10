"""Verification de l'environnement avant lancement du telechargeur."""
import os
import shutil
import time

COOKIES_MAX_AGE_DAYS = 30


def check_environment(cookies_path=None) -> list:
    """Renvoie la liste des problemes detectes (vide si tout va bien)."""
    problems = []

    try:
        import yt_dlp
        from yt_dlp.version import __version__ as ytdlp_version
        if not ytdlp_version:
            problems.append("Impossible de determiner la version de yt-dlp.")
    except ImportError:
        problems.append("yt-dlp n'est pas installe (pip install yt-dlp).")

    gallery_ok = shutil.which("gallery-dl") is not None
    if not gallery_ok:
        try:
            import gallery_dl  # noqa: F401
            gallery_ok = True
        except ImportError:
            pass
    if not gallery_ok:
        problems.append("gallery-dl est introuvable (pip install gallery-dl).")

    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            problems.append(f"{tool} est introuvable dans le PATH.")

    if cookies_path:
        if not os.path.isfile(cookies_path):
            problems.append(f"Fichier de cookies introuvable : {cookies_path}")
        else:
            age_days = (time.time() - os.path.getmtime(cookies_path)) / 86400
            if age_days > COOKIES_MAX_AGE_DAYS:
                problems.append(
                    f"Le fichier de cookies a {int(age_days)} jours "
                    f"(plus de {COOKIES_MAX_AGE_DAYS}) : il est probablement expire."
                )

    return problems


if __name__ == "__main__":
    try:
        from yt_dlp.version import __version__ as v
        print(f"yt-dlp version : {v}")
    except ImportError:
        pass
    default_cookies = "tiktok.com_cookies.txt"
    issues = check_environment(default_cookies if os.path.exists(default_cookies) else None)
    if issues:
        print("Problemes detectes :")
        for i in issues:
            print(f" - {i}")
    else:
        print("Environnement OK.")
