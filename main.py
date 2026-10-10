import argparse
import yt_dlp
import os
import sys
import json
import time
import subprocess
import glob
import shutil
import re
import tempfile
import threading
import queue
import copy
from datetime import datetime
from metadata_manager import OptimizedMetadataManager
from ytdlp_options import build_ydl_opts, build_gallerydl_cookie_args

def get_user_dir(username):
    """Returns the directory path for a specific user."""
    return os.path.join("downloads", username)

SCAN_STATE_FILENAME = "scan_state.json"


def _scan_state_path(username):
    return os.path.join(get_user_dir(username), SCAN_STATE_FILENAME)


def load_scan_state(username):
    """Etat de scan du profil : {"fully_scanned": bool, "completed_at": str | None}.

    Fichier absent, illisible ou invalide => fully_scanned False (scan complet a faire).
    """
    state = {"fully_scanned": False, "completed_at": None}
    try:
        with open(_scan_state_path(username), "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return state
    if isinstance(data, dict) and data.get("fully_scanned") is True:
        state["fully_scanned"] = True
        completed = data.get("completed_at")
        state["completed_at"] = completed if isinstance(completed, str) else None
    return state


def save_scan_state(username, fully_scanned):
    """Ecrit l'etat de scan de facon atomique (fichier temporaire + os.replace)."""
    user_dir = get_user_dir(username)
    os.makedirs(user_dir, exist_ok=True)
    path = _scan_state_path(username)
    data = {
        "fully_scanned": bool(fully_scanned),
        "completed_at": datetime.now().isoformat(timespec="seconds") if fully_scanned else None,
    }
    fd, tmp_path = tempfile.mkstemp(dir=user_dir, prefix=".scan_state_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def get_metadata_manager(username):
    """
    Retourne ou crée un OptimizedMetadataManager pour l'utilisateur
    """
    user_dir = get_user_dir(username)
    os.makedirs(user_dir, exist_ok=True)

    return OptimizedMetadataManager(username, user_dir)

def load_history(username):
    """
    Loads the list of downloaded video IDs using OptimizedMetadataManager
    """
    manager = get_metadata_manager(username)
    return manager.get_all_ids()

def save_to_history(username, video_id, url="", item_type="video", file_size=0, file_count=1, success=True,
                    preserve_user_fields=False):
    """
    Saves a video ID to history with metadata using OptimizedMetadataManager

    preserve_user_fields=True : conserve les tags / favori / notes d'une entrée existante.
    """
    manager = get_metadata_manager(username)
    manager.add(video_id, url, item_type, file_size, file_count, success,
                preserve_user_fields=preserve_user_fields)


def load_history_split(username):
    """(ids réussis, ids en échec hérités success=False) de metadata.json, en LECTURE SEULE.

    Contrairement à load_history, ne crée jamais le dossier du profil : dossier absent =>
    deux ensembles vides. Une entrée sans clé 'success' compte comme réussie.
    """
    user_dir = get_user_dir(username)
    if not os.path.isdir(user_dir):
        return set(), set()
    data = OptimizedMetadataManager(username, user_dir).load() or {}
    success, failed = set(), set()
    for vid_id, entry in data.items():
        ok = entry.get('success', True) if isinstance(entry, dict) else True
        (success if ok is not False else failed).add(str(vid_id))
    return success, failed


# ---------------------------------------------------------------- dernière erreur (par thread)
# Les fonctions de téléchargement / sonde gardent leurs valeurs de retour (bool / None) :
# le message de la dernière erreur est exposé à part, par thread (workers parallèles).
_last_error_state = threading.local()
_LAST_ERROR_MAX = 500


def reset_last_error():
    """Efface la dernière erreur mémorisée pour le thread courant."""
    _last_error_state.message = None


def last_error():
    """Message de la dernière erreur de téléchargement / sonde du thread courant, ou None."""
    return getattr(_last_error_state, 'message', None)


def _set_last_error(message):
    text = str(message or '').strip()
    _last_error_state.message = text[-_LAST_ERROR_MAX:] if text else None

# Cache mémoire des extractions : url -> (timestamp monotonic, info_dict).
# Alimenté par is_slideshow, consommé (pop) par download_video : 1 requête par vidéo.
_INFO_CACHE_TTL = 120    # durée de vie (s)
_INFO_CACHE_MAX = 64     # taille maximale
_info_cache = {}
_info_cache_lock = threading.Lock()


def _info_cache_put(url, info):
    now = time.monotonic()
    with _info_cache_lock:
        for key in [k for k, (ts, _) in _info_cache.items() if now - ts > _INFO_CACHE_TTL]:
            del _info_cache[key]
        while len(_info_cache) >= _INFO_CACHE_MAX:
            del _info_cache[min(_info_cache, key=lambda k: _info_cache[k][0])]
        _info_cache[url] = (now, info)


def _info_cache_pop(url):
    """Renvoie (et retire) l'info fraîche de l'URL, ou None."""
    with _info_cache_lock:
        entry = _info_cache.pop(url, None)
    if entry and time.monotonic() - entry[0] <= _INFO_CACHE_TTL:
        return entry[1]
    return None


def is_slideshow(video_url, username=None, use_cache=True, cookies_browser=None, cookies_file=None):
    """
    Detects if a video is a slideshow by checking available formats.
    Now with caching support for performance.

    Args:
        video_url: URL to check
        username: Optional username for cache lookup
        use_cache: If True, checks cache before API call
        cookies_browser: Browser to extract cookies from
        cookies_file: Path to cookies.txt file

    Returns:
        bool | None: True if slideshow, False if normal video,
                     None if the type could not be determined (yt-dlp error:
                     expired cookies, 403, invalid JSON, network...).
                     None is NEVER cached: callers must treat it as an error
                     and retry later (do not download it as a normal video).
                     The error message is then available via last_error().
    """
    reset_last_error()
    # Try cache first if username provided
    if use_cache and username:
        manager = get_metadata_manager(username)
        cached_result = manager.get_slideshow_type_from_cache(video_url)
        if cached_result is not None:
            return cached_result

    # API call
    try:
        ydl_opts = build_ydl_opts('probe', cookies_file, cookies_browser)

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)

            if not info:
                # yt-dlp a renvoyé None : type inconnu (pas une vidéo normale)
                print(f"Error checking slideshow: no info returned for {video_url}")
                _set_last_error(f"no info returned for {video_url}")
                return None

            # Check if there's video format available
            formats = info.get('formats') or []
            if not formats:
                # Aucun format : impossible de conclure
                print(f"Error checking slideshow: no formats returned for {video_url}")
                _set_last_error(f"no formats returned for {video_url}")
                return None

            has_video = any(f.get('vcodec') != 'none' for f in formats)
            has_audio = any(f.get('acodec') != 'none' for f in formats)

            # If only audio available (no video), it's likely a slideshow
            result = has_audio and not has_video
            if not result:
                _info_cache_put(video_url, info)  # réutilisé par download_video (1 requête)

        # Cache the result (only known results reach this point)
        if use_cache and username:
            manager = get_metadata_manager(username)
            manager.cache_slideshow_type(video_url, result)

        return result

    except Exception as e:
        # Type inconnu : ne PAS mettre en cache, l'appelant réessaiera plus tard
        print(f"Error checking slideshow (type unknown, will retry later): {e}")
        _set_last_error(str(e) or type(e).__name__)
        return None

def download_slideshow(video_url, username, video_id, cookies_browser=None, cookies_file=None):
    """Downloads a slideshow using gallery-dl and organizes files.

    Args:
        cookies_browser: Browser to extract cookies from
        cookies_file: Path to cookies.txt file

    En cas d'échec, le message d'erreur (stderr de gallery-dl, exception) est disponible via
    last_error().
    """
    reset_last_error()
    try:
        # Get upload date from TikTok
        ydl_opts = build_ydl_opts('probe', cookies_file, cookies_browser)

        upload_date = None
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            if info:
                upload_date = info.get('upload_date', datetime.now().strftime('%Y%m%d'))

        if not upload_date:
            upload_date = datetime.now().strftime('%Y%m%d')

        # Temporary download directory + config file, unique per call
        # (évite les collisions entre workers parallèles)
        temp_dir = tempfile.mkdtemp(prefix=f"temp_slideshow_{video_id}_")
        config_file = None

        try:
            # Configuration gallery-dl
            config = {
                "base-directory": temp_dir,
                "extractor": {
                    "tiktok": {
                        "directory": ["{author[uniqueId]}", "{id}"],
                        "filename": "{num:>02}_{id}.{extension}",
                        "videos": False,  # Only images
                    }
                }
            }

            # Create temporary config file (delete=False : gallery-dl doit pouvoir le lire sous Windows)
            with tempfile.NamedTemporaryFile('w', suffix='.json', prefix='gallery-dl-config-',
                                             delete=False, encoding='utf-8') as f:
                json.dump(config, f, indent=2)
                config_file = f.name

            # Execute gallery-dl
            cmd = [
                'gallery-dl',
                '--config', config_file,
            ]

            # Cookies (options vérifiées avec gallery-dl --help : -C/--cookies, --cookies-from-browser)
            cmd += build_gallerydl_cookie_args(cookies_file, cookies_browser)

            cmd.append(video_url)

            print(f"Downloading slideshow with gallery-dl: {video_url}")
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                print(f"gallery-dl error (returncode {result.returncode})")
                if result.stderr:
                    print(f"Error: {result.stderr}")
                _set_last_error(_tail_lines(result.stderr)
                                or f"gallery-dl a échoué (code {result.returncode})")
                return False

            # Find downloaded files in temp directory
            downloaded_files = glob.glob(os.path.join(glob.escape(temp_dir), '**', '*'), recursive=True)
            image_files = [f for f in downloaded_files if os.path.isfile(f) and f.lower().endswith(IMAGE_EXTENSIONS)]
            audio_files = [f for f in downloaded_files if os.path.isfile(f) and f.lower().endswith(('.mp3', '.m4a', '.aac'))]

            if not image_files:
                print("No images found after gallery-dl download")
                _set_last_error(_tail_lines(result.stderr)
                                or "No images found after gallery-dl download")
                return False

            # Delete audio files (we don't need them)
            for audio_file in audio_files:
                try:
                    os.remove(audio_file)
                    print(f"Removed audio file: {os.path.basename(audio_file)}")
                except Exception as e:
                    print(f"Warning: Could not remove audio file: {e}")

            # Move images to final destination with proper naming
            output_dir = get_user_dir(username)
            os.makedirs(output_dir, exist_ok=True)

            # Sort images to maintain order
            image_files.sort()

            moved_count = 0
            for idx, img_file in enumerate(image_files, start=1):
                ext = os.path.splitext(img_file)[1]
                # Format: date_pseudo_id_img=numero.ext
                new_filename = f"{upload_date}_{username}_{video_id}_img={idx}{ext}"
                new_path = os.path.join(output_dir, new_filename)

                try:
                    shutil.move(img_file, new_path)
                    moved_count += 1
                    print(f"Moved: {new_filename}")
                except Exception as e:
                    print(f"Error moving {img_file}: {e}")

            if moved_count == 0:
                print("No images could be moved to the destination folder")
                _set_last_error("No images could be moved to the destination folder")
                return False

            print(f"Slideshow downloaded: {moved_count} images saved to {output_dir}")
            return True

        finally:
            # Clean up config file and temp directory
            if config_file and os.path.exists(config_file):
                try:
                    os.remove(config_file)
                except Exception as e:
                    print(f"Warning: Could not remove temp config file: {e}")
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception as e:
                print(f"Warning: Could not remove temp directory: {e}")

    except FileNotFoundError:
        print("ERROR: gallery-dl is not installed!")
        print("Install with: pip install gallery-dl")
        _set_last_error("gallery-dl is not installed")
        return False
    except Exception as e:
        print(f"Error downloading slideshow: {e}")
        import traceback
        traceback.print_exc()
        _set_last_error(str(e) or type(e).__name__)
        return False


def _tail_lines(text, max_lines=3):
    """Dernières lignes non vides d'une sortie (stderr), jointes par ' | '."""
    lines = [line.strip() for line in str(text or '').splitlines() if line.strip()]
    return ' | '.join(lines[-max_lines:])

class _YtdlpErrorCapture:
    """Logger yt-dlp minimal : mémorise les erreurs (ignoreerrors=True les rend silencieuses)."""

    def __init__(self):
        self.errors = []

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        self.errors.append(str(msg))


def _console_print(line, end="\n"):
    try:
        print(line, end=end, flush=True)
    except UnicodeEncodeError:  # console cp1252 (Windows)
        print(line.encode('ascii', 'replace').decode('ascii'), end=end, flush=True)
    except Exception:
        pass


class _YtdlpConsoleLogger(_YtdlpErrorCapture):
    """Logger yt-dlp du téléchargement : mémorise les erreurs ET garde l'affichage console.

    Avec un logger, yt-dlp n'écrit plus rien lui-même : les messages d'écran passent par
    debug() (progression comprise), les avertissements par warning(), les erreurs par error().
    """

    def debug(self, msg):
        msg = str(msg)
        if msg.startswith('[debug] '):
            return
        # Lignes de progression : réécrites sur la même ligne (sauf la dernière)
        if msg.startswith('[download]') and '%' in msg and ('ETA' in msg or ' at ' in msg):
            _console_print(msg, end="\n" if '100%' in msg else "\r")
            return
        _console_print(msg)

    def info(self, msg):
        _console_print(str(msg))

    def warning(self, msg):
        _console_print(f"WARNING: {msg}")

    def error(self, msg):
        super().error(msg)
        _console_print(str(msg))


GALLERYDL_STALL_TIMEOUT = 300    # s sans aucune ligne de sortie avant d'abandonner
GALLERYDL_LIST_TIMEOUT = 7200    # plafond total du listing (s)
GALLERYDL_PRINT_FORMAT = 'https://www.tiktok.com/@{author[uniqueId]}/{type}/{id}'
_TIKTOK_ITEM_RE = re.compile(r'https?://(?:www\.)?tiktok\.com/@[\w.\-]+/(?:video|photo)/(\d+)')


def _ytdlp_entries(url, ydl_opts, log, username):
    """Entrées brutes du listing yt-dlp. Lève une exception si yt-dlp n'a rien pu extraire."""
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if not info:
            raise RuntimeError("yt-dlp n'a renvoyé aucune information")
        if 'entries' in info:
            log(f"Found channel/user: {info.get('title', username)}")
            for entry in info['entries']:
                if entry:
                    yield entry
        else:
            yield info


def _stop_process(proc, grace=5):
    """Termine proprement un processus (terminate, puis kill après `grace` s)."""
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            pass
    except OSError:
        pass


def _gallerydl_entries(url, limit, history_size, cookies_file, cookies_browser):
    """Listing gallery-dl (`--no-download -N`) : GÉNÉRATEUR d'entrées brutes {'id','url'}.

    Chaque entrée est produite dès que gallery-dl l'affiche (ordre conservé, sans doublon),
    sans attendre la fin de la pagination. La sortie (stderr fusionné) est lue par un thread.

    Délais : GALLERYDL_STALL_TIMEOUT (inactivité : aucune ligne de sortie) et
    GALLERYDL_LIST_TIMEOUT (plafond total). Les deux ne comptent que le temps passé à
    attendre la sortie de gallery-dl : le temps du consommateur entre deux entrées
    (téléchargements en flux continu) est exclu. Dépassement -> RuntimeError (le message précise
    si des entrées avaient déjà été produites) et le processus est tué.

    Erreurs : RuntimeError si gallery-dl est absent ou échoue (code != 0) sans rien renvoyer ;
    code != 0 après des entrées déjà produites -> simple avertissement (entrées valides).
    Un profil vide avec code 0 produit un générateur vide. Le processus est toujours terminé
    et le thread lecteur joint à la fermeture du générateur (arrêt anticipé, exception).
    """
    # `-g` n'affiche que les URLs CDN (gallery-dl >= 1.30) : on imprime l'URL du post via --print,
    # sans rien télécharger (--no-download). Les lignes parasites sont filtrées par regex.
    cmd = (['gallery-dl'] + build_gallerydl_cookie_args(cookies_file, cookies_browser)
           + ['--no-download', '-N', GALLERYDL_PRINT_FORMAT])
    if limit:
        # Les éléments déjà historisés sont sautés en aval : on les compte dans la plage
        cmd += ['--range', f'1-{limit + history_size}']
    cmd.append(url.rstrip('/') + '/posts')  # l'URL de profil nue ne liste que avatar/posts
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding='utf-8', errors='replace')
    except FileNotFoundError:
        raise RuntimeError("gallery-dl n'est pas installé (pip install gallery-dl)")

    lines = queue.Queue()

    def reader():
        try:
            for raw in proc.stdout:
                lines.put(raw)
        except Exception:
            pass
        finally:
            lines.put(None)

    thread = threading.Thread(target=reader, name='gallerydl-reader', daemon=True)
    thread.start()

    seen = set()
    last_noise = ''
    # Seul le temps passé à ATTENDRE la sortie de gallery-dl compte (pas celui du consommateur
    # qui télécharge entre deux entrées) : un long téléchargement interleavé ne déclenche
    # donc ni l'inactivité ni le plafond total. La file est non bornée : le thread lecteur
    # continue de vider le pipe pendant que le consommateur travaille.
    waited_total = 0.0   # somme des attentes (plafond total)
    waited_idle = 0.0    # attente depuis la dernière ligne reçue (inactivité)
    try:
        while True:
            stall_left = GALLERYDL_STALL_TIMEOUT - waited_idle
            total_left = GALLERYDL_LIST_TIMEOUT - waited_total
            if stall_left <= 0:
                extra = f" ({len(seen)} élément(s) déjà listé(s))" if seen else ""
                raise RuntimeError(f"gallery-dl ne répond plus depuis {GALLERYDL_STALL_TIMEOUT} s{extra}")
            if total_left <= 0:
                extra = f" ({len(seen)} élément(s) déjà listé(s))" if seen else ""
                raise RuntimeError(f"gallery-dl a dépassé le délai total de {GALLERYDL_LIST_TIMEOUT} s{extra}")
            wait_start = time.monotonic()
            try:
                raw = lines.get(timeout=max(0.01, min(stall_left, total_left, 0.5)))
            except queue.Empty:
                waited = time.monotonic() - wait_start
                waited_total += waited
                waited_idle += waited
                continue
            waited_total += time.monotonic() - wait_start
            waited_idle = 0.0
            if raw is None:
                break
            line = raw.strip()
            match = _TIKTOK_ITEM_RE.search(line)
            if not match:
                if line:
                    last_noise = line
                continue
            if match.group(1) in seen:
                continue
            seen.add(match.group(1))
            yield {'id': match.group(1), 'url': match.group(0)}

        try:
            returncode = proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            returncode = proc.poll() if proc.poll() is not None else -1
        if returncode != 0:
            if not seen:
                raise RuntimeError(f"gallery-dl a échoué (code {returncode})"
                                   + (f" : {last_noise}" if last_noise else ""))
            print(f"[WARNING] gallery-dl a terminé avec le code {returncode} après "
                  f"{len(seen)} élément(s) : listing conservé")
    finally:
        _stop_process(proc)
        try:
            proc.stdout.close()
        except Exception:
            pass
        thread.join(timeout=5)


