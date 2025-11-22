"""
Pipeline de téléchargement ultra-rapide
Combine extraction + téléchargement en streaming pour performance maximale
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue, Empty
import threading
import time
from main import (
    get_video_links,
    download_video,
    download_slideshow,
    is_slideshow,
    save_to_history,
    append_link_to_file,
    get_user_dir
)
import os


class PipelineDownloader:
    """
    Téléchargeur en pipeline

    Principe:
    - Thread 1: Extrait les liens (générateur)
    - Thread 2-4: Téléchargent en parallèle dès qu'un lien arrive

    Avantages:
    - Commence à télécharger immédiatement
    - Pas d'attente de fin d'extraction
    - Téléchargements parallèles
    - 5-10x plus rapide qu'avant
    """

    def __init__(self, max_workers=3, queue_size=10):
        """
        Args:
            max_workers: Nombre de téléchargements simultanés
            queue_size: Taille du buffer (nombre de vidéos en attente)
        """
        self.max_workers = max_workers
        self.queue_size = queue_size
        self.video_queue = Queue(maxsize=queue_size)
        self.extraction_done = threading.Event()
        self.stats = {
            'extracted': 0,
            'downloaded': 0,
            'failed': 0,
            'slideshows': 0
        }
        self.stats_lock = threading.Lock()

    def download_with_pipeline(self, username, platform='tiktok',
                               min_sleep=0, max_sleep=0,
                               force_update=False,
                               limit=None,
                               progress_callback=None):
        """
        Télécharge avec pipeline extraction->téléchargement

        Args:
            username: Nom d'utilisateur TikTok
            platform: Plateforme (tiktok, youtube)
            min_sleep: Délai minimum (ignoré en mode pipeline)
            max_sleep: Délai maximum (ignoré en mode pipeline)
            force_update: Force le scan complet
            limit: Limite de vidéos
            progress_callback: Fonction callback(event_type, data)

        Returns:
            dict: Statistiques finales
        """
        from main import load_history

        # Réinitialiser
        self.extraction_done.clear()
        self.stats = {'extracted': 0, 'downloaded': 0, 'failed': 0, 'slideshows': 0}

        # Charger historique
        history = load_history(username)

        # Callback pour logs
        def log_callback(msg, level="info"):
            if progress_callback:
                progress_callback('log', {'message': msg, 'level': level})

        # Thread 1: Extraction
        extractor_thread = threading.Thread(
            target=self._extractor_worker,
            args=(username, history, platform, limit, force_update, log_callback, progress_callback),
            daemon=True
        )

        # Threads 2-N: Téléchargements
        download_futures = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Démarrer l'extracteur
            extractor_thread.start()

            # Lancer les workers de téléchargement
            for i in range(self.max_workers):
                future = executor.submit(
                    self._downloader_worker,
                    username,
                    progress_callback
                )
                download_futures.append(future)

            # Attendre la fin de l'extraction
            extractor_thread.join()

            # Signaler que l'extraction est terminée
            self.extraction_done.set()

            # Attendre que tous les téléchargements soient finis
            for future in as_completed(download_futures):
                try:
                    future.result()
                except Exception as e:
                    if progress_callback:
                        progress_callback('error', {'message': f'Download worker error: {e}'})

        # Statistiques finales
        if progress_callback:
            progress_callback('complete', self.stats)

        return self.stats

    def _extractor_worker(self, username, history, platform, limit,
                         force_update, log_callback, progress_callback):
        """Thread d'extraction - alimente la queue"""
        try:
            # Générateur de vidéos
            video_generator = get_video_links(
                username,
                history,
                platform,
                limit=limit,
                callback_log=log_callback,
                force_update=force_update
            )

            # Alimenter la queue au fur et à mesure
            for video in video_generator:
                # Ajouter à la queue (bloque si pleine)
                self.video_queue.put(video)

                # Stats
                with self.stats_lock:
                    self.stats['extracted'] += 1

                # Sauvegarder le lien immédiatement
                append_link_to_file(username, video['url'])

                # Callback
                if progress_callback and self.stats['extracted'] % 5 == 0:
                    progress_callback('extraction_progress', {
                        'count': self.stats['extracted']
                    })

        except Exception as e:
            if progress_callback:
                progress_callback('error', {'message': f'Extraction error: {e}'})

        finally:
            # Signaler la fin (les downloaders verront la queue vide + flag)
            if progress_callback:
                progress_callback('extraction_done', {
                    'total': self.stats['extracted']
                })

    def _downloader_worker(self, username, progress_callback):
        """Thread de téléchargement - consomme la queue"""
        user_dir = get_user_dir(username)

        while True:
            try:
                # Essayer de récupérer une vidéo (timeout 1s)
                try:
                    video = self.video_queue.get(timeout=1)
                except Empty:
                    # Queue vide - vérifier si extraction terminée
                    if self.extraction_done.is_set():
                        break
                    continue

                video_id = video['id']
                video_url = video['url']

                # Détecter le type (avec cache)
                start_time = time.time()
                item_type = 'slideshow' if is_slideshow(video_url, username=username) else 'video'

                # Télécharger
                if item_type == 'slideshow':
                    success = download_slideshow(video_url, username, video_id)

                    if success:
                        # Compter images
                        image_count = 0
                        for f in os.listdir(user_dir):
                            if video_id in f and f.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                                image_count += 1

                        save_to_history(username, video_id, url=video_url,
                                      item_type="slideshow", file_size=0,
                                      file_count=image_count, success=True)

                        with self.stats_lock:
                            self.stats['slideshows'] += 1
                            self.stats['downloaded'] += 1

                        if progress_callback:
                            progress_callback('slideshow_complete', {
                                'id': video_id,
                                'image_count': image_count,
                                'duration': time.time() - start_time
                            })
                    else:
                        with self.stats_lock:
                            self.stats['failed'] += 1
                        save_to_history(username, video_id, url=video_url,
                                      item_type="slideshow", success=False)

                else:  # video
                    success = download_video(video_url, username, video_id)

                    if success:
                        # Trouver taille
                        file_size = 0
                        filename = None
                        for f in os.listdir(user_dir):
                            if video_id in f and f.endswith('.mp4'):
                                filename = f
                                file_path = os.path.join(user_dir, f)
                                file_size = os.path.getsize(file_path)
                                break

                        save_to_history(username, video_id, url=video_url,
                                      item_type="video", file_size=file_size, success=True)

                        with self.stats_lock:
                            self.stats['downloaded'] += 1

                        if progress_callback:
                            progress_callback('video_complete', {
                                'id': video_id,
                                'filename': filename,
                                'size_mb': file_size / (1024 * 1024),
                                'duration': time.time() - start_time
                            })
                    else:
                        with self.stats_lock:
                            self.stats['failed'] += 1
                        save_to_history(username, video_id, url=video_url,
                                      item_type="video", success=False)

                # Marquer la tâche comme terminée
                self.video_queue.task_done()

            except Exception as e:
                with self.stats_lock:
                    self.stats['failed'] += 1
                if progress_callback:
                    progress_callback('error', {'message': f'Download error: {e}'})


