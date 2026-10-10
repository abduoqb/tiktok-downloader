"""
Module pour téléchargements parallèles
Télécharge plusieurs vidéos simultanément pour améliorer les performances
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from main import download_video, download_slideshow, is_slideshow


class ParallelDownloader:
    """Gestionnaire de téléchargements parallèles"""

    def __init__(self, max_workers=3):
        """
        Initialize parallel downloader

        Args:
            max_workers: Nombre de téléchargements simultanés (défaut: 3)
        """
        self.max_workers = max_workers

    def download_videos(self, items, username, progress_callback=None):
        """
        Télécharge plusieurs vidéos en parallèle

        Args:
            items: Liste de dictionnaires {'url': ..., 'id': ..., 'type': ...}
            username: Nom d'utilisateur
            progress_callback: Fonction appelée pour chaque vidéo (item, success, index, total)

        Returns:
            dict: {'success': count, 'failed': count, 'results': [...]}
        """
        total = len(items)
        success_count = 0
        failed_count = 0
        results = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Soumettre toutes les tâches
            future_to_item = {}
            for index, item in enumerate(items):
                future = executor.submit(
                    self._download_single_item,
                    item,
                    username
                )
                future_to_item[future] = (item, index)

            # Récupérer les résultats au fur et à mesure
            for future in as_completed(future_to_item):
                item, index = future_to_item[future]
                try:
                    success, file_info = future.result()

                    if success:
                        success_count += 1
                    else:
                        failed_count += 1

                    result = {
                        'item': item,
                        'success': success,
                        'file_info': file_info,
                        'index': index
                    }
                    results.append(result)

                    # Callback de progression
                    if progress_callback:
                        progress_callback(item, success, index + 1, total, file_info)

                except Exception as e:
                    failed_count += 1
                    result = {
                        'item': item,
                        'success': False,
                        'error': str(e),
                        'index': index
                    }
                    results.append(result)

                    if progress_callback:
                        progress_callback(item, False, index + 1, total, {'error': str(e)})

        return {
            'success': success_count,
            'failed': failed_count,
            'total': total,
            'results': sorted(results, key=lambda x: x['index'])  # Tri par ordre original
        }

    def _download_single_item(self, item, username):
        """
        Télécharge un seul élément (vidéo ou slideshow)

        Args:
            item: Dictionnaire {'url': ..., 'id': ..., 'type': ...}
            username: Nom d'utilisateur

        Returns:
            tuple: (success: bool, file_info: dict)
        """
        import os
        from main import get_user_dir, find_downloaded_videos

        video_id = item['id']
        video_url = item['url']
        item_type = item['type']

        start_time = time.time()

        # Type inconnu (is_slideshow() a renvoyé None) : erreur, ne pas traiter comme une vidéo normale
        if item_type not in ('slideshow', 'video'):
            return False, {'type': 'unknown', 'error': 'Type inconnu (slideshow/vidéo), réessayer plus tard'}

        try:
            if item_type == 'slideshow':
                success = download_slideshow(video_url, username, video_id)

                if success:
                    # Compter les images
                    user_dir = get_user_dir(username)
                    image_count = 0
                    for f in os.listdir(user_dir):
                        if video_id in f and f.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                            image_count += 1

                    return True, {
                        'type': 'slideshow',
                        'file_count': image_count,
                        'duration': time.time() - start_time
                    }
                else:
                    return False, {'type': 'slideshow', 'error': 'Download failed'}

            else:  # video
                success = download_video(video_url, username, video_id)

                # Fichier vérifié obligatoire pour signaler un succès
                video_files = find_downloaded_videos(username, video_id) if success else []

                if success and video_files:
                    # Trouver le fichier et obtenir sa taille
                    file_path = video_files[0]
                    filename = os.path.basename(file_path)
                    file_size = os.path.getsize(file_path)

                    return True, {
                        'type': 'video',
                        'filename': filename,
                        'size': file_size,
                        'size_mb': file_size / (1024 * 1024),
                        'duration': time.time() - start_time
                    }
                else:
                    return False, {'type': 'video', 'error': 'Download failed'}

        except Exception as e:
            return False, {'error': str(e), 'type': item_type}


def download_batch_parallel(items, username, max_workers=3, min_sleep=0, max_sleep=0):
    """
    Fonction helper pour télécharger un batch en parallèle

    Args:
        items: Liste d'items à télécharger
        username: Nom d'utilisateur
        max_workers: Nombre de workers parallèles
        min_sleep: Délai minimum entre batches (ignoré en mode parallèle)
        max_sleep: Délai maximum entre batches (ignoré en mode parallèle)

    Returns:
        dict: Résultats du téléchargement
    """
    downloader = ParallelDownloader(max_workers=max_workers)

    def progress(item, success, current, total, file_info):
        """Callback de progression"""
        status = "OK" if success else "FAIL"
        item_type = file_info.get('type', 'unknown')

        if success and item_type == 'video':
            size_mb = file_info.get('size_mb', 0)
            duration = file_info.get('duration', 0)
            print(f"[{current}/{total}] Video OK - {size_mb:.1f} MB ({duration:.1f}s)")
        elif success and item_type == 'slideshow':
            file_count = file_info.get('file_count', 0)
            duration = file_info.get('duration', 0)
            print(f"[{current}/{total}] Slideshow OK - {file_count} images ({duration:.1f}s)")
        else:
            error = file_info.get('error', 'Unknown error')
            print(f"[{current}/{total}] {status} - {error}")

    return downloader.download_videos(items, username, progress_callback=progress)


if __name__ == "__main__":
    # Test simple
    test_items = [
        {'url': 'https://www.tiktok.com/@test/video/123', 'id': '123', 'type': 'video'},
        {'url': 'https://www.tiktok.com/@test/video/456', 'id': '456', 'type': 'video'},
    ]

    result = download_batch_parallel(test_items, "test_user", max_workers=2)
    print(f"\nRésultat: {result['success']} succès, {result['failed']} échecs")
