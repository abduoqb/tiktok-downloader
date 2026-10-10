"""
Orchestrateur de téléchargement unique (CLI, web, pipeline).

Point d'entrée : run_download(). Il enchaîne :
    1. chargement de l'historique (mode incrémental) ;
    2. listing paresseux via main.get_video_links (limit et force_update respectés) ;
    3. pour chaque élément, DÈS qu'il est listé (workers=1, flux continu) : pause anti-ban,
       détection du type (main.is_slideshow), téléchargement (main.download_slideshow /
       main.download_video), vérification, historique ;
    4. sauvegarde des liens listés (main.save_links_to_file), une seule fois en fin de run
       (aussi en cas d'arrêt ou d'erreur).

Import d'une liste de liens : run_import() (ou run_download(items=...)) court-circuite le
listing et réutilise EXACTEMENT la même boucle de traitement (pauses, détection du type,
téléchargement, vérification, historique, arrêt, progression). Le total est connu d'avance et
scan_state.json n'est jamais modifié : un import ne marque ni ne démarque le profil comme
entièrement scanné.

Tri des liens (triage.py) : chargé UNE fois par dossier (historique metadata.json en lecture
seule, fichiers du disque via disk_index, états link_state.json via LinkState), sans créer le
dossier. Chaque élément est classé : downloaded (succès historisé, jamais retéléchargé, même
avec force_update), adopt (fichier présent sur le disque mais absent de l'historique : ajouté
à l'historique SANS retéléchargement), ignored (supprimé par l'utilisateur : jamais
retéléchargé, même avec force_update), unavailable / retry_waiting (sautés ; force_update les
fait repasser en retry_due), retry_due et new (traités).

Règles métier :
    - is_slideshow renvoie True / False / None. None = type inconnu. Si l'erreur de sonde
      (main.last_error()) est définitive (vidéo supprimée / privée...), l'élément devient
      « indisponible » (compté dans `failed`) ; sinon : erreur loggée, compté dans
      `unknown`, jamais téléchargé comme vidéo, NON écrit dans l'historique, une tentative
      temporaire est enregistrée dans link_state.json.
    - Succès vidéo uniquement si main.find_downloaded_videos trouve un fichier non vide ;
      la taille enregistrée vient de ce fichier. Un succès efface l'état retry/unavailable.
    - Un échec n'est PLUS écrit dans metadata.json : il est classé (download_errors) puis
      enregistré dans link_state.json (temporaire => réessai après 10 min / 1 h / 6 h, au plus
      link_state.MAX_ATTEMPTS tentatives ; définitif ou tentatives épuisées => indisponible).
      Un échec hérité (success=False dans metadata.json, sans état) est retenté une fois.
    - link_state.json est sauvegardé tous les 10 éléments traités et en fin de run (aussi en
      cas d'arrêt ou d'exception).
    - Une exception sur un élément ne tue jamais le run.

Anti-ban : pause random.uniform(min_sleep, max_sleep) avant chaque élément sauf le
premier (y compris après un échec), découpée en tranches de 1 s maximum pour
réagir rapidement à should_stop().

Parallélisme : workers=1 (défaut) = exécution strictement séquentielle, sans thread, en flux
continu : le premier téléchargement démarre pendant que le listing avance (le total n'est
connu qu'à la fin du listing : item_start / item_done portent total=None). workers>1 =
comportement par lots inchangé : le listing est d'abord collecté en entier, puis un
ThreadPoolExecutor traite les éléments (total connu) ; chaque tâche dort quand même avant
de démarrer, mais plusieurs requêtes partent en même temps : le risque de rate-limit / ban
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
from datetime import datetime

import disk_index
import download_errors
import link_state
import main
import triage

# Sauvegarde de link_state.json tous les N éléments traités (et toujours en fin de run)
STATE_SAVE_EVERY = 10

# Catégories du tri considérées comme « connues » pour l'arrêt incrémental du listing
_KNOWN_CATEGORIES = ("downloaded", "adopt", "ignored", "unavailable", "retry_waiting")

# Catégorie du tri -> sous-compteur de stats (tous inclus dans stats["skipped"])
_SKIP_COUNTERS = {
    "downloaded": "known",
    "adopt": "adopted",
    "ignored": "ignored",
    "unavailable": "unavailable",
    "retry_waiting": "retry_waiting",
    "duplicate": "duplicate",
    "invalid": "invalid",
}


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


def _item_key(raw_id):
    """Identifiant normalisé (comme triage.classify_links) ; '' si absent."""
    return str(raw_id).strip() if raw_id is not None else ""


def _adoption_url(username, item_id, kind):
    """URL reconstruite d'un élément adopté depuis le disque."""
    path = "photo" if kind == "slideshow" else "video"
    return f"https://www.tiktok.com/@{username}/{path}/{item_id}"


