"""
Orchestrateur de téléchargement unique (CLI, web, pipeline).

Point d'entrée : run_download(). Il enchaîne :
    1. chargement de l'historique (mode incrémental) ;
    2. extraction des liens via main.get_video_links (limit et force_update respectés) ;
    3. sauvegarde des liens (main.save_links_to_file) ;
    4. pour chaque élément : détection du type (main.is_slideshow), téléchargement
       (main.download_slideshow / main.download_video), vérification, historique.

Règles métier :
    - is_slideshow renvoie True / False / None. None = type inconnu : erreur loggée,
      compté dans `unknown`, jamais téléchargé comme vidéo, NON écrit dans
      l'historique (réessayé au prochain lancement).
    - Succès vidéo uniquement si main.find_downloaded_videos trouve un fichier non vide ;
      la taille enregistrée vient de ce fichier.
    - Tout échec est historisé avec success=False.
    - Une exception sur un élément ne tue jamais le run.

Anti-ban : pause random.uniform(min_sleep, max_sleep) avant chaque élément sauf le
premier (y compris après un échec), découpée en tranches de 1 s maximum pour
réagir rapidement à should_stop().

Parallélisme : workers=1 (défaut) = exécution strictement séquentielle, sans thread.
workers>1 = ThreadPoolExecutor ; chaque tâche dort quand même avant de démarrer,
mais plusieurs requêtes partent en même temps : le risque de rate-limit / ban
TikTok augmente avec le nombre de workers.

Ce module appelle main via `import main` (et non `from main import ...`) pour que
les monkeypatch des tests s'appliquent. Il n'importe pas web_app.
"""
import math
import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import main


# Sérialise les accès à metadata.json. main.get_metadata_manager crée un nouveau
# OptimizedMetadataManager à chaque appel : save_to_history fait un
# lecture-modification-écriture complet (mises à jour perdues si deux threads
# écrivent en même temps, fichier .tmp partagé). On protège donc save_to_history.
_metadata_lock = threading.Lock()


def _default_log(message, level="info"):
    """Log par défaut : affichage console."""
    print(f"[{str(level).upper()}] {message}")


def _count_slideshow_images(username, video_id):
    """Compte les images d'un slideshow dans le dossier utilisateur (comme les boucles historiques)."""
    user_dir = main.get_user_dir(username)
    if not os.path.isdir(user_dir):
        return 0
    return sum(
        1 for name in os.listdir(user_dir)
        if str(video_id) in name and name.lower().endswith(main.IMAGE_EXTENSIONS)
    )


def _normalize_sleep(min_sleep, max_sleep):
    """Convertit en float finis >= 0 (repli 0) avec min <= max."""
    def conv(value):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.0
        return number if math.isfinite(number) and number > 0 else 0.0

    low, high = conv(min_sleep), conv(max_sleep)
    return (high, low) if low > high else (low, high)