def _filter_entries(entries, history, limit, force_update, log, scan_all=False, scan_report=None,
                    known_ids=None):
    """Logique aval commune : historique, arrêt incrémental, limite. Générateur de {'url','id'}.

    known_ids (optionnel) : ensemble des ids considérés comme « connus » (sautés et comptés
    dans les 10 consécutifs) ; None = `history` (comportement historique).
    L'arrêt après 10 doublons consécutifs n'est appliqué que si NOT (force_update OR scan_all).
    scan_report (dict, optionnel) : 'listed' (entrées vues) et 'ended_by'
    ('exhausted' | 'incremental' | 'limit'). 'limit' est posé AVANT le dernier yield, car le
    consommateur peut fermer le générateur dès qu'il a reçu assez d'éléments.
    """
    new_videos_count = 0
    consecutive_matches = 0
    allow_incremental = not (force_update or scan_all)
    known = history if known_ids is None else known_ids
    for entry in entries:
        video_id = entry.get('id')
        if scan_report is not None:
            scan_report['listed'] = scan_report.get('listed', 0) + 1

        # INCREMENTAL CHECK (Smart Mode)
        if video_id in known:
            consecutive_matches += 1
            if consecutive_matches >= 10 and allow_incremental:
                log(f"Found {consecutive_matches} consecutive existing videos. Stopping extraction (Smart Incremental Mode).", "warning")
                if scan_report is not None:
                    scan_report['ended_by'] = 'incremental'
                break
        else:
            consecutive_matches = 0  # Reset counter if we find a new video

            video_url = entry.get('url') or entry.get('webpage_url')
            if video_url and video_id:
                new_videos_count += 1
                hit_limit = bool(limit) and new_videos_count >= limit
                if hit_limit and scan_report is not None:
                    scan_report['ended_by'] = 'limit'
                yield {'url': video_url, 'id': video_id}

                # LIMIT CHECK
                if hit_limit:
                    log(f"Limit of {limit} videos reached. Stopping extraction.", "warning")
                    break
    else:
        if scan_report is not None:
            scan_report['ended_by'] = 'exhausted'

    return new_videos_count