def download_with_streaming_pipeline(username, platform='tiktok',
                                     max_workers=3, limit=None,
                                     progress_callback=None):
    """
    Fonction helper pour télécharger avec pipeline

    Args:
        username: Nom d'utilisateur
        platform: Plateforme (tiktok, youtube)
        max_workers: Nombre de workers parallèles
        limit: Limite de vidéos
        progress_callback: Fonction callback(event_type, data)

    Returns:
        dict: Statistiques
    """
    pipeline = PipelineDownloader(max_workers=max_workers)

    # Callback de progression par défaut
    def default_callback(event_type, data):
        if event_type == 'log':
            print(f"[{data['level'].upper()}] {data['message']}")
        elif event_type == 'extraction_progress':
            print(f"Extraction: {data['count']} vidéos trouvées...")
        elif event_type == 'extraction_done':
            print(f"Extraction terminée: {data['total']} vidéos")
        elif event_type == 'video_complete':
            print(f"Video OK: {data['filename']} ({data['size_mb']:.1f}MB en {data['duration']:.1f}s)")
        elif event_type == 'slideshow_complete':
            print(f"Slideshow OK: {data['image_count']} images en {data['duration']:.1f}s")
        elif event_type == 'complete':
            print(f"\nTerminé! {data['downloaded']} téléchargés, {data['failed']} échecs")
        elif event_type == 'error':
            print(f"ERREUR: {data['message']}")

    callback = progress_callback or default_callback

    return pipeline.download_with_pipeline(
        username=username,
        platform=platform,
        limit=limit,
        progress_callback=callback
    )


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python pipeline_downloader.py <username> [max_workers] [limit]")
        print("Example: python pipeline_downloader.py lapukipuks 3 10")
        sys.exit(1)

    username = sys.argv[1]
    max_workers = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else None

    print(f"Pipeline Download: @{username}")
    print(f"Workers: {max_workers}")
    print(f"Limit: {limit or 'Aucune'}")
    print("-" * 50)

    start = time.time()
    stats = download_with_streaming_pipeline(
        username=username,
        max_workers=max_workers,
        limit=limit
    )
    duration = time.time() - start

    print("\n" + "=" * 50)
    print(f"STATISTIQUES FINALES")
    print("=" * 50)
    print(f"Durée totale: {duration:.1f}s")
    print(f"Vidéos extraites: {stats['extracted']}")
    print(f"Téléchargements réussis: {stats['downloaded']}")
    print(f"  - Vidéos: {stats['downloaded'] - stats['slideshows']}")
    print(f"  - Slideshows: {stats['slideshows']}")
    print(f"Échecs: {stats['failed']}")
    if stats['downloaded'] > 0:
        print(f"Vitesse: {stats['downloaded'] / duration:.2f} vidéos/seconde")