def run_download(username, platform="tiktok", *, min_sleep=2, max_sleep=6, limit=None,
                 force_update=False, cookies_file=None, cookies_browser=None, workers=1,
                 log=None, progress=None, should_stop=None, sleep=None, forward_extraction_logs=True):
    """
    Télécharge les nouvelles vidéos et slideshows d'un profil.

    Args:
        username: Nom d'utilisateur (ou URL si platform n'est ni tiktok ni youtube).
        platform: "tiktok" ou "youtube".
        min_sleep, max_sleep: Bornes (secondes) de la pause anti-ban avant chaque élément
            sauf le premier.
        limit: Nombre maximal de nouveaux éléments traités (None = pas de limite).
        force_update: Désactive l'arrêt incrémental de l'extraction ET réessaie les
            éléments historisés avec success=False (retirés de l'historique transmis à
            main.get_video_links et du filtre de saut). Sans force_update, les échecs
            historisés restent ignorés comme les succès.
        cookies_file, cookies_browser: Transmis à toutes les fonctions de main.
        workers: 1 = séquentiel sans thread ; >1 = pool de threads (augmente le risque
            de rate-limit).
        log: callable(message, level) avec level dans info/success/warning/error.
        progress: callable(event, data) optionnel. Événements : "extraction_done",
            "item_start", "item_done", "complete".
        should_stop: callable() -> bool, vérifié pendant l'extraction, entre les
            éléments et pendant les pauses.
        sleep: callable(seconds), injectable pour les tests (défaut time.sleep).
        forward_extraction_logs: True = les logs d'extraction de main.get_video_links sont
            aussi transmis à `log` ; False (CLI) = seulement le print de get_video_links.

    Returns:
        dict: videos, slideshows, failed, unknown, skipped, downloaded (videos+slideshows),
        processed (downloaded+failed), total_extracted, size_mb,
        duration_s, stopped, extraction_error (str | None), results (liste de dicts par élément traité).
    """
    log_fn = log or _default_log
    should_stop_fn = should_stop or (lambda: False)
    sleep_fn = sleep or time.sleep
    workers = max(1, int(workers or 1))
    min_sleep, max_sleep = _normalize_sleep(min_sleep, max_sleep)
    start = time.monotonic()

    stats = {
        "videos": 0,
        "slideshows": 0,
        "failed": 0,
        "unknown": 0,
        "skipped": 0,
        "downloaded": 0,
        "processed": 0,
        "total_extracted": 0,
        "size_mb": 0.0,
        "duration_s": 0.0,
        "stopped": False,
        "extraction_error": None,
        "results": [],
    }
    stats_lock = threading.Lock()
    stop_event = threading.Event()

    def emit(message, level="info"):
        """Log protégé : une erreur du callback ne doit pas interrompre le run."""
        try:
            log_fn(message, level)
        except Exception:
            pass

    def notify(event, data):
        """Progression protégée : une erreur du callback ne doit pas interrompre le run."""
        if progress is None:
            return
        try:
            progress(event, data)
        except Exception as e:
            emit(f"Erreur du callback de progression ({event}) : {e}", "warning")

    def stop_requested():
        """Vrai si un arrêt a été demandé (mémorisé pour tous les threads)."""
        if stop_event.is_set():
            return True
        try:
            if should_stop_fn():
                stop_event.set()
                return True
        except Exception as e:
            emit(f"Erreur dans should_stop : {e}", "warning")
        return False

    def pause():
        """Pause anti-ban découpée en tranches <= 1 s. Renvoie False si arrêt demandé."""
        try:
            duration = random.uniform(min_sleep, max_sleep)
        except Exception as e:
            emit(f"Pause ignorée (erreur : {e})", "warning")
            return not stop_requested()
        if duration <= 0:
            return not stop_requested()
        emit(f"Pause : {duration:.1f} secondes", "info")
        remaining = duration
        while remaining > 0:
            if stop_requested():
                return False
            chunk = min(1.0, remaining)
            sleep_fn(chunk)
            remaining -= chunk
        return not stop_requested()

    def record_history(video_id, url, item_type, file_size=0, file_count=1, success=True):
        """Appel sérialisé de main.save_to_history."""
        with _metadata_lock:
            main.save_to_history(username, video_id, url=url, item_type=item_type,
                                 file_size=file_size, file_count=file_count, success=success)

    def finish(result, index, total, item_start):
        """Enregistre le résultat et émet l'événement de fin d'élément."""
        result["duration_s"] = time.monotonic() - item_start
        with stats_lock:
            stats["results"].append(result)
            done = len(stats["results"])
            size_mb = stats["size_mb"]
        notify("item_done", {**result, "total": total, "done": done,
                             "total_size_mb": size_mb,
                             "elapsed_s": time.monotonic() - start})
        return result

    def process_item(item, index, total):
        """Traite un élément ; ne lève jamais. Renvoie le dict résultat."""
        video_id = item["id"]
        url = item["url"]
        result = {"index": index, "id": video_id, "url": url, "type": None, "success": False,
                  "files": [], "file_count": 0, "size": 0, "error": None}
        label = f"[{index + 1}/{total}]"
        notify("item_start", {"index": index, "total": total, "id": video_id, "url": url})
        item_start = time.monotonic()

        # 1. Détection du type. Une exception ici = type inconnu (pas d'historique).
        try:
            flag = main.is_slideshow(url, username=username,
                                     cookies_browser=cookies_browser,
                                     cookies_file=cookies_file)
        except Exception as e:
            flag = None
            result["error"] = f"détection du type : {e}"

        if flag is None:
            result["type"] = "unknown"
            result["error"] = result["error"] or "type inconnu (cookies / réseau / yt-dlp ?)"
            emit(f"{label} Type inconnu pour {video_id} ({result['error']}) - ignoré, "
                 f"réessai au prochain lancement", "error")
            with stats_lock:
                stats["unknown"] += 1
            return finish(result, index, total, item_start)

        item_type = "slideshow" if flag else "video"
        result["type"] = item_type

        # 2. Téléchargement + vérification + historique
        try:
            if item_type == "slideshow":
                emit(f"{label} Slideshow en cours : {url}", "info")
                ok = main.download_slideshow(url, username, video_id,
                                             cookies_browser=cookies_browser,
                                             cookies_file=cookies_file)
                if ok:
                    image_count = _count_slideshow_images(username, video_id)
                    record_history(video_id, url, "slideshow", file_size=0,
                                   file_count=image_count, success=True)
                    result.update(success=True, file_count=image_count)
                    with stats_lock:
                        stats["slideshows"] += 1
                        stats["downloaded"] += 1
                        stats["processed"] += 1
                    emit(f"{label} Slideshow ({image_count} images)", "success")
                else:
                    result["error"] = "échec du téléchargement du slideshow"
            else:
                emit(f"{label} Vidéo en cours : {url}", "info")
                ok = main.download_video(url, username, video_id,
                                         cookies_browser=cookies_browser,
                                         cookies_file=cookies_file)
                files = main.find_downloaded_videos(username, video_id) if ok else []
                if ok and files:
                    file_size = os.path.getsize(files[0])
                    record_history(video_id, url, "video", file_size=file_size, success=True)
                    result.update(success=True, files=list(files), file_count=len(files),
                                  size=file_size)
                    with stats_lock:
                        stats["videos"] += 1
                        stats["downloaded"] += 1
                        stats["processed"] += 1
                        stats["size_mb"] += file_size / (1024 * 1024)
                    emit(f"{label} {os.path.basename(files[0])} "
                         f"({file_size / (1024 * 1024):.1f} MB)", "success")
                else:
                    result["error"] = ("aucun fichier vidéo trouvé après téléchargement"
                                       if ok else "échec du téléchargement de la vidéo")
        except Exception as e:
            result["error"] = f"exception : {e}"

        if not result["success"]:
            with stats_lock:
                stats["failed"] += 1
                stats["processed"] += 1
            emit(f"{label} Échec ({item_type}) : {result['error']}", "error")
            try:
                record_history(video_id, url, item_type, file_size=0, success=False)
            except Exception as e:
                emit(f"{label} Impossible d'historiser l'échec de {video_id} : {e}", "error")

        return finish(result, index, total, item_start)

    def task(item, index, total):
        """Tâche complète d'un élément : pause anti-ban (sauf le premier) puis traitement."""
        if stop_requested():
            return None
        if index > 0 and not pause():
            return None
        if stop_requested():
            return None
        return process_item(item, index, total)

    try:
        # ---------------------------------------------------------------- historique
        user_dir = main.get_user_dir(username)
        os.makedirs(user_dir, exist_ok=True)
        history = set(main.load_history(username))
        if force_update:
            emit("Mode MAJ forcée activé", "warning")
            # Les échecs historisés (success=False) sont réessayés en MAJ forcée
            try:
                failed_ids = {entry["id"] for entry in
                              main.get_metadata_manager(username).get_failed_downloads()}
                history -= failed_ids
            except Exception as e:
                emit(f"Impossible de lire les échecs historisés : {e}", "warning")

        # ---------------------------------------------------------------- extraction
        emit(f"Analyse du profil @{username}...", "info")
        extracted = []
        try:
            generator = main.get_video_links(
                username, history, platform, limit=limit,
                # Log par défaut : get_video_links affiche déjà ses messages (pas de doublon)
                callback_log=log if forward_extraction_logs else None,
                force_update=force_update,
                cookies_browser=cookies_browser, cookies_file=cookies_file,
            )
            for video in generator or ():
                if stop_requested():
                    emit("Arrêt demandé pendant l'extraction", "warning")
                    break
                extracted.append(video)
                if limit and len(extracted) >= limit:
                    break
        except Exception as e:
            stats["extraction_error"] = str(e)
            emit(f"Erreur d'extraction : {e}", "error")

        stats["total_extracted"] = len(extracted)
        notify("extraction_done", {"total": len(extracted)})

        if extracted:
            try:
                main.save_links_to_file(username, extracted)
            except Exception as e:
                emit(f"Impossible de sauvegarder les liens : {e}", "warning")

        # Filtrage : déjà dans l'historique (sauf force_update) ou doublon dans ce run
        items = []
        seen = set()
        for video in extracted:
            video_id = video.get("id")
            if not video_id or not video.get("url") or video_id in seen \
                    or (video_id in history and not force_update):
                stats["skipped"] += 1
                continue
            seen.add(video_id)
            items.append(video)

        if not items:
            if not stop_requested():
                emit("Aucune nouvelle vidéo à télécharger", "warning")
        elif not stop_requested():
            total = len(items)
            emit(f"Démarrage du téléchargement de {total} élément(s)", "info")
            if workers == 1:
                for index, item in enumerate(items):
                    if task(item, index, total) is None and stop_requested():
                        break
            else:
                emit(f"Mode parallèle : {workers} workers (risque de rate-limit accru)",
                     "warning")
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    futures = [executor.submit(task, item, index, total)
                               for index, item in enumerate(items)]
                    for future in futures:
                        try:
                            future.result()
                        except Exception as e:  # filet de sécurité, task ne lève pas
                            emit(f"Erreur inattendue d'un worker : {e}", "error")
    except Exception as e:
        emit(f"Erreur critique : {e}", "error")

    stats["stopped"] = stop_event.is_set()
    if stats["stopped"]:
        emit(f"Arrêt demandé pour @{username}", "warning")
    stats["duration_s"] = time.monotonic() - start
    # Ordre d'extraction des résultats, même en parallèle
    stats["results"].sort(key=lambda r: r["index"])
    notify("complete", {k: v for k, v in stats.items() if k != "results"})
    return stats
