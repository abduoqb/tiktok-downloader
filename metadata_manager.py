"""
Optimized Metadata Manager for TikTok Scraper
Uses JSON with in-memory caching for O(1) lookups
"""
import json
import os
import shutil
from datetime import datetime
from collections import defaultdict


class OptimizedMetadataManager:
    """
    Gestionnaire de métadonnées optimisé avec cache en mémoire

    Amélioration de performance:
    - Vérifications O(1) au lieu de O(n)
    - Cache pour is_slideshow() (évite 99% des appels API)
    - Un seul fichier metadata.json au lieu de 3
    - Métadonnées riches: type, date, taille, statut
    """

    def __init__(self, username, user_dir):
        self.username = username
        self.user_dir = user_dir
        self.metadata_file = os.path.join(user_dir, "metadata.json")

        # Caches en mémoire pour performances O(1)
        self._metadata = None
        self._id_set = None  # Set pour O(1) lookup
        self._slideshow_cache = {}  # Cache is_slideshow results

    def load(self):
        """Charge les métadonnées une seule fois et met en cache"""
        if self._metadata is not None:
            return self._metadata

        if not os.path.exists(self.metadata_file):
            self._metadata = {}
            self._id_set = set()
            return self._metadata

        try:
            with open(self.metadata_file, "r", encoding="utf-8") as f:
                self._metadata = json.load(f)

            # Créer le set pour recherches O(1)
            self._id_set = set(self._metadata.keys())

            # Charger le cache slideshow depuis les métadonnées
            for vid_id, data in self._metadata.items():
                if data.get('type') and data.get('url'):
                    self._slideshow_cache[data['url']] = (data['type'] == 'slideshow')

        except Exception as e:
            print(f"Error loading metadata: {e}")
            self._metadata = {}
            self._id_set = set()

        return self._metadata

    def is_downloaded(self, video_id):
        """
        Vérifie si une vidéo a déjà été téléchargée
        Performance: O(1) grâce au set
        """
        self.load()
        return video_id in self._id_set

    def get_slideshow_type_from_cache(self, video_url):
        """
        Récupère le type (slideshow ou non) depuis le cache
        Retourne None si pas en cache
        """
        return self._slideshow_cache.get(video_url)

    def cache_slideshow_type(self, video_url, is_slideshow):
        """Met en cache le résultat d'un appel is_slideshow()"""
        self._slideshow_cache[video_url] = is_slideshow

    def add(self, video_id, url, item_type, file_size=0, file_count=1, success=True):
        """
        Ajoute un téléchargement avec métadonnées

        Args:
            video_id: ID unique de la vidéo
            url: URL de la vidéo
            item_type: "video" ou "slideshow"
            file_size: Taille en octets (0 pour slideshows)
            file_count: Nombre de fichiers (>1 pour slideshows)
            success: True si téléchargement réussi
        """
        self.load()

        self._metadata[video_id] = {
            "url": url,
            "type": item_type,
            "date": datetime.now().isoformat(),
            "size": file_size,
            "file_count": file_count,
            "success": success
        }

        # Mise à jour des caches
        self._id_set.add(video_id)
        self._slideshow_cache[url] = (item_type == 'slideshow')

        # Sauvegarde
        self._save()

    def mark_as_failed(self, video_id, url, item_type):
        """Marque un téléchargement comme échoué"""
        self.add(video_id, url, item_type, file_size=0, success=False)

    def _save(self):
        """Sauvegarde avec backup automatique"""
        try:
            # Backup de sécurité avant écrasement
            if os.path.exists(self.metadata_file):
                backup = self.metadata_file + '.backup'
                shutil.copy2(self.metadata_file, backup)

            # Sauvegarde atomique (write to temp then rename)
            temp_file = self.metadata_file + '.tmp'
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self._metadata, f, indent=2)

            # Atomic rename
            if os.path.exists(self.metadata_file):
                os.remove(self.metadata_file)
            os.rename(temp_file, self.metadata_file)

        except Exception as e:
            print(f"Error saving metadata: {e}")
            # En cas d'erreur, on essaie de restaurer le backup
            backup = self.metadata_file + '.backup'
            if os.path.exists(backup):
                shutil.copy2(backup, self.metadata_file)

    def get_stats(self):
        """
        Retourne des statistiques depuis le cache

        Returns:
            dict: {"video": {"count": X, "size": Y}, "slideshow": {...}}
        """
        self.load()
        stats = defaultdict(lambda: {"count": 0, "size": 0, "file_count": 0})

        for data in self._metadata.values():
            if data.get('success', True):
                item_type = data.get('type', 'video')
                stats[item_type]["count"] += 1
                stats[item_type]["size"] += data.get('size', 0)
                stats[item_type]["file_count"] += data.get('file_count', 1)

        return dict(stats)

    def get_failed_downloads(self):
        """
        Retourne la liste des téléchargements échoués

        Returns:
            list: [{"id": "123", "url": "...", "type": "video"}, ...]
        """
        self.load()
        failed = []

        for vid_id, data in self._metadata.items():
            if not data.get('success', True):
                failed.append({
                    "id": vid_id,
                    "url": data.get('url'),
                    "type": data.get('type'),
                    "date": data.get('date')
                })

        return failed

    def get_all_ids(self):
        """
        Retourne la liste de tous les IDs téléchargés (pour compatibilité)

        Returns:
            list: Liste des IDs
        """
        self.load()
        return list(self._id_set)

    def export_to_legacy_format(self):
        """
        Exporte vers l'ancien format pour compatibilité
        Crée download_history.json avec juste les IDs
        """
        self.load()
        legacy_file = os.path.join(self.user_dir, "download_history.json")

        # Liste simple des IDs comme avant
        ids = [vid_id for vid_id, data in self._metadata.items()
               if data.get('success', True)]

        try:
            with open(legacy_file, "w", encoding="utf-8") as f:
                json.dump(ids, f, indent=4)
        except Exception as e:
            print(f"Error exporting to legacy format: {e}")


