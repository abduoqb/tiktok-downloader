# Changelog

Tous les changements notables de ce projet seront documentés dans ce fichier.

Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/),
et ce projet adhère au [Semantic Versioning](https://semver.org/lang/fr/).

## [1.6.0] - 2026-10-10

### Ajouté
- **Orchestrateur unique** (`orchestrator.py`) : `run_download()` est le seul point d'entrée de téléchargement, utilisé par le CLI (`main.py --download`) et par l'interface web (`background_download_task`)
- **Options yt-dlp / cookies centralisées** dans `ytdlp_options.py` (`build_ydl_opts`, `default_cookies_file`, ...)
- Tests : `tests/test_orchestrator.py`, `tests/test_ytdlp_options.py`, `tests/test_web_download.py`

### Corrigé
- **Limite ignorée dans l'interface web** : `POST /api/download` lit `limit` (entier positif ou `null`, sinon 400) et le transmet jusqu'à `run_download`

### Supprimé
- `pipeline_downloader.py` et `parallel_downloader.py` (remplacés par l'orchestrateur) et leurs références dans la documentation
- Calcul dupliqué du chemin du fichier de cookies et chemin codé en dur dans `web_app.py`

## [1.5.0] - 2026-10-10

### Supprimé
- **Suppression de l'intégration Telegram** : envoi automatique des vidéos, création de topics, routes `/api/telegram/topics`, fichier de mapping des topics, documentation dédiée, dépendances `pyrogram` et `tgcrypto`, clés du fichier `config.json.example` et références dans la documentation et les scripts de déploiement
- Les entrées des versions précédentes mentionnant cette fonctionnalité sont conservées à titre d'historique et ne reflètent plus le comportement actuel

## [1.4.0] - 2025-11-22

### Ajouté
- **Système de métadonnées optimisé** (`metadata_manager.py`)
  - Vérifications O(1) au lieu de O(n) grâce aux sets Python
  - Cache en mémoire pour `is_slideshow()` (évite 99% des appels API)
  - Un seul fichier `metadata.json` au lieu de 3 (download_history.json, slideshows.json, videos.txt)
  - Métadonnées riches: type, date, taille, statut, tags, favoris, notes
  - Méthodes de recherche et filtrage (tags, favoris, recherche texte)
- **Pipeline de téléchargement ultra-rapide** (`pipeline_downloader.py`)
  - Architecture streaming avec 1 thread extraction + 3 threads téléchargement
  - Queue pour buffering et parallélisation
  - **Performance: 5-10x plus rapide** (100 vidéos: 13min → 2min)
  - Support des callbacks pour logs en temps réel
- **Export multi-format** (`export_data.py`)
  - Export CSV (compatible Excel)
  - Export JSON (backup complet avec statistiques)
  - Export HTML (rapport visuel avec graphiques)
- **Système de Tags & Favoris**
  - Ajouter/supprimer des tags sur les vidéos
  - Marquer comme favori
  - Ajouter des notes personnelles
  - Recherche par tags, favoris ou texte
- **Gestionnaire d'arrêt propre** (web_app.py)
  - Arrêt gracieux de tous les threads lors de la fermeture du serveur
  - Signal handlers (SIGINT, SIGTERM)
  - Nettoyage automatique via `atexit`
  - Timeout de 5 secondes pour terminer les tâches en cours
- **Protection encodage Windows**
  - Reconfiguration UTF-8 automatique sur Windows
  - Gestion des erreurs d'encodage dans `emit_log()`
  - Remplacement des caractères spéciaux (═ → =)
- **API endpoints supplémentaires**
  - `POST /api/tasks/clear` - Réinitialise toutes les tâches
  - `POST /api/task/<task_id>/reset` - Réinitialise une tâche spécifique
  - `POST /api/extract` - Extraction de liens en arrière-plan

### Modifié
- **Générateur streaming dans `get_video_links()`**
  - Changé de `return videos` à `yield video`
  - Permet de commencer le téléchargement **immédiatement** sans attendre l'extraction complète
  - Économie mémoire: O(1) au lieu de O(n)
- **Réorganisation complète de la documentation**
  - Suppression des fichiers obsolètes (analysis.md, explication_projet.md, LOGS_IMPROVEMENTS.md, AMELIORATIONS.md)
  - Création de `docs/README.md` comme index principal
  - Conservation uniquement de la documentation pertinente
- **Système de vérification des threads**
  - Utilisation de `thread.is_alive()` pour vérifier l'état réel
  - Dictionnaire `active_threads` pour stocker les références
  - Évite les faux positifs "Download already in progress"

### Corrigé
- 🐛 **Rectangle rouge fantôme dans l'interface web**
  - Vérification de `response.ok` avant d'afficher les notifications
  - Protection contre les messages vides/undefined
  - Meilleure gestion des erreurs API
- 🐛 **Erreurs d'encodage Windows**
  - Crashs avec `UnicodeEncodeError: 'charmap' codec can't encode`
  - Problèmes avec les caractères Unicode dans les logs
- 🐛 **Routes API manquantes** (404 errors)
  - Restauration de `/api/profiles`, `/api/download`, `/api/extract`, `/api/task/<task_id>`
  - Completion de la fonction `serve_video()`
- 🐛 **Slideshow downloads échouaient**
  - Mauvaise configuration de `base-directory` dans gallery-dl
  - Fichiers téléchargés dans le mauvais dossier

### Connu
- ⚠️ **Bug limite de téléchargement**: Le paramètre `limit` de l'interface web est ignoré
  - Cause: `limit` non passé à `background_download_task`
  - Workaround: Utiliser la ligne de commande avec `--limit`
  - Fichiers concernés: `web_app.py:405-822`

## [1.3.0] - 2025-11-22

### Modifié
- **Réorganisation du projet** : Nettoyage de la racine du projet
  - Déplacement de la documentation dans `docs/`
  - Déplacement des scripts utilitaires dans `scripts/`
  - Déplacement des tests dans `tests/`
  - Mise à jour des chemins dans les scripts et la documentation

## [1.2.0] - 2025-01-22

### Ajouté
- **Statistiques au début du téléchargement** : Tableau récapitulatif affiché avant de commencer
  - Informations sur le profil (plateforme, nombre de vidéos, etc.)
  - Configuration (mode, délais)
  - Prévisions (temps estimé, taille estimée)
- **Barre de progression simple** : Affichée toutes les minutes et à la fin
  - Format compact sur une seule ligne
  - Progression visuelle avec barre ASCII `[####····]`
  - Temps écoulé, temps restant, taille
  - Moins imposante et mieux alignée
- **Résumé final détaillé** : Statistiques complètes en fin de session
  - Taux de succès, durée totale, taille totale
  - Vitesse moyenne de téléchargement
  - Informations de stockage

### Modifié
- **Format des logs** : Nouveau format sobre `[HH:MM:SS] [NIVEAU] [MODULE] Message`
  - Niveaux : INFO, OK, WARN, ERROR
  - Modules : SCAN, DOWNLOAD, PROGRESS, STATS, SUMMARY, SYSTEM
- **Filtrage des slideshows** : Détectés et filtrés **avant** le comptage
  - Ne sont plus affichés dans les logs (traitement silencieux)
  - Mentionnés uniquement dans les statistiques initiales
- Messages de l'ancienne intégration de messagerie : réduction de la verbosité (intégration de messagerie supprimée en 1.5.0)

### Amélioré
- Cohérence visuelle dans tous les messages
- Lisibilité avec séparateurs et indentation
- Calcul automatique du temps restant et vitesse moyenne

## [1.1.0] - 2025-01-22

### Ajouté
- Bouton "Télécharger" vert dans l'interface web pour télécharger directement (sans passer par l'extraction)
- API de gestion manuelle des topics de l'ancienne intégration de messagerie (intégration de messagerie supprimée en 1.5.0)
- Documentation complète du déploiement VPS (`DEPLOYMENT.md`)
- Script d'installation automatique pour VPS (`deploy.sh`)
- Support Docker avec `Dockerfile` et `docker-compose.yml`
- Fichier de configuration exemple pour systemd (`tiktok-scraper.service`)
- Fichier de configuration exemple pour Nginx (`nginx.conf`)
- Guide de contribution dans le README
- Section "Technologies" dans le README
- Section "Améliorations futures" dans le README

### Corrigé
- 🐛 **Bug critique** : Topics en doublon lors de téléchargements parallèles dans l'ancienne intégration de messagerie (intégration de messagerie supprimée en 1.5.0)

### Amélioré
- Logs plus clairs avec émojis (✅, ❌, ⚠️)
- Documentation README plus complète avec Quick Start et table des matières
- Ajout de `gunicorn` dans les requirements pour la production

## [1.0.0] - 2025-01-20

### Ajouté
- Interface web Flask avec dashboard moderne
- Extraction de liens vidéos (mode extract_flat)
- Téléchargement de vidéos avec retry automatique
- Détection intelligente des slideshows TikTok
- Intégration de messagerie avec création automatique de topics (intégration de messagerie supprimée en 1.5.0)
- Mode incrémental (arrêt après 10 vidéos consécutives déjà connues)
- Support TikTok et YouTube Shorts
- Gestion d'historique JSON
- Logs en temps réel via Server-Sent Events (SSE)
- API REST complète
- Lecteur vidéo intégré dans l'interface
- Page détails profil avec statistiques
- Synchronisation des profils (bouton Sync)
- Suppression de profils via l'interface
- Anti-bannissement avec délais aléatoires configurables

---

## Types de changements

- `Ajouté` pour les nouvelles fonctionnalités.
- `Modifié` pour les changements aux fonctionnalités existantes.
- `Obsolète` pour les fonctionnalités qui seront bientôt supprimées.
- `Supprimé` pour les fonctionnalités supprimées.
- `Corrigé` pour les corrections de bugs.
- `Sécurité` pour les corrections de vulnérabilités.