def _retry_text(entry):
    """Courte description d'un état link_state pour les logs."""
    if not entry:
        return ""
    if entry.get("status") == "retry":
        due = entry.get("next_retry") or "?"
        return f"nouvel essai après {due} (tentative {entry.get('attempts')}/" \
               f"{link_state.MAX_ATTEMPTS})"
    if entry.get("status") == "unavailable":
        return "marquée indisponible"
    return entry.get("status") or ""


def _update_scan_state(username, stats, scan_report, items, critical_error, emit):
    """Met à jour scan_state.json et stats['full_scan'] / stats['scan_complete'].

    Le profil devient fully_scanned seulement si le listing est allé au bout (épuisé ou arrêt
    incrémental), sans erreur ni arrêt, avec tous les éléments listés traités et aucun type
    inconnu (non historisés). Sinon l'état est laissé tel quel, sauf si des éléments listés
    n'ont pas été traités : un profil déjà scanné repasse alors à False.
    """
    ended_by = scan_report.get("ended_by")
    stats["full_scan"] = bool(ended_by == "exhausted" and not stats["extraction_error"]
                              and not critical_error)
    try:
        was_scanned = main.load_scan_state(username)["fully_scanned"]
        all_treated = (len(stats["results"]) >= len(items)
                       and not scan_report.get("interrupted"))
        complete = (ended_by in ("exhausted", "incremental")
                    and not stats["extraction_error"] and not critical_error
                    and not stats["stopped"] and all_treated and stats["unknown"] == 0)
        if complete:
            if not was_scanned:
                main.save_scan_state(username, True)
                emit("Scan complet terminé : les prochaines mises à jour seront rapides "
                     "(mode incrémental).", "success")
            stats["scan_complete"] = True
        elif was_scanned and not all_treated:
            main.save_scan_state(username, False)
            stats["scan_complete"] = False
        else:
            stats["scan_complete"] = was_scanned
    except Exception as e:
        emit(f"Impossible de mettre à jour l'état de scan : {e}", "warning")