def migrate_from_legacy(username, user_dir):
    """
    Migration depuis l'ancien système vers le nouveau

    Migre:
    - download_history.json -> metadata.json
    - slideshows.json -> metadata.json
    - username_videos.txt -> metadata.json (URLs)

    Args:
        username: Nom d'utilisateur
        user_dir: Répertoire de l'utilisateur

    Returns:
        OptimizedMetadataManager: Instance avec données migrées
    """
    manager = OptimizedMetadataManager(username, user_dir)

    # Vérifier si migration déjà effectuée
    if os.path.exists(manager.metadata_file):
        print(f"Metadata already exists for {username}, skipping migration")
        return manager

    migrated_count = 0

    # 1. Migrer download_history.json
    history_file = os.path.join(user_dir, "download_history.json")
    if os.path.exists(history_file):
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                history = json.load(f)

            for video_id in history:
                # On ne connaît pas le type, on met "video" par défaut
                manager.add(video_id, "", "video", success=True)
                migrated_count += 1

            print(f"Migrated {len(history)} entries from download_history.json")
        except Exception as e:
            print(f"Error migrating history: {e}")

    # 2. Migrer slideshows.json
    slideshow_file = os.path.join(user_dir, "slideshows.json")
    if os.path.exists(slideshow_file):
        try:
            with open(slideshow_file, "r", encoding="utf-8") as f:
                slideshows = json.load(f)

            for item in slideshows:
                video_id = item.get('id')
                url = item.get('url', '')
                if video_id:
                    manager.add(video_id, url, "slideshow", success=True)
                    migrated_count += 1

            print(f"Migrated {len(slideshows)} slideshows from slideshows.json")
        except Exception as e:
            print(f"Error migrating slideshows: {e}")

    # 3. Enrichir avec les URLs depuis username_videos.txt
    videos_file = os.path.join(user_dir, f"{username}_videos.txt")
    if os.path.exists(videos_file):
        try:
            with open(videos_file, "r", encoding="utf-8") as f:
                urls = [line.strip() for line in f if line.strip()]

            # Essayer de matcher les URLs avec les IDs existants
            manager.load()
            for url in urls:
                # Extraire l'ID de l'URL TikTok
                try:
                    if '/video/' in url:
                        video_id = url.split('/video/')[1].split('?')[0]
                        if video_id in manager._metadata:
                            # Mettre à jour l'URL
                            manager._metadata[video_id]['url'] = url
                except:
                    pass

            manager._save()
            print(f"Enriched with URLs from {username}_videos.txt")
        except Exception as e:
            print(f"Error enriching with URLs: {e}")

    print(f"Migration complete: {migrated_count} total entries migrated for {username}")
    return manager