def _explain_ytdlp_error(error_msg, log):
    """Messages actionnables pour les erreurs yt-dlp courantes."""
    if "JSONDecodeError" in error_msg or "Failed to parse JSON" in error_msg:
        log("Erreur JSON - Causes possibles :", "error")
        log("  1. Cookies expirés -> Réexportez vos cookies TikTok", "error")
        log("  2. yt-dlp obsolète -> Exécutez: pip install --upgrade yt-dlp", "error")
        log("  3. Profil inexistant ou privé", "error")
    elif "HTTP Error 403" in error_msg or "Forbidden" in error_msg:
        log("Accès refusé (403) - Cookies invalides ou expirés", "error")
        log("  -> Réexportez vos cookies TikTok dans tiktok.com_cookies.txt", "error")
    elif "HTTP Error 404" in error_msg or "not found" in error_msg.lower():
        log("Profil introuvable - Vérifiez que le nom d'utilisateur est correct", "error")
    elif "getaddrinfo" in error_msg or "ConnectionError" in error_msg or "URLError" in error_msg:
        log("Erreur réseau - Vérifiez votre connexion Internet", "error")
    else:
        log(f"Error extracting links: {error_msg}", "error")


def get_video_links(username, history, platform="tiktok", limit=None, callback_log=None, force_update=False, cookies_browser=None, cookies_file=None, scan_all=None, scan_report=None, known_ids=None):
    """
    Extracts video links for a given username using yt-dlp (repli gallery-dl pour TikTok).
    Stops if a video ID is already in history (Incremental Mode), unless force_update is True.
    Stops if the limit of new videos is reached.
    Generator: yields dicts with 'url' and 'id'.

    Si yt-dlp ne peut pas lister le profil (exception, ou aucune entrée alors qu'une
    erreur a été vue), bascule sur `gallery-dl`. Si les deux échouent, lève
    RuntimeError (un profil réellement vide n'est PAS une erreur).

    Args:
        cookies_browser: Browser to extract cookies from (chrome, firefox, edge, etc.)
        cookies_file: Path to cookies.txt file
        scan_all: True = parcourt tout le profil (pas d'arrêt incrémental). None = auto :
            True tant que le profil n'est pas fully_scanned (scan_state.json).
        scan_report: dict rempli par la fonction : 'ended_by' ('exhausted' | 'incremental' |
            'limit' | 'error') et 'listed' (entrées vues). Cette fonction ne modifie jamais
            l'état de scan.
        known_ids: ensemble optionnel des ids « connus » (sautés et comptés pour l'arrêt
            incrémental) ; None = history. history reste utilisé pour la plage gallery-dl.
    """
    if known_ids is not None:
        known_ids = {str(i) for i in known_ids}
    if scan_report is None:
        scan_report = {}
    scan_report['listed'] = 0
    scan_report['ended_by'] = 'error'  # valeur par défaut tant que le listing n'est pas terminé
    auto_scan = False
    if scan_all is None:
        auto_scan = not load_scan_state(username)["fully_scanned"]
        scan_all = auto_scan

    if platform.lower() == "tiktok":
        url = f"https://www.tiktok.com/@{username}"
    elif platform.lower() == "youtube":
        url = f"https://www.youtube.com/@{username}/shorts"
    else:
        url = username

    def log(msg, level="info"):
        line = f"[{level.upper()}] {msg}"
        try:
            print(line)
        except UnicodeEncodeError:  # console cp1252 (Windows) : ne jamais planter sur un log
            print(line.encode('ascii', 'replace').decode('ascii'))
        if callback_log:
            callback_log(msg, level)

    log(f"Fetching videos for: {url}")
    if auto_scan and not force_update:
        log("Premier scan complet de ce profil : les vidéos déjà connues sont ignorées, "
            "l'ensemble du profil est parcouru (le mode incrémental sera activé ensuite).", "info")

    capture = _YtdlpErrorCapture()
    ydl_opts = build_ydl_opts('list', cookies_file, cookies_browser, logger=capture)

    # Add cookies support for private accounts
    if cookies_file:
        log(f"Using cookies from file: {cookies_file}", "info")
    elif cookies_browser:
        log(f"Using cookies from {cookies_browser}", "info")

    raw_count = [0]

    def tracked(entries):
        for entry in entries:
            raw_count[0] += 1
            yield entry

    ytdlp_error = None
    try:
        found = yield from _filter_entries(tracked(_ytdlp_entries(url, ydl_opts, log, username)),
                                           history, limit, force_update, log,
                                           scan_all=scan_all, scan_report=scan_report,
                                           known_ids=known_ids)
        if raw_count[0] == 0 and capture.errors:
            ytdlp_error = capture.errors[-1]
        else:
            log(f"Extraction finished. Found {found} new videos.", "success")
    except Exception as e:
        if raw_count[0] > 0:
            # Listing interrompu en cours de route : on garde ce qui a été trouvé
            scan_report['ended_by'] = 'error'
            _explain_ytdlp_error(str(e), log)
            return
        ytdlp_error = str(e)

    if ytdlp_error is None:
        return

    _explain_ytdlp_error(ytdlp_error, log)
    if platform.lower() != "tiktok":
        raise RuntimeError(f"Listing impossible pour {url} : {ytdlp_error}. "
                           "Vérifiez les cookies et que le compte existe.")

    log("yt-dlp ne peut plus lister ce profil, repli sur gallery-dl", "warning")
    # Consommation paresseuse : chaque entrée est traitée dès que gallery-dl l'affiche.
    # Erreur AVANT toute entrée -> RuntimeError combinée yt-dlp + gallery-dl.
    # Erreur APRÈS des entrées -> loggée en erreur, on garde ce qui a déjà été produit.
    gdl_count = [0]
    scan_report['listed'] = 0
    scan_report['ended_by'] = 'error'

    def gdl_tracked():
        skipped_size = len(history) if known_ids is None else max(len(history), len(known_ids))
        for entry in _gallerydl_entries(url, limit, skipped_size, cookies_file, cookies_browser):
            gdl_count[0] += 1
            yield entry

    try:
        found = yield from _filter_entries(gdl_tracked(), history, limit, force_update, log,
                                           scan_all=scan_all, scan_report=scan_report,
                                           known_ids=known_ids)
    except RuntimeError as e:
        scan_report['ended_by'] = "error"
        if gdl_count[0] == 0:
            raise RuntimeError(
                f"Listing impossible pour @{username} : yt-dlp ({ytdlp_error}) et gallery-dl ({e}) "
                "ont échoué. Vérifiez les cookies (tiktok.com_cookies.txt) et que le compte existe."
            ) from e
        log(f"gallery-dl interrompu après {gdl_count[0]} élément(s) : {e}. "
            "Les éléments déjà listés sont conservés.", "error")
        return

    log(f"gallery-dl a listé {gdl_count[0]} élément(s)", "info")
    log(f"Extraction finished. Found {found} new videos.", "success")