def run_download(username, platform="tiktok", *, min_sleep=2, max_sleep=6, limit=None,
                 force_update=False, cookies_file=None, cookies_browser=None, workers=1,
                 log=None, progress=None, should_stop=None, sleep=None, forward_extraction_logs=True,
                 items=None):
    """
    Télécharge les nouvelles vidéos et slideshows d'un profil.

    Args:
        username: Nom d'utilisateur (ou URL si platform n'est ni tiktok ni youtube).
        platform: "tiktok" ou "youtube".
        min_sleep, max_sleep: Bornes (secondes) de la pause anti-ban avant chaque élément
            sauf le premier.
        limit: Nombre maximal de nouveaux éléments traités (None = pas de limite).
        force_update: Désactive l'arrêt incrémental de l'extraction ET réessaie tout de
            suite les éléments indisponibles ou en attente de réessai (retry_due). Les succès
            historisés et les éléments ignorés restent TOUJOURS sautés (scan et import).
        cookies_file, cookies_browser: Transmis à toutes les fonctions de main.
        workers: 1 = séquentiel sans thread, en flux continu (téléchargement pendant le
            listing) ; >1 = listing complet d'abord, puis pool de threads (augmente le
            risque de rate-limit).
        log: callable(message, level) avec level dans info/success/warning/error.
        progress: callable(event, data) optionnel. Événements : "item_start", "item_done",
            "extraction_done" (fin du listing, total = éléments listés), "complete".
            Événements additifs : "pause" {seconds} au début de chaque pause anti-ban et
            "pause_end" {} à sa fin (même interrompue) ; "step" {id, step} avec step =
            "detection" puis "telechargement" pendant le traitement d'un élément.
            En flux continu, extraction_done arrive APRÈS les traitements et
            item_start / item_done portent total=None (total inconnu pendant le listing).
        should_stop: callable() -> bool, vérifié pendant l'extraction, entre les
            éléments et pendant les pauses.
        sleep: callable(seconds), injectable pour les tests (défaut time.sleep).
        forward_extraction_logs: True = les logs d'extraction de main.get_video_links sont
            aussi transmis à `log` ; False (CLI) = seulement le print de get_video_links.
        items: liste de dicts {"id", "url"} déjà connus (import de liens). Si fournie : ni
            listing, ni limit, ni mise à jour de scan_state.json, ni save_links_to_file ;
            workers est forcé à 1 et le total est connu dès le début (progress total != None).

    Returns:
        dict: videos, slideshows, failed, unknown, skipped, downloaded (videos+slideshows),
        processed (downloaded+failed), total_extracted, size_mb,
        duration_s, stopped, extraction_error (str | None), full_scan (le run a parcouru
        tout le profil sans arrêt incrémental), scan_complete (état fully_scanned après le run),
        results (liste de dicts par élément traité, avec sa catégorie de tri "category" :
        "new" ou "retry_due").
        Sous-compteurs du tri : skipped = known (déjà téléchargés) + adopted (adoptés depuis
        le disque) + ignored + unavailable + retry_waiting + duplicate + invalid.
        retried = éléments traités qui étaient à retenter ; marked_unavailable = éléments
        devenus indisponibles pendant ce run.
    """
    log_fn = log or _default_log
    should_stop_fn = should_stop or (lambda: False)
    sleep_fn = sleep or time.sleep
    import_mode = items is not None
    workers = 1 if import_mode else max(1, int(workers or 1))
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
        "full_scan": False,
        "scan_complete": False,
        # Sous-compteurs du tri (leur somme = skipped)
        "known": 0,
        "adopted": 0,
        "ignored": 0,
        "unavailable": 0,
        "retry_waiting": 0,
        "duplicate": 0,
        "invalid": 0,
        # Éléments traités qui étaient à retenter / devenus indisponibles pendant ce run
        "retried": 0,
        "marked_unavailable": 0,
        "results": [],
    }
    scan_report = {}
    extracted = []
    import_items = items if import_mode else None
    items = []  # éléments à traiter (après tri)
    categories = {}  # id -> catégorie du tri ('new' | 'retry_due') des éléments à traiter
    total_ref = [None]  # total d'éléments à traiter ; None tant que le listing n'est pas fini
    critical_error = False
    stats_lock = threading.Lock()
    stop_event = threading.Event()
    # Tri : chargé une fois (dans le try principal) ; lstate None tant que non chargé
    tri = {"ctx": None, "lstate": None, "now": None, "adopted_ids": set()}
    # Compteur d'éléments traités depuis la dernière sauvegarde de link_state.json
    state_lock = threading.Lock()
    state_counter = [0]

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
        notify("pause", {"seconds": duration})
        remaining = duration
        try:
            while remaining > 0:
                if stop_requested():
                    return False
                chunk = min(1.0, remaining)
                sleep_fn(chunk)
                remaining -= chunk
            return not stop_requested()
        finally:
            notify("pause_end", {})

    def record_history(video_id, url, item_type, file_size=0, file_count=1, success=True):
        """Appel sérialisé de main.save_to_history (tags / favori / notes conservés)."""
        with _metadata_lock:
            main.save_to_history(username, video_id, url=url, item_type=item_type,
                                 file_size=file_size, file_count=file_count, success=success,
                                 preserve_user_fields=True)

    def save_state():
        """Sauvegarde atomique de link_state.json (sans effet si rien n'a changé)."""
        lstate = tri["lstate"]
        if lstate is None:
            return
        try:
            with state_lock:
                lstate.save()
        except Exception as e:
            emit(f"Impossible de sauvegarder link_state.json : {e}", "warning")

    def state_tick():
        """Un élément traité de plus : sauvegarde périodique de link_state.json."""
        with state_lock:
            state_counter[0] += 1
            due = state_counter[0] >= STATE_SAVE_EVERY
            if due:
                state_counter[0] = 0
        if due:
            save_state()

    def count_skip(category):
        """Élément non traité : sous-compteur de sa catégorie + total skipped."""
        with stats_lock:
            stats["skipped"] += 1
            stats[_SKIP_COUNTERS[category]] += 1

    def adopt(video_id, url, entry):
        """Fichier présent sur le disque mais absent de l'historique : historisé sans
        retéléchargement, état retry/unavailable effacé. Renvoie True si adopté."""
        key = _item_key(video_id)
        kind = entry.kind if entry is not None and entry.kind in ("video", "slideshow") \
            else "video"
        size = int(getattr(entry, "size", 0) or 0)
        file_count = (int(getattr(entry, "image_count", 0) or 0) or 1) \
            if kind == "slideshow" else 1
        try:
            record_history(key, url or _adoption_url(username, key, kind), kind,
                           file_size=size, file_count=file_count, success=True)
        except Exception as e:
            emit(f"Adoption impossible de {key} : {e}", "warning")
            return False
        tri["lstate"].clear(key)
        tri["ctx"].history_success.add(key)
        tri["adopted_ids"].add(key)
        count_skip("adopt")
        return True

    def record_failure(video_id, detail):
        """Échec d'un élément : classement de l'erreur puis état dans link_state.json.
        Renvoie (reason, statut, entrée d'état)."""
        kind, reason = download_errors.classify_error(detail)
        lstate = tri["lstate"]
        status = lstate.record_failure(video_id, kind, detail)
        if status == "unavailable" and kind == "permanent":
            lstate.mark_unavailable(video_id, reason, detail)  # raison lisible
        if status == "unavailable":
            with stats_lock:
                stats["marked_unavailable"] += 1
        return reason, status, lstate.get(video_id)

    def finish(result, index, item_start):
        """Enregistre le résultat et émet l'événement de fin d'élément."""
        result["duration_s"] = time.monotonic() - item_start
        with stats_lock:
            stats["results"].append(result)
            done = len(stats["results"])
            size_mb = stats["size_mb"]
        state_tick()
        notify("item_done", {**result, "total": total_ref[0], "done": done,
                             "total_size_mb": size_mb,
                             "elapsed_s": time.monotonic() - start})
        return result

    def process_item(item, index):
        """Traite un élément ; ne lève jamais. Renvoie le dict résultat."""
        video_id = item["id"]
        url = item["url"]
        key = _item_key(video_id)
        category = categories.get(key, "new")
        result = {"index": index, "id": video_id, "url": url, "type": None, "success": False,
                  "files": [], "file_count": 0, "size": 0, "error": None,
                  "category": category, "reason": None, "link_status": None}
        total = total_ref[0]
        label = f"[{index + 1}/{total}]" if total else f"[{index + 1}]"
        notify("item_start", {"index": index, "total": total, "id": video_id, "url": url})
        item_start = time.monotonic()
        if category == "retry_due":
            with stats_lock:
                stats["retried"] += 1

        # 1. Détection du type. Une exception ici = type inconnu (pas d'historique).
        notify("step", {"id": video_id, "step": "detection"})
        probe_exc = None
        main.reset_last_error()
        try:
            flag = main.is_slideshow(url, username=username,
                                     cookies_browser=cookies_browser,
                                     cookies_file=cookies_file)
        except Exception as e:
            flag = None
            probe_exc = e
            result["error"] = f"détection du type : {e}"

        if flag is None:
            detail = main.last_error() or (str(probe_exc) if probe_exc is not None else "")
            kind, reason = download_errors.classify_error(detail)
            if detail and kind == "permanent":
                # Vidéo supprimée / privée... : indisponible, jamais rejouée comme « type inconnu »
                result["type"] = "unavailable"
                result["reason"] = reason
                result["error"] = result["error"] or f"détection du type : {detail}"
                try:
                    tri["lstate"].mark_unavailable(key, reason, detail)
                    result["link_status"] = tri["lstate"].status(key)
                except Exception as e:
                    emit(f"{label} Impossible d'enregistrer l'état de {video_id} : {e}", "error")
                with stats_lock:
                    stats["failed"] += 1
                    stats["processed"] += 1
                    if result["link_status"] == "unavailable":
                        stats["marked_unavailable"] += 1
                emit(f"{label} {video_id} indisponible : {reason} ({detail})", "error")
                return finish(result, index, item_start)

            result["type"] = "unknown"
            result["error"] = result["error"] or "type inconnu (cookies / réseau / yt-dlp ?)"
            result["reason"] = reason
            try:
                _, status, entry = record_failure(key, detail or result["error"])
                result["link_status"] = status
                retry = _retry_text(entry)
            except Exception as e:
                retry = ""
                emit(f"{label} Impossible d'enregistrer l'état de {video_id} : {e}", "error")
            emit(f"{label} Type inconnu pour {video_id} ({result['error']}) - ignoré, "
                 f"réessai plus tard" + (f" : {retry}" if retry else ""), "error")
            with stats_lock:
                stats["unknown"] += 1
            return finish(result, index, item_start)

        item_type = "slideshow" if flag else "video"
        result["type"] = item_type

        # 2. Téléchargement + vérification + historique
        notify("step", {"id": video_id, "step": "telechargement"})
        main.reset_last_error()
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
            download_exc = str(e)
        else:
            download_exc = None

        if result["success"]:
            try:
                tri["lstate"].clear(key)
            except Exception as e:
                emit(f"{label} Impossible d'effacer l'état de {video_id} : {e}", "warning")
        else:
            with stats_lock:
                stats["failed"] += 1
                stats["processed"] += 1
            # L'échec n'est plus écrit dans metadata.json : link_state.json fait foi
            detail = main.last_error() or download_exc or result["error"]
            retry = ""
            try:
                reason, status, entry = record_failure(key, detail)
                result.update(reason=reason, link_status=status)
                retry = f"{reason} - {_retry_text(entry)}"
            except Exception as e:
                emit(f"{label} Impossible d'enregistrer l'échec de {video_id} : {e}", "error")
            emit(f"{label} Échec ({item_type}) : {result['error']}"
                 + (f" ({retry})" if retry else ""), "error")

        return finish(result, index, item_start)

    def task(item, index):
        """Tâche complète d'un élément : pause anti-ban (sauf le premier) puis traitement."""
        if stop_requested():
            return None
        if index > 0 and not pause():
            return None
        if stop_requested():
            return None
        return process_item(item, index)

    def classify(key):
        return triage.classify_id(key, tri["ctx"], force_update=force_update, now=tri["now"])

    def run_body():
        # ---------------------------------------------------------------- tri (chargement)
        # Lecture seule : aucun dossier n'est créé tant qu'il n'y a rien à écrire.
        user_dir = main.get_user_dir(username)
        history_success, history_failed = main.load_history_split(username)
        disk = disk_index.scan_profile_dir(user_dir)
        lstate = link_state.LinkState.load(user_dir)
        if lstate.recovered_from_corruption:
            emit("link_state.json illisible : mis de côté (.corrupt-*), états repartis de zéro",
                 "warning")
        ctx = triage.TriageContext(history_success=set(history_success),
                                   history_failed=set(history_failed) - set(history_success),
                                   disk=disk, state=lstate.items())
        tri.update(ctx=ctx, lstate=lstate, now=datetime.now())
        if force_update:
            emit("Mode MAJ forcée activé", "warning")

        # ---------------------------------------------------------------- listing
        # workers == 1 : flux continu (chaque élément est traité dès qu'il est listé).
        # workers > 1 : le listing est collecté en entier, puis traité par le pool.
        streaming = workers == 1
        known = set()
        if import_mode:
            # Import : la liste fournie remplace le listing ; tri en amont, adoptions en lot
            plan = triage.classify_links(import_items, ctx, force_update=force_update,
                                         now=tri["now"])
            for item, entry in plan.to_adopt:
                adopt(item.get("id"), item.get("url"), entry)
            total_ref[0] = len(plan.to_process) or None  # total connu dès le départ
            emit(f"Import de {len(import_items)} lien(s) pour @{username} "
                 f"({len(plan.to_process)} à traiter)", "info")
            c = plan.counts
            extra = [f"{n} {label}" for n, label in (
                (c["retry_waiting"], "en attente de réessai"), (c["duplicate"], "doublon(s)"),
                (c["invalid"], "invalide(s)")) if n]
            emit(f"{plan.total} liens : {c['downloaded']} déjà téléchargés, "
                 f"{c['adopt']} adoptés depuis le disque, {c['retry_due']} à retenter, "
                 f"{c['ignored']} ignorés, {c['unavailable']} indisponibles, "
                 f"{c['new']} nouveaux" + (", " + ", ".join(extra) if extra else ""), "info")
        else:
            # Fichiers présents sur le disque mais absents de l'historique : adoptés en lot
            for key in sorted(disk):
                if classify(key) == "adopt":
                    adopt(key, None, disk[key])
            if stats["adopted"]:
                emit(f"{stats['adopted']} élément(s) déjà présent(s) sur le disque ajouté(s) "
                     "à l'historique (non retéléchargés)", "info")
            # Ids « connus » pour l'arrêt incrémental et le saut : succès, adoptés, ignorés,
            # indisponibles, réessais non échus. retry_due et new n'en font jamais partie.
            candidates = (set(ctx.history_success) | set(ctx.history_failed) | set(disk)
                          | set(ctx.state))
            known = {k for k in candidates if classify(k) in _KNOWN_CATEGORIES}
            emit(f"Analyse du profil @{username}...", "info")
        if streaming and not import_mode:
            emit("Téléchargement au fil du listing (flux continu)", "info")
        seen = set()
        generator = None
        try:
            try:
                scan_report.clear()
                generator = list(import_items) if import_mode else main.get_video_links(
                    username, known, platform, limit=limit,
                    # Log par défaut : get_video_links affiche déjà ses messages (pas de doublon)
                    callback_log=log if forward_extraction_logs else None,
                    force_update=force_update,
                    cookies_browser=cookies_browser, cookies_file=cookies_file,
                    scan_report=scan_report,
                )
                iterator = iter(generator or ())
            except Exception as e:
                iterator = iter(())
                stats["extraction_error"] = str(e)
                emit(f"Erreur d'extraction : {e}", "error")

            while stats["extraction_error"] is None:
                try:
                    video = next(iterator)
                except StopIteration:
                    break
                except Exception as e:
                    stats["extraction_error"] = str(e)
                    emit(f"Erreur d'extraction : {e}", "error")
                    break
                if stop_requested():
                    emit("Arrêt demandé pendant l'extraction", "warning")
                    scan_report["interrupted"] = True  # éléments listés non traités
                    break
                extracted.append(video)
                stats["total_extracted"] = len(extracted)

                # Tri de l'élément (mêmes règles que triage.classify_links)
                is_dict = isinstance(video, dict)
                raw_id = video.get("id") if is_dict else None
                key = _item_key(raw_id)
                if not key or not (video.get("url") if is_dict else None):
                    category = "invalid"
                elif key in seen:
                    category = "duplicate"
                else:
                    seen.add(key)
                    # Adopté en lot au début du run : déjà compté
                    category = None if key in tri["adopted_ids"] else classify(key)
                if category in ("new", "retry_due"):
                    categories[key] = category
                    items.append(video)
                    if streaming and task(video, len(items) - 1) is None and stop_requested():
                        break
                elif category == "adopt":
                    if not adopt(raw_id, video.get("url"), disk.get(key)):
                        count_skip("adopt")
                elif category is not None:
                    count_skip(category)
                if limit and len(extracted) >= limit:
                    break
        finally:
            # Ferme le générateur (termine gallery-dl) puis sauvegarde les liens listés
            close = getattr(generator, "close", None)
            if close:
                try:
                    close()
                except Exception as e:
                    emit(f"Fermeture du listing : {e}", "warning")
            if extracted and not import_mode:
                try:
                    main.save_links_to_file(username, extracted)
                except Exception as e:
                    emit(f"Impossible de sauvegarder les liens : {e}", "warning")

        stats["total_extracted"] = len(extracted)
        notify("extraction_done", {"total": len(extracted)})
        if not import_mode and stats["skipped"]:
            emit(f"Tri : {stats['known']} déjà téléchargé(s), {stats['adopted']} adopté(s), "
                 f"{stats['ignored']} ignoré(s), {stats['unavailable']} indisponible(s), "
                 f"{stats['retry_waiting']} en attente de réessai", "info")

        if not items:
            if not stop_requested():
                emit("Aucune nouvelle vidéo à télécharger", "warning")
        elif not streaming and not stop_requested():
            total = total_ref[0] = len(items)
            emit(f"Démarrage du téléchargement de {total} élément(s)", "info")
            emit(f"Mode parallèle : {workers} workers (risque de rate-limit accru)",
                 "warning")
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [executor.submit(task, item, index)
                           for index, item in enumerate(items)]
                for future in futures:
                    try:
                        future.result()
                    except Exception as e:  # filet de sécurité, task ne lève pas
                        emit(f"Erreur inattendue d'un worker : {e}", "error")

    try:
        try:
            run_body()
        except Exception as e:
            critical_error = True
            emit(f"Erreur critique : {e}", "error")
    finally:
        # link_state.json : toujours sauvegardé (fin normale, arrêt, limite, exception)
        save_state()

    stats["stopped"] = stop_event.is_set()
    if import_mode:
        # Un import ne modifie jamais scan_state.json (lecture seule pour le rapport)
        try:
            stats["scan_complete"] = main.load_scan_state(username)["fully_scanned"]
        except Exception:
            pass
    else:
        _update_scan_state(username, stats, scan_report, items, critical_error, emit)
    if stats["stopped"]:
        emit(f"Arrêt demandé pour @{username}", "warning")
    stats["duration_s"] = time.monotonic() - start
    # Ordre d'extraction des résultats, même en parallèle
    stats["results"].sort(key=lambda r: r["index"])
    notify("complete", {k: v for k, v in stats.items() if k != "results"})
    return stats


def run_import(username, items, *, min_sleep=2, max_sleep=6, cookies_file=None,
               cookies_browser=None, force_update=False, log=None, progress=None,
               should_stop=None, sleep=None):
    """Télécharge une liste de liens déjà connue (exportée depuis le navigateur).

    Mince enveloppe de run_download(items=...) : même boucle, mêmes statistiques, aucun
    listing et aucune modification de scan_state.json. `items` : liste de {"id", "url"}.
    """
    return run_download(username, "tiktok", min_sleep=min_sleep, max_sleep=max_sleep,
                        force_update=force_update, cookies_file=cookies_file,
                        cookies_browser=cookies_browser, log=log, progress=progress,
                        should_stop=should_stop, sleep=sleep, items=items)