def organize_slideshow(output_dir, video_id):
    """Post-process downloaded files to organize slideshows into folders."""
    import glob
    import shutil
    
    # Find all files with this video ID
    # Correspondance littérale sur l'id (les crochets non échappés étaient lus
    # par glob comme une classe de caractères et attrapaient d'autres vidéos)
    files = [
        f for f in glob.glob(os.path.join(glob.escape(output_dir), '*'))
        if f'[{video_id}]' in os.path.basename(f)
        or f'_{video_id}.' in os.path.basename(f)
        or f'_{video_id}_' in os.path.basename(f)
    ]
    
    if not files:
        return
    
    # Categorize files
    images = [f for f in files if f.lower().endswith(IMAGE_EXTENSIONS)]
    audio = [f for f in files if f.lower().endswith(('.m4a', '.mp3', '.aac'))]
    videos = [f for f in files if f.lower().endswith(('.mp4', '.webm', '.mkv'))]
    
    # If we have multiple images, it's a slideshow
    if len(images) > 1:
        # Get base name from first image (without extension and numbering)
        base_name = os.path.basename(images[0])
        # Remove extension
        base_name = base_name.rsplit('.', 1)[0]
        # Remove potential _001, _01, etc suffixes that yt-dlp might add
        import re
        base_name = re.sub(r'_\d+$', '', base_name)
        
        # Create folder
        folder_path = os.path.join(output_dir, base_name)
        os.makedirs(folder_path, exist_ok=True)
        
        print(f"Detected slideshow: organizing {len(images)} images into folder...")
        
        # Move images to folder
        for img in images:
            dest = os.path.join(folder_path, os.path.basename(img))
            shutil.move(img, dest)
        
        # Delete audio files
        for aud in audio:
            try:
                os.remove(aud)
                print(f"Removed audio file: {os.path.basename(aud)}")
            except Exception as e:
                print(f"Could not remove audio: {e}")
        
        print(f"Slideshow organized in: {folder_path}")

def sanitize_filename(filename):
    """Clean filename by removing problematic characters"""
    import re
    # Remove or replace problematic characters
    # Keep only: alphanumeric, dash, underscore, dot, brackets
    filename = re.sub(r'[^\w\-_\.\[\]\(\)]', '_', filename)
    # Remove multiple consecutive underscores
    filename = re.sub(r'_+', '_', filename)
    # Remove leading/trailing underscores
    filename = filename.strip('_')
    return filename

def get_video_codec(file_path):
    """Return the codec name of the first video stream (lowercase), or None if unknown."""
    try:
        result = subprocess.run(
            [
                'ffprobe', '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=codec_name',
                '-of', 'csv=p=0',
                file_path
            ],
            capture_output=True, text=True, timeout=15
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    return result.stdout.strip().lower() or None


def ensure_h264(file_path):
    """Make sure a video file is an H.264 mp4 playable in every browser.

    Uses ffprobe to detect the codec, then ffmpeg to re-encode only when needed
    (HEVC/AV1/VP9 would give a black screen with sound). Other containers
    (mkv, webm, mov) are converted to mp4. The output is forced to 8-bit
    yuv420p, the only pixel format all browsers decode.

    Returns:
        str: Path to the final file (same path, or the .mp4 path if the
        container changed). The original is kept if anything fails.
    """
    if not file_path or not os.path.exists(file_path):
        return file_path

    ext = os.path.splitext(file_path)[1].lower()
    if ext not in ('.mp4', '.mkv', '.webm', '.mov'):
        return file_path

    temp_path = None
    try:
        codec = get_video_codec(file_path)

        if not codec:
            print(f"[H264] Could not detect codec for {os.path.basename(file_path)}")
            return file_path

        is_h264 = codec in ('h264', 'avc1', 'avc')

        # H.264 already in an mp4: nothing to do
        if is_h264 and ext == '.mp4':
            return file_path

        target_path = os.path.splitext(file_path)[0] + '.mp4'
        if is_h264:
            print(f"[H264] Remuxing {os.path.basename(file_path)} ({ext} -> .mp4)...")
            video_args = ['-c:v', 'copy']
        else:
            print(f"[H264] Re-encoding {os.path.basename(file_path)} ({codec} -> h264)...")
            video_args = [
                '-c:v', 'libx264',      # Re-encode video to H.264
                '-preset', 'fast',      # Good speed/quality balance
                '-crf', '23',           # Visual quality (lower = better, 23 = default)
                '-pix_fmt', 'yuv420p',  # 8-bit 4:2:0, required for browser playback
            ]

        # Unique temp file in the same directory (os.replace must stay on the same volume)
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        fd, temp_path = tempfile.mkstemp(prefix=f"{base_name}.", suffix='.tmp.mp4',
                                         dir=os.path.dirname(os.path.abspath(file_path)))
        os.close(fd)

        result = subprocess.run(
            [
                'ffmpeg', '-y',
                '-i', file_path,
                *video_args,
                '-c:a', 'aac',             # Ensure audio is AAC
                '-movflags', '+faststart', # Web-optimized: metadata at start
                '-v', 'warning',
                temp_path
            ],
            capture_output=True, text=True, timeout=900
        )

        if result.returncode == 0 and os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
            # Atomic replace: original is only overwritten once the new file is valid
            os.replace(temp_path, target_path)
            temp_path = None
            if target_path != file_path:
                os.remove(file_path)
            print(f"[H264] Converted successfully: {os.path.basename(target_path)}")
            return target_path

        print(f"[H264] Conversion failed, keeping original ({codec})")
        if result.stderr:
            print(f"[H264] ffmpeg error: {result.stderr[:200]}")
        return file_path

    except FileNotFoundError:
        print("[H264] ffmpeg/ffprobe not found, skipping re-encoding")
        return file_path
    except subprocess.TimeoutExpired:
        print(f"[H264] Re-encoding timed out for {os.path.basename(file_path)}")
        return file_path
    except Exception as e:
        print(f"[H264] Error: {e}")
        return file_path
    finally:
        # Cleanup failed attempt (the original is never touched here)
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception as e:
                print(f"[H264] Could not remove temp file: {e}")

VIDEO_EXTENSIONS = ('mp4', 'webm', 'mkv', 'mov')
IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp')

def find_downloaded_videos(username, video_id, extensions=VIDEO_EXTENSIONS):
    """Returns the non-empty final video files for video_id in the user's directory.

    Strict match: the name must end with "_<id>.<ext>" (or be "<id>.<ext>"),
    so partial/temporary files (.part, .tmp.mp4, .f137.mp4, .temp.mp4...) are excluded.
    """
    output_dir = get_user_dir(username)
    if not video_id or not os.path.isdir(output_dir):
        return []

    pattern = re.compile(r'(?:^|_)' + re.escape(str(video_id)) + r'\.(?:' + '|'.join(extensions) + r')$',
                         re.IGNORECASE)
    found = []
    for name in sorted(os.listdir(output_dir)):
        if not pattern.search(name):
            continue
        path = os.path.join(output_dir, name)
        try:
            if os.path.isfile(path) and os.path.getsize(path) > 0:
                found.append(path)
        except OSError:
            continue
    return found

def download_video(video_url, username, video_id, retries=3, cookies_browser=None, cookies_file=None):
    """Downloads a single video using yt-dlp into the user's directory with retry logic.

    Args:
        cookies_browser: Browser to extract cookies from
        cookies_file: Path to cookies.txt file

    En cas d'échec, last_error() donne la dernière erreur remontée par yt-dlp (via un logger
    léger, ignoreerrors=True rendant les erreurs silencieuses) ou, à défaut, la dernière
    exception.
    """
    reset_last_error()
    output_dir = get_user_dir(username)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    capture = _YtdlpConsoleLogger()
    ydl_opts = build_ydl_opts('download', cookies_file, cookies_browser,
                              outtmpl=f'{output_dir}/%(upload_date)s_%(id)s.%(ext)s',
                              logger=capture)
    last_exception = [None]

    def fail(message):
        # Priorité à l'erreur yt-dlp (la plus précise), sinon l'exception / le message
        _set_last_error(capture.errors[-1] if capture.errors else message)
        return False


    # Extraction déjà faite par is_slideshow : première tentative seulement, sans requête de plus
    cached_info = _info_cache_pop(video_url)

    downloaded = False
    for attempt in range(retries):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # With ignoreerrors=True, yt-dlp does not raise: the file check below is the source of truth
                if cached_info is not None:
                    info, cached_info = cached_info, None  # jamais réutilisée aux tentatives suivantes
                    print("Reusing cached extraction (no second page request)")
                    # Le sélecteur de format est ré-appliqué à la liste complète `formats`
                    retcode = 0 if ydl.process_ie_result(copy.deepcopy(info), download=True) is not None else 1
                else:
                    retcode = ydl.download([video_url])

            # Post-process: Rename to include username
            # Find file with this video ID (just downloaded)
            pattern = os.path.join(glob.escape(output_dir), f'*{glob.escape(str(video_id))}*')
            files = glob.glob(pattern)
            
            for file_path in files:
                if os.path.isfile(file_path):
                    old_name = os.path.basename(file_path)
                    # Extract date and extension
                    # Format: YYYYMMDD_ID.ext -> YYYYMMDD_username_ID.ext
                    parts = old_name.split('_')
                    if len(parts) >= 2:
                        date_part = parts[0]
                        # Last part has ID.ext
                        id_and_ext = '_'.join(parts[1:])
                        new_name = f"{date_part}_{username}_{id_and_ext}"
                        new_name = sanitize_filename(new_name)

                        # Already renamed (re-download of same id): don't add the username twice
                        expected_prefix = sanitize_filename(f"{date_part}_{username}") + "_"
                        if old_name.startswith(expected_prefix):
                            continue

                        if new_name != old_name:
                            new_path = os.path.join(output_dir, new_name)
                            try:
                                os.rename(file_path, new_path)
                                print(f"Renamed: {old_name} -> {new_name}")
                            except Exception as e:
                                print(f"Could not rename: {e}")

            # Verify that a non-empty video file really exists for this ID
            if not find_downloaded_videos(username, video_id):
                raise RuntimeError(f"no video file found for {video_id} after download (yt-dlp retcode={retcode})")

            downloaded = True
            break
        except Exception as e:
            last_exception[0] = str(e) or type(e).__name__
            print(f"Error downloading {video_url} (Attempt {attempt+1}/{retries}): {e}")
            if attempt < retries - 1:
                time.sleep(2) # Wait a bit before retrying
            else:
                print("Max retries reached.")

    if not downloaded:
        return fail(last_exception[0] or "download failed")

    # Post-process (once, after a successful download): ensure H.264 for browser compatibility
    for video_file in find_downloaded_videos(username, video_id):
        final_path = ensure_h264(video_file)
        codec = get_video_codec(final_path) if final_path else None
        if codec and codec not in ('h264', 'avc1', 'avc'):
            print(f"[H264] WARNING: {os.path.basename(final_path)} is still {codec}: "
                  f"it will show a black screen in browsers (ffmpeg missing or conversion failed)")

    # Post-process: organize slideshows
    try:
        organize_slideshow(output_dir, video_id)
    except Exception as e:
        print(f"Warning: could not organize slideshow files: {e}")

    # Final check (the file must still be there after post-processing)
    if not find_downloaded_videos(username, video_id):
        print(f"Error: video file for {video_id} missing after post-processing")
        _set_last_error(f"video file for {video_id} missing after post-processing")
        return False

    return True

def save_links_to_file(username, videos):
    """Saves unique video links to a text file in the user's directory."""
    output_dir = get_user_dir(username)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    filename = os.path.join(output_dir, f"{username}_videos.txt")
    try:
        # Read existing links if file exists
        existing_links = set()
        if os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as f:
                existing_links = set(line.strip() for line in f if line.strip())
        
        # Add new links
        new_links = [video['url'] for video in videos]
        all_links = existing_links.union(new_links)
        
        # Write all unique links back (sorted for consistency)
        with open(filename, "w", encoding="utf-8") as f:
            for link in sorted(all_links):
                f.write(link + "\n")
        
        added_count = len(all_links) - len(existing_links)
        print(f"Successfully saved {len(all_links)} unique links ({added_count} new) to {os.path.abspath(filename)}")
    except Exception as e:
        print(f"Error saving to file: {e}")

def append_link_to_file(username, video_url):
    """Appends a single video link to the user's video list file."""
    output_dir = get_user_dir(username)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    filename = os.path.join(output_dir, f"{username}_videos.txt")
    try:
        with open(filename, "a", encoding="utf-8") as f:
            f.write(video_url + "\n")
        return True
    except Exception as e:
        print(f"Error appending to file: {e}")
        return False

def _cli_log(message, level="info"):
    prefix = {"error": "ERROR: ", "warning": "WARNING: "}.get(level, "")
    print(f"{prefix}{message}")


def _print_download_summary(stats):
    print("\nDownload Summary:")
    print(f"   Videos: {stats['videos']}")
    print(f"   Slideshows: {stats['slideshows']}")
    print(f"   Total: {stats['downloaded']}")
    if stats['failed']:
        print(f"   Failed: {stats['failed']}")
    if stats['unknown']:
        print(f"   Unknown type (skipped, retry later): {stats['unknown']}")
    print(f"   Size: {stats['size_mb']:.1f} MB")
    print(f"   Duration: {stats['duration_s']:.0f}s")


def import_links_cli(args):
    """Mode --links-file : importe une liste de liens (fichier, ou « - » = stdin) et la télécharge.

    Si un pseudo est aussi donné en argument, tous les liens lui sont attribués ; sinon ils sont
    groupés par pseudo présent dans les URLs. N'altère jamais scan_state.json.
    Retourne le code de sortie (0 = ok, 1 = aucun lien valide ou fichier illisible).
    """
    import links_import
    from orchestrator import run_import

    try:
        if args.links_file == "-":
            text = sys.stdin.read()
        else:
            with open(args.links_file, "r", encoding="utf-8-sig", errors="replace") as fh:
                text = fh.read()
    except OSError as e:
        print(f"ERROR: impossible de lire {args.links_file} : {e}")
        return 1

    groups, report = links_import.parse_links(text)
    if report["ignored"]:
        print(f"WARNING: {report['ignored']} lien(s) court(s) vm./vt.tiktok.com ignoré(s) "
              "(ouvrez-les dans le navigateur et utilisez le lien complet)")
    if report["invalid_count"]:
        print(f"WARNING: {report['invalid_count']} ligne(s) sans lien valide, par exemple : "
              + " | ".join(report["invalid"][:3]))
    if not groups:
        print("ERROR: aucun lien de vidéo TikTok valide trouvé "
              "(format : https://www.tiktok.com/@pseudo/video/123...)")
        return 1

    forced = args.username_or_url
    if forced:
        forced = forced.strip().lstrip("@")
        if not links_import.is_valid_username(forced):
            print("ERROR: pseudo invalide (lettres, chiffres, point, tiret et tiret bas uniquement)")
            return 1
    plan = links_import.build_plan(
        groups, mode="single" if forced else "by_author", destination=forced or None,
        existing_folders=links_import.list_folders("downloads"))

    for username, items in plan:
        print(f"Import de {len(items)} lien(s) pour @{username}")
        stats = run_import(
            username, items,
            min_sleep=args.min_sleep, max_sleep=args.max_sleep,
            cookies_file=args.cookies_file, cookies_browser=args.cookies_browser,
            force_update=args.force_update, log=_cli_log,
        )
        if len(plan) > 1:
            print(f"--- @{username} ---")
        _print_download_summary(stats)
    return 0


def main():
    parser = argparse.ArgumentParser(description="Extract and download videos from a user profile or single URL, or import a list of links (--links-file).")
    parser.add_argument("username_or_url", nargs="?", default=None,
                        help="The username (pseudo) or a direct TikTok URL. Optional with --links-file "
                             "(if given, all imported links are filed under this pseudo).")
    parser.add_argument("--platform", default="tiktok", help="Target platform (default: tiktok).")
    parser.add_argument("--download", action="store_true", help="Download the videos after extraction.")
    parser.add_argument("--min-sleep", type=int, default=2, help="Minimum sleep time in seconds (default: 2).")
    parser.add_argument("--max-sleep", type=int, default=6, help="Maximum sleep time in seconds (default: 6).")
    parser.add_argument("--limit", type=int, help="Limit the number of videos to extract/download.")
    parser.add_argument("--force-update", action="store_true", help="Force update mode: check all videos and ignore incremental stop.")
    parser.add_argument("--cookies-browser", choices=['chrome', 'firefox', 'edge', 'safari', 'opera', 'brave'],
                        help="Browser to extract cookies from (for private accounts). Example: chrome")
    parser.add_argument("--cookies-file", type=str,
                        help="Path to cookies.txt file (for private accounts). Example: cookies.txt")
    parser.add_argument("--links-file", metavar="FICHIER",
                        help="Import and download a list of video links exported from your browser "
                             "(text file, one URL per line; '-' reads stdin). Replaces profile listing; "
                             "honours --min-sleep/--max-sleep/--cookies-*/--force-update.")

    args = parser.parse_args()
    if not args.links_file and not args.username_or_url:
        parser.error("the following arguments are required: username_or_url (or --links-file)")

    from preflight import check_environment
    for problem in check_environment(args.cookies_file):
        print(f"[preflight] {problem}")

    if args.links_file:
        sys.exit(import_links_cli(args))

    # Check if input is a URL or username
    is_url = "tiktok.com" in args.username_or_url or "http" in args.username_or_url
    
    if is_url:
        # Single URL mode
        print(f"Single URL mode detected: {args.username_or_url}")
        
        # Extract username from URL for folder organization
        # Format: https://www.tiktok.com/@username/video/123
        try:
            username = args.username_or_url.split('@')[1].split('/')[0]
        except:
            username = "single_downloads"
        
        user_dir = get_user_dir(username)
        os.makedirs(user_dir, exist_ok=True)
        
        # Check if it's a slideshow
        print("Checking if slideshow...")
        slideshow_flag = is_slideshow(args.username_or_url, username=username, cookies_browser=args.cookies_browser, cookies_file=args.cookies_file)
        if slideshow_flag is None:
            # Type inconnu (cookies expirés, 403, réseau...) : ne pas télécharger comme vidéo normale
            print("ERROR: Could not determine if this is a slideshow or a video (check cookies / network / yt-dlp version). Retry later.")
            sys.exit(1)
        if slideshow_flag:
            print("Slideshow detected - downloading with gallery-dl")
            # Extract video ID from URL
            try:
                video_id = args.username_or_url.split('/video/')[1].split('?')[0]
            except:
                video_id = "unknown"

            success = download_slideshow(args.username_or_url, username, video_id, cookies_browser=args.cookies_browser, cookies_file=args.cookies_file)
            if success:
                print(f"Slideshow download complete! Saved to {user_dir}")
            else:
                print("Slideshow download failed.")
            return

        # Download the video
        print("Downloading video...")
        try:
            video_id = args.username_or_url.split('/video/')[1].split('?')[0]
        except:
            video_id = "unknown"

        success = download_video(args.username_or_url, username, video_id, cookies_browser=args.cookies_browser, cookies_file=args.cookies_file)
        if success:
            print(f"Download complete! Saved to {user_dir}")
        else:
            print("Download failed.")
        return
    
    # Username mode (original behavior)
    username = args.username_or_url
    
    # Create user directory if it doesn't exist
    user_dir = get_user_dir(username)
    if not os.path.exists(user_dir):
        os.makedirs(user_dir, exist_ok=True)
        print(f"Created directory: {user_dir}")

    # Load history FIRST for incremental extraction
    history = load_history(username)

    print(f"Starting extraction for user: {username} on {args.platform}...")
    if args.force_update:
        print("WARNING: FORCE UPDATE MODE ENABLED: Will scan all videos.")
    if args.download:
        # Orchestrateur unique : extraction + détection du type + téléchargement + historique
        from orchestrator import run_download

        stats = run_download(
            username, args.platform,
            min_sleep=args.min_sleep, max_sleep=args.max_sleep, limit=args.limit,
            force_update=args.force_update,
            cookies_file=args.cookies_file, cookies_browser=args.cookies_browser,
            log=_cli_log,
            forward_extraction_logs=False,  # get_video_links affiche déjà ses messages
        )
        if stats.get("extraction_error") and not stats.get("total_extracted"):
            print(f"ERROR: {stats['extraction_error']}")
            sys.exit(1)
        _print_download_summary(stats)
        return

    videos_generator = get_video_links(username, history, args.platform, args.limit, force_update=args.force_update, cookies_browser=args.cookies_browser, cookies_file=args.cookies_file)

    # Convert generator to list for processing
    try:
        videos = list(videos_generator)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    if videos:
        save_links_to_file(username, videos)
    else:
        print("No new videos found.")

if __name__ == "__main__":
    main()
